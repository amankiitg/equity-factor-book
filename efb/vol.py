"""Volatility estimators and forecast evaluation (Sprint E2, Task 4).

Estimators, all forecasts for date t using information through t-1:

- EWMA: sigma_t^2 = lambda sigma_{t-1}^2 + (1 - lambda) r_{t-1}^2,
  lambda in {0.94, 0.97} (INPUT: returns.parquet r).
- Realized: trailing sample variance over a window ending t-1
  (windows 21 and 63), annualized by 252 where stated.
- GARCH(1,1): sigma_t^2 = omega + a r_{t-1}^2 + b sigma_{t-1}^2, fit via
  the arch package on the in-sample window, forecasts with fixed
  parameters.

Evaluation: QLIKE(sigma_hat_t, r_t) = ln sigma_hat_t^2 + r_t^2 /
sigma_hat_t^2, averaged out of sample; Mincer-Zarnowitz regression
r_t^2 = a + b sigma_hat_t^2 + e. Variance units are daily decimals, so
QLIKE levels are comparable across methods but not to other scales.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

LAMBDAS = (0.94, 0.97)
REALIZED_WINDOWS = (21, 63)
BASELINE_WINDOW = 252
ANNUALIZATION = 252


def _frame(x: pd.Series | pd.DataFrame) -> pd.DataFrame:
    return x.to_frame() if isinstance(x, pd.Series) else x


def _same_type(out: pd.DataFrame, original: pd.Series | pd.DataFrame):
    return out.iloc[:, 0] if isinstance(original, pd.Series) else out


def ewma_vol(
    r: pd.Series | pd.DataFrame, lam: float = 0.94, min_obs: int = 60
) -> pd.Series | pd.DataFrame:
    """EWMA variance forecast for date t from returns through t-1.

    Initialized at the sample variance of the first min_obs returns so the
    recursion is never seeded with a look-ahead estimate.
    """
    rf = _frame(r).astype(float)
    out = pd.DataFrame(np.nan, index=rf.index, columns=rf.columns)
    values = rf.to_numpy()
    state = np.full(rf.shape[1], np.nan)
    for i in range(rf.shape[0]):
        if i >= min_obs:
            out.iloc[i] = state
        row = values[i]
        valid = np.isfinite(row)
        if i == min_obs - 1:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                state = np.nanvar(values[: min_obs], axis=0)
        elif i >= min_obs:
            state = np.where(
                np.isfinite(state),
                lam * state + (1.0 - lam) * np.where(valid, row, np.nan) ** 2,
                state,
            )
    return _same_type(out, r)


def realized_vol(
    r: pd.Series | pd.DataFrame,
    window: int = 21,
    annualize: bool = True,
    min_obs: int | None = None,
) -> pd.Series | pd.DataFrame:
    """Trailing volatility over the window ending t-1, forecast for t."""
    rf = _frame(r).astype(float)
    min_periods = window if min_obs is None else min_obs
    shifted = rf.shift(1)
    out = shifted.rolling(window, min_periods=min_periods).std(ddof=1)
    if annualize:
        out = out * np.sqrt(ANNUALIZATION)
    return _same_type(out, r)


def realized_var(
    r: pd.Series | pd.DataFrame,
    window: int = 21,
    min_obs: int | None = None,
) -> pd.Series | pd.DataFrame:
    """Trailing sample variance over the window ending t-1, forecast for t."""
    vol_ = realized_vol(r, window=window, annualize=False, min_obs=min_obs)
    return vol_**2


def qlike(
    sigma2_hat: pd.Series | pd.DataFrame, r: pd.Series | pd.DataFrame
) -> pd.Series | pd.DataFrame:
    """QLIKE loss: ln sigma_hat^2 + r^2 / sigma_hat^2.

    Variance forecasts and returns are aligned by index; a Series and a
    Series are combined elementwise regardless of their names.
    """
    if isinstance(sigma2_hat, pd.Series) and isinstance(r, pd.Series):
        s2, rr = sigma2_hat.align(r, join="outer")
        s2 = s2.astype(float)
        rr = rr.astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.log(s2) + rr**2 / s2
    s2 = _frame(sigma2_hat).astype(float)
    rf = _frame(r).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.log(s2) + rf**2 / s2
    return _same_type(out, sigma2_hat)


@dataclass
class MZResult:
    alpha: float
    beta: float
    r_squared: float
    n_obs: int


def mincer_zarnowitz(
    r2: pd.Series, sigma2_hat: pd.Series
) -> MZResult:
    """Mincer-Zarnowitz regression of r^2 on the forecast variance."""
    frame = pd.concat([r2.rename("r2"), sigma2_hat.rename("s2")], axis=1).dropna()
    if len(frame) < 10:
        return MZResult(float("nan"), float("nan"), float("nan"), len(frame))
    y = frame["r2"].to_numpy(dtype=float)
    x = frame["s2"].to_numpy(dtype=float)
    x_mat = np.column_stack([np.ones(len(x)), x])
    beta = np.linalg.lstsq(x_mat, y, rcond=None)[0]
    resid = y - x_mat @ beta
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2_fit = 1.0 - float(resid @ resid) / ss_tot if ss_tot > 0 else float("nan")
    return MZResult(float(beta[0]), float(beta[1]), r2_fit, len(frame))


def fit_garch(r: pd.Series) -> dict[str, float] | None:
    """Fit GARCH(1,1) with the arch package; None when unavailable or failing.

    Returns omega, alpha, beta, persistence (alpha + beta) and the
    unconditional variance. Returns are scaled by 100 for numerical
    stability and the variance is converted back to decimal units.
    """
    try:
        from arch import arch_model
    except Exception:  # pragma: no cover - depends on the environment
        return None
    series = r.dropna().to_numpy(dtype=float) * 100.0
    if len(series) < 250:
        return None
    try:
        model = arch_model(series, vol="Garch", p=1, q=1, mean="Constant", dist="normal")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = model.fit(disp="off", show_warning=False)
    except Exception:  # pragma: no cover - numerical failures are recorded, not fatal
        return None
    omega = float(result.params.get("omega", np.nan)) / 1e4
    alpha = float(result.params.get("alpha[1]", np.nan))
    beta = float(result.params.get("beta[1]", np.nan))
    if not np.isfinite(omega) or omega <= 0 or alpha + beta >= 1.0:
        return None
    return {
        "omega": omega,
        "alpha": alpha,
        "beta": beta,
        "persistence": alpha + beta,
        "unconditional_variance": omega / max(1.0 - alpha - beta, 1e-12),
    }


def garch_forecast(r: pd.Series, oos_start: str, params: dict[str, float] | None = None):
    """One-step GARCH variance forecasts over the out-of-sample window.

    Parameters are fit on the data before oos_start and held fixed; the
    recursion uses realized squared returns through t-1.
    """
    series = r.dropna()
    split = pd.Timestamp(oos_start)
    in_sample = series[series.index < split]
    fitted = fit_garch(in_sample) if params is None else params
    if fitted is None:
        return None
    out_index = series.index[series.index >= split]
    if len(out_index) == 0:
        return None
    omega, alpha, beta = fitted["omega"], fitted["alpha"], fitted["beta"]
    squared = series.to_numpy(dtype=float) ** 2
    position = series.index.get_indexer([out_index[0]])[0]
    state = float(in_sample.var())
    forecasts = np.full(len(out_index), np.nan)
    for i, loc in enumerate(range(position, position + len(out_index))):
        prev = squared[loc - 1] if loc - 1 >= 0 else state
        state = omega + alpha * prev + beta * state
        forecasts[i] = state
    return pd.Series(forecasts, index=out_index, name="garch")


def vol_horse_race(
    r: pd.DataFrame,
    oos_start: str,
    include_garch: bool = True,
    garch_tickers: int | None = 60,
) -> pd.DataFrame:
    """QLIKE comparison of volatility forecasts across names.

    r: daily returns (date x ticker). Methods: ewma_094, ewma_097,
    realized_21, realized_63, trailing_252 (baseline) and, when the arch
    package is available, garch for the first garch_tickers names.
    Returns one row per (ticker, method) with the mean out-of-sample
    QLIKE and the number of observations.
    """
    rf = _frame(r).astype(float)
    split = pd.Timestamp(oos_start)
    forecasts: dict[str, pd.DataFrame] = {
        "ewma_094": _frame(ewma_vol(rf, lam=0.94, min_obs=60)),
        "ewma_097": _frame(ewma_vol(rf, lam=0.97, min_obs=60)),
        "realized_21": _frame(realized_var(rf, window=21)),
        "realized_63": _frame(realized_var(rf, window=63)),
        "trailing_252": _frame(realized_var(rf, window=252)),
    }
    rows: list[dict[str, object]] = []
    for name, sigma2 in forecasts.items():
        losses = _frame(qlike(sigma2, rf))
        oos = losses.loc[losses.index >= split]
        for ticker in oos.columns:
            values = oos[ticker].dropna()
            if len(values) < 100:
                continue
            rows.append(
                {"ticker": ticker, "method": name, "qlike": float(values.mean()), "n_obs": int(len(values))}
            )
    if include_garch:
        names = list(rf.columns[: garch_tickers]) if garch_tickers else list(rf.columns)
        for ticker in names:
            series = rf[ticker].dropna()
            forecast = garch_forecast(series, oos_start=oos_start)
            if forecast is None:
                continue
            values = qlike(forecast, series.reindex(forecast.index)).dropna()
            if len(values) < 100:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "method": "garch",
                    "qlike": float(values.mean()),
                    "n_obs": int(len(values)),
                }
            )
    return pd.DataFrame(rows)


def beats_baseline(table: pd.DataFrame, baseline: str = "trailing_252") -> pd.DataFrame:
    """Share of names where each method's QLIKE beats the baseline."""
    pivot = table.pivot_table(index="ticker", columns="method", values="qlike")
    if baseline not in pivot.columns:
        return pd.DataFrame(columns=["method", "win_share", "n_names"])
    rows = []
    for method in pivot.columns:
        if method == baseline:
            continue
        both = pivot[[method, baseline]].dropna()
        if both.empty:
            rows.append({"method": method, "win_share": float("nan"), "n_names": 0})
            continue
        wins = (both[method] < both[baseline]).mean()
        rows.append({"method": method, "win_share": float(wins), "n_names": int(len(both))})
    return pd.DataFrame(rows).sort_values("win_share", ascending=False).reset_index(drop=True)
