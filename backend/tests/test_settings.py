"""Settings load secrets from the environment and mask them in representations."""

from app.core.config import Settings


def test_settings_reads_database_url_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./unit-test.db")
    settings = Settings()
    assert settings.database_url.get_secret_value() == "sqlite:///./unit-test.db"
    assert "unit-test.db" not in repr(settings)
