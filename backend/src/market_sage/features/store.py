"""Universe feature store with forward outcomes and their *availability dates*.

Forward outcome columns (``fwd_ret_h``, ``mfe_h``, ``mae_h``) for a row at session t are only knowable
at session t+h; ``known_h`` records that date so research/learning code can filter to outcomes that
were observable at a given cutoff (no look-ahead).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from market_sage.data.service import MarketDataService
from market_sage.features.builder import build_features

HORIZONS = (1, 3, 5, 10, 20)


def add_forward_outcomes(f: pd.DataFrame, horizons: tuple[int, ...] = HORIZONS) -> pd.DataFrame:
    c, h, lo = f["close"], f["high"], f["low"]
    for n in horizons:
        f[f"fwd_ret_{n}"] = c.shift(-n) / c - 1
        fut_h = pd.concat([h.shift(-k) for k in range(1, n + 1)], axis=1).max(axis=1, skipna=False)
        fut_l = pd.concat([lo.shift(-k) for k in range(1, n + 1)], axis=1).min(axis=1, skipna=False)
        f[f"mfe_{n}"] = fut_h / c - 1
        f[f"mae_{n}"] = fut_l / c - 1
        f[f"known_{n}"] = f["session_date"].shift(-n)
    return f


class FeatureStore:
    def __init__(self, mds: MarketDataService, index_symbol: str = "NIFTY 50") -> None:
        self.mds = mds
        self.index_symbol = index_symbol
        self._cache: dict[tuple[int, date | None], pd.DataFrame] = {}

    def index_instrument(self) -> dict | None:
        for sym in (self.index_symbol, "SYNNIFTY"):
            inst = self.mds.instruments.by_symbol("NSE", sym)
            if inst is not None:
                return inst
        return None

    def instrument_features(self, instrument_id: int, until: date | None = None) -> pd.DataFrame:
        """Features as they were knowable at session ``until``.

        Fast path: all features are trailing-window, so the full-history frame truncated at ``until`` is
        identical to a recomputation — unless a corporate action with ex-date after ``until`` exists (its
        adjustment could not have been known), in which case features are recomputed from scratch.
        Forward-outcome columns not yet observable at ``until`` are masked.
        """
        key = (instrument_id, until)
        if key in self._cache:
            return self._cache[key]
        if until is not None and not any(a.ex_date > until for a in self.mds.corporate_actions(instrument_id)):
            full = self.instrument_features(instrument_id, None)
            f = full[full["session_date"] <= until].copy()
            for n in HORIZONS:
                unknown = f[f"known_{n}"].isna() | (f[f"known_{n}"] > until)
                f.loc[unknown, [f"fwd_ret_{n}", f"mfe_{n}", f"mae_{n}"]] = np.nan
                f.loc[unknown, f"known_{n}"] = None
            self._cache[key] = f
            return f
        return self._compute(instrument_id, until)

    def _compute(self, instrument_id: int, until: date | None) -> pd.DataFrame:
        key = (instrument_id, until)
        inst = self.mds.instruments.get(instrument_id)
        assert inst is not None
        bars = self.mds.daily_bars(instrument_id, until=until)
        idx = self.index_instrument()
        idx_bars = self.mds.daily_bars(idx["id"], until=until) if idx and idx["id"] != instrument_id else None
        sector_bars = None
        if inst.get("sector"):
            sec = self.mds.instruments.by_symbol("NSE", inst["sector"])
            if sec is not None:
                sector_bars = self.mds.daily_bars(sec["id"], until=until)
        f = build_features(bars, idx_bars, sector_bars)
        f.insert(0, "instrument_id", instrument_id)
        f = add_forward_outcomes(f)
        self._cache[key] = f
        return f

    def universe_features(self, until: date | None = None, instrument_ids: list[int] | None = None) -> pd.DataFrame:
        ids = instrument_ids or [i["id"] for i in self.mds.instruments.all(include_indices=False)]
        frames = [self.instrument_features(i, until) for i in ids]
        frames = [f for f in frames if not f.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def clear(self) -> None:
        self._cache.clear()


def outcome_known(frame: pd.DataFrame, horizon: int, cutoff: date) -> pd.Series:
    k = frame[f"known_{horizon}"]
    return k.notna() & (k <= cutoff) & np.isfinite(frame[f"fwd_ret_{horizon}"])
