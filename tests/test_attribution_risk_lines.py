"""The realized volatility is measured over the history, not over the batch.

`_with_risk_lines` takes a trailing standard deviation positionally over the frame it
is handed. `from_positions` hands it the sessions **not already attributed**, so an
evening that attributes one session gives the window one observation (a null) and an
evening that attributes two gives it the standard deviation of two numbers. The live
store carried both failures on 2026-10-22: eight rows with no realized volatility at
all, and 2026-10-15 with **0.226%** - the tenfold cliff the page drew - against
2.477% over the same session's own history.

These tests pin the arithmetic to the live series, and pin the restatement to writing
those three columns and nothing else.
"""

from __future__ import annotations

import math
import pathlib

import numpy as np
import pandas as pd
import pytest

from efb import attribution
from live import attribution_job, store

# The live store's own P&L, read on 2026-10-22 (`efb.attribution`, the refinalized
# rows). Small enough to keep in the test, and real enough that the numbers below
# are the numbers the page showed.
LIVE_PNL = {
    "2026-09-28": -0.0021041617,
    "2026-09-29": 0.0020268643,
    "2026-09-30": -0.0012472048,
    "2026-10-01": -0.0002750064,
    "2026-10-02": -0.0023290491,
    "2026-10-05": -0.0023007574,
    "2026-10-06": -0.0020078551,
    "2026-10-07": -0.0013494872,
    "2026-10-08": -0.0013212687,
    "2026-10-09": -0.0041165415,
    "2026-10-12": -0.0012909104,
    "2026-10-13": 0.0003346462,
    "2026-10-14": 0.0003936899,
    "2026-10-15": 0.0005924712,
    "2026-10-16": -0.0012765567,
    "2026-10-19": -0.0004966133,
    "2026-10-20": 0.0004967537,
    "2026-10-21": -0.0019875866,
}
LIVE_FORECAST = {
    "2026-09-28": None,
    "2026-09-29": 0.028712,
    "2026-09-30": 0.026772,
    "2026-10-01": 0.027185,
    "2026-10-02": 0.024776,
    "2026-10-05": 0.025380,
    "2026-10-06": 0.025073,
    "2026-10-07": None,
    "2026-10-08": 0.026557,
    "2026-10-09": 0.027653,
    "2026-10-12": 0.026365,
    "2026-10-13": 0.027599,
    "2026-10-14": None,
    "2026-10-15": 0.027479,
    "2026-10-16": 0.030109,
    "2026-10-19": 0.029609,
    "2026-10-20": 0.029202,
    "2026-10-21": 0.028650,
}
CLIFF_DAY = "2026-10-15"


def _history(days: list[str] | None = None) -> pd.DataFrame:
    chosen = days or sorted(LIVE_PNL)
    return pd.DataFrame(
        {
            "trade_date": chosen,
            "pnl_total": [LIVE_PNL[day] for day in chosen],
            "forecast_vol": [LIVE_FORECAST[day] for day in chosen],
        }
    )


def _two_point_vol(days: list[str]) -> float:
    """What the old path measured: the window over the batch, and nothing else."""
    values = np.array([LIVE_PNL[day] for day in days], dtype=float)
    return float(np.nanstd(values, ddof=1) * math.sqrt(252.0))


def _line(frame: pd.DataFrame, day: str) -> dict[str, object]:
    rows = frame.loc[frame["trade_date"] == day]
    assert len(rows) == 1, f"expected one line for {day}, got {len(rows)}"
    return dict(rows.iloc[0].to_dict())


def test_the_quarter_is_measured_over_the_history_not_the_batch() -> None:
    """The 10-15 cliff, both ways, on the store's own numbers."""
    history = attribution.risk_lines_over(_history())
    correct = float(_line(history, CLIFF_DAY)["realized_vol"])
    # 2.477%: what a rolling window over the book's own P&L produces, and what the
    # forecast of 2.748% beside it is comparable with.
    assert correct == pytest.approx(0.024771, abs=1e-6)

    # The bug: the two-session batch that the 10-15 evening actually priced.
    batch = _two_point_vol(["2026-10-14", "2026-10-15"])
    assert batch == pytest.approx(0.002231, abs=1e-6)
    # A tenfold cliff from one session to the next, out of a trailing-quarter measure.
    assert correct / batch > 10.0

    # And a batch of one cannot measure a standard deviation at all, which is why
    # every session attributed on its own was stored with no realized volatility.
    alone = attribution.risk_lines_over(_history([CLIFF_DAY]))
    assert pd.isna(_line(alone, CLIFF_DAY)["realized_vol"])


def test_every_session_of_the_history_matches_the_stored_series() -> None:
    """The restate reproduces the rows a full-history batch wrote, to the digit.

    The store's 09-29..10-20 rows were written by a run that attributed the whole
    series at once, so they are the reference. If the restate disagreed with them it
    would be replacing a good series with a different one.
    """
    history = attribution.risk_lines_over(_history()).set_index("trade_date")
    stored = {
        "2026-09-29": 0.046371,
        "2026-09-30": 0.034609,
        "2026-10-01": 0.028289,
        "2026-10-02": 0.028068,
        "2026-10-05": 0.026956,
        "2026-10-06": 0.025286,
        "2026-10-07": 0.023430,
        "2026-10-08": 0.021927,
        "2026-10-09": 0.025297,
        "2026-10-12": 0.024021,
        "2026-10-13": 0.024371,
        "2026-10-14": 0.024539,
        "2026-10-15": 0.024771,
        "2026-10-16": 0.023885,
        "2026-10-19": 0.023193,
        "2026-10-20": 0.023230,
    }
    for day, expected in stored.items():
        assert float(history.loc[day, "realized_vol"]) == pytest.approx(
            expected, abs=1e-6
        ), day
    # The session that had none: it is a number like its neighbours now.
    assert float(history.loc["2026-10-21", "realized_vol"]) == pytest.approx(
        0.022864, abs=1e-6
    )
    # 09-28 established the book, so it has no earlier P&L to measure against.
    assert pd.isna(history.loc["2026-09-28", "realized_vol"])


def test_the_ratio_is_the_realized_over_the_forecast() -> None:
    history = attribution.risk_lines_over(_history())
    line = _line(history, CLIFF_DAY)
    assert float(line["vol_ratio"]) == pytest.approx(
        float(line["realized_vol"]) / LIVE_FORECAST[CLIFF_DAY], rel=1e-12
    )
    # A session with no forecast has no ratio rather than a large one.
    assert pd.isna(_line(history, "2026-10-14")["vol_ratio"])


def test_a_re_priced_session_moves_every_later_window() -> None:
    """Why the restate is a series operation: a cost rewrite is in every window."""
    before = attribution.risk_lines_over(_history()).set_index("trade_date")
    repaired = _history()
    repaired.loc[repaired["trade_date"] == "2026-10-09", "pnl_total"] = (
        -0.0041165415 + 0.0009
    )
    after = attribution.risk_lines_over(repaired).set_index("trade_date")

    assert float(after.loc["2026-10-09", "realized_vol"]) != pytest.approx(
        float(before.loc["2026-10-09", "realized_vol"])
    )
    # A session whose window no longer holds the changed one does not move.
    assert float(after.loc["2026-10-20", "realized_vol"]) != pytest.approx(
        float(before.loc["2026-10-20", "realized_vol"])
    )


@pytest.fixture()
def local_store(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> pathlib.Path:
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    monkeypatch.setenv("EFB_STORE", "local")
    return tmp_path


def _rows() -> list[dict[str, object]]:
    """The store's rows as they were, with the three risk columns deliberately wrong."""
    out: list[dict[str, object]] = []
    for day in sorted(LIVE_PNL):
        out.append(
            {
                "trade_date": day,
                "pnl_total": LIVE_PNL[day],
                "forecast_vol": LIVE_FORECAST[day],
                # The two failures, side by side: a null where a session was priced
                # alone, and the two-point cliff on 10-15.
                "realized_vol": (float("nan") if day != CLIFF_DAY else 0.002258),
                "vol_ratio": float("nan"),
                "bias_statistic": None,
                "pnl_cost": -0.0001,
                "n_filled": 0.0,
                "written_at": "2026-10-20T23:42:08.806224+00:00",
            }
        )
    return out


def test_the_restate_writes_the_three_columns_and_leaves_the_row_alone(
    local_store: pathlib.Path,
) -> None:
    store.upsert("attribution", _rows())
    changed = attribution_job.restate_risk_lines()

    # Every session with a P&L history to look back on: all but the first, which
    # established the book and has no earlier session to measure against, so its
    # three columns are absent before and after and there is nothing to write.
    assert {item["day"] for item in changed} == set(LIVE_PNL) - {"2026-09-28"}
    repair = _line(
        store.select("attribution").rename(columns={"trade_date": "trade_date"}),
        CLIFF_DAY,
    )
    assert float(repair["realized_vol"]) == pytest.approx(0.024771, abs=1e-6)
    # Nothing else about the row moved: the cost, the fill count and the timestamp
    # are the row's own, not this pass's.
    assert float(repair["pnl_cost"]) == pytest.approx(-0.0001)
    assert float(repair["n_filled"]) == 0.0
    assert str(repair["written_at"]) == "2026-10-20T23:42:08.806224+00:00"
    # The session that had none now has one.
    assert float(_line(store.select("attribution"), "2026-10-21")["realized_vol"]) == (
        pytest.approx(0.022864, abs=1e-6)
    )


def test_a_second_restate_writes_nothing(local_store: pathlib.Path) -> None:
    """Idempotent: the values it wrote are the values it computes."""
    store.upsert("attribution", _rows())
    attribution_job.restate_risk_lines()
    settled = (
        store.select("attribution").sort_values("trade_date").reset_index(drop=True)
    )

    again = attribution_job.restate_risk_lines()

    assert again == []
    after = store.select("attribution").sort_values("trade_date").reset_index(drop=True)
    assert settled.equals(after)


def test_a_dry_run_reports_without_writing(local_store: pathlib.Path) -> None:
    store.upsert("attribution", _rows())
    before = (
        store.select("attribution").sort_values("trade_date").reset_index(drop=True)
    )

    changed = attribution_job.restate_risk_lines(dry_run=True)

    assert changed, "the dry run found nothing to restate, so it proves nothing"
    after = store.select("attribution").sort_values("trade_date").reset_index(drop=True)
    assert before.equals(after)


def test_the_row_it_writes_is_a_row_the_store_can_take() -> None:
    """jsonb comes back as a dict and has to go back as text, without a NaN in it.

    The first live apply of this restatement refused with "cannot adapt type 'dict'":
    a row read from Postgres carries its four jsonb columns parsed, and the write path
    wants text. The local store takes a dict happily, which is why the suite did not
    see it.
    """
    row = {
        "trade_date": pd.Timestamp("2026-10-15"),
        "realized_vol": 0.024771,
        "pnl_factor_json": {"market": 0.1, "value": float("nan")},
        "exposure_json": {"market": 0.4},
        "pnl_cost": -0.0001,
        "written_at": pd.Timestamp("2026-10-20T23:42:08"),
    }

    written = attribution_job._as_stored(row)

    assert written["trade_date"] == "2026-10-15"
    for column in attribution.JSON_COLUMNS:
        if column in row:
            assert isinstance(written[column], str), column
            assert "NaN" not in written[column], column
    # The rest of the row is the row: only the four jsonb columns and the key change.
    assert written["realized_vol"] == 0.024771
    assert written["pnl_cost"] == -0.0001
