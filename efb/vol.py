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
                state = np.nanvar(values[:min_obs], axis=0)
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


def qlike_variance(
    sigma2_hat: pd.Series | pd.DataFrame, realized_var: pd.Series | pd.DataFrame
) -> pd.Series | pd.DataFrame:
    """QLIKE with the target already a variance level rather than a return.

    qlike() squares its second argument, which is right for a next-day
    return and wrong for a realized variance, where the level is already a
    sum of squares. The functional form is the same, ln s2 + rv / s2, so a
    one-step call here and a call to qlike() on the same second of data
    give identical numbers.
    """
    if isinstance(sigma2_hat, pd.Series) and isinstance(realized_var, pd.Series):
        s2, rv = sigma2_hat.align(realized_var, join="outer")
        s2 = s2.astype(float)
        rv = rv.astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.log(s2) + rv / s2
    s2 = _frame(sigma2_hat).astype(float)
    rv = _frame(realized_var).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.log(s2) + rv / s2
    return _same_type(out, sigma2_hat)


@dataclass
class MZResult:
    alpha: float
    beta: float
    r_squared: float
    n_obs: int


def mincer_zarnowitz(r2: pd.Series, sigma2_hat: pd.Series) -> MZResult:
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
        model = arch_model(
            series, vol="GARCH", p=1, q=1, mean="Constant", dist="normal"
        )
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


def garch_forecast(
    r: pd.Series, oos_start: str, params: dict[str, float] | None = None
):
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
                {
                    "ticker": ticker,
                    "method": name,
                    "qlike": float(values.mean()),
                    "n_obs": int(len(values)),
                }
            )
    if include_garch:
        names = list(rf.columns[:garch_tickers]) if garch_tickers else list(rf.columns)
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


def garch_horizon_sum(
    params: dict[str, float], sigma2_next: float, horizon: int
) -> float | None:
    """Expected sum of the next `horizon` GARCH variances from sigma2_next.

    For GARCH(1,1) the k-step variance reverts geometrically toward the
    unconditional level, so the sum is h * uncond plus the transient term
    (sigma2_next - uncond) * (1 - p^h) / (1 - p) with p = alpha + beta.
    Returns None when the fit is not stationary, because then there is no
    unconditional level to revert to.
    """
    omega = float(params["omega"])
    persistence = float(params["persistence"])
    if not np.isfinite(omega) or omega <= 0 or persistence >= 1.0:
        return None
    uncond = omega / (1.0 - persistence)
    if horizon <= 0:
        return None
    transient = (
        1.0
        if persistence == 0.0
        else (1.0 - persistence**horizon) / (1.0 - persistence)
    )
    return float(horizon * uncond + (sigma2_next - uncond) * transient)


def garch_horizon_forecast(
    r: pd.DataFrame,
    params: dict[str, float],
    oos_start: str,
    horizon: int = 21,
) -> pd.DataFrame | None:
    """h-day expected variance sums from a GARCH fit held fixed at oos_start.

    The recursion is walked over realized squared returns to reach each
    forecast date, then the multi-step sum is closed form from there.
    Returns a frame indexed like the one-step forecasts, in decimal
    variance units.
    """
    frame = _frame(r).astype(float)
    split = pd.Timestamp(oos_start)
    index = frame.index[frame.index >= split]
    if len(index) == 0:
        return None
    omega = float(params["omega"])
    alpha = float(params["alpha"])
    beta = float(params["beta"])
    uncond = omega / (1.0 - float(params["persistence"]))
    values = frame.to_numpy(dtype=float)
    positions = frame.index.get_indexer(index)
    first = int(positions[0])
    out = np.full((len(index), frame.shape[1]), np.nan)

    for column in range(frame.shape[1]):
        series = values[:, column]
        state = uncond
        # walk the recursion through the in-sample period first
        for warm in range(first):
            previous = series[warm - 1] if warm >= 1 else uncond
            if not np.isfinite(previous):
                previous = uncond
            state = omega + alpha * previous**2 + beta * state
        for i, loc in enumerate(positions):
            previous = series[loc - 1] if loc >= 1 else uncond
            if not np.isfinite(previous):
                previous = uncond
            state = omega + alpha * previous**2 + beta * state
            total = garch_horizon_sum(params, state, horizon)
            out[i, column] = np.nan if total is None else total

    return pd.DataFrame(out, index=index, columns=frame.columns)


def forward_realized_variance(r: pd.DataFrame, horizon: int = 21) -> pd.DataFrame:
    """Realized variance of the `horizon` days starting at the index date.

    The convention matches every forecast in this module: a value indexed
    at t is a forecast of the return realized at t, because ewma_vol and
    the trailing windows all use information through t-1. So the h-day
    target at t is the sum of squared returns over t to t+h-1, and the
    last h-1 rows have no future to measure and stay NaN.
    """
    frame = _frame(r).astype(float)
    squared = frame**2
    forward = squared.rolling(horizon, min_periods=horizon).sum().shift(-(horizon - 1))
    return forward.astype(float)


def horizon_forecast(sigma2: pd.DataFrame, horizon: int = 21) -> pd.DataFrame:
    """Scale a one-step variance forecast to a flat `horizon`-day sum.

    EWMA and a trailing window have no multi-step dynamics, so the only
    consistent h-day forecast they can make is the one-step level held for
    h days.
    """
    return _frame(sigma2).astype(float) * float(horizon)


def aligned_horse_race(
    r: pd.DataFrame,
    oos_start: str,
    horizons: tuple[int, ...] = (1, 21),
    include_garch: bool = True,
    garch_tickers: int | None = 60,
    min_obs: int = 100,
    garch_params: dict[str, dict[str, float]] | None = None,
) -> pd.DataFrame:
    """QLIKE comparison where forecast and target share a horizon.

    horizon 1: one-step forecasts against the next day's squared return,
    which is what F2.3 already did. horizon h: h-day forecasts from GARCH
    multi-step, EWMA held flat and a trailing window held flat, against the
    realized variance of the next h days. Every method is scored on the
    same out-of-sample window, and the caller passes returns that already
    exclude flagged rows.

    Returns one row per (horizon, ticker, method) with the mean QLIKE and
    the number of observations, plus `n_attempted` rows for diagnostics
    where a GARCH fit failed.
    """
    frame = _frame(r).astype(float)
    split = pd.Timestamp(oos_start)
    rows: list[dict[str, object]] = []
    garch_ok: list[str] = []
    garch_failed: list[str] = []

    for horizon in horizons:
        target = forward_realized_variance(frame, horizon=horizon)
        one_step = {
            "ewma_094": _frame(ewma_vol(frame, lam=0.94, min_obs=60)),
            "ewma_097": _frame(ewma_vol(frame, lam=0.97, min_obs=60)),
            "trailing_252": _frame(realized_var(frame, window=252)),
            "trailing_63": _frame(realized_var(frame, window=63)),
        }
        forecasts = (
            one_step
            if horizon == 1
            else {
                name: horizon_forecast(value, horizon)
                for name, value in one_step.items()
            }
        )

        if include_garch:
            names = (
                list(frame.columns[:garch_tickers])
                if garch_tickers
                else list(frame.columns)
            )
            for ticker in names:
                series = frame[ticker].dropna()
                fitted = (garch_params or {}).get(ticker)
                if fitted is None:
                    fitted = fit_garch(series[series.index < split])
                if fitted is None:
                    garch_failed.append(ticker)
                    continue
                single = garch_horizon_forecast(
                    frame[[ticker]], params=fitted, oos_start=oos_start, horizon=1
                )
                if single is None:
                    garch_failed.append(ticker)
                    continue
                if horizon == 1:
                    path = single
                else:
                    multi = garch_horizon_forecast(
                        frame[[ticker]],
                        params=fitted,
                        oos_start=oos_start,
                        horizon=horizon,
                    )
                    if multi is None:
                        garch_failed.append(ticker)
                        continue
                    path = multi
                garch_ok.append(ticker)
                losses = qlike_variance(path, target[[ticker]])
                window = losses.loc[losses.index >= split]
                values = window.iloc[:, 0].dropna()
                if len(values) < min_obs:
                    continue
                rows.append(
                    {
                        "horizon": horizon,
                        "ticker": ticker,
                        "method": "garch",
                        "qlike": float(values.mean()),
                        "n_obs": int(len(values)),
                    }
                )

        for name, path in forecasts.items():
            losses = qlike_variance(path, target)
            window = losses.loc[losses.index >= split]
            for ticker in window.columns:
                values = window[ticker].dropna()
                if len(values) < min_obs:
                    continue
                rows.append(
                    {
                        "horizon": horizon,
                        "ticker": ticker,
                        "method": name,
                        "qlike": float(values.mean()),
                        "n_obs": int(len(values)),
                    }
                )

    table = pd.DataFrame(rows)
    table.attrs["garch_fitted"] = sorted(set(garch_ok))
    table.attrs["garch_failed"] = sorted(set(garch_failed))
    table.attrs["oos_start"] = oos_start
    return table


def win_rate_by_year(
    r: pd.DataFrame,
    oos_start: str,
    method: str = "ewma_094",
    baseline: str = "trailing_252",
):
    """Day-level win rate of one estimator over the baseline, by calendar year.

    F2.3 counts names: it averages each name's QLIKE and then asks how many
    names favor the method. This counts name-days instead, which answers a
    different question: how often the method is better on a given day. When
    the two disagree, a few names with extreme losses are driving the
    name-level average rather than the method being worse.
    """
    frame = _frame(r).astype(float)
    split = pd.Timestamp(oos_start)
    target = forward_realized_variance(frame, 1)
    options = {
        "ewma_094": _frame(ewma_vol(frame, lam=0.94, min_obs=60)),
        "ewma_097": _frame(ewma_vol(frame, lam=0.97, min_obs=60)),
        "trailing_252": _frame(realized_var(frame, window=252)),
        "trailing_63": _frame(realized_var(frame, window=63)),
    }
    if method not in options or baseline not in options:
        raise KeyError(f"unknown method {method!r} or baseline {baseline!r}")
    left = _frame(qlike_variance(options[method], target)).loc[split:]
    right = _frame(qlike_variance(options[baseline], target)).loc[split:]
    both = pd.concat(
        [left.stack().rename("method"), right.stack().rename("baseline")], axis=1
    ).dropna()
    wins = both["method"] < both["baseline"]
    years = pd.Series(wins.index.get_level_values(0).year, index=wins.index)
    by_year = {
        int(year): float(value) for year, value in wins.groupby(years).mean().items()
    }
    return {
        "pooled": float(wins.mean()),
        "n_name_days": int(len(wins)),
        "by_year": by_year,
        "excluding_2020": float(wins[years != 2020].mean()),
    }


def diagnose(r: pd.DataFrame, oos_start: str, garch_tickers: int | None = 60):
    """Print the F2.3 diagnostic the close-out brief asks for.

    a) the exact target behind QLIKE and the horizon of every estimator;
    b) whether returns are scaled for the arch fit and how many fits fail;
    c) the win rate by calendar year, and with 2020 excluded.
    """
    frame = _frame(r).astype(float)
    split = pd.Timestamp(oos_start)
    print("=== C3 F2.3 diagnostic ===")
    print(f"out-of-sample window: {split.date()} to {frame.index.max().date()}")
    print("(a) target and horizons")
    print("  QLIKE(sigma2, r) = ln(sigma2) + r^2 / sigma2, and every forecast in")
    print("  this module is indexed as a forecast of the return on that date,")
    print("  so the target is the SAME-DAY squared return, one step ahead.")
    table = vol_horse_race(
        frame, oos_start=oos_start, include_garch=True, garch_tickers=garch_tickers
    )
    rows = []
    for name in sorted(table["method"].unique()):
        block = table[table["method"] == name]
        rows.append(
            {
                "method": name,
                "horizon": 1,
                "names": int(len(block)),
                "mean_qlike": round(float(block["qlike"].mean()), 3),
            }
        )
    print(pd.DataFrame(rows).to_string(index=False))
    print("  trailing_21 and trailing_63 are trailing variances: one step ahead.")
    print("  All methods are one-step, so F2.3 is horizon aligned already.")

    print("(b) arch fit")
    names = (
        list(frame.columns[:garch_tickers]) if garch_tickers else list(frame.columns)
    )
    fitted: list[str] = []
    failed: list[str] = []
    for ticker in names:
        series = frame[ticker].dropna()
        params = fit_garch(series[series.index < split])
        (fitted if params is not None else failed).append(ticker)
    print("  returns are scaled by 100 before arch_model and the variance is")
    print("  divided by 1e4 on the way out, for numerical stability.")
    print(f"  attempted: {len(names)}, fitted: {len(fitted)}, failed: {len(failed)}")
    if failed:
        print(f"  did not converge: {failed}")

    print("(c) win rate by calendar year")
    stats = win_rate_by_year(frame, oos_start)
    print("  EWMA(0.94) vs trailing 252d, fraction of name-days with lower QLIKE")
    for year, value in stats["by_year"].items():
        print(f"    {year}: {value:.3f}")
    print(f"  pooled: {stats['pooled']:.3f}  over {stats['n_name_days']} name-days")
    print(f"  excluding 2020: {stats['excluding_2020']:.3f}")
    print("  the window starts in 2024, so 2020 is not in it")
    print("(d) name level against day level")
    print("  F2.3 counts names, this diagnostic counts name-days. When the two")
    print("  disagree, a few names with extreme losses drive the name average.")
    return stats


def aligned_win_shares(
    table: pd.DataFrame, baseline: str = "trailing_252"
) -> pd.DataFrame:
    """Win share per horizon, method and baseline, on matched names."""
    rows: list[dict[str, object]] = []
    for horizon, block in table.groupby("horizon"):
        pivot = block.pivot(index="ticker", columns="method", values="qlike")
        for method in sorted(set(pivot.columns) - {baseline}):
            pair = pivot[[method, baseline]].dropna()
            if pair.empty:
                continue
            rows.append(
                {
                    "horizon": int(horizon),
                    "method": method,
                    "n_names": int(len(pair)),
                    "win_share": float((pair[method] < pair[baseline]).mean()),
                    "mean_qlike": float(pair[method].mean()),
                    "baseline_qlike": float(pair[baseline].mean()),
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
        rows.append(
            {"method": method, "win_share": float(wins), "n_names": int(len(both))}
        )
    return (
        pd.DataFrame(rows)
        .sort_values("win_share", ascending=False)
        .reset_index(drop=True)
    )
