"""Battery physics contract: efficiencies, clipping, SoC bounds and asset scaling."""

from __future__ import annotations

import math

import pytest

from battery_rl.agents.schemas import BatteryContext, Schedule, index_to_level
from battery_rl.config import load_farm_config
from battery_rl.env.battery import (
    DEFAULT_STEP_HOURS,
    Battery,
    BatterySpec,
    BatteryStepResult,
)
from battery_rl.seeding import make_rng

CAPACITY = 10.0
P_MAX = 2.0


def make_spec(capacity_mwh: float = CAPACITY, p_max_mw: float = P_MAX) -> BatterySpec:
    return BatterySpec(capacity_mwh=capacity_mwh, p_max_mw=p_max_mw)


def make_battery(soc: float = 0.5) -> Battery:
    return Battery(make_spec(), soc=soc)


# ---------------------------------------------------------------------------
# Spec and construction
# ---------------------------------------------------------------------------


def test_spec_rejects_invalid_nameplate() -> None:
    with pytest.raises(ValueError, match="capacity_mwh"):
        BatterySpec(capacity_mwh=0.0, p_max_mw=2.0)
    with pytest.raises(ValueError, match="p_max_mw"):
        BatterySpec(capacity_mwh=10.0, p_max_mw=0.0)
    with pytest.raises(ValueError, match="soc bounds"):
        BatterySpec(capacity_mwh=10.0, p_max_mw=2.0, soc_min=0.9, soc_max=0.9)
    with pytest.raises(ValueError, match="eta_c"):
        BatterySpec(capacity_mwh=10.0, p_max_mw=2.0, eta_c=0.0)
    with pytest.raises(ValueError, match="eta_d"):
        BatterySpec(capacity_mwh=10.0, p_max_mw=2.0, eta_d=1.5)


def test_spec_from_farm_config_scales_capacity_and_power() -> None:
    farm = load_farm_config()
    spec = BatterySpec.from_farm_config(farm)
    assert spec.capacity_mwh == pytest.approx(10.0)
    assert spec.p_max_mw == pytest.approx(2.0)
    assert spec.eta_c == pytest.approx(0.95)
    assert spec.eta_d == pytest.approx(0.95)
    assert spec.soc_min == pytest.approx(0.10)
    assert spec.soc_max == pytest.approx(0.90)

    scaled = BatterySpec.from_config(farm.battery, asset_scale=2.0)
    assert scaled.capacity_mwh == pytest.approx(20.0)
    assert scaled.p_max_mw == pytest.approx(4.0)
    assert scaled.energy_min_mwh == pytest.approx(2.0)
    assert scaled.energy_max_mwh == pytest.approx(18.0)

    with pytest.raises(ValueError, match="asset_scale"):
        BatterySpec.from_config(farm.battery, asset_scale=0.0)


def test_initial_state() -> None:
    battery = make_battery(0.5)
    assert battery.soc == pytest.approx(0.5)
    assert battery.energy_mwh == pytest.approx(5.0)
    assert battery.spec.energy_min_mwh == pytest.approx(1.0)
    assert battery.spec.energy_max_mwh == pytest.approx(9.0)


def test_reset_validates_soc_bounds() -> None:
    battery = make_battery()
    battery.reset(0.1)
    assert battery.soc == pytest.approx(0.1)
    battery.reset(0.9)
    assert battery.soc == pytest.approx(0.9)
    for invalid in (0.05, 0.95, -0.1, 1.1):
        with pytest.raises(ValueError, match="initial soc"):
            battery.reset(invalid)
    with pytest.raises(ValueError, match="soc must be finite"):
        battery.reset(math.nan)


# ---------------------------------------------------------------------------
# Feasible envelope
# ---------------------------------------------------------------------------


def test_headroom_at_mid_soc_is_power_limited() -> None:
    battery = make_battery(0.5)
    assert battery.max_charge_mw() == pytest.approx(P_MAX)
    assert battery.max_discharge_mw() == pytest.approx(P_MAX)


def test_headroom_at_soc_bounds_is_zero() -> None:
    battery = make_battery(0.9)
    assert battery.max_charge_mw() == pytest.approx(0.0)
    assert battery.max_discharge_mw() == pytest.approx(P_MAX)

    battery.reset(0.1)
    assert battery.max_discharge_mw() == pytest.approx(0.0)
    assert battery.max_charge_mw() == pytest.approx(P_MAX)


def test_discharge_headroom_uses_eta_d() -> None:
    battery = make_battery(0.12)
    expected = (0.12 - 0.10) * CAPACITY * 0.95 / DEFAULT_STEP_HOURS
    assert battery.max_discharge_mw() == pytest.approx(expected)
    assert expected == pytest.approx(0.76)


def test_charge_headroom_uses_eta_c() -> None:
    battery = make_battery(0.88)
    expected = (0.90 - 0.88) * CAPACITY / (0.95 * DEFAULT_STEP_HOURS)
    assert battery.max_charge_mw() == pytest.approx(expected)
    assert expected == pytest.approx(0.8421052631578947)


# ---------------------------------------------------------------------------
# Energy accounting
# ---------------------------------------------------------------------------


def test_charge_uses_eta_c() -> None:
    battery = make_battery(0.5)
    result = battery.step(-2.0)
    assert isinstance(result, BatteryStepResult)
    assert result.requested_mw == pytest.approx(-2.0)
    assert result.executed_mw == pytest.approx(-2.0)
    assert result.charge_mw == pytest.approx(2.0)
    assert result.discharge_mw == pytest.approx(0.0)
    assert result.energy_before_mwh == pytest.approx(5.0)
    assert result.charge_energy_mwh == pytest.approx(2.0 * 0.25 * 0.95)
    assert result.energy_after_mwh == pytest.approx(5.475)
    assert result.soc_after == pytest.approx(0.5475)
    assert result.throughput_mwh == pytest.approx(0.475)
    assert result.violation_mwh == pytest.approx(0.0)
    assert result.feasible is True
    assert battery.energy_mwh == pytest.approx(5.475)


def test_discharge_uses_eta_d() -> None:
    battery = make_battery(0.5)
    result = battery.step(2.0)
    assert result.executed_mw == pytest.approx(2.0)
    assert result.discharge_mw == pytest.approx(2.0)
    assert result.charge_mw == pytest.approx(0.0)
    assert result.discharge_energy_mwh == pytest.approx(2.0 * 0.25 / 0.95)
    assert result.energy_after_mwh == pytest.approx(5.0 - 2.0 * 0.25 / 0.95)
    assert result.soc_after == pytest.approx(0.4473684210526316)
    assert result.throughput_mwh == pytest.approx(2.0 * 0.25 / 0.95)
    assert result.feasible is True


def test_hold_is_a_noop() -> None:
    battery = make_battery(0.42)
    result = battery.step(0.0)
    assert result.executed_mw == 0.0
    assert result.charge_mw == 0.0
    assert result.discharge_mw == 0.0
    assert result.energy_after_mwh == pytest.approx(result.energy_before_mwh)
    assert result.throughput_mwh == pytest.approx(0.0)
    assert result.violation_mwh == pytest.approx(0.0)
    assert result.feasible is True


def test_requested_within_envelope_is_not_a_violation() -> None:
    battery = make_battery(0.5)
    result = battery.step(1.5)
    assert result.feasible is True
    assert result.violation_mwh == pytest.approx(0.0)
    assert result.executed_mw == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Clipping and violations
# ---------------------------------------------------------------------------


def test_discharge_is_clipped_at_soc_min() -> None:
    battery = make_battery(0.12)
    result = battery.step(2.0)
    assert result.executed_mw == pytest.approx(0.76)
    assert result.feasible is False
    assert result.violation_mwh == pytest.approx((2.0 - 0.76) * 0.25)
    assert result.energy_after_mwh == pytest.approx(1.0)
    assert result.soc_after == pytest.approx(0.10)
    assert result.throughput_mwh == pytest.approx(0.20)


def test_charge_is_clipped_at_soc_max() -> None:
    battery = make_battery(0.88)
    result = battery.step(-2.0)
    assert result.executed_mw == pytest.approx(-0.8421052631578947)
    assert result.feasible is False
    assert result.violation_mwh == pytest.approx((2.0 - 0.8421052631578947) * 0.25)
    assert result.energy_after_mwh == pytest.approx(9.0)
    assert result.soc_after == pytest.approx(0.90)
    assert result.throughput_mwh == pytest.approx(0.20)


def test_request_above_p_max_is_clipped() -> None:
    battery = make_battery(0.5)
    discharge = battery.step(3.0)
    assert discharge.executed_mw == pytest.approx(P_MAX)
    assert discharge.violation_mwh == pytest.approx((3.0 - P_MAX) * 0.25)
    assert discharge.feasible is False

    battery.reset(0.5)
    charge = battery.step(-3.0)
    assert charge.executed_mw == pytest.approx(-P_MAX)
    assert charge.violation_mwh == pytest.approx((3.0 - P_MAX) * 0.25)
    assert charge.feasible is False


def test_invalid_power_and_interval_are_rejected() -> None:
    battery = make_battery()
    for invalid in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="power must be finite"):
            battery.step(invalid)
    with pytest.raises(ValueError, match="dt_h"):
        battery.step(0.0, dt_h=0.0)
    with pytest.raises(ValueError, match="dt_h"):
        battery.max_charge_mw(0.0)


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_energy_accounting_holds_over_random_steps() -> None:
    rng = make_rng(42)
    battery = make_battery(0.5)
    for _ in range(1_000):
        result = battery.step(rng.uniform(-5.0, 5.0))
        assert battery.spec.soc_min - 1e-9 <= battery.soc <= battery.spec.soc_max + 1e-9
        assert result.energy_after_mwh - result.energy_before_mwh == pytest.approx(
            result.charge_energy_mwh - result.discharge_energy_mwh
        )
        assert result.throughput_mwh == pytest.approx(
            result.charge_energy_mwh + result.discharge_energy_mwh
        )
        assert result.violation_mwh >= 0.0
        assert result.feasible == (
            abs(result.requested_mw - result.executed_mw) <= 1e-9
        )


def test_schedule_soc_validation_agrees_with_battery_clipping() -> None:
    battery_context = BatteryContext(
        capacity_mwh=CAPACITY,
        p_max_mw=P_MAX,
        soc=0.5,
        soc_min=0.10,
        soc_max=0.90,
        eta_c=0.95,
        eta_d=0.95,
        degradation_cost_ron_per_mwh=50.0,
    )

    feasible_indices = [8] * 16
    feasible_schedule = Schedule.from_action_indices(feasible_indices)
    assert feasible_schedule.soc_errors(battery_context) == []
    battery = make_battery(0.5)
    assert not any(
        battery.step(index_to_level(index) * P_MAX).violation_mwh > 1e-9
        for index in feasible_indices
    )

    infeasible_indices = [16] * 16
    infeasible_schedule = Schedule.from_action_indices(infeasible_indices)
    assert infeasible_schedule.soc_errors(battery_context)
    battery.reset(0.5)
    assert any(
        battery.step(index_to_level(index) * P_MAX).violation_mwh > 1e-9
        for index in infeasible_indices
    )
