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

The store never falls back silently. The local parquet fallback under
`live/state/` exists for the test suite and for local dry runs, and it has to be
asked for by name with `EFB_STORE=local`. Without that request a missing
`EFB_SUPABASE_DB_URL` is an error: on Render the fallback would write the
evening's rows to a disk the next container never sees, the run would still
notify `ok`, the appendix would re-seed from git every night and the dashboard
would read its own empty fallback, which is the healthy-looking failure this
rule exists to prevent. `EFB_STORE=local` is refused outright where `RENDER` is
set, and the first line of the run's notification names the store, so the
wrong store is visible in the message before anything else is read.

Every writer is an upsert on the natural key, so a re-run updates one row
instead of duplicating it.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
# The local fallback lives in its own subdirectory so it cannot collide
# with live/state.py's decision and settings files.
LOCAL_DIR = ROOT / "live" / "state" / "supabase"

DEFAULT_SCHEMA = "efb"

# The explicit request for the local fallback, and the variable Render sets.
LOCAL_MODE_ENV = "EFB_STORE"
LOCAL_MODE_VALUE = "local"
POSTGRES_MODE_VALUE = "postgres"
RENDER_ENV = "RENDER"
URL_ENV = "EFB_SUPABASE_DB_URL"

# The explicit first-run request, and the only two values it accepts. A store is
# seeded exactly once, by a run that says so, and never inferred from what the
# tables happen to hold: the round-trip check writes `run_status` rows of its own
# on a store that has never been seeded.
INIT_STORE_ENV = "EFB_INIT_STORE"
INIT_TRUE = "true"
INIT_FALSE = "false"

# The one-row marker that makes a store count as seeded, and its key. It is its
# own table so that "the store has rows" can never be mistaken for "the store has
# been seeded", and so the marker can be read or wiped deliberately.
SEED_MARKER_TABLE = "store_seed"
SEED_MARKER_KEY = "first_run"


class StoreNotConfigured(RuntimeError):
    """The store cannot be used as configured, so the run has to stop.

    Raised rather than defaulted: a store that quietly writes somewhere else is
    worse than a store that refuses, because the run still reports success.
    """


# Annotated as variable-length: `live/corporate_actions.py` and `live/appendix.py`
# each add their own tables at import, and without this the inferred type would be
# the exact length of this literal and the additions would be a type error.
TABLES: tuple[str, ...] = (
    "proposals",
    "orders",
    "fills",
    "positions",
    "reconciliation",
    "nav",
    "decisions",
    "cron_runs",
    "run_status",
    SEED_MARKER_TABLE,
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
    # one row, keyed by the marker's own name, so the seed is written once and a
    # re-run of the first run replaces it instead of adding a second
    SEED_MARKER_TABLE: ("marker",),
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


def store_mode() -> str:
    """`postgres` or `local`, decided once and never guessed.

    Local is only ever returned for an explicit `EFB_STORE=local` on a machine
    where `RENDER` is not set. Everything else that cannot reach Postgres is an
    error naming what to set, including the contradictory pair of a connection
    string and a request for local, which would otherwise write to whichever the
    code happened to check first.
    """
    url = os.environ.get(URL_ENV, "").strip()
    requested = os.environ.get(LOCAL_MODE_ENV, "").strip().lower()
    if requested and requested not in (LOCAL_MODE_VALUE, POSTGRES_MODE_VALUE):
        raise StoreNotConfigured(
            f"{LOCAL_MODE_ENV}={requested!r} is not a store mode: set it to "
            f"{LOCAL_MODE_VALUE!r} or leave it unset"
        )
    if url and requested == LOCAL_MODE_VALUE:
        raise StoreNotConfigured(
            f"both {URL_ENV} and {LOCAL_MODE_ENV}=local are set, so a write would "
            f"go to whichever is checked first; set one of them"
        )
    if requested == LOCAL_MODE_VALUE:
        if os.environ.get(RENDER_ENV, "").strip():
            raise StoreNotConfigured(
                f"{LOCAL_MODE_ENV}=local is refused where {RENDER_ENV} is set: a "
                f"local write on Render lands on a disk the next container never "
                f"sees, and the run would still report ok"
            )
        return LOCAL_MODE_VALUE
    if not url:
        raise StoreNotConfigured(
            f"{URL_ENV} is not set, so the live series has nowhere to go; set it, "
            f"or set {LOCAL_MODE_ENV}=local for a local run"
        )
    return POSTGRES_MODE_VALUE


def store_label() -> str:
    """How the store is named in a message, and never by raising.

    When the configuration is unusable the label says so, because that is the
    news the owner needs in the first line of the notification.
    """
    try:
        mode = store_mode()
    except StoreNotConfigured as exc:
        return f"ERROR {exc}"
    if mode == LOCAL_MODE_VALUE:
        try:
            where = LOCAL_DIR.relative_to(ROOT)
        except ValueError:  # pragma: no cover - a relocated fallback
            where = LOCAL_DIR
        return f"local parquet ({where})"
    return f"postgres/{_schema()}"


def init_store_flag() -> bool:
    """Whether this run asked to seed the store, and never a guess.

    Unset and `false` are a normal run; `true` is a first run; anything else is
    an error that names the value. A strict parse is the point: a spelling nobody
    meant (`yes`, `1`, a typo) must not be read as permission to seed, and a flag
    left set after the first run has to fail the next evening loudly rather than
    re-seed quietly.
    """
    value = os.environ.get(INIT_STORE_ENV, "").strip().lower()
    if value in ("", INIT_FALSE):
        return False
    if value == INIT_TRUE:
        return True
    raise StoreNotConfigured(
        f"{INIT_STORE_ENV}={value!r} is not a first-run flag: set it to "
        f"{INIT_TRUE!r} for the first run only, or leave it unset"
    )


def json_safe(value: Any) -> Any:
    """A JSON-safe copy of a value: NaN and infinity become null.

    `json.dumps` writes bare `NaN`, which is not valid JSON and which Postgres
    `jsonb` refuses, so a single NaN anywhere in a run's inputs would fail the
    whole `run_status` row. This is recursive, so a NaN nested in a list or a
    dict is caught too.
    """
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    if isinstance(value, (str, bytes)) or value is None:
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):  # pragma: no cover - arrays and the like
        return value
    if isinstance(value, (pd.Timestamp, dt.datetime, dt.date)):
        # Dates and timestamps go over as ISO strings, which is what jsonb holds
        # anyway and what the round-trip check reads back.
        return value.isoformat()
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)


def json_text(value: Any, *, sort_keys: bool = False) -> str:
    """The jsonb-safe JSON string for a value: no NaN, no infinity."""
    return json.dumps(json_safe(value), sort_keys=sort_keys)


def get_connection():
    """A direct Postgres connection. Raises when the store is not configured.

    psycopg is imported lazily so the local fallback and the test suite run
    without a driver installed. The connection string is
    `EFB_SUPABASE_DB_URL`, a `postgresql://` URL to the session pooler (5432) or
    the direct endpoint, never the transaction pooler: psycopg's prepared
    statements and its `prepare_threshold` do not survive a transaction pooler.
    """
    if store_mode() == LOCAL_MODE_VALUE:
        return None
    import psycopg  # type: ignore

    return psycopg.connect(os.environ[URL_ENV].strip())


def is_supabase() -> bool:
    """Whether the live series goes to Postgres. False when it cannot be used."""
    try:
        return store_mode() == POSTGRES_MODE_VALUE
    except StoreNotConfigured:
        return False


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


def _dated(frame: pd.DataFrame) -> pd.DataFrame:
    """Date and timestamp columns as pandas datetimes, whichever store answered.

    Postgres hands back `datetime.date` and `datetime.datetime` objects; the parquet
    fallback hands back pandas timestamps. The same column therefore arrives with two
    types depending on the store, and anything that merges the two raises "Cannot
    compare Timestamp with datetime.date", which is how the second Render run died in
    the appendix on a store whose rows were perfectly good. Converting here, at the
    boundary, is what makes the two modes interchangeable.
    """
    for column in frame.columns:
        values = frame[column]
        # a datetime is a date, so one isinstance covers both
        if values.map(lambda value: isinstance(value, dt.date)).any():
            frame[column] = pd.to_datetime(values)
    return frame


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
        return _dated(pd.DataFrame(data, columns=columns))
    path = _local_path(table)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def upsert_one(table: str, key: str, value: Any, row: dict[str, Any]) -> None:
    """Upsert a single row, removing any existing row with the same key first."""
    frame = select(table)
    frame = frame.loc[~frame[key].astype(str).isin([str(value)])]
    upsert(table, frame.to_dict("records") + [row])


def seed_marker() -> dict[str, Any] | None:
    """The one-row record that this store was seeded, or None.

    This marker is what "seeded" means. A store that holds any rows at all is not
    evidence of a seed, because `scripts/verify_store_roundtrip.py` records its
    result in `run_status` with `job = store_roundtrip` on a store that has never
    been seeded, and the owner runs that check before the first run.
    """
    frame = select(SEED_MARKER_TABLE)
    if frame.empty:
        return None
    return {str(key): value for key, value in frame.iloc[-1].to_dict().items()}


def write_seed_marker(*, seeded_from: str, data_hash: str, written_at: str) -> None:
    """Write the marker that makes a store count as seeded, once.

    It records the close the seed was taken through, the committed data hash it
    was taken from, and when it was written, so a seeded store names its own
    provenance rather than trusting that somebody remembers.
    """
    upsert(
        SEED_MARKER_TABLE,
        [
            {
                "marker": SEED_MARKER_KEY,
                "seeded_from": seeded_from,
                "data_hash": data_hash,
                "written_at": written_at,
            }
        ],
    )
