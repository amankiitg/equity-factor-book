"""The research corporate-actions record: the table, the alias and the rule.

The point of these tests is the seam E11 found: a spin-off moves one session's
return, neither price vendor adjusts for it, and the returns build has to be able
to put the correction back from a record rather than from the vendor's arithmetic.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from efb import corporate_actions, hygiene

PARENT, CHILD = "CTVA", "VYLR"
EX_DATE = pd.Timestamp("2026-10-01")
PRIOR = pd.Timestamp("2026-09-30")


def prices_frame() -> pd.DataFrame:
    """A two-session panel with the parent's raw print and no child."""
    rows = [
        {"date": PRIOR, "ticker": PARENT, "close": 77.65},
        {"date": EX_DATE, "ticker": PARENT, "close": 12.57},
        {"date": PRIOR, "ticker": "AAPL", "close": 200.0},
        {"date": EX_DATE, "ticker": "AAPL", "close": 202.0},
    ]
    frame = pd.DataFrame(rows).set_index(["date", "ticker"])
    for column in (
        "open",
        "high",
        "low",
        "adj_close",
        "volume",
        "dividend",
        "split_factor",
    ):
        frame[column] = np.nan
    return frame


def returns_frame() -> pd.DataFrame:
    """The returns the build computes from those prices alone."""
    rows = [
        {"date": PRIOR, "ticker": PARENT, "r": np.nan},
        {"date": EX_DATE, "ticker": PARENT, "r": 12.57 / 77.65 - 1.0},
        {"date": PRIOR, "ticker": "AAPL", "r": np.nan},
        {"date": EX_DATE, "ticker": "AAPL", "r": 0.01},
    ]
    frame = pd.DataFrame(rows).set_index(["date", "ticker"])
    frame["g"] = np.log1p(frame["r"])
    return hygiene.apply_flags(frame)


def write_table(
    tmp_path, child: str = CHILD, child_close: float | None = 68.26, **over
):
    row = {
        "first_seen": "2026-10-03T00:00:00",
        "last_seen": "2026-10-03T00:00:00",
        "ticker": PARENT,
        "effective_date": EX_DATE.date().isoformat(),
        "new_ticker": child,
        "vendor_symbol": child,
        "factor": 1.0,
        "source_rate": 1.0,
        "new_rate": 1.0,
        "child_close": child_close,
        "parent_close": 12.57,
        "parent_prior_close": 77.65,
        "prior_session": PRIOR.date().isoformat(),
        "action_kind": "share_distribution",
        "source": "alpaca.corporate_actions",
        "explained_by": "spinoff",
        "cross_check_ratio": None,
    }
    row.update(over)
    (tmp_path / "processed").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_parquet(tmp_path / corporate_actions.TABLE, index=False)


def test_a_temporary_line_is_priced_on_the_security_behind_it() -> None:
    """A when-issued suffix names the same security; a warrant suffix does not."""
    assert corporate_actions.priceable_symbol("AIRC.WI") == ("AIRC", "WI")
    assert corporate_actions.priceable_symbol("VYLR") == (
        "VYLR",
        "share_distribution",
    )
    # A warrant comes back untouched: pricing GME.WS as GME would apply the
    # distribution to the parent twice, which is a measured 9.4-point error.
    assert corporate_actions.priceable_symbol("GME.WS") == ("GME.WS", "WS")
    assert "vendor_symbol" in corporate_actions.COLUMNS


def test_collect_records_the_child_close_and_both_symbols(tmp_path) -> None:
    """The record is self-contained: the close is fetched once and stored."""

    def records(symbols, year):
        assert year == 2026
        return [
            {
                "parent": PARENT,
                "child": "AIRC.WI",
                "ex_date": EX_DATE,
                "source_rate": 1.0,
                "new_rate": 1.0,
            }
        ]

    asked: list[tuple[str, pd.Timestamp]] = []

    def close(symbol, session, source_rate=0.0):
        asked.append((symbol, session))
        return 68.26

    def parent_closes(symbol, session):
        return 12.57, 77.65, PRIOR

    frame = corporate_actions.collect(
        tmp_path,
        universe=[PARENT],
        years=(2026,),
        spin_off_fetcher=records,
        close_fetcher=close,
        parent_fetcher=parent_closes,
    )
    assert asked == [("AIRC", EX_DATE)], "the temporary suffix is stripped to price it"
    row = frame.iloc[0]
    assert row["new_ticker"] == "AIRC"
    assert row["vendor_symbol"] == "AIRC.WI"
    assert row["child_close"] == 68.26
    assert row["action_kind"] == "WI"
    assert corporate_actions.read(tmp_path).equals(frame)
    summary = corporate_actions.summary(tmp_path)
    assert summary["records"] == 1 and summary["applied"] == 1


def test_apply_corrects_the_parent_and_keeps_the_raw_print_in_the_flag(
    tmp_path,
) -> None:
    """The cell holds the total return; the flag still says there was a print."""
    write_table(tmp_path)
    before = returns_frame()
    assert (
        bool(before.loc[(EX_DATE, PARENT), "outlier"]) is True
    ), "the CTVA shape is a large move on the vendor's own numbers"
    after, outcomes = corporate_actions.apply(before, prices_frame(), tmp_path)
    expected = (12.57 + 1.0 * 68.26) / 77.65 - 1.0
    assert len(outcomes) == 1
    assert after.loc[(EX_DATE, PARENT), "r"] == expected
    assert after.loc[(EX_DATE, PARENT), "g"] == np.log1p(expected)
    assert (
        bool(after.loc[(EX_DATE, PARENT), "outlier"]) is True
    ), "the print the rule replaced stays on the record"
    assert bool(after.loc[(EX_DATE, PARENT), "corrected"]) is True
    # nothing else in the panel moved
    assert after.loc[(EX_DATE, "AAPL"), "r"] == before.loc[(EX_DATE, "AAPL"), "r"]
    assert bool(after.loc[(EX_DATE, "AAPL"), "corrected"]) is False


def test_a_print_over_the_bound_is_flagged_and_the_repaired_cell_still_fits(
    tmp_path,
) -> None:
    """A repaired cell is not masked: the flag is the record, the cell is the input."""
    frame = returns_frame()
    assert bool(frame.loc[(EX_DATE, PARENT), "outlier"]) is True
    assert np.isnan(
        hygiene.clean_returns(frame).loc[(EX_DATE, PARENT)]
    ), "before the repair the print is masked out, as it must be"
    write_table(tmp_path)
    after, _outcomes = corporate_actions.apply(frame, prices_frame(), tmp_path)
    assert (
        bool(after.loc[(EX_DATE, PARENT), "outlier"]) is True
    ), "the print stays recorded"
    repaired = hygiene.clean_returns(after).loc[(EX_DATE, PARENT)]
    assert np.isfinite(repaired), "a repaired cell is not thrown away by the mask"
    assert repaired == after.loc[(EX_DATE, PARENT), "r"]


def test_apply_nulls_the_cell_when_the_child_cannot_be_priced(tmp_path) -> None:
    """A hole is reported and a wrong return is not: E11's own choice."""
    write_table(tmp_path, child="AIRC.WI", child_close=None)
    after, outcomes = corporate_actions.apply(returns_frame(), prices_frame(), tmp_path)
    assert len(outcomes) == 1
    assert outcomes[0].missing_child is True
    assert np.isnan(after.loc[(EX_DATE, PARENT), "r"])
    assert bool(after.loc[(EX_DATE, PARENT), "corrected"]) is True


def test_apply_is_a_fixed_point(tmp_path) -> None:
    """Re-applying writes the same numbers: the record and the closes are inputs."""
    write_table(tmp_path)
    once, _ = corporate_actions.apply(returns_frame(), prices_frame(), tmp_path)
    twice, _ = corporate_actions.apply(once, prices_frame(), tmp_path)
    shared = ["r", "g"]
    assert once[shared].equals(twice[shared])


def test_the_priced_frame_adds_the_child_and_overrides_the_parents_raw_closes(
    tmp_path,
) -> None:
    """The child is added; the parent's own two closes are replaced by raw ones.

    A research panel is delivered back-adjusted, so its prior close already has the
    distribution taken out of it. The rule is written for raw closes on both sides,
    which is why the parent's two are overridden rather than trusted.
    """
    write_table(
        tmp_path,
        child=CHILD,
        child_close=68.26,
        parent_close=12.57,
        parent_prior_close=77.65,
        prior_session=PRIOR.date().isoformat(),
    )
    frame = corporate_actions.priced_frame(tmp_path, prices_frame())
    assert frame.loc[(EX_DATE, CHILD), "close"] == 68.26, "the child is added"
    assert len(frame) == len(prices_frame()) + 1
    assert frame.loc[(EX_DATE, PARENT), "close"] == 12.57
    assert frame.loc[(PRIOR, PARENT), "close"] == 77.65
    assert frame.loc[(EX_DATE, "AAPL"), "close"] == 202.0, "nothing else moved"
    assert (
        prices_frame().loc[(PRIOR, PARENT), "close"] == 77.65
    ), "the input is untouched"


def test_a_record_the_vendor_drops_stays_applied(tmp_path) -> None:
    """The table is the union of every read, not the latest one.

    Measured: the same per-year read returned 30 records in the morning and 28 in
    the afternoon, and `EXC -> CEG` was in the first and in none of the later ones.
    Replacing the table on each read would have dropped it and put the vendor's own
    arithmetic back on 2022-02-02.
    """

    def first_read(symbols, year):
        return [
            {
                "parent": PARENT,
                "child": CHILD,
                "ex_date": EX_DATE,
                "source_rate": 1.0,
                "new_rate": 1.0,
            },
            {
                "parent": "EXC",
                "child": "CEG",
                "ex_date": pd.Timestamp("2022-02-02"),
                "source_rate": 1.0,
                "new_rate": 0.33333,
            },
        ]

    def close(symbol, session, source_rate=0.0):
        return 68.26 if symbol == CHILD else 46.41

    def parent_closes(symbol, session):
        return (
            (12.57, 77.65, PRIOR)
            if symbol == PARENT
            else (42.86, 57.83, pd.Timestamp("2022-02-01"))
        )

    corporate_actions.collect(
        tmp_path,
        universe=[PARENT, "EXC"],
        years=(2022, 2026),
        spin_off_fetcher=first_read,
        close_fetcher=close,
        parent_fetcher=parent_closes,
        seen_at="2026-10-03T05:25:00",
    )
    assert corporate_actions.summary(tmp_path)["records"] == 2

    # the second read reports only the first of the two
    def second_read(symbols, year):
        if year != 2026:
            return []
        return [
            {
                "parent": PARENT,
                "child": CHILD,
                "ex_date": EX_DATE,
                "source_rate": 1.0,
                "new_rate": 1.0,
            }
        ]

    corporate_actions.collect(
        tmp_path,
        universe=[PARENT, "EXC"],
        years=(2026,),
        spin_off_fetcher=second_read,
        close_fetcher=close,
        parent_fetcher=parent_closes,
        seen_at="2026-10-03T12:00:00",
    )
    table = corporate_actions.read(tmp_path)
    assert len(table) == 2, "the dropped record is still there"
    exc = table.loc[table["ticker"] == "EXC"].iloc[0]
    assert exc["new_ticker"] == "CEG"
    assert float(exc["factor"]) == pytest.approx(0.33333)
    summary = corporate_actions.summary(tmp_path)
    assert summary["records"] == 2
    assert summary["not_in_the_latest_read"] == ["EXC 2022-02-02"]
    assert len(summary["reads"]) == 2, "each read keeps the date it was seen"
    # the refreshed row keeps the date it was first seen on
    kept = table.loc[table["ticker"] == PARENT].iloc[0]
    assert kept["first_seen"] < kept["last_seen"]


def test_merge_takes_a_read_taken_earlier_with_its_own_date(tmp_path) -> None:
    """A cached read can be put on the record without re-dating it."""
    frame = corporate_actions.merge(
        tmp_path,
        [
            {
                "parent": "FTI",
                "child": "THNPF",
                "ex_date": pd.Timestamp("2021-02-16"),
                "source_rate": 1.0,
                "new_rate": 0.2,
            }
        ],
        seen_at="2026-10-03T05:25:00",
        source="alpaca.corporate_actions (cached read)",
        close_fetcher=lambda symbol, session, rate=0.0: None,
        parent_fetcher=lambda symbol, session: (None, None, None),
    )
    row = frame.iloc[0]
    assert row["ticker"] == "FTI"
    assert row["first_seen"] == "2026-10-03T05:25:00"
    assert row["new_ticker"] == "THNPF"
    assert float(row["factor"]) == pytest.approx(0.2)
    assert row["child_close"] is None, "no close was recorded with that read"
    assert corporate_actions.summary(tmp_path)["reads"] == ["2026-10-03T05:25:00"]


def test_a_warrant_record_carries_no_ratio(tmp_path) -> None:
    """The suffix is kept and the ratio dropped: there is no child share to price."""
    frame = corporate_actions.merge(
        tmp_path,
        [
            {
                "parent": "GME",
                "child": "GME.WS",
                "ex_date": pd.Timestamp("2025-10-03"),
                "source_rate": 1.0,
                "new_rate": 0.1,
            }
        ],
        seen_at="2026-10-03T00:00:00",
    )
    row = frame.iloc[0]
    assert row["new_ticker"] == "GME.WS"
    assert row["action_kind"] == "WS"
    assert row["factor"] is None


def test_a_root_with_no_table_reads_as_no_records(tmp_path) -> None:
    """A fresh container builds without a vendor history rather than refusing to."""
    assert corporate_actions.read(tmp_path).empty
    assert corporate_actions.ensure(tmp_path).empty
    assert corporate_actions.recorded(tmp_path) == []
    frame = returns_frame()
    after, outcomes = corporate_actions.apply(frame, prices_frame(), tmp_path)
    assert outcomes == []
    assert after.equals(frame)
