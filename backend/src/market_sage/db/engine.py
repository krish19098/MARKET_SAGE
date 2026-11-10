"""Engine creation and schema bootstrap."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event

from market_sage.core.config import get_settings


def make_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, future=True, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _rec):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def upgrade_to_head(url: str | None = None) -> None:
    """Apply Alembic migrations programmatically."""
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url or get_settings().database_url)
    command.upgrade(cfg, "head")
