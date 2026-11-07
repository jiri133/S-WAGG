"""Park layout (DESIGN_SPEC §4): 2 blocks × 5 rows × 4 tables × 12 modules = 480 modules.

A table holds 2×6 portrait modules. A string is 2 tables (24 modules), so a row has 2 strings
and one inverter (10 inverters × 48 modules). Rows are 9 m apart; the 2 blocks sit side by side,
45 m apart along x. `x_m`/`y_m` are a module's top-left corner, in metres from the park's
top-left corner.
"""

from functools import lru_cache

from app.schemas import Module

BLOCKS, ROWS, TABLES, MODULES_PER_TABLE = 2, 5, 4, 12
TABLE_COLS = 6  # modules across a table, 2 modules high
ROW_PITCH_M, BLOCK_PITCH_M = 9.0, 45.0
MODULE_W_M, MODULE_H_M, TABLE_GAP_M = 1.0, 1.7, 1.0

# A module is 6×10 cells of 4 px = 24×40 px, exactly a Raptor crop. A frame covers one table.
CELL_PX = 4
SLOT_W, SLOT_H = 6 * CELL_PX, 10 * CELL_PX
FRAME_W, FRAME_H = TABLE_COLS * SLOT_W, 2 * SLOT_H


def _module(block: int, row: int, table: int, pos: int) -> Module:
    half, col = divmod(pos - 1, TABLE_COLS)  # positions 1–6 on top, 7–12 below
    table_x = (block - 1) * BLOCK_PITCH_M + (table - 1) * (TABLE_COLS * MODULE_W_M + TABLE_GAP_M)
    return Module(
        id=f"B{block}-R{row}-T{table}-M{pos:02d}",
        table=f"B{block}-R{row}-T{table}",
        string=f"B{block}-R{row}-S{(table + 1) // 2}",
        inverter=f"INV-{block}.{row}",
        block=block,
        row=row,
        pos=pos,
        x_m=table_x + col * MODULE_W_M,
        y_m=(row - 1) * ROW_PITCH_M + half * MODULE_H_M,
    )


@lru_cache
def park() -> list[Module]:
    """The 480 modules in flight order: block, row, table, then position 1–12."""
    return [
        _module(b, r, t, p)
        for b in range(1, BLOCKS + 1)
        for r in range(1, ROWS + 1)
        for t in range(1, TABLES + 1)
        for p in range(1, MODULES_PER_TABLE + 1)
    ]


@lru_cache
def tables() -> dict[str, list[Module]]:
    """The 40 tables in flight order, each with its 12 modules in position order."""
    out: dict[str, list[Module]] = {}
    for m in park():
        out.setdefault(m.table, []).append(m)
    return out
