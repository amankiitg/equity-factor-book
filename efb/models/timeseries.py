"""Time-series factor models (Sprint E2, TS-v1).

Per-stock regressions of excess returns on observed factors, with OLS and
Newey-West HAC standard errors, residuals and idiosyncratic volatility.
Every input is labeled by file and column in the walkthrough; here the
contract is:

- y: returns.parquet column excess (per ticker).
- X: factors_ff.parquet columns mkt_rf, smb, hml, rmw, cma, mom.
- OUTPUT: data/models/TS-v1/loadings.parquet, loadings_se.parquet,
  residuals.parquet, idio_vol.parquet.

Design rules: NaN rows are dropped, never imputed; rows flagged stale or
outlier are excluded and counted; a name with fewer than min_obs usable
rows returns NaN loadings rather than a guess.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

NW_LAG = 5
MIN_OBS = 60
MODEL_START = 2010

MARKET_FACTORS = ["mkt_rf"]
MULTI_FACTORS = ["mkt_rf", "smb", "hml", "rmw", "cma", "mom"]
OPTIONAL_FACTORS = ["st_rev"]


def select_factors(
    factors_frame: pd.DataFrame, include_optional: bool = False
) -> pd.DataFrame:
    """The FF5 + Momentum regressor set (optionally plus ST reversal)."""
    columns = MULTI_FACTORS + (OPTIONAL_FACTORS if include_optional else [])
    return factors_frame[columns]


@dataclass
class OLSFit:
    """Result of a single OLS regression."""

    params: pd.Series
    ols_se: pd.Series
    nw_se: pd.Series
    residuals: pd.Series
    r_squared: float
    sigma_eps: float
    n_obs: int
    n_dropped_nan: int = 0
    factor_names: list[str] = field(default_factory=list)
    nw_lag: int = NW_LAG


def apply_exclusions(
    y: pd.Series, flags: pd.DataFrame
) -> tuple[pd.Series, dict[str, int]]:
    """Mask flagged rows (stale, outlier) to NaN and count what was masked.

    flags: DataFrame indexed like y with stale and outlier boolean columns
    (INPUT: returns.parquet columns stale, outlier).
    """
    masked = y.copy()
    counts = {"stale": 0, "outlier": 0, "nan": int(y.isna().sum())}
    for column in ("stale", "outlier"):
        if column not in flags.columns:
            continue
        bad = flags[column].reindex(y.index).fillna(False).astype(bool)
        counts[column] = int((bad & y.notna()).sum())
        masked = masked.mask(bad)
    return masked, counts


def newey_west_cov(X: np.ndarray, resid: np.ndarray, lag: int) -> np.ndarray:
    """Newey-West HAC covariance of the OLS estimator.

    V = (X'X)^-1 S (X'X)^-1 with
    S = G_0 + sum_{j=1..L} (1 - j/(L+1)) (G_j + G_j') and
    G_j = sum_t u_t u_{t-j} x_t x_{t-j}'.
    """
    n, k = X.shape
    xtx_inv = np.linalg.pinv(X.T @ X)
    u = resid.reshape(-1, 1)
    xu = X * u
    s = xu.T @ xu
    for j in range(1, lag + 1):
        w = 1.0 - j / (lag + 1)
        gamma = xu[j:].T @ xu[:-j]
        s += w * (gamma + gamma.T)
    cov = xtx_inv @ s @ xtx_inv
    # small-sample correction for the fitted degrees of freedom
    if n > k:
        cov = cov * (n / (n - k))
    return cov


def _design(y: pd.Series, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, pd.Index]:
    """Align y and X, drop NaN rows, add an intercept column."""
    frame = pd.concat([y.rename("y"), X], axis=1)
    frame = frame.dropna(how="any")
    y_vec = frame["y"].to_numpy(dtype=float)
    x_mat = np.column_stack(
        [np.ones(len(frame))] + [frame[c].to_numpy(dtype=float) for c in X.columns]
    )
    return y_vec, x_mat, frame.index


def ols_fit(
    y: pd.Series, X: pd.DataFrame, nw_lag: int = NW_LAG, min_obs: int = MIN_OBS
) -> OLSFit:
    """Fit y on X with OLS and Newey-West standard errors.

    y: excess returns (returns.parquet excess). X: factor returns
    (factors_ff.parquet). NaN rows in y or X are dropped, never imputed.
    """
    n_input = len(y)
    factor_names = list(X.columns)
    y_vec, x_mat, index = _design(y, X)
    n = len(index)
    names = ["alpha"] + factor_names
    n_dropped = max(n_input - n, 0)
    if n < min_obs or n <= x_mat.shape[1]:
        nan = pd.Series(np.nan, index=names)
        return OLSFit(
            params=nan,
            ols_se=nan.copy(),
            nw_se=nan.copy(),
            residuals=pd.Series(dtype=float),
            r_squared=float("nan"),
            sigma_eps=float("nan"),
            n_obs=n,
            n_dropped_nan=n_dropped,
            factor_names=factor_names,
            nw_lag=nw_lag,
        )
    xtx = x_mat.T @ x_mat
    try:
        xtx_inv = np.linalg.inv(xtx)
    except np.linalg.LinAlgError:
        nan = pd.Series(np.nan, index=names)
        return OLSFit(
            params=nan,
            ols_se=nan.copy(),
            nw_se=nan.copy(),
            residuals=pd.Series(dtype=float),
            r_squared=float("nan"),
            sigma_eps=float("nan"),
            n_obs=n,
            n_dropped_nan=n_dropped,
            factor_names=factor_names,
            nw_lag=nw_lag,
        )
    beta = xtx_inv @ x_mat.T @ y_vec
    resid = y_vec - x_mat @ beta
    dof = n - x_mat.shape[1]
    sigma2 = float(resid @ resid) / dof
    ols_cov = sigma2 * xtx_inv
    nw_cov = newey_west_cov(x_mat, resid, nw_lag)
    ss_tot = float(((y_vec - y_vec.mean()) ** 2).sum())
    r_squared = 1.0 - float(resid @ resid) / ss_tot if ss_tot > 0 else float("nan")
    return OLSFit(
        params=pd.Series(beta, index=names),
        ols_se=pd.Series(np.sqrt(np.diag(ols_cov)), index=names),
        nw_se=pd.Series(np.sqrt(np.diag(nw_cov)), index=names),
        residuals=pd.Series(resid, index=index),
        r_squared=r_squared,
        sigma_eps=float(np.sqrt(sigma2)),
        n_obs=n,
        n_dropped_nan=n_dropped,
        factor_names=factor_names,
        nw_lag=nw_lag,
    )


def _as_frame(y: pd.Series | pd.DataFrame) -> pd.DataFrame:
    return y.to_frame() if isinstance(y, pd.Series) else y


def _as_series(out: pd.DataFrame, was_series: bool) -> pd.Series | pd.DataFrame:
    return out.iloc[:, 0] if was_series else out


def rolling_beta(
    y: pd.Series | pd.DataFrame,
    x: pd.Series,
    window: int = 252,
    min_obs: int = 126,
) -> pd.Series | pd.DataFrame:
    """Rolling OLS beta of y on x, dated t, fit on data through t-1.

    y: excess returns (returns.parquet). x: market factor
    (factors_ff.parquet mkt_rf). The shift(1) is the look-ahead guard.
    """
    yf = _as_frame(y)
    xs = x.shift(1)
    ys = yf.shift(1)
    cov = ys.rolling(window, min_periods=min_obs).cov(xs)
    var = xs.rolling(window, min_periods=min_obs).var()
    out = cov.div(var.replace(0.0, np.nan), axis=0)
    return _as_series(out, isinstance(y, pd.Series))


def rolling_beta_se(
    y: pd.Series | pd.DataFrame,
    x: pd.Series,
    window: int = 252,
    min_obs: int = 126,
) -> pd.Series | pd.DataFrame:
    """Rolling OLS standard error of the beta, dated t, fit through t-1.

    SE = sqrt(RSS / (n - 2)) / sqrt(Sxx) with
    RSS = (var_y - beta^2 var_x) * (n - 1) and Sxx = var_x * (n - 1).
    """
    yf = _as_frame(y)
    xs = x.shift(1)
    ys = yf.shift(1)
    n = ys.rolling(window, min_periods=min_obs).count()
    var_y = ys.rolling(window, min_periods=min_obs).var()
    var_x = xs.rolling(window, min_periods=min_obs).var()
    beta = _as_frame(rolling_beta(yf, x, window, min_obs))
    sxx = (n - 1).mul(var_x, axis=0)
    rss = (var_y - beta.pow(2).mul(var_x, axis=0)) * (n - 1)
    out = np.sqrt(rss.div(n - 2).div(sxx, axis=0).clip(lower=0.0))
    return _as_series(out, isinstance(y, pd.Series))


def ewma_weights(n: int, half_life: float) -> np.ndarray:
    """Exponential weights: 1 at age 0, 0.5 at age half_life."""
    ages = np.arange(n, dtype=float)
    return np.power(0.5, ages / half_life)


def ewma_beta(
    y: pd.Series | pd.DataFrame,
    x: pd.Series,
    half_life: float = 63,
    min_obs: int = 252,
) -> pd.Series | pd.DataFrame:
    """Exponentially weighted beta, dated t, fit on data through t-1.

    Closed form with EWMA-recursive weighted sums, decay factor
    lambda = 0.5^(1 / half_life):
    beta = (Sxy - Sx Sy / Sw) / (Sxx - Sx^2 / Sw).
    """
    yf = _as_frame(y)
    yy = yf.to_numpy(dtype=float)
    xx = x.to_numpy(dtype=float)
    lam = 0.5 ** (1.0 / half_life)
    n_dates, n_assets = yy.shape
    sw = np.zeros(n_assets)
    sx = np.zeros(n_assets)
    sy = np.zeros(n_assets)
    sxy = np.zeros(n_assets)
    sxx = np.zeros(n_assets)
    counts = np.zeros(n_assets)
    out = np.full((n_dates, n_assets), np.nan)
    for t in range(n_dates):
        if t > 0:
            with np.errstate(invalid="ignore", divide="ignore"):
                denom = sxx - sx * sx / sw
                numer = sxy - sx * sy / sw
                beta = numer / denom
            ok = (counts >= min_obs) & np.isfinite(beta) & (denom > 0) & (sw > 0)
            out[t] = np.where(ok, beta, np.nan)
        xt = xx[t]
        row = yy[t]
        valid = np.isfinite(xt) & np.isfinite(row)
        sw = np.where(np.isfinite(sw), lam * sw, 0.0)
        sx = lam * sx
        sy = lam * sy
        sxy = lam * sxy
        sxx = lam * sxx
        use = np.where(valid, 1.0, 0.0)
        sw = sw + use
        sx = sx + np.where(valid, xt, 0.0)
        sy = sy + np.where(valid, row, 0.0)
        sxy = sxy + np.where(valid, xt * row, 0.0)
        sxx = sxx + np.where(valid, xt * xt, 0.0)
        counts = counts + use
    frame = pd.DataFrame(out, index=yf.index, columns=yf.columns)
    return _as_series(frame, isinstance(y, pd.Series))


def blume_shrink(beta: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """Blume shrinkage: 0.67 * beta + 0.33."""
    return 0.67 * beta + 0.33


def vasicek_shrink(
    beta: pd.Series,
    se: pd.Series,
    beta_bar: float | None = None,
) -> pd.Series:
    """Vasicek shrinkage toward the cross-sectional mean.

    w = sigma_xs^2 / (sigma_xs^2 + SE^2), where sigma_xs^2 is the
    cross-sectional variance of beta; beta_s = w beta + (1 - w) beta_bar.
    Names with a large standard error move most.
    """
    aligned = pd.concat([beta.rename("beta"), se.rename("se")], axis=1).dropna()
    if aligned.empty:
        return beta.copy()
    bar = float(aligned["beta"].mean()) if beta_bar is None else float(beta_bar)
    sigma_xs2 = float(aligned["beta"].var(ddof=1))
    if not np.isfinite(sigma_xs2) or sigma_xs2 <= 0:
        return beta.copy()
    w = sigma_xs2 / (sigma_xs2 + aligned["se"] ** 2)
    shrunk = w * aligned["beta"] + (1.0 - w) * bar
    return shrunk.reindex(beta.index)


def beta_history(
    y: pd.DataFrame,
    x: pd.Series,
    window: int = 252,
    half_lives: tuple[int, ...] = (63, 126),
    min_obs: int = 126,
) -> pd.DataFrame:
    """Rolling, EWMA and shrunk betas for every column of y.

    Returns a DataFrame with MultiIndex columns (method, ticker) where
    method is raw, ewma_<half_life>, vasicek and blume. The raw method
    feeds the Vasicek and Blume shrinkage.
    """
    frames: dict[str, pd.DataFrame] = {"raw": _as_frame(rolling_beta(y, x, window, min_obs))}
    for half_life in half_lives:
        frames[f"ewma_{half_life}"] = _as_frame(
            ewma_beta(y, x, half_life=half_life, min_obs=252)
        )
    se = _as_frame(rolling_beta_se(y, x, window, min_obs))
    raw = frames["raw"]
    vasicek = pd.DataFrame(index=raw.index, columns=raw.columns, dtype=float)
    for date in raw.index:
        row = raw.loc[date]
        se_row = se.loc[date]
        vasicek.loc[date] = vasicek_shrink(row, se_row)
    frames["vasicek"] = vasicek
    frames["blume"] = blume_shrink(raw)
    out = pd.concat(frames, axis=1)
    out.columns.names = ["method", "ticker"]
    return out


def _beta_window(
    y: np.ndarray, x: np.ndarray, min_obs: int
) -> np.ndarray:
    """Vectorized single-factor beta over one window (columns are names)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        valid = np.isfinite(y) & np.isfinite(x)[:, None]
        counts = valid.sum(axis=0)
        yy = np.where(valid, y, np.nan)
        xm = np.where(valid, x[:, None], np.nan)
        x_bar = np.nanmean(xm, axis=0)
        y_bar = np.nanmean(yy, axis=0)
        xc = xm - x_bar
        yc = yy - y_bar
        sxy = np.nansum(xc * yc, axis=0)
        sxx = np.nansum(xc * xc, axis=0)
        beta = sxy / sxx
    return np.where((counts >= min_obs) & (sxx > 0), beta, np.nan)


def beta_horse_race(
    y: pd.DataFrame,
    x: pd.Series,
    window: int = 252,
    min_obs: int = 126,
    forward: int = 63,
) -> pd.DataFrame:
    """Forecast next-quarter realized beta with each beta estimator.

    At each month end t, predictors are fit on data through t-1 and the
    target is the realized beta over the next `forward` trading days.
    Returns one row per method with rmse, mean bias and n_obs.
    """
    dates = y.index
    month_ends = pd.Series(dates, index=dates).groupby([dates.year, dates.month]).last()
    history = beta_history(y, x, window=window, min_obs=min_obs)
    rows: list[dict[str, object]] = []
    y_arr = y.to_numpy(dtype=float)
    x_arr = x.to_numpy(dtype=float)
    index_of = {d: i for i, d in enumerate(dates)}
    for t in month_ends:
        i = index_of[t]
        if i < min_obs or i + forward >= len(dates):
            continue
        preds: dict[str, pd.Series] = {}
        for method in ["raw", "vasicek", "blume"]:
            preds[method] = pd.Series(history.loc[t].loc[method], index=y.columns)
        for column in history.columns.get_level_values(0).unique():
            if column.startswith("ewma_"):
                preds[column] = pd.Series(history.loc[t].loc[column], index=y.columns)
        realized = _beta_window(
            y_arr[i + 1 : i + 1 + forward], x_arr[i + 1 : i + 1 + forward], min_obs=20
        )
        realized_s = pd.Series(realized, index=y.columns)
        for method, predicted in preds.items():
            pair = pd.concat(
                [predicted.rename("pred"), realized_s.rename("real")], axis=1
            ).dropna()
            if not pair.empty:
                rows.append(
                    {
                        "method": method,
                        "date": t,
                        "n_obs": int(len(pair)),
                        "rmse": float(np.sqrt(((pair["pred"] - pair["real"]) ** 2).mean())),
                        "mean_bias": float((pair["pred"] - pair["real"]).mean()),
                    }
                )
    per_date = pd.DataFrame(rows)
    summary = (
        per_date.groupby("method")
        .apply(
            lambda g: pd.Series(
                {
                    "rmse": float(np.sqrt((g["rmse"] ** 2 * g["n_obs"]).sum() / g["n_obs"].sum())),
                    "mean_bias": float((g["mean_bias"] * g["n_obs"]).sum() / g["n_obs"].sum()),
                    "n_obs": int(g["n_obs"].sum()),
                    "n_dates": int(len(g)),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    return summary


def panel_from_artifacts(
    returns_frame: pd.DataFrame,
    factors_frame: pd.DataFrame,
    start: int = 2010,
    exclude_flags: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build the (date x ticker) excess panel, factor matrix and flag panel.

    returns_frame: returns.parquet long frame with excess, stale, outlier.
    factors_frame: factors_ff.parquet wide frame.
    """
    dates = pd.DatetimeIndex(sorted(returns_frame.index.get_level_values("date").unique()))
    dates = dates[dates.year >= start]
    y = returns_frame["excess"].unstack("ticker").reindex(index=dates)
    stale = returns_frame["stale"].unstack("ticker").reindex(index=dates).fillna(False)
    outlier = returns_frame["outlier"].unstack("ticker").reindex(index=dates).fillna(False)
    # columns are a MultiIndex (flag, ticker); flags["stale"] is a date x ticker frame
    flags = pd.concat({"stale": stale, "outlier": outlier}, axis=1)
    factors = factors_frame.reindex(index=dates)
    if exclude_flags:
        for column in ("stale", "outlier"):
            y = y.mask(flags[column].astype(bool))
    return y, factors, flags


def fit_factor_model(
    y: pd.DataFrame,
    factors: pd.DataFrame,
    flags: pd.DataFrame | None = None,
    nw_lag: int = NW_LAG,
    min_obs: int = MIN_OBS,
) -> dict[str, pd.DataFrame | pd.Series]:
    """Fit the multi-factor model for every column of y.

    Returns a dict with loadings, loadings_ols_se, loadings_nw_se,
    alpha, r_squared, sigma_eps, n_obs, exclusions and residuals (long).
    """
    loadings: dict[str, pd.Series] = {}
    ols_ses: dict[str, pd.Series] = {}
    nw_ses: dict[str, pd.Series] = {}
    alphas: dict[str, float] = {}
    r2s: dict[str, float] = {}
    sigmas: dict[str, float] = {}
    nobs: dict[str, int] = {}
    exclusion_rows: list[dict[str, int]] = []
    residual_frames: list[pd.Series] = []
    for ticker in y.columns:
        series = y[ticker]
        counts = {"stale": 0, "outlier": 0, "nan": int(series.isna().sum())}
        if flags is not None:
            ticker_flags = pd.DataFrame(
                {c: flags[c][ticker] for c in ("stale", "outlier") if c in flags}
            )
            series, counts = apply_exclusions(series, ticker_flags)
        fit = ols_fit(series, factors, nw_lag=nw_lag, min_obs=min_obs)
        loadings[ticker] = fit.params
        ols_ses[ticker] = fit.ols_se
        nw_ses[ticker] = fit.nw_se
        alphas[ticker] = float(fit.params["alpha"])
        r2s[ticker] = fit.r_squared
        sigmas[ticker] = fit.sigma_eps
        nobs[ticker] = fit.n_obs
        exclusion_rows.append({"ticker": ticker, **counts})
        if not fit.residuals.empty:
            residual_frames.append(fit.residuals.rename(ticker))
    loadings_df = pd.DataFrame(loadings).T
    residuals = (
        pd.concat(residual_frames, axis=1)
        .stack()
        .rename("residual")
        .to_frame()
        if residual_frames
        else pd.DataFrame(columns=["residual"])
    )
    if not residuals.empty:
        residuals.index.names = ["date", "ticker"]
    return {
        "loadings": loadings_df,
        "loadings_ols_se": pd.DataFrame(ols_ses).T,
        "loadings_nw_se": pd.DataFrame(nw_ses).T,
        "alpha": pd.Series(alphas, name="alpha"),
        "r_squared": pd.Series(r2s, name="r_squared"),
        "sigma_eps": pd.Series(sigmas, name="sigma_eps"),
        "n_obs": pd.Series(nobs, name="n_obs"),
        "exclusions": pd.DataFrame(exclusion_rows).set_index("ticker"),
        "residuals": residuals,
    }
