"""Sprint E4 Task 3: the momentum book's predicted variance and where it misses.

Every test reads the stored Task 3 artifacts, so the numbers the deliverable
quotes are the numbers these tests defend. Nothing here changes XS-v1.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"


def load(name: str) -> pd.DataFrame:
    path = EVAL / f"xs_task3_{name}.parquet"
    if not path.exists():
        pytest.skip(f"{path.name} not written yet")
    return pd.read_parquet(path)


@pytest.mark.integration
def test_3a_momentum_is_a_large_share_not_five_percent() -> None:
    frame = load("decomposition")
    shares = frame.groupby("tercile")["momentum_share"].mean()
    assert shares["low"] == pytest.approx(0.319808, abs=1e-5)
    assert shares["mid"] == pytest.approx(0.465699, abs=1e-5)
    assert shares["high"] == pytest.approx(0.561267, abs=1e-5)
    assert (
        shares["high"] > 0.5
    ), "the five percent back-of-envelope is refuted: the factor is a large slice"
    assert shares["high"] > shares["low"], "the share rises with exposure"
    predicted = frame.groupby("tercile")["predicted_vol"].mean()
    assert predicted.max() - predicted.min() < 0.005, "the prediction is flat"
    idio = frame.groupby("tercile")["idio_share"].mean()
    assert idio.max() < 0.25, "the diagonal is a fifth of predicted variance at most"


@pytest.mark.integration
def test_3b_the_confound_is_measured_with_the_stored_realized_volatility() -> None:
    frame = load("confound")
    by_tercile = frame.groupby("tercile")[
        [
            "market_vol_forward",
            "book_realized_vol",
            "book_predicted_vol",
            "book_realized_vol_covariance_form",
        ]
    ].first()
    # the high-exposure months are also calmer in the market, so part of the
    # fall in realized book volatility is a period effect and is stated as such
    assert (
        by_tercile.loc["high", "market_vol_forward"]
        < by_tercile.loc["low", "market_vol_forward"]
    )
    assert by_tercile.loc["high", "book_realized_vol"] == pytest.approx(
        0.027775, abs=1e-5
    )
    assert by_tercile.loc["low", "book_realized_vol"] == pytest.approx(
        0.049093, abs=1e-5
    )
    # the covariance form disagrees in level, which is why the stored one wins
    assert (
        by_tercile.loc["high", "book_realized_vol_covariance_form"]
        > by_tercile.loc["high", "book_realized_vol"]
    )
    membership = frame.groupby("tercile")["months"].first()
    assert membership.sum() == 131, "three terciles over the labelled rebalances"


@pytest.mark.integration
def test_3c_the_covariance_between_the_two_components_is_negative_when_it_matters() -> (
    None
):
    frame = load("orthogonality")
    by_tercile = frame.groupby("tercile")[
        [
            "var_factor_component",
            "var_specific_component",
            "covariance",
            "correlation",
            "covariance_share_of_total",
        ]
    ].mean()
    assert by_tercile.loc["high", "covariance"] < 0, "the high tercile hedges"
    assert by_tercile.loc["high", "correlation"] < -0.05
    assert (
        by_tercile.loc["high", "covariance_share_of_total"] < -0.10
    ), "the negative covariance is material, not noise"
    # the factor component is larger than the model's factor part, so the
    # paradox is the covariance rather than an overstated factor part
    realized_factor_vol = np.sqrt(
        by_tercile.loc["high", "var_factor_component"] * 252.0
    )
    assert realized_factor_vol > 0.06


@pytest.mark.integration
def test_3d_the_half_life_sweep_does_not_rescue_the_bias() -> None:
    frame = load("sweep")
    by_bucket = frame.groupby(["half_life", "tercile"])["bias"].mean().unstack()
    for half_life in (21, 42, 90):
        assert (
            by_bucket.loc[half_life, "high"] < 0.8
        ), "no half-life brings the high tercile inside the band"
        assert by_bucket.loc[half_life, "low"] > 0.9, "the low tercile stays near one"
    spread = by_bucket.loc[90, "low"] - by_bucket.loc[90, "high"]
    assert spread == pytest.approx(
        0.398414, abs=1e-5
    ), "the half-life moves almost nothing"


@pytest.mark.integration
def test_3e_a_few_residual_directions_carry_most_of_the_specific_variance() -> None:
    frame = load("projection")
    by_tercile = frame.groupby("tercile")[
        [
            "top1_share",
            "top3_share",
            "top5_share",
            "top10_share",
            "effective_directions",
        ]
    ].mean()
    assert (
        by_tercile["top5_share"].min() > 0.5
    ), "five residual directions carry more than half the book's specific variance"
    assert by_tercile["effective_directions"].max() < 13
    assert by_tercile["top1_share"].mean() > 0.20
    assert (
        frame["n_above_edge"].mean() > 10
    ), "the residual spectrum is far above its own Marchenko-Pastur edge"
