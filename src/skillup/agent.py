"""L'agente che propone un piano di studi: un agent loop scritto a mano.

Guardrail nel codice, non nel prompt:
  - strumenti permessi: solo quelli in STRUMENTI, tutti in sola lettura;
  - limite di passi: settings.agente_max_passi;
  - budget: settings.agente_budget_token;
  - il piano esce «proposto»: lo approva una persona (api.py).
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from skillup import llm
from skillup.config import settings
from skillup.log import traccia
from skillup.models import Chunk
from skillup.prompts import prompt
from skillup.rag import cerca
from skillup.schemas import PianoProposto

Risultato = list[dict[str, str]]

# --- gli strumenti (sola lettura) --------------------------------------------------------


async def cerca_pagine(s: AsyncSession, query: str, corso_id: str | None = None) -> Risultato:
    passaggi = await cerca(s, query, corso_id)
    return [
        {
            "pagina": p.chunk.pagina,
            "sezione": p.chunk.sezione,
            "link": p.chunk.link,
            "estratto": p.chunk.testo[:300],
        }
        for p in passaggi
    ]


async def elenco_pagine_corso(s: AsyncSession, corso_id: str) -> Risultato:
    query = (
        select(Chunk.file, Chunk.sezione, Chunk.pagina, Chunk.link)
        .where(Chunk.corso_id == corso_id)
        .distinct()
        .order_by(Chunk.file)
        .limit(80)
    )
    righe = (await s.execute(query)).all()
    return [{"sezione": r.sezione, "pagina": r.pagina, "link": r.link} for r in righe]


STRUMENTI: dict[str, Callable[..., Awaitable[Risultato]]] = {
    "cerca_pagine": cerca_pagine,
    "elenco_pagine_corso": elenco_pagine_corso,
}

SCHEMI_STRUMENTI: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "cerca_pagine",
            "description": "Cerca nel materiale dei corsi le pagine più pertinenti a un argomento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "l'argomento da cercare"},
                    "corso_id": {
                        "type": "string",
                        "description": "facoltativo, es. 02_docker-devops",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "elenco_pagine_corso",
            "description": "Elenca in ordine le pagine di un corso, con sezione e link.",
            "parameters": {
                "type": "object",
                "properties": {"corso_id": {"type": "string"}},
                "required": ["corso_id"],
            },
        },
    },
]

# --- il loop -----------------------------------------------------------------------------


@dataclass
class EsitoAgente:
    motivo: Literal["completato", "limite_passi", "budget"]
    piano: PianoProposto | None
    passi: int
    token: int
    traccia: list[dict[str, Any]] = field(default_factory=list)


async def _esegui(s: AsyncSession, chiamata: dict[str, Any], link_visti: set[str]) -> str:
    nome = chiamata["function"]["name"]
    if nome not in STRUMENTI:
        return json.dumps({"errore": f"strumento non permesso: {nome}"})
    try:
        argomenti = json.loads(chiamata["function"].get("arguments") or "{}")
        risultato = await STRUMENTI[nome](s, **argomenti)
    except (json.JSONDecodeError, TypeError) as e:
        return json.dumps({"errore": f"argomenti non validi: {e}"})
    link_visti.update(r["link"] for r in risultato if r.get("link"))
    return json.dumps(risultato, ensure_ascii=False)


async def corsi_disponibili(s: AsyncSession) -> list[str]:
    righe = (await s.execute(select(Chunk.corso_id, Chunk.corso).distinct())).all()
    return [f"{r.corso_id} ({r.corso})" for r in righe]


async def pianifica(
    s: AsyncSession,
    obiettivo: str,
    max_passi: int | None = None,
    budget: int | None = None,
) -> EsitoAgente:
    max_passi = max_passi or settings.agente_max_passi
    budget = budget or settings.agente_budget_token
    corsi = ", ".join(await corsi_disponibili(s))
    messaggi: list[dict[str, Any]] = [
        {"role": "system", "content": prompt("piano")},
        {"role": "user", "content": f"Corsi disponibili: {corsi}\n\nOBIETTIVO: {obiettivo}"},
    ]
    link_visti: set[str] = set()
    token = 0
    passi: list[dict[str, Any]] = []

    for passo in range(1, max_passi + 1):
        t = perf_counter()
        r = await llm.chat_con_strumenti(messaggi, SCHEMI_STRUMENTI)
        token += int(r["token"])
        messaggio = r["messaggio"]
        messaggi.append(messaggio)
        chiamate = messaggio.get("tool_calls") or []
        voce = {
            "passo": passo,
            "strumenti": [c["function"]["name"] for c in chiamate],
            "token": token,
            "ms": round((perf_counter() - t) * 1000),
        }
        passi.append(voce)
        traccia("agente.passo", **voce)

        if token > budget:
            return EsitoAgente("budget", None, passo, token, passi)

        if not chiamate:  # il modello ha finito di cercare: ora il piano, tipizzato
            messaggi.append(
                {
                    "role": "user",
                    "content": "Ora scrivi il piano finale. Usa SOLO link comparsi nei "
                    "risultati degli strumenti.",
                }
            )
            piano = await llm.strutturato(messaggi, PianoProposto)
            # verifica dal codice: via i passi con un link che gli strumenti non hanno mai dato
            piano.passi = [p for p in piano.passi if p.link in link_visti]
            return EsitoAgente("completato", piano, passo, token, passi)

        for c in chiamate:
            risultato = await _esegui(s, c, link_visti)
            messaggi.append({"role": "tool", "tool_call_id": c["id"], "content": risultato})

    return EsitoAgente("limite_passi", None, max_passi, token, passi)