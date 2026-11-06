"""The additive refresh adds rows for new names and never changes existing ones."""

from __future__ import annotations

import pandas as pd

from efb import universe
from live import evening_job


def _sectors(tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": tickers,
            "gics_sector": ["Information Technology"] * len(tickers),
            "gics_sub_industry": ["Software"] * len(tickers),
            "source": ["wikipedia"] * len(tickers),
            "as_of": [pd.Timestamp("2026-09-11")] * len(tickers),
        }
    )


def _snapshot(symbols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": symbols,
            "security": [f"Security {symbol}" for symbol in symbols],
            "gics_sector": ["Financials"] * len(symbols),
            "gics_sub_industry": ["Banks"] * len(symbols),
        }
    )


def test_adds_a_row_for_a_name_the_snapshot_knows_but_the_table_does_not() -> None:
    current = _sectors(["AAPL", "MSFT"])
    snapshot = _snapshot(["AAPL", "MSFT", "OKTA"])
    combined, added = universe.additive_sector_refresh(current, snapshot, "2026-11-04")
    assert added == ["OKTA"]
    assert set(combined["ticker"]) == {"AAPL", "MSFT", "OKTA"}


def test_existing_rows_are_unchanged_and_none_are_removed() -> None:
    current = _sectors(["AAPL", "MSFT", "BLDR"])
    snapshot = _snapshot(["AAPL", "OKTA"])  # BLDR left the index
    combined, added = universe.additive_sector_refresh(current, snapshot, "2026-11-04")
    assert added == ["OKTA"]
    # BLDR is not removed even though the snapshot no longer lists it.
    assert "BLDR" in set(combined["ticker"])
    aapl = combined.loc[combined["ticker"] == "AAPL"].iloc[0]
    assert aapl["gics_sector"] == "Information Technology"
    assert str(aapl["as_of"].date()) == "2026-09-11"


def test_a_snapshot_with_no_new_names_is_a_no_op() -> None:
    current = _sectors(["AAPL", "MSFT"])
    snapshot = _snapshot(["AAPL", "MSFT"])
    combined, added = universe.additive_sector_refresh(current, snapshot, "2026-11-04")
    assert added == []
    assert combined.equals(current)


def test_still_without_gics_names_only_those_without_a_row() -> None:
    sectors = _sectors(["AAPL"])
    assert evening_job.still_without_gics(["OKTA", "AAPL"], sectors) == ["OKTA"]


def test_refresh_reads_writes_and_reports_added(tmp_path) -> None:
    root = tmp_path
    (root / "processed").mkdir(parents=True)
    (root / "raw" / "wikipedia_constituents").mkdir(parents=True)
    _sectors(["AAPL"]).to_parquet(root / "processed" / "sectors.parquet", index=False)
    _snapshot(["AAPL", "OKTA"]).to_parquet(
        root
        / "raw"
        / "wikipedia_constituents"
        / "wikipedia_constituents_2026-11-04.parquet",
        index=False,
    )
    combined, added = evening_job.refresh_sectors_additive(root, as_of="2026-11-04")
    assert added == ["OKTA"]
    on_disk = pd.read_parquet(root / "processed" / "sectors.parquet")
    assert "OKTA" in set(on_disk["ticker"])


def test_refresh_with_no_snapshot_is_a_no_op(tmp_path) -> None:
    root = tmp_path
    (root / "processed").mkdir(parents=True)
    _sectors(["AAPL"]).to_parquet(root / "processed" / "sectors.parquet", index=False)
    combined, added = evening_job.refresh_sectors_additive(root, as_of="2026-11-04")
    assert added == []
    assert set(combined["ticker"]) == {"AAPL"}


def test_held_names_do_not_gain_a_row_before_their_release_date() -> None:
    current = _sectors(["AAPL"])
    snapshot = _snapshot(["AAPL", "BE", "SKYD"])
    combined, added = universe.additive_sector_refresh(
        current, snapshot, "2026-11-04", holds=universe.SECTOR_HOLDS
    )
    # BE is parked until 2026-11-24; SKYD is not held and gains a row.
    assert added == ["SKYD"]
    assert "BE" not in set(combined["ticker"])


def test_held_names_gain_a_row_on_or_after_their_release_date() -> None:
    current = _sectors(["AAPL"])
    snapshot = _snapshot(["AAPL", "BE"])
    combined, added = universe.additive_sector_refresh(
        current, snapshot, "2026-11-24", holds=universe.SECTOR_HOLDS
    )
    assert added == ["BE"]
    assert "BE" in set(combined["ticker"])


def test_the_hold_list_names_exactly_the_parked_tickers() -> None:
    assert set(universe.SECTOR_HOLDS) == {"BE", "ILMN", "P"}
    assert universe.SECTOR_HOLDS["BE"] == "2026-11-24"
    assert universe.SECTOR_HOLDS["ILMN"] == "2026-11-24"
    assert universe.SECTOR_HOLDS["P"] == "2026-11-24"
