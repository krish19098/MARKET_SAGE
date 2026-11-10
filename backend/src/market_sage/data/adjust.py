"""Corporate-action adjustment (L2). Unadjusted bars are always retained; factors are computed here.

Split/bonus adjust prices (divide) and volumes (multiply) for sessions before the ex-date.
Cash dividends are *not* adjusted in the price series (documented limitation; total-return series later).
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from market_sage.data.models import CorporateAction


def action_factor(ca: CorporateAction) -> float:
    """Multiplicative share-count factor for split/bonus; 1.0 for others."""
    if ca.kind == "split" and ca.ratio_num and ca.ratio_den:
        return ca.ratio_num / ca.ratio_den  # e.g. FV 10 -> 2 : ratio 5/1
    if ca.kind == "bonus" and ca.ratio_num and ca.ratio_den:
        return (ca.ratio_num + ca.ratio_den) / ca.ratio_den  # a:b bonus -> (a+b)/b
    return 1.0


def adjust_bars(bars: pd.DataFrame, actions: Iterable[CorporateAction]) -> pd.DataFrame:
    df = bars.copy()
    if df.empty:
        df["adj_factor"] = []
        return df
    cum = pd.Series(1.0, index=df.index)
    for ca in actions:
        f = action_factor(ca)
        if f != 1.0:
            cum[df["session_date"] < ca.ex_date] *= f
    for c in ("open", "high", "low", "close"):
        df[c] = df[c] / cum
    for c in ("volume", "delivery_qty"):
        if c in df:
            df[c] = df[c] * cum
    df["adj_factor"] = cum
    return df
