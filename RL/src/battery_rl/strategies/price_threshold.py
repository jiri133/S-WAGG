"""Price-threshold baseline: charge below a daily price quantile, discharge above it.

The thresholds are known one day ahead (the PZU price array is in the context), so this is
a legitimate baseline with no future information.  It charges from the grid or PV at low
prices and sells at high prices.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from battery_rl.env.battery import BatterySpec
from battery_rl.strategies.common import (
    HOLD_ACTION,
    charge_action,
    discharge_action,
    simulate_plan,
    spec_from_context,
)


class PriceThreshold:
    """Charge below ``low_price``, discharge above ``high_price``, hold otherwise."""

    name = "price_threshold"

    def __init__(
        self,
        spec: BatterySpec,
        prices: Sequence[float] | None = None,
        *,
        low_price_ron_mwh: float | None = None,
        high_price_ron_mwh: float | None = None,
        low_quantile: float = 0.3,
        high_quantile: float = 0.7,
        soc_deadband: float = 0.02,
    ) -> None:
        if not 0.0 <= low_quantile < high_quantile <= 1.0:
            raise ValueError("quantiles must satisfy 0 <= low_quantile < high_quantile <= 1")
        if not 0.0 <= soc_deadband < spec.soc_max - spec.soc_min:
            raise ValueError(f"soc_deadband is outside the usable SoC range: {soc_deadband}")

        if prices is not None:
            values = np.asarray(list(prices), dtype=float)
            if values.size == 0 or not np.all(np.isfinite(values)):
                raise ValueError("prices must be a non-empty finite sequence")
            low_price = float(np.quantile(values, low_quantile))
            high_price = float(np.quantile(values, high_quantile))
        elif low_price_ron_mwh is not None and high_price_ron_mwh is not None:
            low_price = float(low_price_ron_mwh)
            high_price = float(high_price_ron_mwh)
            if low_price > high_price:
                raise ValueError("low_price_ron_mwh must not exceed high_price_ron_mwh")
        else:
            raise ValueError("provide prices or both explicit low/high price thresholds")

        self.spec = spec
        self.low_price_ron_mwh = low_price
        self.high_price_ron_mwh = high_price
        self.soc_deadband = soc_deadband

    def act(self, info: dict) -> int:
        """Choose an action from the current SoC and the current interval's price."""
        return self._choose(
            price=float(info["price_ron_mwh"]),
            soc=float(info["soc"]),
            spec=self.spec,
        )

    def _choose(self, *, price: float, soc: float, spec: BatterySpec) -> int:
        if price <= self.low_price_ron_mwh:
            return charge_action(spec, soc, deadband=self.soc_deadband)
        if price >= self.high_price_ron_mwh:
            return discharge_action(spec, soc, deadband=self.soc_deadband)
        return HOLD_ACTION

    def plan(self, context: dict, execution_steps: int = 16) -> list[int]:
        context_spec = spec_from_context(context)
        return simulate_plan(
            context,
            lambda info: self._choose(
                price=float(info["price_ron_mwh"]),
                soc=float(info["soc"]),
                spec=context_spec,
            ),
            execution_steps,
        )


__all__ = ["HOLD_ACTION", "PriceThreshold"]
