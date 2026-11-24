# SkillUp AI Tutor

Chat RAG sui corsi SkillUp con fonte citata, agente che propone un piano di studi
(approvato da una persona) e server MCP. Project Work AI Engineer.

## Comandi
- Test e qualità: `uv run ruff check . && uv run mypy src tests && uv run pytest -q`
- Servizio: `uv run uvicorn skillup.api:app --reload` (Swagger su /docs)
- Indicizzazione: `uv run python -m skillup.ingest [--forza]`
- Misura: `uv run python -m skillup.valuta --golden eval/golden.jsonl --out eval/results/vN.json`
- Tutto in Docker: `docker compose up --build`

## Regole
- Il materiale dei corsi sta FUORI dal repository (`MATERIALE_DIR` nel `.env`). Mai copiarlo qui.
- In CI solo `sample_data/` (inventato) e risposte registrate (`LLM_MODE=replay`).
- I prompt stanno in `prompts/`: se ne cambi uno, rilancia la misura e registra di nuovo.
- Tutte le chiamate al modello passano da `src/skillup/llm.py`.
- Gli strumenti dell'agente sono in sola lettura: l'agente propone, la persona approva.
- Python 3.12, tipi ovunque (`mypy --strict`), commenti in italiano.