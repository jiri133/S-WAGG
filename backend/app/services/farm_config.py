"""Export the active farm config to the RL package's YAML format."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.schemas.farm import FarmConfigRead


def export_farm_config(farm, config_dir: Path) -> tuple[Path, str]:
    """Write ``farm.yaml`` and ``farm.yaml.sha256`` atomically; return path and checksum."""
    read_model = farm if isinstance(farm, FarmConfigRead) else FarmConfigRead.model_validate(farm)
    checksum = read_model.canonical_checksum()
    payload = read_model.to_rl_dict()

    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / "farm.yaml"
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    temp.replace(target)
    (config_dir / "farm.yaml.sha256").write_text(checksum + "\n", encoding="utf-8")
    return target, checksum
