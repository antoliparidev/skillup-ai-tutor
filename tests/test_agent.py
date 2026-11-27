"""L'agent loop con un modello finto: si verificano i guardrail, non la qualità."""

from typing import Any

import pytest

from skillup import agent, llm
from skillup.schemas import PassoPiano, PianoProposto


def _chiamata(nome: str, argomenti: str = '{"query": "docker"}') -> dict[str, Any]:
    return {"id": "c1", "type": "function", "function": {"name": nome, "arguments": argomenti}}


@pytest.fixture
def finto(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    stato: dict[str, Any] = {"risposte": [], "token": 100}

    async def chat_con_strumenti(*_: Any, **__: Any) -> dict[str, Any]:
        return {"messaggio": stato["risposte"].pop(0), "token": stato["token"]}

    async def strutturato(*_: Any, **__: Any) -> PianoProposto:
        return PianoProposto(
            obiettivo="o",
            passi=[
                PassoPiano(ordine=1, titolo="vero", link="https://x/vero", perche="p"),
                PassoPiano(ordine=2, titolo="inventato", link="https://x/finto", perche="p"),
            ],
        )

    async def cerca_pagine(_: Any, **__: Any) -> list[dict[str, str]]:
        return [{"pagina": "P", "sezione": "S", "link": "https://x/vero", "estratto": "e"}]

    async def corsi(_: Any) -> list[str]:
        return ["99_corso-inventato"]

    monkeypatch.setattr(llm, "chat_con_strumenti", chat_con_strumenti)
    monkeypatch.setattr(llm, "strutturato", strutturato)
    monkeypatch.setitem(agent.STRUMENTI, "cerca_pagine", cerca_pagine)
    monkeypatch.setattr(agent, "corsi_disponibili", corsi)
    monkeypatch.setattr(agent, "prompt", lambda _: "prompt di prova")
    return stato


async def test_si_ferma_al_limite_di_passi(finto: dict[str, Any]) -> None:
    finto["risposte"] = [{"role": "assistant", "tool_calls": [_chiamata("cerca_pagine")]}] * 3
    esito = await agent.pianifica(None, "docker", max_passi=1)  # type: ignore[arg-type]
    assert esito.motivo == "limite_passi" and esito.piano is None


async def test_si_ferma_quando_finisce_il_budget(finto: dict[str, Any]) -> None:
    finto["token"] = 999
    finto["risposte"] = [{"role": "assistant", "tool_calls": [_chiamata("cerca_pagine")]}]
    esito = await agent.pianifica(None, "docker", budget=500)  # type: ignore[arg-type]
    assert esito.motivo == "budget"


async def test_strumento_non_permesso_non_viene_eseguito(finto: dict[str, Any]) -> None:
    link: set[str] = set()
    out = await agent._esegui(None, _chiamata("cancella_tutto"), link)  # type: ignore[arg-type]
    assert "non permesso" in out


async def test_piano_tiene_solo_i_link_visti(finto: dict[str, Any]) -> None:
    finto["risposte"] = [
        {"role": "assistant", "tool_calls": [_chiamata("cerca_pagine")]},
        {"role": "assistant", "content": "pronto"},
    ]
    esito = await agent.pianifica(None, "docker")  # type: ignore[arg-type]
    assert esito.motivo == "completato" and esito.piano is not None
    assert [p.link for p in esito.piano.passi] == ["https://x/vero"]