"""Sprint E11, E11-F15: the model inputs on Render, as a git seed plus an appendix.

Render's filesystem is ephemeral and the model inputs extend by appending one
session, so a run that starts from the committed artifacts every evening either
re-extends from the deploy date or prices from stale inputs. The design the
owner chose:

- the git artifacts are the seed, and the rows dated on or before
  `SEED_CUTOFF` (2026-09-03) stay byte-identical in git;
- Postgres, schema `efb`, holds the appendix: the rows after that cutoff, one
  session per run, table per input, keyed so a re-run upserts;
- a run hydrates the local artifacts as seed plus appendix, extends by the new
  session with the existing `live.extend` code, and writes only the new session
  back.

`hydrate` seeds the appendix from the local artifact the first time it finds it
empty, so the first run on a fresh database takes the committed post-cutoff
rows into Postgres rather than truncating them, and after that the appendix is
authoritative for every date after the cutoff.

The rolling estimators need history before the cutoff; the seed supplies it, so
the appendix holds nothing but the post-cutoff sessions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from live import store

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
SEED_CUTOFF = pd.Timestamp("2026-09-03")
DATE_COLUMN = "trade_date"


@dataclass(frozen=True)
class InputSpec:
    """One model input: its artifact, its appendix table and its key.

    `date_field` is the artifact's own date column, or None for the factor
    covariance artifact, which is a matrix with no date and rolls forward as a
    snapshot. `value_columns` are the columns carried into the appendix, in the
    artifact's order, and `column_map` renames any artifact column whose name is
    not a plain SQL identifier.
    """

    name: str
    table: str
    path: str
    date_field: str | None
    value_columns: tuple[str, ...]
    key: tuple[str, ...]
    index_key: str | None = None  # "ticker" when the date lives in a MultiIndex
    column_map: dict[str, str] | None = None


SPECS: tuple[InputSpec, ...] = (
    InputSpec(
        name="prices",
        table="e11_prices",
        path="raw/prices.parquet",
        date_field=None,
        index_key="ticker",
        key=(DATE_COLUMN, "ticker"),
        value_columns=(
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "dividend",
            "split_factor",
        ),
    ),
    InputSpec(
        name="descriptors",
        table="e11_descriptors",
        path="models/XS-v1/descriptors.parquet",
        date_field="date",
        key=(DATE_COLUMN, "ticker", "descriptor"),
        value_columns=(
            "descriptor",
            "value_raw",
            "value_winsor",
            "value_z",
            "value_z_orth",
            "n_obs",
            "look_ahead",
        ),
    ),
    InputSpec(
        name="factor_returns",
        table="e11_factor_returns",
        path="models/XS-v1/factor_returns.parquet",
        date_field="date",
        key=(DATE_COLUMN, "factor"),
        value_columns=(
            "factor",
            "f",
            "f_pre_identification",
            "estimation",
            "is_sector",
            "is_reference_sector",
            "n_names",
        ),
    ),
    InputSpec(
        name="specific_returns",
        table="e11_specific_returns",
        path="models/XS-v1/specific_returns.parquet",
        date_field="date",
        key=(DATE_COLUMN, "ticker"),
        value_columns=("specific_return",),
    ),
    InputSpec(
        name="specific_var",
        table="e11_specific_var",
        path="models/XS-v1/specific_var.parquet",
        date_field="date",
        key=(DATE_COLUMN, "ticker"),
        value_columns=(
            "specific_var_raw",
            "specific_var",
            "bucket",
            "bucket_mean",
            "n_obs",
        ),
    ),
    InputSpec(
        name="factor_cov",
        table="e11_factor_cov",
        path="models/XS-v1/factor_cov.parquet",
        date_field=None,
        key=(DATE_COLUMN, "factor", "with_factor"),
        value_columns=("covariance",),
    ),
    InputSpec(
        name="shares",
        table="e11_shares",
        path="raw/shares_history.parquet",
        date_field="date",
        key=(DATE_COLUMN, "ticker"),
        value_columns=("shares", "source", "fetched_at", "status"),
    ),
    InputSpec(
        name="sectors",
        table="e11_sectors",
        path="processed/sectors.parquet",
        date_field="as_of",
        key=(DATE_COLUMN, "ticker"),
        value_columns=("gics_sector", "gics_sub_industry", "source"),
    ),
    InputSpec(
        name="universe",
        table="e11_universe",
        path="raw/spy_holdings",
        date_field="as_of",
        key=(DATE_COLUMN, "ticker"),
        value_columns=(
            "name",
            "identifier",
            "sedol",
            "weight",
            "sector",
            "shares_held",
            "local_currency",
        ),
        column_map={"shares held": "shares_held", "local currency": "local_currency"},
    ),
)
SPEC_BY_NAME = {spec.name: spec for spec in SPECS}
TABLE_BY_NAME = {spec.name: spec.table for spec in SPECS}
INPUT_NAMES = tuple(spec.name for spec in SPECS)


def register_tables() -> None:
    """Put the appendix tables and their keys into the store's registry.

    Keyed by session and by the name within the session, so a re-run of the
    same session upserts one row per key instead of duplicating it.
    """
    for spec in SPECS:
        if spec.table not in store.TABLES:
            store.TABLES = store.TABLES + (spec.table,)
        store.TABLE_KEYS[spec.table] = spec.key


register_tables()


def _universe_files(spec: InputSpec, root: Path) -> list[Path]:
    return sorted((root / spec.path).glob("spy_holdings_*.parquet"))


def artifact_rows(spec: InputSpec, root: Path, cutoff: pd.Timestamp | None = None):
    """The input's appendix-shaped rows, optionally only those after a cutoff.

    Appendix shape is one row per key with a `trade_date` column, which is what
    the Postgres tables carry: the artifact's own date column is renamed, a
    MultiIndex is flattened, and the factor covariance matrix is unpivoted.
    """
    path = root / spec.path
    if spec.name == "universe":
        frames = []
        for file in _universe_files(spec, root):
            frame = pd.read_parquet(file)
            frame[DATE_COLUMN] = pd.to_datetime(frame["as_of"])
            frames.append(frame)
        long = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    elif spec.name == "factor_cov":
        long = factor_cov_rows(pd.read_parquet(path))
    elif spec.index_key:
        frame = pd.read_parquet(path).reset_index()
        long = frame.rename(columns={"date": DATE_COLUMN})
    else:
        frame = pd.read_parquet(path)
        long = frame.rename(columns={spec.date_field: DATE_COLUMN})
    if long.empty:
        return long
    long[DATE_COLUMN] = pd.to_datetime(long[DATE_COLUMN])
    if spec.column_map:
        long = long.rename(columns=spec.column_map)
    columns = list(dict.fromkeys([*spec.key, *spec.value_columns]))
    long = long.loc[:, _present(long, columns)]
    if cutoff is not None:
        long = long.loc[long[DATE_COLUMN] > cutoff]
    return long.reset_index(drop=True)


def _present(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if column in frame.columns]


def factor_cov_rows(
    matrix: pd.DataFrame, as_of: pd.Timestamp | None = None
) -> pd.DataFrame:
    """Unpivot the covariance matrix into one row per factor pair.

    The artifact is a single snapshot with no date, so its session is the close
    the run priced from; the caller passes it, and hydration drops rows whose
    session is not in the appendix.
    """
    stamp = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp("1970-01-01")
    rows: list[dict[str, Any]] = []
    for factor in matrix.index:
        for with_factor in matrix.columns:
            rows.append(
                {
                    DATE_COLUMN: stamp,
                    "factor": str(factor),
                    "with_factor": str(with_factor),
                    "covariance": float(matrix.loc[factor, with_factor]),
                }
            )
    return pd.DataFrame(rows)


def factor_cov_matrix(rows: pd.DataFrame) -> pd.DataFrame:
    """The latest snapshot's matrix, rebuilt from its rows."""
    if rows.empty:
        return pd.DataFrame()
    latest = pd.to_datetime(rows[DATE_COLUMN]).max()
    block = rows.loc[pd.to_datetime(rows[DATE_COLUMN]) == latest]
    return block.pivot(index="factor", columns="with_factor", values="covariance")


def read_appendix(spec: InputSpec) -> pd.DataFrame:
    """Every appendix row this input holds, empty when it holds none."""
    return store.select(spec.table)


def appendix_identity(spec: InputSpec) -> dict[str, Any]:
    """What the run was priced from: rows, latest session and a hash of them.

    Recorded in the proposal so a book is never priced from an appendix it
    cannot name.
    """
    rows = read_appendix(spec)
    if rows.empty:
        return {"rows": 0, "max_date": None, "sha256": None}
    serialized = rows.sort_values(list(rows.columns)).to_csv(index=False).encode()
    return {
        "rows": int(len(rows)),
        "max_date": str(pd.to_datetime(rows[DATE_COLUMN]).max().date()),
        "sha256": hashlib.sha256(serialized).hexdigest(),
    }


def seed_appendix(spec: InputSpec, root: Path) -> int:
    """Put the local post-cutoff rows into an empty appendix, once.

    The first run on a fresh database would otherwise hydrate from an empty
    appendix and drop the committed post-cutoff rows. Returns the rows written.
    """
    if not read_appendix(spec).empty:
        return 0
    rows = artifact_rows(spec, root, cutoff=SEED_CUTOFF)
    if rows.empty:
        return 0
    store.upsert(spec.table, rows.to_dict("records"))
    return int(len(rows))


def hydrate(root: Path = DATA_ROOT, seed_empty: bool = True) -> dict[str, int]:
    """Rewrite each artifact as seed plus appendix, and report rows written.

    The seed is the artifact's rows on or before the cutoff; the appendix is
    authoritative for the rows after it. This is the function the daily run
    calls on a fresh container, and the test that proves the read equals the
    local artifacts drives it end to end.
    """
    written: dict[str, int] = {}
    for spec in SPECS:
        if seed_empty:
            seed_appendix(spec, root)
        appendix = read_appendix(spec)
        written[spec.name] = _hydrate_one(spec, root, appendix)
    return written


def _hydrate_one(spec: InputSpec, root: Path, appendix: pd.DataFrame) -> int:
    path = root / spec.path
    if spec.name == "universe":
        return _hydrate_universe(spec, root, appendix)
    if spec.name == "factor_cov":
        matrix = factor_cov_matrix(appendix)
        if not matrix.empty:
            matrix.to_parquet(path)
        return int(len(appendix))
    if spec.index_key:
        seed = pd.read_parquet(path).reset_index()
        seed = seed.loc[~(pd.to_datetime(seed["date"]) > SEED_CUTOFF)]
        seed = seed.rename(columns={"date": DATE_COLUMN})
    else:
        seed = pd.read_parquet(path)
        stamp = pd.to_datetime(seed[spec.date_field])
        seed = seed.loc[~(stamp > SEED_CUTOFF)]
        seed = seed.rename(columns={spec.date_field: DATE_COLUMN})
    # The seed rows are not after the cutoff and the appendix rows are after
    # it, so the two sets cannot collide and the seed goes back verbatim. Two
    # things this preserves: the 62,022 duplicated (date, ticker) pairs in the
    # share counts before the cutoff, which are distinct fetches, and the 58
    # share rows with no date at all (empty fetches for delisted names), which
    # cannot live in a date-keyed appendix.
    combined = pd.concat([seed, appendix], ignore_index=True)
    sort_keys = list(spec.key)
    if spec.index_key:
        order = [DATE_COLUMN, spec.index_key]
        out = combined.sort_values(order, kind="stable").set_index(order)
        out.index = out.index.set_names(["date", "ticker"])
    else:
        out = combined.sort_values(sort_keys, kind="stable").rename(
            columns={DATE_COLUMN: spec.date_field}
        )
    out.to_parquet(path)
    return int(len(appendix))


def _hydrate_universe(spec: InputSpec, root: Path, appendix: pd.DataFrame) -> int:
    """Write one dated holdings file per appendix session, idempotently."""
    if appendix.empty:
        return 0
    out_dir = root / spec.path
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions = sorted(pd.to_datetime(appendix[DATE_COLUMN]).unique())
    for session in sessions:
        block = appendix.loc[pd.to_datetime(appendix[DATE_COLUMN]) == session]
        frame = block.rename(columns={DATE_COLUMN: "as_of"}).copy()
        if spec.column_map:
            reverse = {new: old for old, new in spec.column_map.items()}
            frame = frame.rename(columns=reverse)
        frame["as_of"] = str(pd.Timestamp(session).date())
        stamp = pd.Timestamp(session).strftime("%Y-%m-%d")
        frame.to_parquet(out_dir / f"spy_holdings_{stamp}.parquet", index=False)
    return int(len(appendix))


def persist_new_sessions(root: Path = DATA_ROOT) -> dict[str, int]:
    """Write each input's post-cutoff sessions to the appendix.

    Called after the extension, so the appendix holds every session the run
    created. Idempotent: the store upserts on the table's key.
    """
    written: dict[str, int] = {}
    for spec in SPECS:
        rows = artifact_rows(spec, root, cutoff=SEED_CUTOFF)
        if spec.name == "factor_cov":
            rows = _factor_cov_with_session(root, rows)
        if rows.empty:
            written[spec.name] = 0
            continue
        store.upsert(spec.table, rows.to_dict("records"))
        written[spec.name] = int(len(rows))
    return written


def _factor_cov_with_session(root: Path, rows: pd.DataFrame) -> pd.DataFrame:
    """Stamp the covariance snapshot with the latest close the run has."""
    returns_path = root / "processed" / "returns.parquet"
    if not returns_path.exists():
        return rows.iloc[:0]
    frame = pd.read_parquet(returns_path)
    latest = pd.to_datetime(frame.index.get_level_values("date").max())
    if latest <= SEED_CUTOFF:
        return rows.iloc[:0]
    stamped = rows.copy()
    stamped[DATE_COLUMN] = latest
    return stamped


def appendix_manifest() -> dict[str, dict[str, Any]]:
    """Per input, the appendix state the run was priced from."""
    return {spec.name: appendix_identity(spec) for spec in SPECS}


# The close the marker records: the last session the git seed carries. The seed
# is the committed artifacts through this date, so it is what a first run names.
SEED_FROM = SEED_CUTOFF


class StoreNotSeeded(RuntimeError):
    """The store holds no seed marker, so this run may not write to it."""


class StoreAlreadySeeded(RuntimeError):
    """The first-run flag is set on a store that is already seeded."""


class StoreAppendixLost(RuntimeError):
    """The marker says seeded, but the appendix holds no rows at all."""


def data_hash(root: Path = DATA_ROOT) -> str | None:
    """The committed data hash, which is the seed's own version string."""
    path = root / "VERSION.json"
    if not path.exists():
        return None
    try:
        return str(json.loads(path.read_text())["data_hash"])
    except (KeyError, ValueError):
        return None


def is_empty() -> bool:
    """Whether the appendix holds no rows at all, in any of its inputs.

    Every input rather than any: `e11_factor_cov` is legitimately empty after a
    seed, because the covariance artifact is a dateless snapshot that only gets a
    session once a run stamps it, so an any-table test would refuse a store that
    is perfectly fine.
    """
    return all(read_appendix(spec).empty for spec in SPECS)


def open_store(root: Path = DATA_ROOT, now: datetime | None = None) -> bool:
    """Decide that this run may use the store, and seed it exactly once.

    `EFB_INIT_STORE` is parsed strictly and the marker is what "seeded" means, so
    the four states are told apart rather than guessed at:

        1. no marker, flag not `true`  -> refuse: the store was never seeded
        2. no marker, flag `true`      -> seed from git, write the marker
        3. marker, flag `true`         -> refuse: the flag was left set
        4. marker, appendix empty      -> refuse: data was lost after the seed

    Case 4 is tested before case 3, so a store whose appendix was wiped is never
    re-seeded, whatever the flag says. Only case 2 has a seeding path and every
    other case raises before `hydrate` is called with `seed_empty=True`, which is
    what makes "never re-seeded automatically" structural rather than a promise.

    Returns whether this run seeded the store, which the run records as `init`
    and states in its message. The rule applies to Postgres and to the local
    fallback alike, because a store is a store wherever it lives.
    """
    first_run = store.init_store_flag()
    marker = store.seed_marker()
    if marker is not None:
        if is_empty():
            raise StoreAppendixLost(
                f"the store is seeded through {SEED_FROM.date()} but the appendix "
                "holds no rows at all: data was lost after the seed, and it is "
                "never re-seeded automatically; restore the appendix, or wipe "
                f"the {store.SEED_MARKER_TABLE} marker deliberately"
            )
        if first_run:
            raise StoreAlreadySeeded(
                f"store already seeded: remove {store.INIT_STORE_ENV}"
            )
        hydrate(root, seed_empty=False)
        return False
    if not first_run:
        raise StoreNotSeeded(
            f"store not seeded: set {store.INIT_STORE_ENV}=true for the first run "
            "only"
        )
    hydrate(root, seed_empty=True)
    store.write_seed_marker(
        seeded_from=SEED_FROM.date().isoformat(),
        data_hash=data_hash(root) or "",
        written_at=(now or datetime.now(UTC)).isoformat(),
    )
    return True
