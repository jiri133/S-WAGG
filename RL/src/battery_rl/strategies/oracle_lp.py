"""Perfect-foresight LP upper bound.

Under the merchant balance the cash flow is linear in battery power and the PV term is a
constant, so the optimal action path is price-driven.  The oracle uses the same LP as MPC;
the difference is that the evaluation builds its context with **actual future PV** rather
than the causal forecast.  That makes the reported objective the true perfect-foresight
upper bound while the action path is the same as MPC's.
"""

from __future__ import annotations

from battery_rl.strategies.mpc import MPC


class OracleLP(MPC):
    """Full-foresight variant of :class:`~battery_rl.strategies.mpc.MPC`."""

    name = "oracle_lp"


__all__ = ["OracleLP"]
