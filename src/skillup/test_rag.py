"""Il RAG con un modello finto: nessuna chiamata vera, nessun database."""

from typing import Any

import pytest

from skillup import llm, rag
from skillup.models import Chunk
from skillup.rag import Passaggio
from skillup.schemas import RispostaModello


def _passaggio(n: int, similarita: float) -> Passaggio:
    c = Chunk(
        corso_id="99",
        corso="C",
        sezione="S",
        pagina=f"P{n}",
        titolo="T",
        link=f"https://x/{n}",
        file=f"f{n}.md",
        testo="testo",
    )
    return Passaggio(n, c, similarita)


@pytest.fixture
def finto(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    stato: dict[str, Any] = {"passaggi": [], "risposta": None, "chiamate_llm": 0}

    async def cerca(*_: Any, **__: Any) -> list[Passaggio]:
        return list(stato["passaggi"])

    async def strutturato(*_: Any, **__: Any) -> RispostaModello:
        stato["chiamate_llm"] += 1
        risposta: RispostaModello = stato["risposta"]
        return risposta

    monkeypatch.setattr(rag, "cerca", cerca)
    monkeypatch.setattr(llm, "strutturato", strutturato)
    monkeypatch.setattr(rag, "prompt", lambda _: "prompt di prova")
    return stato


async def test_sotto_soglia_non_lo_so_senza_chiamare_il_modello(finto: dict[str, Any]) -> None:
    finto["passaggi"] = [_passaggio(1, 0.1)]
    r = await rag.rispondi(None, "chi ha vinto lo scudetto?")  # type: ignore[arg-type]
    assert r.non_lo_so and r.fonti == []
    assert finto["chiamate_llm"] == 0


async def test_le_fonti_le_costruisce_il_codice(finto: dict[str, Any]) -> None:
    finto["passaggi"] = [_passaggio(1, 0.9), _passaggio(2, 0.8)]
    # il modello cita il passaggio 2 e un passaggio 7 che non esiste
    finto["risposta"] = RispostaModello(risposta="ok", fonti_usate=[2, 7], non_lo_so=False)
    r = await rag.rispondi(None, "domanda")  # type: ignore[arg-type]
    assert not r.non_lo_so
    assert [f.link for f in r.fonti] == ["https://x/2"]


async def test_risposta_senza_fonti_diventa_non_lo_so(finto: dict[str, Any]) -> None:
    finto["passaggi"] = [_passaggio(1, 0.9)]
    finto["risposta"] = RispostaModello(risposta="inventata", fonti_usate=[], non_lo_so=False)
    r = await rag.rispondi(None, "domanda")  # type: ignore[arg-type]
    assert r.non_lo_so