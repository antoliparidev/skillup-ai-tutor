"""Le impostazioni del servizio: si leggono dall'ambiente e dal file .env."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # database (porta 5433 sul PC: la 5432 può essere occupata da altri progetti)
    database_url: str = "postgresql+asyncpg://skillup:skillup@localhost:5433/skillup"

    # dove sta il materiale da indicizzare: FUORI dal repository
    materiale_dir: Path = Path("sample_data")
    corsi: str = "02_docker-devops"  # vuoto = tutti; es. "02_docker-devops,03_python-foundations"

    # modello: l'SDK OpenAI legge OPENAI_BASE_URL dall'ambiente (l'adattatore del corso)
    openai_api_key: str = "locale"
    modello_chat: str = "gpt-4o-mini"
    modello_embedding: str = "text-embedding-3-small"
    dimensioni: int = 1536

    # RAG
    top_k: int = 5
    soglia_similarita: float = (
        0.5  # sotto questa soglia: «non lo so» senza chiamare il modello
    )

    # agente: i guardrail
    agente_max_passi: int = 6
    agente_budget_token: int = (
        150_000  # la strada OpenCode aggiunge ~10k token a richiesta
    )

    # live = modello vero · record = modello vero + salva · replay = solo risposte salvate
    llm_mode: Literal["live", "record", "replay"] = "live"
    recordings_dir: Path = Path("eval/recordings")
    prompts_dir: Path = Path("prompts")


settings = Settings()
