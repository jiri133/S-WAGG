"""Tools exposed to the dispatch LLM.

The agent uses the frozen context/schedule contract from TEAM_PLAN.md.  The
simulator is injected: lane B's env/runner can implement ``simulate(context,
actions, execution_steps)``; tests use ``agents.stub.StubSimulator``.
"""

from __future__ import annotations

from typing import Any, Protocol


class ScheduleValidationError(ValueError):
    """Raised when the LLM schedule violates the action contract."""


class Simulator(Protocol):
    """Contract for the env/runner used by ``simulate_schedule``.

    ``actions`` are signed action indices (0..16) as defined by
    ``configs/env.yaml``.  The returned dict must be JSON-safe and include at
    least ``net_cost_ron``, ``soc_trajectory``, ``feasible`` and
    ``violations_mwh``.
    """

    def simulate(
        self, context: dict, actions: list[int], execution_steps: int
    ) -> dict: ...


def level_to_index(level: float, action_levels: list[float]) -> int | None:
    """Map a signed level to its action index, or ``None`` if not allowed."""

    for index, allowed in enumerate(action_levels):
        if abs(float(level) - float(allowed)) <= 1e-6:
            return index
    return None


def actions_to_levels(actions: list[int], action_levels: list[float]) -> list[float]:
    levels: list[float] = []
    for index, action in enumerate(actions):
        if not isinstance(action, int) or not 0 <= action < len(action_levels):
            raise ScheduleValidationError(
                f"action {index}: {action!r} is not an index in 0..{len(action_levels) - 1}"
            )
        levels.append(float(action_levels[action]))
    return levels


def normalize_schedule(
    schedule: Any, execution_steps: int, action_levels: list[float]
) -> list[float]:
    """Validate and normalize a schedule to a list of signed levels.

    Accepts either entries of the form ``{"interval": i, "level": v}`` or a
    plain list of numbers.  ``action`` indices are accepted as a convenience.
    """

    if not isinstance(schedule, list):
        raise ScheduleValidationError("schedule must be a list")
    if len(schedule) != execution_steps:
        raise ScheduleValidationError(
            f"schedule must have {execution_steps} entries, got {len(schedule)}"
        )

    levels: list[float] = []
    for index, entry in enumerate(schedule):
        if isinstance(entry, dict):
            if "level" in entry:
                value = entry["level"]
            elif "action" in entry:
                action = entry["action"]
                if not isinstance(action, int) or not 0 <= action < len(action_levels):
                    raise ScheduleValidationError(
                        f"entry {index}: action must be an index in "
                        f"0..{len(action_levels) - 1}"
                    )
                value = action_levels[action]
            else:
                raise ScheduleValidationError(
                    f"entry {index}: expected 'level' or 'action'"
                )
            if "interval" in entry and entry["interval"] != index:
                raise ScheduleValidationError(
                    f"entry {index}: interval must equal {index}"
                )
        elif isinstance(entry, (int, float)) and not isinstance(entry, bool):
            value = float(entry)
        else:
            raise ScheduleValidationError(
                f"entry {index}: expected an object or a number"
            )

        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ScheduleValidationError(f"entry {index}: level must be numeric")
        level = float(value)
        if level_to_index(level, action_levels) is None:
            raise ScheduleValidationError(
                f"entry {index}: level {level} is not one of the allowed levels"
            )
        levels.append(level)
    return levels


def to_jsonable(value: Any) -> Any:
    """Recursively convert numpy-like values to JSON-safe Python values."""

    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    return value


_SCHEDULE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "schedule": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "interval": {"type": "integer"},
                    "level": {"type": "number"},
                },
                "required": ["interval", "level"],
            },
        },
        "rationale": {"type": "string"},
    },
    "required": ["schedule"],
}

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_state",
            "description": "Return the current battery and site state.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_forecast",
            "description": (
                "Return the remaining price, PV and national-load forecasts. "
                "National load is market context; site demand is zero."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_schedule",
            "description": (
                "Run a candidate schedule through the simulator and return cash "
                "flow, SoC trajectory, feasibility and violations. Call this "
                "before submitting."
            ),
            "parameters": _SCHEDULE_SCHEMA,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_schedule",
            "description": (
                "Submit the final schedule. It must contain one level per "
                "execution interval."
            ),
            "parameters": _SCHEDULE_SCHEMA,
        },
    },
]


class AgentTools:
    """Stateful tool dispatcher for one planning attempt."""

    def __init__(
        self,
        *,
        context: dict,
        execution_steps: int,
        action_levels: list[float],
        simulator: Simulator | None = None,
        max_simulator_calls: int = 3,
    ):
        self.context = context
        self.execution_steps = execution_steps
        self.action_levels = action_levels
        self.simulator = simulator
        self.max_simulator_calls = max(0, max_simulator_calls)
        self.simulator_calls = 0
        self.submitted: list[float] | None = None
        self.rationale: str | None = None
        self._last_simulation_levels: tuple[float, ...] | None = None
        self._last_simulation: dict | None = None

    def tool_definitions(self) -> list[dict]:
        return TOOL_DEFINITIONS

    def dispatch(self, name: str, arguments: dict) -> dict:
        if not isinstance(arguments, dict):
            return {"error": "tool arguments must be a JSON object"}
        if name == "get_state":
            return self.get_state()
        if name == "get_forecast":
            return self.get_forecast()
        if name == "simulate_schedule":
            return self.simulate_schedule(
                arguments.get("schedule"), arguments.get("rationale")
            )
        if name == "submit_schedule":
            return self.submit_schedule(
                arguments.get("schedule"), arguments.get("rationale")
            )
        return {"error": f"unknown tool {name!r}"}

    def get_state(self) -> dict:
        battery = self.context.get("battery", {})
        return {
            "time_utc": self.context.get("time_utc"),
            "step_index": self.context.get("step_index"),
            "steps_remaining": self.context.get("steps_remaining"),
            "execution_steps": self.execution_steps,
            "soc": battery.get("soc"),
            "soc_min": battery.get("soc_min"),
            "soc_max": battery.get("soc_max"),
            "capacity_mwh": battery.get("capacity_mwh"),
            "p_max_mw": battery.get("p_max_mw"),
            "eta_c": battery.get("eta_c"),
            "eta_d": battery.get("eta_d"),
            "terminal_value": self.context.get("terminal_value"),
            "limits": self.context.get("limits"),
            "site_demand_mw": 0.0,
        }

    def get_forecast(self) -> dict:
        step = int(self.context.get("step_index", 0))
        prices = list(self.context.get("market", {}).get("prices_ron_mwh", []))
        return {
            "step_index": step,
            "prices_ron_mwh": prices[step:],
            "pv_forecast_mw": list(self.context.get("pv", {}).get("forecast_mw", [])),
            "load_forecast_mw": list(
                self.context.get("load", {}).get("forecast_mw", [])
            ),
            "note": "National load is market context; site demand is zero.",
        }

    def simulate_schedule(self, schedule: Any, rationale: str | None = None) -> dict:
        try:
            levels = normalize_schedule(
                schedule, self.execution_steps, self.action_levels
            )
        except ScheduleValidationError as exc:
            return {"available": True, "feasible": False, "error": str(exc)}
        if self.simulator is None:
            return {
                "available": False,
                "message": "simulator is not configured; submit without simulation",
            }
        if self.simulator_calls >= self.max_simulator_calls:
            return {
                "available": False,
                "message": f"max simulator calls reached ({self.max_simulator_calls})",
                "next_step": (
                    "Call submit_schedule now with the best feasible candidate. "
                    "Further simulate_schedule calls will be rejected."
                ),
            }

        actions = [
            index
            for index in (level_to_index(level, self.action_levels) for level in levels)
            if index is not None
        ]
        result = to_jsonable(
            self.simulator.simulate(self.context, actions, self.execution_steps)
        )
        self.simulator_calls += 1
        self._last_simulation_levels = tuple(levels)
        self._last_simulation = result
        remaining = self.max_simulator_calls - self.simulator_calls
        if remaining > 0:
            next_step = f"Simulator calls remaining: {remaining}."
        else:
            next_step = (
                "This was the last simulator call. Call submit_schedule now with "
                "the best feasible candidate."
            )
        return {
            "available": True,
            "rationale": rationale,
            "simulator_calls_remaining": remaining,
            "next_step": next_step,
            **result,
        }

    def submit_schedule(self, schedule: Any, rationale: str | None = None) -> dict:
        try:
            levels = normalize_schedule(
                schedule, self.execution_steps, self.action_levels
            )
        except ScheduleValidationError as exc:
            return {"accepted": False, "error": str(exc)}

        key = tuple(levels)
        simulation = (
            self._last_simulation
            if self._last_simulation_levels == key
            else None
        )
        if simulation is None and self.simulator is not None:
            if self.simulator_calls >= self.max_simulator_calls:
                simulation = None
            else:
                actions = [
                    index
                    for index in (
                        level_to_index(level, self.action_levels) for level in levels
                    )
                    if index is not None
                ]
                simulation = to_jsonable(
                    self.simulator.simulate(
                        self.context, actions, self.execution_steps
                    )
                )
                self.simulator_calls += 1
                self._last_simulation_levels = key
                self._last_simulation = simulation

        if simulation is not None and simulation.get("feasible") is False:
            return {
                "accepted": False,
                "error": "schedule is infeasible",
                "simulation": simulation,
            }

        self.submitted = levels
        self.rationale = rationale
        return {"accepted": True, "execution_steps": self.execution_steps}
