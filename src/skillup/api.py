"""Il servizio FastAPI. Avvio: uv run uvicorn skillup.api:app --reload"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from skillup.db import Sessione, init_db
from skillup.log import configura_log, traccia
from skillup.rag import rispondi
from skillup.schemas import DomandaChat, RispostaChat


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