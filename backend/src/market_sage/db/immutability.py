"""DDL that makes ledger tables append-only at the database level."""

from __future__ import annotations

from sqlalchemy import Connection, text


def install_immutability_triggers(conn: Connection, tables: tuple[str, ...]) -> None:
    dialect = conn.dialect.name
    if dialect == "postgresql":
        conn.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION market_sage_reject_mutation() RETURNS trigger AS $$
                BEGIN
                  RAISE EXCEPTION 'MARKET SAGE: table % is append-only (% rejected)', TG_TABLE_NAME, TG_OP;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
        )
        for t in tables:
            conn.execute(
                text(
                    f"CREATE TRIGGER {t}_append_only BEFORE UPDATE OR DELETE ON {t} "
                    "FOR EACH ROW EXECUTE FUNCTION market_sage_reject_mutation()"
                )
            )
            conn.execute(
                text(
                    f"CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {t} "
                    "FOR EACH STATEMENT EXECUTE FUNCTION market_sage_reject_mutation()"
                )
            )
    elif dialect == "sqlite":
        for t in tables:
            for op in ("UPDATE", "DELETE"):
                conn.execute(
                    text(
                        f"CREATE TRIGGER {t}_no_{op.lower()} BEFORE {op} ON {t} BEGIN "
                        f"SELECT RAISE(ABORT, 'MARKET SAGE: table {t} is append-only ({op} rejected)'); END"
                    )
                )
    else:  # pragma: no cover
        raise RuntimeError(f"unsupported dialect {dialect}")


def drop_immutability_triggers(conn: Connection, tables: tuple[str, ...]) -> None:
    dialect = conn.dialect.name
    for t in tables:
        if dialect == "postgresql":
            conn.execute(text(f"DROP TRIGGER IF EXISTS {t}_append_only ON {t}"))
            conn.execute(text(f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}"))
        else:
            conn.execute(text(f"DROP TRIGGER IF EXISTS {t}_no_update"))
            conn.execute(text(f"DROP TRIGGER IF EXISTS {t}_no_delete"))
