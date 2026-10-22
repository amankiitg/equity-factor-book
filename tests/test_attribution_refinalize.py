"""The attribution re-prices a close once its fills exist.

The evening attributes a close before its orders settle, so the row it writes prices
the day at the *expected* cost and records `n_filled = 0`. Eight live rows were in
that state on 2026-10-21 (`docs/owner_fixes/attribution_recompute.md`), and the page
showed them as measured costs. The next run that knows what the fills cost re-runs
the same computation with the fills in the store and rewrites the row.

It does that from the evening job, not the morning one, and the reason is measured
rather than preferred: the morning's service holds no artifacts - `render.yaml` says
so, because every parquet under `data/` is gitignored - and a row cannot be rebuilt
without the XS-v1 artifacts its exposures are read from. The evening is the first run
with both the fills and a tree, so `run()` carries the pass (`refinalize_stale`) and
`refinalize` is the single day it calls.

Four properties are pinned here, and they are the whole contract:

- a row written against an estimate is replaced by the one the fills produce, with
  the corrected pre-hedge volatility untouched - the recompute runs the current code,
  so it can only restate that column;
- a second run is a no-op, because the stored `n_filled` then matches the fills;
- a close whose fills are already counted is not touched at all, which is what keeps
  the step idempotent and safe to run on every evening;
- the evening's own `run()` finds the stale rows and re-prices them without being
  told which they are, and leaves a hold day alone.
"""

from __future__ import annotations

import math
import pathlib

import pandas as pd
import pytest

from live import attribution_job, store

ROOT = pathlib.Path(__file__).resolve().parents[1]
# The newest session the repository's artifacts price, and the one the book earns.
BOOK_DAY = "2026-09-18"
SESSION = "2026-09-21"


@pytest.fixture()
def local_store(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> pathlib.Path:
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


def _fill_row(
    trade_date: str, ticker: str, notional: float, cost: float
) -> dict[str, object]:
    """One filled leg, shaped like `live.fills.reconcile_day`'s frame."""
    return {
        "trade_date": trade_date,
        "ticker": ticker,
        "status": "FILLED",
        "filled_notional": notional,
        "filled_quantity": notional / 100.0,
        "filled_price": 100.0,
        "filled_cost": cost,
        "intended_notional": notional,
        "side": "buy" if notional > 0 else "sell",
        # The measured cost is the slippage against the close the book was sized
        # from, which is the column `live.fills.realized_cost_bps` reads.
        "close_price": 100.0,
        "slippage_bps": cost / (abs(notional) / 100.0) * 1e4 if notional else 0.0,
    }


def _same_row(left: dict[str, object], right: dict[str, object]) -> bool:
    """Two stored rows, equal, with NaN equal to NaN: a stored absence is one."""
    if set(left) != set(right):
        return False
    for key, value in left.items():
        other = right[key]
        if isinstance(value, float) and isinstance(other, float):
            if math.isnan(value) and math.isnan(other):
                continue
            if abs(value - other) > 1e-12 * max(1.0, abs(value)):
                return False
        elif value != other:
            return False
    return True


def _stored(day: str) -> dict[str, object]:
    frame = store.select("attribution")
    days = frame["trade_date"].astype(str).str.slice(0, 10)
    return dict(frame.loc[days == day].iloc[-1].to_dict())


def _evening_row(local_store: pathlib.Path) -> None:
    """The evening as it is: a book, its attribution row, and no fills yet."""
    store.upsert(
        "positions",
        [
            _position_row(BOOK_DAY, "AAPL", 0.5),
            _position_row(BOOK_DAY, "MSFT", -0.5),
        ],
    )
    store.upsert(
        "nav",
        [{"trade_date": SESSION, "nav": 1_000_000.0, "equity": 1_000_000.0}],
    )
    store.upsert(
        "reconciliation",
        [
            {
                "trade_date": SESSION,
                "expected_cost_bps": 12.0,
                "expected_spread_bps": 4.0,
                "expected_impact_bps": 6.0,
                "expected_commission_bps": 1.0,
                "expected_borrow_bps": 1.0,
                "forecast_annual_vol": 0.03,
            }
        ],
    )
    attribution_job.run(ROOT / "data")


def test_the_morning_replaces_a_cost_written_before_the_fills(
    local_store: pathlib.Path,
) -> None:
    """The row the evening wrote is priced at the estimate; the morning's is not.

    The fills are put in the store after the evening's row exists, exactly as the
    15:30 reconciliation does, and the re-run must move the cost and the day's total
    while leaving the pre-hedge volatility alone - that column was corrected by the
    B4 fix and this step must not restate it into something else.
    """
    _evening_row(local_store)
    evening = _stored(SESSION)
    assert float(evening["n_filled"] or 0.0) == 0.0, "the evening wrote a fill count"

    store.upsert(
        "fills",
        [
            _fill_row(SESSION, "AAPL", 500_000.0, 55.0),
            _fill_row(SESSION, "MSFT", -500_000.0, 47.0),
        ],
    )
    report = attribution_job.refinalize(SESSION, ROOT / "data")
    assert report["changed"] is True, report
    assert report["n_filled"] == 2
    assert "pnl_cost" in report["moved"]

    morning = _stored(SESSION)
    assert float(morning["n_filled"]) == 2.0
    assert float(morning["pnl_cost"]) != pytest.approx(float(evening["pnl_cost"]))
    # The measured cost is the fills' own, and it is the number the row carries.
    assert float(morning["realized_cost_bps"]) == pytest.approx(
        report["after"]["realized_cost_bps"], rel=1e-9
    )
    # The volatility the hedge removed is the corrected one, unchanged: this step
    # re-runs the current code, so it may restate that column but never alter it.
    assert float(morning["pre_hedge_vol"]) == pytest.approx(
        float(evening["pre_hedge_vol"]), abs=1e-15
    )
    # And the identity still closes on the rewritten row.
    residual = float(morning["pnl_total"]) - (
        float(morning["pnl_factor"])
        + float(morning["pnl_idio"])
        + float(morning["pnl_cost"])
    )
    assert residual == pytest.approx(float(morning["identity_residual"]), abs=1e-12)


def test_a_second_morning_is_a_no_op(local_store: pathlib.Path) -> None:
    """Idempotent: once the fills are counted, the row is not touched again."""
    _evening_row(local_store)
    store.upsert("fills", [_fill_row(SESSION, "AAPL", 500_000.0, 55.0)])
    first = attribution_job.refinalize(SESSION, ROOT / "data")
    assert first["changed"] is True
    after_first = _stored(SESSION)

    second = attribution_job.refinalize(SESSION, ROOT / "data")
    assert second["changed"] is False
    assert "already counts these fills" in second["reason"]
    assert _same_row(_stored(SESSION), after_first)


def test_a_close_whose_fills_are_already_counted_is_left_alone(
    local_store: pathlib.Path,
) -> None:
    """A rerun of the same morning does not rewrite a row it has already corrected."""
    _evening_row(local_store)
    store.upsert(
        "fills",
        [
            _fill_row(SESSION, "AAPL", 500_000.0, 55.0),
            _fill_row(SESSION, "MSFT", -500_000.0, 47.0),
        ],
    )
    attribution_job.refinalize(SESSION, ROOT / "data")
    stored = _stored(SESSION)
    # The evening's own step never sees this day again: it has a row.
    assert attribution_job.run(ROOT / "data")["n_stored"] == 0
    assert _same_row(_stored(SESSION), stored)


def test_a_close_with_no_fills_is_not_rewritten(local_store: pathlib.Path) -> None:
    """A day the loop held has nothing to re-price, and is left exactly as stored."""
    _evening_row(local_store)
    before = _stored(SESSION)
    report = attribution_job.refinalize(SESSION, ROOT / "data")
    assert report["changed"] is False
    assert _same_row(_stored(SESSION), before)


def test_a_close_with_no_row_is_reported_rather_than_invented(
    local_store: pathlib.Path,
) -> None:
    """Nothing is created: the step corrects rows, it never adds a day."""
    report = attribution_job.refinalize("2026-10-30", ROOT / "data")
    assert report["changed"] is False
    assert "no stored row" in report["reason"]
    assert store.select("attribution").empty


def test_a_dry_run_reports_the_change_and_writes_nothing(
    local_store: pathlib.Path,
) -> None:
    """What the owner reads before the morning is allowed to move a number."""
    _evening_row(local_store)
    before = _stored(SESSION)
    store.upsert("fills", [_fill_row(SESSION, "AAPL", 500_000.0, 55.0)])
    report = attribution_job.refinalize(SESSION, ROOT / "data", dry_run=True)
    assert report["changed"] is False
    assert report["dry_run"] is True
    assert report["moved"], "the dry run found nothing to change"
    assert _same_row(_stored(SESSION), before)


def test_the_cost_the_row_carries_is_the_fills_own(
    local_store: pathlib.Path,
) -> None:
    """The rewritten cost is `live.fills.realized_cost_bps`, not a second estimate."""
    from live import fills as fills_module

    _evening_row(local_store)
    rows = [
        _fill_row(SESSION, "AAPL", 500_000.0, 55.0),
        _fill_row(SESSION, "MSFT", -500_000.0, 47.0),
    ]
    store.upsert("fills", rows)
    attribution_job.refinalize(SESSION, ROOT / "data")
    expected = fills_module.realized_cost_bps(pd.DataFrame(rows), 1_000_000.0)
    assert expected is not None
    assert float(_stored(SESSION)["realized_cost_bps"]) == pytest.approx(
        expected, rel=1e-9
    )


def test_the_evenings_own_run_re_prices_the_close_the_morning_filled(
    local_store: pathlib.Path,
) -> None:
    """The pass finds the stale row itself: the evening never names the days.

    This is the whole forward fix end to end. The evening writes the estimate, the
    fills arrive, and the next run of the same job - with no argument about which
    days are stale - replaces the row and says so in its report.
    """
    _evening_row(local_store)
    evening = _stored(SESSION)
    store.upsert("fills", [_fill_row(SESSION, "AAPL", 500_000.0, 55.0)])

    report = attribution_job.run(ROOT / "data")

    assert [item["day"] for item in report["refinalized"]] == [SESSION]
    assert "pnl_cost" in report["refinalized"][0]["moved"]
    now = _stored(SESSION)
    assert float(now["n_filled"]) == 1.0
    assert float(now["pnl_cost"]) != pytest.approx(float(evening["pnl_cost"]))
    assert float(now["pre_hedge_vol"]) == pytest.approx(
        float(evening["pre_hedge_vol"]), abs=1e-15
    )


def test_a_re_priced_close_is_not_re_priced_again(local_store: pathlib.Path) -> None:
    """Once the row counts its fills, the pass has nothing to do on any later run."""
    _evening_row(local_store)
    store.upsert("fills", [_fill_row(SESSION, "AAPL", 500_000.0, 55.0)])
    attribution_job.run(ROOT / "data")
    settled = _stored(SESSION)

    again = attribution_job.run(ROOT / "data")

    assert again["refinalized"] == []
    assert _same_row(_stored(SESSION), settled)


def test_a_close_with_no_fills_is_never_a_candidate(
    local_store: pathlib.Path,
) -> None:
    """A hold day has no fills to price, so the pass cannot touch its row."""
    _evening_row(local_store)
    evening = _stored(SESSION)

    again = attribution_job.run(ROOT / "data")

    assert again["refinalized"] == []
    assert _same_row(_stored(SESSION), evening)
