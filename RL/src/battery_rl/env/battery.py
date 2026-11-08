"""Battery physics: feasible power, SoC update, efficiencies and asset scale.

Sign convention (``PLAN.md`` section 3.2): positive power discharges to the bus (sells),
negative power charges from the bus (buys).  Powers are MW, energies MWh, time hours.

The environment never produces an invalid SoC: requests are clipped to the feasible
charge/discharge envelope before the energy update, and the difference between requested
and executed power is reported for the violation metric and penalty term.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from battery_rl.config import BatteryConfig, FarmConfig

DEFAULT_STEP_HOURS = 0.25
"""A 15-minute dispatch interval, matching ``configs/env.yaml``."""

POWER_EPS_MW = 1e-9
"""Below this difference a request is considered executed exactly."""

SOC_EPS = 1e-9
"""SoC tolerance used only to absorb floating-point noise, never to relax the limits."""

ENERGY_EPS_MWH = 1e-9
"""Energy tolerance for the post-step numerical safety check."""


@dataclass(frozen=True)
class BatterySpec:
    """Scaled battery nameplate values.

    Build it from the active farm config with :meth:`from_config` so ``asset_scale``
    multiplies capacity and power together, exactly as ``PLAN.md`` section 3.2 requires.
    """

    capacity_mwh: float
    p_max_mw: float
    soc_min: float = 0.1
    soc_max: float = 0.9
    eta_c: float = 0.95
    eta_d: float = 0.95

    def __post_init__(self) -> None:
        if not math.isfinite(self.capacity_mwh) or self.capacity_mwh <= 0:
            raise ValueError(f"capacity_mwh must be finite and positive, got {self.capacity_mwh}")
        if not math.isfinite(self.p_max_mw) or self.p_max_mw <= 0:
            raise ValueError(f"p_max_mw must be finite and positive, got {self.p_max_mw}")
        if not (0.0 <= self.soc_min < self.soc_max <= 1.0):
            raise ValueError(
                f"soc bounds must satisfy 0 <= soc_min < soc_max <= 1, got "
                f"[{self.soc_min}, {self.soc_max}]"
            )
        for name, value in (("eta_c", self.eta_c), ("eta_d", self.eta_d)):
            if not math.isfinite(value) or not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must be in (0, 1], got {value}")

    @property
    def energy_min_mwh(self) -> float:
        return self.soc_min * self.capacity_mwh

    @property
    def energy_max_mwh(self) -> float:
        return self.soc_max * self.capacity_mwh

    @classmethod
    def from_config(cls, battery: BatteryConfig, asset_scale: float = 1.0) -> BatterySpec:
        """Scale the farm's nameplate battery values by ``asset_scale``."""
        if not math.isfinite(asset_scale) or asset_scale <= 0:
            raise ValueError(f"asset_scale must be finite and positive, got {asset_scale}")
        return cls(
            capacity_mwh=battery.capacity_mwh * asset_scale,
            p_max_mw=battery.p_max_mw * asset_scale,
            soc_min=battery.soc_min,
            soc_max=battery.soc_max,
            eta_c=battery.eta_charge,
            eta_d=battery.eta_discharge,
        )

    @classmethod
    def from_farm_config(cls, farm: FarmConfig) -> BatterySpec:
        """Build the scaled battery from the active ``configs/farm.yaml`` object."""
        return cls.from_config(farm.battery, farm.asset_scale)


@dataclass(frozen=True)
class BatteryStepResult:
    """Everything one 15-minute battery step produces for the ``info`` dict and metrics."""

    requested_mw: float
    executed_mw: float
    charge_mw: float
    discharge_mw: float
    soc_before: float
    soc_after: float
    energy_before_mwh: float
    energy_after_mwh: float
    charge_energy_mwh: float
    discharge_energy_mwh: float
    throughput_mwh: float
    violation_mwh: float
    feasible: bool


class Battery:
    """Stateful battery asset: clip a requested power, then update stored energy."""

    def __init__(self, spec: BatterySpec, soc: float = 0.5) -> None:
        self.spec = spec
        self._energy_mwh = 0.0
        self.reset(soc)

    def reset(self, soc: float = 0.5) -> None:
        """Set the state of charge; the evaluation default is 50%."""
        if not math.isfinite(soc):
            raise ValueError(f"soc must be finite, got {soc}")
        if soc < self.spec.soc_min - SOC_EPS or soc > self.spec.soc_max + SOC_EPS:
            raise ValueError(
                f"initial soc must lie within [{self.spec.soc_min}, {self.spec.soc_max}], "
                f"got {soc}"
            )
        bounded = min(max(soc, self.spec.soc_min), self.spec.soc_max)
        self._energy_mwh = bounded * self.spec.capacity_mwh

    @property
    def soc(self) -> float:
        return self._energy_mwh / self.spec.capacity_mwh

    @property
    def energy_mwh(self) -> float:
        return self._energy_mwh

    def max_charge_mw(self, dt_h: float = DEFAULT_STEP_HOURS) -> float:
        """``P_charge_max``: room to the upper SoC bound, capped at ``P_max``."""
        _validate_dt(dt_h)
        headroom_mwh = self.spec.energy_max_mwh - self._energy_mwh
        return max(
            0.0,
            min(self.spec.p_max_mw, headroom_mwh / (self.spec.eta_c * dt_h)),
        )

    def max_discharge_mw(self, dt_h: float = DEFAULT_STEP_HOURS) -> float:
        """``P_discharge_max``: room to the lower SoC bound, capped at ``P_max``."""
        _validate_dt(dt_h)
        headroom_mwh = self._energy_mwh - self.spec.energy_min_mwh
        return max(
            0.0,
            min(self.spec.p_max_mw, headroom_mwh * self.spec.eta_d / dt_h),
        )

    def clip(self, requested_mw: float, dt_h: float = DEFAULT_STEP_HOURS) -> float:
        """Return the feasible signed power closest to ``requested_mw``."""
        _validate_power(requested_mw)
        if requested_mw >= 0.0:
            return min(requested_mw, self.max_discharge_mw(dt_h))
        return -min(-requested_mw, self.max_charge_mw(dt_h))

    def step(
        self,
        requested_mw: float,
        dt_h: float = DEFAULT_STEP_HOURS,
    ) -> BatteryStepResult:
        """Clip, apply and return one step; the battery state is updated in place."""
        _validate_power(requested_mw)
        _validate_dt(dt_h)

        soc_before = self.soc
        energy_before = self._energy_mwh
        executed_mw = self.clip(requested_mw, dt_h)

        if executed_mw >= 0.0:
            discharge_energy_mwh = executed_mw * dt_h / self.spec.eta_d
            charge_energy_mwh = 0.0
            energy_after = energy_before - discharge_energy_mwh
        else:
            charge_energy_mwh = -executed_mw * dt_h * self.spec.eta_c
            discharge_energy_mwh = 0.0
            energy_after = energy_before + charge_energy_mwh

        lower = self.spec.energy_min_mwh
        upper = self.spec.energy_max_mwh
        if energy_after < lower - ENERGY_EPS_MWH or energy_after > upper + ENERGY_EPS_MWH:
            raise RuntimeError(
                "battery clipping produced an out-of-bounds SoC: "
                f"{energy_after / self.spec.capacity_mwh} not in "
                f"[{self.spec.soc_min}, {self.spec.soc_max}]"
            )
        energy_after = min(max(energy_after, lower), upper)
        self._energy_mwh = energy_after

        violation_mwh = abs(requested_mw - executed_mw) * dt_h
        return BatteryStepResult(
            requested_mw=requested_mw,
            executed_mw=executed_mw,
            charge_mw=max(-executed_mw, 0.0),
            discharge_mw=max(executed_mw, 0.0),
            soc_before=soc_before,
            soc_after=self.soc,
            energy_before_mwh=energy_before,
            energy_after_mwh=energy_after,
            charge_energy_mwh=charge_energy_mwh,
            discharge_energy_mwh=discharge_energy_mwh,
            throughput_mwh=charge_energy_mwh + discharge_energy_mwh,
            violation_mwh=violation_mwh,
            feasible=abs(requested_mw - executed_mw) <= POWER_EPS_MW,
        )


def _validate_power(power_mw: float) -> None:
    if not math.isfinite(power_mw):
        raise ValueError(f"power must be finite, got {power_mw}")


def _validate_dt(dt_h: float) -> None:
    if not math.isfinite(dt_h) or dt_h <= 0:
        raise ValueError(f"dt_h must be finite and positive, got {dt_h}")
