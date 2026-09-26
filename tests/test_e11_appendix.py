"""Sprint E11, E11-F15: the appendix round trip and its idempotence.

The machinery is driven on small synthetic artifacts so the properties are
exact, then the round trip is run on the real artifacts and the block hashes
are printed, which is the evidence the task asks for.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from live import appendix, store

CUTOFF = appendix.SEED_CUTOFF
PRE = [CUTOFF - pd.Timedelta(days=3), CUTOFF - pd.Timedelta(days=2)]
POST = [CUTOFF + pd.Timedelta(days=1), CUTOFF + pd.Timedelta(days=4)]
TICKERS = ["AAA", "BBB", "CCC"]


def _write_inputs(root: Path) -> None:
    """A small artifact per input, with pre-cutoff and post-cutoff sessions."""
    (root / "raw" / "spy_holdings").mkdir(parents=True, exist_ok=True)
    (root / "processed").mkdir(parents=True, exist_ok=True)
    (root / "models" / "XS-v1").mkdir(parents=True, exist_ok=True)

    index = pd.MultiIndex.from_product([PRE + POST, TICKERS], names=["date", "ticker"])
    prices = pd.DataFrame(
        {
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "adj_close": 1.5,
            "volume": 100.0,
            "dividend": 0.0,
            "split_factor": 1.0,
        },
        index=index,
    )
    prices.to_parquet(root / "raw" / "prices.parquet")

    descriptors = pd.DataFrame(
        [
            {
                "date": date,
                "ticker": ticker,
                "descriptor": name,
                "value_raw": 1.0,
                "value_winsor": 1.0,
                "value_z": 0.5,
                "value_z_orth": 0.5,
                "n_obs": 3.0,
                "look_ahead": False,
            }
            for date in PRE + POST
            for ticker in TICKERS
            for name in ("beta", "size")
        ]
    )
    descriptors.to_parquet(root / "models" / "XS-v1" / "descriptors.parquet")

    factor_returns = pd.DataFrame(
        [
            {
                "date": date,
                "factor": factor,
                "f": 0.01,
                "f_pre_identification": 0.01,
                "estimation": "full",
                "is_sector": False,
                "is_reference_sector": False,
                "n_names": 3.0,
            }
            for date in PRE + POST
            for factor in ("market", "beta")
        ]
    )
    factor_returns.to_parquet(root / "models" / "XS-v1" / "factor_returns.parquet")

    specific_returns = pd.DataFrame(
        [
            {"date": date, "ticker": ticker, "specific_return": 0.02}
            for date in PRE + POST
            for ticker in TICKERS
        ]
    )
    specific_returns.to_parquet(root / "models" / "XS-v1" / "specific_returns.parquet")

    specific_var = pd.DataFrame(
        [
            {
                "date": date,
                "ticker": ticker,
                "specific_var_raw": 0.04,
                "specific_var": 0.04,
                "bucket": "b1",
                "bucket_mean": 0.04,
                "n_obs": 3.0,
            }
            for date in PRE + POST
            for ticker in TICKERS
        ]
    )
    specific_var.to_parquet(root / "models" / "XS-v1" / "specific_var.parquet")

    pd.DataFrame(
        [[0.04, 0.01], [0.01, 0.09]],
        index=["market", "beta"],
        columns=["market", "beta"],
    ).to_parquet(root / "models" / "XS-v1" / "factor_cov.parquet")

    shares = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "date": date,
                "shares": 1_000.0,
                "source": "yfinance",
                "fetched_at": "2026-09-20T00:00:00Z",
                "status": "ok",
            }
            for date in PRE + POST
            for ticker in TICKERS
        ]
    )
    shares.to_parquet(root / "raw" / "shares_history.parquet")

    sectors = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "gics_sector": "Industrials",
                "gics_sub_industry": "Machinery",
                "source": "wikipedia",
                "as_of": date,
            }
            for date in PRE + POST
            for ticker in TICKERS
        ]
    )
    sectors.to_parquet(root / "processed" / "sectors.parquet")

    for date in PRE + POST:
        frame = pd.DataFrame(
            {
                "ticker": TICKERS,
                "name": ["Alpha", "Beta", "Gamma"],
                "identifier": ["C1", "C2", "C3"],
                "sedol": ["S1", "S2", "S3"],
                "weight": [0.4, 0.35, 0.25],
                "sector": ["Industrials"] * 3,
                # The underscore spellings, which is what the archives on disk
                # carry and what `efb/spy.py`'s parser writes from the vendor's
                # header. The spaced vendor spellings are the legacy case, and
                # `column_map` exists to read those.
                "shares_held": [10.0, 20.0, 30.0],
                "local_currency": ["USD"] * 3,
                "as_of": [str(date.date())] * 3,
            }
        )
        stamp = pd.Timestamp(date).strftime("%Y-%m-%d")
        frame.to_parquet(
            root / "raw" / "spy_holdings" / f"spy_holdings_{stamp}.parquet", index=False
        )


def _hash(root: Path, spec: appendix.InputSpec) -> str:
    """A hash of one artifact as the appendix machinery reads it."""
    rows = appendix.artifact_rows(spec, root)
    serialized = rows.sort_values(list(rows.columns)).to_csv(index=False).encode()
    return hashlib.sha256(serialized).hexdigest()


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Synthetic artifacts, an empty appendix, and hydration run once."""
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "state")
    root = tmp_path / "data"
    _write_inputs(root)
    appendix.hydrate(root)
    return root


def test_hydration_reproduces_every_input_it_seeded(
    seeded: Path, tmp_path: Path
) -> None:
    """Seed plus appendix equals the artifact the appendix was seeded from."""
    reference = tmp_path / "reference"
    _write_inputs(reference)
    for spec in appendix.SPECS:
        if spec.name == "factor_cov":
            continue  # a snapshot with no date; covered by the session stamping
        assert _hash(seeded, spec) == _hash(reference, spec), spec.name


def test_hydration_writes_the_universe_with_the_names_the_loop_fetches(
    seeded: Path,
) -> None:
    """One directory, one convention, so the reader cannot see two spellings."""
    import pyarrow.parquet as pq  # noqa: PLC0415 - only this test reads a schema

    files = sorted((seeded / "raw" / "spy_holdings").glob("*.parquet"))
    assert files, "hydration wrote no archive"
    for path in files:
        names = set(pq.read_schema(path).names)
        assert {"shares_held", "local_currency"} <= names, path.name
        assert not {"shares held", "local currency"} & names, path.name


def test_a_legacy_spelled_archive_does_not_duplicate_the_universe_columns(
    tmp_path: Path,
) -> None:
    """A mixed directory must not lose a column the way mapping after the concat did.

    Both archives are written by hand rather than by hydration, because the point
    is a tree that holds two conventions at once: the loop fetches a session with
    the parser's underscore names, and an older hand-made file carries the
    vendor's spaced ones. With the map applied once, after the concatenation, the
    two became one column name twice and the store write kept only the later one,
    so every session from the other file lost `shares_held` and `local_currency`.
    """
    spec = appendix.SPEC_BY_NAME["universe"]
    archive = tmp_path / "data" / "raw" / "spy_holdings"
    archive.mkdir(parents=True)
    columns = ["ticker", "name", "identifier", "sedol", "weight", "sector"]
    values = [
        ["AAA", "Alpha", "C1", "S1", 0.4, "Industrials"],
        ["BBB", "Beta", "C2", "S2", 0.6, "Industrials"],
    ]
    fetched = pd.DataFrame(values, columns=columns)
    fetched["shares_held"] = [10.0, 20.0]
    fetched["local_currency"] = ["USD", "USD"]
    fetched["as_of"] = ["2026-09-21"] * 2
    fetched.to_parquet(archive / "spy_holdings_2026-09-21.parquet", index=False)
    legacy = fetched.rename(
        columns={"shares_held": "shares held", "local_currency": "local currency"}
    )
    legacy["as_of"] = ["2026-09-18"] * 2
    legacy.to_parquet(archive / "spy_holdings_2026-09-18.parquet", index=False)

    rows = appendix.artifact_rows(spec, tmp_path / "data")

    assert not rows.columns.duplicated().any(), list(rows.columns)
    # and the values survive for both sessions, not only the one read last
    assert len(rows) == 4
    assert rows["shares_held"].notna().all()
    assert rows["local_currency"].notna().all()
    assert sorted(rows["shares_held"]) == [10.0, 10.0, 20.0, 20.0]


def test_the_appendix_holds_only_sessions_after_the_cutoff(seeded: Path) -> None:
    for spec in appendix.SPECS:
        rows = appendix.read_appendix(spec)
        if spec.name in ("factor_cov",):
            continue
        if rows.empty:
            assert spec.name in ("factor_cov",)
            continue
        assert (pd.to_datetime(rows[appendix.DATE_COLUMN]) > CUTOFF).all(), spec.name


def test_an_append_is_idempotent(seeded: Path) -> None:
    first = appendix.persist_new_sessions(seeded)
    counts = {spec.name: len(appendix.read_appendix(spec)) for spec in appendix.SPECS}
    second = appendix.persist_new_sessions(seeded)
    after = {spec.name: len(appendix.read_appendix(spec)) for spec in appendix.SPECS}
    assert first == second
    assert counts == after
    # one row per key, on the tables that have several rows per session
    descriptors = appendix.read_appendix(appendix.SPEC_BY_NAME["descriptors"])
    keys = [appendix.DATE_COLUMN, "ticker", "descriptor"]
    assert not descriptors.duplicated(subset=keys).any()
    prices = appendix.read_appendix(appendix.SPEC_BY_NAME["prices"])
    assert not prices.duplicated(subset=[appendix.DATE_COLUMN, "ticker"]).any()


def test_the_appendix_identity_names_what_was_read(seeded: Path) -> None:
    appendix.persist_new_sessions(seeded)
    identity = appendix.appendix_manifest()
    assert set(identity) == set(appendix.INPUT_NAMES)
    prices = identity["prices"]
    assert prices["rows"] > 0
    assert prices["max_date"] == str(POST[-1].date())
    assert len(prices["sha256"]) == 64


@pytest.mark.slow
def test_the_proposal_names_the_appendix_it_was_priced_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A proposal never priced from an appendix it cannot name (E11-F15).

    The empty-appendix half of this test makes its own empty directory rather than
    reading the ambient one: a full run leaves rows in the real fallback, and the
    assertion then depends on which tests ran before it.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "state")
    from live import evening_job

    identity = appendix.appendix_manifest()
    assert set(identity) == set(appendix.INPUT_NAMES)
    manifest = evening_job.build_proposal(store=False, appendix=identity)
    assert manifest["appendix"] == identity
    # with no database configured the fallback is empty, and the manifest still
    # carries the field, so the shape does not depend on the store
    assert manifest["appendix"]["prices"]["rows"] == 0
    assert manifest["appendix"]["prices"]["max_date"] is None


@pytest.mark.slow
def test_the_real_artifacts_round_trip_and_report_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The evidence run: seed plus appendix equals the committed artifacts."""
    reference = appendix.DATA_ROOT
    root = tmp_path / "data"
    import shutil

    for spec in appendix.SPECS:
        source = reference / spec.path
        target = root / spec.path
        if spec.name == "universe":
            target.mkdir(parents=True, exist_ok=True)
            for file in sorted(source.glob("*.parquet")):
                shutil.copy2(file, target / file.name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # Through monkeypatch, never by assignment: this test is marked slow, so the
    # fast selection never runs it, and a direct assignment here leaked the
    # temporary directory into every later test in the same process. The full
    # suite caught it; the guard below keeps it caught.
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "state")
    appendix.hydrate(root)
    for spec in appendix.SPECS:
        if spec.name == "factor_cov":
            continue
        before = _hash(reference, spec)
        after = _hash(root, spec)
        print(f"{spec.name:18s} {before} {after}")
        assert before == after, spec.name
