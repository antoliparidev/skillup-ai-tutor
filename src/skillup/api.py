"""Il servizio FastAPI. Avvio: uv run uvicorn skillup.api:app --reload"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from skillup.agent import pianifica
from skillup.db import Sessione, init_db
from skillup.log import configura_log, traccia
from skillup.models import Piano
from skillup.rag import rispondi
from skillup.schemas import DomandaChat, PianoOut, PianoProposto, RichiestaPiano, RispostaChat


@asynccontextmanager
async def ciclo_di_vita(_: FastAPI) -> AsyncIterator[None]:
    configura_log()
    await init_db()
    yield


app = FastAPI(title="SkillUp AI Tutor", lifespan=ciclo_di_vita)


async def sessione() -> AsyncIterator[AsyncSession]:
    async with Sessione() as s:
        yield s


Db = Annotated[AsyncSession, Depends(sessione)]


@app.middleware("http")
async def latenza(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    t = perf_counter()
    risposta = await call_next(request)
    ms = round((perf_counter() - t) * 1000)
    traccia("http", metodo=request.method, path=request.url.path, stato=risposta.status_code, ms=ms)
    return risposta


@app.get("/healthz")
async def healthz(s: Db) -> dict[str, str]:
    await s.execute(text("SELECT 1"))
    return {"stato": "ok"}


@app.post("/chat")
async def chat(d: DomandaChat, s: Db) -> RispostaChat:
    return await rispondi(s, d.domanda, d.corso_id)


def _out(p: Piano) -> PianoOut:
    piano = p.contenuto.get("piano")
    return PianoOut(
        id=p.id,
        stato=p.stato,
        motivo_fine=p.motivo_fine,
        piano=PianoProposto.model_validate(piano) if piano else None,
        passi_agente=int(p.contenuto.get("passi", 0)),
        token=int(p.contenuto.get("token", 0)),
    )


@app.post("/piani", status_code=201)
async def crea_piano(r: RichiestaPiano, s: Db) -> PianoOut:
    esito = await pianifica(s, r.obiettivo)
    p = Piano(
        obiettivo=r.obiettivo,
        stato="proposto" if esito.piano else "fallito",
        motivo_fine=esito.motivo,
        contenuto={
            "piano": esito.piano.model_dump() if esito.piano else None,
            "passi": esito.passi,
            "token": esito.token,
            "traccia": esito.traccia,
        },
    )
    s.add(p)
    await s.commit()
    return _out(p)


@app.get("/piani/{piano_id}")
async def leggi_piano(piano_id: int, s: Db) -> PianoOut:
    p = await s.get(Piano, piano_id)
    if p is None:
        raise HTTPException(404, "piano non trovato")
    return _out(p)


@app.post("/piani/{piano_id}/approva")
async def approva_piano(piano_id: int, s: Db) -> PianoOut:
    """Human in the loop: è una persona a confermare il piano proposto dall'agente."""
    p = await s.get(Piano, piano_id)
    if p is None:
        raise HTTPException(404, "piano non trovato")
    if p.stato != "proposto":
        raise HTTPException(409, f"si approva solo un piano proposto, questo è {p.stato}")
    p.stato = "approvato"
    await s.commit()
    traccia("piano.approvato", id=p.id)
    return _out(p)