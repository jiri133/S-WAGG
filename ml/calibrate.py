"""Calibrare (spec §3.4): temperature scaling pe val + praguri „unsure” pe grup de severitate.

Rulează model.onnx pe split-ul de validare, potrivește T (un parametru) prin NLL, raportează
ECE înainte/după, desenează reliability diagram și alege pragurile astfel încât ce trece
automat are precizie ≥ ținta grupului de severitate (risc 98%, restul 95%). Pragul se alege
pe fiecare clasă a grupului: o clasă slabă (ex. module_offline, confundată cu ok) nu blochează
o clasă bună din același grup (ex. diode_substring).

Regula „unsure” (aceeași pe care o aplică backend-ul, din thresholds.json):
  p = softmax(logits / T); c = argmax p
  unsure dacă p[c] < min_conf[c]
       sau (c == "ok" și suma p pe risk_classes > max_risk_prob_ok)

Rulează din rădăcina repo-ului:  uv run --project ml python ml/calibrate.py
"""

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageDraw

from train import CLASSES, load_split

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "backend" / "artifacts"
REPORTS = ROOT / "reports"

RISK = ["hot_cell", "multi_hot", "diode_substring"]
# min_support: sub atâtea exemple trecute automat pe val, precizia nu e de încredere și clasa
# merge mereu la inginer. Mai strict pe risc (tichetul 32: multi_hot ales pe 26 de exemple).
GROUPS = {
    "risk": {"classes": RISK, "target_precision": 0.98, "min_support": 50},
    "defect": {"classes": ["module_offline", "soiling", "shadow_vegetation", "other"],
               "target_precision": 0.95, "min_support": 20},
    "ok": {"classes": ["ok"], "target_precision": 0.95, "min_support": 20},
}
CONF_GRID = np.round(np.arange(0.30, 1.0001, 0.01), 2)
# Regulă de siguranță (spec §3.4, punct de pornire 0,15): un „ok” cu masă mare pe clasele de
# risc merge în coadă. Fix, nu optimizat: optimizat după acoperire, s-ar relaxa singur.
MAX_RISK_PROB_OK = 0.15


def softmax(logits: np.ndarray, t: float = 1.0) -> np.ndarray:
    z = logits / t
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def nll(logits: np.ndarray, y: np.ndarray, t: float) -> float:
    p = softmax(logits, t)[np.arange(len(y)), y]
    return float(-np.log(np.clip(p, 1e-12, None)).mean())


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """T care minimizează NLL, căutat pe o grilă logaritmică 0,05–20 și apoi rafinat."""
    grid = np.exp(np.linspace(np.log(0.05), np.log(20), 400))
    best = min(grid, key=lambda t: nll(logits, y, t))
    fine = np.linspace(best * 0.97, best * 1.03, 61)
    return float(min(fine, key=lambda t: nll(logits, y, t)))


def reliability(probs: np.ndarray, y: np.ndarray, n_bins: int = 15) -> list[dict]:
    """Pe bin-uri egale de încredere: număr, încredere medie, acuratețe."""
    conf, correct = probs.max(axis=1), probs.argmax(axis=1) == y
    idx = np.minimum((conf * n_bins).astype(int), n_bins - 1)
    bins = []
    for b in range(n_bins):
        m = idx == b
        n = int(m.sum())
        bins.append({"lo": b / n_bins, "hi": (b + 1) / n_bins, "n": n,
                     "conf": float(conf[m].mean()) if n else 0.0,
                     "acc": float(correct[m].mean()) if n else 0.0})
    return bins


def ece(probs: np.ndarray, y: np.ndarray, n_bins: int = 15) -> float:
    bins = reliability(probs, y, n_bins)
    return float(sum(b["n"] * abs(b["acc"] - b["conf"]) for b in bins) / len(y))


def unsure_mask(probs: np.ndarray, thresholds: dict) -> np.ndarray:
    """True unde predicția merge în coadă (vezi regula din docstring-ul modulului)."""
    pred = probs.argmax(axis=1)
    min_conf = np.array([thresholds["min_conf"][c] for c in CLASSES])
    risk_p = probs[:, [CLASSES.index(c) for c in thresholds["risk_classes"]]].sum(axis=1)
    ok_risky = (pred == CLASSES.index("ok")) & (risk_p > thresholds["max_risk_prob_ok"])
    return (probs.max(axis=1) < min_conf[pred]) | ok_risky


def choose_min_conf(probs: np.ndarray, y: np.ndarray, cls: str, target: float,
                    allowed: np.ndarray, min_support: int = 20) -> float:
    """Cel mai mic prag la care predicțiile `cls` trecute automat au precizie ≥ țintă.

    1,01 = clasa nu trece niciodată automat (nu atinge ținta cu cel puțin min_support exemple).
    """
    i = CLASSES.index(cls)
    is_cls = (probs.argmax(axis=1) == i) & allowed
    top = probs.max(axis=1)
    for t in CONF_GRID:
        m = is_cls & (top >= t)
        if m.sum() < min_support:
            break
        if (y[m] == i).mean() >= target:
            return float(t)
    return 1.01


def choose_thresholds(probs: np.ndarray, y: np.ndarray) -> dict:
    risk_p = probs[:, [CLASSES.index(c) for c in RISK]].sum(axis=1)
    min_conf = {}
    for g in GROUPS.values():
        for c in g["classes"]:
            allowed = risk_p <= MAX_RISK_PROB_OK if c == "ok" else np.ones(len(y), bool)
            min_conf[c] = choose_min_conf(probs, y, c, g["target_precision"], allowed,
                                          g["min_support"])
    th = {"risk_classes": RISK, "max_risk_prob_ok": MAX_RISK_PROB_OK, "groups": GROUPS,
          "min_conf": {c: min_conf[c] for c in CLASSES}}
    auto = ~unsure_mask(probs, th)
    pred = probs.argmax(axis=1)
    per_class = {}
    for i, c in enumerate(CLASSES):
        m = auto & (pred == i)
        per_class[c] = {"auto": int(m.sum()),
                        "precision": float((y[m] == i).mean()) if m.any() else None}
    th["val"] = {
        "coverage": float(auto.mean()),
        "precision_auto": float((pred[auto] == y[auto]).mean()) if auto.any() else None,
        "per_class": per_class,
    }
    return th


def draw_reliability(before: list[dict], after: list[dict], path: Path) -> None:
    """Două panouri (înainte / după): bare = acuratețe pe bin, diagonala = calibrare perfectă."""
    w, pad = 360, 40
    side = w - pad
    img = Image.new("RGB", (2 * w + pad, side + 3 * pad), "white")
    d = ImageDraw.Draw(img)
    for k, (title, bins) in enumerate([("inainte (T=1)", before), ("dupa (T calibrat)", after)]):
        x0, y0 = pad + k * w, pad
        d.rectangle([x0, y0, x0 + side, y0 + side], outline="black")
        for b in bins:
            if not b["n"]:
                continue
            bx0, bx1 = x0 + b["lo"] * side, x0 + b["hi"] * side
            d.rectangle([bx0, y0 + side * (1 - b["acc"]), bx1, y0 + side],
                        fill=(70, 130, 180), outline="white")
            gy = y0 + side * (1 - b["conf"])
            d.line([bx0, gy, bx1, gy], fill=(220, 50, 50), width=2)
        d.line([x0, y0 + side, x0 + side, y0], fill="gray", width=1)
        d.text((x0, y0 - 16), title, fill="black")
        d.text((x0, y0 + side + 6), "incredere 0 -> 1, bare = acuratete, rosu = incredere",
               fill="black")
    img.save(path)


def run_onnx(model: Path, x: np.ndarray, batch: int = 512) -> np.ndarray:
    sess = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name
    return np.concatenate([sess.run(None, {name: x[i:i + batch]})[0]
                           for i in range(0, len(x), batch)])


def main() -> None:
    x, y = load_split("val")
    x, y = x.numpy(), y.numpy()
    logits = run_onnx(ARTIFACTS / "model.onnx", x)
    t = fit_temperature(logits, y)
    before, after = softmax(logits), softmax(logits, t)
    temp = {"temperature": t, "n_val": len(y),
            "nll_before": nll(logits, y, 1.0), "nll_after": nll(logits, y, t),
            "ece_before": ece(before, y), "ece_after": ece(after, y)}
    th = choose_thresholds(after, y)

    (ARTIFACTS / "temperature.json").write_text(json.dumps(temp, indent=2), encoding="utf-8")
    (ARTIFACTS / "thresholds.json").write_text(json.dumps(th, indent=2), encoding="utf-8")
    REPORTS.mkdir(exist_ok=True)
    draw_reliability(reliability(before, y), reliability(after, y),
                     REPORTS / "reliability_val.png")

    pred = after.argmax(axis=1)
    ok_off = (y == CLASSES.index("ok")) & (pred == CLASSES.index("module_offline"))
    auto = ~unsure_mask(after, th)
    print(json.dumps(temp, indent=2))
    print(json.dumps(th, indent=2))
    print(f"ok→module_offline pe val: {int(ok_off.sum())}, trec automat: "
          f"{int((ok_off & auto).sum())}")


if __name__ == "__main__":
    main()
