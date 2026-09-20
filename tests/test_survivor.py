"""Sprint E4 Task 4: the survivor restriction and the coverage gap.

The stored numbers are what `efb/survivor.py` printed. Two of them matter more
than the rest: the size and liquidity factor returns correlate 0.58 and 0.63
between the two universes, so the 323 excluded names are not a rounding
difference, and the mean names per date differ by 101, which is the guard that
stopped this task's first version from printing one fit twice.
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
    assert size == pytest.approx(0.577780, abs=5e-6)
    assert size < 0.9
    assert factors.loc["liquidity", "correlation_panel_vs_mapped"] < 0.9
    assert factors.loc["resid_vol", "correlation_panel_vs_mapped"] < 0.9
    # the styles the XS-v1 book leans on are stable, which is why the
    # restriction shows up as a size and liquidity effect
    for stable in ("beta", "momentum", "reversal"):
        assert factors.loc[stable, "correlation_panel_vs_mapped"] > 0.95


@pytest.mark.integration
def test_the_size_premium_deepens_between_universes(factors: pd.DataFrame) -> None:
    size = factors.loc["size"]
    assert size["premium_panel"] < 0.0
    assert size["premium_mapped"] < 0.0
    # the restricted universe makes the small-cap discount four times larger
    assert size["premium_mapped"] < 4.0 * size["premium_panel"]
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
    assert excluded["names"] == 323
    assert included["names"] == 502
