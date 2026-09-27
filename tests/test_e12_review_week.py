"""Sprint E12 item 8: the weekly review, and that it works on one day.

The requirement is that it runs after day one, so the tests here drive it at one
day, at three, at a longer window and at nothing at all. What they check is that
the seven columns are the stored values, that a single day is described as a single
day rather than as a distribution, and that the summary says which parts of the
review have no data behind them instead of printing a number anyway.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts import review_week

ROOT = Path(__file__).resolve().parents[1]
SEED_ARTIFACT = ROOT / "data" / "attribution" / "daily.parquet"


def _row(day: str, **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "trade_date": day,
        "pnl_total": 0.0010,
        "pnl_factor": 0.0002,
        "pnl_idio": 0.0008,
        "pnl_cost": 0.0,
        "pnl_timing": 0.0001,
        "identity_residual": 0.0,
        "forecast_vol": 0.10,
        "realized_vol": 0.09,
        "expected_cost_bps": 15.0,
        "realized_cost_bps": 12.0,
        "n_target": 100,
        "n_filled": 100,
        "max_fill_gap": 0.0,
        "n_missing_return": 0,
        "missing_return_weight": 0.0,
    }
    base.update(over)
    return base


def _frame(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def test_one_day_reports_the_seven_columns_and_says_it_is_one_day() -> None:
    """The day-one case, which is the requirement: it runs before a week exists."""
    report = review_week.summarize(_frame(_row("2026-10-01")))
    assert report["n_days"] == 1
    assert report["first_day"] == report["last_day"] == "2026-10-01"
    row = report["rows"][0]
    assert row["pnl_total"] == pytest.approx(0.0010)
    assert row["pnl_factor"] == pytest.approx(0.0002)
    assert row["pnl_idio"] == pytest.approx(0.0008)
    assert row["pnl_cost"] == 0.0
    assert row["pnl_timing"] == pytest.approx(0.0001)
    assert row["realized_cost_bps"] == 12.0
    assert row["expected_cost_bps"] == 15.0
    assert row["n_filled"] == 100
    text = review_week.text(report)
    assert "1 attributed day" in text
    assert "no distribution yet" in text
    # And the closed form still travels, because it is a property of the bar and the
    # imagined edge rather than of the sample.
    assert "1008 days" in text


def test_the_components_and_the_hedge_line_are_the_stored_numbers() -> None:
    frame = _frame(
        _row("2026-10-01", pnl_total=0.001, pnl_factor=0.0002, pnl_idio=0.0008),
        _row("2026-10-02", pnl_total=0.003, pnl_factor=-0.0001, pnl_idio=0.0031),
    )
    report = review_week.summarize(frame)
    assert report["totals"]["pnl_total"] == pytest.approx(0.004)
    assert report["totals"]["pnl_factor"] == pytest.approx(0.0001)
    assert report["totals"]["pnl_idio"] == pytest.approx(0.0039)
    assert report["totals"]["pnl_timing"] == pytest.approx(0.0002)
    # The hedge's promise is stated with its own number, not asserted.
    line = [entry for entry in report["lines"] if "hedge's promise" in entry][0]
    assert "the hedge timing is +2.0 bp" in line


def test_realized_against_expected_cost_is_averaged_over_the_days_that_have_it() -> (
    None
):
    """A day with no realized fill is not a zero-cost day."""
    frame = _frame(
        _row("2026-10-01", realized_cost_bps=12.0, expected_cost_bps=15.0),
        _row("2026-10-02", realized_cost_bps=8.0, expected_cost_bps=11.0),
        _row("2026-10-03", realized_cost_bps=None, expected_cost_bps=9.0),
    )
    report = review_week.summarize(frame)
    assert report["cost"]["realized_bps"] == pytest.approx(10.0)
    assert report["cost"]["expected_bps"] == pytest.approx(35.0 / 3.0)
    line = [entry for entry in report["lines"] if entry.startswith("Cost, realized")][0]
    assert "over 2 of 3 day(s)" in line


def test_days_without_a_forecast_say_so_rather_than_showing_a_ratio() -> None:
    frame = _frame(_row("2026-10-01", forecast_vol=None, realized_vol=None))
    report = review_week.summarize(frame)
    assert report["volatility"] == {"forecast": None, "realized": None}
    assert any("no forecast was stored" in entry for entry in report["lines"])


def test_fills_are_counted_across_the_window_with_the_worst_gap() -> None:
    frame = _frame(
        _row("2026-10-01", n_target=10, n_filled=9, max_fill_gap=500.0),
        _row("2026-10-02", n_target=10, n_filled=10, max_fill_gap=120.0),
    )
    report = review_week.summarize(frame)
    line = [entry for entry in report["lines"] if entry.startswith("Fills:")][0]
    assert "19 of 20" in line
    assert "$500" in line


def test_no_days_at_all_is_reported_rather_than_raised() -> None:
    report = review_week.summarize(pd.DataFrame())
    assert report["n_days"] == 0
    assert report["rows"] == []
    assert "nothing to read" in review_week.text(report)


@pytest.mark.integration
def test_the_seed_book_reviews_over_its_own_artifact() -> None:
    """The same review, on the sprint's own stored days, so it is scaffolded."""
    if not SEED_ARTIFACT.exists():
        pytest.skip("the seed attribution artifact is not built")
    frame = review_week.load(days=30, artifact=True)
    report = review_week.summarize(frame)
    assert report["n_days"] == 30
    assert report["last_day"] == "2026-07-31"
    text = review_week.text(report)
    # The seven columns, the hedge line and the skill line all appear.
    for marker in ("close", "hedge", "real/exp cost", "vol real/fc", "fills", "Skill:"):
        assert marker in text, marker
    # The seed days carry no cost or forecast, and the review says that rather than
    # printing a zero for either.
    assert any("not being reviewed here" in entry for entry in report["lines"])
    assert any("no forecast was stored" in entry for entry in report["lines"])
    assert report["rows"][0]["pnl_total"] is not None


@pytest.mark.integration
def test_the_command_runs_on_the_artifact_and_exits_zero(
    capsys: pytest.CaptureFixture,
) -> None:
    if not SEED_ARTIFACT.exists():
        pytest.skip("the seed attribution artifact is not built")
    code = review_week.main(["--artifact", "--days", "5"])
    captured = capsys.readouterr().out
    assert code == 0
    assert "EFB weekly review" in captured
    assert "5 attributed days" in captured
