"""Model ladder: baselines and candidate learners behind one interface (predict_proba over CLASSES)."""

from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from market_sage.models.calibration import CLASSES


class Estimator(Protocol):
    name: str

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> Estimator: ...
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray: ...


def _full_proba(model, X: pd.DataFrame) -> np.ndarray:
    p = model.predict_proba(X)
    out = np.zeros((len(X), len(CLASSES)))
    for j, cls in enumerate(model.classes_):
        out[:, CLASSES.index(int(cls))] = p[:, j]
    return out


class Climatology:
    name = "climatology"

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> Climatology:
        self.p = np.array([(y == c).mean() for c in CLASSES])
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return np.tile(self.p, (len(X), 1))


class MomentumRule:
    """Class frequencies conditional on a simple trend rule (ret_20 > 0 and price above 50-SMA)."""

    name = "momentum_rule"

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> MomentumRule:
        m = self._mask(X)
        base = np.array([(y == c).mean() for c in CLASSES])
        self.p_on = np.array([(y[m] == c).mean() for c in CLASSES]) if m.sum() > 30 else base
        self.p_off = np.array([(y[~m] == c).mean() for c in CLASSES]) if (~m).sum() > 30 else base
        return self

    @staticmethod
    def _mask(X: pd.DataFrame) -> np.ndarray:
        return ((X["ret_20"] > 0) & (X["c_sma50"] > 0)).to_numpy()

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        m = self._mask(X)
        return np.where(m[:, None], self.p_on, self.p_off)


class SkModel:
    def __init__(self, name: str, model) -> None:
        self.name, self.model = name, model

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> SkModel:
        self.model.fit(X, y.astype(int))
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return _full_proba(self.model, X)


def make_estimator(name: str, seed: int = 0) -> Estimator:
    if name == "climatology":
        return Climatology()
    if name == "momentum_rule":
        return MomentumRule()
    if name == "logistic":
        return SkModel(
            name,
            make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=500)),
        )
    if name == "random_forest":
        return SkModel(
            name,
            make_pipeline(
                SimpleImputer(strategy="median"),
                RandomForestClassifier(
                    n_estimators=200, min_samples_leaf=50, max_features="sqrt", n_jobs=-1, random_state=seed
                ),
            ),
        )
    if name == "hgb":
        return SkModel(
            name,
            HistGradientBoostingClassifier(
                max_depth=3,
                learning_rate=0.05,
                max_iter=200,
                min_samples_leaf=100,
                l2_regularization=1.0,
                random_state=seed,
            ),
        )
    raise ValueError(name)


LADDER = ("climatology", "momentum_rule", "logistic", "random_forest", "hgb")
