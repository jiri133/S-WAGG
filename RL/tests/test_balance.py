"""Power balance and cash-flow contract: import/export, curtailment and conservation."""

from __future__ import annotations

import math

import pytest

from battery_rl.env.balance import BalanceResult, solve_balance
from battery_rl.seeding import make_rng


def assert_conserved(result: BalanceResult) -> None:
    """The primary invariant, in power form."""
    charge = max(-result.battery_mw, 0.0)
    discharge = max(result.battery_mw, 0.0)
    lhs = result.pv_mw + result.import_mw + discharge + result.unserved_mw
    rhs = result.demand_mw + charge + result.export_mw + result.curtailed_mw
    assert lhs == pytest.approx(rhs, abs=1e-9)
    assert result.conservation_residual_mw == pytest.approx(0.0, abs=1e-9)


def solve(**kwargs: float | None) -> BalanceResult:
    defaults = {
        "pv_mw": 0.0,
        "demand_mw": 0.0,
        "price_ron_mwh": 500.0,
        "battery_mw": 0.0,
    }
    defaults.update(kwargs)
    return solve_balance(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Import and export
# ---------------------------------------------------------------------------


def test_deficit_is_imported_at_the_spot_price() -> None:
    result = solve(pv_mw=0.0, demand_mw=1.0, price_ron_mwh=500.0)
    assert result.p_net_mw == pytest.approx(1.0)
    assert result.import_mw == pytest.approx(1.0)
    assert result.export_mw == pytest.approx(0.0)
    assert result.import_energy_mwh == pytest.approx(0.25)
    assert result.cost_ron == pytest.approx(125.0)
    assert_conserved(result)


def test_surplus_is_exported_at_the_spot_price() -> None:
    result = solve(pv_mw=3.0, demand_mw=1.0, price_ron_mwh=400.0)
    assert result.p_net_mw == pytest.approx(-2.0)
    assert result.import_mw == pytest.approx(0.0)
    assert result.export_mw == pytest.approx(2.0)
    assert result.export_energy_mwh == pytest.approx(0.5)
    assert result.cost_ron == pytest.approx(-200.0)
    assert_conserved(result)


def test_pv_exactly_matches_demand() -> None:
    result = solve(pv_mw=1.0, demand_mw=1.0)
    assert result.p_net_mw == pytest.approx(0.0)
    assert result.import_mw == pytest.approx(0.0)
    assert result.export_mw == pytest.approx(0.0)
    assert result.cost_ron == pytest.approx(0.0)
    assert_conserved(result)


def test_negative_price_means_paid_to_import() -> None:
    result = solve(pv_mw=0.0, demand_mw=1.0, price_ron_mwh=-100.0)
    assert result.import_mw == pytest.approx(1.0)
    assert result.cost_ron == pytest.approx(-25.0)
    assert_conserved(result)


def test_buy_and_sell_use_the_same_price() -> None:
    imported = solve(pv_mw=0.0, demand_mw=1.0, price_ron_mwh=300.0)
    exported = solve(pv_mw=2.0, demand_mw=1.0, price_ron_mwh=300.0)
    assert imported.cost_ron == pytest.approx(75.0)
    assert exported.cost_ron == pytest.approx(-75.0)


# ---------------------------------------------------------------------------
# Battery interaction
# ---------------------------------------------------------------------------


def test_discharge_reduces_import() -> None:
    result = solve(pv_mw=0.0, demand_mw=3.0, battery_mw=2.0)
    assert result.p_net_mw == pytest.approx(1.0)
    assert result.import_mw == pytest.approx(1.0)
    assert result.cost_ron == pytest.approx(125.0)
    assert_conserved(result)


def test_charge_increases_import() -> None:
    result = solve(pv_mw=0.0, demand_mw=0.0, battery_mw=-2.0)
    assert result.p_net_mw == pytest.approx(2.0)
    assert result.import_mw == pytest.approx(2.0)
    assert result.cost_ron == pytest.approx(250.0)
    assert_conserved(result)


def test_charge_can_absorb_pv_surplus() -> None:
    result = solve(pv_mw=2.0, demand_mw=0.0, battery_mw=-2.0)
    assert result.p_net_mw == pytest.approx(0.0)
    assert result.import_mw == pytest.approx(0.0)
    assert result.export_mw == pytest.approx(0.0)
    assert result.cost_ron == pytest.approx(0.0)
    assert_conserved(result)


def test_discharge_can_export() -> None:
    result = solve(pv_mw=0.0, demand_mw=0.0, battery_mw=2.0, price_ron_mwh=500.0)
    assert result.export_mw == pytest.approx(2.0)
    assert result.cost_ron == pytest.approx(-250.0)
    assert_conserved(result)


# ---------------------------------------------------------------------------
# Grid limits
# ---------------------------------------------------------------------------


def test_export_limit_curtails_the_surplus() -> None:
    result = solve(pv_mw=3.0, demand_mw=0.0, price_ron_mwh=400.0, export_limit_mw=1.0)
    assert result.export_mw == pytest.approx(1.0)
    assert result.curtailed_mw == pytest.approx(2.0)
    assert result.curtailed_energy_mwh == pytest.approx(0.5)
    assert result.cost_ron == pytest.approx(-100.0)
    assert_conserved(result)


def test_export_limit_is_not_binding_below_the_cap() -> None:
    result = solve(pv_mw=1.0, demand_mw=0.0, export_limit_mw=2.0)
    assert result.export_mw == pytest.approx(1.0)
    assert result.curtailed_mw == pytest.approx(0.0)
    assert_conserved(result)


def test_import_limit_reports_unserved_load() -> None:
    result = solve(pv_mw=0.0, demand_mw=3.0, import_limit_mw=1.0)
    assert result.import_mw == pytest.approx(1.0)
    assert result.unserved_mw == pytest.approx(2.0)
    assert result.unserved_energy_mwh == pytest.approx(0.5)
    assert result.cost_ron == pytest.approx(125.0)
    assert_conserved(result)


def test_limits_are_unlimited_by_default() -> None:
    result = solve(pv_mw=4.0, demand_mw=0.0)
    assert result.export_mw == pytest.approx(4.0)
    assert result.curtailed_mw == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Invariants and validation
# ---------------------------------------------------------------------------


def test_conservation_holds_over_random_intervals() -> None:
    rng = make_rng(7)
    for _ in range(500):
        result = solve(
            pv_mw=rng.uniform(0.0, 10.0),
            demand_mw=rng.uniform(0.0, 10.0),
            battery_mw=rng.uniform(-5.0, 5.0),
            price_ron_mwh=rng.uniform(-200.0, 1_000.0),
        )
        assert_conserved(result)


def test_invalid_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="pv_mw"):
        solve(pv_mw=-1.0)
    with pytest.raises(ValueError, match="pv_mw"):
        solve(pv_mw=math.nan)
    with pytest.raises(ValueError, match="demand_mw"):
        solve(demand_mw=-1.0)
    with pytest.raises(ValueError, match="price_ron_mwh"):
        solve(price_ron_mwh=math.nan)
    with pytest.raises(ValueError, match="battery_mw"):
        solve(battery_mw=math.inf)
    with pytest.raises(ValueError, match="dt_h"):
        solve(dt_h=0.0)
    with pytest.raises(ValueError, match="export_limit_mw"):
        solve(export_limit_mw=0.0)
    with pytest.raises(ValueError, match="import_limit_mw"):
        solve(import_limit_mw=-1.0)
