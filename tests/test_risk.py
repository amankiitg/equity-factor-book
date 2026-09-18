"""Sprint E3 Tasks 5, 8 and 9: Sigma, the Euler decomposition, realized
residual covariance and the exposure time series.

Every identity is checked against an explicitly formed covariance matrix, so
the decomposition is proven against linear algebra rather than against
itself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from efb.models import fundamental as fx
from efb.risk import (
    RiskDecomposition,
    decompose,
    decomposition_frame,
    exposure_series,
    realized_idio_variance,
    realized_residual_covariance,
)

FACTORS = ["market", "size", "sector_10", "sector_20"]


def _cross_section(n_names: int = 20, seed: int = 5) -> fx.CrossSection:
    rng = np.random.default_rng(seed)
    tickers = pd.Index([f"T{i:02d}" for i in range(n_names)])
    design = np.column_stack(
        [
            np.ones(n_names),
            rng.normal(0, 1, n_names),
            np.zeros(n_names),
            np.zeros(n_names),
        ]
    )
    membership = rng.integers(0, 2, n_names)
    design[np.arange(n_names), 2 + membership] = 1.0
    sectors = np.where(membership == 0, "Energy", "Industrials")
    return fx.CrossSection(
        date=pd.Timestamp("2020-06-30"),
        tickers=tickers,
        design=design,
        weights=rng.uniform(1e9, 1e11, n_names),
        returns=rng.normal(0.0004, 0.01, n_names),
        sector_names=sectors,
    )


def _covariance(day: fx.CrossSection, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    loadings = rng.normal(0, 0.02, (len(FACTORS), len(FACTORS)))
    covariance = loadings @ loadings.T + np.eye(len(FACTORS)) * 1e-6
    return pd.DataFrame(covariance * 1e-4, index=FACTORS, columns=FACTORS)


def _specific_var(day: fx.CrossSection, value: float = 4e-4) -> pd.Series:
    return pd.Series(value, index=day.tickers)


def _explicit_sigma(
    day: fx.CrossSection, factor_cov: pd.DataFrame, specific: pd.Series
) -> np.ndarray:
    covariance = factor_cov.reindex(index=FACTORS, columns=FACTORS).to_numpy()
    return day.design @ covariance @ day.design.T + np.diag(
        specific.reindex(day.tickers).to_numpy()
    )


def _weights(day: fx.CrossSection) -> pd.Series:
    rng = np.random.default_rng(11)
    raw = rng.normal(0, 1, len(day.tickers))
    return pd.Series(raw / np.abs(raw).sum(), index=day.tickers)


def test_factorial_and_idio_variance_equals_the_quadratic_form() -> None:
    day = _cross_section()
    factor_cov = _covariance(day)
    specific = _specific_var(day)
    weights = _weights(day)
    result = decompose("book", day.date, weights, day, factor_cov, specific)
    sigma = _explicit_sigma(day, factor_cov, specific)
    w = weights.reindex(day.tickers).to_numpy(dtype=float)
    expected = float(w @ sigma @ w)
    assert result.total_variance == pytest.approx(expected, rel=1e-10)
    assert result.factor_variance + result.idio_variance == pytest.approx(
        result.total_variance, rel=1e-12
    )
    assert result.sigma_p == pytest.approx(float(np.sqrt(expected)), rel=1e-12)


def test_contributions_sum_to_the_portfolio_volatility() -> None:
    day = _cross_section()
    result = decompose(
        "book", day.date, _weights(day), day, _covariance(day), _specific_var(day)
    )
    assert float(result.contribution.sum()) == pytest.approx(result.sigma_p, rel=1e-10)


def test_mcr_matches_the_explicit_matrix_product() -> None:
    day = _cross_section()
    factor_cov = _covariance(day)
    specific = _specific_var(day)
    weights = _weights(day)
    result = decompose("book", day.date, weights, day, factor_cov, specific)
    sigma = _explicit_sigma(day, factor_cov, specific)
    w = weights.reindex(day.tickers).to_numpy(dtype=float)
    expected = sigma @ w / float(np.sqrt(w @ sigma @ w))
    assert result.mcr.to_numpy() == pytest.approx(expected, rel=1e-10)


def test_percent_of_variance_sums_to_one() -> None:
    day = _cross_section()
    result = decompose(
        "book", day.date, _weights(day), day, _covariance(day), _specific_var(day)
    )
    assert float(result.percent_of_variance.sum()) == pytest.approx(1.0, rel=1e-10)
    assert result.factor_share + result.idio_share == pytest.approx(1.0, rel=1e-12)


def test_names_with_no_descriptor_row_are_reported_as_residual_weight() -> None:
    day = _cross_section()
    weights = _weights(day)
    weights["NOT_IN_DESIGN"] = 0.25
    result = decompose(
        "book", day.date, weights, day, _covariance(day), _specific_var(day)
    )
    assert result.residual_weight == pytest.approx(0.25)
    assert result.n_names == len(day.tickers)
    assert "NOT_IN_DESIGN" not in result.mcr.index


def test_top_mcr_names_are_ordered_by_magnitude() -> None:
    day = _cross_section()
    result = decompose(
        "book",
        day.date,
        _weights(day),
        day,
        _covariance(day),
        _specific_var(day),
        top_n=5,
    )
    magnitudes = [abs(value) for _, value in result.top_mcr]
    assert magnitudes == sorted(magnitudes, reverse=True)
    assert len(result.top_mcr) == 5


def test_decomposition_frame_carries_both_levels() -> None:
    day = _cross_section()
    result = decompose(
        "book", day.date, _weights(day), day, _covariance(day), _specific_var(day)
    )
    frame = decomposition_frame(result)
    assert set(frame["level"]) == {"factor", "name"}
    assert set(frame.loc[frame["level"] == "factor", "factor"]) == set(FACTORS)
    assert frame["sigma_p"].nunique() == 1
    assert len(frame.loc[frame["level"] == "name"]) == len(day.tickers)


def test_realized_residual_covariance_recovers_a_common_factor() -> None:
    rng = np.random.default_rng(19)
    dates = pd.bdate_range("2020-01-01", periods=300)
    names = [f"T{i}" for i in range(8)]
    common = rng.normal(0, 0.01, (300, 1))
    values = common @ np.ones((1, 8)) * 0.7 + rng.normal(0, 0.005, (300, 8))
    specific = pd.DataFrame(values, index=dates, columns=names)
    covariance = realized_residual_covariance(specific, dates[-1], window=252)
    off_diagonal = covariance.to_numpy()[np.triu_indices(8, 1)]
    assert np.mean(np.abs(off_diagonal)) > 1e-5
    # the diagonal-only model would miss that entirely
    assert np.mean(np.abs(off_diagonal)) > 0.1 * np.mean(np.diag(covariance))


def test_realized_covariance_ignores_data_after_the_end_date() -> None:
    rng = np.random.default_rng(23)
    dates = pd.bdate_range("2020-01-01", periods=300)
    names = ["AAA", "BBB"]
    frame = pd.DataFrame(rng.normal(0, 0.01, (300, 2)), index=dates, columns=names)
    before = realized_residual_covariance(frame, dates[259], window=252)
    bumped = frame.copy()
    bumped.iloc[260:] = 0.5
    after = realized_residual_covariance(bumped, dates[259], window=252)
    assert before.to_numpy() == pytest.approx(after.to_numpy())


def test_realized_idio_variance_behaves_differently_for_the_two_books() -> None:
    """A long-only book and a dollar-neutral book need opposite comments.

    With positively correlated specific returns the diagonal D understates a
    long-only book's idio risk and overstates a dollar-neutral book's, because
    in the second case the common component cancels. That asymmetry is what
    F3.8's two-way reporting exists to expose.
    """
    rng = np.random.default_rng(29)
    dates = pd.bdate_range("2020-01-01", periods=300)
    names = [f"T{i}" for i in range(6)]
    common = rng.normal(0, 0.01, (300, 1))
    specific = pd.DataFrame(
        common @ np.ones((1, 6)) + rng.normal(0, 0.002, (300, 6)),
        index=dates,
        columns=names,
    )
    covariance = realized_residual_covariance(specific, dates[-1], window=252)
    diagonal = pd.Series(np.diag(covariance), index=names)
    long_only = pd.Series(1.0 / 6.0, index=names)
    long_short = pd.Series([1.0, 1.0, 1.0, -1.0, -1.0, -1.0], index=names) / 6.0
    assert realized_idio_variance(long_only, covariance) > float(
        (long_only**2 * diagonal).sum()
    )
    assert realized_idio_variance(long_short, covariance) < float(
        (long_short**2 * diagonal).sum()
    )


def test_exposure_series_is_linear_in_the_weights() -> None:
    day = _cross_section()
    weights = _weights(day)
    doubled = weights * 2.0
    single = exposure_series({day.date: day}, {day.date: weights}, FACTORS)
    twice = exposure_series({day.date: day}, {day.date: doubled}, FACTORS)
    merged = single.merge(twice, on="factor", suffixes=("_1", "_2"))
    assert (merged["exposure_1"] * 2).tolist() == pytest.approx(
        merged["exposure_2"].tolist()
    )
    assert set(merged["factor"]) == set(FACTORS)


def test_exposure_series_skips_dates_without_a_design() -> None:
    day = _cross_section()
    weights = _weights(day)
    other = pd.Timestamp("2020-07-31")
    out = exposure_series({day.date: day}, {day.date: weights, other: weights}, FACTORS)
    assert set(out["date"]) == {day.date}


def test_decomposition_reports_the_factor_breakdown_of_variance() -> None:
    day = _cross_section()
    factor_cov = _covariance(day)
    specific = _specific_var(day)
    result = decompose("book", day.date, _weights(day), day, factor_cov, specific)
    contributions = []
    for factor in FACTORS:
        exposure = float(result.exposures[factor])
        factor_cov_row = factor_cov.loc[factor].to_numpy()
        contributions.append(
            exposure * float(factor_cov_row @ result.exposures.to_numpy())
        )
    assert float(np.sum(contributions)) == pytest.approx(
        result.factor_variance, rel=1e-10
    )


def test_decomposition_type_is_stable() -> None:
    day = _cross_section()
    result = decompose(
        "book", day.date, _weights(day), day, _covariance(day), _specific_var(day)
    )
    assert isinstance(result, RiskDecomposition)
    assert result.book == "book"
