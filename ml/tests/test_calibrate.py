import json

import numpy as np

import calibrate as cal

N_CLS = len(cal.CLASSES)


def overconfident_logits(n: int = 4000, seed: int = 0):
    """Logits sintetice de 3× prea mari: modelul e corect ~70% dar pare aproape sigur."""
    rng = np.random.default_rng(seed)
    y = rng.integers(0, N_CLS, n)
    logits = rng.normal(0, 1, (n, N_CLS))
    logits[np.arange(n), y] += 1.5
    return logits * 3, y


def test_softmax_rows_sum_to_one_and_temperature_flattens():
    logits, _ = overconfident_logits(50)
    p1, p3 = cal.softmax(logits), cal.softmax(logits, 3.0)
    assert np.allclose(p1.sum(axis=1), 1) and np.allclose(p3.sum(axis=1), 1)
    assert p3.max(axis=1).mean() < p1.max(axis=1).mean()


def test_fit_temperature_recovers_scale_and_lowers_ece():
    logits, y = overconfident_logits()
    t = cal.fit_temperature(logits, y)
    assert t > 1.5  # logits prea mari → T > 1 le turtește
    assert cal.nll(logits, y, t) < cal.nll(logits, y, 1.0)
    assert cal.ece(cal.softmax(logits, t), y) < cal.ece(cal.softmax(logits), y) / 2


def test_ece_is_zero_for_perfect_calibration():
    probs = np.zeros((10, N_CLS))
    probs[:, 0] = 1.0
    assert cal.ece(probs, np.zeros(10, int)) == 0.0


def test_thresholds_reach_target_and_route_weak_class_to_unsure(tmp_path):
    rng = np.random.default_rng(1)
    ok, off, diode = (cal.CLASSES.index(c) for c in ("ok", "module_offline", "diode_substring"))
    n = 600
    # ok sigur și corect; diode corect; module_offline prezis sigur, dar jumătate sunt ok.
    y = np.r_[np.full(n, ok), np.full(n, diode), np.full(n // 2, off), np.full(n // 2, ok)]
    pred = np.r_[np.full(n, ok), np.full(n, diode), np.full(n, off)]
    probs = np.full((len(y), N_CLS), 0.01)
    probs[np.arange(len(y)), pred] = rng.uniform(0.6, 0.99, len(y))
    probs /= probs.sum(axis=1, keepdims=True)

    th = cal.choose_thresholds(probs, y)
    assert th["min_conf"]["module_offline"] == 1.01
    assert th["min_conf"]["diode_substring"] <= 0.6
    assert th["val"]["precision_auto"] >= 0.95
    unsure = cal.unsure_mask(probs, th)
    assert unsure[pred == off].all() and not unsure[pred == diode].any()

    risky_ok = probs[:1].copy()
    risky_ok[0, ok], risky_ok[0, diode] = 0.7, 0.3
    assert cal.unsure_mask(risky_ok, th)[0]

    json.dumps(th)  # se poate scrie în thresholds.json
    cal.draw_reliability(cal.reliability(probs, y), cal.reliability(probs, y),
                         tmp_path / "r.png")
    assert (tmp_path / "r.png").stat().st_size > 0
