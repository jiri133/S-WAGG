"""Tests for .env loading and secret handling (no real keys required)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from battery_rl import credentials
from battery_rl.config import load_agent_config


@pytest.fixture
def restore_env() -> Iterator[None]:
    before = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(before)


def test_load_env_parses_values(tmp_path: Path, monkeypatch, restore_env) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'BATTERY_RL_TEST_A=plain\n'
        'BATTERY_RL_TEST_B="hello world"\n'
        "# comment\n"
        "BATTERY_RL_TEST_C=\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(credentials, "ENV_PATH", env_file)
    monkeypatch.delenv("BATTERY_RL_TEST_A", raising=False)
    monkeypatch.delenv("BATTERY_RL_TEST_B", raising=False)
    monkeypatch.delenv("BATTERY_RL_TEST_C", raising=False)

    assert credentials.get_secret("BATTERY_RL_TEST_A") == "plain"
    assert credentials.get_secret("BATTERY_RL_TEST_B") == "hello world"
    assert credentials.get_secret("BATTERY_RL_TEST_C") is None
    assert credentials.secret_status(["BATTERY_RL_TEST_A"]) == {
        "BATTERY_RL_TEST_A": True
    }


def test_os_environment_wins_by_default(
    tmp_path: Path, monkeypatch, restore_env
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("BATTERY_RL_TEST_X=file\n", encoding="utf-8")
    monkeypatch.setenv("BATTERY_RL_TEST_X", "os")

    credentials.load_env(env_file, override=False)
    assert os.environ["BATTERY_RL_TEST_X"] == "os"

    credentials.load_env(env_file, override=True)
    assert os.environ["BATTERY_RL_TEST_X"] == "file"


def test_required_secret_raises_without_exposing_a_value(
    tmp_path: Path, monkeypatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(credentials, "ENV_PATH", env_file)
    monkeypatch.delenv("BATTERY_RL_TEST_MISSING", raising=False)

    with pytest.raises(credentials.MissingSecretError, match="BATTERY_RL_TEST_MISSING"):
        credentials.get_secret("BATTERY_RL_TEST_MISSING", required=True)


def test_agent_api_key_uses_configured_variable(monkeypatch, restore_env) -> None:
    config = load_agent_config()
    monkeypatch.setenv(config.api_key_env, "test-key")
    assert credentials.agent_api_key(config) == "test-key"
