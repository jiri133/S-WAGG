from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All config comes from env vars / backend/.env. Add new keys here."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Hackathon API"
    env: str = "dev"
    database_url: str = "sqlite:///./app.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    # One POST per alert or work order (§8); the mock ticketing system is the default receiver.
    webhook_url: str = "http://localhost:8000/api/mock/ticketing"

    # Optional LLM summary of the report (Q13): off by default, template fallback on any doubt.
    report_llm: bool = False

    # Fill in only if the challenge needs them
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
