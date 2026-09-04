"""Tests for Task 2: point-in-time universe membership and sectors."""

import pandas as pd
import pytest

from efb.universe import (
    build_membership,
    build_sectors,
    membership_changes,
    survivorship_stats,
)

CHANGES = pd.DataFrame(
    {
        "effective_date": pd.to_datetime(["2015-01-02", "2018-06-01"]),
        "added_ticker": ["C", "D"],
        "removed_ticker": ["A", None],
        "reason": ["merger", "addition"],
    }
)
CONSTITUENTS = pd.DataFrame(
    {
        "symbol": ["B", "C", "D"],
        "security": ["Bee", "Cee", "Dee"],
        "gics_sector": ["Financials", "Tech", "Health Care"],
        "gics_sub_industry": ["Banks", "Software", "Biotech"],
        "date_added": pd.to_datetime(["2000-01-03", "2015-01-02", "2018-06-01"]),
    }
)


def test_build_membership_point_in_time() -> None:
    members = build_membership(
        CHANGES, CONSTITUENTS, start="2014-01-02", end="2019-12-31"
    )
    assert set(members.columns) == {"A", "B", "C", "D"}
    d = members.index
    before_c = (d < pd.Timestamp("2015-01-02")) & (d >= pd.Timestamp("2014-01-02"))
    # A was a member before its removal; C was not.
    assert members.loc[before_c, "A"].all()
    assert not members.loc[before_c, "C"].any()
    # After the change, C is in and A is out.
    after_c = d >= pd.Timestamp("2015-01-02")
    assert members.loc[after_c, "C"].all()
    assert not members.loc[after_c, "A"].any()
    # D joins on 2018-06-01.
    assert not members.loc[
        (d >= pd.Timestamp("2015-01-02")) & (d < pd.Timestamp("2018-06-01")), "D"
    ].any()
    assert members.loc[d >= pd.Timestamp("2018-06-01"), "D"].all()
    # B is always in.
    assert members["B"].all()


def test_build_membership_respects_rejoin() -> None:
    changes = pd.DataFrame(
        {
            "effective_date": pd.to_datetime(["2015-01-02", "2018-06-01"]),
            "added_ticker": [None, "A"],
            "removed_ticker": ["A", None],
            "reason": ["", ""],
        }
    )
    constituents = pd.DataFrame(
        {
            "symbol": ["A"],
            "security": ["Aye"],
            "gics_sector": ["Tech"],
            "gics_sub_industry": ["Software"],
            "date_added": pd.to_datetime(["2018-06-01"]),
        }
    )
    members = build_membership(
        changes, constituents, start="2014-01-02", end="2019-12-31"
    )
    d = members.index
    assert members.loc[
        (d >= pd.Timestamp("2014-01-02")) & (d < pd.Timestamp("2015-01-02")), "A"
    ].all()
    assert not members.loc[
        (d >= pd.Timestamp("2015-01-02")) & (d < pd.Timestamp("2018-06-01")), "A"
    ].any()
    assert members.loc[d >= pd.Timestamp("2018-06-01"), "A"].all()


def test_membership_changes_events() -> None:
    members = build_membership(
        CHANGES, CONSTITUENTS, start="2014-01-02", end="2019-12-31"
    )
    events = membership_changes(members)
    joined = events[events["event_type"] == "added"]
    left = events[events["event_type"] == "removed"]
    assert set(joined["ticker"]) == {"C", "D"}
    assert set(left["ticker"]) == {"A"}
    assert joined.loc[joined["ticker"] == "C", "date"].iloc[0] >= pd.Timestamp(
        "2015-01-02"
    )


def test_survivorship_stats_fraction() -> None:
    members = build_membership(
        CHANGES, CONSTITUENTS, start="2014-01-02", end="2019-12-31"
    )
    stats = survivorship_stats(members, price_tickers={"A", "B", "C", "D"})
    assert stats["n_deleted"] == 1
    assert stats["n_recovered"] == 1
    assert stats["fraction"] == pytest.approx(1.0)
    stats2 = survivorship_stats(members, price_tickers={"B", "C", "D"})
    assert stats2["fraction"] == pytest.approx(0.0)


def test_build_sectors() -> None:
    sectors = build_sectors(CONSTITUENTS, as_of="2026-09-04")
    assert set(sectors.columns) == {
        "ticker",
        "gics_sector",
        "gics_sub_industry",
        "source",
        "as_of",
    }
    assert sectors.loc[sectors["ticker"] == "B", "gics_sector"].iloc[0] == "Financials"
