from skillup.config import Settings


def test_impostazioni_predefinite() -> None:
    s = Settings(_env_file=None)  # ignora il .env: controlliamo i valori di partenza
    assert s.top_k == 5
    assert s.llm_mode == "live"
    assert s.dimensioni == 1536
