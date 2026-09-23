"""Sprint E11: the construction table, the owner's decision surface.

The table is seven rows: minimum position size of $1,500 / $2,000 / $3,000 /
$5,000 (each applied iteratively to a fixed point), top N by absolute alpha at
N = 150 and N = 200, and one flagged two-part floor (min $1,500 and min 20
shares). Each row re-hedges on its own subset, renormalizes to gross 1.0, then
quantizes.
"""

from __future__ import annotations

import pytest

from live import construction_table as ct


@pytest.mark.slow
@pytest.mark.integration
def test_the_table_has_all_seven_rows_and_renormalizes() -> None:
    table = ct.build_table(store=False)
    assert sorted(table["construction"]) == [
        "min_position_1500",
        "min_position_2000",
        "min_position_3000",
        "min_position_5000",
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
def test_the_two_part_floor_is_flagged_and_narrower_than_the_dollar_floor() -> None:
    table = ct.build_table(store=False)
    row = table.loc[table["construction"] == "two_part_floor_1500_20shares"].iloc[0]
    assert bool(row["flagged_for_veto"]) is True
    # the share leg drops names and therefore never adds breadth over the
    # dollar floor alone
    assert int(row["n_kept_post_iteration"]) <= int(row["n_kept_pre_iteration"])
    # the share leg tightens the p90 rounding error
    assert float(row["quant_error_p90_post_iteration"]) < float(
        row["quant_error_p90_pre_iteration"]
    )
    # the only flagged row is the two-part floor
    assert int(table["flagged_for_veto"].sum()) == 1
