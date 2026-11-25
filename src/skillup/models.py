"""Le tabelle del database."""

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Index, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from skillup.config import settings


class Base(DeclarativeBase):
    pass


class Chunk(Base):
    """Un pezzo di una pagina del corso, con il suo vettore e i dati per citarla."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    corso_id: Mapped[str] = mapped_column(String(100), index=True)  # es. 02_docker-devops
    corso: Mapped[str] = mapped_column(String(300))
    sezione: Mapped[str] = mapped_column(String(300))
    pagina: Mapped[str] = mapped_column(String(300))
    titolo: Mapped[str] = mapped_column(String(300))  # il paragrafo dentro la pagina
    link: Mapped[str] = mapped_column(String(300))
    file: Mapped[str] = mapped_column(String(300))
    testo: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(Vector(settings.dimensioni))

    __table_args__ = (
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Piano(Base):
    """Un piano di studi proposto dall'agente. Lo approva una persona."""

    __tablename__ = "piani"

    id: Mapped[int] = mapped_column(primary_key=True)
    obiettivo: Mapped[str] = mapped_column(Text)
    stato: Mapped[str] = mapped_column(String(20))  # proposto | approvato | fallito
    motivo_fine: Mapped[str] = mapped_column(String(30))
    contenuto: Mapped[dict[str, Any]] = mapped_column(JSON)
    creato: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())