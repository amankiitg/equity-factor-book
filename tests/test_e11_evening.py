"""Sprint E11, Task 1 to Task 3: the evening proposal job.

The tests pin the three things the evening job must never get wrong: the
universe is the SPY archive and asserted as such, the proposal carries the
idio share after the FMP hedge, and a null book that cannot reach the E10
vol target inside the gross cap is capped rather than leveraged past it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from live import evening_job as ev


def _write_spy_archive(data_root: Path, as_of: str, tickers: list[str]) -> Path:
    """Write one fake dated SPY holdings file with the columns the loader reads."""
    out_dir = data_root / "raw" / "spy_holdings"
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "ticker": tickers,
            "name": tickers,
            "identifier": [f"CUSIP{i:04d}" for i in range(len(tickers))],
            "sedol": [f"SEDOL{i:04d}" for i in range(len(tickers))],
            "weight": [1.0 / len(tickers)] * len(tickers),
            "sector": ["Information Technology"] * len(tickers),
            "shares held": [1] * len(tickers),
            "local currency": ["USD"] * len(tickers),
            "as_of": [as_of] * len(tickers),
        }
    )
    stamp = pd.to_datetime(as_of).strftime("%Y-%m-%d")
    path = out_dir / f"spy_holdings_{stamp}.parquet"
    frame.to_parquet(path, index=False)
    return path


def test_load_spy_universe_uses_the_latest_archive(tmp_path: Path) -> None:
    _write_spy_archive(tmp_path, "2026-09-17", ["AAA", "BBB"])
    _write_spy_archive(tmp_path, "2026-09-18", ["AAA", "CCC"])
    frame, path = ev.load_spy_universe(tmp_path)
    assert path.name == "spy_holdings_2026-09-18.parquet"
    assert sorted(frame["ticker"]) == ["AAA", "CCC"]


def test_load_spy_universe_rejects_an_archive_before_the_seam(tmp_path: Path) -> None:
    _write_spy_archive(tmp_path, "2026-09-17", ["AAA"])
    with pytest.raises(ValueError, match="before the live universe seam"):
        ev.load_spy_universe(tmp_path)


def test_load_spy_universe_fails_without_any_archive(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no SPY archive files"):
        ev.load_spy_universe(tmp_path)


def test_stored_ic_reads_the_summary_row(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame({"signal": ["idio_momentum"], "ic_h1_mean": [0.012102]})
    summary.to_parquet(tmp_path / "alpha" / "summary.parquet", index=False)
    assert ev._stored_ic("idio_momentum", tmp_path) == pytest.approx(0.012102)


def test_decomposition_reports_exposure_gross_and_net() -> None:
    design = np.ones((4, 1))  # market column only
    factor_covariance = np.eye(1)
    specific = np.full(4, 0.01)
    weights = np.array([0.25, -0.25, 0.25, -0.25])
    result = ev._decomposition(weights, design, factor_covariance, specific)
    assert result["gross"] == pytest.approx(1.0)
    assert result["net"] == pytest.approx(0.0)
    assert result["max_abs_exposure"] == pytest.approx(0.0)
    assert result["n_eff"] == pytest.approx(4.0)
    assert result["idio_share"] == pytest.approx(1.0)


@pytest.mark.slow
def test_build_proposal_asserts_the_spy_universe_and_stores_idio_share() -> None:
    manifest = ev.build_proposal(store=False)
    # the universe is the SPY archive, asserted in the manifest
    assert manifest["universe_source"].startswith("raw/spy_holdings/")
    assert manifest["universe_as_of"] >= "2026-09-18"
    # the null book is factor-neutral after the exact FMP hedge
    assert manifest["idio_share_after_fmp"] == pytest.approx(1.0, abs=1e-9)
    assert manifest["max_abs_exposure_after_fmp"] < 1e-9
    # the E8 constraint set holds: gross within cap, net zero
    assert manifest["gross"] <= 1.0 + 1e-9
    assert abs(manifest["net"]) < 1e-9
    # the SPY names the frozen model does not know are excluded, not imputed
    assert manifest["n_excluded"] >= 1
    assert manifest["n_names"] + manifest["n_excluded"] >= 490


@pytest.mark.slow
def test_build_proposal_respects_the_vol_target_and_gross_cap() -> None:
    manifest = ev.build_proposal(store=False)
    assert manifest["gross"] <= 1.0 + 1e-9
    assert manifest["achieved_annual_vol"] <= manifest["target_annual_vol"] + 1e-9
    if manifest["gross_cap_bound"]:
        assert manifest["gross"] == pytest.approx(1.0)
    else:
        assert manifest["achieved_annual_vol"] == pytest.approx(
            manifest["target_annual_vol"], abs=1e-9
        )


@pytest.mark.slow
def test_build_proposal_stores_nav_beside_the_cost() -> None:
    manifest = ev.build_proposal(store=False)
    assert manifest["nav"] == pytest.approx(ev.PAPER_NAV)
    breakdown = manifest["cost_breakdown_bps"]
    total = (
        breakdown["spread"]
        + breakdown["impact"]
        + breakdown["commission"]
        + breakdown["borrow"]
    )
    assert breakdown["total"] == pytest.approx(total)
    assert manifest["expected_establishment_cost_bps"] == pytest.approx(
        breakdown["total"]
    )
    assert manifest["expected_establishment_cost_usd"] == pytest.approx(
        breakdown["total"] / 1e4 * manifest["nav"]
    )
    assert manifest["notional"] > 0
    assert manifest["avg_trade_size"] > 0
    # E11-F2: the average trade size divides by the names that actually trade,
    # not the full list, so a dropped tail cannot understate the average.
    assert manifest["avg_trade_size"] == pytest.approx(
        manifest["notional"] / manifest["n_effective"]
    )


def test_build_proposal_rejects_a_null_nav() -> None:
    with pytest.raises(ValueError, match="null"):
        ev.build_proposal(nav=None, store=False)


def test_shares_as_of_is_clamped_to_the_close() -> None:
    # A count filed the day after the close it prices is look-ahead, so the
    # reported as-of is the latest count on or before the close, never the
    # global maximum.
    shares = pd.DataFrame({"date": ["2026-09-21", "2026-09-22"], "shares": [1, 2]})
    assert ev._shares_as_of(shares, pd.Timestamp("2026-09-21")) == pd.Timestamp(
        "2026-09-21"
    )
    assert ev._shares_as_of(shares, pd.Timestamp("2026-09-22")) == pd.Timestamp(
        "2026-09-22"
    )


def test_shares_as_of_fails_without_a_count_on_or_before_the_close() -> None:
    shares = pd.DataFrame({"date": ["2026-09-22"], "shares": [1]})
    with pytest.raises(ValueError, match="no share count on or before"):
        ev._shares_as_of(shares, pd.Timestamp("2026-09-21"))


def test_below_floor_checks_the_share_leg_on_final_shares() -> None:
    shares = np.array([20, 19, 5, 40])
    prices = np.array([100.0, 100.0, 100.0, 100.0])
    below = ev.below_floor(shares, prices, dollar_floor=0.0, share_floor=20)
    assert below.tolist() == [False, True, True, False]


def test_below_floor_checks_the_dollar_leg_on_final_notional() -> None:
    shares = np.array([20, 19, 15, 40])
    prices = np.array([100.0, 100.0, 100.0, 100.0])
    below = ev.below_floor(shares, prices, dollar_floor=2000.0, share_floor=0)
    # notional: 2000, 1900, 1500, 4000 -> only the last clears
    assert below.tolist() == [False, True, True, False]


def test_below_floor_requires_both_legs_when_both_are_set() -> None:
    shares = np.array([20, 19, 20, 30])
    prices = np.array([100.0, 100.0, 50.0, 50.0])
    below = ev.below_floor(shares, prices, dollar_floor=2000.0, share_floor=20)
    # notional 2000/1900/1000/1500 and shares 20/19/20/30: all but the first fail
    assert below.tolist() == [False, True, True, True]


def test_floor_shortfalls_reports_the_worst_of_each_leg() -> None:
    shares = np.array([20, 5, 19, 40])
    prices = np.array([100.0, 100.0, 50.0, 50.0])
    short_shares, short_dollars = ev.floor_shortfalls(
        shares, prices, dollar_floor=2000.0, share_floor=20
    )
    assert short_shares == pytest.approx(15.0)  # the 5-share name is 15 short
    # dollar shortfalls: 5*100=500 (1500 short), 19*50=950 (1050 short); 20-share
    # name at 100 clears dollars; so the worst dollar shortfall is 1500
    assert short_dollars == pytest.approx(1500.0)


def test_floor_thresholds_take_the_larger_of_the_two_legs() -> None:
    close = {"A": 100.0, "B": 10.0}
    thresholds = ev.floor_thresholds(close, ["A", "B"], 1500.0, 20)
    # A needs 20 shares at $100 = $2,000, which binds over the $1,500 leg;
    # B needs 20 shares at $10 = $200, so the dollar leg binds
    assert thresholds.tolist() == [2000.0, 1500.0]


def test_the_prefix_scan_takes_the_largest_passing_prefix(monkeypatch) -> None:
    """The pass set is not monotone in k, so the scan is linear, not a bisection.

    Only a three-name book clears the floor here. A bisection would probe k=2
    first, find it failing, and search downward, never reaching k=3.
    """
    names = ["A", "B", "C", "D"]
    full = np.array([4.0, 3.0, 2.0, 1.0])
    close = {ticker: 10.0 for ticker in names}
    calls: list[int] = []

    def fake_finalize(keep, *args, **kwargs):
        idx = np.where(keep)[0]
        calls.append(len(idx))
        shares = np.full(len(idx), 20 if len(idx) == 3 else 19, dtype=int)
        return {
            "idx": idx,
            "names_sub": [names[i] for i in idx],
            "shares": shares,
            "prices": np.full(len(idx), 10.0),
        }

    monkeypatch.setattr(ev, "finalize_kept_set", fake_finalize)
    keep, _finalize, k = ev.enforce_floor_by_prefix(
        names,
        np.ones(4),
        np.zeros((4, 1)),
        np.eye(1),
        np.ones(4),
        close,
        1000.0,
        full,
        0.0,
        20,
    )
    assert k == 3
    assert keep.tolist() == [True, True, True, False]
    # descending from the full book, so exactly two probes: the full book, then 3
    assert calls == [4, 3]


def test_the_prefix_scan_fails_loudly_when_no_prefix_clears(monkeypatch) -> None:
    names = ["A", "B"]
    monkeypatch.setattr(
        ev,
        "finalize_kept_set",
        lambda keep, *args, **kwargs: {
            "idx": np.where(keep)[0],
            "names_sub": [t for t, k in zip(names, keep, strict=True) if k],
            "shares": np.zeros(int(np.sum(keep)), dtype=int),
            "prices": np.full(int(np.sum(keep)), 10.0),
        },
    )
    with pytest.raises(ValueError, match="no prefix"):
        ev.enforce_floor_by_prefix(
            names,
            np.ones(2),
            np.zeros((2, 1)),
            np.eye(1),
            np.ones(2),
            {t: 10.0 for t in names},
            1000.0,
            np.array([2.0, 1.0]),
            0.0,
            20,
        )


@pytest.mark.slow
def test_build_proposal_stores_the_share_only_floor_and_breadth() -> None:
    manifest = ev.build_proposal(store=False)
    # the chosen construction: min 20 shares, no dollar floor, enforced on the
    # final weights (E11-F12)
    assert manifest["min_position_dollars"] == pytest.approx(0.0)
    assert manifest["min_position_pct_of_nav"] == pytest.approx(0.0)
    # names whose final position is below 20 shares are dropped
    assert manifest["n_kept"] + manifest["n_dropped"] == manifest["n_names"]
    assert manifest["n_kept"] < manifest["n_names"]
    assert manifest["n_dropped"] > 0
    # both breadth measures are recorded: the naive N-bound and the governing
    # n_eff-bound, which uses the E8 effective-breadth construction
    assert manifest["breadth_naive_bound"] >= 1.0
    assert manifest["breadth_governing"] >= 1.0
    assert manifest["n_eff_full"] == manifest["n_eff"]
    assert manifest["n_eff_kept"] <= manifest["n_eff_full"]
    # the new quantization distribution is on the kept book only
    assert manifest["quantization"]["long_targets_rounding_to_zero"] == 0
    assert manifest["quantization"]["short_targets_rounding_to_zero"] == 0
    # the construction is recorded in the artifact so the page can label it
    # from the stored fields rather than asserting a label beside it
    assert manifest["construction"] == "share_only"
    assert manifest["construction_floor_dollars"] is None
    assert manifest["construction_floor_shares"] == ev.SHARE_FLOOR
    assert manifest["construction_top_n"] is None
    assert manifest["floor_iterated"] is True
    assert isinstance(manifest["code_commit"], str) and manifest["code_commit"]
    assert 0.0 < manifest["kept_gross_before_renorm"] < manifest["kept_gross"]


@pytest.mark.slow
def test_build_proposal_stores_every_input_as_of_and_max_staleness() -> None:
    manifest = ev.build_proposal(store=False)
    for key in (
        "prices",
        "shares",
        "universe",
        "sectors",
        "descriptors",
        "factor_returns",
        "specific_returns",
        "factor_cov",
        "specific_var",
    ):
        assert key in manifest["input_as_of"], key
        assert manifest["input_as_of"][key], key
    assert manifest["max_input_staleness_days"] >= 0
