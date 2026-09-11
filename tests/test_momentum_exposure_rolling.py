"""Tests for close-out task C8: momentum exposure from rolling betas.

The C4 finding was that the momentum book looks 90 percent idiosyncratic
under a static name-level decomposition. That number cannot be right for a
book that is re-sorted every month: the weights change at each rebalance
and a full-sample beta does not, so the two never meet on the same date.
C8 measures the book's MOM exposure at each rebalance from rolling 252-day
name-level betas, and separately gives the diagonal model's bias statistic
for the book on a 21-day forward window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from efb import portfolios as pf


def _weights(dates: pd.DatetimeIndex, long: str, short: str) -> pd.DataFrame:
    frame = pd.DataFrame(0.0, index=dates, columns=["A", "B", "C", "D"])
    frame[long] = 0.5
    frame[short] = -0.5
    return frame


def _panel(dates: pd.DatetimeIndex, values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(values, index=dates, dtype=float)


def _covariance(factor: str = "mom", variance: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame([[variance]], index=[factor], columns=[factor])


def test_exposure_is_the_weighted_average_of_the_names_held() -> None:
    dates = pd.bdate_range("2023-01-02", periods=90)
    weights = _weights(dates, "A", "D")
    betas = {"mom": _panel(dates, {"A": 1.2, "B": 0.0, "C": 0.0, "D": 0.2})}
    idio = pd.DataFrame(0.0, index=dates, columns=["A", "B", "C", "D"])
    out = pf.rolling_book_exposure(weights, betas, _covariance(), idio, factor="mom")
    assert not out.empty
    # 0.5 * 1.2 + (-0.5) * 0.2 = 0.5
    assert (
        out["exposure"].iloc[0] == np.float64(0.5).item()
        or abs(out["exposure"].iloc[0] - 0.5) < 1e-12
    )
    assert out["gross"].iloc[0] == 1.0
    assert out["net"].iloc[0] == 0.0


def test_exposure_follows_the_weights_when_they_turn_over() -> None:
    """The whole point: the number tracks the book, not a static beta set.

    The betas are constant, so a static aggregate would report the same
    exposure on every date. The weights change at the second rebalance, so
    the exposure has to change with them.
    """
    dates = pd.bdate_range("2023-01-02", periods=130)
    weights = _weights(dates, "A", "D")
    turn = pd.bdate_range("2023-01-02", periods=130)[60]
    weights.loc[weights.index >= turn] = 0.0
    weights.loc[weights.index >= turn, "C"] = 0.5
    weights.loc[weights.index >= turn, "D"] = -0.5
    betas = {"mom": _panel(dates, {"A": 1.2, "B": 0.0, "C": -0.4, "D": 0.2})}
    idio = pd.DataFrame(0.0, index=dates, columns=["A", "B", "C", "D"])
    out = pf.rolling_book_exposure(weights, betas, _covariance(), idio, factor="mom")
    assert out["exposure"].nunique() > 1
    assert out["exposure"].max() > out["exposure"].min()


def test_the_share_uses_the_whole_factor_set() -> None:
    dates = pd.bdate_range("2023-01-02", periods=90)
    weights = _weights(dates, "A", "D")
    betas = {
        "mom": _panel(dates, {"A": 1.0, "B": 0.0, "C": 0.0, "D": -1.0}),
        "mkt_rf": _panel(dates, {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0}),
    }
    cov = pd.DataFrame(
        [[1.0, 0.0], [0.0, 1.0]], index=["mom", "mkt_rf"], columns=["mom", "mkt_rf"]
    )
    idio = pd.DataFrame(1.0, index=dates, columns=["A", "B", "C", "D"])
    out = pf.rolling_book_exposure(weights, betas, cov, idio, factor="mom")
    row = out.iloc[0]
    # factor variance = (0.5 * 1.0 + (-0.5) * (-1.0))^2 = 1.0
    # idio variance   = 0.25 + 0.25 = 0.5
    assert abs(row["factor_variance"] - 1.0) < 1e-12
    assert abs(row["idio_variance"] - 0.5) < 1e-12
    assert abs(row["factor_share"] - 1.0 / 1.5) < 1e-12


def test_a_missing_factor_is_skipped_not_guessed() -> None:
    dates = pd.bdate_range("2023-01-02", periods=90)
    weights = _weights(dates, "A", "D")
    idio = pd.DataFrame(0.0, index=dates, columns=["A", "B", "C", "D"])
    out = pf.rolling_book_exposure(
        weights, {"mkt_rf": _panel(dates, {"A": 1.0})}, _covariance("mkt_rf"), idio
    )
    assert out.empty


def test_biases_are_measured_over_the_month_for_a_monthly_book() -> None:
    """C8(b): the momentum book's own history, 21 days forward."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2021-01-01", periods=800)
    tickers = [f"T{i:02d}" for i in range(10)]
    returns = pd.DataFrame(
        rng.normal(0.0, 0.01, size=(len(dates), len(tickers))),
        index=dates,
        columns=tickers,
    )
    weights = pd.DataFrame(0.1, index=dates, columns=tickers)
    weights.iloc[:, 5:] = -0.1
    betas = pd.DataFrame(1.0, index=dates, columns=tickers)
    factor_var = pd.Series(0.0001, index=dates)
    idio_var = pd.DataFrame(0.0001, index=dates, columns=tickers)
    history = pf.portfolio_risk_history(
        weights, returns, betas, factor_var, idio_var, forward=21
    )
    assert not history.empty
    assert {"bias_ratio", "predicted_vol_ann", "realized_vol_ann"} <= set(
        history.columns
    )
    # the first date with 21 forward days has to be at least 21 rows in
    assert (history.index.max() - history.index.min()).days > 300


def test_a_rebalance_with_no_betas_is_skipped_not_zeroed() -> None:
    """A missing beta is not evidence of no exposure.

    The rolling beta needs a year of data, so the first few rebalances have
    no betas at all. Treating those as zero exposure would put a fabricated
    number in the series and drag its mean toward zero.
    """
    dates = pd.bdate_range("2023-01-02", periods=100)
    weights = _weights(dates, "A", "D")
    betas = {
        "mom": pd.DataFrame(
            np.nan, index=dates, columns=["A", "B", "C", "D"], dtype=float
        )
    }
    idio = pd.DataFrame(0.0, index=dates, columns=["A", "B", "C", "D"])
    out = pf.rolling_book_exposure(weights, betas, _covariance(), idio, factor="mom")
    assert out.empty
