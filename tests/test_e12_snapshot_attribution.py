"""Sprint E12 item 6: the attribution section of the page, and its contract.

The page reads one document, `docs/snapshot.schema.json` is that document's
contract, and `live.snapshot.build` is the only writer. So the things worth pinning
are that the block the builder emits is the block the schema declares, that the
cumulative sums are the stored rows' own sums rather than a second reconstruction,
that the live period is the store's own days and not the research panel's, and that
a run which could not read the attribution store says so on the page instead of
showing an empty table.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from live import snapshot

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs" / "snapshot.schema.json"
# The sprint's own artifact: the seed book's stored attribution, which is the
# page's backtest view.
SEED_ATTRIBUTION = ROOT / "data" / "attribution" / "daily.parquet"
SEED_MONTHLY = ROOT / "data" / "attribution" / "monthly.parquet"


def _day(
    trade_date: str,
    total: float,
    factor: float,
    idio: float,
    cost: float,
    **over: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "trade_date": trade_date,
        "n_names": 100,
        "gross": 1.0,
        "net": 0.0,
        "pnl_total": total,
        "pnl_factor": factor,
        "pnl_idio": idio,
        "pnl_cost": cost,
        # What the artifact itself reports: the row adds up only with this term,
        # and on a live day it is what is left of a residual that is nearly zero.
        "identity_residual": total - (factor + idio + cost),
        "pnl_factor_json": {"market": factor},
        "pnl_timing": 0.00001,
        "pnl_timing_json": {"market": 0.00001},
        "exposure_json": {"market": 0.1},
        "book_exposure_json": {"market": 0.1},
        "n_computed_specific": 1,
        "book_beta": 0.0228,
        "market_return": -0.0048,
        "pnl_beta": -0.00011,
        "forecast_vol": 0.0266,
        "pre_hedge_vol": 0.1023,
        "hedged_vol": 0.0255,
        "realized_vol": 0.0220,
        "vol_ratio": 0.83,
        "bias_statistic": 0.0,
        "factor_var_share": 0.000142,
        "idio_var_share": 0.999858,
        "n_missing_specific_var": 0,
        "expected_cost_bps": 14.23,
        "expected_trading_bps": 5.89,
        "expected_borrow_bps": 8.34,
        "realized_cost_bps": -10.24,
        "n_target": 220,
        "n_filled": 190,
        "max_fill_gap": 0.0,
        "n_missing_return": 0,
        "missing_return_weight": 0.0,
    }
    row.update(over)
    return row


@pytest.fixture(scope="module")
def live_frame() -> pd.DataFrame:
    """The store's rows: two rehearsal sessions, then two live ones."""
    return pd.DataFrame(
        [
            _day("2026-09-29", 0.0020, -0.00009, 0.0035, -0.0014),
            _day("2026-09-30", -0.0012, 0.0, 0.0002, -0.0015),
            _day("2026-10-01", -0.00028, -0.00022, -0.00006, 0.000005),
            _day("2026-10-02", -0.00233, -0.000007, -0.00277, 0.00045),
        ]
    )


@pytest.fixture(scope="module")
def seed_frame() -> pd.DataFrame:
    if not SEED_ATTRIBUTION.exists():
        pytest.skip("the seed attribution artifact is not built")
    return pd.read_parquet(SEED_ATTRIBUTION)


@pytest.fixture(scope="module")
def seed_monthly() -> pd.DataFrame:
    if not SEED_MONTHLY.exists():
        pytest.skip("the seed monthly attribution artifact is not built")
    return pd.read_parquet(SEED_MONTHLY)


def test_the_live_period_is_the_stores_days_from_the_period_start(
    live_frame: pd.DataFrame,
) -> None:
    """The rehearsal sessions are stored, attributed and left out of the view."""
    block = snapshot.attribution_block(live_frame)
    live = block["live"]
    assert live["first_day"] == "2026-10-01"
    assert live["last_day"] == "2026-10-02"
    assert (
        live["n_days"] == 2
    ), "the rehearsal sessions were counted into the live period"
    assert "2 rehearsal session(s)" in live["note"]
    assert [day["trade_date"] for day in live["daily"]] == ["2026-10-01", "2026-10-02"]
    assert "2026-10-01" in live["label"]


def test_the_seed_artifact_reports_its_own_sums(
    seed_frame: pd.DataFrame, seed_monthly: pd.DataFrame
) -> None:
    """Cumulative is the stored rows' sum, not a recomputation of them."""
    block = snapshot.attribution_block(pd.DataFrame(), (seed_frame, seed_monthly))
    backtest = block["backtest"]
    assert backtest["n_days"] == len(seed_frame)
    for field, column in (
        ("pnl_total", "pnl_total"),
        ("pnl_factor", "pnl_factor"),
        ("pnl_idio", "pnl_idio"),
        ("pnl_cost", "pnl_cost"),
        ("pnl_unexplained", "identity_residual"),
    ):
        assert backtest["cumulative"][field] == pytest.approx(
            float(seed_frame[column].sum())
        ), field
    # The worst day of the identity, not the sum of the residuals: a decomposition
    # is checked per day, and a summed residual of zero would hide two bad days.
    assert backtest["cumulative"]["max_identity_residual"] == pytest.approx(
        float(seed_frame["identity_residual"].abs().max())
    )
    assert backtest["cumulative"]["n_computed_specific"] == int(
        seed_frame["n_computed_specific"].sum()
    )


def test_a_days_four_terms_reach_its_total(
    seed_frame: pd.DataFrame, seed_monthly: pd.DataFrame
) -> None:
    """The point of the fourth term: every displayed row adds up.

    The artifacts' own residual is up to 123 bp on the seed's older vintages, so
    the three components do **not** reach the total; the day's four terms do, and
    the page draws the fourth rather than folding it into the others.
    """
    block = snapshot.attribution_block(pd.DataFrame(), (seed_frame, seed_monthly))
    for day in block["backtest"]["daily"]:
        parts = (
            day["pnl_factor"]
            + day["pnl_idio"]
            + day["pnl_cost"]
            + day["pnl_unexplained"]
        )
        assert parts == pytest.approx(day["pnl_total"], abs=1e-15)
    live = snapshot.attribution_block(
        pd.DataFrame(
            [
                # 2026-10-08 as the store holds it: the four terms of a live day,
                # whose residual is 1.1e-16 rather than a typed-in zero.
                _day(
                    "2026-10-08",
                    -0.001588529961824681,
                    0.0000470586875752,
                    -0.0002123169402226,
                    -0.0014232717091772,
                )
            ]
        )
    )["live"]
    day = live["daily"][0]
    assert day["pnl_unexplained"] == pytest.approx(0.0, abs=1e-15)
    assert day["pnl_factor"] + day["pnl_idio"] + day["pnl_cost"] + day[
        "pnl_unexplained"
    ] == pytest.approx(day["pnl_total"], abs=1e-15)


def test_the_per_factor_totals_are_the_stored_maps(seed_frame: pd.DataFrame) -> None:
    block = snapshot.attribution_block(pd.DataFrame(), (seed_frame, pd.DataFrame()))
    expected: dict[str, float] = {}
    for mapping in seed_frame["pnl_factor_json"]:
        for name, value in mapping.items():
            expected[name] = expected.get(name, 0.0) + float(value)
    assert set(block["backtest"]["by_factor"]) == set(expected)
    for name, value in expected.items():
        assert block["backtest"]["by_factor"][name] == pytest.approx(value)


def test_the_daily_series_is_the_window_newest_last_and_days_not_timestamps(
    seed_frame: pd.DataFrame,
) -> None:
    block = snapshot.attribution_block(pd.DataFrame(), (seed_frame, pd.DataFrame()))
    backtest = block["backtest"]
    days = [day["trade_date"] for day in backtest["daily"]]
    assert len(days) == snapshot.ATTRIBUTION_DAYS
    assert backtest["n_days_carried"] == snapshot.ATTRIBUTION_DAYS
    assert backtest["n_days"] > backtest["n_days_carried"], "the window is not bounded"
    assert days == sorted(days), "the series is not in date order"
    assert days[-1] == backtest["last_day"]
    for day in days:
        assert len(str(day)) == 10, f"a date carries a time: {day}"
    # Every day carries the lines the section shows, including the hedge's own
    # factor P&L, the raw-beta line and the risk split.
    for key in (
        "pnl_timing",
        "book_beta",
        "pnl_beta",
        "market_return",
        "factor_var_share",
        "idio_var_share",
    ):
        assert key in backtest["daily"][0], key


def test_the_backtest_is_labelled_and_carries_its_months(
    seed_frame: pd.DataFrame, seed_monthly: pd.DataFrame
) -> None:
    """The research panel is a separate, named period, and its chart is its months."""
    block = snapshot.attribution_block(pd.DataFrame(), (seed_frame, seed_monthly))
    backtest = block["backtest"]
    assert "research panel" in backtest["label"]
    assert "backtest" in backtest["note"]
    assert len(backtest["monthly"]) == len(seed_monthly)
    months = [row["month"] for row in backtest["monthly"]]
    assert months == sorted(months)
    assert backtest["monthly"][0]["month"].startswith("2012")
    assert sum(row["n_sessions"] for row in backtest["monthly"]) == len(seed_frame)
    # The live period carries no months: its own days are the series.
    live = snapshot.attribution_block(
        pd.DataFrame([_day("2026-10-01", 0.0, 0.0, 0.0, 0.0)])
    )
    assert live["live"]["monthly"] == []


def test_the_risk_split_is_the_path_the_days_carry() -> None:
    frame = pd.DataFrame(
        [
            _day(
                "2026-10-01",
                0.0,
                0.0,
                0.0,
                0.0,
                factor_var_share=0.0568,
                idio_var_share=0.9432,
            ),
            _day(
                "2026-10-02",
                0.0,
                0.0,
                0.0,
                0.0,
                factor_var_share=0.0002,
                idio_var_share=0.9998,
            ),
        ]
    )
    risk = snapshot.attribution_block(frame)["live"]["risk"]
    assert risk["as_of"] == "2026-10-02"
    assert risk["factor_share"] == pytest.approx(0.0002)
    assert risk["idio_share"] == pytest.approx(0.9998)
    assert [row["trade_date"] for row in risk["path"]] == ["2026-10-01", "2026-10-02"]


def test_a_period_with_no_risk_split_says_nothing_rather_than_zero() -> None:
    """A share nobody measured is not a share of nothing."""
    frame = pd.DataFrame(
        [
            _day(
                "2026-10-01",
                0.0,
                0.0,
                0.0,
                0.0,
                factor_var_share=float("nan"),
                idio_var_share=float("nan"),
            )
        ]
    )
    assert snapshot.attribution_block(frame)["live"]["risk"] is None


def test_a_cost_row_populates_realized_against_expected() -> None:
    """The two cost numbers travel separately, so the page can show both."""
    frame = pd.DataFrame([_day("2026-10-01", 0.001, 0.0005, 0.0008, -0.0003)])
    live = snapshot.attribution_block(frame)["live"]
    assert live["cost"]["expected_bps"] == pytest.approx(14.23)
    assert live["cost"]["realized_bps"] == pytest.approx(-10.24)
    assert live["cost"]["n_realized"] == 1


def test_the_cost_split_travels_beside_the_total_and_sums_to_it() -> None:
    """The page compares the realized cost against the trading half, not the total.

    The total carries borrow, which is a holding cost over the horizon and no fill
    price pays it, so the two halves travel as their own numbers. A day whose split
    the store never recorded leaves the halves as the days that do have one say,
    rather than averaging a missing day in as zero.
    """
    frame = pd.DataFrame(
        [
            _day(
                "2026-10-01",
                0.0,
                0.0,
                0.0,
                0.0,
                expected_trading_bps=float("nan"),
                expected_borrow_bps=float("nan"),
            ),
            _day(
                "2026-10-02",
                0.0,
                0.0,
                0.0,
                0.0,
                expected_cost_bps=10.0,
                expected_trading_bps=4.0,
                expected_borrow_bps=6.0,
            ),
            _day(
                "2026-10-05",
                0.0,
                0.0,
                0.0,
                0.0,
                expected_cost_bps=16.0,
                expected_trading_bps=8.0,
                expected_borrow_bps=8.0,
            ),
        ]
    )
    cost = snapshot.attribution_block(frame)["live"]["cost"]
    # The total is averaged over every day that has one; the halves over the days
    # that carry a split, so the first day's missing split is not averaged in as a
    # free fill.
    assert cost["expected_bps"] == pytest.approx((14.23 + 10.0 + 16.0) / 3)
    assert cost["expected_trading_bps"] == pytest.approx(6.0)
    assert cost["expected_borrow_bps"] == pytest.approx(7.0)
    assert cost["expected_trading_bps"] + cost["expected_borrow_bps"] == pytest.approx(
        13.0
    )


def test_a_period_with_no_cost_split_says_nothing_rather_than_zero() -> None:
    """A half nobody computed is not a half of nothing, and not a free fill."""
    frame = pd.DataFrame(
        [
            _day(
                "2026-10-01",
                0.0,
                0.0,
                0.0,
                0.0,
                expected_trading_bps=float("nan"),
                expected_borrow_bps=float("nan"),
            )
        ]
    )
    cost = snapshot.attribution_block(frame)["live"]["cost"]
    assert cost["expected_bps"] == pytest.approx(14.23)
    assert cost["expected_trading_bps"] is None
    assert cost["expected_borrow_bps"] is None


def test_the_hedge_forecast_travels_with_the_split_it_is_read_beside() -> None:
    """The two books, so the section can show what the hedge removed.

    A split alone is flat by design on a hedged book: the number that says whether
    the hedge was worth anything is the volatility before it against the volatility
    after, read off one covariance.
    """
    frame = pd.DataFrame(
        [
            _day("2026-10-01", 0.0, 0.0, 0.0, 0.0),
            _day(
                "2026-10-02",
                0.0,
                0.0,
                0.0,
                0.0,
                pre_hedge_vol=0.1111,
                hedged_vol=0.0262,
            ),
        ]
    )
    risk = snapshot.attribution_block(frame)["live"]["risk"]
    assert risk["as_of"] == "2026-10-02"
    assert risk["pre_hedge_vol"] == pytest.approx(0.1111)
    assert risk["hedged_vol"] == pytest.approx(0.0262)
    assert [row["pre_hedge_vol"] for row in risk["path"]] == [0.1023, 0.1111]


def test_the_recorded_live_read_shows_the_hedge_removing_risk() -> None:
    """The live record's own claim, measured on the days it carries.

    This is the number the section exists for: on every live day of the recorded
    read the sized book carries more predicted volatility than the book that was
    held, and the cost's two halves are the total the evening expected. Both are
    read out of the same file the page's fixtures are built from, so a change to
    either the builder or the recording has to keep the claim true.
    """
    recorded = json.loads(
        (ROOT / "tests" / "fixtures" / "attribution_live.json").read_text()
    )
    period = snapshot.attribution_block(pd.DataFrame(recorded["rows"]))["live"]
    pairs = [
        (row["pre_hedge_vol"], row["hedged_vol"])
        for row in period["risk"]["path"]
        if row["pre_hedge_vol"] is not None and row["hedged_vol"] is not None
    ]
    assert len(pairs) >= 5, "the recorded read stopped carrying the hedge forecast"
    for before, after in pairs:
        assert before > after, "the hedge adds risk on a day of the recorded read"
    cost = period["cost"]
    assert cost["expected_trading_bps"] + cost["expected_borrow_bps"] == pytest.approx(
        cost["expected_bps"]
    )
    assert cost["realized_bps"] < cost["expected_trading_bps"]


def test_an_unrealized_cost_is_counted_as_missing_rather_than_zero() -> None:
    """A cost nobody measured is not a cost of nothing."""
    frame = pd.DataFrame(
        [
            _day("2026-10-01", 0.001, 0.0, 0.001, 0.0, realized_cost_bps=11.0),
            _day("2026-10-02", 0.002, 0.0, 0.002, 0.0, realized_cost_bps=None),
        ]
    )
    live = snapshot.attribution_block(frame)["live"]
    assert live["cost"]["expected_bps"] == pytest.approx(14.23)
    assert live["cost"]["realized_bps"] == pytest.approx(11.0)
    assert live["cost"]["n_realized"] == 1, "the null was counted as measured"


def test_an_empty_store_says_so_rather_than_showing_nothing() -> None:
    block = snapshot.attribution_block(pd.DataFrame())
    assert block["live"]["n_days"] == 0
    assert block["live"]["daily"] == []
    assert block["live"]["note"], "an empty period must say why it is empty"
    assert block["live"]["cumulative"]["pnl_total"] is None


def test_the_builder_and_the_schema_declare_the_same_block(
    seed_frame: pd.DataFrame, seed_monthly: pd.DataFrame
) -> None:
    """The drift check the page's contract rests on.

    `types.ts` and the fixtures are checked against the schema on the TypeScript
    side; this is the other half, that the writer's own keys are the schema's. The
    period's shape is declared once, under `$defs`, because the two periods are one
    shape and two copies of it could drift.
    """
    schema = json.loads(SCHEMA.read_text())
    declared = schema["properties"]["attribution"]
    period = schema["$defs"]["attribution_period"]
    assert "attribution" in schema["required"]
    block = snapshot.empty_attribution("nothing yet")
    assert set(block) == set(declared["required"])
    assert set(block) == set(declared["properties"])
    assert set(block["live"]) == set(period["required"])
    assert set(block["live"]) == set(period["properties"])
    assert set(block["live"]["cumulative"]) == set(
        period["properties"]["cumulative"]["required"]
    )
    assert set(block["live"]["cost"]) == set(period["properties"]["cost"]["required"])
    # A real day's keys against the schema's, because the empty period carries no
    # day at all and the day is where the section's lines live.
    real = snapshot.attribution_block(
        pd.DataFrame([_day("2026-10-01", 0.0, 0.0, 0.0, 0.0)]),
        (seed_frame, seed_monthly),
    )
    day_schema = period["properties"]["daily"]["items"]
    assert set(real["live"]["daily"][0]) == set(day_schema["properties"])
    assert set(day_schema["required"]) <= set(real["live"]["daily"][0])
    month_schema = period["properties"]["monthly"]["items"]
    assert set(real["backtest"]["monthly"][0]) == set(month_schema["properties"])
    assert real["live"]["monthly"] == []
    risk_schema = period["properties"]["risk"]["oneOf"][0]
    risk = real["live"]["risk"]
    assert set(risk) == set(risk_schema["required"])
    assert set(risk["path"][0]) == set(
        risk_schema["properties"]["path"]["items"]["properties"]
    )


def test_build_passes_the_block_through_and_says_when_it_was_not_read() -> None:
    """`build` is an assembler: it never recomputes the store's numbers."""
    carried = snapshot.empty_attribution("from the run")
    carried["live"]["n_days"] = 3
    payload = snapshot.build(run={"target_close": "2026-09-21", "attribution": carried})
    assert payload["attribution"]["live"]["n_days"] == 3
    assert payload["attribution"]["note"] == "from the run"
    # A run that did not read the store says so, rather than showing an empty
    # section that reads as a book that earned nothing.
    bare = snapshot.build(run={"target_close": "2026-09-21"})
    assert bare["attribution"]["live"]["n_days"] == 0
    assert bare["attribution"]["note"] == "the run did not read the attribution store"
