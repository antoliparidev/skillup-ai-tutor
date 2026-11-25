"""Il RAG: cerca i passaggi più simili alla domanda e fa rispondere il modello solo su quelli.
    Seconda fase del RAG ovvero la risposta. 
    domanda -> cerca nel db -> risposta
"""

from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from skillup import llm
from skillup.config import settings
from skillup.log import traccia
from skillup.models import Chunk
from skillup.prompts import prompt
from skillup.schemas import Fonte, RispostaChat, RispostaModello

NON_LO_SO = "Non lo so: nel materiale dei corsi non trovo informazioni su questa domanda."


@dataclass
class Passaggio:
    numero: int
    chunk: Chunk
    similarita: float


def _ms(inizio: float) -> int:
    return round((perf_counter() - inizio) * 1000)


async def cerca(
    s: AsyncSession, domanda: str, corso_id: str | None = None, k: int | None = None
) -> list[Passaggio]:
    """I k passaggi più vicini alla domanda. Il filtro per corso sta nel WHERE della query."""
    [vettore] = await llm.embed([f"search_query: {domanda}"])
    distanza = Chunk.embedding.cosine_distance(vettore)
    query = select(Chunk, distanza.label("distanza")).order_by(distanza).limit(k or settings.top_k)
    if corso_id:
        query = query.where(Chunk.corso_id == corso_id)
    righe = (await s.execute(query)).all()
    return [Passaggio(i + 1, c, 1 - float(d)) for i, (c, d) in enumerate(righe)]


def _non_lo_so(recuperati: list[str], ms: dict[str, int]) -> RispostaChat:
    return RispostaChat(risposta=NON_LO_SO, fonti=[], non_lo_so=True, recuperati=recuperati, ms=ms)


async def rispondi(s: AsyncSession, domanda: str, corso_id: str | None = None) -> RispostaChat:
    ms: dict[str, int] = {}

    t = perf_counter()
    passaggi = await cerca(s, domanda, corso_id)
    ms["retrieve"] = _ms(t)
    recuperati = [p.chunk.file for p in passaggi]
    migliore = passaggi[0].similarita if passaggi else 0.0
    traccia("rag.retrieve", ms=ms["retrieve"], migliore=round(migliore, 3), file=recuperati)

    # 1° «non lo so»: nessun passaggio abbastanza simile, il modello non lo chiamiamo nemmeno
    if migliore < settings.soglia_similarita:
        traccia("rag.non_lo_so", motivo="sotto_soglia")
        return _non_lo_so(recuperati, ms)

    contesto = "\n\n".join(
        f"[{p.numero}] {p.chunk.pagina} › {p.chunk.titolo}\n{p.chunk.testo}" for p in passaggi
    )
    messaggi = [
        {"role": "system", "content": prompt("chat")},
        {"role": "user", "content": f"PASSAGGI:\n{contesto}\n\nDOMANDA: {domanda}"},
    ]
    t = perf_counter()
    out = await llm.strutturato(messaggi, RispostaModello)
    ms["llm"] = _ms(t)
    traccia("rag.llm", ms=ms["llm"], non_lo_so=out.non_lo_so, fonti=out.fonti_usate)

    # le fonti le costruisce il CODICE dai numeri: il modello non può inventare un link
    per_numero = {p.numero: p for p in passaggi}
    fonti: dict[str, Fonte] = {}
    for n in out.fonti_usate:
        if n in per_numero:
            c = per_numero[n].chunk
            fonti.setdefault(
                c.link, Fonte(pagina=c.pagina, sezione=c.sezione, link=c.link, file=c.file)
            )

    # 2° «non lo so»: lo dice il modello, oppure risponde senza citare nessuna fonte valida
    if out.non_lo_so or not fonti:
        traccia("rag.non_lo_so", motivo="modello" if out.non_lo_so else "nessuna_fonte")
        return _non_lo_so(recuperati, ms)

    return RispostaChat(
        risposta=out.risposta,
        fonti=list(fonti.values()),
        non_lo_so=False,
        recuperati=recuperati,
        ms=ms,
    )