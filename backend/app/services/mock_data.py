"""Fixed mock data with the final API shape (DESIGN_SPEC §9).

Lets React work before the real simulator, pipeline and decision layer exist.
Each later ticket replaces one of these builders with the real service.
"""

import struct
import zlib
from functools import lru_cache

from app.schemas import (
    AgentEvent,
    Alert,
    Evidence,
    Finding,
    Mission,
    MissionSettings,
    ModuleStatus,
    Plan,
    PlanDay,
    PlanTask,
    Prediction,
    ReviewIn,
    SimilarCase,
    StreamEvent,
    WorkOrder,
)
from app.services.decision import workorders
from app.services.sim import compose
from app.services.sim.park import park

MOCK_TS = "2026-11-07T10:00:00Z"
CLASSES = (
    "ok",
    "hot_cell",
    "multi_hot",
    "diode_substring",
    "module_offline",
    "soiling",
    "shadow_vegetation",
    "other",
)


# module, model class, baseline class, apparent ΔT K, unsure
_FINDINGS = [
    ("B1-R2-T3-M07", "hot_cell", "hot_cell", 22.4, False),
    ("B1-R4-T1-M03", "diode_substring", "multi_hot", 9.8, False),
    ("B2-R1-T2-M11", "module_offline", "module_offline", 3.1, False),
    ("B2-R3-T4-M05", "multi_hot", "hot_cell", 12.6, True),
    ("B2-R5-T1-M09", "soiling", "ok", 2.2, False),
]
MOCK_MONTH = 11  # month of MOCK_TS, picks the PVGIS daily yield
_NOT_INSPECTED_TABLE = "B2-R4-T3"
# Engineer reviews, in memory until the mission state / SQLite ticket replaces this.
_reviews: dict[str, ReviewIn] = {}


def _finding(i: int, row: tuple) -> Finding:
    module_id, cls, base, dt, unsure = row
    fid = f"F-{i:03d}"
    top = 0.55 if unsure else 0.93
    probs = {c: (1 - top) / (len(CLASSES) - 1) for c in CLASSES}
    probs[cls] = top
    table = module_id.rsplit("-", 1)[0]
    prediction = Prediction(
        cls=cls,
        probs=probs,
        temperature=1.42,
        unsure=unsure,
        unsure_reason="probabilitate sub prag pe clasă de risc" if unsure else None,
    )
    fields = workorders.finding_fields(prediction, dt, MOCK_MONTH)
    rule = fields.pop("rule_applied")
    return Finding(
        id=fid,
        module_id=module_id,
        prediction=prediction,
        baseline_cls=base,
        **fields,
        evidence=Evidence(
            frame_ids=[f"FR-{table}-P1", f"FR-{table}-P2"],
            crop_url=f"/api/findings/{fid}/crop.png",
            gradcam_url=f"/api/findings/{fid}/gradcam.png",
            delta_t_k=dt,
            pattern="punct fierbinte izolat" if cls == "hot_cell" else "pattern mock",
            seen_in_both_passes=True,
            similar=[
                SimilarCase(
                    id=f"raptor-{1000 + i * 3 + k}",
                    cls=cls,
                    crop_url=f"/api/findings/{fid}/crop.png",
                    distance=round(0.1 + 0.05 * k, 2),
                )
                for k in range(3)
            ],
            rule_applied=rule,
        ),
    )


@lru_cache
def _detected() -> list[Finding]:
    return [_finding(i, row) for i, row in enumerate(_FINDINGS, start=1)]


def findings() -> list[Finding]:
    """Detected findings with the engineer's reviews applied."""
    return [
        f.model_copy(update={"review": r.decision, "review_note": r.note})
        if (r := _reviews.get(f.id))
        else f
        for f in _detected()
    ]


def review(finding_id: str, decision: ReviewIn) -> None:
    _reviews[finding_id] = decision


def mission(mission_id: str, settings: MissionSettings | None = None) -> Mission:
    modules = park()
    status: dict[str, ModuleStatus] = {m.id: "ok" for m in modules}
    for m in modules:
        if m.table == _NOT_INSPECTED_TABLE:
            status[m.id] = "not_inspected"
    for f in findings():
        status[f.module_id] = "unsure" if f.prediction.unsure else "finding"
    return Mission(
        id=mission_id,
        settings=settings or MissionSettings(),
        phase="analysed",
        modules=modules,
        status=status,
        truth={f.module_id: f.prediction.cls for f in findings()},
    )


def work_orders() -> list[WorkOrder]:
    return workorders.work_orders(findings(), park(), MOCK_TS)


def _day_tasks(orders: list[WorkOrder]) -> list[PlanTask]:
    tasks, t = [], 0.0
    for w in orders:
        tasks.append(
            PlanTask(
                work_order_id=w.id,
                crew=w.crew,
                start_h=round(t, 2),
                duration_h=w.est_hours,
                reason=f"urgență {w.urgency}, sortat după scor",
            )
        )
        t += w.est_hours + 10 / 60  # 10 min travel between rows
    return tasks


def plan() -> Plan:
    orders = work_orders()
    day1 = _day_tasks([w for w in orders if w.crew == "electrical"])
    day3 = _day_tasks([w for w in orders if w.crew == "cleaning"])
    cap = {"electrical": 7.0, "cleaning": 7.0}

    def used(tasks: list[PlanTask]) -> dict[str, float]:
        return {c: sum(t.duration_h for t in tasks if t.crew == c) for c in cap}

    return Plan(
        days=[
            PlanDay(
                day=1,
                date="2026-11-08",
                weather="senin",
                capacity_h=cap,
                used_h=used(day1),
                tasks=day1,
            ),
            PlanDay(
                day=2,
                date="2026-11-09",
                weather="ploaie",
                capacity_h=cap,
                used_h=used([]),
                tasks=[],
            ),
            PlanDay(
                day=3,
                date="2026-11-10",
                weather="senin",
                capacity_h=cap,
                used_h=used(day3),
                tasks=day3,
            ),
        ],
        unscheduled=[],
        total_loss_avoided_kwh=round(sum(f.loss_kwh_day for f in findings()) * 30, 1),
    )


def alerts() -> list[Alert]:
    return [
        Alert(
            id="AL-001",
            finding_id="F-001",
            level="critical",
            message="Hot cell cu ΔT 22,4 K pe B1-R2-T3-M07 (≥ 20 K)",
            raised_at=MOCK_TS,
        )
    ]


def events() -> list[AgentEvent]:
    t = _NOT_INSPECTED_TABLE
    return [
        AgentEvent(
            ts=MOCK_TS,
            kind="frame_rejected",
            ref=f"FR-{t}-P1",
            message="Cadru respins: iradianță 450 W/m² < 600",
        ),
        AgentEvent(ts=MOCK_TS, kind="refly_proposed", ref=t, message=f"Re-zbor propus pentru {t}"),
        AgentEvent(
            ts=MOCK_TS,
            kind="alert_raised",
            ref="AL-001",
            message="Alertă critică trimisă pe webhook",
        ),
        AgentEvent(
            ts=MOCK_TS,
            kind="work_order_created",
            ref="WO-001",
            message="Ordin de lucru WO-001 creat",
        ),
    ]


def stream_events() -> list[StreamEvent]:
    """One event of each §9 type, in flight order."""
    flown = compose.frames(MissionSettings())
    m, fr = park()[0], flown[0]
    return [
        StreamEvent(type="waypoint", data={"x_m": m.x_m, "y_m": m.y_m, "table": m.table}),
        StreamEvent(type="frame_captured", data=fr.model_dump()),
        StreamEvent(
            type="frame_checked", data={"frame_id": fr.id, "check_ok": True, "problems": []}
        ),
        StreamEvent(type="cloud", data={"irradiance_wm2": 450.0}),
        StreamEvent(type="flight_done", data={"frames": len(flown)}),
        StreamEvent(type="findings_ready", data={"count": len(findings())}),
        StreamEvent(type="alert_raised", data=alerts()[0].model_dump()),
        StreamEvent(type="agent_event", data=events()[0].model_dump()),
    ]


def report_html(mission_id: str) -> str:
    rows = "".join(
        f"<tr><td>{f.module_id}</td><td>{f.prediction.cls}</td><td>{f.urgency}</td></tr>"
        for f in findings()
    )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>Raport {mission_id}</title>"
        f"</head><body><h1>Raport misiune {mission_id} (mock)</h1>"
        f"<table><tr><th>Modul</th><th>Clasă</th><th>Urgență</th></tr>{rows}</table>"
        "</body></html>"
    )


@lru_cache
def gray_png(width: int = 24, height: int = 40, value: int = 128) -> bytes:
    """A flat 8-bit grayscale PNG, built with the stdlib only."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"".join(b"\x00" + bytes([value]) * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
