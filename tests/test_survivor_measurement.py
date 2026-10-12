"""Sprint E4 Task 4: the survivor restriction and the coverage gap.

The stored numbers are what `efb/survivor.py` printed. Two of them matter more
than the rest: the size and liquidity factor returns correlate 0.83 and 0.86
between the two universes, so the 309 excluded names are not a rounding
difference, and the mean names per date differ by 93, which is the guard that
stopped this task's first version from printing one fit twice.

The size numbers were restated on 2026-10-04. Before the frozen-panel propagation
pass the file read 0.58 and 0.63 with 323 excluded names and the two factors it
singled out were size and residual volatility. The panel those numbers came from
carried a reused-ticker extension, repaired corporate actions and a different
membership grid, so the fit is a different cross-section. Whether the change is
an artifact of the reused-ticker series was measured rather than assumed: E1 was
rebuilt in a copy of the tree with those drops disabled, first for the thirteen
names the coverage rule adds and then for all forty-nine the identity layer
removes, and the survivor fit was re-run on each. The size correlation moves
0.8263 to 0.8263 to 0.8284 across the three, the residual-volatility correlation
0.95900 to 0.95923 to 0.95901, and the panel's size premium stays positive in all
three at about +0.00017. The junk series are therefore not the explanation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT = ROOT / "data" / "eval" / "xs_survivor_measurement.parquet"
EXCLUDED = ROOT / "data" / "eval" / "xs_survivor_excluded_names.parquet"
SUMMARY = ROOT / "data" / "eval" / "xs_survivor_universe_summary.parquet"


@pytest.fixture(scope="module")
def factors() -> pd.DataFrame:
    return pd.read_parquet(MEASUREMENT).set_index("factor")


@pytest.fixture(scope="module")
def summary() -> pd.DataFrame:
    return pd.read_parquet(SUMMARY).set_index("universe")


@pytest.mark.integration
def test_the_two_universes_are_not_the_same_fit(summary: pd.DataFrame) -> None:
    panel = summary.loc["panel_825", "mean_names"]
    mapped = summary.loc["mapped_502", "mean_names"]
    assert panel > mapped
    assert panel - mapped > 50


@pytest.mark.integration
def test_style_correlations_are_stored_and_size_is_the_low_one(
    factors: pd.DataFrame,
) -> None:
    assert factors.loc["market", "correlation_panel_vs_mapped"] > 0.99
    size = factors.loc["size", "correlation_panel_vs_mapped"]
    assert size == pytest.approx(0.826271, abs=5e-6)
    # on this panel the restriction shows up as size and liquidity, and no
    # longer as residual volatility: that factor tracks the panel at 0.959,
    # which is inside the bar the other two break
    assert size < 0.9
    assert factors.loc["liquidity", "correlation_panel_vs_mapped"] < 0.9
    assert factors.loc["resid_vol", "correlation_panel_vs_mapped"] == pytest.approx(
        0.959004, abs=5e-6
    )
    # the styles the XS-v1 book leans on are stable, which is why the
    # restriction shows up as a size and liquidity effect
    for stable in ("beta", "momentum", "reversal"):
        assert factors.loc[stable, "correlation_panel_vs_mapped"] > 0.95


@pytest.mark.integration
def test_the_size_premium_runs_the_other_way_in_the_two_universes(
    factors: pd.DataFrame,
) -> None:
    """Restated 2026-10-04: this is no longer a small-cap discount at all.

    The pre-back-port reading had the panel leg negative and the mapped leg four
    times larger, which is what "the small-cap discount deepens" described. On
    the corrected panel both legs are a fraction of a basis point: +0.000174
    with t 0.51 on the panel and -0.000169 with t -0.57 on the mapped set. The
    sign runs the other way on the panel leg and neither is distinguishable from
    zero, so the claim the file may make is the ordering of the t statistics, not
    a discount. The measurement that shows the reused-ticker series are not what
    moved it is in this file's docstring.
    """
    size = factors.loc["size"]
    assert size["premium_panel"] == pytest.approx(0.000174, abs=1e-6)
    assert size["premium_mapped"] == pytest.approx(-0.000169, abs=1e-6)
    assert size["t_panel"] == pytest.approx(0.514, abs=5e-3)
    assert size["t_mapped"] == pytest.approx(-0.572, abs=5e-3)
    # the restriction does move the premium, and in the direction the t
    # statistics are ordered: the mapped leg is the lower of the two
    assert size["premium_difference"] > 0.0
    assert size["t_mapped"] < size["t_panel"]


@pytest.mark.integration
def test_restricting_the_universe_raises_r_squared_and_lowers_specific_variance(
    summary: pd.DataFrame,
) -> None:
    assert (
        summary.loc["mapped_502", "mean_r_squared"]
        > summary.loc["panel_825", "mean_r_squared"]
    )
    assert (
        summary.loc["mapped_502", "mean_specific_variance"]
        < summary.loc["panel_825", "mean_specific_variance"]
    )
    assert int(summary.loc["panel_825", "dates"]) == int(
        summary.loc["mapped_502", "dates"]
    )


@pytest.mark.integration
def test_the_excluded_names_were_riskier_and_earned_less() -> None:
    frame = pd.read_parquet(EXCLUDED).set_index("group")
    excluded = frame.loc["excluded, outside it"]
    included = frame.loc["included, in the sector file"]
    assert excluded["annualized_vol"] > included["annualized_vol"]
    assert excluded["cross_sectional_vol_mean"] > included["cross_sectional_vol_mean"]
    assert excluded["differential_annualized"] < 0.0
    assert excluded["names"] == 309
    assert included["names"] == 502
