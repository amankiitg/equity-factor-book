"""Sprint E11: the live-series store, direct Postgres with a local fallback.

Render's filesystem is ephemeral, so the live series (proposals, orders,
fills, positions, reconciliation, NAV, decisions and cron runs) lives in
Postgres under schema `efb`, keyed by date. The connection is direct
Postgres over `EFB_SUPABASE_DB_URL`, never PostgREST: PostgREST serves only
schemas added to "Exposed schemas" in the project API settings, which is a
dashboard change on the project shared with credit-trading-lab. Every SQL
statement is schema-qualified (`"efb"."table"`); nothing targets `public` or
an unqualified name. The schema name comes from `EFB_DB_SCHEMA`, default
`efb`.

When `EFB_SUPABASE_DB_URL` is not set, the store falls back to parquet files
under `live/state/`, so local dry runs and the test suite keep working
without a database. Every writer is an upsert on the natural key, so a re-run
updates one row instead of duplicating it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
# The local fallback lives in its own subdirectory so it cannot collide
# with live/state.py's decision and settings files.
LOCAL_DIR = ROOT / "live" / "state" / "supabase"

DEFAULT_SCHEMA = "efb"
TABLES = (
    "proposals",
    "orders",
    "fills",
    "positions",
    "reconciliation",
    "nav",
    "decisions",
    "cron_runs",
    "run_status",
)

# The natural key of each live-series table, used by the upsert's
# ON CONFLICT clause. Rows are keyed by date, and by ticker (and order id)
# where a day has many rows.
TABLE_KEYS: dict[str, tuple[str, ...]] = {
    "proposals": ("trade_date",),
    "orders": ("trade_date", "ticker"),
    "fills": ("trade_date", "ticker", "order_id"),
    "positions": ("trade_date", "ticker"),
    "reconciliation": ("trade_date",),
    "nav": ("trade_date",),
    "decisions": ("trade_date",),
    "cron_runs": ("run_date", "job"),
    # keyed by the target close rather than the day the job ran, so a re-fire
    # for the same session replaces its row and a missing session stays missing
    "run_status": ("target_close", "job"),
}


def _local_path(table: str) -> Path:
    return LOCAL_DIR / f"{table}.parquet"


def _schema() -> str:
    """The schema every statement targets, from the environment."""
    value = os.environ.get("EFB_DB_SCHEMA", "").strip()
    return value or DEFAULT_SCHEMA


def _qualified(table: str) -> str:
    """The schema-qualified table name every statement must use."""
    return f'"{_schema()}"."{table}"'


def get_connection():
    """A direct Postgres connection, or None when not configured.

    psycopg is imported lazily so the local fallback and the test suite run
    without a driver installed. The connection string is
    `EFB_SUPABASE_DB_URL`, a `postgresql://` URL to the direct (5432) or
    transaction-pooled (6543) endpoint.
    """
    url = os.environ.get("EFB_SUPABASE_DB_URL", "")
    if not url:
        return None
    import psycopg  # type: ignore

    return psycopg.connect(url)


def is_supabase() -> bool:
    """Whether the live series is persisted in Postgres rather than locally."""
    return bool(os.environ.get("EFB_SUPABASE_DB_URL", ""))


def _upsert_sql(table: str, columns: list[str]) -> str:
    """The schema-qualified upsert statement for one table's columns."""
    keys = TABLE_KEYS[table]
    column_sql = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    key_sql = ", ".join(f'"{k}"' for k in keys)
    set_sql = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in columns if c not in keys)
    return (
        f"INSERT INTO {_qualified(table)} ({column_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT ({key_sql}) DO UPDATE SET {set_sql}"
    )


def upsert(table: str, rows: list[dict[str, Any]]) -> None:
    """Upsert one or more rows into a live-series table.

    The Postgres path upserts on the table's primary key; the local path
    concatenates and drops duplicates on the same key, keeping the last.
    """
    if table not in TABLES:
        raise ValueError(f"unknown live-series table {table!r}")
    connection = get_connection()
    if connection is not None:
        if not rows:
            return
        columns = sorted(rows[0].keys())
        statement = _upsert_sql(table, columns)
        values = [tuple(row.get(c) for c in columns) for row in rows]
        with connection.cursor() as cursor:
            cursor.executemany(statement, values)
        connection.commit()
        return
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    path = _local_path(table)
    frame = pd.read_parquet(path) if path.exists() else pd.DataFrame(rows)
    if len(rows):
        incoming = pd.DataFrame(rows)
        key = incoming.columns[0]
        existing = frame.loc[~frame[key].isin(incoming[key])] if len(frame) else frame
        frame = pd.concat([existing, incoming], ignore_index=True)
    frame.to_parquet(path, index=False)


def select(table: str) -> pd.DataFrame:
    """Every row of a live-series table, empty frame when there are none."""
    if table not in TABLES:
        raise ValueError(f"unknown live-series table {table!r}")
    connection = get_connection()
    if connection is not None:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {_qualified(table)} ORDER BY 1")
            columns = [description.name for description in cursor.description]
            data = cursor.fetchall()
        return pd.DataFrame(data, columns=columns)
    path = _local_path(table)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def upsert_one(table: str, key: str, value: Any, row: dict[str, Any]) -> None:
    """Upsert a single row, removing any existing row with the same key first."""
    frame = select(table)
    frame = frame.loc[~frame[key].astype(str).isin([str(value)])]
    upsert(table, frame.to_dict("records") + [row])
