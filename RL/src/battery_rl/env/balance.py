"""Power balance and economics for the PV + battery + grid site.

``PLAN.md`` section 3.3.  Powers are MW, energies MWh, prices RON/MWh.  Positive
``cost_ron`` means money spent; negative means money earned (both are valid, PZU prices can
be negative).

The primary invariant is the power balance::

    pv + import + discharge + unserved = demand + charge + export + curtailed

Without a configured import limit ``unserved_mw`` is always zero, which reduces it to the
form in the specification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from battery_rl.env.battery import DEFAULT_STEP_HOURS

MW_EPS = 1e-9
"""Tolerance for treating a value as zero when splitting import/export."""


@dataclass(frozen=True)
class BalanceResult:
    """One interval of grid exchange, curtailment and cash flow."""

    pv_mw: float
    demand_mw: float
    battery_mw: float
    p_net_mw: float
    import_mw: float
    export_mw: float
    curtailed_mw: float
    unserved_mw: float
    import_energy_mwh: float
    export_energy_mwh: float
    curtailed_energy_mwh: float
    unserved_energy_mwh: float
    cost_ron: float
    conservation_residual_mw: float


def solve_balance(
    *,
    pv_mw: float,
    demand_mw: float,
    price_ron_mwh: float,
    battery_mw: float,
    dt_h: float = DEFAULT_STEP_HOURS,
    export_limit_mw: float | None = None,
    import_limit_mw: float | None = None,
) -> BalanceResult:
    """Solve one interval's grid exchange and cash flow.

    ``battery_mw`` is the *executed* signed battery power: positive discharges to the bus,
    negative charges from it.  ``export_limit_mw`` curtails PV surplus beyond the limit;
    ``import_limit_mw`` records the deficit as unserved load rather than silently breaking
    the energy balance.  Both limits are ``None`` (unlimited) in the default scenario.
    """
    _validate_balance_inputs(
        pv_mw=pv_mw,
        demand_mw=demand_mw,
        price_ron_mwh=price_ron_mwh,
        battery_mw=battery_mw,
        dt_h=dt_h,
        export_limit_mw=export_limit_mw,
        import_limit_mw=import_limit_mw,
    )

    p_net_mw = demand_mw - pv_mw - battery_mw
    import_unlimited = max(p_net_mw, 0.0)
    export_unlimited = max(-p_net_mw, 0.0)

    import_mw = import_unlimited
    unserved_mw = 0.0
    if import_limit_mw is not None and import_mw > import_limit_mw:
        unserved_mw = import_mw - import_limit_mw
        import_mw = import_limit_mw

    export_mw = export_unlimited
    curtailed_mw = 0.0
    if export_limit_mw is not None and export_mw > export_limit_mw:
        curtailed_mw = export_mw - export_limit_mw
        export_mw = export_limit_mw

    battery_charge_mw = max(-battery_mw, 0.0)
    battery_discharge_mw = max(battery_mw, 0.0)
    residual_mw = (
        pv_mw
        + import_mw
        + battery_discharge_mw
        + unserved_mw
        - demand_mw
        - battery_charge_mw
        - export_mw
        - curtailed_mw
    )

    cost_ron = (price_ron_mwh * import_mw * dt_h) - (price_ron_mwh * export_mw * dt_h)

    return BalanceResult(
        pv_mw=pv_mw,
        demand_mw=demand_mw,
        battery_mw=battery_mw,
        p_net_mw=p_net_mw,
        import_mw=import_mw,
        export_mw=export_mw,
        curtailed_mw=curtailed_mw,
        unserved_mw=unserved_mw,
        import_energy_mwh=import_mw * dt_h,
        export_energy_mwh=export_mw * dt_h,
        curtailed_energy_mwh=curtailed_mw * dt_h,
        unserved_energy_mwh=unserved_mw * dt_h,
        cost_ron=cost_ron,
        conservation_residual_mw=residual_mw,
    )


def _validate_balance_inputs(
    *,
    pv_mw: float,
    demand_mw: float,
    price_ron_mwh: float,
    battery_mw: float,
    dt_h: float,
    export_limit_mw: float | None,
    import_limit_mw: float | None,
) -> None:
    if not math.isfinite(pv_mw) or pv_mw < 0.0:
        raise ValueError(f"pv_mw must be finite and non-negative, got {pv_mw}")
    if not math.isfinite(demand_mw) or demand_mw < 0.0:
        raise ValueError(f"demand_mw must be finite and non-negative, got {demand_mw}")
    if not math.isfinite(price_ron_mwh):
        raise ValueError(f"price_ron_mwh must be finite, got {price_ron_mwh}")
    if not math.isfinite(battery_mw):
        raise ValueError(f"battery_mw must be finite, got {battery_mw}")
    if not math.isfinite(dt_h) or dt_h <= 0.0:
        raise ValueError(f"dt_h must be finite and positive, got {dt_h}")
    for name, limit in (
        ("export_limit_mw", export_limit_mw),
        ("import_limit_mw", import_limit_mw),
    ):
        if limit is not None and (not math.isfinite(limit) or limit <= 0.0):
            raise ValueError(f"{name} must be finite and positive when set, got {limit}")
