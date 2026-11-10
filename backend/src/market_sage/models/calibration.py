"""Probability calibration and calibration diagnostics."""

from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression

CLASSES = (-1, 0, 1)


class IsotonicMulticlass:
    """One-vs-rest isotonic calibration, renormalised to sum to 1."""

    def __init__(self) -> None:
        self.maps: list[IsotonicRegression] = []

    def fit(self, proba: np.ndarray, y: np.ndarray) -> IsotonicMulticlass:
        self.maps = []
        for j, cls in enumerate(CLASSES):
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(proba[:, j], (y == cls).astype(float))
            self.maps.append(iso)
        return self

    def transform(self, proba: np.ndarray) -> np.ndarray:
        cal = np.column_stack([m.predict(proba[:, j]) for j, m in enumerate(self.maps)])
        cal = np.clip(cal, 1e-4, None)
        return cal / cal.sum(axis=1, keepdims=True)


def brier_multiclass(proba: np.ndarray, y: np.ndarray) -> float:
    onehot = np.column_stack([(y == c).astype(float) for c in CLASSES])
    return float(np.mean(np.sum((proba - onehot) ** 2, axis=1)))


def log_loss_multiclass(proba: np.ndarray, y: np.ndarray) -> float:
    idx = np.searchsorted(np.array(CLASSES), y.astype(int))
    p = np.clip(proba[np.arange(len(y)), idx], 1e-6, 1.0)
    return float(-np.mean(np.log(p)))


def reliability(p: np.ndarray, outcome: np.ndarray, bins: int = 10) -> dict:
    """Reliability table and expected calibration error for one class probability."""
    edges = np.linspace(0, 1, bins + 1)
    rows, ece = [], 0.0
    for a, b in zip(edges[:-1], edges[1:], strict=True):
        m = (p >= a) & ((p < b) if b < 1 else (p <= b))
        if m.sum() == 0:
            continue
        mp, fo = float(p[m].mean()), float(outcome[m].mean())
        rows.append({"bin": [round(a, 2), round(b, 2)], "n": int(m.sum()), "mean_p": mp, "freq": fo})
        ece += m.sum() / len(p) * abs(mp - fo)
    return {"bins": rows, "ece": float(ece), "n": int(len(p))}
