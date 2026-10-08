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


def test_a_member_with_no_price_is_reported_by_name(tmp_path: Path) -> None:
    """A takeover or a halt leaves a name in the index with no print.

    It drops out of the book because the model needs its return, and that is the
    right answer: the run must not stop for it. The names come back so that the
    message can say them rather than leave the gap to be noticed.
    """
    _write_spy_archive(tmp_path, "2026-09-21", ["PRICED", "HALTED"])
    priced = pd.MultiIndex.from_product(
        [[pd.Timestamp("2026-09-21")], ["PRICED"]], names=["date", "ticker"]
    )
    pd.DataFrame({"close": [10.0]}, index=priced).to_parquet(
        tmp_path / "raw" / "prices.parquet"
    )

    assert ev.universe_without_prices(tmp_path) == ["HALTED"]

    # and with every member priced there is nothing to report
    full = pd.MultiIndex.from_product(
        [[pd.Timestamp("2026-09-21")], ["PRICED", "HALTED"]], names=["date", "ticker"]
    )
    pd.DataFrame({"close": [10.0, 20.0]}, index=full).to_parquet(
        tmp_path / "raw" / "prices.parquet"
    )
    assert ev.universe_without_prices(tmp_path) == []


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
    assert result["effective_breadth"] == pytest.approx(4.0)
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


def _synthetic_book() -> tuple[list[str], np.ndarray, dict[str, float]]:
    """Six names, one degenerate factor, so every weight is predictable.

    Prices are all $10 and NAV is $1,000, so a name holds floor(|w| * 100)
    shares. The alpha vector is dollar-neutral (5 - 5 + 4 - 4 + 3 - 3), and
    with no factor loading the hedge has nothing to do, so the kept weights
    are alpha over its gross and the shares are 20 or more for A and B only on
    the full book.
    """
    names = ["A", "B", "C", "D", "E", "F"]
    alpha = np.array([5.0, -5.0, 4.0, -4.0, 3.0, -3.0])
    close = {ticker: 10.0 for ticker in names}
    return names, alpha, close


def _synthetic_pieces(names: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return np.zeros((len(names), 1)), np.eye(1), np.ones(len(names))


def test_the_fast_floor_check_matches_the_finalized_vector() -> None:
    names, alpha, close = _synthetic_book()
    design, factor_covariance, specific = _synthetic_pieces(names)
    for keep in (
        np.array([True] * 6),
        np.array([True, True, True, False, False, False]),
        np.array([True, True, False, False, False, False]),
    ):
        finalize = ev.finalize_kept_set(
            keep, names, alpha, design, factor_covariance, specific, close, 1000.0
        )
        full = not ev.below_floor(
            np.asarray(finalize["shares"], dtype=int),
            np.asarray(finalize["prices"], dtype=float),
            0.0,
            20,
        ).any()
        fast = ev.kept_set_clears_floor(
            keep,
            names,
            alpha,
            design,
            factor_covariance,
            specific,
            close,
            1000.0,
            0.0,
            20,
        )
        assert fast == full


def test_drop_then_admit_only_adds_and_is_a_local_maximum() -> None:
    """The rule's own claim, asserted without hard-coding a fixture's numbers.

    The search's membership moves when the sizing moves - the variance-share cap
    is part of the sizing now - so the numbers a 6-name fixture happens to produce
    are not the claim. The claim is: it starts from the drop-only set and only
    adds, what it returns clears its floor, and no single excluded name can be
    added without breaking a kept name's floor.
    """
    names, alpha, close = _synthetic_book()
    design, factor_covariance, specific = _synthetic_pieces(names)
    full_weights = alpha.copy()
    keep, _finalize, info = ev.enforce_floor_by_drop_then_admit(
        names,
        alpha,
        design,
        factor_covariance,
        specific,
        close,
        1000.0,
        full_weights,
        0.0,
        20,
    )
    kept = int(keep.sum())
    assert kept > info["n_drop_only"], "nothing was admitted"
    assert info["admitted"] == kept - info["n_drop_only"]
    assert info["n_one_pass_admission"] >= info["n_drop_only"]
    assert info["converged"] is True
    # What the search promises is the floor, on the vector that trades, so that is
    # what is asserted here. (This fixture's single factor is a zero column, so its
    # hedge has nothing to remove and an odd-sized subset keeps a net dollar that
    # the real design's constant market column zeroes. The rehearsal's own book
    # records net 3.6e-16, which is where dollar neutrality is checked.)
    assert [
        message
        for message in ev.floor_book_violations(
            keep,
            names,
            alpha,
            design,
            factor_covariance,
            specific,
            close,
            1000.0,
            0.0,
            20,
            min_names=kept,
        )
        if "below their floor" in message
    ] == []
    # local maximum under single-name moves: adding any excluded name breaks a
    # kept name's floor
    for position in np.where(~keep)[0]:
        trial = keep.copy()
        trial[position] = True
        assert not ev.kept_set_clears_floor(
            trial,
            names,
            alpha,
            design,
            factor_covariance,
            specific,
            close,
            1000.0,
            0.0,
            20,
        )
    # and under the default rank margin the set reports its own thinness, or
    # nothing when it is thick enough
    reported = ev.floor_book_violations(
        keep,
        names,
        alpha,
        design,
        factor_covariance,
        specific,
        close,
        1000.0,
        0.0,
        20,
    )
    if kept < ev.MIN_FLOOR_BOOK_NAMES:
        assert (
            f"{kept} kept names, below the {ev.MIN_FLOOR_BOOK_NAMES} name rank margin"
            in reported
        )
    assert not [message for message in reported if "below their floor" in message]


def test_drop_then_admit_is_deterministic() -> None:
    names, alpha, close = _synthetic_book()
    design, factor_covariance, specific = _synthetic_pieces(names)
    first = ev.enforce_floor_by_drop_then_admit(
        names,
        alpha,
        design,
        factor_covariance,
        specific,
        close,
        1000.0,
        alpha.copy(),
        0.0,
        20,
    )
    second = ev.enforce_floor_by_drop_then_admit(
        names,
        alpha,
        design,
        factor_covariance,
        specific,
        close,
        1000.0,
        alpha.copy(),
        0.0,
        20,
    )
    assert first[0].tolist() == second[0].tolist()
    assert first[2] == second[2]


def test_drop_then_admit_reports_a_cycle_cap_instead_of_a_cycle() -> None:
    names, alpha, close = _synthetic_book()
    design, factor_covariance, specific = _synthetic_pieces(names)
    keep, _finalize, info = ev.enforce_floor_by_drop_then_admit(
        names,
        alpha,
        design,
        factor_covariance,
        specific,
        close,
        1000.0,
        alpha.copy(),
        0.0,
        20,
        max_cycles=0,
    )
    assert info["converged"] is False
    assert info["cycles"] == 0
    assert int(keep.sum()) == info["n_drop_only"]


def test_floor_book_violations_names_what_is_wrong() -> None:
    names, alpha, close = _synthetic_book()
    design, factor_covariance, specific = _synthetic_pieces(names)
    # a book with names below their floor, and nothing else wrong with it. How
    # many is the sizing's answer, so it is counted from the same vector the
    # check reads rather than pinned to a fixture whose weights move.
    thin = np.ones(len(names), dtype=bool)
    _idx, _names_sub, w_sub, prices, _design_sub, _specific_sub, _pre = (
        ev.sized_kept_weights(
            thin,
            names,
            alpha,
            design,
            factor_covariance,
            specific,
            close,
            1000.0,
        )
    )
    below = int(
        ev.below_floor(ev.kept_shares(w_sub, prices, 1000.0), prices, 0.0, 20).sum()
    )
    assert below > 0, "the fixture no longer has a name below its floor"
    messages = ev.floor_book_violations(
        thin,
        names,
        alpha,
        design,
        factor_covariance,
        specific,
        close,
        1000.0,
        0.0,
        20,
        min_names=6,
    )
    assert messages == [f"{below} kept names are below their floor"]
    # a book that clears its floor but is too thin for the rank margin
    small = np.array([True, True, True, True, False, False])
    messages = ev.floor_book_violations(
        small,
        names,
        alpha,
        design,
        factor_covariance,
        specific,
        close,
        1000.0,
        0.0,
        20,
    )
    assert messages == [
        f"4 kept names, below the {ev.MIN_FLOOR_BOOK_NAMES} name rank margin"
    ]


@pytest.mark.slow
def test_build_proposal_stores_the_share_only_floor_and_breadth() -> None:
    manifest = ev.build_proposal(store=False)
    # the chosen construction: min 20 shares, no dollar floor, enforced on the
    # final weights by the drop-then-admit rule (E11-F13R)
    assert manifest["min_position_dollars"] == pytest.approx(0.0)
    assert manifest["min_position_pct_of_nav"] == pytest.approx(0.0)
    # names whose final position is below 20 shares are dropped
    assert manifest["n_kept"] + manifest["n_dropped"] == manifest["n_names"]
    assert manifest["n_kept"] < manifest["n_names"]
    assert manifest["n_dropped"] > 0
    # the rule, its search and its run time are recorded so the page can label
    # the book from its own fields
    assert manifest["floor_rule"] == "drop_then_admit"
    assert manifest["floor_search_converged"] is True
    assert manifest["floor_search_cycles"] >= 1
    assert manifest["n_kept"] >= manifest["n_kept_one_pass_admission"]
    assert manifest["n_kept_one_pass_admission"] >= manifest["n_kept_drop_only"]
    assert manifest["floor_search_seconds"] > 0.0
    # both breadth measures are recorded: the naive N-bound and the governing
    # n_eff-bound, which uses the E8 effective-breadth construction
    assert manifest["breadth_naive_bound"] >= 1.0
    assert manifest["breadth_governing"] >= 1.0
    assert manifest["n_eff_kept"] <= manifest["n_eff_full_book"]
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
    # the traded book name by name, with each name's specific variance and its
    # share of the book's predicted specific variance, so the comparison and the
    # page's risk block read the book the run traded rather than re-deriving it
    kept = manifest["kept_book"]
    assert len(kept) == manifest["n_effective"] == manifest["n_kept"]
    assert sum(entry["variance_share"] for entry in kept) == pytest.approx(1.0)
    for entry in kept:
        assert set(entry) == {
            "ticker",
            "weight",
            "specific_variance",
            "variance_share",
        }
        # a variance, so its square root is the specific volatility the alpha
        # contract multiplies by
        assert entry["specific_variance"] > 0.0
        assert abs(entry["weight"]) > 1e-12
    # the concentration reading: the cap binds when a name sits at or above it
    assert manifest["variance_share_cap"] == pytest.approx(ev.sizing.VARIANCE_SHARE_CAP)
    assert manifest["max_variance_share"] == pytest.approx(
        max(entry["variance_share"] for entry in kept)
    )
    assert manifest["variance_share_cap_binds"] is (
        manifest["max_variance_share"] >= ev.sizing.VARIANCE_SHARE_CAP - 1e-12
    )
    top = manifest["top_variance_shares"]
    assert [entry["ticker"] for entry in top] == [
        entry["ticker"]
        for entry in sorted(kept, key=lambda row: -row["variance_share"])[:5]
    ]


@pytest.mark.slow
def test_the_traded_alpha_is_the_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every alpha the evening sizes from is IC x sigma x z x kappa.

    The formula is written out here rather than called: the test's job is to
    disagree with the code if the code moves the contract, so it may not borrow
    the function it is checking. On the code before S1 the alpha carries an extra
    factor of the name's own volatility, so the negative control below fails
    there.
    """
    monkeypatch.setattr(ev, "PROPOSAL_DIR", tmp_path)
    manifest = ev.build_proposal(store=True)
    rows = pd.read_parquet(tmp_path / f"proposal_{manifest['as_of']}.parquet")
    kept = {entry["ticker"]: entry for entry in manifest["kept_book"]}
    # the traded book is the recorded book, name by name
    assert set(rows["ticker"]) == set(kept)
    variance = np.array(
        [kept[ticker]["specific_variance"] for ticker in rows["ticker"]]
    )
    z = rows["z"].to_numpy(dtype=float)
    ic = float(manifest["ic"])
    kappa = float(manifest["kappa"])

    expected = ic * np.sqrt(variance) * z * kappa

    assert np.allclose(rows["alpha"].to_numpy(dtype=float), expected, rtol=1e-12)
    # the negative control: the variance where the volatility belongs
    old = ic * variance * z * kappa
    assert not np.allclose(rows["alpha"].to_numpy(dtype=float), old)


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


def test_a_kept_name_with_no_close_is_dropped_and_the_rest_are_priced() -> None:
    """One name with no usable close is out of the book; the rest still trade.

    This is the evening of 2026-09-29: the vendor answered for every name but one,
    the model knew the missing name from its history, and the whole run stopped at
    quantization on that single name. The rule is the one the universe already
    follows one step upstream, where a member with no print tonight drops out of
    the book by construction: the name is dropped, the remaining names are priced
    and quantized, and the book is renormalized to gross 1.0 without it, exactly as
    it is after the share floor. Prices are $10 and NAV is $10,000, so every name of
    this fixture's full book clears the 20-share floor and C is a name the book
    would have kept.
    """
    names, alpha, close = _synthetic_book()
    design, factor_covariance, specific = _synthetic_pieces(names)

    # the precondition, measured rather than asserted: with its close in hand, C is
    # in the book, so the drop below is a drop and not something the floor would
    # have done anyway
    whole_keep, _whole_finalize, _whole_info = ev.enforce_floor_by_drop_then_admit(
        names,
        alpha,
        design,
        factor_covariance,
        specific,
        dict(close),
        10_000.0,
        alpha.copy(),
        0.0,
        20,
    )
    assert whole_keep[names.index("C")]

    close["C"] = float("nan")
    priced, dropped = ev.dropped_for_no_price(names, close)
    assert dropped == ["C"]
    assert priced.tolist() == [True, True, False, True, True, True]

    # the run's own path: the search starts from the priced names
    keep, finalize, _info = ev.enforce_floor_by_drop_then_admit(
        names,
        alpha,
        design,
        factor_covariance,
        specific,
        close,
        10_000.0,
        alpha.copy(),
        0.0,
        20,
        start=priced,
    )

    assert "C" not in finalize["names_sub"]
    assert names.index("C") not in set(np.asarray(finalize["idx"]).tolist())
    assert int(keep.sum()) == len(finalize["names_sub"])
    # the rest are priced and quantized: a real close and a whole-share count
    assert np.isfinite(np.asarray(finalize["prices"], dtype=float)).all()
    assert (np.asarray(finalize["shares"], dtype=int) > 0).all()
    # and renormalized to gross 1.0 after the drop
    assert np.abs(np.asarray(finalize["w_sub"], dtype=float)).sum() == pytest.approx(
        1.0
    )

    # the negative control: a set that skipped the drop still refuses, which is
    # what the evening did before this rule existed
    with pytest.raises(ValueError, match="no usable close price for C at the"):
        ev.enforce_floor_by_drop_then_admit(
            names,
            alpha,
            design,
            factor_covariance,
            specific,
            close,
            10_000.0,
            alpha.copy(),
            0.0,
            20,
        )


def test_the_book_stops_when_more_than_ten_names_drop_for_no_price() -> None:
    """The drop is bounded by a count of names, not by a floor on what is left.

    One or a few names missing is a halt, a delisting or a single missed symbol on
    the night, and the book drops them and prices the rest. Ten at once is the fetch
    having broken, and then the run stops and emails rather than trading a book
    built from whatever the fetch did answer for: the book targets roughly 180 names
    and needs its rank margin, so a book of 100 is not a smaller book, it is another
    one. The refusal names the drops it is refusing over, because "too many" without
    them is a count nobody can act on.
    """
    names = [f"T{index:03d}" for index in range(499)]
    close = {name: 10.0 for name in names}
    assert ev.MAX_PRICE_DROPS == 10

    # the boundary: ten names missing prices the book without a refusal
    for name in names[:10]:
        close.pop(name)
    priced, dropped = ev.priced_names_or_stop(names, close)
    assert dropped == names[:10]
    assert int(priced.sum()) == 489

    # and the count is the parameter, so the boundary is testable rather than
    # asserted: eleven drops stop, and a rule that allowed eleven would not
    priced, dropped = ev.priced_names_or_stop(names, close, max_drops=10)
    assert len(dropped) == 10
    close.pop(names[10])
    with pytest.raises(ValueError, match="more than the 10 the evening accepts"):
        ev.priced_names_or_stop(names, close)

    # a fetch that answered for nothing is the case the rule exists for
    with pytest.raises(ValueError, match="499 of 499 names have no usable close"):
        ev.priced_names_or_stop(names, {})


def test_merged_no_price_names_both_rules_once() -> None:
    """The email's one line carries the universe's members and the book's drops.

    Both are the same fact about tonight, that the index had no print for the name,
    so they belong on one line and a name both rules found is said once.
    """
    manifest = {"dropped_no_price": ["CSGP", "WBA"]}
    assert ev.merged_no_price(["WBA", "EA"], manifest) == ["CSGP", "EA", "WBA"]
    # a manifest from before this rule carries no such list, and neither does a
    # run whose book lost nothing
    assert ev.merged_no_price(["EA"], {}) == ["EA"]
    assert ev.merged_no_price(None, {}) == []


@pytest.mark.slow
def test_build_proposal_drops_a_kept_name_with_no_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same drop at the book, on the real panel.

    The missing name is taken from the manifest's own kept book rather than pinned,
    so the test says what it means on any vintage: a name the book would have kept
    is out of the book, the rest are priced and quantized, and the traded gross is
    the same 1.0 it would have been.

    Dropping a name is not a mechanical minus one, and the kept count is not
    asserted to fall: the book is renormalized without the name, so the names
    admitted afterwards clear their floor against a different vector. Measured on
    the 2026-09-21 vintage this panel ends at, the kept count goes 180 (nothing
    missing) to 190 (the book's largest name missing).
    """
    baseline = ev.build_proposal(store=False)
    victim = str(baseline["kept_book"][0]["ticker"])
    real_close_prices = ev._close_prices

    def without_the_victim(as_of: pd.Timestamp, root: Path) -> dict[str, float]:
        close = dict(real_close_prices(as_of, root))
        close.pop(victim)
        return close

    monkeypatch.setattr(ev, "_close_prices", without_the_victim)
    manifest = ev.build_proposal(store=False)

    assert manifest["dropped_no_price"] == [victim]
    assert manifest["n_dropped_no_price"] == 1
    assert manifest["max_price_drops"] == ev.MAX_PRICE_DROPS
    assert victim not in {entry["ticker"] for entry in manifest["kept_book"]}
    assert manifest["n_kept"] + manifest["n_dropped"] == manifest["n_names"]
    assert manifest["floor_search_converged"] is True
    # the rest are priced and quantized, and the traded book is renormalized
    assert sum(abs(entry["weight"]) for entry in manifest["kept_book"]) == (
        pytest.approx(1.0)
    )
    assert manifest["kept_gross"] == pytest.approx(1.0)
    assert manifest["quantization"]["long_targets_rounding_to_zero"] == 0
    assert manifest["quantization"]["short_targets_rounding_to_zero"] == 0
    assert manifest["n_kept"] >= ev.MIN_FLOOR_BOOK_NAMES
    # the control: with no name missing, the same build drops nothing
    assert baseline["dropped_no_price"] == []
    assert baseline["n_dropped_no_price"] == 0


def test_the_sizing_still_refuses_a_nan_close_passed_to_it() -> None:
    """The invariant behind the drop: a NaN close cannot become a share count.

    `kept_shares` floors `|w| * nav / max(price, 1e-12)`, so a NaN price makes that
    division undefined and the cast to int silently produces a share count nobody
    asked for. The book drops such a name before it sizes anything, so reaching the
    sizing with one is a caller that built its own keep set, and it is refused
    rather than priced. The real panel has this: APH has no close on 2026-08-28,
    09-01, 09-02 and 09-03, and its price halves on 09-04.
    """
    names, alpha, close = _synthetic_book()
    design, factor_covariance, specific = _synthetic_pieces(names)
    close["C"] = float("nan")
    with pytest.raises(ValueError, match="no usable close price for C at the"):
        ev.sized_kept_weights(
            np.array([True] * 6),
            names,
            alpha,
            design,
            factor_covariance,
            specific,
            close,
            1000.0,
        )


def test_the_sizing_refuses_a_missing_close_too() -> None:
    """A name absent from the close map defaulted to 0.0, which is just as

    unusable as a NaN and produced an astronomically large share count."""
    names, alpha, close = _synthetic_book()
    design, factor_covariance, specific = _synthetic_pieces(names)
    del close["D"]
    close["E"] = 0.0
    with pytest.raises(ValueError, match="no usable close price for D, E at the"):
        ev.sized_kept_weights(
            np.array([True] * 6),
            names,
            alpha,
            design,
            factor_covariance,
            specific,
            close,
            1000.0,
        )


def test_usable_prices_passes_every_kept_name_through() -> None:
    """The negative control: the guard changes nothing when prices are fine."""
    prices = ev.usable_prices(["A", "B"], {"A": 10.0, "B": 20.0})
    assert list(prices) == [10.0, 20.0]


def test_load_spy_universe_clamps_to_the_close(tmp_path: Path) -> None:
    """The universe is the newest archive on or before the close being priced.

    The 2026-09-18 proposal used to record its universe as of 2026-09-21, a
    snapshot filed one session after the close it priced.
    """
    _write_spy_archive(tmp_path, "2026-09-18", ["AAA", "BBB"])
    _write_spy_archive(tmp_path, "2026-09-21", ["AAA", "CCC"])
    frame, path = ev.load_spy_universe(tmp_path, as_of=pd.Timestamp("2026-09-18"))
    assert path.name == "spy_holdings_2026-09-18.parquet"
    assert sorted(frame["ticker"]) == ["AAA", "BBB"]
    # the same close a day later still sees only what existed by then
    frame, path = ev.load_spy_universe(tmp_path, as_of=pd.Timestamp("2026-09-19"))
    assert path.name == "spy_holdings_2026-09-18.parquet"
    # and the newest archive is still the answer when no close is given
    frame, path = ev.load_spy_universe(tmp_path)
    assert path.name == "spy_holdings_2026-09-21.parquet"


def test_a_universe_that_postdates_the_close_is_refused(tmp_path: Path) -> None:
    """The shift audit: no archive on or before the close is a refusal, never a
    later snapshot used anyway."""
    _write_spy_archive(tmp_path, "2026-09-21", ["AAA", "BBB"])
    with pytest.raises(ValueError, match="postdates the close being priced"):
        ev.load_spy_universe(tmp_path, as_of=pd.Timestamp("2026-09-18"))


def test_an_archive_name_without_a_date_is_refused(tmp_path: Path) -> None:
    archive = tmp_path / "raw" / "spy_holdings"
    archive.mkdir(parents=True, exist_ok=True)
    _write_spy_archive(tmp_path, "2026-09-18", ["AAA"])
    (archive / "spy_holdings_backup.parquet").write_bytes(b"not a parquet")
    with pytest.raises(ValueError, match="does not carry a date"):
        ev.load_spy_universe(tmp_path, as_of=pd.Timestamp("2026-09-18"))


def _measured(names: list[str], unmeasured: int) -> np.ndarray:
    """A variance for every name but the first `unmeasured`."""
    values = np.full(len(names), 4e-04)
    values[:unmeasured] = np.nan
    return values


def test_a_name_with_no_risk_estimate_is_dropped_before_the_sizing() -> None:
    """A name the model cannot measure is not a name to size on the median.

    The alpha contract multiplies by the specific volatility, so a name with no
    specific variance and a name with a variance of zero both leave the book
    before anything is priced. They come back named, with which of the two rules
    fired, because the manifest and the message have to say it.
    """
    names = ["AAA", "BBB", "QQQ", "ZERO", "DDD"]
    variances = np.array([4e-04, 9e-04, np.nan, 0.0, 1e-04])

    covered, dropped = ev.dropped_for_no_risk(names, variances)

    assert covered == ["AAA", "BBB", "DDD"]
    assert dropped == [
        {"ticker": "QQQ", "reason": "no specific variance"},
        {"ticker": "ZERO", "reason": "specific variance 0 is not positive"},
    ]
    # a negative variance is not a risk either: `trade_reasons.specific_std` maps
    # one to NaN before it can reach the store, and the sizing must not price it
    covered, dropped = ev.dropped_for_no_risk(["AAA"], np.array([-1e-04]))
    assert covered == []
    assert dropped == [
        {"ticker": "AAA", "reason": "specific variance -0.0001 is not positive"}
    ]
    # the control: a fully measured diagonal drops nothing
    covered, dropped = ev.dropped_for_no_risk(names[:2], variances[:2])
    assert covered == names[:2]
    assert dropped == []


def test_the_book_stops_when_more_than_ten_names_have_no_risk_estimate() -> None:
    """The drop is bounded by a count of names, from the risk side.

    A name with a short history has no estimate until it does, and dropping it is
    the answer - Q, FDXF and HONA on 2026-10-07 were all that. A diagonal that
    arrived empty or truncated is not that, and it is the case the stop exists
    for: the run emails rather than building a book out of whatever the artifact
    did answer for. The refusal names the drops it is refusing over, because a
    count nobody can act on is not a message.
    """
    names = [f"T{index:03d}" for index in range(499)]
    assert ev.MAX_RISK_DROPS == 10

    # the boundary: ten unmeasured names still size the other 489
    covered, dropped = ev.risk_names_or_stop(names, _measured(names, 10))
    assert len(covered) == 489
    assert [entry["ticker"] for entry in dropped] == names[:10]

    # and the count is the parameter, so the boundary is testable rather than
    # asserted: eleven stop, and a rule that allowed eleven would not
    covered, dropped = ev.risk_names_or_stop(names, _measured(names, 11), max_drops=11)
    assert len(dropped) == 11
    with pytest.raises(ValueError, match="more than the 10 the evening accepts"):
        ev.risk_names_or_stop(names, _measured(names, 11))

    # a diagonal that answered for nothing is the case the rule exists for
    with pytest.raises(ValueError, match="499 of 499 names have no specific variance"):
        ev.risk_names_or_stop(names, np.full(len(names), np.nan))


@pytest.mark.slow
def test_build_proposal_sizes_only_the_names_the_risk_model_can_measure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Q case at the book, on the real panel.

    On 2026-10-07 Q was sized on the cross-sectional median - EQT's own specific
    variance, to the last bit - kept by the share floor at $3,623, and then
    refused by `efb.positions.idio_vol`, which is `not null`, after the whole book
    had been priced. The name is the right thing to drop and the median is the
    wrong thing to size it on, so the names the diagonal does not cover leave
    before anything is priced, and the counts still add up:
    universe = excluded + dropped_no_risk + n_names.

    The name taken is the baseline's own largest kept name rather than Q, because
    the fixture tree's session is not 2026-10-07: what has to hold is the rule, and
    the rule says a name with no estimate is out of the book and named. Measured on
    this tree, the three names the real artifact is missing (Q, FDXF, HONA) are all
    below the share floor, so dropping them moves the sized universe 502 -> 499 and
    leaves the traded book's 188 names as they were; dropping a *kept* name's
    estimate on top of that takes the sized universe to 498 and the book to 178.
    The kept count is therefore asserted to move rather than to fall by one: the
    book is renormalized without the name, and the names admitted afterwards clear
    the floor against a different vector.
    """
    baseline = ev.build_proposal(store=False)
    assert baseline["max_risk_drops"] == ev.MAX_RISK_DROPS
    victim = str(baseline["kept_book"][0]["ticker"])

    # The same reader the sizing uses, so this is the 2026-10-07 shape exactly: a
    # name the diagonal has no row for, which `_xs_pieces` would fill with the
    # median before pricing it.
    real_specific_for = ev.race._specific_for

    def without_the_victim(
        date: pd.Timestamp, names: list[str], root: Path
    ) -> tuple[np.ndarray, int]:
        values, missing = real_specific_for(date, names, root)
        values = np.array(values, dtype=float, copy=True)
        if victim in names:
            values[names.index(victim)] = np.nan
            missing += 1
        return values, missing

    monkeypatch.setattr(ev.race, "_specific_for", without_the_victim)
    manifest = ev.build_proposal(store=False)

    def universe_of(built: dict) -> int:
        return built["n_names"] + built["n_excluded"] + built["n_dropped_no_risk"]

    dropped = {
        str(entry["ticker"]): str(entry["reason"])
        for entry in manifest["dropped_no_risk"]
    }
    assert dropped.get(victim) == "no specific variance"
    assert victim not in {entry["ticker"] for entry in manifest["kept_book"]}
    # the drop is exactly the names the diagonal cannot measure, and it is taken
    # out of the sizing rather than out of the universe: the counts still add up
    assert set(manifest["dropped_no_risk"][0]) == {"ticker", "reason"}
    assert all(
        entry["reason"] == "no specific variance"
        for entry in manifest["dropped_no_risk"]
    )
    assert manifest["n_names"] == baseline["n_names"] - 1
    assert manifest["n_dropped_no_risk"] == baseline["n_dropped_no_risk"] + 1
    assert universe_of(manifest) == universe_of(baseline)
    assert manifest["n_kept"] != baseline["n_kept"]
    assert manifest["n_kept"] != baseline["n_kept"]
    assert manifest["n_kept"] + manifest["n_dropped"] == manifest["n_names"]
    assert manifest["floor_search_converged"] is True
    # every name the book did keep carries a variance of its own: none of them is
    # the cross-sectional median standing in for a missing row
    assert all(
        float(entry["specific_variance"]) > 0.0 for entry in manifest["kept_book"]
    )
    assert manifest["kept_gross"] == pytest.approx(1.0)
    assert manifest["quantization"]["long_targets_rounding_to_zero"] == 0
    assert manifest["quantization"]["short_targets_rounding_to_zero"] == 0
