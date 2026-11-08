"""Configuration models and loaders for the battery optimization project.

The farm configuration is the canonical contract shared with the backend/UI. The UI exports
``configs/farm.yaml`` and this module validates it before training, simulation or evaluation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

RL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = RL_ROOT / "configs"


class Tracking(StrEnum):
    NONE = "none"
    SINGLE_AXIS = "single_axis"
    DUAL_AXIS = "dual_axis"


class PVConfig(BaseModel):
    """PV plant geometry and capacity (unscaled values)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kwp: float = Field(gt=0, description="Installed DC capacity in kWp")
    inverter_ac_mw: float = Field(gt=0, description="Inverter AC rating in MW")
    tilt_deg: float = Field(ge=0, le=90)
    azimuth_deg: float = Field(ge=0, le=360, description="0=N, 90=E, 180=S, 270=W")
    tracking: Tracking = Tracking.NONE


class BatteryConfig(BaseModel):
    """Battery nameplate and efficiency (unscaled values)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    capacity_mwh: float = Field(gt=0)
    p_max_mw: float = Field(gt=0)
    soc_min: float = Field(ge=0, lt=1)
    soc_max: float = Field(gt=0, le=1)
    eta_charge: float = Field(gt=0, le=1)
    eta_discharge: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _check_soc_range(self) -> BatteryConfig:
        if self.soc_min >= self.soc_max:
            raise ValueError("soc_min must be strictly less than soc_max")
        return self


class GridConfig(BaseModel):
    """Grid connection limits; ``None`` means unlimited."""

    model_config = ConfigDict(extra="forbid")

    export_limit_mw: float | None = Field(default=None, gt=0)
    import_limit_mw: float | None = Field(default=None, gt=0)


class FarmConfig(BaseModel):
    """One farm configuration, matching the Phase 1A UI export.

    ``asset_scale`` multiplies PV capacity, inverter AC, battery power and battery capacity
    together, preserving the base ratios. The national load is not scaled.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    asset_scale: float = Field(default=1.0, gt=0)
    pv: PVConfig
    battery: BatteryConfig
    grid: GridConfig = Field(default_factory=GridConfig)
    metered_pv_path: str | None = None
    timezone: str = "Europe/Bucharest"
    notes: str | None = None

    @property
    def scaled_pv_kwp(self) -> float:
        return self.pv.kwp * self.asset_scale

    @property
    def scaled_inverter_ac_mw(self) -> float:
        return self.pv.inverter_ac_mw * self.asset_scale

    @property
    def scaled_battery_capacity_mwh(self) -> float:
        return self.battery.capacity_mwh * self.asset_scale

    @property
    def scaled_p_max_mw(self) -> float:
        return self.battery.p_max_mw * self.asset_scale

    def scaled_assets(self) -> dict[str, float]:
        return {
            "pv_kwp": self.scaled_pv_kwp,
            "inverter_ac_mw": self.scaled_inverter_ac_mw,
            "battery_capacity_mwh": self.scaled_battery_capacity_mwh,
            "p_max_mw": self.scaled_p_max_mw,
        }

    def canonical_dict(self) -> dict:
        """JSON-safe, key-sorted representation used for checksums/contracts."""
        return json.loads(json.dumps(self.model_dump(mode="json"), sort_keys=True))

    def checksum(self) -> str:
        payload = json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ObjectiveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degradation_cost_ron_per_mwh: float = Field(default=50.0, ge=0)
    violation_penalty_ron_per_mwh: float = Field(default=5.0, ge=0)
    terminal_value_mode: Literal["episode_mean_price", "fixed", "none"] = "episode_mean_price"
    terminal_reference_price_ron_per_mwh: float | None = Field(default=None, ge=0)


class EnvConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_steps: int = Field(default=96, gt=0)
    step_minutes: int = Field(default=15, gt=0)
    initial_soc: float = Field(default=0.5, ge=0, le=1)
    action_levels: list[float] = Field(
        default_factory=lambda: [round(-1.0 + i * 0.125, 3) for i in range(17)]
    )
    objective: ObjectiveConfig = Field(default_factory=ObjectiveConfig)

    @model_validator(mode="after")
    def _check_episode_and_actions(self) -> EnvConfig:
        if self.episode_steps * self.step_minutes != 24 * 60:
            raise ValueError("episode_steps * step_minutes must equal 24 hours")
        levels = self.action_levels
        if len(levels) < 3 or len(levels) % 2 == 0:
            raise ValueError("action_levels must contain an odd number of values (>= 3)")
        if any(later <= earlier for earlier, later in zip(levels, levels[1:], strict=False)):
            raise ValueError("action_levels must be strictly increasing")
        if levels[0] != -1.0 or levels[-1] != 1.0 or 0.0 not in levels:
            raise ValueError("action_levels must span [-1, 1] and include 0")
        return self


class PVModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Literal["hist_gradient_boosting", "lightgbm", "xgboost"] = "hist_gradient_boosting"
    target: Literal["pv_mw"] = "pv_mw"
    horizon_steps: int = Field(default=96, gt=0)
    replan_steps: int = Field(default=16, gt=0)
    nwp_source: str = Field(default="open-meteo-single-runs", min_length=1)
    nwp_model: str = Field(default="ecmwf_ifs", min_length=1)
    nwp_run_lag_hours: float = Field(default=6.0, ge=0, le=24)
    random_seed: int = 42
    features: list[str] = Field(
        default_factory=lambda: [
            "hour_sin",
            "hour_cos",
            "doy_sin",
            "doy_cos",
            "month",
            "ghi",
            "dni",
            "dhi",
            "cloud_cover",
            "temperature",
            "humidity",
            "wind_speed",
            "precipitation",
            "snow",
            "aerosol",
            "clear_sky_ghi",
            "clear_sky_index",
            "lead_steps",
            "pv_lag_1",
            "pv_lag_2",
            "pv_roll_4",
        ]
    )


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="deepseek", min_length=1)
    model_id: str = Field(default="deepseek-chat", min_length=1)
    prompt_version: str = Field(default="v1", min_length=1)
    replan_steps: int = Field(default=16, gt=0)
    execution_steps: int = Field(default=16, gt=0)
    planning_horizon: Literal["rest_of_day"] = "rest_of_day"
    max_simulator_calls: int = Field(default=3, ge=0)
    max_output_tokens: int = Field(default=4096, gt=0)
    max_retries: int = Field(default=1, ge=0)
    fallback: Literal["rule_based", "hold"] = "rule_based"
    api_key_env: str = Field(default="DEEPSEEK_API_KEY", min_length=1)
    base_url_env: str = Field(default="DEEPSEEK_BASE_URL", min_length=1)


class DateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: date
    end: date

    @model_validator(mode="after")
    def _check_order(self) -> DateRange:
        if self.start > self.end:
            raise ValueError("date_range.start must not be after date_range.end")
        return self


class SplitConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    train_end: date
    val_end: date
    test_end: date

    @model_validator(mode="after")
    def _check_order(self) -> SplitConfig:
        if not (self.train_end < self.val_end < self.test_end):
            raise ValueError("split dates must satisfy train_end < val_end < test_end")
        return self


class EvalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int = 42
    repeats: int = Field(default=3, ge=1)
    date_range: DateRange
    split: SplitConfig
    strategies: list[str] = Field(
        default_factory=lambda: [
            "idle",
            "rule_based",
            "price_threshold",
            "mpc",
            "oracle_lp",
            "llm",
        ]
    )
    regimes: list[str] = Field(
        default_factory=lambda: [
            "high_price",
            "low_price",
            "volatile",
            "sunny",
            "cloudy",
            "weekend",
        ]
    )
    output_dir: str = "artifacts/reports"

    @model_validator(mode="after")
    def _check_split_window(self) -> EvalConfig:
        if not (
            self.date_range.start
            <= self.split.train_end
            < self.split.val_end
            < self.split.test_end
            <= self.date_range.end
        ):
            raise ValueError("split dates must lie inside date_range in increasing order")
        return self


@dataclass(frozen=True)
class ConfigBundle:
    env: EnvConfig
    pv_model: PVModelConfig
    agent: AgentConfig
    eval: EvalConfig
    config_dir: Path


def config_dir() -> Path:
    return DEFAULT_CONFIG_DIR


def load_yaml(path: str | Path) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            "Export a farm config from the Phase 1A UI or pass an explicit --config path."
        )
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{config_path} must contain a YAML mapping")
    return data


def load_farm_config(path: str | Path | None = None) -> FarmConfig:
    target = Path(path) if path is not None else DEFAULT_CONFIG_DIR / "farm.yaml"
    return FarmConfig.model_validate(load_yaml(target))


def load_env_config(path: str | Path | None = None) -> EnvConfig:
    target = Path(path) if path is not None else DEFAULT_CONFIG_DIR / "env.yaml"
    return EnvConfig.model_validate(load_yaml(target))


def load_pv_model_config(path: str | Path | None = None) -> PVModelConfig:
    target = Path(path) if path is not None else DEFAULT_CONFIG_DIR / "pv_model.yaml"
    return PVModelConfig.model_validate(load_yaml(target))


def load_agent_config(path: str | Path | None = None) -> AgentConfig:
    target = Path(path) if path is not None else DEFAULT_CONFIG_DIR / "agent.yaml"
    return AgentConfig.model_validate(load_yaml(target))


def load_eval_config(path: str | Path | None = None) -> EvalConfig:
    target = Path(path) if path is not None else DEFAULT_CONFIG_DIR / "eval.yaml"
    return EvalConfig.model_validate(load_yaml(target))


def load_configs(directory: str | Path | None = None) -> ConfigBundle:
    root = Path(directory) if directory is not None else DEFAULT_CONFIG_DIR
    return ConfigBundle(
        env=load_env_config(root / "env.yaml"),
        pv_model=load_pv_model_config(root / "pv_model.yaml"),
        agent=load_agent_config(root / "agent.yaml"),
        eval=load_eval_config(root / "eval.yaml"),
        config_dir=root,
    )


def export_farm_config(farm: FarmConfig, path: str | Path) -> Path:
    """Write a farm config as YAML (same shape the UI must produce)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = farm.model_dump(mode="json")
    target.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return target
