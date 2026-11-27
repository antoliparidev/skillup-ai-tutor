"""La misura: golden dataset → metriche → (facoltativo) gate che fa fallire.

Misura:    uv run python -m skillup.valuta --golden eval/golden.jsonl --out eval/results/v1.json
Gate (CI): aggiungi --soglie eval/soglie_ci.json
Taratura:  uv run python -m skillup.valuta --taratura eval/taratura.jsonl --out eval/results/v1.json
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from skillup import llm
from skillup.db import Sessione
from skillup.prompts import prompt
from skillup.rag import rispondi
from skillup.schemas import Giudizio


def leggi_jsonl(file: Path) -> list[dict[str, Any]]:
    righe = file.read_text(encoding="utf-8").splitlines()
    return [json.loads(r) for r in righe if r.strip()]


async def giudica(domanda: str, attesa: str, data: str) -> Giudizio:
    messaggi = [
        {"role": "system", "content": prompt("giudice")},
        {
            "role": "user",
            "content": f"DOMANDA: {domanda}\n\nRISPOSTA ATTESA: {attesa}\n\nRISPOSTA DATA: {data}",
        },
    ]
    return await llm.strutturato(messaggi, Giudizio)


async def valuta(casi: list[dict[str, Any]]) -> dict[str, Any]:
    dettagli: list[dict[str, Any]] = []
    async with Sessione() as s:
        for caso in casi:
            t = perf_counter()
            r = await rispondi(s, caso["domanda"], caso.get("corso_id"))
            ms = round((perf_counter() - t) * 1000)
            fuori = bool(caso.get("fuori_perimetro"))
            riga: dict[str, Any] = {
                "id": caso["id"],
                "fuori_perimetro": fuori,
                "non_lo_so": r.non_lo_so,
                "non_lo_so_corretto": r.non_lo_so == fuori,
                "ms": ms,
            }
            if not fuori:
                attesi = set(caso["file_attesi"])
                riga["recall_at_5"] = 1.0 if attesi & set(r.recuperati) else 0.0
                if r.non_lo_so:
                    riga["voto"], riga["motivo"] = 0.0, "ha detto non lo so"
                else:
                    g = await giudica(caso["domanda"], caso["risposta_attesa"], r.risposta)
                    riga["voto"], riga["motivo"] = g.voto, g.motivo
            riga["risposta"] = r.risposta
            dettagli.append(riga)
            print(f"{caso['id']}: {json.dumps({k: v for k, v in riga.items() if k != 'risposta'})}")

    dentro = [d for d in dettagli if not d["fuori_perimetro"]]
    metriche = {
        "casi": len(dettagli),
        "recall_at_5": round(mean(d["recall_at_5"] for d in dentro), 3) if dentro else None,
        "voto_giudice": round(mean(d["voto"] for d in dentro), 3) if dentro else None,
        "accuratezza_non_lo_so": round(mean(d["non_lo_so_corretto"] for d in dettagli), 3),
        "latenza_media_ms": round(mean(d["ms"] for d in dettagli)),
    }
    return {"metriche": metriche, "dettagli": dettagli}


def controlla_soglie(metriche: dict[str, Any], soglie: dict[str, float]) -> list[str]:
    return [
        f"{nome}: {metriche.get(nome)} < {minimo}"
        for nome, minimo in soglie.items()
        if metriche.get(nome) is None or metriche[nome] < minimo
    ]


def taratura(file_umano: Path, file_risultati: Path) -> None:
    """Confronta il voto del giudice con il tuo, caso per caso."""
    umani = {r["id"]: float(r["voto_umano"]) for r in leggi_jsonl(file_umano)}
    giudice = {
        d["id"]: d["voto"]
        for d in json.loads(file_risultati.read_text(encoding="utf-8"))["dettagli"]
        if "voto" in d
    }
    comuni = [i for i in umani if i in giudice]
    differenze = [abs(umani[i] - giudice[i]) for i in comuni]
    d_accordo = sum(d <= 0.25 for d in differenze)
    for i in comuni:
        print(f"{i}: tu {umani[i]}  giudice {giudice[i]}")
    print(
        f"Casi: {len(comuni)} · differenza media {mean(differenze):.2f} · "
        f"d'accordo (±0.25) {d_accordo}/{len(comuni)}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Misura la qualità di SkillUp AI Tutor")
    p.add_argument("--golden", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--soglie", type=Path, help="se c'è, sotto soglia esce con errore (gate)")
    p.add_argument("--taratura", type=Path, help="file con i tuoi voti, da confrontare")
    args = p.parse_args()

    if args.taratura:
        taratura(args.taratura, args.out)
        return

    risultato = asyncio.run(valuta(leggi_jsonl(args.golden)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(risultato, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(risultato["metriche"], indent=2))

    if args.soglie:
        soglie = json.loads(args.soglie.read_text(encoding="utf-8"))
        errori = controlla_soglie(risultato["metriche"], soglie)
        if errori:
            print("GATE FALLITO:\n  " + "\n  ".join(errori))
            sys.exit(1)
        print("GATE SUPERATO")


if __name__ == "__main__":
    main()