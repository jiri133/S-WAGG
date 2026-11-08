"""A new day's analysis: unseen faults carry over, seen ones update, ok ones are dropped."""

from app.services import findings as results
from tests import fakes


def test_merge_keeps_unseen_updates_seen_and_drops_resolved():
    today = [
        (fakes.finding(1, ("B1-R2-T3-M07", "diode_substring", "diode_substring", 9.0, False)),
         b"today-1"),
        (fakes.finding(2, ("B2-R1-T2-M11", "hot_cell", "hot_cell", 21.0, False)), b"today-2"),
    ]
    prev_seen = fakes.finding(1, ("B1-R2-T3-M07", "hot_cell", "hot_cell", 22.4, False))
    prev_seen = prev_seen.model_copy(
        update={"review": "confirmed", "review_note": "confirmat ieri"}
    )
    prev_ok = fakes.finding(2, ("B1-R4-T1-M03", "diode_substring", "multi_hot", 9.8, False))
    prev_unseen = fakes.finding(3, ("B2-R3-T4-M05", "multi_hot", "hot_cell", 12.6, True))
    prev_unseen = prev_unseen.model_copy(update={"review": "rejected"})
    imaged = {"B1-R2-T3-M07", "B2-R1-T2-M11", "B1-R4-T1-M03"}

    out = results.merge(today, [(prev_seen, b"old-1"), (prev_ok, b"old-ok"),
                                (prev_unseen, b"old-unseen")], imaged, "M-0001")
    by_mod = {f.module_id: (f, crop) for f, crop in out}

    # seen again today: today's finding wins, but the engineer's review is kept
    seen, seen_crop = by_mod["B1-R2-T3-M07"]
    assert seen.prediction.cls == "diode_substring" and seen.evidence.delta_t_k == 9.0
    assert (seen.review, seen.review_note) == ("confirmed", "confirmat ieri")
    assert seen.carried_from is None and seen.seen_ok_today is False and seen_crop == b"today-1"

    # seen ok today: kept for the engineer, because a model ok does not close the case
    ok, _ = by_mod["B1-R4-T1-M03"]
    assert ok.seen_ok_today is True and ok.carried_from == "M-0001"

    # not imaged today: carried with a new id, its crop and review
    carried, carried_crop = by_mod["B2-R3-T4-M05"]
    assert carried.carried_from == "M-0001" and carried.id not in {"F-001", "F-002"}
    assert carried.seen_ok_today is False and carried.review == "rejected"
    assert carried_crop == b"old-unseen"
