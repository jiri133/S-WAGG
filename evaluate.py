"""Evaluation on the test split, run once (DESIGN_SPEC §3.6).

Models: rules → Random Forest → ResNet18 (production) → small CNN from scratch (ablation, §3.3.4),
then the degradation test (noise, blur, contrast) on the production model.

Writes reports/eval.json (schema: backend/app/schemas/eval.py), served by GET /api/eval and
drawn by React. The data download and the Random Forest run in the ml/ environment, because
they need scikit-learn, which stays out of the backend.

    uv run --project backend python evaluate.py
"""

import base64
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas import EvalReport  # noqa: E402
from app.services import metrics  # noqa: E402
from app.services.baseline.features import load_crop, vector  # noqa: E402
from app.services.baseline.rules_classifier import load_thresholds, predict  # noqa: E402
from app.services.pipeline import calibrate, infer  # noqa: E402

CLASSES = infer.CLASSES
OUT = ROOT / "reports" / "eval.json"
RF_PRED = ROOT / "backend" / "cache" / "rf_test_pred.json"
SMALL_CNN = infer.ARTIFACTS / "small_cnn.onnx"  # ablation from ml/train_small.py, not served
N_CONFUSIONS, N_EXAMPLES = 5, 6
# Degradation test (§3.6) on the 8-bit test crops: level 0 (clean), then 3 levels.
DEGRADATIONS = {
    "noise": ("sigma", [0.0, 5.0, 10.0, 20.0]),  # Gaussian σ, in gray levels out of 255
    "blur": ("radius_px", [0.0, 0.5, 1.0, 2.0]),  # PIL GaussianBlur radius
    "contrast": ("kept", [1.0, 0.75, 0.5, 0.25]),  # share of contrast kept around the crop mean
}
NOTES = [
    "Modelele prezic 8 clase, deci pe cele 12 clase Raptor se raportează doar recall-ul "
    "(cât din fiecare clasă originală ajunge în clasa ei mapată), nu macro-F1.",
    "Robustețea pe pipeline (§6) e testată separat, pe simulator, în "
    "backend/tests/test_robustness.py (tichetul 22), nu aici.",
    "Degradarea se aplică pe crop-urile de test, cu modelul din producție (model.onnx).",
]


def run_ml(*args: str) -> None:
    cmd = ["uv", "run", "--project", str(ROOT / "ml"), "python", *args]
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}  # the backend's venv
    subprocess.run(cmd, cwd=ROOT / "ml", env=env, check=True)


def model_scores(name: str, y: np.ndarray, pred: np.ndarray, raptor: np.ndarray) -> dict:
    cm = metrics.confusion(y, pred, len(CLASSES))
    f1 = metrics.f1_per_class(cm)
    correct = y == pred
    recall_12 = {r: float(correct[raptor == r].mean()) for r in sorted(set(raptor))}
    return {
        "name": name,
        "macro_f1": float(f1.mean()),
        "accuracy": float(correct.mean()),
        "f1_per_class": dict(zip(CLASSES, map(float, f1), strict=True)),
        "recall_12": recall_12,
        "macro_recall_12": float(np.mean(list(recall_12.values()))),
        "confusion": cm.tolist(),
    }


def selective(p: np.ndarray, y: np.ndarray, th: dict) -> dict:
    """Coverage and precision of what passes the thresholds automatically (not `unsure`)."""
    auto = np.array([calibrate.unsure_reason(row, th) is None for row in p])
    pred = p.argmax(axis=1)
    hit = pred == y
    per_class = {}
    for k, c in enumerate(CLASSES):
        m = auto & (pred == k)
        precision = float(hit[m].mean()) if m.any() else None
        per_class[c] = {"auto": int(m.sum()), "precision": precision}
    return {
        "target_precision": min(g["target_precision"] for g in th["groups"].values()),
        "coverage": float(auto.mean()),
        "precision_auto": float(hit[auto].mean()),
        "per_class": per_class,
    }


def perturb(crops: np.ndarray, kind: str, value: float, rng: np.random.Generator) -> np.ndarray:
    """(n, 40, 24) crops in 0–255 → the same crops perturbed, rounded back to 8-bit levels."""
    x = np.asarray(crops, dtype=np.float32)
    if kind == "noise":
        x = x + rng.normal(0.0, value, x.shape)
    elif kind == "blur":
        blur = ImageFilter.GaussianBlur(value)
        x = np.stack([np.asarray(Image.fromarray(c.astype(np.uint8)).filter(blur)) for c in x])
    elif kind == "contrast":
        mean = x.mean(axis=(1, 2), keepdims=True)
        x = mean + (x - mean) * value
    else:
        raise ValueError(kind)
    return np.rint(np.clip(x, 0, 255)).astype(np.float32)


def degradation(classify, crops: np.ndarray, y: np.ndarray) -> list[dict]:
    """Macro-F1 of `classify` (crops → class indices) per perturbation and level (0 = clean)."""
    def macro_f1(x: np.ndarray) -> float:
        cm = metrics.confusion(y, classify(x), len(CLASSES))
        return float(metrics.f1_per_class(cm).mean())

    rng, clean = np.random.default_rng(0), macro_f1(crops)
    return [{"kind": kind, "param": param, "levels": [
        {"level": i, "value": v,
         "macro_f1": clean if i == 0 else macro_f1(perturb(crops, kind, v, rng))}
        for i, v in enumerate(values)]} for kind, (param, values) in DEGRADATIONS.items()]


def png_uri(path: Path) -> str:
    buf = io.BytesIO()
    Image.open(path).convert("L").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def errors(p: np.ndarray, y: np.ndarray, rows: list[dict]) -> list[dict]:
    """Top confusions of the model, each with its most confident wrong examples."""
    pred, conf = p.argmax(axis=1), p.max(axis=1)
    cm = metrics.confusion(y, pred, len(CLASSES))
    out = []
    for t, k, count in metrics.top_confusions(cm, N_CONFUSIONS):
        idx = np.flatnonzero((y == t) & (pred == k))
        idx = idx[np.argsort(-conf[idx], kind="stable")][:N_EXAMPLES]
        out.append({
            "truth": CLASSES[t], "pred": CLASSES[k], "count": count,
            "examples": [{"image_id": rows[i]["image_id"], "conf": float(conf[i]),
                          "crop_png": png_uri(ROOT / rows[i]["path"])} for i in idx],
        })
    return out


def main() -> None:
    run_ml("-c", "import data; data.download(); data.extract()")
    RF_PRED.parent.mkdir(parents=True, exist_ok=True)
    run_ml("baseline_rf.py", "--test", str(RF_PRED))

    with open(ROOT / "ml" / "splits" / "test.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    y = np.array([CLASSES.index(r["class"]) for r in rows])
    raptor = np.array([r["raptor_class"] for r in rows])
    crops = np.stack([load_crop(ROOT / r["path"]) for r in rows])

    rules = predict(np.stack([vector(c) for c in crops]), load_thresholds())
    rf_by_id = json.loads(RF_PRED.read_text(encoding="utf-8"))
    rf = [rf_by_id[r["image_id"]] for r in rows]

    model, t, th = infer.load_model(), calibrate.load_temperature(), calibrate.load_thresholds()
    p_raw, p = infer.probs(model, crops, 1.0), infer.probs(model, crops, t)

    models = [model_scores(name, y, np.array([CLASSES.index(c) for c in pred]), raptor)
              for name, pred in [("rules", rules), ("random_forest", rf)]]
    models.append(model_scores("resnet18", y, p.argmax(axis=1), raptor))
    small = infer.probs(infer.load_model(SMALL_CNN), crops, 1.0).argmax(axis=1)
    models.append(model_scores("small_cnn", y, small, raptor))
    report = EvalReport.model_validate({
        "split": "test",
        "n": len(rows),
        "classes": CLASSES,
        "support": {c: int((y == k).sum()) for k, c in enumerate(CLASSES)},
        "models": models,
        "calibration": {
            "temperature": t,
            "ece_before": metrics.ece(p_raw, y), "ece_after": metrics.ece(p, y),
            "bins_before": metrics.reliability(p_raw, y), "bins_after": metrics.reliability(p, y),
        },
        "risk_coverage": metrics.risk_coverage(p.max(axis=1), p.argmax(axis=1) == y),
        "selective": selective(p, y, th),
        "degradation": degradation(lambda x: infer.probs(model, x, t).argmax(axis=1), crops, y),
        "errors": errors(p, y, rows),
        "notes": NOTES,
    })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(report.model_dump_json(indent=1), encoding="utf-8")

    for m in report.models:
        print(f"{m.name:14s} macro-F1 {m.macro_f1:.3f}  macro-recall-12 {m.macro_recall_12:.3f}")
    c, s = report.calibration, report.selective
    print(f"ECE {c.ece_before:.3f} -> {c.ece_after:.3f} (T={t:.2f}); auto coverage "
          f"{s.coverage:.3f} at precision {s.precision_auto:.3f} (target {s.target_precision})")
    for d in report.degradation:
        print(f"{d.kind:9s} " + "  ".join(f"{lv.value:g}: {lv.macro_f1:.3f}" for lv in d.levels))
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
