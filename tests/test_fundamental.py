"""Sprint E3 Tasks 1 to 4: descriptors, standardization, WLS, FMPs, identification.

The recovery tests use a synthetic cross-section with known factor returns,
so the estimator is proven before it touches the real panel. The window and
shift tests are the ones the PRD names as design rules.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from efb.models import fundamental as fx

TICKERS = [f"T{i:02d}" for i in range(60)]
SECTOR_CYCLE = ("Energy", "Industrials", "Utilities")
SECTORS = pd.Series({name: SECTOR_CYCLE[i % 3] for i, name in enumerate(TICKERS)})
BETAS = pd.Series({name: 0.5 + 0.02 * i for i, name in enumerate(TICKERS)})
IDIO = 0.008


def _panel(n_days: int = 320, seed: int = 3) -> dict[str, pd.DataFrame]:
    idx = pd.bdate_range("2019-01-01", periods=n_days)
    rng = np.random.default_rng(seed)
    proxy = pd.Series(rng.normal(0.0004, 0.010, n_days), index=idx)
    returns = pd.DataFrame(
        {t: 0.0002 + BETAS[t] * proxy + rng.normal(0, IDIO, n_days) for t in TICKERS},
        index=idx,
    )
    close = pd.DataFrame(
        {t: 50.0 + np.arange(n_days) * 0.05 + i * 0.1 for i, t in enumerate(TICKERS)},
        index=idx,
    )
    volume = pd.DataFrame(1e6, index=idx, columns=TICKERS)
    market_cap = pd.DataFrame(
        {t: 1e9 * (i + 1) for i, t in enumerate(TICKERS)}, index=idx
    )
    return {
        "returns": returns,
        "close": close,
        "volume": volume,
        "market_cap": market_cap,
        "proxy": proxy,
    }


def test_market_cap_is_close_times_shares() -> None:
    close = pd.DataFrame(
        {"AAA": [10.0, 11.0]}, index=pd.bdate_range("2020-01-01", periods=2)
    )
    shares = pd.DataFrame({"AAA": [100.0, 200.0]}, index=close.index)
    mcap = fx.market_cap(close, shares)
    assert mcap["AAA"].tolist() == [1000.0, 2200.0]


def test_market_proxy_is_cap_weighted() -> None:
    idx = pd.bdate_range("2020-01-01", periods=3)
    returns = pd.DataFrame(
        {"AAA": [0.10, 0.0, 0.0], "BBB": [0.0, 0.10, 0.20]}, index=idx
    )
    mcap = pd.DataFrame(
        {"AAA": [100.0, 100.0, 100.0], "BBB": [300.0, 300.0, 300.0]}, index=idx
    )
    proxy = fx.market_proxy(returns, mcap)
    # the first day has no t-1 market cap by construction, so it is NaN
    assert np.isnan(proxy.iloc[0])
    # 0.25 * 0.00 + 0.75 * 0.10 on the second day
    assert proxy.iloc[1] == pytest.approx(0.075)
    assert proxy.iloc[2] == pytest.approx(0.15)


def test_size_is_the_log_of_lagged_market_cap() -> None:
    panel = _panel()
    raw = fx.raw_descriptors(
        returns=panel["returns"],
        close=panel["close"],
        volume=panel["volume"],
        market_cap=panel["market_cap"],
        proxy=panel["proxy"],
    )
    date = panel["returns"].index[100]
    previous = panel["market_cap"].loc[panel["returns"].index[99], "T00"]
    assert raw["size"].loc[date, "T00"] == pytest.approx(float(np.log(previous)))


def test_momentum_and_reversal_are_hand_computed() -> None:
    panel = _panel()
    returns = panel["returns"].copy()
    returns.loc[:, :] = 0.0
    returns.iloc[-40:-29, :] = 0.02  # rows t-40 to t-30
    returns.iloc[-25:, :] = 0.01  # rows t-24 to t
    raw = fx.raw_descriptors(
        returns=returns,
        close=panel["close"],
        volume=panel["volume"],
        market_cap=panel["market_cap"],
        proxy=panel["proxy"],
    )
    last = returns.index[-1]
    # reversal covers rows t-20 to t-1, all of which carry 1%, so it is
    # 1.01^20 - 1 and the 2% block is outside its window.
    assert raw["reversal"].loc[last, "T00"] == pytest.approx(1.01**20 - 1)
    # momentum covers rows t-251 to t-21: four 1% days (t-24 to t-21) and
    # eleven 2% days (t-40 to t-30).
    expected = 1.01**4 * 1.02**11 - 1
    assert raw["momentum"].loc[last, "T00"] == pytest.approx(expected)


def test_beta_recovers_a_known_beta() -> None:
    panel = _panel()
    raw = fx.raw_descriptors(
        returns=panel["returns"],
        close=panel["close"],
        volume=panel["volume"],
        market_cap=panel["market_cap"],
        proxy=panel["proxy"],
    )
    last = panel["returns"].index[-1]
    # Vasicek shrinkage moves a name only slightly at 252 observations, so
    # the recovered beta stays within 0.15 of the fixture's true value.
    assert raw["beta"].loc[last, "T59"] == pytest.approx(float(BETAS["T59"]), abs=0.15)
    assert raw["beta"].loc[last, "T00"] == pytest.approx(float(BETAS["T00"]), abs=0.15)


def test_residual_vol_recovers_a_known_residual_vol() -> None:
    panel = _panel()
    raw = fx.raw_descriptors(
        returns=panel["returns"],
        close=panel["close"],
        volume=panel["volume"],
        market_cap=panel["market_cap"],
        proxy=panel["proxy"],
    )
    last = panel["returns"].index[-1]
    # the fixture's idiosyncratic noise is 0.008 daily, annualized
    assert raw["resid_vol"].loc[last, "T00"] == pytest.approx(
        IDIO * np.sqrt(252), rel=0.35
    )


def test_liquidity_is_log_mean_dollar_volume() -> None:
    panel = _panel()
    panel["close"].loc[:, :] = 10.0
    panel["volume"].loc[:, :] = 1000.0
    raw = fx.raw_descriptors(
        returns=panel["returns"],
        close=panel["close"],
        volume=panel["volume"],
        market_cap=panel["market_cap"],
        proxy=panel["proxy"],
    )
    last = panel["returns"].index[-1]
    assert raw["liquidity"].loc[last, "T00"] == pytest.approx(float(np.log(10_000.0)))


def test_size_and_liquidity_are_nan_rather_than_infinite() -> None:
    """A zero market cap or a zero volume day is missing, never minus infinity."""
    panel = _panel()
    panel["market_cap"].loc[panel["market_cap"].index[100], "T00"] = 0.0
    panel["volume"].loc[panel["volume"].index[-70:], "T00"] = 0.0
    raw = fx.raw_descriptors(
        returns=panel["returns"],
        close=panel["close"],
        volume=panel["volume"],
        market_cap=panel["market_cap"],
        proxy=panel["proxy"],
    )
    assert np.isnan(raw["size"].loc[panel["market_cap"].index[101], "T00"])
    assert np.isnan(raw["liquidity"].loc[panel["volume"].index[-1], "T00"])
    for name in ("size", "liquidity"):
        assert not np.isinf(raw[name].to_numpy(dtype=float)).any(), name


def test_descriptors_do_not_read_the_future() -> None:
    """Changing the return on t must not move any descriptor dated t."""
    panel = _panel()
    before = fx.raw_descriptors(
        returns=panel["returns"],
        close=panel["close"],
        volume=panel["volume"],
        market_cap=panel["market_cap"],
        proxy=panel["proxy"],
    )
    changed = panel["returns"].copy()
    changed.iloc[-1, :] = changed.iloc[-1, :] + 0.05
    after = fx.raw_descriptors(
        returns=changed,
        close=panel["close"],
        volume=panel["volume"],
        market_cap=panel["market_cap"],
        proxy=panel["proxy"],
    )
    last = panel["returns"].index[-1]
    for name in fx.STYLE_NAMES:
        if name == "market":
            continue
        assert before[name].loc[last].equals(after[name].loc[last]), name


def test_standardize_zeroes_the_cap_weighted_mean_and_winsorizes() -> None:
    idx = pd.bdate_range("2020-01-01", periods=1)
    names = [f"T{i}" for i in range(6)]
    raw = pd.DataFrame(
        {name: [float(i + 1)] for i, name in enumerate(names)}, index=idx
    )
    raw["T5"] = 1000.0
    mask = pd.DataFrame(True, index=idx, columns=names)
    mcap = pd.DataFrame({name: [100.0] for name in names}, index=idx)
    mcap["T5"] = 500.0
    z, stats, winsorized = fx.standardize(raw, mask, mcap)
    row = z.iloc[0]
    weights = mcap.iloc[0] / mcap.iloc[0].sum()
    assert float((row * weights).sum()) == pytest.approx(0.0, abs=1e-12)
    assert stats.iloc[0]["n_names"] == 6
    # the outlier is winsorized, so its z is a clip boundary, not 800x
    assert abs(row["T5"]) < 4.0
    assert float(winsorized.iloc[0]["T5"]) == pytest.approx(stats.iloc[0]["upper"])


def test_orthogonalized_descriptor_is_uncorrelated_with_its_regressors() -> None:
    idx = pd.bdate_range("2020-01-01", periods=1)
    names = [f"T{i}" for i in range(6)]
    momentum = pd.DataFrame(
        {name: [float(i)] for i, name in enumerate(names)}, index=idx
    )
    beta = pd.DataFrame(
        {name: [float(i % 3)] for i, name in enumerate(names)}, index=idx
    )
    size = pd.DataFrame(
        {name: [float((i * 2) % 3)] for i, name in enumerate(names)}, index=idx
    )
    z = {"momentum": momentum, "beta": beta, "size": size}
    out = fx.orthogonalize(z, {"momentum": ["beta", "size"]})
    residual = out["momentum"].iloc[0]
    for regressor in (beta, size):
        column = regressor.iloc[0]
        assert float(np.corrcoef(residual, column)[0, 1]) == pytest.approx(
            0.0, abs=1e-10
        )
    assert out["beta"].equals(beta)


def _synthetic_cross_section(
    n_names: int = 60, k: int = 3, seed: int = 11
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    design = rng.normal(0, 1, (n_names, k))
    design[:, 0] = 1.0
    true_f = np.array([0.0010, 0.0020, -0.0015])
    returns = design @ true_f + rng.normal(0, 1e-9, n_names)
    weights = rng.uniform(1e8, 1e10, n_names)
    return design, returns, weights, true_f


def test_wls_recovers_known_factor_returns() -> None:
    design, returns, weights, true_f = _synthetic_cross_section()
    fit = fx.wls_fit(design, returns, weights)
    assert fit.factor_returns.tolist() == pytest.approx(true_f.tolist(), rel=1e-6)


def test_fmp_identity_holds_to_machine_precision() -> None:
    design, returns, weights, _ = _synthetic_cross_section()
    fit = fx.wls_fit(design, returns, weights)
    exposures = design.T @ fit.fmp_weights.T
    assert np.max(np.abs(exposures - np.eye(design.shape[1]))) < 1e-8


def test_fmp_rows_are_portfolios_that_reproduce_the_factor_return() -> None:
    design, returns, weights, _ = _synthetic_cross_section()
    fit = fx.wls_fit(design, returns, weights)
    assert fit.fmp_weights @ returns == pytest.approx(fit.factor_returns.tolist())


def test_identification_zeroes_the_cap_weighted_sector_return() -> None:
    rng = np.random.default_rng(5)
    n_styles, n_sectors = 1, 3
    estimated = rng.normal(0.001, 0.002, n_styles + n_sectors - 1)
    weights = np.array([0.2, 0.3, 0.5])
    identified = fx.identify(estimated, weights, n_styles)
    assert identified.sector.shape[0] == n_sectors
    assert float(identified.sector @ weights) == pytest.approx(0.0, abs=1e-18)


def test_identification_moves_the_cap_weighted_sector_mean_into_the_market() -> None:
    estimated = np.array([0.0010, 0.0004, -0.0002])
    weights = np.array([0.25, 0.35, 0.40])
    identified = fx.identify(estimated, weights, n_styles=1)
    shift = float(np.array([0.0004, -0.0002, 0.0]) @ weights)
    assert identified.market == pytest.approx(0.0010 + shift)
    assert identified.sector.tolist() == pytest.approx(
        [0.0004 - shift, -0.0002 - shift, -shift]
    )


def test_identification_leaves_fitted_values_untouched() -> None:
    """The reference sector loses exactly what the market factor gains."""
    rng = np.random.default_rng(9)
    n_names, n_sectors, n_styles = 60, 3, 1
    membership = rng.integers(0, n_sectors, n_names)
    # the reduced design: one dummy per sector except the reference sector
    reduced = np.zeros((n_names, n_styles + n_sectors - 1))
    reduced[:, 0] = 1.0
    for sector in range(n_sectors - 1):
        reduced[np.arange(n_names), n_styles + sector] = (membership == sector).astype(
            float
        )
    estimated = np.array([0.0010, 0.0004, -0.0002])
    weights = np.array([0.25, 0.35, 0.40])
    identified = fx.identify(estimated, weights, n_styles)
    # the reported design carries all eleven, here all three, sector dummies
    reported = np.zeros((n_names, n_styles + n_sectors))
    reported[:, 0] = 1.0
    for sector in range(n_sectors):
        reported[np.arange(n_names), n_styles + sector] = (membership == sector).astype(
            float
        )
    assert (reported @ identified.as_vector()).tolist() == pytest.approx(
        (reduced @ estimated).tolist(), abs=1e-15
    )


def test_identification_satisfies_the_constrained_normal_equations() -> None:
    """The reported factor returns reproduce the same fit and the constraint."""
    rng = np.random.default_rng(17)
    n_names, n_styles, n_sectors = 40, 2, 3
    membership = rng.integers(0, n_sectors, n_names)
    design = np.zeros((n_names, n_styles + n_sectors - 1))
    design[:, 0] = 1.0
    design[:, 1:n_styles] = rng.normal(0, 1, (n_names, n_styles - 1))
    for sector in range(n_sectors - 1):
        design[np.arange(n_names), n_styles + sector] = (membership == sector).astype(
            float
        )
    returns = rng.normal(0, 0.01, n_names)
    weights = rng.uniform(1e8, 1e10, n_names)
    totals = np.array([weights[membership == s].sum() for s in range(n_sectors)])
    sector_weights = totals / totals.sum()

    fit = fx.wls_fit(design, returns, weights)
    identified = fx.identify(fit.factor_returns, sector_weights, n_styles=n_styles)
    vector = identified.as_vector()
    # (a) the constraint holds
    assert float(vector[n_styles:] @ sector_weights) == pytest.approx(0.0, abs=1e-18)
    # (b) the reported factor returns reproduce the fitted values through the
    #     reported design
    reported = np.zeros((n_names, n_styles + n_sectors))
    reported[:, :n_styles] = design[:, :n_styles]
    for sector in range(n_sectors):
        reported[np.arange(n_names), n_styles + sector] = (membership == sector).astype(
            float
        )
    assert (reported @ vector).tolist() == pytest.approx(
        (design @ fit.factor_returns).tolist(), abs=1e-12
    )
    # (c) the weighted normal equations still hold
    gradient = design.T @ (weights * (returns - design @ fit.factor_returns))
    assert float(np.max(np.abs(gradient))) < 1e-9 * float(np.max(np.abs(weights)))


def test_specific_returns_plus_fitted_equals_returns() -> None:
    design, returns, weights, _ = _synthetic_cross_section()
    fit = fx.wls_fit(design, returns, weights)
    assert fit.fitted + fit.specific == pytest.approx(returns.tolist(), abs=1e-16)


def test_weighted_r_squared_is_one_for_a_noiseless_fit() -> None:
    rng = np.random.default_rng(21)
    n_names, k = 30, 3
    design = rng.normal(0, 1, (n_names, k))
    design[:, 0] = 1.0
    returns = design @ np.array([0.001, 0.002, -0.001])
    weights = rng.uniform(1e8, 1e10, n_names)
    fit = fx.wls_fit(design, returns, weights)
    assert fit.r_squared == pytest.approx(1.0)


def test_design_matrix_flags_missing_descriptors() -> None:
    idx = pd.bdate_range("2020-01-01", periods=1)
    names = [f"T{i}" for i in range(60)]
    style = {
        name: pd.DataFrame(1.0, index=idx, columns=names) for name in fx.STYLE_NAMES
    }
    style["size"].loc[idx[0], names[-1]] = np.nan
    returns = pd.DataFrame(1.0, index=idx, columns=names)
    sectors = pd.Series({name: SECTOR_CYCLE[i % 3] for i, name in enumerate(names)})
    day = fx.build_cross_section(
        date=idx[0],
        styles=style,
        returns=returns,
        mcap=pd.DataFrame(1e9, index=idx, columns=names),
        sectors=sectors,
    )
    assert day is not None
    assert names[-1] not in day.tickers
    assert len(day.tickers) == 59


@pytest.mark.slow
def test_full_design_has_a_constant_for_the_market() -> None:
    panel = _panel()
    result = fx.build_design(
        returns=panel["returns"],
        close=panel["close"],
        volume=panel["volume"],
        market_cap=panel["market_cap"],
        sectors=SECTORS,
        proxy=panel["proxy"],
    )
    assert result.factor_names[:7] == list(fx.STYLE_NAMES)
    assert len(result.factor_names) == 7 + 11
    last = result.days[-1]
    assert last.design is not None
    market_column = last.design[:, result.factor_names.index("market")]
    assert np.all(market_column == 1.0)
    sector_block = last.design[:, 7:]
    assert np.all(sector_block.sum(axis=1) == 1.0)
    # the market descriptor is the constant column, so it is not standardized
    assert result.standardized["market"].loc[last.date].nunique() == 1
    assert float(result.standardized["market"].loc[last.date].iloc[0]) == 1.0


@pytest.mark.slow
def test_shift_test_reports_the_two_vintages_and_their_difference() -> None:
    panel = _panel()
    design = fx.build_design(
        returns=panel["returns"],
        close=panel["close"],
        volume=panel["volume"],
        market_cap=panel["market_cap"],
        sectors=SECTORS,
        proxy=panel["proxy"],
    )
    summary = fx.shift_test(design)
    assert summary["shift_test_days"] == len(design.days) - 1
    assert summary["shift_test_lagged_mean_r_squared"] > 0
    assert summary["shift_test_dated_t_mean_r_squared"] > 0
    assert summary["shift_test_difference"] == pytest.approx(
        summary["shift_test_dated_t_mean_r_squared"]
        - summary["shift_test_lagged_mean_r_squared"],
        rel=1e-12,
    )
    # the lagged mean is the model's own mean R squared on the paired days
    assert (
        abs(
            summary["shift_test_lagged_mean_r_squared"]
            - float(
                pd.Series(
                    [
                        fx.wls_fit(
                            day.design,
                            day.returns,
                            day.weights,
                        ).r_squared
                        for day in design.days[:-1]
                    ]
                ).mean()
            )
        )
        < 5e-3
    )


def test_the_size_descriptor_of_the_next_day_contains_that_days_return() -> None:
    # a price path and the returns it implies, so the identity is checkable
    idx = pd.bdate_range("2020-01-01", periods=8)
    returns = pd.DataFrame(
        {"AAA": [0.02, -0.01, 0.005, 0.0, -0.03, 0.04, 0.001, -0.002]}, index=idx
    )
    close = 100.0 * (1.0 + returns).cumprod()
    volume = pd.DataFrame(1e6, index=idx, columns=returns.columns)
    market_cap = close.copy()
    proxy = close.pct_change().fillna(0.0).squeeze()

    raw = fx.raw_descriptors(returns, close, volume, market_cap, proxy)

    first, second = idx[2], idx[3]
    change = float(raw["size"].loc[second, "AAA"] - raw["size"].loc[first, "AAA"])
    explained = float(np.log1p(returns.loc[first, "AAA"]))
    # size is log(market cap shifted one row), so its one day change is the log
    # of the price ratio, which is the return the later design would explain
    assert change == pytest.approx(explained, rel=1e-12)
    assert change != 0.0
