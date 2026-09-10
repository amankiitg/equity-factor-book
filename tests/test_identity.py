"""Tests for close-out task C1: ticker identity (criterion F2.6b).

A removed S&P 500 member's symbol can be taken over by an unrelated
listing, and the vendor then splices both histories into one series. The
name on the other end of the symbol is the only cheap way to tell.
"""

from __future__ import annotations

import pandas as pd
import pytest

from efb import identity


def _changes(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "effective_date": pd.to_datetime([r[0] for r in rows]),
            "added_ticker": [None] * len(rows),
            "added_security": [None] * len(rows),
            "removed_ticker": [r[1] for r in rows],
            "removed_security": [r[2] for r in rows],
            "reason": ["test"] * len(rows),
        }
    )


def _prices(ticker: str, values: dict[str, float]) -> pd.DataFrame:
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(list(values)), [ticker]], names=["date", "ticker"]
    )
    return pd.DataFrame({"adj_close": list(values.values())}, index=idx)


def _span(ticker: str, start: str, end: str, level: float) -> pd.DataFrame:
    """Business-day prices at a constant level, like a real price series."""
    dates = pd.bdate_range(start, end)
    return _prices(ticker, dict.fromkeys(dates.strftime("%Y-%m-%d"), level))


def _names(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": [r[0] for r in rows],
            "symbol": [r[0] for r in rows],
            "long_name": [r[1] for r in rows],
            "short_name": [r[1] for r in rows],
        }
    )


def test_normalize_name_strips_legal_suffixes_and_punctuation() -> None:
    assert identity.normalize_name("Compuware Corp.") == frozenset({"compuware"})
    assert identity.normalize_name("Pepco Holdings, Inc.") == frozenset(
        {"pepco", "holdings"}
    )
    assert identity.normalize_name("NVIDIA Corporation Class A") == frozenset(
        {"nvidia"}
    )
    assert identity.normalize_name("Marshall & Ilsley Corp") == frozenset(
        {"marshall", "ilsley"}
    )


def test_normalize_name_handles_empty_and_nan() -> None:
    assert identity.normalize_name(None) == frozenset()
    assert identity.normalize_name(float("nan")) == frozenset()
    assert identity.normalize_name("Inc.") == frozenset()


def test_match_score_identical_names_is_one() -> None:
    assert identity.match_score("Compuware Corp", "Compuware Corporation") == 1.0


def test_match_score_unrelated_names_is_zero() -> None:
    score = identity.match_score("Compuware Corp", "Ocean Thermal Energy Corporation")
    assert score == 0.0


def test_match_score_partial_overlap_sits_between() -> None:
    score = identity.match_score("El Paso Corp", "El Paso Electric Company")
    assert 0.0 < score < 1.0


def test_identity_table_flags_a_reused_symbol() -> None:
    # a mismatch plus a level break in the prices is a splice
    frame = identity.identity_table(
        _changes([("2014-12-01", "CPWR", "Compuware Corp")]),
        _span("CPWR", "2010-01-04", "2026-09-03", 0.0002),
        _names([("CPWR", "Ocean Thermal Energy Corporation")]),
        breaks={"CPWR"},
    )
    row = frame.iloc[0]
    assert row["ticker"] == "CPWR"
    assert row["removed_name"] == "Compuware Corp"
    assert row["current_name"] == "Ocean Thermal Energy Corporation"
    assert row["match_score"] == 0.0
    assert bool(row["reused"]) is True
    assert bool(row["has_break"]) is True
    assert row["removal_date"] == pd.Timestamp("2014-12-01")
    assert row["first_valid_date"] == pd.Timestamp("2010-01-04")
    assert row["last_valid_date"] == pd.Timestamp("2026-09-03")


def test_a_name_change_without_a_price_break_is_still_excluded() -> None:
    # du Pont became DuPont and 21st Century Fox became Fox, real renames, but
    # ADC Telecommunications became ADC Therapeutics and Amoco became
    # AutoNation with the same visible profile: a name mismatch and clean
    # prices. Names and prices cannot separate the two, so a mismatch is
    # excluded and the renames are recorded for the security-master work.
    frame = identity.identity_table(
        _changes([("2019-03-20", "FOXA", "21st Century Fox Class A")]),
        _span("FOXA", "2010-01-04", "2026-09-03", 30.0),
        _names([("FOXA", "Fox Corporation")]),
    )
    row = frame.iloc[0]
    assert row["match_score"] < identity.MATCH_THRESHOLD
    assert bool(row["reused"]) is True
    assert bool(row["has_break"]) is False
    assert bool(row["rename_suspect"]) is True
    assert row["action"] == "drop"
    assert row["note"].startswith("symbol reused")


def test_an_unverified_symbol_is_kept_and_recorded() -> None:
    frame = identity.identity_table(
        _changes([("2018-06-01", "WCG", "WellCare Health Plans")]),
        _span("WCG", "2010-01-04", "2018-05-31", 150.0),
        _names([("WCG", None)]),  # type: ignore[list-item]
    )
    row = frame.iloc[0]
    assert bool(row["verified"]) is False
    assert bool(row["reused"]) is False
    assert row["action"] == "keep"
    assert "could not verify" in row["note"]


def test_identity_table_keeps_a_name_that_still_matches() -> None:
    frame = identity.identity_table(
        _changes([("2016-03-29", "POM", "Pepco Holdings Inc")]),
        _span("POM", "2010-01-04", "2026-09-03", 18.0),
        _names([("POM", "Pepco Holdings Inc.")]),
    )
    row = frame.iloc[0]
    assert bool(row["reused"]) is False
    assert row["action"] == "keep"
    assert row["match_score"] == 1.0


def test_truncate_when_the_current_company_segment_starts_later() -> None:
    # two live segments: the early one is the member, the late one is the
    # company that took the symbol. The break date is visible, so the rows
    # before it are dropped rather than the whole ticker.
    prices = pd.concat(
        [
            _span("XYZ", "2010-01-04", "2011-06-30", 20.0),
            _span("XYZ", "2020-01-02", "2026-09-03", 3.0),
        ]
    )
    frame = identity.identity_table(
        _changes([("2011-07-01", "XYZ", "Old Member Corp")]),
        prices,
        _names([("XYZ", "Brand New Listing Inc")]),
        breaks={"XYZ"},
    )
    row = frame.iloc[0]
    assert bool(row["reused"]) is True
    assert row["action"] == "truncate"
    assert row["drop_before"] == pd.Timestamp("2020-01-02")
    assert row["gap_days"] > 60


def test_drop_when_the_break_date_cannot_be_determined() -> None:
    # one continuous live segment with no gap: nothing in the prices says
    # where one company ends and the other begins
    frame = identity.identity_table(
        _changes([("2012-05-16", "EP", "El Paso Corp")]),
        _span("EP", "2010-01-04", "2026-09-03", 12.0),
        _names([("EP", "Empire Petroleum Corporation")]),
        breaks={"EP"},
    )
    row = frame.iloc[0]
    assert bool(row["reused"]) is True
    assert row["action"] == "drop"
    assert row["drop_before"] is None
    assert row["note"].startswith("symbol reused and break date cannot be determined")


def test_a_reused_symbol_with_no_membership_overlap_is_dropped() -> None:
    # truncation would keep the unrelated current company and throw away the
    # member, so the ticker goes instead
    prices = pd.concat(
        [
            _span("XYZ", "2010-01-04", "2011-06-30", 20.0),
            _span("XYZ", "2020-01-02", "2026-09-03", 3.0),
        ]
    )
    members = pd.DataFrame(
        {"XYZ": True}, index=pd.bdate_range("2010-01-04", "2011-06-30")
    )
    frame = identity.identity_table(
        _changes([("2011-07-01", "XYZ", "Old Member Corp")]),
        prices,
        _names([("XYZ", "Brand New Listing Inc")]),
        members=members,
        breaks={"XYZ"},
    )
    row = frame.iloc[0]
    assert row["action"] == "drop"
    assert "does not overlap" in row["note"]


def test_gap_flag_above_sixty_business_days() -> None:
    prices = pd.concat(
        [
            _span("GAP", "2010-01-04", "2010-06-30", 20.0),
            _span("GAP", "2011-06-01", "2026-09-03", 3.0),
        ]
    )
    frame = identity.identity_table(
        _changes([("2010-07-01", "GAP", "Old Name Corp")]),
        prices,
        _names([("GAP", "Old Name Corp")]),
    )
    row = frame.iloc[0]
    assert row["gap_days"] > 60
    assert bool(row["has_gap"]) is True
    assert bool(row["reused"]) is False  # the name still matches


def test_short_gap_is_not_flagged() -> None:
    prices = pd.concat(
        [
            _span("SG", "2010-01-04", "2010-03-01", 20.0),
            _span("SG", "2010-03-10", "2026-09-03", 24.0),
        ]
    )
    frame = identity.identity_table(
        _changes([("2011-01-03", "SG", "Same Name Corp")]),
        prices,
        _names([("SG", "Same Name Corp")]),
    )
    assert bool(frame.iloc[0]["has_gap"]) is False


def test_fetch_symbol_names_calls_yfinance_once_per_symbol(
    tmp_path: pytest.TempPathFactory,
) -> None:
    calls: list[str] = []

    def fake_fetcher(symbol: str) -> dict[str, str]:
        calls.append(symbol)
        return {"longName": f"{symbol} Long", "shortName": f"{symbol} Short"}

    cache = tmp_path / "yf_names.parquet"  # type: ignore[operator]
    first = identity.fetch_symbol_names(["AAPL", "CPWR"], cache, fetcher=fake_fetcher)
    assert calls == ["AAPL", "CPWR"]
    assert list(first["long_name"]) == ["AAPL Long", "CPWR Long"]

    # second call reads the cache and hits the network zero times
    second = identity.fetch_symbol_names(["AAPL", "CPWR"], cache, fetcher=fake_fetcher)
    assert calls == ["AAPL", "CPWR"]
    assert list(second["long_name"]) == ["AAPL Long", "CPWR Long"]

    # a new symbol is fetched, the cached ones are not
    identity.fetch_symbol_names(["AAPL", "MSFT"], cache, fetcher=fake_fetcher)
    assert calls == ["AAPL", "CPWR", "MSFT"]


def test_fetch_symbol_names_survives_a_failed_lookup(
    tmp_path: pytest.TempPathFactory,
) -> None:
    def flaky_fetcher(symbol: str) -> dict[str, str]:
        if symbol == "BAD":
            raise RuntimeError("no data")
        return {"longName": "Fine Inc", "shortName": "Fine"}

    cache = tmp_path / "yf_names.parquet"  # type: ignore[operator]
    frame = identity.fetch_symbol_names(["AAPL", "BAD"], cache, fetcher=flaky_fetcher)
    assert set(frame["ticker"]) == {"AAPL", "BAD"}
    assert pd.isna(frame.loc[frame["ticker"] == "BAD", "long_name"]).all()


def test_exclusions_split_drops_from_truncations() -> None:
    table = pd.DataFrame(
        {
            "ticker": ["CPWR", "EP", "MI", "POM", "XYZ"],
            "action": ["drop", "drop", "drop", "drop", "truncate"],
            "drop_before": [None, None, None, None, pd.Timestamp("2020-01-02")],
        }
    )
    dropped, truncated = identity.exclusions(table)
    assert dropped == ["CPWR", "EP", "MI", "POM"]
    assert truncated == {"XYZ": pd.Timestamp("2020-01-02")}
