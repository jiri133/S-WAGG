"""Phase 0 configuration tests: schema, scaling, checksums and loaders."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from battery_rl.config import (
    EnvConfig,
    FarmConfig,
    export_farm_config,
    load_agent_config,
    load_configs,
    load_env_config,
    load_eval_config,
    load_farm_config,
    load_pv_model_config,
    load_yaml,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
EXAMPLE = CONFIG_DIR / "farm.example.yaml"


def test_load_farm_example() -> None:
    farm = load_farm_config(EXAMPLE)
    assert farm.name == "seed-demo"
    assert farm.pv.kwp == 6000.0
    assert farm.battery.capacity_mwh == 10.0
    assert farm.grid.export_limit_mw is None
    assert farm.asset_scale == 1.0
    assert farm.scaled_pv_kwp == 6000.0
    assert farm.scaled_battery_capacity_mwh == 10.0


def test_asset_scale_multiplies_assets() -> None:
    farm = load_farm_config(EXAMPLE)
    scaled = farm.model_copy(update={"asset_scale": 500.0})
    assert scaled.scaled_pv_kwp == 3_000_000.0
    assert scaled.scaled_inverter_ac_mw == 3000.0
    assert scaled.scaled_battery_capacity_mwh == 5000.0
    assert scaled.scaled_p_max_mw == 1000.0


def test_checksum_is_stable_and_sensitive() -> None:
    farm = load_farm_config(EXAMPLE)
    assert farm.checksum() == load_farm_config(EXAMPLE).checksum()
    assert len(farm.checksum()) == 64
    changed = farm.model_copy(update={"asset_scale": 2.0})
    assert changed.checksum() != farm.checksum()
    assert changed.checksum() == farm.model_copy(update={"asset_scale": 2.0}).checksum()


def test_export_roundtrip(tmp_path: Path) -> None:
    farm = load_farm_config(EXAMPLE)
    target = export_farm_config(farm, tmp_path / "farm.yaml")
    reloaded = load_farm_config(target)
    assert reloaded == farm
    assert reloaded.checksum() == farm.checksum()


def test_invalid_latitude_rejected() -> None:
    data = load_yaml(EXAMPLE)
    data["latitude"] = 100
    with pytest.raises(ValidationError):
        FarmConfig.model_validate(data)


def test_invalid_soc_range_rejected() -> None:
    data = load_yaml(EXAMPLE)
    data["battery"]["soc_min"] = 0.95
    with pytest.raises(ValidationError):
        FarmConfig.model_validate(data)


def test_invalid_efficiency_rejected() -> None:
    data = load_yaml(EXAMPLE)
    data["battery"]["eta_charge"] = 0
    with pytest.raises(ValidationError):
        FarmConfig.model_validate(data)


def test_invalid_asset_scale_rejected() -> None:
    data = load_yaml(EXAMPLE)
    data["asset_scale"] = 0
    with pytest.raises(ValidationError):
        FarmConfig.model_validate(data)


def test_unknown_field_rejected() -> None:
    data = load_yaml(EXAMPLE)
    data["unexpected"] = "nope"
    with pytest.raises(ValidationError):
        FarmConfig.model_validate(data)


def test_env_config_action_levels() -> None:
    env = load_env_config(CONFIG_DIR / "env.yaml")
    assert env.episode_steps == 96
    assert env.step_minutes == 15
    assert env.episode_steps * env.step_minutes == 24 * 60
    assert len(env.action_levels) == 17
    assert env.action_levels[0] == -1.0
    assert env.action_levels[-1] == 1.0
    assert 0.0 in env.action_levels
    assert all(
        later > earlier
        for earlier, later in zip(env.action_levels, env.action_levels[1:], strict=False)
    )


def test_env_rejects_wrong_episode_length() -> None:
    data = load_yaml(CONFIG_DIR / "env.yaml")
    data["episode_steps"] = 95
    with pytest.raises(ValidationError):
        EnvConfig.model_validate(data)


def test_pv_model_config() -> None:
    model = load_pv_model_config(CONFIG_DIR / "pv_model.yaml")
    assert model.model == "hist_gradient_boosting"
    assert model.horizon_steps == 96
    assert model.replan_steps == 16
    assert "ghi" in model.features


def test_agent_config() -> None:
    agent = load_agent_config(CONFIG_DIR / "agent.yaml")
    assert agent.model_id == "deepseek-chat"
    assert agent.replan_steps == 16
    assert agent.max_simulator_calls == 3
    assert agent.api_key_env == "DEEPSEEK_API_KEY"
    assert agent.base_url_env == "DEEPSEEK_BASE_URL"


def test_eval_config() -> None:
    evaluation = load_eval_config(CONFIG_DIR / "eval.yaml")
    assert evaluation.repeats == 3
    assert evaluation.date_range.start <= evaluation.split.train_end
    assert evaluation.split.train_end < evaluation.split.val_end < evaluation.split.test_end
    assert "llm" in evaluation.strategies


def test_load_all_configs() -> None:
    bundle = load_configs(CONFIG_DIR)
    assert bundle.env.episode_steps == 96
    assert bundle.pv_model.horizon_steps == 96
    assert bundle.agent.model_id == "deepseek-chat"
    assert bundle.eval.repeats == 3
    assert bundle.config_dir == CONFIG_DIR


def test_missing_farm_config_has_clear_error() -> None:
    with pytest.raises(FileNotFoundError, match="Phase 1A UI"):
        load_farm_config(ROOT / "configs" / "does-not-exist.yaml")
