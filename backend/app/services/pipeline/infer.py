"""Step 3 (DESIGN_SPEC §5): 24×40 crops → ONNX logits → softmax(z / T)."""

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort

ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts"
META = json.loads((ARTIFACTS / "model_meta.json").read_text(encoding="utf-8"))
CLASSES: list[str] = META["classes"]


def load_model(path: Path = ARTIFACTS / "model.onnx") -> ort.InferenceSession:
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def probs(model: ort.InferenceSession, crops: np.ndarray, temperature: float) -> np.ndarray:
    """(n, 40, 24) gray crops with pixels 0–255 → (n, 8) probabilities, in CLASSES order."""
    x = (np.asarray(crops, dtype=np.float32) / 255.0)[:, None]
    z = model.run([META["output_name"]], {META["input_name"]: x})[0] / temperature
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)
