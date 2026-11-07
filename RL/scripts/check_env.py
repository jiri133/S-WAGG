#!/usr/bin/env python3
"""Report which secrets are configured, without printing their values."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battery_rl.credentials import ENV_PATH, load_env, secret_status  # noqa: E402

DEFAULT_NAMES = ("ANTHROPIC_API_KEY", "ENTSOE_API_TOKEN")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check RL .env configuration.")
    parser.add_argument(
        "--require",
        nargs="*",
        default=[],
        metavar="NAME",
        help="exit 1 if these variables are missing",
    )
    args = parser.parse_args(argv)

    load_env()
    state = "found" if ENV_PATH.exists() else "not found"
    print(f"env file: {ENV_PATH} ({state})")
    names = sorted(set(DEFAULT_NAMES) | set(args.require))
    status = secret_status(names)
    for name in names:
        print(f"{name}: {'set' if status[name] else 'missing'}")

    missing = [name for name in args.require if not status[name]]
    if missing:
        print(f"missing required: {', '.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
