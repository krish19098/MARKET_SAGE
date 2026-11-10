"""Operational schema (PostgreSQL in production; SQLite supported for local development and tests).

Large time series (bars) live in Parquet, not here. Tables listed in ``IMMUTABLE_TABLES`` are
append-only: database triggers reject UPDATE and DELETE (see the initial Alembic migration).
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from market_sage.db.types import UTCDateTime

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

# --- Reference / market data ---------------------------------------------------------------

instruments = Table(
    "instruments",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("isin", String(12), index=True),
    Column("name", String(200)),
    Column("exchange", String(8), nullable=False),
    Column("symbol", String(40), nullable=False),
    Column("series", String(8)),
    Column("sector", String(80)),
    Column("industry", String(120)),
    Column("is_index", Boolean, nullable=False, default=False),
    Column("listed_on", Date),
    Column("delisted_on", Date),
    Column("created_at", UTCDateTime, nullable=False),
    UniqueConstraint("exchange", "symbol", name="uq_instruments_exchange_symbol"),
)

symbol_history = Table(
    "symbol_history",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("instrument_id", ForeignKey("instruments.id"), nullable=False, index=True),
    Column("exchange", String(8), nullable=False),
    Column("symbol", String(40), nullable=False),
    Column("valid_from", Date, nullable=False),
    Column("valid_to", Date),
)

provider_instrument_map = Table(
    "provider_instrument_map",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("provider", String(32), nullable=False),
    Column("provider_token", String(64), nullable=False),
    Column("exchange", String(8), nullable=False),
    Column("symbol", String(60), nullable=False),
    Column("instrument_id", ForeignKey("instruments.id"), nullable=False, index=True),
    Column("valid_from", Date, nullable=False),
    Column("valid_to", Date),
    UniqueConstraint("provider", "provider_token", "valid_from", name="uq_pim_provider_token_from"),
)

raw_files = Table(
    "raw_files",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("provider", String(32), nullable=False),
    Column("dataset", String(64), nullable=False),
    Column("source_ref", Text, nullable=False),  # URL / endpoint + params
    Column("path", Text, nullable=False),
    Column("sha256", String(64), nullable=False, index=True),
    Column("size_bytes", Integer, nullable=False),
    Column("fetched_at", UTCDateTime, nullable=False),
    Column("is_synthetic", Boolean, nullable=False, default=False),
    Column("licence_note", Text),
)

ingestion_runs = Table(
    "ingestion_runs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("provider", String(32), nullable=False),
    Column("dataset", String(64), nullable=False),
    Column("started_at", UTCDateTime, nullable=False),
    Column("finished_at", UTCDateTime),
    Column("status", String(16), nullable=False),
    Column("rows", Integer, default=0),
    Column("message", Text),
)

data_quality_issues = Table(
    "data_quality_issues",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("ingestion_runs.id")),
    Column("instrument_id", ForeignKey("instruments.id")),
    Column("dataset", String(64), nullable=False),
    Column("trade_date", Date),
    Column("check", String(48), nullable=False),
    Column("severity", String(8), nullable=False),  # info | warn | error
    Column("detail", Text),
    Column("detected_at", UTCDateTime, nullable=False),
)

corporate_actions = Table(
    "corporate_actions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("instrument_id", ForeignKey("instruments.id"), nullable=False, index=True),
    Column("ex_date", Date, nullable=False),
    Column("kind", String(16), nullable=False),  # split | bonus | dividend | rights | other
    Column("ratio_num", Float),  # new shares (split/bonus)
    Column("ratio_den", Float),  # old shares
    Column("cash_amount", Float),
    Column("purpose", Text),
    Column("source", String(32), nullable=False),
    Column("published_at", UTCDateTime),
    Column("raw_file_id", ForeignKey("raw_files.id")),
    UniqueConstraint("instrument_id", "ex_date", "kind", name="uq_ca_instrument_exdate_kind"),
)

calendar_days = Table(
    "calendar_days",
    metadata,
    Column("trade_date", Date, primary_key=True),
    Column("exchange", String(8), primary_key=True),
    Column("status", String(16), nullable=False),  # trading | holiday
    Column("source", String(48), nullable=False),
)

filings = Table(
    "filings",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("instrument_id", ForeignKey("instruments.id"), nullable=False, index=True),
    Column("kind", String(32), nullable=False),  # results | announcement | shareholding
    Column("period_end", Date),
    Column("published_at", UTCDateTime, nullable=False),  # public availability: the PIT key
    Column("source", String(32), nullable=False),
    Column("raw_file_id", ForeignKey("raw_files.id")),
    Column("payload", JSON, nullable=False),
)

# --- Configuration versions ------------------------------------------------------------------

settings_versions = Table(
    "settings_versions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("kind", String(16), nullable=False),  # risk | costs
    Column("version", String(32), nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
    Column("payload", JSON, nullable=False),
    UniqueConstraint("kind", "version", name="uq_settings_kind_version"),
)

# --- Models -----------------------------------------------------------------------------------

model_registry = Table(
    "model_registry",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("target", String(64), nullable=False),
    Column("version", String(64), nullable=False),
    Column("algorithm", String(64), nullable=False),
    Column("status", String(16), nullable=False),  # candidate | production | rejected | retired
    Column("created_at", UTCDateTime, nullable=False),
    Column("train_start", Date),
    Column("train_end", Date),
    Column("data_hash", String(64)),
    Column("feature_set_version", String(32)),
    Column("params", JSON),
    Column("metrics", JSON),
    Column("gate_report", JSON),
    Column("artifact_path", Text),
    Column("is_synthetic_data", Boolean, nullable=False, default=False),
    Column("promoted_at", UTCDateTime),
    Column("retired_at", UTCDateTime),
    UniqueConstraint("target", "version", name="uq_model_target_version"),
)

# --- Prediction ledger (append-only) -----------------------------------------------------------

predictions = Table(
    "predictions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("seq", Integer, nullable=False, unique=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("kind", String(16), nullable=False),  # recommendation | suppressed | forecast
    Column("instrument_id", ForeignKey("instruments.id"), nullable=False, index=True),
    Column("exchange", String(8), nullable=False),
    Column("symbol", String(40), nullable=False),
    Column("data_cutoff", UTCDateTime, nullable=False),
    Column("latest_data_ts", UTCDateTime, nullable=False),
    Column("data_status", String(16), nullable=False),  # live | delayed | eod | stale | synthetic
    Column("price_at_prediction", Float),
    Column("action", String(8), nullable=False),  # BUY | HOLD | EXIT | AVOID
    Column("direction", String(8)),  # up | down | neutral
    Column("entry_low", Float),
    Column("entry_high", Float),
    Column("stop", Float),
    Column("target1", Float),
    Column("target2", Float),
    Column("horizon_sessions", Integer),
    Column("probabilities", JSON),
    Column("calibration_status", String(24), nullable=False),
    Column("uncertainty", JSON),
    Column("evidence", JSON, nullable=False),
    Column("thesis", JSON, nullable=False),
    Column("invalidation", Text),
    Column("plan", JSON),
    Column("model_version", String(64)),
    Column("feature_set_version", String(32)),
    Column("strategy_version", String(32), nullable=False),
    Column("risk_settings_version", String(32)),
    Column("provenance", JSON, nullable=False),
    Column("parent_prediction_id", String(36)),
    Column("content_hash", String(64), nullable=False),
    Column("prev_hash", String(64), nullable=False),
)

prediction_events = Table(
    "prediction_events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("prediction_id", ForeignKey("predictions.id"), nullable=False, index=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("event_type", String(32), nullable=False),
    Column("data_cutoff", UTCDateTime),
    Column("payload", JSON, nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("prev_hash", String(64), nullable=False),
)

alerts = Table(
    "alerts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("alert_class", String(40), nullable=False),
    Column("stage", String(16), nullable=False),  # early_warning | approaching | confirmed | info
    Column("instrument_id", ForeignKey("instruments.id")),
    Column("symbol", String(40)),
    Column("prediction_id", ForeignKey("predictions.id")),
    Column("position_id", Integer),
    Column("title", String(200), nullable=False),
    Column("message", Text, nullable=False),
    Column("data_cutoff", UTCDateTime),
    Column("probability", Float),
    Column("evidence", JSON),
    Column("invalidation", Text),
    Column("dedupe_key", String(200), nullable=False, index=True),
)

alert_outcomes = Table(
    "alert_outcomes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("alert_id", ForeignKey("alerts.id"), nullable=False, index=True),
    Column("recorded_at", UTCDateTime, nullable=False),
    Column("outcome", String(24), nullable=False),  # occurred | not_occurred | expired
    Column("event_time", UTCDateTime),
    Column("detail", JSON),
)

evaluations = Table(
    "evaluations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("prediction_id", ForeignKey("predictions.id"), nullable=False, index=True),
    Column("horizon", String(16), nullable=False),  # 1s | 3s | 5s | 10s | 20s | closure
    Column("evaluated_at", UTCDateTime, nullable=False),
    Column("data_cutoff", UTCDateTime, nullable=False),
    Column("metrics", JSON, nullable=False),
    UniqueConstraint("prediction_id", "horizon", name="uq_eval_prediction_horizon"),
)

lessons = Table(
    "lessons",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("prediction_id", ForeignKey("predictions.id"), nullable=False, index=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("error_cause", String(16), nullable=False),
    Column("payload", JSON, nullable=False),
)

# --- Positions, paper trading, notifications ---------------------------------------------------

positions = Table(
    "positions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("kind", String(12), nullable=False),  # actual (user fill) | paper (simulated)
    Column("instrument_id", ForeignKey("instruments.id"), nullable=False, index=True),
    Column("exchange", String(8), nullable=False),
    Column("symbol", String(40), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("avg_price", Float, nullable=False),
    Column("opened_at", UTCDateTime, nullable=False),
    Column("entry_costs", Float, nullable=False, default=0.0),
    Column("stop", Float),
    Column("target1", Float),
    Column("target2", Float),
    Column("source_prediction_id", ForeignKey("predictions.id")),
    Column("status", String(8), nullable=False),  # open | closed
    Column("closed_at", UTCDateTime),
    Column("exit_price", Float),
    Column("exit_costs", Float),
    Column("notes", Text),
    Column("monitor_state", String(24), nullable=False, default="normal"),
)

paper_fills = Table(
    "paper_fills",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("prediction_id", ForeignKey("predictions.id")),
    Column("position_id", ForeignKey("positions.id")),
    Column("instrument_id", ForeignKey("instruments.id"), nullable=False),
    Column("side", String(4), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("requested_price", Float),
    Column("fill_price", Float),
    Column("fill_ts", UTCDateTime),
    Column("costs", Float),
    Column("status", String(12), nullable=False),  # filled | missed | rejected
    Column("reason", Text),
)

push_subscriptions = Table(
    "push_subscriptions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("endpoint", Text, nullable=False, unique=True),
    Column("keys", JSON, nullable=False),
    Column("user_agent", Text),
    Column("created_at", UTCDateTime, nullable=False),
    Column("active", Boolean, nullable=False, default=True),
)

notification_deliveries = Table(
    "notification_deliveries",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("alert_id", ForeignKey("alerts.id"), nullable=False, index=True),
    Column("channel", String(16), nullable=False),
    Column("subscription_id", ForeignKey("push_subscriptions.id")),
    Column("attempt", Integer, nullable=False),
    Column("status", String(16), nullable=False),  # sent | failed | skipped
    Column("created_at", UTCDateTime, nullable=False),
    Column("error", Text),
)

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("ts", UTCDateTime, nullable=False),
    Column("actor", String(32), nullable=False),
    Column("action", String(64), nullable=False),
    Column("detail", JSON),
)

Index("ix_predictions_created_at", predictions.c.created_at)
Index("ix_alerts_created_at", alerts.c.created_at)

IMMUTABLE_TABLES = (
    "predictions",
    "prediction_events",
    "alerts",
    "alert_outcomes",
    "evaluations",
    "lessons",
    "raw_files",
    "notification_deliveries",
    "paper_fills",
    "audit_log",
)
