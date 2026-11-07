"""Merchant rule-based baseline: PV charges the battery, the battery serves the grid.

``TEAM_PLAN.md`` section 6 still describes the old "discharge on deficit" rule; with the
merchant balance the site has zero local demand, so the analogue is:

- when PV is available, charge at the PV power (never above it, so no grid import);
- when PV is absent, discharge to the grid;
- hold inside a SoC deadband and quantize to a feasible action level.

This is intentionally naive on price: it is the PV-following baseline that MPC must beat.
"""

from __future__ import annotations

from battery_rl.env.battery import BatterySpec
from battery_rl.strategies.common import (
    HOLD_ACTION,
    charge_action,
    discharge_action,
    simulate_plan,
    spec_from_context,
)


class RuleBased:
    """Charge from PV surplus, discharge when PV is absent, with a SoC deadband."""

    name = "rule_based"

    def __init__(self, spec: BatterySpec, *, soc_deadband: float = 0.02) -> None:
        if not 0.0 <= soc_deadband < spec.soc_max - spec.soc_min:
            raise ValueError(f"soc_deadband is outside the usable SoC range: {soc_deadband}")
        self.spec = spec
        self.soc_deadband = soc_deadband

    def act(self, info: dict) -> int:
        """Choose an action from the current SoC and the current PV production.

        The runner passes the state *before* the interval, so ``info["soc"]`` is the
        current SoC and ``info["pv_mw"]`` is the PV available in the interval.
        """
        return self._choose(
            soc=float(info["soc"]),
            pv_mw=float(info["pv_mw"]),
            spec=self.spec,
        )

    def _choose(self, *, soc: float, pv_mw: float, spec: BatterySpec) -> int:
        if pv_mw <= 0.0:
            return discharge_action(spec, soc, deadband=self.soc_deadband)
        max_fraction = min(pv_mw / spec.p_max_mw, 1.0)
        return charge_action(
            spec,
            soc,
            max_fraction=max_fraction,
            deadband=self.soc_deadband,
        )

    def plan(self, context: dict, execution_steps: int = 16) -> list[int]:
        context_spec = spec_from_context(context)
        return simulate_plan(
            context,
            lambda info: self._choose(
                soc=float(info["soc"]),
                pv_mw=float(info["pv_mw"]),
                spec=context_spec,
            ),
            execution_steps,
        )


__all__ = ["HOLD_ACTION", "RuleBased"]
