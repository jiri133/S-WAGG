"""Artefacts and injections (DESIGN_SPEC §4 and §6), all drawn from the mission seed.

Random artefacts follow the MissionSettings probabilities: cloud (`p_cloud`, per frame,
irradiance 420–480 W/m²), GPS offset of ±1 module (`p_gps`, per frame), glare in one of the two
passes (`p_glare`, per table) and lost frames (`p_lost`, per frame). Each value in `inject` hits
both passes of one table chosen from the seed: "rgb" (3 channels, radiometric=false),
"no_panels" (ground only), "low_irr" (irradiance under 600 W/m²) and "missing" (no frames).
"""

import numpy as np

from app.schemas import MissionSettings
from app.services.sim.park import CELL_PX, FRAME_H, FRAME_W, SLOT_H, SLOT_W, tables

INJECTIONS = ("rgb", "no_panels", "low_irr", "missing")
GROUND_C = 28.0  # a freed slot or a frame without panels shows bare ground
GLARE_PX = 2 * CELL_PX  # glare covers 2×2 cells


def plan(settings: MissionSettings) -> list[dict]:
    """Every planned frame in flight order (passes 1 and 2 of each table) with its artefacts.

    The draws have a fixed size, so changing one probability or injection never moves the
    others. A `lost` frame (p_lost or "missing") is never delivered. `gps` is the true offset in
    modules: +1 means the camera looked one module further along +x, so the last column of
    slots shows ground. `glare` is (y, x, ΔK) in frame pixels, in exactly one pass of a table.
    """
    names = list(tables())
    n_tables, n_frames = len(names), 2 * len(names)
    rng = np.random.default_rng([settings.seed, 3])
    u_lost, u_cloud, u_gps = rng.random((3, n_frames))
    gps_sign = rng.choice((-1, 1), size=n_frames)
    shade = rng.uniform(420, 480, n_frames)
    wind = rng.uniform(1.5, 5.0, n_frames)
    sun = rng.uniform(800, 880, n_tables)  # both passes of a table are seconds apart
    low = rng.uniform(520, 590, n_tables)
    u_glare = rng.random(n_tables)
    glare_pass = rng.integers(1, 3, n_tables)
    glare_y = rng.integers(0, (FRAME_H - GLARE_PX) // CELL_PX + 1, n_tables) * CELL_PX
    glare_x = rng.integers(0, (FRAME_W - GLARE_PX) // CELL_PX + 1, n_tables) * CELL_PX
    glare_k = rng.uniform(7, 11, n_tables)
    hit = dict(zip(rng.permutation(n_tables)[: len(INJECTIONS)].tolist(), INJECTIONS, strict=True))

    out = []
    for i in range(n_frames):
        t, pass_no = divmod(i, 2)
        pass_no += 1
        inject = hit.get(t) if hit.get(t) in settings.inject else None
        cloud = bool(u_cloud[i] < settings.p_cloud)
        glare = bool(u_glare[t] < settings.p_glare) and glare_pass[t] == pass_no
        irradiance = shade[i] if cloud else low[t] if inject == "low_irr" else sun[t]
        out.append(
            {
                "index": i,
                "id": f"FR-{names[t]}-P{pass_no}",
                "table": names[t],
                "pass_no": pass_no,
                "lost": bool(u_lost[i] < settings.p_lost) or inject == "missing",
                "cloud": cloud,
                "gps": int(gps_sign[i]) if u_gps[i] < settings.p_gps else 0,
                "glare": (int(glare_y[t]), int(glare_x[t]), float(glare_k[t])) if glare else None,
                "inject": inject,
                "irradiance_wm2": round(float(irradiance), 1),
                "wind_ms": round(float(wind[i]), 1),
            }
        )
    return out


def t_base(irradiance_wm2: float) -> float:
    """Temperature of a healthy module: 20 °C air + 25 K per 800 W/m² (NOCT 45 °C).

    That is how T_base drops under a cloud (§4): ~46 °C in sun, ~34 °C at 450 W/m².
    """
    return 20.0 + irradiance_wm2 * 25.0 / 800.0


def ground(rng: np.random.Generator) -> np.ndarray:
    """A whole frame of bare ground at 28 °C with a little sensor noise, °C float32."""
    return (GROUND_C + rng.normal(0.0, 0.5, (FRAME_H, FRAME_W))).astype(np.float32)


def with_glare(img: np.ndarray, glare: tuple[int, int, float]) -> np.ndarray:
    """A copy of the frame with a sun reflection of +ΔK on 2×2 cells."""
    y, x, dk = glare
    out = img.copy()
    out[y : y + GLARE_PX, x : x + GLARE_PX] += dk
    return out


def rgb_frame() -> np.ndarray:
    """What a visible-light camera sends by mistake: blue cells, light grid, silver frames."""
    img = np.full((FRAME_H, FRAME_W, 3), (30, 45, 95), np.uint8)
    img[::CELL_PX] = (70, 85, 140)
    img[:, ::CELL_PX] = (70, 85, 140)
    img[::SLOT_H] = (170, 170, 175)
    img[:, ::SLOT_W] = (170, 170, 175)
    return img
