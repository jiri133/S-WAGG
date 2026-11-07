"""Tichetul 32: macro-F1 mai mare fără reantrenare (TTA cu flip-uri + bias pe clase).

Totul se alege DOAR pe val: TTA da/nu, media pe logits sau pe probabilități, vectorul de bias
(coordinate ascent pe o grilă, clasa `ok` fixată la 0, fiindcă un bias comun nu schimbă argmax).
Testul nu e citit aici. Cu --export, varianta cea mai bună intră în backend/artifacts/model.onnx
doar dacă bate v1 pe val; după export rulează ml/calibrate.py (T se refit-uiește după bias).

Rulează din rădăcina repo-ului:
    uv run --project ml python ml/boost.py [--export]
"""

import argparse
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

import export_onnx
from train import CLASSES, ROOT, load_split

ARTIFACTS = ROOT / "backend" / "artifacts"
# ±3 ales pe val: cu ±2 module_offline stătea la margine; pe jumătatea de val nevăzută la
# căutare, ±3 dă 0,711 față de 0,694 (±2) și 0,707 (±4).
BIAS_GRID = np.round(np.arange(-3.0, 3.0001, 0.1), 2)


def macro_f1(y: np.ndarray, pred: np.ndarray, k: int = len(CLASSES)) -> float:
    cm = np.bincount(y * k + pred, minlength=k * k).reshape(k, k)
    tp, denom = np.diag(cm), cm.sum(0) + cm.sum(1)
    return float(np.mean(np.where(denom > 0, 2 * tp / np.maximum(denom, 1), 0.0)))


def search_bias(z: np.ndarray, y: np.ndarray, grid: np.ndarray = BIAS_GRID,
                rounds: int = 5) -> tuple[np.ndarray, float]:
    """Coordinate ascent: pe rând, fiecare clasă (în afară de 0) ia valoarea din grilă care
    crește cel mai mult macro-F1 pe (z + bias).argmax. Se oprește când o rundă nu mai câștigă."""
    bias = np.zeros(z.shape[1])
    best = macro_f1(y, z.argmax(1))
    for _ in range(rounds):
        improved = False
        for c in range(1, z.shape[1]):
            for v in grid:
                cand = bias.copy()
                cand[c] = v
                f = macro_f1(y, (z + cand).argmax(1))
                if f > best + 1e-9:
                    bias, best, improved = cand, f, True
        if not improved:
            break
    return bias, best


def tta(views: np.ndarray, mode: str) -> np.ndarray:
    """(4, n, 8) logits pe flip-uri → (n, 8), la fel ca `export_onnx.Boosted`."""
    if mode == "logits":
        return views.mean(0)
    e = np.exp(views - views.max(-1, keepdims=True))
    return np.log((e / e.sum(-1, keepdims=True)).mean(0))


@torch.no_grad()
def view_logits(net: torch.nn.Module, x: torch.Tensor, bs: int = 512) -> np.ndarray:
    """Logits pe cele 4 variante: original, flip orizontal, flip vertical, ambele."""
    flips = [lambda v: v, lambda v: v.flip(-1), lambda v: v.flip(-2),
             lambda v: v.flip(-1).flip(-2)]
    return np.stack([np.concatenate([net(f(x[i:i + bs])).numpy()
                                     for i in range(0, len(x), bs)]) for f in flips])


def variants(views: np.ndarray, y: np.ndarray) -> dict[str, dict]:
    """Macro-F1 pe val pentru v1, doar TTA (ambele medii), doar bias, TTA + bias."""
    out = {}
    for name, mode in [("v1", None), ("tta_logits", "logits"), ("tta_probs", "probs")]:
        z = views[0] if mode is None else tta(views, mode)
        out[name] = {"tta": mode, "bias": [0.0] * z.shape[1], "macro_f1": macro_f1(y, z.argmax(1))}
        bias, f = search_bias(z, y)
        key = "bias" if mode is None else f"{name}+bias"
        out[key] = {"tta": mode, "bias": bias.tolist(), "macro_f1": f}
    return out


def half_check(views: np.ndarray, y: np.ndarray, mode: str | None) -> dict:
    """Stabilitate pe val: bias ales pe o jumătate, măsurat pe cealaltă (rânduri pare/impare)."""
    z = views[0] if mode is None else tta(views, mode)
    out = {}
    for name, a, b in [("even→odd", 0, 1), ("odd→even", 1, 0)]:
        bias, _ = search_bias(z[a::2], y[a::2])
        out[name] = {"without_bias": macro_f1(y[b::2], z[b::2].argmax(1)),
                     "with_bias": macro_f1(y[b::2], (z[b::2] + bias).argmax(1))}
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ckpt", default=str(ARTIFACTS / "best.pt"))
    p.add_argument("--export", action="store_true", help="scrie model.onnx dacă bate v1 pe val")
    a = p.parse_args()

    x, y = load_split("val")
    y = y.numpy()
    net, _ = export_onnx.load_net(Path(a.ckpt))
    views = view_logits(net, x)
    res = variants(views, y)
    best = max(res, key=lambda k: res[k]["macro_f1"])
    report = {"n_val": len(y), "variants": res, "best": best,
              "half_check": half_check(views, y, res[best]["tta"])}
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "boost_val.json").write_text(json.dumps(report, indent=2),
                                                     encoding="utf-8")
    for k, v in res.items():
        bias = " ".join(f"{b:+.1f}" for b in v["bias"])
        print(f"{k:18s} val macro-F1 {v['macro_f1']:.4f}  bias [{bias}]")
    print(f"cea mai bună pe val: {best}; half check {json.dumps(report['half_check'])}")

    if not a.export:
        return
    if res[best]["macro_f1"] <= res["v1"]["macro_f1"]:
        print("nimic nu bate v1 pe val; artefactele rămân neschimbate")
        return
    v = res[best]
    onnx_path = export_onnx.export(Path(a.ckpt), ARTIFACTS, tta=v["tta"], bias=v["bias"],
                                   val_macro_f1=v["macro_f1"])
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    print(f"ONNX: intrare {inp.name} {inp.shape}, ieșire {sess.get_outputs()[0].shape}")
    z = sess.run(None, {inp.name: x.numpy()})[0]
    expected = (views[0] if v["tta"] is None else tta(views, v["tta"])) + np.array(v["bias"])
    print(f"ONNX pe val: macro-F1 {macro_f1(y, z.argmax(1)):.4f}, "
          f"max |ONNX - numpy| {np.abs(z - expected).max():.2e}")


if __name__ == "__main__":
    main()
