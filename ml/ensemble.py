"""Tichetul 36: mai multe modele de pe Kaggle → un singur model.onnx, ales doar pe val.

    uv run --project ml python ml/ensemble.py --ckpt a.pt --ckpt b.pt [--install]

Afișează pe val macro-F1 și acoperirea automată (după temperatură și praguri, ca în
ml/calibrate.py) ale ansamblului (TTA pe probabilități + bias pe clase), lângă modelul actual.
Cu --install, și doar dacă bate modelul actual la amândouă, scrie backend/artifacts/model.onnx,
copiază primul membru în best.pt (Grad-CAM și cazurile similare; refă-le cu ml/build_index.py)
și rulează din nou ml/calibrate.py. Testul nu e citit aici.
"""

import argparse
import shutil
from pathlib import Path

import numpy as np

import boost
import calibrate
import export_onnx
from train import ROOT, load_split

ARTIFACTS = ROOT / "backend" / "artifacts"


def member_probs(ckpt: Path, x) -> np.ndarray:
    """Probabilitățile unui membru, media pe cele 4 flip-uri."""
    net, _ = export_onnx.load_net(ckpt)
    v = boost.view_logits(net, x)
    e = np.exp(v - v.max(-1, keepdims=True))
    return (e / e.sum(-1, keepdims=True)).mean(0)


def combine(probs: list[np.ndarray]) -> np.ndarray:
    """Log-probabilitățile ansamblului: media probabilităților membrilor."""
    return np.log(np.mean(probs, axis=0))


def val_scores(z: np.ndarray, y: np.ndarray) -> dict:
    """Macro-F1 și ce trece automat, cu temperatura și pragurile alese ca în calibrate.py."""
    t = calibrate.fit_temperature(z, y)
    th = calibrate.choose_thresholds(calibrate.softmax(z, t), y)
    return {
        "macro_f1": boost.macro_f1(y, z.argmax(1)),
        "coverage": th["val"]["coverage"],
        "precision_auto": th["val"]["precision_auto"],
        "always_unsure": [c for c, m in th["min_conf"].items() if m > 1],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ckpt", action="append", required=True, help="un membru; primul → best.pt")
    p.add_argument("--install", action="store_true", help="scrie artefactele dacă bate v-ul actual")
    a = p.parse_args()
    ckpts = [Path(c) for c in a.ckpt]

    x, y = load_split("val")
    y = y.numpy()
    z = combine([member_probs(c, x) for c in ckpts])
    bias, _ = boost.search_bias(z, y)
    new = val_scores(z + bias, y)
    current = val_scores(calibrate.run_onnx(ARTIFACTS / "model.onnx", x.numpy()), y)
    for name, s in [("actual", current), ("ansamblu", new)]:
        print(f"{name:9s} val macro-F1 {s['macro_f1']:.4f}  automat {s['coverage']:.3f} "
              f"la precizie {s['precision_auto']:.3f}  mereu nesigure: {s['always_unsure']}")

    if not a.install:
        return
    if not (new["macro_f1"] > current["macro_f1"] and new["coverage"] > current["coverage"]):
        print("nu bate modelul actual pe val; artefactele rămân neschimbate")
        return
    onnx = export_onnx.export_ensemble(ckpts, ARTIFACTS, bias.tolist(), new["macro_f1"])
    gap = np.abs(calibrate.run_onnx(onnx, x.numpy()) - (z + bias)).max()
    print(f"max |ONNX - numpy| pe val: {gap:.2e}")
    assert gap < 1e-3, gap
    shutil.copy(ckpts[0], ARTIFACTS / "best.pt")
    calibrate.main()


if __name__ == "__main__":
    main()
