"""L'unico punto che parla con il modello.

Tre funzioni: embed, strutturato (output tipizzato con Instructor) e chat_con_strumenti.
Ognuna passa dal «registro»: in modalità record salva la risposta su file, in replay la
rilegge senza chiamare il modello. È così che la pipeline misura senza modello.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel

from skillup.config import settings

_client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=180, max_retries=2)
_instructor = instructor.from_openai(_client)


class RegistrazioneMancante(RuntimeError):
    """In replay manca la risposta registrata: è cambiato un prompt, un dato o il codice."""


async def _con_registro(tipo: str, richiesta: Any, chiama: Callable[[], Awaitable[Any]]) -> Any:
    if settings.llm_mode == "live":
        return await chiama()
    testo = json.dumps(richiesta, sort_keys=True, ensure_ascii=False)
    chiave = hashlib.sha256(testo.encode()).hexdigest()[:24]
    file = settings.recordings_dir / f"{tipo}-{chiave}.json"
    if settings.llm_mode == "replay":
        if not file.exists():
            raise RegistrazioneMancante(f"manca {file}: rilancia in modalità record")
        return json.loads(file.read_text(encoding="utf-8"))
    risultato = await chiama()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(risultato, ensure_ascii=False), encoding="utf-8")
    return risultato


async def embed(testi: list[str]) -> list[list[float]]:
    """Trasforma ogni testo in un vettore di numeri."""

    async def chiama() -> list[list[float]]:
        r = await _client.embeddings.create(model=settings.modello_embedding, input=testi)
        return [d.embedding for d in r.data]

    richiesta = {"modello": settings.modello_embedding, "testi": testi}
    vettori: list[list[float]] = await _con_registro("embed", richiesta, chiama)
    return vettori


async def strutturato[M: BaseModel](messaggi: list[dict[str, Any]], modello: type[M]) -> M:
    """Chiede al modello una risposta che rispetta lo schema Pydantic `modello`."""

    async def chiama() -> dict[str, Any]:
        r = await _instructor.chat.completions.create(
            model=settings.modello_chat,
            response_model=modello,
            messages=messaggi,  # type: ignore[arg-type]
            max_retries=2,
        )
        return r.model_dump()

    richiesta = {"modello": settings.modello_chat, "schema": modello.__name__, "msg": messaggi}
    return modello.model_validate(await _con_registro("chat", richiesta, chiama))


async def chat_con_strumenti(
    messaggi: list[dict[str, Any]], strumenti: list[dict[str, Any]]
) -> dict[str, Any]:
    """Un giro dell'agente: il modello risponde oppure chiede di usare uno strumento."""

    async def chiama() -> dict[str, Any]:
        r = await _client.chat.completions.create(
            model=settings.modello_chat,
            messages=messaggi,  # type: ignore[arg-type]
            tools=strumenti,  # type: ignore[arg-type]
        )
        messaggio = r.choices[0].message.model_dump(exclude_none=True)
        messaggio.setdefault("content", "")  # con i tool_calls è None: Instructor lo vuole
        return {
            "messaggio": messaggio,
            "token": r.usage.total_tokens if r.usage else 0,
        }

    richiesta = {"modello": settings.modello_chat, "msg": messaggi, "tools": strumenti}
    risultato: dict[str, Any] = await _con_registro("tools", richiesta, chiama)
    return risultato