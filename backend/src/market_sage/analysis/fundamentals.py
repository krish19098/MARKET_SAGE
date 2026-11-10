"""Point-in-time fundamentals accessor.

Values become usable only from their public ``published_at`` timestamp. When no filings exist the
analyst reports fundamentals as *unknown* — values are never invented.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Engine, select

from market_sage.analysis.evidence import Evidence
from market_sage.db import schema as s


def latest_filings(
    engine: Engine, instrument_id: int, known_by: datetime, kind: str = "results", n: int = 8
) -> list[dict]:
    t = s.filings
    with engine.connect() as conn:
        rows = conn.execute(
            select(t)
            .where((t.c.instrument_id == instrument_id) & (t.c.kind == kind) & (t.c.published_at <= known_by))
            .order_by(t.c.published_at.desc())
            .limit(n)
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def fundamental_evidence(engine: Engine, instrument_id: int, known_by: datetime) -> list[Evidence]:
    rows = latest_filings(engine, instrument_id, known_by)
    if not rows:
        return [
            Evidence(
                "fundamentals",
                "unknown",
                "neutral",
                "No point-in-time fundamental filings ingested for this company; fundamentals unknown.",
                method="filings PIT lookup",
            )
        ]
    out: list[Evidence] = []
    cur = rows[0]["payload"]
    prev = next(
        (
            r["payload"]
            for r in rows[1:]
            if r["period_end"] and rows[0]["period_end"] and (rows[0]["period_end"] - r["period_end"]).days > 300
        ),
        None,
    )
    as_of = rows[0]["published_at"].isoformat()
    for key, label in (("revenue", "Revenue"), ("net_profit", "Net profit")):
        if prev and cur.get(key) and prev.get(key):
            g = cur[key] / prev[key] - 1
            out.append(
                Evidence(
                    "fundamentals",
                    "fact",
                    "bullish" if g > 0.1 else "bearish" if g < 0 else "neutral",
                    f"{label} YoY growth {g:+.1%} (filing published {as_of})",
                    value=g,
                    method="YoY from PIT filings",
                    as_of=as_of,
                )
            )
    for key, label, good in (("roe", "ROE", 0.15), ("roce", "ROCE", 0.15)):
        if cur.get(key) is not None:
            v = float(cur[key])
            out.append(
                Evidence(
                    "fundamentals",
                    "fact",
                    "bullish" if v >= good else "neutral",
                    f"{label} {v:.1%}",
                    value=v,
                    method="reported",
                    as_of=as_of,
                )
            )
    if cur.get("debt_to_equity") is not None:
        de = float(cur["debt_to_equity"])
        out.append(
            Evidence(
                "fundamentals",
                "fact",
                "bearish" if de > 1.5 else "neutral",
                f"Debt/equity {de:.2f}",
                value=de,
                method="reported",
                as_of=as_of,
            )
        )
    return out or [Evidence("fundamentals", "unknown", "neutral", "Filings present but no parsable metrics.")]
