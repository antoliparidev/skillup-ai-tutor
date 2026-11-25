"""Connessione async a Postgres e creazione delle tabelle."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from skillup.config import settings
from skillup.models import Base

engine = create_async_engine(settings.database_url)
Sessione = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Attiva pgvector e crea le tabelle che mancano (idempotente)."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)