"""Task 0 (Sprint E3) tests: probe helpers plus the E1 reference values.

Everything except the two marked integration tests runs offline on
fixtures, so the parsing and the availability rules are pinned without a
network call. The rules tested here are the ones the descriptors depend
on, so a change in a window is a test failure rather than a silent
coverage shift.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import evaluate, probes
from efb.probes import (
    MOMENTUM_MIN_OBS,
    MOMENTUM_SKIP,
    SHARES_CACHE,
    availability_masks,
    coverage_table,
    dedupe_share_history,
    fetch_share_history,
    first_full_row_day,
    members_outside_sector_file,
    sector_members,
    share_count_panel,
)

ROOT = Path(__file__).resolve().parents[1]

N_DAYS = 300
TICKERS = ("AAA", "BBB", "CCC")


def _panel(
    n_days: int = N_DAYS, tickers: tuple[str, ...] = TICKERS
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.DataFrame]:
    idx = pd.bdate_range("2019-01-01", periods=n_days)
    rng = np.random.default_rng(7)
    returns = pd.DataFrame(
        rng.normal(0.0004, 0.01, (n_days, len(tickers))),
        index=idx,
        columns=list(tickers),
    )
    market = returns.mean(axis=1)
    volume = pd.DataFrame(1e6, index=idx, columns=list(tickers))
    close = pd.DataFrame(50.0, index=idx, columns=list(tickers))
    return returns, market, volume, close


def _shares_wide(
    idx: pd.DatetimeIndex, tickers: tuple[str, ...] = TICKERS
) -> pd.DataFrame:
    return pd.DataFrame(1e8, index=idx, columns=list(tickers))


def _masks(**overrides: object) -> dict[str, pd.DataFrame]:
    returns, market, volume, close = _panel()
    shares = _shares_wide(returns.index)
    sectors = pd.Series({t: "Industrials" for t in TICKERS})
    kwargs = dict(
        returns=returns,
        market=market,
        volume=volume,
        close=close,
        shares=shares,
        sectors=sectors,
    )
    kwargs.update(overrides)
    return availability_masks(**kwargs)  # type: ignore[arg-type]


def test_all_descriptors_available_on_a_full_fixture() -> None:
    masks = _masks()
    last = masks["full"].index[-1]
    assert bool(masks["full"].loc[last].all())
    assert set(masks) == {
        "market",
        "size",
        "beta",
        "momentum",
        "reversal",
        "resid_vol",
        "liquidity",
        "sector",
        "full",
    }


def test_full_row_needs_every_descriptor() -> None:
    returns, market, volume, close = _panel()
    volume.iloc[-63:, volume.columns.get_loc("CCC")] = np.nan
    masks = availability_masks(
        returns=returns,
        market=market,
        volume=volume,
        close=close,
        shares=_shares_wide(returns.index),
        sectors=pd.Series({t: "Industrials" for t in TICKERS}),
    )
    last = masks["full"].index[-1]
    assert int(masks["full"].loc[last].sum()) == 2
    assert not bool(masks["liquidity"].loc[last, "CCC"])
    assert bool(masks["liquidity"].loc[last, "AAA"])


def test_momentum_needs_231_of_252_but_reversal_does_not() -> None:
    returns, market, volume, close = _panel()
    n = len(returns)
    momentum_window = returns.iloc[n - 252 : n - 21]
    returns.iloc[n - 252 : n - 230, returns.columns.get_loc("BBB")] = (
        np.nan
    )  # 22 gaps inside the 12-1 window
    assert len(momentum_window) == 231
    masks = availability_masks(
        returns=returns,
        market=market,
        volume=volume,
        close=close,
        shares=_shares_wide(returns.index),
        sectors=pd.Series({t: "Industrials" for t in TICKERS}),
    )
    last = masks["full"].index[-1]
    assert not bool(masks["momentum"].loc[last, "BBB"])
    assert bool(masks["reversal"].loc[last, "BBB"])


def test_beta_needs_126_observations() -> None:
    returns, market, volume, close = _panel()
    returns.iloc[:270, returns.columns.get_loc("CCC")] = np.nan
    masks = availability_masks(
        returns=returns,
        market=market,
        volume=volume,
        close=close,
        shares=_shares_wide(returns.index),
        sectors=pd.Series({t: "Industrials" for t in TICKERS}),
    )
    last = masks["full"].index[-1]
    assert not bool(masks["beta"].loc[last, "CCC"])
    assert bool(masks["beta"].loc[last, "AAA"])


def test_resid_vol_needs_all_63_residual_days() -> None:
    returns, market, volume, close = _panel()
    # The descriptor on date t reads data through t-1, so the gap has to sit
    # inside the 63 sessions ending the day before, not on the date itself.
    returns.iloc[-2, returns.columns.get_loc("BBB")] = np.nan
    masks = availability_masks(
        returns=returns,
        market=market,
        volume=volume,
        close=close,
        shares=_shares_wide(returns.index),
        sectors=pd.Series({t: "Industrials" for t in TICKERS}),
    )
    last = masks["full"].index[-1]
    assert not bool(masks["resid_vol"].loc[last, "BBB"])
    assert bool(masks["resid_vol"].loc[last, "AAA"])
    assert bool(masks["reversal"].loc[last, "BBB"])


def test_sector_availability_is_membership_of_the_sector_file() -> None:
    masks = _masks(sectors=pd.Series({"AAA": "Industrials", "BBB": "Energy"}))
    last = masks["full"].index[-1]
    assert bool(masks["sector"].loc[last, "AAA"])
    assert not bool(masks["sector"].loc[last, "CCC"])
    assert int(masks["full"].loc[last].sum()) == 2


def test_coverage_table_aggregates_to_year_ends() -> None:
    masks = _masks()
    table = coverage_table(masks, by="year")
    assert list(table.columns[:3]) == ["year", "date", "n_names"]
    assert set(TICKERS).issubset(set(masks["full"].columns))
    assert table["full"].iloc[-1] == 3
    assert table["sector"].iloc[-1] == 3
    assert str(table["date"].iloc[-1]) == str(masks["full"].index[-1].date())


def test_coverage_table_counts_only_names_with_a_return() -> None:
    """A descriptor is not available on a day the name did not trade."""
    returns, market, volume, close = _panel()
    returns.iloc[-1, returns.columns.get_loc("CCC")] = np.nan
    masks = availability_masks(
        returns=returns,
        market=market,
        volume=volume,
        close=close,
        shares=_shares_wide(returns.index),
        sectors=pd.Series({t: "Industrials" for t in TICKERS}),
    )
    table = coverage_table(masks, by="year")
    last = table.iloc[-1]
    assert last["n_names"] == 2
    assert last["size"] == 2
    assert last["liquidity"] == 2
    assert last["full"] == 2


def test_shares_ramp_counts_only_names_with_a_real_count() -> None:
    idx = pd.bdate_range("2020-01-01", periods=60)
    history = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "date": pd.to_datetime(["2020-01-02", "2020-03-02"]),
            "shares": [100.0, 200.0],
            "status": ["ok", "ok"],
        }
    )
    panel = share_count_panel(history, idx, ["AAA", "BBB"])
    shares = panel.pivot(index="date", columns="ticker", values="shares")
    look_ahead = panel.pivot(index="date", columns="ticker", values="look_ahead")
    ramp = probes.shares_coverage_ramp(shares, look_ahead)
    assert int(ramp.loc[ramp.index == "2020-01"].iloc[0]) == 1
    assert int(ramp.loc[ramp.index == "2020-02"].iloc[0]) == 1
    assert int(ramp.loc[ramp.index == "2020-03"].iloc[0]) == 2


def test_first_full_row_day_requires_the_threshold() -> None:
    masks = _masks()
    day = first_full_row_day(masks, min_names=3)
    assert day is not None
    position = masks["full"].index.get_loc(day)
    # Momentum is the last descriptor to fill: 231 observations ending at
    # t-21 means the 251st session is the first complete one.
    assert position == MOMENTUM_MIN_OBS + MOMENTUM_SKIP - 1
    assert int(masks["full"].iloc[position].sum()) == 3
    assert int(masks["full"].iloc[position - 1].sum()) == 0
    assert first_full_row_day(masks, min_names=4) is None


def test_share_count_panel_uses_the_last_filing_on_or_before_t_minus_1() -> None:
    idx = pd.bdate_range("2020-01-01", periods=90)
    history = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA", "AAA"],
            "date": pd.to_datetime(["2020-01-31", "2020-02-28", "2020-03-31"]),
            "shares": [100.0, 200.0, 300.0],
        }
    )
    panel = share_count_panel(history, idx, ["AAA"])
    as_of = panel.set_index(["date", "ticker"])
    # On 2020-02-28 the count filed that day is not yet usable: the value
    # is the 2020-01-31 filing.
    on_second = as_of.loc[(pd.Timestamp("2020-02-28"), "AAA")]
    assert on_second["shares"] == 100.0
    assert on_second["shares_as_of"] == pd.Timestamp("2020-01-31")
    # The next session sees the 2020-02-28 filing.
    after = as_of.loc[(pd.Timestamp("2020-03-02"), "AAA")]
    assert after["shares"] == 200.0
    assert after["shares_as_of"] == pd.Timestamp("2020-02-28")
    # Later filings are never read early.
    assert as_of.loc[(pd.Timestamp("2020-03-30"), "AAA")]["shares"] == 200.0


def test_share_count_panel_backfills_the_first_filing_and_flags_look_ahead() -> None:
    idx = pd.bdate_range("2020-01-01", periods=60)
    history = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA"],
            "date": pd.to_datetime(["2020-02-28", "2020-03-31"]),
            "shares": [200.0, 300.0],
        }
    )
    panel = share_count_panel(history, idx, ["AAA"]).set_index(["date", "ticker"])
    early = panel.loc[(pd.Timestamp("2020-01-15"), "AAA")]
    assert early["shares"] == 200.0
    assert bool(early["look_ahead"]) is True
    assert early["shares_as_of"] is None or pd.isna(early["shares_as_of"])
    on_filing = panel.loc[(pd.Timestamp("2020-03-02"), "AAA")]
    assert bool(on_filing["look_ahead"]) is False
    assert on_filing["shares"] == 200.0


def test_share_count_panel_ignores_rows_without_a_date() -> None:
    idx = pd.bdate_range("2020-01-01", periods=5)
    history = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "date": [pd.Timestamp("2020-01-02"), pd.NaT],
            "shares": [100.0, np.nan],
            "status": ["ok", "empty"],
        }
    )
    panel = share_count_panel(history, idx, ["AAA", "BBB"])
    wide = panel.pivot(index="date", columns="ticker", values="shares")
    assert wide["AAA"].notna().all()
    assert wide["BBB"].isna().all()


def test_dedupe_share_history_keeps_the_largest_and_counts_split_steps() -> None:
    raw = pd.DataFrame(
        {
            "ticker": ["AAA"] * 4,
            "date": pd.to_datetime(
                ["2020-08-28", "2020-08-31", "2020-08-31", "2020-09-30"]
            ),
            "shares": [100.0, 400.0, 100.0, 398.0],
        }
    )
    clean, deduped, splits = dedupe_share_history(raw)
    assert deduped == 1
    assert splits == 1
    assert len(clean) == 3
    row = clean.loc[clean["date"] == pd.Timestamp("2020-08-31"), "shares"]
    assert row.iloc[0] == 400.0
    assert clean["shares"].tolist() == [100.0, 400.0, 398.0]


def test_members_outside_sector_file_counts_and_share() -> None:
    idx = pd.bdate_range("2020-01-01", periods=4)
    membership = pd.DataFrame(True, index=idx, columns=["AAA", "BBB", "CCC", "DDD"])
    table = members_outside_sector_file(membership, {"AAA", "BBB"})
    first = table.iloc[0]
    assert first["year"] == 2020
    assert first["n_members_mean"] == 4
    assert first["n_mapped_mean"] == 2
    assert first["n_outside_mean"] == 2
    assert first["n_outside_distinct"] == 2
    assert first["share_outside"] == pytest.approx(0.5)


def test_members_outside_sector_file_respects_point_in_time_dates() -> None:
    idx = pd.bdate_range("2020-01-01", periods=4)
    membership = pd.DataFrame(False, index=idx, columns=["AAA", "BBB"])
    membership["AAA"] = True
    membership.loc[idx[2] :, "BBB"] = True
    table = members_outside_sector_file(membership, {"AAA"})
    row = table.iloc[0]
    # 1, 1, 2, 2 members over the four days, with AAA always mapped.
    assert row["n_members_mean"] == pytest.approx(1.5)
    assert row["n_mapped_mean"] == pytest.approx(1.0)
    assert row["n_outside_mean"] == pytest.approx(0.5)
    assert row["n_outside_distinct"] == 1
    assert row["share_outside"] == pytest.approx(2 / 6)


def test_members_outside_sector_file_can_weight_by_market_cap() -> None:
    """The name share and the cap share answer different questions."""
    idx = pd.bdate_range("2020-01-01", periods=3)
    membership = pd.DataFrame(True, index=idx, columns=["AAA", "BBB"])
    market_cap = pd.DataFrame({"AAA": 90.0, "BBB": 10.0}, index=idx)
    table = members_outside_sector_file(membership, {"AAA"}, market_cap=market_cap)
    row = table.iloc[0]
    assert row["share_outside"] == pytest.approx(0.5)
    assert row["share_outside_mcap"] == pytest.approx(0.1)


def test_sector_members_counts_names_per_sector_per_day() -> None:
    idx = pd.bdate_range("2020-01-01", periods=3)
    universe = pd.DataFrame(
        np.ones((3, 4)), index=idx, columns=["AAA", "BBB", "CCC", "DDD"]
    )
    sectors = pd.Series(
        {
            "AAA": "Energy",
            "BBB": "Energy",
            "CCC": "Energy",
            "DDD": "Utilities",
        }
    )
    counts = sector_members(universe, sectors)
    assert counts.loc[idx[0], "Energy"] == 3
    assert counts.loc[idx[0], "Utilities"] == 1
    small = probes.small_sector_days(counts, min_members=5)
    assert small == len(idx)
    large = probes.small_sector_days(
        pd.DataFrame({"Energy": [5, 5, 1]}, index=idx), min_members=5
    )
    assert large == 1


def test_fetch_share_history_caches_and_does_not_refetch(tmp_path: Path) -> None:
    calls: list[str] = []

    def fetcher(symbol: str) -> pd.Series:
        calls.append(symbol)
        return pd.Series(
            [100.0, 110.0], index=pd.to_datetime(["2020-01-31", "2020-02-28"])
        )

    cache = tmp_path / "shares_history.parquet"
    first = fetch_share_history(["AAA", "BBB"], cache_path=cache, fetcher=fetcher)
    assert len(calls) == 2
    assert set(first["ticker"]) == {"AAA", "BBB"}
    second = fetch_share_history(["AAA", "BBB"], cache_path=cache, fetcher=fetcher)
    assert len(calls) == 2, "a cached ticker must not be asked twice"
    assert len(second) == len(first)


def test_fetch_share_history_records_an_empty_answer_as_a_marker(
    tmp_path: Path,
) -> None:
    def fetcher(symbol: str) -> pd.Series | None:
        return (
            None
            if symbol == "AAA"
            else pd.Series([1.0], index=pd.to_datetime(["2020-01-31"]))
        )

    cache = tmp_path / "shares_history.parquet"
    frame = fetch_share_history(["AAA", "BBB"], cache_path=cache, fetcher=fetcher)
    marker = frame.loc[frame["ticker"] == "AAA"].iloc[0]
    assert marker["status"] == "empty"
    assert pd.isna(marker["date"])
    assert (frame["status"] == "ok").sum() == 1


def test_fetch_share_history_records_a_failure_and_retries(tmp_path: Path) -> None:
    attempts: list[str] = []

    def fetcher(symbol: str) -> pd.Series:
        attempts.append(symbol)
        if len(attempts) < 3:
            raise RuntimeError("vendor timeout")
        return pd.Series([1.0], index=pd.to_datetime(["2020-01-31"]))

    cache = tmp_path / "shares_history.parquet"
    frame = fetch_share_history(["AAA"], cache_path=cache, fetcher=fetcher, attempts=3)
    assert len(attempts) == 3
    assert (frame["status"] == "ok").sum() == 1


def test_fetch_share_history_normalizes_vendor_offsets(tmp_path: Path) -> None:
    """A market-time timestamp must not survive into the cache as an offset."""
    # New York market time, with the offset changing between the two rows.
    market_time = pd.to_datetime(
        ["2020-01-31 00:00:00", "2020-06-01 00:00:00"]
    ).tz_localize("America/New_York")
    assert str(market_time[0]) != str(market_time[1])

    def fetcher(symbol: str) -> pd.Series:
        return pd.Series([100.0, 110.0], index=market_time)

    cache = tmp_path / "shares_history.parquet"
    frame = fetch_share_history(["AAA"], cache_path=cache, fetcher=fetcher)
    dates = pd.to_datetime(frame["date"])
    assert not isinstance(dates.dtype, pd.DatetimeTZDtype)
    assert dates.tolist() == [pd.Timestamp("2020-01-31"), pd.Timestamp("2020-06-01")]
    # A second call over the same cache must not raise on mixed offsets.
    again = fetch_share_history(["AAA"], cache_path=cache, fetcher=fetcher)
    assert len(again) == len(frame)


def test_shares_cache_path_is_the_data_raw_artifact() -> None:
    assert SHARES_CACHE == ROOT / "data" / "raw" / "shares_history.parquet"


def test_write_results_stores_and_preserves_reference_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "RESULTS.json"
    criteria = {
        "F9.9": {
            "criterion": "text",
            "threshold": "t",
            "stored_number": 1.0,
            "verdict": "pass",
            "note": "n",
        }
    }
    refs = {"sharpe_annualized": 0.76, "ratio_lo_over_iid": 0.922}
    evaluate.write_results(
        criteria, path, sprint="E1", data_hash="abc", reference_values=refs
    )
    stored = json.loads(path.read_text())
    assert stored["reference_values"] == refs
    # A writer that does not know about the block must not erase it.
    evaluate.write_results(criteria, path, sprint="E1", data_hash="abc")
    assert json.loads(path.read_text())["reference_values"] == refs
    # And an explicit new block replaces it.
    evaluate.write_results(
        criteria,
        path,
        sprint="E1",
        data_hash="abc",
        reference_values={"sharpe_annualized": 0.75},
    )
    assert json.loads(path.read_text())["reference_values"] == {
        "sharpe_annualized": 0.75
    }


def test_write_results_does_not_duplicate_history_when_only_refs_change(
    tmp_path: Path,
) -> None:
    path = tmp_path / "RESULTS.json"
    criteria = {
        "F9.9": {
            "criterion": "text",
            "threshold": "t",
            "stored_number": 1.0,
            "verdict": "pass",
            "note": "n",
        }
    }
    evaluate.write_results(
        criteria, path, sprint="E1", data_hash="abc", reference_values={"a": 1}
    )
    evaluate.write_results(
        criteria, path, sprint="E1", data_hash="abc", reference_values={"a": 2}
    )
    stored = json.loads(path.read_text())
    assert len(stored["revisions"]["history"]) == 1
    assert stored["revisions"]["n_changed"] == 0


@pytest.mark.integration
def test_e1_reference_values_recompute_from_the_artifacts() -> None:
    """The stored block must equal a fresh computation from the parquet."""
    results = json.loads((ROOT / "sprints" / "E1" / "RESULTS.json").read_text())
    stored = results["reference_values"]
    fresh = evaluate.e1_reference_values(ROOT / "data")
    assert set(stored) == set(fresh), "the reference block keys changed"
    for key, value in fresh.items():
        if isinstance(value, float):
            assert stored[key] == pytest.approx(value, rel=1e-12), key
        else:
            assert stored[key] == value, key
    assert stored["sharpe_annualized"] == pytest.approx(0.7601, abs=5e-5)
    assert stored["se_lo2002_annualized"] < stored["se_iid_annualized"]
    assert stored["lag1_autocorrelation_ff_market"] < 0


@pytest.mark.integration
def test_e1_walkthrough_asserts_against_the_stored_reference_block() -> None:
    notebook_path = ROOT / "notebooks" / "E1_walkthrough.ipynb"
    notebook = json.loads(notebook_path.read_text())
    source = "\n".join(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )
    printed = "\n".join(
        "".join(output.get("text", []))
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
        for output in cell.get("outputs", [])
    )
    assert "reference_values" in source
    assert "RESULTS.json" in source
    # No reference value may be typed into a code cell: they come from the
    # results file, which is what makes the notebook survive a correction.
    for literal in ("0.7601", "0.9220", "0.2460", "0.2268", "0.1029"):
        assert literal not in source, f"{literal} is hardcoded in the notebook"
    stored = json.loads((ROOT / "sprints" / "E1" / "RESULTS.json").read_text())[
        "reference_values"
    ]
    assert f"{stored['sharpe_annualized']:.4f}" in printed
    assert f"{stored['se_lo2002_annualized']:.4f}" in printed
    assert f"{stored['ratio_lo_over_iid']:.4f}" in printed
