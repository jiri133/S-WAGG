"""Continuous battery LP shared by MPC and the perfect-foresight oracle.

The merchant balance with zero site demand and no export limit makes cash flow linear in
battery power::

    cost_t = price_t * (charge_t - pv_t - discharge_t) * dt

The PV term is a constant, so the optimal action path depends on prices, degradation and
terminal value; the PV forecast only shifts the reported objective.  The LP enforces the
same battery equations, SoC bounds and objective terms as the environment so the comparison
is exact up to action quantization.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from battery_rl.env.battery import DEFAULT_STEP_HOURS, BatterySpec


class LPError(RuntimeError):
    """Raised when the battery LP cannot be solved."""


@dataclass(frozen=True)
class LPSolution:
    """Continuous LP solution over the planned horizon."""

    charge_mw: np.ndarray
    discharge_mw: np.ndarray
    energy_mwh: np.ndarray
    objective_ron: float


def solve_battery_lp(
    prices_ron_mwh: Sequence[float],
    pv_mw: Sequence[float] | None,
    spec: BatterySpec,
    *,
    start_soc: float,
    degradation_cost_ron_per_mwh: float,
    terminal_price_ron_mwh: float | None,
    dt_h: float = DEFAULT_STEP_HOURS,
) -> LPSolution:
    """Solve the merchant battery LP over one horizon.

    Variables are ``charge[t]``, ``discharge[t]`` (MW, both non-negative) and
    ``energy[t]`` (MWh, ``N + 1`` values including the start and end).  The objective is
    cash flow plus degradation minus terminal value; the PV term is a constant added to the
    reported objective and does not change the optimal action path.
    """
    prices = np.asarray(list(prices_ron_mwh), dtype=float)
    n = len(prices)
    if n == 0:
        raise ValueError("prices must contain at least one interval")
    if not np.all(np.isfinite(prices)):
        raise ValueError("prices must be finite")
    if pv_mw is not None:
        pv = np.asarray(list(pv_mw), dtype=float)
        if len(pv) != n:
            raise ValueError(f"pv_mw must have {n} entries, got {len(pv)}")
        if not np.all(np.isfinite(pv)):
            raise ValueError("pv_mw must be finite")
    else:
        pv = None
    if not math.isfinite(dt_h) or dt_h <= 0.0:
        raise ValueError(f"dt_h must be finite and positive, got {dt_h}")
    if not math.isfinite(degradation_cost_ron_per_mwh) or degradation_cost_ron_per_mwh < 0:
        raise ValueError(
            "degradation_cost_ron_per_mwh must be finite and non-negative, "
            f"got {degradation_cost_ron_per_mwh}"
        )
    if terminal_price_ron_mwh is not None and not math.isfinite(terminal_price_ron_mwh):
        raise ValueError("terminal_price_ron_mwh must be finite when set")
    if not spec.soc_min - 1e-9 <= start_soc <= spec.soc_max + 1e-9:
        raise ValueError(
            f"start_soc must lie in [{spec.soc_min}, {spec.soc_max}], got {start_soc}"
        )

    p_max = spec.p_max_mw
    e_min = spec.energy_min_mwh
    e_max = spec.energy_max_mwh
    start_energy = min(max(start_soc, spec.soc_min), spec.soc_max) * spec.capacity_mwh

    # Variables: charge[n], discharge[n], energy[n + 1].
    n_vars = 2 * n + (n + 1)
    objective = np.zeros(n_vars)
    objective[:n] = prices * dt_h + degradation_cost_ron_per_mwh * spec.eta_c * dt_h
    objective[n : 2 * n] = -prices * dt_h + degradation_cost_ron_per_mwh * dt_h / spec.eta_d
    if terminal_price_ron_mwh is not None:
        objective[2 * n + n] = -terminal_price_ron_mwh * spec.eta_d

    constraints = np.zeros((n, n_vars))
    rhs = np.zeros(n)
    for t in range(n):
        constraints[t, t] = -spec.eta_c * dt_h
        constraints[t, n + t] = dt_h / spec.eta_d
        constraints[t, 2 * n + t] = -1.0
        constraints[t, 2 * n + t + 1] = 1.0

    bounds: list[tuple[float | None, float | None]] = (
        [(0.0, p_max)] * n
        + [(0.0, p_max)] * n
        + [(e_min, e_max)] * (n + 1)
    )
    bounds[2 * n] = (start_energy, start_energy)

    result = linprog(
        objective,
        A_eq=constraints,
        b_eq=rhs,
        bounds=bounds,
        method="highs",
    )
    if not result.success:
        raise LPError(f"battery LP failed: {result.message}")

    charge = np.clip(np.asarray(result.x[:n], dtype=float), 0.0, p_max)
    discharge = np.clip(np.asarray(result.x[n : 2 * n], dtype=float), 0.0, p_max)
    energy = np.asarray(result.x[2 * n :], dtype=float)
    pv_constant = -float(np.sum(prices * pv * dt_h)) if pv is not None else 0.0
    return LPSolution(
        charge_mw=charge,
        discharge_mw=discharge,
        energy_mwh=energy,
        objective_ron=float(result.fun) + pv_constant,
    )
