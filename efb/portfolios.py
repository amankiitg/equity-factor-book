"""Seed portfolios and portfolio risk under the time-series model.

Sprint E2, Task 5.

- Equal-weight seed book: long-only, equal weight across point-in-time
  members with prices. Because it is long-only it carries
  survivorship_caveat = true (E1 finding 1b).
- Sector-neutral long/short momentum quintile seed book: at each month
  end, rank point-in-time members by past 126-day return within GICS
  sector, long the top quantile and short the bottom quantile, equal
  weight within each leg, dollar and sector neutral. This becomes the
  second seed book for E3. survivorship_caveat = false, but the ledger
  notes that short-side specific risk is biased downward (E1 finding 1c).

Risk decomposition (OUTPUT: data/portfolios/*_risk.parquet):
sigma_p^2 = w' B F B' w + w' D w, with B the TS-v1 loadings, F the EWMA
factor covariance (half-life 90d) and D the diagonal idio variances.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LOOKBACK = 126
QUANTILE = 0.2
REBALANCE = "ME"


def ew_seed_weights(members: pd.DataFrame) -> pd.DataFrame:
    """Equal weight across current members; zero for non-members."""
    member = members.astype(bool)
    counts = member.sum(axis=1).replace(0, np.nan)
    weights = member.div(counts, axis=0)
    return weights.fillna(0.0)


def momentum_signal(returns_r: pd.DataFrame, lookback: int = LOOKBACK) -> pd.DataFrame:
    """Past cumulative return over [t - lookback, t - 1] for each name.

    Built from the rolling sum of log returns with at least 80% of the
    window present, so missing days shrink the count instead of being
    imputed as zero returns.
    """
    log_r = np.log1p(returns_r)
    min_periods = int(0.8 * lookback)
    total = log_r.rolling(lookback, min_periods=min_periods).sum().shift(1)
    return np.exp(total) - 1.0


def month_end_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    grouped = pd.Series(index, index=index).groupby([index.year, index.month]).last()
    return pd.DatetimeIndex(grouped.to_numpy())


def momentum_ls_weights(
    returns_r: pd.DataFrame,
    members: pd.DataFrame,
    sectors: pd.DataFrame,
    lookback: int = LOOKBACK,
    quantile: float = QUANTILE,
    min_names: int = 10,
) -> pd.DataFrame:
    """Sector-neutral long/short momentum weights, daily, month-end signal.

    Weights are set at each month end using data through t-1 and held
    until the next month end. Rows sum to zero (dollar neutral) and each
    sector's net weight is zero (sector neutral) by construction.
    """
    signal = momentum_signal(returns_r, lookback=lookback)
    sector_map = sectors.drop_duplicates("ticker").set_index("ticker")["gics_sector"]
    rebalance_dates = month_end_dates(returns_r.index)
    weights_at = pd.DataFrame(
        np.nan, index=rebalance_dates, columns=returns_r.columns, dtype=float
    )
    for date in rebalance_dates:
        row_signal = signal.loc[date] if date in signal.index else None
        if row_signal is None:
            continue
        member_row = (
            members.loc[date]
            if date in members.index
            else pd.Series(False, index=members.columns)
        )
        active = row_signal[
            member_row.reindex(row_signal.index).fillna(False).astype(bool)
        ].dropna()
        if len(active) < min_names:
            continue
        active_sectors = sector_map.reindex(active.index)
        raw = pd.Series(0.0, index=active.index)
        for _sector, group in active.groupby(active_sectors):
            if len(group) < 2:
                continue
            n_long = max(1, int(np.floor(len(group) * quantile)))
            ordered = group.sort_values(ascending=False)
            longs = ordered.index[:n_long]
            shorts = ordered.index[-n_long:]
            raw.loc[longs] = raw.loc[longs] + 1.0 / (2.0 * n_long)
            raw.loc[shorts] = raw.loc[shorts] - 1.0 / (2.0 * n_long)
        gross = float(raw.abs().sum())
        if gross > 0:
            full_row = pd.Series(0.0, index=returns_r.columns)
            full_row.loc[raw.index] = raw / gross
            weights_at.loc[date] = full_row
    weights = weights_at.reindex(returns_r.index).ffill().fillna(0.0)
    return weights


def to_long_weights(weights: pd.DataFrame, caveat: bool) -> pd.DataFrame:
    """Long format artifact with only nonzero weights and a caveat flag."""
    stacked = weights.stack()
    stacked = stacked[stacked.abs() > 0]
    frame = stacked.rename("weight").to_frame()
    frame.index.names = ["date", "ticker"]
    frame["survivorship_caveat"] = bool(caveat)
    return frame.reset_index()


def risk_decomposition(
    w: pd.Series,
    B: pd.DataFrame,
    F: pd.DataFrame,
    idio_var: pd.Series,
) -> dict[str, float]:
    """sigma_p^2 = w' B F B' w + w' D w.

    w: portfolio weights (ticker index). B: loadings (ticker x factor).
    F: factor covariance (factor x factor). idio_var: diagonal of D as a
    Series over tickers (a DataFrame raises, so a full matrix is never
    silently squeezed).
    """
    if isinstance(idio_var, pd.DataFrame):
        raise ValueError("idio_var must be a Series (the diagonal of D)")
    tickers = w.index
    beta = B.reindex(tickers)
    sigma2_idio = idio_var.reindex(tickers).fillna(0.0).to_numpy(dtype=float)
    factor_names = list(B.columns)
    beta_mat = beta.to_numpy(dtype=float)
    # names with a missing loading contribute only idio variance
    beta_mat = np.where(np.isfinite(beta_mat), beta_mat, 0.0)
    w_vec = w.to_numpy(dtype=float)
    beta_p = w_vec @ beta_mat
    F_mat = F.reindex(index=factor_names, columns=factor_names).to_numpy(dtype=float)
    factor_var = float(beta_p @ F_mat @ beta_p)
    idio = float(np.nansum(w_vec**2 * sigma2_idio))
    total = factor_var + idio
    out = {
        "factor_variance": factor_var,
        "idio_variance": idio,
        "total_variance": total,
        "factor_share": factor_var / total if total > 0 else float("nan"),
        "portfolio_vol_ann": float(np.sqrt(total * 252)),
    }
    for i, name in enumerate(factor_names):
        out[f"portfolio_beta_{name}"] = float(beta_p[i])
    return out


def ewma_factor_cov(
    factors: pd.DataFrame, half_life: float = 90.0, min_obs: int = 252
) -> pd.DataFrame:
    """EWMA factor covariance from factor returns (through the last date)."""
    lam = 0.5 ** (1.0 / half_life)
    values = factors.dropna().to_numpy(dtype=float)
    if len(values) < min_obs:
        return pd.DataFrame(np.nan, index=factors.columns, columns=factors.columns)
    weights = lam ** np.arange(len(values) - 1, -1, -1)
    weights = weights / weights.sum()
    demeaned = values - np.average(values, axis=0, weights=weights)
    cov = (demeaned * weights[:, None]).T @ demeaned
    return pd.DataFrame(cov, index=factors.columns, columns=factors.columns)


def rolling_idio_var(
    residuals: pd.DataFrame, window: int = 252, min_obs: int = 126
) -> pd.DataFrame:
    """Rolling idio variance per name, dated t from residuals through t-1."""
    return residuals.shift(1).rolling(window, min_periods=min_obs).var(ddof=1)


def predict_portfolio_vol(
    w: pd.Series,
    betas: pd.Series,
    factor_var: float,
    idio_var: pd.Series,
) -> tuple[float, float, float]:
    """Predicted portfolio vol (single factor), factor and idio variances.

    Returns (predicted_vol_ann, factor_variance, idio_variance) with
    sigma_p^2 = beta_p^2 F + sum_i w_i^2 sigma_i^2, beta_p = sum_i w_i beta_i.
    """
    aligned_beta = betas.reindex(w.index).fillna(0.0)
    beta_p = float((w * aligned_beta).sum())
    factor_variance = beta_p**2 * float(factor_var)
    idio_variance = float((w**2 * idio_var.reindex(w.index).fillna(0.0)).sum())
    total = factor_variance + idio_variance
    return float(np.sqrt(total * 252.0)), factor_variance, idio_variance


def portfolio_risk_history(
    weights: pd.DataFrame,
    returns_r: pd.DataFrame,
    betas: pd.DataFrame,
    factor_var: pd.Series,
    idio_var: pd.DataFrame,
    forward: int = 63,
) -> pd.DataFrame:
    """Month-end predicted vs realized portfolio vol with the bias ratio.

    weights: daily portfolio weights (date x ticker), signals set at month
    ends. betas: rolling market beta (date x ticker, already shifted).
    factor_var: EWMA market factor variance per date (through t-1).
    idio_var: rolling idio variance per date and name (through t-1).
    Realized vol is the standard deviation of the next `forward` daily
    portfolio returns, annualized.
    """
    rf = returns_r.reindex_like(weights)
    port_r = (weights * rf).sum(axis=1, min_count=1)
    rebalance_dates = month_end_dates(weights.index)
    rows: list[dict[str, float]] = []
    for date in rebalance_dates:
        if date not in weights.index:
            continue
        position = weights.index.get_indexer([date])[0]
        forward_window = port_r.iloc[position + 1 : position + 1 + forward].dropna()
        if len(forward_window) < forward // 2:
            continue
        w = weights.loc[date]
        w = w[w.abs() > 0]
        if w.empty:
            continue
        predicted, factor_var_t, idio_var_t = predict_portfolio_vol(
            w,
            betas.loc[date] if date in betas.index else pd.Series(dtype=float),
            float(factor_var.loc[date]) if date in factor_var.index else np.nan,
            idio_var.loc[date] if date in idio_var.index else pd.Series(dtype=float),
        )
        realized = float(forward_window.std(ddof=1) * np.sqrt(252.0))
        rows.append(
            {
                "date": date,
                "predicted_vol_ann": predicted,
                "realized_vol_ann": realized,
                "bias_ratio": (
                    realized / predicted if predicted and predicted > 0 else np.nan
                ),
                "factor_variance": factor_var_t,
                "idio_variance": idio_var_t,
                "factor_share": (
                    factor_var_t / (factor_var_t + idio_var_t)
                    if (factor_var_t + idio_var_t) > 0
                    else np.nan
                ),
                "gross": float(w.abs().sum()),
                "net": float(w.sum()),
            }
        )
    out = pd.DataFrame(rows).set_index("date")
    return out
