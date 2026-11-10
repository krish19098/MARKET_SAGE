"""Warehouse storage: L0 immutable raw files, L1 canonical Parquet bars, instrument registry."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, and_, insert, select

from market_sage.core.timeutil import IST, utcnow
from market_sage.data.models import BAR_COLUMNS, Interval, ProviderInstrument
from market_sage.db import schema as s

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


class RawStore:
    """Stores source payloads exactly as received, with checksum and provenance (never modified)."""

    def __init__(self, engine: Engine, root: Path) -> None:
        self.engine, self.root = engine, root

    def save(
        self,
        provider: str,
        dataset: str,
        source_ref: str,
        content: bytes,
        filename: str,
        *,
        is_synthetic: bool = False,
        licence_note: str | None = None,
    ) -> int:
        sha = hashlib.sha256(content).hexdigest()
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(s.raw_files.c.id).where(and_(s.raw_files.c.sha256 == sha, s.raw_files.c.dataset == dataset))
            ).scalar()
            if existing is not None:
                return int(existing)
            now = utcnow()
            path = self.root / "raw" / provider / dataset / f"{now:%Y}" / f"{sha[:12]}_{_SAFE.sub('_', filename)}"
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(content)
                path.chmod(0o444)
            res = conn.execute(
                insert(s.raw_files).values(
                    provider=provider,
                    dataset=dataset,
                    source_ref=source_ref,
                    path=str(path),
                    sha256=sha,
                    size_bytes=len(content),
                    fetched_at=now,
                    is_synthetic=is_synthetic,
                    licence_note=licence_note,
                )
            )
            return int(res.inserted_primary_key[0])  # type: ignore[index]


@dataclass
class UpsertResult:
    inserted: int
    conflicts: pd.DataFrame  # rows whose values differ from already-stored rows (kept original)


class BarStore:
    """Canonical (unadjusted) bars in Parquet, one file per (exchange, interval, instrument)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, exchange: str, interval: Interval, instrument_id: int) -> Path:
        return self.root / "bars" / exchange / interval.value / f"{instrument_id}.parquet"

    def read(self, exchange: str, interval: Interval, instrument_id: int) -> pd.DataFrame:
        p = self._path(exchange, interval, instrument_id)
        if not p.exists():
            return pd.DataFrame(columns=BAR_COLUMNS)
        return pd.read_parquet(p)

    def upsert(self, exchange: str, interval: Interval, instrument_id: int, bars: pd.DataFrame) -> UpsertResult:
        bars = bars[BAR_COLUMNS].copy()
        existing = self.read(exchange, interval, instrument_id)
        if existing.empty:
            merged, conflicts, inserted = bars, bars.iloc[0:0], len(bars)
        else:
            joined = bars.merge(
                existing[["ts", "open", "high", "low", "close", "volume"]],
                on="ts",
                how="left",
                suffixes=("", "_old"),
                indicator=True,
            )
            dup = joined["_merge"] == "both"
            differs = dup & (
                (joined["close"] - joined["close_old"]).abs().gt(1e-9)
                | (joined["volume"] - joined["volume_old"]).abs().gt(1e-6)
                | (joined["high"] - joined["high_old"]).abs().gt(1e-9)
                | (joined["low"] - joined["low_old"]).abs().gt(1e-9)
            )
            conflicts = bars[differs.to_numpy()]
            new_rows = bars[(~dup).to_numpy()]
            inserted = len(new_rows)
            merged = pd.concat([existing, new_rows], ignore_index=True) if inserted else existing
        merged = merged.sort_values("ts").reset_index(drop=True)
        p = self._path(exchange, interval, instrument_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        merged.to_parquet(tmp, index=False)
        tmp.replace(p)
        return UpsertResult(inserted, conflicts)


class InstrumentRegistry:
    """Stable internal instrument ids across symbol changes and providers."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get_or_create(
        self,
        exchange: str,
        symbol: str,
        *,
        isin: str | None = None,
        name: str | None = None,
        series: str | None = None,
        sector: str | None = None,
        is_index: bool = False,
        as_of: date | None = None,
    ) -> int:
        t = s.instruments
        with self.engine.begin() as conn:
            row = None
            if isin:
                row = conn.execute(
                    select(t.c.id, t.c.symbol).where(and_(t.c.isin == isin, t.c.exchange == exchange))
                ).first()
            if row is None:
                row = conn.execute(
                    select(t.c.id, t.c.symbol).where(and_(t.c.exchange == exchange, t.c.symbol == symbol))
                ).first()
            if row is not None:
                iid = int(row.id)
                if row.symbol != symbol:  # symbol change detected via ISIN
                    conn.execute(t.update().where(t.c.id == iid).values(symbol=symbol))
                    sh = s.symbol_history
                    conn.execute(
                        sh.update()
                        .where(and_(sh.c.instrument_id == iid, sh.c.valid_to.is_(None)))
                        .values(valid_to=as_of or utcnow().astimezone(IST).date())
                    )
                    conn.execute(
                        insert(sh).values(
                            instrument_id=iid,
                            exchange=exchange,
                            symbol=symbol,
                            valid_from=as_of or utcnow().astimezone(IST).date(),
                        )
                    )
                return iid
            res = conn.execute(
                insert(t).values(
                    exchange=exchange,
                    symbol=symbol,
                    isin=isin,
                    name=name,
                    series=series,
                    sector=sector,
                    is_index=is_index,
                    created_at=utcnow(),
                )
            )
            iid = int(res.inserted_primary_key[0])  # type: ignore[index]
            conn.execute(
                insert(s.symbol_history).values(
                    instrument_id=iid, exchange=exchange, symbol=symbol, valid_from=as_of or date(1990, 1, 1)
                )
            )
            return iid

    def map_provider(self, inst: ProviderInstrument, instrument_id: int, valid_from: date) -> None:
        m = s.provider_instrument_map
        with self.engine.begin() as conn:
            exists = conn.execute(
                select(m.c.id).where(
                    and_(
                        m.c.provider == inst.provider, m.c.provider_token == inst.provider_token, m.c.valid_to.is_(None)
                    )
                )
            ).first()
            if exists is None:
                conn.execute(
                    insert(m).values(
                        provider=inst.provider,
                        provider_token=inst.provider_token,
                        exchange=inst.exchange,
                        symbol=inst.symbol,
                        instrument_id=instrument_id,
                        valid_from=valid_from,
                    )
                )

    def provider_token(self, provider: str, instrument_id: int) -> str | None:
        m = s.provider_instrument_map
        with self.engine.connect() as conn:
            return conn.execute(
                select(m.c.provider_token).where(
                    and_(m.c.provider == provider, m.c.instrument_id == instrument_id, m.c.valid_to.is_(None))
                )
            ).scalar()

    def by_symbol(self, exchange: str, symbol: str) -> dict | None:
        t = s.instruments
        with self.engine.connect() as conn:
            row = conn.execute(select(t).where(and_(t.c.exchange == exchange, t.c.symbol == symbol))).first()
            return dict(row._mapping) if row else None

    def get(self, instrument_id: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(s.instruments).where(s.instruments.c.id == instrument_id)).first()
            return dict(row._mapping) if row else None

    def all(self, include_indices: bool = True) -> list[dict]:
        t = s.instruments
        q = select(t).order_by(t.c.id)
        if not include_indices:
            q = q.where(t.c.is_index.is_(False))
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]
