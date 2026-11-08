#!/usr/bin/env python3
"""Snapshot the current model state into a restorable archive.

Run this before changing prompts, agent configuration or the trained PV model.
The archive contains the trained PV model artifact, the LLM agent
config/prompts/tools, the evaluation code and configs, and the baseline
reports.  The secret ``.env`` file, virtual environments, caches and the raw
input data are never included.

Example::

    cd RL
    .venv\\Scripts\\python.exe scripts/backup_model_state.py --label pre_phase8

Outputs (under ``artifacts/backups/`` by default):

- ``<label>_<timestamp>.tar.gz`` — the snapshot itself
- ``<label>_<timestamp>.tar.gz.sha256`` — archive checksum
- ``<label>_<timestamp>.manifest.md`` — human-readable manifest (also inside the archive)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import platform
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts/backups"

INCLUDE: tuple[str, ...] = (
    "configs",
    "src/battery_rl",
    "scripts",
    "tests",
    "artifacts/models/pv",
    "artifacts/reports/val",
    "artifacts/reports/test",
    "artifacts/data/processed/splits.json",
    "artifacts/data/processed/dataset_meta.json",
    "artifacts/data/processed/data_card.md",
    "artifacts/data/processed/validation_report.json",
    "pyproject.toml",
    "README.md",
    "PLAN.md",
    "TEAM_PLAN.md",
    "IDEA.md",
    "PV_MODEL.md",
    "docs",
    ".env.example",
)

EXCLUDE_DIRS = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "backups",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
FORBIDDEN_NAMES = {".env"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT.parent), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return completed.stdout.strip()


def collect_files() -> list[Path]:
    files: list[Path] = []
    for relative in INCLUDE:
        path = ROOT / relative
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
            continue
        for candidate in sorted(path.rglob("*")):
            if not candidate.is_file():
                continue
            parts = candidate.relative_to(ROOT).parts
            if any(part in EXCLUDE_DIRS for part in parts):
                continue
            if candidate.suffix in EXCLUDE_SUFFIXES:
                continue
            if candidate.name in FORBIDDEN_NAMES:
                continue
            files.append(candidate)
    unique: dict[Path, None] = {}
    for file in files:
        unique.setdefault(file, None)
    return sorted(unique)


def read_agent_summary() -> dict[str, object]:
    summary: dict[str, object] = {}
    agent_path = ROOT / "configs/agent.yaml"
    if agent_path.exists():
        try:
            import yaml

            data = yaml.safe_load(agent_path.read_text(encoding="utf-8")) or {}
            for key in (
                "provider",
                "model_id",
                "prompt_version",
                "replan_steps",
                "execution_steps",
                "fallback",
            ):
                if key in data:
                    summary[key] = data[key]
        except Exception as exc:  # pragma: no cover - manifest is best effort
            summary["error"] = f"{type(exc).__name__}: {exc}"
    prompts_path = ROOT / "src/battery_rl/agents/prompts.py"
    if prompts_path.exists():
        for line in prompts_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("PROMPT_VERSION"):
                summary["prompts_module_version"] = line.split("=", 1)[1].strip().strip('"')
                break
    return summary


def build_manifest(
    label: str,
    created: datetime,
    files: list[Path],
    *,
    archive_name: str,
) -> str:
    checkpoint = git_output("rev-parse", "HEAD")
    branch = git_output("rev-parse", "--abbrev-ref", "HEAD")
    dirty = git_output("status", "--porcelain")
    farm_sha = ROOT / "configs/farm.yaml.sha256"
    farm_checksum = (
        farm_sha.read_text(encoding="utf-8").strip()
        if farm_sha.exists()
        else "unavailable"
    )
    agent = read_agent_summary()

    lines = [
        "# Model state backup",
        "",
        f"- Label: `{label}`",
        f"- Created (UTC): `{created.isoformat()}`",
        f"- Archive: `{archive_name}`",
        f"- Repository: `{ROOT.parent}`",
        f"- Git branch: `{branch}`",
        f"- Git commit: `{checkpoint}`",
        f"- Working tree: `{'dirty' if dirty else 'clean'}`",
        f"- Python: `{platform.python_version()}`",
        f"- Platform: `{platform.platform()}`",
        f"- Farm checksum: `{farm_checksum}`",
        "",
        "## Agent / model summary",
        "",
    ]
    if agent:
        lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(agent.items()))
    else:
        lines.append("- (agent config unavailable)")
    lines.extend(
        [
            "",
            "## Included files",
            "",
            "| Path | Bytes | SHA-256 |",
            "|---|---:|---|",
        ]
    )
    for file in files:
        relative = file.relative_to(ROOT).as_posix()
        lines.append(f"| `{relative}` | {file.stat().st_size} | `{sha256(file)}` |")
    lines.extend(
        [
            "",
            "## Excluded on purpose",
            "",
            "- `RL/.env` (secret API key), `.env` files anywhere, virtual environments,",
            "  caches, `__pycache__`, raw data downloads, and the large processed CSVs.",
            "",
            "## Restore",
            "",
            "```powershell",
            "cd RL",
            f"tar -xzf artifacts/backups/{archive_name} -C .",
            "```",
            "",
            "The archive paths are relative to `RL/`, so extracting over the checkout",
            "restores the snapshotted files. Verify the archive checksum first:",
            "",
            "```powershell",
            f"Get-FileHash artifacts/backups/{archive_name} -Algorithm SHA256",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="model_state")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created = datetime.now(UTC)
    stamp = created.strftime("%Y-%m-%d_%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{args.label}_{stamp}.tar.gz"
    manifest_path = output_dir / f"{args.label}_{stamp}.manifest.md"
    checksum_path = output_dir / f"{archive.name}.sha256"

    files = collect_files()
    if not files:
        raise SystemExit("nothing to back up")
    manifest = build_manifest(args.label, created, files, archive_name=archive.name)

    with tarfile.open(archive, "w:gz") as handle:
        for file in files:
            handle.add(file, arcname=file.relative_to(ROOT).as_posix())
        manifest_bytes = manifest.encode("utf-8")
        info = tarfile.TarInfo("BACKUP_MANIFEST.md")
        info.size = len(manifest_bytes)
        info.mtime = int(created.timestamp())
        handle.addfile(info, io.BytesIO(manifest_bytes))

    manifest_path.write_text(manifest, encoding="utf-8")
    digest = sha256(archive)
    checksum_path.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")

    print(f"archive: {archive}")
    print(f"files:   {len(files)}")
    print(f"bytes:   {archive.stat().st_size}")
    print(f"sha256:  {digest}")
    print(f"manifest:{manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
