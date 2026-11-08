"""Load secrets from ``RL/.env`` without hardcoding or logging them.

Real secrets live in ``RL/.env`` (gitignored). ``RL/.env.example`` is the
tracked template. OS environment variables take precedence over the file, so
CI and container overrides keep working.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from dotenv import load_dotenv

from .config import RL_ROOT, AgentConfig

ENV_PATH = RL_ROOT / ".env"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class MissingSecretError(RuntimeError):
    """Raised when a required secret is not configured."""

    def __init__(self, name: str, env_path: Path = ENV_PATH):
        self.name = name
        self.env_path = env_path
        super().__init__(
            f"{name} is not set. Add it to {env_path} "
            f"(copy {env_path.with_name('.env.example')} to {env_path.name}) "
            "or export it in the environment."
        )


def load_env(path: str | Path | None = None, *, override: bool = False) -> bool:
    """Load a .env file into ``os.environ``.

    Existing environment variables win unless ``override=True``.
    """

    target = Path(path) if path is not None else ENV_PATH
    return load_dotenv(dotenv_path=target, override=override)


def get_secret(
    name: str, *, required: bool = False, default: str | None = None
) -> str | None:
    """Return a secret from the environment after loading ``RL/.env``."""

    load_env()
    value = os.environ.get(name)
    if value is None or not value.strip():
        if required:
            raise MissingSecretError(name, ENV_PATH)
        return default
    return value


def agent_api_key(config: AgentConfig) -> str:
    """Resolve the LLM key named by ``config.api_key_env``.

    The returned value is a live secret. Pass it to the SDK; never log it,
    serialize it into artifacts, or include it in prompts.
    """

    return cast(str, get_secret(config.api_key_env, required=True))


def agent_base_url(
    config: AgentConfig, default: str = DEFAULT_DEEPSEEK_BASE_URL
) -> str:
    """Resolve the OpenAI-compatible base URL for the agent provider."""

    load_env()
    value = os.environ.get(config.base_url_env, "").strip()
    return value or default


def secret_status(names: Iterable[str]) -> dict[str, bool]:
    """Report whether secrets are set, without exposing their values."""

    return {name: get_secret(name) is not None for name in names}
