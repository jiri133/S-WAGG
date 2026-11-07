"""Park layout and the shared literal types (DESIGN_SPEC §9)."""

from typing import Literal

from pydantic import BaseModel

FaultClass = Literal[
    "ok",
    "hot_cell",
    "multi_hot",
    "diode_substring",
    "module_offline",
    "soiling",
    "shadow_vegetation",
    "other",
]
Urgency = Literal["critical", "high", "medium", "low"]
ModuleStatus = Literal["pending", "ok", "finding", "unsure", "not_inspected"]


class Module(BaseModel):
    id: str
    table: str
    string: str
    inverter: str
    block: int
    row: int
    pos: int
    x_m: float
    y_m: float
