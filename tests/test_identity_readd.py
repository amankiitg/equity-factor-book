"""Tests for close-out task C6: re-added and current tickers (F2.6c).

C1 dropped every reused symbol, which also dropped four current S&P 500
constituents whose symbols were never reused at all: they were renamed, and
the changes table records a later add row for them. Those have a name on
the other side of the symbol that still matches, so they belong back in the
panel, truncated to start where the current company does.
"""

from __future__ import annotations

import pandas as pd
import pytest

from efb import identity


def _span(ticker: str, start: str, end: str, level: float) -> pd.DataFrame:
    dates = pd.bdate_range(start, end)
    idx = pd.MultiIndex.from_product([dates, [ticker]], names=["date", "ticker"])
    return pd.DataFrame({"adj_close": [level] * len(dates)}, index=idx)


def _prices(tickers: list[str]) -> pd.DataFrame:
    return pd.concat([_span(t, "2010-01-04", "2026-09-03", 20.0) for t in tickers])


def _names(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": [r[0] for r in rows],
            "symbol": [r[0] for r in rows],
            "long_name": [r[1] for r in rows],
            "short_name": [r[1] for r in rows],
        }
    )


def _constituents(tickers: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [t[0] for t in tickers],
            "security": [t[1] for t in tickers],
            "gics_sector": ["Industrials"] * len(tickers),
        }
    )


def _changes_with_adds(rows: list[tuple[str, str, str, str, str]]) -> pd.DataFrame:
    """(removal date, ticker, removed name, add date, added name)."""
    removals = pd.DataFrame(
        {
            "effective_date": pd.to_datetime([r[0] for r in rows]),
            "added_ticker": [None] * len(rows),
            "added_security": [None] * len(rows),
            "removed_ticker": [r[1] for r in rows],
            "removed_security": [r[2] for r in rows],
            "reason": ["test"] * len(rows),
        }
    )
    adds = [
        {
            "effective_date": pd.Timestamp(r[3]),
            "added_ticker": r[1],
            "added_security": r[4],
            "removed_ticker": None,
            "removed_security": None,
            "reason": "test",
        }
        for r in rows
        if r[3]
    ]
    frame = pd.concat([removals, pd.DataFrame(adds)], ignore_index=True)
    return frame.sort_values("effective_date").reset_index(drop=True)


def test_readd_table_keeps_a_current_constituent_that_was_renamed() -> None:
    changes = _changes_with_adds(
        [("2019-01-18", "PCG", "Pacific Gas & Electric Company", "2022-10-03", "PG&E")]
    )
    identity_table = identity.identity_table(
        changes,
        _prices(["PCG"]),
        _names([("PCG", "PG&E Corporation")]),
        breaks={"PCG"},
    )
    assert identity_table.iloc[0]["action"] == "drop"
    review = identity.readded_review(
        identity_table,
        changes,
        _constituents([("PCG", "PG&E")]),
        _names([("PCG", "PG&E Corporation")]),
    )
    row = review.iloc[0]
    assert row["ticker"] == "PCG"
    assert row["removed_name"] == "Pacific Gas & Electric Company"
    assert row["added_name"] == "PG&E"
    assert row["current_name"] == "PG&E Corporation"
    assert row["decision"] == "keep_truncated"
    assert row["truncation_date"] == pd.Timestamp("2022-10-03")


def test_readd_table_leaves_an_unmatched_holder_dropped() -> None:
    changes = _changes_with_adds(
        [("2019-01-18", "XYZ", "Old Name Corp", "2020-06-01", "New Name Corp")]
    )
    review = identity.readded_review(
        identity.identity_table(
            changes,
            _prices(["XYZ"]),
            _names([("XYZ", "Unrelated Holdings Inc")]),
            breaks={"XYZ"},
        ),
        changes,
        _constituents([("XYZ", "New Name Corp")]),
        _names([("XYZ", "Unrelated Holdings Inc")]),
    )
    assert review.iloc[0]["decision"] == "stays_dropped"


def test_readd_truncation_uses_the_first_price_when_it_is_later() -> None:
    changes = _changes_with_adds(
        [("2019-01-18", "XYZ", "Old Name Corp", "2020-06-01", "New Name Corp")]
    )
    prices = _span("XYZ", "2024-05-01", "2026-09-03", 20.0)
    review = identity.readded_review(
        identity.identity_table(
            changes, prices, _names([("XYZ", "New Name Corp")]), breaks={"XYZ"}
        ),
        changes,
        _constituents([("XYZ", "New Name Corp")]),
        _names([("XYZ", "New Name Corp")]),
    )
    row = review.iloc[0]
    assert row["decision"] == "keep_truncated"
    assert row["truncation_date"] == pd.Timestamp("2024-05-01")


def test_readd_table_uses_the_constituent_name_when_there_is_no_add_row() -> None:
    """ATI: removed in 2015, a current constituent, and no add row after.

    The changes table simply never records the return, so the only name to
    compare is the one the constituents table carries today, and there is
    no re-add date to truncate from. The rule is the later of the re-add
    date and the first valid price, so the first valid price wins and the
    history stays whole. That is the right answer here: yfinance still
    holds the symbol under the same company's current name, so nothing
    else ever took the ticker.
    """
    changes = _changes_with_adds(
        [("2015-07-02", "ATI", "Allegheny Technologies", "", "")]
    )
    review = identity.readded_review(
        identity.identity_table(
            changes,
            _prices(["ATI"]),
            _names([("ATI", "ATI Inc.")]),
            breaks={"ATI"},
        ),
        changes,
        _constituents([("ATI", "ATI Inc.")]),
        _names([("ATI", "ATI Inc.")]),
    )
    row = review.iloc[0]
    assert row["added_name"] == "ATI Inc."
    assert row["decision"] == "keep_truncated"
    assert pd.isna(row["added_date"])
    assert row["truncation_date"] == pd.Timestamp("2010-01-04")


def test_readd_table_leaves_an_unmatched_add_dropped() -> None:
    changes = _changes_with_adds(
        [("2017-09-01", "DD", "DuPont", "2019-06-03", "DuPont")]
    )
    review = identity.readded_review(
        identity.identity_table(
            changes,
            _prices(["DD"]),
            _names([("DD", "Ocean Thermal Energy Corporation")]),
            breaks={"DD"},
        ),
        changes,
        _constituents([("DD", "DuPont")]),
        _names([("DD", "Ocean Thermal Energy Corporation")]),
    )
    row = review.iloc[0]
    assert row["decision"] == "stays_dropped"
    assert pd.isna(row["truncation_date"]) or row["truncation_date"] is None


def test_readd_table_ignores_adds_that_predate_the_removal() -> None:
    # CLF was added in 2009 and removed in 2014, so there is no re-add after
    # the removal and nothing to restore
    changes = _changes_with_adds(
        [("2014-04-02", "CLF", "Cliffs Natural Resources", "2009-12-18", "Cliffs")]
    )
    review = identity.readded_review(
        identity.identity_table(
            changes,
            _prices(["CLF"]),
            _names([("CLF", "Cleveland-Cliffs Inc.")]),
            breaks={"CLF"},
        ),
        changes,
        _constituents([]),
        _names([("CLF", "Cleveland-Cliffs Inc.")]),
    )
    assert review.iloc[0]["decision"] == "stays_dropped"
    assert review.iloc[0]["added_name"] is None


def test_readd_table_skips_tickers_that_were_kept() -> None:
    changes = _changes_with_adds([("2016-03-29", "POM", "Pepco Holdings Inc", "", "")])
    identity_table = identity.identity_table(
        changes,
        _prices(["POM"]),
        _names([("POM", "Pepco Holdings Inc.")]),
    )
    assert identity_table.iloc[0]["action"] == "keep"
    review = identity.readded_review(
        identity_table, changes, _constituents([]), _names([("POM", "Pepco")])
    )
    assert review.empty


def test_exclusions_move_a_matched_readd_from_drop_to_truncate() -> None:
    base = pd.DataFrame(
        {
            "ticker": ["CPWR", "PCG", "DD"],
            "action": ["drop", "drop", "drop"],
            "drop_before": [None, None, None],
        }
    )
    review = pd.DataFrame(
        {
            "ticker": ["PCG", "DD"],
            "decision": ["keep_truncated", "stays_dropped"],
            "truncation_date": [pd.Timestamp("2022-10-03"), None],
        }
    )
    dropped, truncated = identity.exclusions(base, readded=review)
    assert dropped == ["CPWR", "DD"]
    assert truncated == {"PCG": pd.Timestamp("2022-10-03")}


def test_panel_coverage_counts_current_constituents_present_in_the_panel() -> None:
    constituents = _constituents([("AAA", "A Corp"), ("BBB", "B Corp"), ("CCC", "C")])
    returns = _span("AAA", "2024-01-01", "2024-03-01", 10.0)
    stats = identity.panel_coverage(constituents, returns)
    assert stats["n_current"] == 3
    assert stats["n_covered"] == 1
    assert stats["coverage"] == pytest.approx(1 / 3)
    assert stats["missing"] == ["BBB", "CCC"]
