import numpy as np
import pandas as pd
import pytest

from market_sage.analysis.analogues import find_analogues
from market_sage.analysis.analyst import Analyst
from market_sage.features import indicators as ind
from market_sage.features.builder import MODEL_FEATURES
from market_sage.features.store import FeatureStore, outcome_known
from market_sage.features.structure import confirmed_pivots


def test_indicator_reference_values():
    c = pd.Series(
        [
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
            46.00,
            46.03,
            46.41,
            46.22,
            45.64,
        ]
    )
    r = ind.rsi(c, 14)
    # StockCharts' published Wilder example (computed with rounded intermediates): 70.53, 66.32, 66.55, 69.41, 66.36, 57.97
    assert list(r.iloc[14:]) == pytest.approx([70.53, 66.32, 66.55, 69.41, 66.36, 57.97], abs=0.1)
    assert ind.sma(c, 3).iloc[2] == pytest.approx(c.iloc[:3].mean())
    h, lo = c + 1, c - 1
    assert (ind.atr(h, lo, c, 5).dropna() > 0).all()
    k, _ = ind.stochastic(h, lo, c)
    assert k.dropna().between(0, 100).all()


def test_pivots_confirmed_with_lag():
    high = np.array([1, 2, 5, 2, 1, 1, 1], dtype=float)
    low = high - 0.5
    p = [x for x in confirmed_pivots(high, low, k=2) if x.kind == "high"]
    assert p and p[0].idx == 2 and p[0].confirmed_at == 4


def test_features_are_point_in_time(mds):
    store = FeatureStore(mds)
    iid = mds.instruments.by_symbol("NSE", "SYN005")["id"]
    full = store.instrument_features(iid)
    cut = full["session_date"].iloc[400]
    trunc = FeatureStore(mds).instrument_features(iid, until=cut)
    a = full[full["session_date"] == cut][MODEL_FEATURES].iloc[0]
    b = trunc.iloc[-1][MODEL_FEATURES]
    pd.testing.assert_series_equal(a.astype(float), b.astype(float), check_names=False)
    # forward outcomes of the truncated row are unknown (no future data available)
    assert np.isnan(trunc.iloc[-1]["fwd_ret_5"])
    assert not outcome_known(full, 5, cut)[full["session_date"] > full["session_date"].iloc[395]].any()


def test_analogues_only_use_known_outcomes(mds):
    store = FeatureStore(mds)
    pool = store.universe_features()
    cut = pool["session_date"].sort_values().unique()[700]
    row = pool[(pool["session_date"] == cut)].iloc[0]
    res = find_analogues(pool, row, cut, k=40)
    assert res is not None and res.sample_size == 40
    assert res.period[1] <= str(cut)


def test_analyst_report_has_separated_evidence(mds):
    store = FeatureStore(mds)
    pool = store.universe_features()
    iid = mds.instruments.by_symbol("NSE", "SYN004")["id"]
    cut = store.instrument_features(iid)["session_date"].iloc[-30]
    rep = Analyst(store).analyse(iid, cut, pool)
    assert rep is not None and rep.cutoff_session == cut
    kinds = {e.kind for e in rep.evidence}
    assert {"fact", "unknown"} <= kinds  # fundamentals unknown on fixture data
    assert any(e.category == "fundamentals" and e.kind == "unknown" for e in rep.evidence)
    assert rep.structure["trend"] in {"uptrend", "downtrend", "range", "undetermined"}
    assert rep.regime["regime_trend"] in {"bull", "bear", "sideways", "unknown"}


def test_failed_breakout_measured_against_broken_level():
    from market_sage.models.setups import detect_setups

    n = 80
    close = np.full(n, 100.0)
    close[-3] = 106.0  # breakout above prior high ~101
    close[-2] = 105.0
    close[-1] = 103.0  # pulled back but still well above the broken level 101 → not invalidated
    f = pd.DataFrame({"close": close, "high": close + 1, "low": close - 1, "open": close, "atr14": 2.0,
                      "vol_ratio20": 1.0, "vol_contraction": 1.0, "rs_index20": 0.0, "macd_hist_n": 0.0,
                      "ret_1": 0.0, "hammer": 0, "bullish_engulfing": 0})
    assert not any(s.stage == "invalidated" for s in detect_setups(f))
    f.loc[n - 1, ["close", "high", "low", "open"]] = [99.0, 100.0, 98.0, 99.0]  # back below 101 - 0.5
    assert any(s.name == "breakout" and s.stage == "invalidated" for s in detect_setups(f))
