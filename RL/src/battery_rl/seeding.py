"""Deterministic seeding helpers for experiments."""

from __future__ import annotations

import os
import random

import numpy as np


def seed_everything(seed: int) -> np.random.Generator:
    """Seed Python, NumPy and (if installed) PyTorch; return a NumPy generator."""
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    np.random.seed(seed)
    try:  # optional; torch is only needed for the optional PPO benchmark
        import torch

        torch.manual_seed(seed)
    except ImportError:
        pass
    return np.random.default_rng(seed)


def make_rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)
