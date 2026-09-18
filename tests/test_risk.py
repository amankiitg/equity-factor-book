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


def test_exposure_series_carries_the_book_label() -> None:
    day = _cross_section()
    weights = _weights(day)
    out = exposure_series({day.date: day}, {day.date: weights}, FACTORS, book="seed_ew")
    assert set(out["book"]) == {"seed_ew"}
    two = pd.concat(
        [
            exposure_series(
                {day.date: day}, {day.date: weights}, FACTORS, book="seed_ew"
            ),
            exposure_series(
                {day.date: day}, {day.date: weights}, FACTORS, book="seed_mom_ls"
            ),
        ],
        ignore_index=True,
    )
    # the same weights under two book labels are two distinguishable series
    assert two.groupby("book")["exposure"].sum().nunique() == 1
    assert not two.duplicated(["book", "date", "factor"]).any()


def _two_books(n_months: int = 9) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two books on the same dates with different exposure distributions."""
    dates = pd.date_range("2016-01-31", periods=n_months, freq="ME")
    spans = {"seed_ew": (-1.0, 1.0), "seed_mom_ls": (0.0, 2.0)}
    bias_rows: list[dict[str, object]] = []
    exposure_rows: list[dict[str, object]] = []
    for book, (low, high) in spans.items():
        for exposure, date in zip(np.linspace(low, high, n_months), dates, strict=True):
            predicted = 0.05 + 0.05 * max(exposure, 0.0)
            bias_rows.append(
                {
                    "book": book,
                    "date": date,
                    "predicted_vol_ann": predicted,
                    "realized_vol_ann": 0.05,
                    "bias_ratio": 0.05 / predicted,
                    "factor_share": 0.5,
                    "n_names": 100,
                    "residual_weight": 0.0,
                }
            )
            exposure_rows.append(
                {
                    "book": book,
                    "date": date,
                    "factor": "momentum",
                    "exposure": exposure,
                }
            )
    return pd.DataFrame(bias_rows), pd.DataFrame(exposure_rows)


def test_bias_by_exposure_uses_each_books_own_exposure() -> None:
    from efb.risk import bias_by_exposure

    bias, exposure = _two_books()
    table = bias_by_exposure(bias, exposure)
    assert set(table["book"]) == {"seed_ew", "seed_mom_ls"}
    assert table["n_months"].sum() == len(bias)
    means = table.pivot(index="bucket", columns="book", values="exposure_mean").loc[
        ["low", "mid", "high"]
    ]
    # each book is split on its own exposure, so the bucket means differ
    assert not np.allclose(means["seed_ew"], means["seed_mom_ls"])
    assert means["seed_ew"].is_monotonic_increasing
    assert means["seed_mom_ls"].is_monotonic_increasing
    # a book split on its own exposure can only see its own months
    assert (table.groupby("book")["n_months"].sum() == len(bias) / 2).all()


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


def _bias_frame(n_months: int = 12) -> pd.DataFrame:
    """A monthly bias frame with a known relation to exposure."""
    dates = pd.date_range("2016-01-31", periods=n_months, freq="ME")
    exposure = np.linspace(-0.5, 1.0, n_months)
    # predicted volatility rises with exposure, realized does not: the bias
    # therefore falls as exposure rises, which is the pattern the tercile
    # table has to expose
    predicted = 0.05 + 0.05 * np.maximum(exposure, 0.0)
    realized = np.full(n_months, 0.05)
    rows = []
    columns = zip(dates, predicted, realized, strict=True)
    for date, pred, real in columns:
        rows.append(
            {
                "book": "seed_mom_ls",
                "date": date,
                "predicted_vol_ann": pred,
                "realized_vol_ann": real,
                "bias_ratio": real / pred,
                "factor_share": 0.5,
                "n_names": 100,
                "residual_weight": 0.0,
            }
        )
    return pd.DataFrame(rows)


def _exposure_frame(bias: pd.DataFrame, factor: str = "momentum") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "book": bias["book"],
            "date": bias["date"],
            "factor": factor,
            "exposure": np.linspace(-0.5, 1.0, len(bias)),
        }
    )


def test_bias_by_exposure_orders_the_buckets_by_exposure() -> None:
    from efb.risk import bias_by_exposure

    bias = _bias_frame()
    table = bias_by_exposure(bias, _exposure_frame(bias))
    assert list(table["bucket"]) == ["low", "mid", "high"]
    assert table["n_months"].sum() == len(bias)
    means = table.set_index("bucket")["exposure_mean"]
    assert means["low"] < means["mid"] < means["high"]
    # the fixture predicts poorly only where the exposure is high
    bias_means = table.set_index("bucket")["bias_mean"]
    assert bias_means["low"] > bias_means["high"]
    assert table["share_in_band"].between(0.0, 1.0).all()


def test_bias_by_exposure_is_flat_when_the_model_is_right() -> None:
    from efb.risk import bias_by_exposure

    bias = _bias_frame()
    bias["predicted_vol_ann"] = 0.05
    bias["bias_ratio"] = 1.0
    table = bias_by_exposure(bias, _exposure_frame(bias))
    assert np.allclose(table["bias_mean"], 1.0)
    assert np.allclose(table["share_in_band"], 1.0)


def test_coverage_by_year_is_one_minus_the_residual_weight() -> None:
    from efb.risk import coverage_by_year

    bias = _bias_frame()
    decomposition = pd.DataFrame(
        {
            "book": ["seed_mom_ls"] * len(bias),
            "date": bias["date"],
            "residual_weight": np.linspace(0.0, 0.5, len(bias)),
            "n_names": 100,
        }
    )
    table = coverage_by_year(bias, decomposition)
    assert table["year"].tolist() == [2016]
    assert table["n_months"].tolist() == [len(bias)]
    assert table["coverage_mean"].iloc[0] == pytest.approx(1.0 - 0.25, rel=1e-9)
    assert table["coverage_max"].iloc[0] == pytest.approx(1.0)
    assert table["coverage_min"].iloc[0] == pytest.approx(0.5)


def test_coverage_by_year_treats_a_missing_row_as_full_exposure() -> None:
    from efb.risk import coverage_by_year

    bias = _bias_frame()
    decomposition = pd.DataFrame(
        {
            "book": ["seed_mom_ls"],
            "date": [bias["date"].iloc[0]],
            "residual_weight": [0.0],
            "n_names": [100],
        }
    )
    table = coverage_by_year(bias, decomposition)
    assert table["n_months"].iloc[0] == len(bias)
    # eleven of twelve months have no decomposition row, so coverage is zero
    # there rather than silently one
    assert table["coverage_mean"].iloc[0] == pytest.approx(1.0 / 12.0)
