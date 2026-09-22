"""Sprint E11: the live-series store, Supabase with a local fallback.

Render's filesystem is ephemeral, so the live series (proposals, orders,
fills, positions, reconciliation, NAV, decisions and cron runs) lives in
Supabase, keyed by date. Research artifacts stay in git and the evidence
snapshot. Credentials come from the environment
(`EFB_SUPABASE_URL`, `EFB_SUPABASE_SECRET_KEY`) and are never committed.

When Supabase is not configured, the store falls back to parquet files
under `live/state/`, so local dry runs and the test suite keep working
without a database. Every writer is an upsert on the natural key, so a
re-run updates one row instead of duplicating it.
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

# Table names in Supabase carry the efb_ prefix so EFB's live series
# cannot collide with credit-trading-lab's tables in the same project.
PREFIX = "efb_"
TABLES = (
    "proposals",
    "orders",
    "fills",
    "positions",
    "reconciliation",
    "nav",
    "decisions",
    "cron_runs",
)


def _local_path(table: str) -> Path:
    return LOCAL_DIR / f"{table}.parquet"


def get_client():
    """A Supabase client, or None when not configured or not installed."""
    url = os.environ.get("EFB_SUPABASE_URL", "")
    key = os.environ.get("EFB_SUPABASE_SECRET_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        return None
    return create_client(url, key)


def is_supabase() -> bool:
    """Whether the live series is persisted in Supabase rather than locally."""
    return get_client() is not None


def upsert(table: str, rows: list[dict[str, Any]]) -> None:
    """Upsert one or more rows into a live-series table.

    The Supabase path upserts on the table's primary key; the local path
    concatenates and drops duplicates on the same key, keeping the last.
    """
    if table not in TABLES:
        raise ValueError(f"unknown live-series table {table!r}")
    client = get_client()
    if client is not None:
        result = client.table(f"{PREFIX}{table}").upsert(rows).execute()
        if getattr(result, "error", None):
            raise RuntimeError(f"Supabase upsert {table}: {result.error}")
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
    client = get_client()
    if client is not None:
        result = client.table(f"{PREFIX}{table}").select("*").execute()
        if getattr(result, "error", None):
            raise RuntimeError(f"Supabase select {table}: {result.error}")
        data = getattr(result, "data", None) or []
        return pd.DataFrame(data)
    path = _local_path(table)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def upsert_one(table: str, key: str, value: Any, row: dict[str, Any]) -> None:
    """Upsert a single row, removing any existing row with the same key first."""
    frame = select(table)
    frame = frame.loc[~frame[key].astype(str).isin([str(value)])]
    upsert(table, frame.to_dict("records") + [row])
