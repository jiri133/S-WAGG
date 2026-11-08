"""Test environment: isolate the database and exported config from dev data."""

import os
import tempfile
from pathlib import Path

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="battery_rl_backend_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_ROOT / 'test.db').as_posix()}"
os.environ["RL_CONFIG_DIR"] = str(_TEST_ROOT / "configs")
