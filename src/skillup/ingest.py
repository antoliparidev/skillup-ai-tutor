"""Indicizzazione: pagine .md → frontmatter → paragrafi → vettori → Postgres.

Uso:  uv run python -m skillup.ingest            (salta se l'indice c'è già)
      uv run python -m skillup.ingest --forza    (cancella e rifà)

      Questa è la prima fase del RAG PREPARARE I DATI (Fatta una sola volta)
      pagine → chunk → vettori → database 
"""

import argparse
import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete, func, select

from skillup import llm
from skillup.config import settings
from skillup.db import Sessione, init_db
from skillup.log import configura_log, traccia
from skillup.models import Chunk

MAX_CARATTERI = 2500  # un paragrafo più lungo si divide, ma mai dentro un blocco di codice
MIN_CARATTERI = 40  # pezzi più corti (un titolo da solo) non servono
LOTTO = 32  # quanti testi per chiamata di embedding

TITOLO = re.compile(r"^#{2,3}\s+(.+)$")
SUMMARY = re.compile(r"<summary>(.*?)</summary>")


@dataclass
class Pezzo:
    titolo: str
    testo: str


def leggi_frontmatter(testo: str) -> tuple[dict[str, Any], str]:
    """Separa i dati fra le due righe --- in testa al file dal corpo della pagina."""
    if not testo.startswith("---"):
        return {}, testo
    _, fm, corpo = testo.split("---", 2)
    dati = yaml.safe_load(fm) or {}
    return dati, corpo


def _apre_o_chiude_codice(riga: str) -> bool:
    return riga.lstrip().startswith("```")


def _blocchi(testo: str) -> list[str]:
    """Paragrafi separati da righe vuote; un blocco di codice resta sempre intero."""
    blocchi: list[str] = []
    corrente: list[str] = []
    in_codice = False
    for riga in testo.splitlines():
        if _apre_o_chiude_codice(riga):
            in_codice = not in_codice
        if not riga.strip() and not in_codice:
            if corrente:
                blocchi.append("\n".join(corrente))
                corrente = []
        else:
            corrente.append(riga)
    if corrente:
        blocchi.append("\n".join(corrente))
    return blocchi


def _per_righe(blocco: str) -> list[str]:
    """Un blocco lungo che NON è codice (es. una tabella) si divide per righe."""
    if len(blocco) <= MAX_CARATTERI or blocco.lstrip().startswith("```"):
        return [blocco]
    parti: list[str] = []
    corrente = ""
    for riga in blocco.splitlines():
        if corrente and len(corrente) + len(riga) + 1 > MAX_CARATTERI:
            parti.append(corrente)
            corrente = riga
        else:
            corrente = f"{corrente}\n{riga}" if corrente else riga
    return [*parti, corrente] if corrente else parti


def _spezza(testo: str) -> list[str]:
    if len(testo) <= MAX_CARATTERI:
        return [testo]
    parti: list[str] = []
    corrente = ""
    for blocco in (p for b in _blocchi(testo) for p in _per_righe(b)):
        if corrente and len(corrente) + len(blocco) + 2 > MAX_CARATTERI:
            parti.append(corrente)
            corrente = blocco
        else:
            corrente = f"{corrente}\n\n{blocco}" if corrente else blocco
    if corrente:
        parti.append(corrente)
    return [p for p in parti if len(p) >= MIN_CARATTERI]


def dividi(corpo: str, titolo_pagina: str) -> list[Pezzo]:
    """Divide la pagina ai titoli ## e ### e ai <summary> degli accordion, mai dentro il codice."""
    pezzi: list[Pezzo] = []
    titolo, in_codice = titolo_pagina, False
    righe: list[str] = []

    def chiudi() -> None:
        testo = "\n".join(righe).strip()
        if len(testo) >= MIN_CARATTERI:
            pezzi.extend(Pezzo(titolo, parte) for parte in _spezza(testo))

    for riga in corpo.splitlines():
        if _apre_o_chiude_codice(riga):
            in_codice = not in_codice
        nuovo = None
        if not in_codice:
            if m := TITOLO.match(riga):
                nuovo = m.group(1).strip()
            elif m := SUMMARY.search(riga):
                nuovo = m.group(1).strip()
        if nuovo is not None:
            chiudi()
            titolo, righe = nuovo, [riga]
        else:
            righe.append(riga)
    chiudi()
    return pezzi


def trova_pagine(cartella: Path) -> list[Path]:
    """Tutti i .md tranne gli allegati (lì ci sono mock d'esame e materiali da scaricare)."""
    pagine = [p for p in cartella.rglob("*.md") if "allegati" not in p.parts]
    return sorted(pagine, key=lambda p: p.relative_to(cartella).as_posix())


def prepara(cartella: Path) -> list[dict[str, Any]]:
    """Le righe da inserire, senza i vettori."""
    righe: list[dict[str, Any]] = []
    for pagina in trova_pagine(cartella):
        fm, corpo = leggi_frontmatter(pagina.read_text(encoding="utf-8-sig"))
        if "corso" not in fm:  # non è una pagina del corso (es. un file di appunti)
            continue
        relativo = pagina.relative_to(cartella).as_posix()
        for pezzo in dividi(corpo, str(fm.get("pagina", ""))):
            righe.append(
                {
                    "corso_id": relativo.split("/")[0],
                    "corso": str(fm["corso"]),
                    "sezione": str(fm.get("sezione", "")),
                    "pagina": str(fm.get("pagina", "")),
                    "titolo": pezzo.titolo[:300],
                    "link": str(fm.get("link", "")),
                    "file": relativo,
                    "testo": pezzo.testo,
                }
            )
    return righe


def testo_da_indicizzare(r: dict[str, Any]) -> str:
    # nomic-embed-text vuole il prefisso «search_document:» per i documenti
    return f"search_document: {r['corso']} › {r['pagina']} › {r['titolo']}\n\n{r['testo']}"


async def indicizza(cartella: Path, forza: bool = False, corsi: set[str] | None = None) -> int:
    """Indicizza le pagine che mancano. Una pagina alla volta: se interrompi, riparte da lì."""
    await init_db()
    async with Sessione() as s:
        if forza:
            await s.execute(delete(Chunk))
            await s.commit()
        gia_fatti = set((await s.scalars(select(Chunk.file).distinct())).all())
        per_file: dict[str, list[dict[str, Any]]] = {}
        for r in prepara(cartella):
            if r["file"] not in gia_fatti and (not corsi or r["corso_id"] in corsi):
                per_file.setdefault(r["file"], []).append(r)
        totale = sum(len(g) for g in per_file.values())
        traccia("ingest.inizio", pagine_presenti=len(gia_fatti), pagine=len(per_file), chunk=totale)
        fatti = 0
        for n, gruppo in enumerate(per_file.values(), start=1):
            for i in range(0, len(gruppo), LOTTO):
                lotto = gruppo[i : i + LOTTO]
                vettori = await llm.embed([testo_da_indicizzare(r) for r in lotto])
                s.add_all(Chunk(**r, embedding=v) for r, v in zip(lotto, vettori, strict=True))
            await s.commit()  # pagina salvata: è il punto da cui si riparte
            fatti += len(gruppo)
            traccia("ingest.pagina", pagina=n, di=len(per_file), chunk=fatti, totale=totale)
        presenti = await s.scalar(select(func.count()).select_from(Chunk)) or 0
        return int(presenti)


def main() -> None:
    configura_log()
    parser = argparse.ArgumentParser(description="Indicizza il materiale dei corsi")
    parser.add_argument("--cartella", type=Path, default=settings.materiale_dir)
    parser.add_argument("--forza", action="store_true", help="cancella l'indice e lo rifà")
    parser.add_argument("--corsi", default=settings.corsi, help="es. 02_docker-devops,03_...")
    args = parser.parse_args()
    corsi = {c.strip() for c in args.corsi.split(",") if c.strip()} or None
    n = asyncio.run(indicizza(args.cartella, args.forza, corsi))
    print(f"Indice pronto: {n} chunk in totale")


if __name__ == "__main__":
    main()