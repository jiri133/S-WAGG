from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All config comes from env vars / backend/.env. Add new keys here.

    Secrets live in ``backend/.env`` (gitignored). Environment variables take
    precedence over the file. ``SecretStr`` keeps keys out of repr/log output.
    """

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Hackathon API"
    env: str = "dev"
    database_url: SecretStr = SecretStr("sqlite:///./app.db")
    cors_origins: list[str] = ["http://localhost:5173"]
    # One POST per alert or work order (§8); the mock ticketing system is the default receiver.
    webhook_url: str = "http://localhost:8000/api/mock/ticketing"

    # Optional LLM summary of the report (Q13): off by default, template fallback on any doubt.
    report_llm: bool = False

    # Fill in only if the challenge needs them.
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Where the active farm config is exported for the RL pipeline.
    rl_config_dir: Path = Path(__file__).resolve().parents[3] / "RL" / "configs"

    # RL checkout and interpreter used by the planning simulation endpoint.
    # ``rl_python`` is optional: when unset the service probes RL/.venv.
    rl_root: Path = Path(__file__).resolve().parents[3] / "RL"
    rl_python: Path | None = None

    # The simulation runner may make several LLM calls; allow a long wall clock.
    simulation_timeout_s: int = 600


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
