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

    # Where the active farm config is exported for the RL pipeline.
    rl_config_dir: Path = Path(__file__).resolve().parents[3] / "RL" / "configs"

    # Fill in only if the challenge needs them.
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
