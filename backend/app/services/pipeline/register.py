"""Step 2 (DESIGN_SPEC §5): find the ground column, undo the GPS offset, re-allocate the slots.

The camera can look ±1 module off along +x, so one column of the frame is bare ground and the
table is shifted by one slot. `offset` reads the ground column at an edge, and `slots` maps each
module position back to its 24×40 crop. A position whose slot fell outside the frame has no
image and is `not_inspected`; the caller marks it from the missing key.

Slots are apparent-temperature crops (°C). The model expects gray levels, so convert them with
`compose.to_gray` before inference.
"""

import numpy as np

from app.services.pipeline.check import is_ground
from app.services.sim.park import SLOT_H, SLOT_W, TABLE_COLS


def offset(img: np.ndarray) -> int:
    """GPS offset in modules read from the ground column at a frame edge: -1, 0 or +1.

    A +1 offset means the camera looked one module further along +x, so the last column is
    ground; -1 means the first column is ground (§4).
    """
    if img.ndim != 2:
        return 0
    if is_ground(img[:, :SLOT_W]):
        return -1
    if is_ground(img[:, -SLOT_W:]):
        return 1
    return 0


def slots(img: np.ndarray, gps: int = 0) -> dict[int, np.ndarray]:
    """Module position 1–12 → its 24×40 crop, with the GPS offset undone.

    Positions absent from the result had no image in this frame (the slot showed ground or was
    outside the frame), so they must become `not_inspected` unless the other pass covers them.
    """
    out = {}
    for pos in range(1, 2 * TABLE_COLS + 1):
        row, col = divmod(pos - 1, TABLE_COLS)
        frame_col = col - gps
        if 0 <= frame_col < TABLE_COLS:
            out[pos] = img[
                row * SLOT_H : (row + 1) * SLOT_H,
                frame_col * SLOT_W : (frame_col + 1) * SLOT_W,
            ]
    return out
