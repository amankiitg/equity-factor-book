"""Sprint E12 item 5: the evening's attribution step, and that it cannot block a run.

The step reads the store's own `positions` table and the run tree's model
artifacts, so a live day and a seed day are attributed by one implementation. The
tests here drive it against the local parquet store and the repository's real
artifacts, because the thing worth pinning is the wiring: which days it picks up,
that it does not redo a day it has done, and that a failure in it is reported
rather than raised into the trading run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from live import attribution_job, store

ROOT = Path(__file__).resolve().parents[1]
# The newest session the repository's artifacts price, and the one before it.
BOOK_DAY = "2026-09-18"
SESSION = "2026-09-21"


@pytest.fixture()
def local_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    monkeypatch.setenv("EFB_STORE", "local")
    return tmp_path


def _position_row(trade_date: str, ticker: str, weight: float) -> dict[str, object]:
    return {
        "trade_date": trade_date,
        "ticker": ticker,
        "weight": weight,
        "signed_notional": weight * 1_000_000.0,
        "side": "long" if weight >= 0 else "short",
        "z": 0.5 * (1 if weight >= 0 else -1),
        "alpha": 1e-5 * (1 if weight >= 0 else -1),
        "rank": 1,
        "idio_vol": 0.02,
        "previous_weight": 0.0,
        "trade": "new position",
        "reason": "new position",
    }


def test_a_stored_book_with_no_row_yet_is_attributed_and_stored(
    local_store: Path,
) -> None:
    """One tested session: the store's own book, through the real artifacts."""
    store.upsert(
        "positions",
        [_position_row(BOOK_DAY, "AAPL", 0.5), _position_row(BOOK_DAY, "MSFT", -0.5)],
    )
    report = attribution_job.run(ROOT / "data")

    assert report["n_stored"] == 1, report
    assert report["sessions"] == [SESSION]
    stored = store.select("attribution")
    assert list(stored["trade_date"].astype(str).str.slice(0, 10)) == [SESSION]
    row = stored.iloc[0]
    assert row["n_names"] == 2
    assert abs(row["gross"] - 1.0) < 1e-9
    # The three components are the total: this is the identity, on a live-style
    # book made of two names the model prices.
    assert abs(row["pnl_total"] - (row["pnl_factor"] + row["pnl_idio"])) < 1e-12
    assert abs(row["identity_residual"]) < 1e-10


def test_the_identity_closes_on_the_stored_row(local_store: Path) -> None:
    """The row is checked in the store, not only in the frame that made it."""
    store.upsert(
        "positions",
        [_position_row(BOOK_DAY, "AAPL", 0.6), _position_row(BOOK_DAY, "MSFT", -0.4)],
    )
    attribution_job.run(ROOT / "data")
    stored = store.select("attribution").iloc[0]
    split = json.loads(stored["pnl_factor_json"])
    parts = sum(float(value) for value in split.values())
    assert abs(parts - float(stored["pnl_factor"])) < 1e-12
    total = float(stored["pnl_factor"]) + float(stored["pnl_idio"])
    assert abs(float(stored["pnl_total"]) - (total + float(stored["pnl_cost"]))) < 1e-12
    # The four per-factor maps went in as JSON text, and jsonb would have refused
    # the row had any of them carried a NaN.
    assert "NaN" not in str(stored["exposure_json"])
    assert len(json.loads(stored["book_exposure_json"])) >= 10
    assert len(json.loads(stored["pnl_timing_json"])) >= 10


def test_a_day_already_attributed_is_not_done_twice(local_store: Path) -> None:
    """A re-run of the evening is a no-op for the days it has already written."""
    store.upsert(
        "positions",
        [_position_row(BOOK_DAY, "AAPL", 0.5), _position_row(BOOK_DAY, "MSFT", -0.5)],
    )
    first = attribution_job.run(ROOT / "data")
    second = attribution_job.run(ROOT / "data")

    assert first["n_stored"] == 1
    assert second["n_stored"] == 0
    assert second["n_done"] == 1
    assert len(store.select("attribution")) == 1, "the day was written twice"


def test_the_day_carries_the_stored_cost_and_forecast(local_store: Path) -> None:
    """Cost and forecast come from the store's own reconciliation row."""
    store.upsert(
        "positions",
        [_position_row(BOOK_DAY, "AAPL", 0.5), _position_row(BOOK_DAY, "MSFT", -0.5)],
    )
    store.upsert(
        "reconciliation",
        [
            {
                "trade_date": SESSION,
                "forecast_annual_vol": 0.10,
                "expected_cost_bps": 15.0,
                "realized_cost_bps": None,
            }
        ],
    )
    attribution_job.run(ROOT / "data")
    row = store.select("attribution").iloc[0]
    # 15 bp of NAV as a fraction, negated: the book is gross 1.0 of NAV, so a
    # basis point of NAV is a basis point of gross.
    assert float(row["pnl_cost"]) == pytest.approx(-15.0 / 1e4)
    assert float(row["forecast_vol"]) == pytest.approx(0.10)
    assert float(row["expected_cost_bps"]) == pytest.approx(15.0)
    # And the identity still closes with a cost in it.
    assert (
        abs(
            float(row["pnl_total"])
            - (
                float(row["pnl_factor"])
                + float(row["pnl_idio"])
                + float(row["pnl_cost"])
            )
        )
        < 1e-12
    )


def test_the_fill_counts_come_from_the_order_rows(local_store: Path) -> None:
    store.upsert(
        "positions",
        [_position_row(BOOK_DAY, "AAPL", 0.5), _position_row(BOOK_DAY, "MSFT", -0.5)],
    )
    store.upsert(
        "orders",
        [
            {
                "trade_date": SESSION,
                "ticker": "AAPL",
                "intended_notional": 5000.0,
                "filled_notional": 4000.0,
                "status": "FILLED",
                "reason": "",
            },
            {
                "trade_date": SESSION,
                "ticker": "MSFT",
                "intended_notional": -5000.0,
                "filled_notional": 0.0,
                "status": "DRY_RUN",
                "reason": "dry run: no order sent",
            },
        ],
    )
    attribution_job.run(ROOT / "data")
    row = store.select("attribution").iloc[0]
    assert int(row["n_target"]) == 2
    assert int(row["n_filled"]) == 1
    assert float(row["max_fill_gap"]) == pytest.approx(5000.0)


def test_a_book_with_no_session_after_it_is_not_attributed(local_store: Path) -> None:
    """The last stored book earns a session that has not happened yet."""
    store.upsert(
        "positions",
        [_position_row(SESSION, "AAPL", 0.5), _position_row(SESSION, "MSFT", -0.5)],
    )
    report = attribution_job.run(ROOT / "data")
    assert report["n_stored"] == 0
    assert store.select("attribution").empty


def test_an_empty_store_is_reported_rather_than_read(local_store: Path) -> None:
    report = attribution_job.run(ROOT / "data")
    assert report["n_stored"] == 0
    assert "no positions" in report["detail"]


def test_the_positions_table_must_carry_the_columns_the_books_need() -> None:
    with pytest.raises(ValueError, match="trade_date"):
        attribution_job.books(pd.DataFrame({"ticker": ["AAPL"], "weight": [1.0]}))


def test_the_evening_calls_the_step_in_a_handler_that_cannot_fail_the_run() -> None:
    """Pinned in the source, because the fake cannot prove the `except` never raises.

    The attribution is a report about the book. A run that could not produce it
    must still hold and trade the book, so the call site catches, logs a scrubbed
    reason, and returns normally: no re-raise, and no use of `logger.exception`,
    whose traceback would carry whatever the failure happened to contain.
    """
    source = (ROOT / "scripts" / "run_live_daily.py").read_text()
    marker = "attributed = store_attribution(run_tree)"
    assert marker in source
    start = source.rindex("try:", 0, source.index(marker))
    end = source.index("snapshot_inputs = {", source.index(marker))
    block = source[start:end]
    assert "except Exception as exc:" in block
    assert "logger.warning(" in block
    assert "raise" not in block
    assert "logger.exception" not in block
    assert "notify.scrub(str(exc))" in block


def test_the_step_takes_the_run_tree_rather_than_a_module_global() -> None:
    """It must read the same extended artifacts the book was priced from."""
    source = (ROOT / "scripts" / "run_live_daily.py").read_text()
    assert "def store_attribution(run_tree: Path) -> dict[str, Any]:" in source
    assert "attribution_job.run(run_tree)" in source
