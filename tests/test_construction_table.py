"""Sprint E11: the construction table, the owner's decision surface.

The table is nine rows: minimum position size of $1,500 / $2,000 / $3,000 /
$5,000 (each applied iteratively to a fixed point), top N by absolute alpha at
N = 150 and N = 200, the flagged two-part floor (min $1,500 and min 20 shares,
at its fixed point), the flagged share-only floor (min 20 shares, no dollar leg)
and the full 499-name reference book. Each row re-hedges on its own subset,
renormalizes to gross 1.0, then quantizes.
"""

from __future__ import annotations

import pytest

from live import construction_table as ct


@pytest.mark.slow
@pytest.mark.integration
def test_the_table_has_all_nine_rows_and_renormalizes() -> None:
    table = ct.build_table(store=False)
    assert sorted(table["construction"]) == [
        "full_book_499",
        "min_position_1500",
        "min_position_2000",
        "min_position_3000",
        "min_position_5000",
        "share_only_20shares",
        "top_n_150",
        "top_n_200",
        "two_part_floor_1500_20shares",
    ]
    # every row renormalizes to gross 1.0 after dropping
    assert float((table["kept_gross_after_renorm"] - 1.0).abs().max()) < 1e-9
    # kept + dropped is the full 499-name book
    assert (table["n_kept"] + table["n_dropped"] == 499).all()
    # every row states long and short counts
    assert (table["n_long"] + table["n_short"] == table["n_kept"]).all()
    # every row reports post-hedge exposure, idio share and both breadth bounds
    for column in (
        "post_hedge_max_abs_exposure",
        "post_hedge_idio_share",
        "max_weight_share_of_gross",
        "breadth_naive",
        "breadth_governing",
        "total_gross_error_share_of_nav",
    ):
        assert table[column].notna().all(), column
    # every row reports net dollar, realized beta and the share distribution
    for column in (
        "net_dollar_share_of_gross",
        "net_dollar_share_of_gross_post_quantization",
        "realized_market_beta",
        "median_share_count",
        "p10_share_count",
        "p90_tail_driver",
        "n_kept_pre_iteration",
        "n_kept_post_iteration",
        "quant_error_p90_pre_iteration",
        "quant_error_p90_post_iteration",
    ):
        assert table[column].notna().all(), column
    # the post-renormalization net is hedged away: gross is 1.0, net is ~0
    assert float(table["net_dollar_share_of_gross"].abs().max()) < 0.01
    # the beta decomposition columns are present and populated
    for column in (
        "n_beta_filled",
        "realized_market_beta_ex_fills",
        "n_beta_zero_filled",
        "realized_market_beta_ex_zero_fills",
        "realized_market_beta_shrunk",
        "realized_market_beta_descriptor",
        "corr_raw_vs_descriptor",
        "residual_exposure_shrunk",
        "residual_exposure_winsor",
        "residual_exposure_standardized",
        "residual_exposure_descriptor",
    ):
        assert table[column].notna().all(), column
    # the FMP hedge zeroes XS-v1's own beta descriptor on every row
    assert float(table["realized_market_beta_descriptor"].abs().max()) < 1e-9
    # the descriptor spans none of the raw beta: the residual exposure at the
    # descriptor stage is the full raw beta (the hedge zeroes the descriptor)
    assert (
        float(
            (table["residual_exposure_descriptor"] - table["realized_market_beta"])
            .abs()
            .max()
        )
        < 1e-6
    )
    # the raw beta is what the descriptor does not span, so it is at least the
    # magnitude of the shrunk pre-winsorization value on every row
    assert (
        table["realized_market_beta"].abs()
        >= table["realized_market_beta_shrunk"].abs()
    ).all()


@pytest.mark.slow
@pytest.mark.integration
def test_the_top_n_rows_select_by_absolute_alpha() -> None:
    table = ct.build_table(store=False)
    row = table.loc[table["construction"] == "top_n_150"].iloc[0]
    assert row["n_kept"] == 150
    # the side of alpha sets the side, so long and short sum to N
    assert int(row["n_long"]) + int(row["n_short"]) == 150


@pytest.mark.slow
@pytest.mark.integration
def test_the_minimum_position_rows_drop_by_dollar_size() -> None:
    table = ct.build_table(store=False)
    kept = table.loc[table["construction"].str.startswith("min_position"), "n_kept"]
    # a larger minimum position keeps fewer names
    assert kept.is_monotonic_decreasing
    assert int(kept.iloc[0]) > int(kept.iloc[-1])


@pytest.mark.slow
@pytest.mark.integration
def test_the_iterative_floor_raises_breadth_and_reports_both_p90s() -> None:
    table = ct.build_table(store=False)
    rows = table.loc[table["construction"].str.startswith("min_position")]
    # the fixed-point floor keeps at least as many names as the plain floor
    assert (rows["n_kept_post_iteration"] >= rows["n_kept_pre_iteration"]).all()
    # every min-position row reports both p90 values
    assert rows["quant_error_p90_pre_iteration"].notna().all()
    assert rows["quant_error_p90_post_iteration"].notna().all()


@pytest.mark.slow
@pytest.mark.integration
def test_the_two_part_floor_is_flagged_and_reaches_its_fixed_point() -> None:
    table = ct.build_table(store=False)
    row = table.loc[table["construction"] == "two_part_floor_1500_20shares"].iloc[0]
    assert bool(row["flagged_for_veto"]) is True
    # pre is one pass of the combined floor, post is its fixed point; the
    # iteration only admits names, so post is at least pre, as on the dollar rows
    assert int(row["n_kept_post_iteration"]) >= int(row["n_kept_pre_iteration"])
    # the fixed point guarantees every kept name 20 shares in the renormalized
    # full-book weights; the median share count survives the re-sizing
    assert float(row["median_share_count"]) >= 20.0
    # exactly two rows are flagged for the owner's veto
    assert int(table["flagged_for_veto"].sum()) == 2


@pytest.mark.slow
@pytest.mark.integration
def test_the_share_only_floor_is_flagged_and_holds_twenty_shares() -> None:
    table = ct.build_table(store=False)
    row = table.loc[table["construction"] == "share_only_20shares"].iloc[0]
    assert bool(row["flagged_for_veto"]) is True
    # the share-only fixed point keeps at least the one-pass set
    assert int(row["n_kept_post_iteration"]) >= int(row["n_kept_pre_iteration"])
    # the median kept name holds at least 20 shares
    assert float(row["median_share_count"]) >= 20.0


@pytest.mark.slow
@pytest.mark.integration
def test_the_book_is_the_drop_then_admit_local_maximum() -> None:
    table = ct.build_table(store=False)
    floor_rows = table.loc[
        table["construction"].str.startswith("min_position")
        | table["construction"].isin(
            ["share_only_20shares", "two_part_floor_1500_20shares"]
        )
    ]
    no_floor_rows = table.loc[
        table["construction"].isin(["top_n_150", "top_n_200", "full_book_499"])
    ]
    # the book is the rule's output, and no kept name is below its floor in the
    # final, quantized weights
    assert (floor_rows["n_below_floor_final"] == 0).all()
    assert bool(floor_rows["admit_converged"].all()) is True
    assert (floor_rows["admit_cycles"] >= 1).all()
    # by construction, not a check (Verification item 4): the rule starts at
    # the drop-only set and only adds names
    assert (floor_rows["n_kept"] >= floor_rows["n_kept_drop_only"]).all()
    assert (floor_rows["n_kept"] >= floor_rows["n_kept_one_pass_admission"]).all()
    # the superseded rules are stored beside the book, for the record: the
    # drop-only count and the E11-F13 prefix, which keeps far fewer names
    assert (floor_rows["n_kept_prefix"] < floor_rows["n_kept"]).all()
    assert (floor_rows["n_kept_drop_only"] < floor_rows["n_kept"]).all()
    # the five checks, recorded per row. Four hold everywhere; the fifth, at
    # least 51 kept names for the rank margin, fails on the $5,000 row alone,
    # which is the stop Part 1R fired
    bad = floor_rows.loc[floor_rows["floor_book_checks"] != "ok"]
    assert list(bad["construction"]) == ["min_position_5000"]
    assert "rank margin" in str(bad["floor_book_checks"].iloc[0])
    # the search and its ordering robustness are reported
    for column in (
        "admit_passes",
        "admit_extra",
        "n_kept_alpha_order",
        "n_eff_kept_alpha_order",
        "n_eff_alpha_gap_pct",
    ):
        assert floor_rows[column].notna().all(), column
    # no-floor rows carry the vacuous stamp with nothing below their (absent)
    # floor and their kept count untouched
    assert (no_floor_rows["n_kept_post_enforcement"] == no_floor_rows["n_kept"]).all()
    assert (no_floor_rows["n_below_floor_final"] == 0).all()
    assert (no_floor_rows["floor_prefix_scans"] == 0).all()
    assert (no_floor_rows["admit_cycles"] == 0).all()
    assert (no_floor_rows["floor_book_checks"] == "ok").all()
