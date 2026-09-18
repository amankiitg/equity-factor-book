"""Risk decomposition for XS-v1 (Sprint E3, Tasks 5, 8 and 9).

Sigma = X F X' + D, and the Euler decomposition of a portfolio's volatility:

- sigma_p = sqrt(w' Sigma w)
- MCR_i = (Sigma w)_i / sigma_p
- contribution_i = w_i MCR_i, and the contributions sum to sigma_p
- factor contribution k = x_k (F x)_k / sigma_p with the exposure x = X'w
- percent of variance = w_i (Sigma w)_i / (w' Sigma w), which sums to one

Everything is computed point in time: the factor covariance used at a date is
estimated from factor returns up to that date, and the specific variance comes
from that date's own row of the artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from efb.models import fundamental as fx

TRADING_DAYS = 252
DEFAULT_HORIZON = 21


@dataclass
class RiskDecomposition:
    """One book on one date, split into factor and idio risk."""

    book: str
    date: pd.Timestamp
    sigma_p: float
    total_variance: float
    factor_variance: float
    idio_variance: float
    exposures: pd.Series
    weights: pd.Series
    mcr: pd.Series
    contribution: pd.Series
    percent_of_variance: pd.Series
    residual_weight: float
    n_names: int
    n_specific_var_filled: int
    top_mcr: list[tuple[str, float]] = field(default_factory=list)

    @property
    def factor_share(self) -> float:
        return (
            self.factor_variance / self.total_variance
            if self.total_variance
            else np.nan
        )

    @property
    def idio_share(self) -> float:
        return (
            self.idio_variance / self.total_variance if self.total_variance else np.nan
        )


def load_book(path: Path | str, date: pd.Timestamp | None = None) -> pd.Series:
    """Weight vector of a seed book, at one rebalance or on the last date.

    INPUT: a long frame with date, ticker, weight. OUTPUT: a Series indexed by
    ticker. When `date` is None the book's last date is used.
    """
    frame = pd.read_parquet(path)
    target = frame["date"].max() if date is None else pd.Timestamp(date)
    rows = frame.loc[frame["date"] == target]
    if rows.empty:
        raise ValueError(f"no weights in {path} on {target}")
    return rows.set_index("ticker")["weight"].astype(float)


def book_dates(path: Path | str) -> list[pd.Timestamp]:
    """Rebalance dates of a seed book, in order."""
    frame = pd.read_parquet(path)
    return list(pd.to_datetime(frame["date"].unique()))


def decompose(
    book: str,
    date: pd.Timestamp,
    weights: pd.Series,
    day: fx.CrossSection,
    factor_cov: pd.DataFrame,
    specific_var: pd.Series,
    top_n: int = 5,
) -> RiskDecomposition:
    """Full risk decomposition of one book on one date.

    INPUT: book name, the date, the book's weights (ticker to weight, long or
    short), the day's cross-section, the factor covariance up to that date and
    the specific variance for that date.
    OUTPUT: a RiskDecomposition. A name in the book with no descriptor row is
    dropped from the risk model and its weight is reported as
    `residual_weight` rather than silently spread over the rest.
    """
    names = factor_cov.index
    aligned = weights.reindex(day.tickers)
    usable = aligned.notna()
    w = aligned.fillna(0.0).to_numpy(dtype=float)
    total_weight = float(weights.sum())
    covered_weight = float(w.sum())
    variance = specific_var.reindex(day.tickers)
    filled = int(variance.isna().sum() and usable.sum())
    fallback = float(variance.median()) if variance.notna().any() else 0.0
    d = variance.fillna(fallback).to_numpy(dtype=float)
    d = np.clip(d, 0.0, None)

    design = day.risk_design
    covariance = factor_cov.reindex(index=names, columns=names).to_numpy(dtype=float)
    exposures = design.T @ w
    factor_variance = float(exposures @ covariance @ exposures)
    idio_variance = float((w**2 * d).sum())
    total_variance = factor_variance + idio_variance
    sigma_p = float(np.sqrt(max(total_variance, 0.0)))
    sigma_w = design @ (covariance @ exposures) + w * d
    mcr = sigma_w / sigma_p if sigma_p else np.zeros_like(sigma_w)
    contribution = w * mcr
    percent = (
        (w * sigma_w) / total_variance if total_variance else np.zeros_like(sigma_w)
    )
    order = np.argsort(-np.abs(mcr))[:top_n]
    top = [(str(day.tickers[i]), float(mcr[i])) for i in order if usable.to_numpy()[i]]
    return RiskDecomposition(
        book=book,
        date=pd.Timestamp(date),
        sigma_p=sigma_p,
        total_variance=total_variance,
        factor_variance=factor_variance,
        idio_variance=idio_variance,
        exposures=pd.Series(exposures, index=names),
        weights=pd.Series(w, index=day.tickers),
        mcr=pd.Series(mcr, index=day.tickers),
        contribution=pd.Series(contribution, index=day.tickers),
        percent_of_variance=pd.Series(percent, index=day.tickers),
        residual_weight=total_weight - covered_weight,
        n_names=int(usable.sum()),
        n_specific_var_filled=filled,
        top_mcr=top,
    )


def decomposition_frame(decomposition: RiskDecomposition) -> pd.DataFrame:
    """The decomposition as a long frame, one row per factor and per name.

    The schema carries a `level` column because the factor level and the name
    level are both needed: the per-factor contribution answers what the
    portfolio is exposed to, and the per-name MCR answers what to trim.
    """
    scale = decomposition.sigma_p if decomposition.sigma_p else np.nan
    rows: list[dict[str, object]] = []
    for factor, exposure in decomposition.exposures.items():
        rows.append(
            {
                "book": decomposition.book,
                "date": decomposition.date,
                "level": "factor",
                "name": factor,
                "factor": factor,
                "weight": np.nan,
                "mcr": np.nan,
                "contribution": np.nan,
                "percent_of_variance": np.nan,
                "exposure": float(exposure),
                "factor_variance": decomposition.factor_variance,
                "idio_variance": decomposition.idio_variance,
                "total_variance": decomposition.total_variance,
                "sigma_p": decomposition.sigma_p,
                "residual_weight": decomposition.residual_weight,
                "n_names": decomposition.n_names,
            }
        )
    total = decomposition.total_variance
    for ticker in decomposition.mcr.index:
        rows.append(
            {
                "book": decomposition.book,
                "date": decomposition.date,
                "level": "name",
                "name": ticker,
                "factor": None,
                "weight": float(decomposition.weights[ticker]),
                "mcr": float(decomposition.mcr[ticker]),
                "contribution": float(decomposition.contribution[ticker]),
                "percent_of_variance": float(decomposition.percent_of_variance[ticker]),
                "exposure": np.nan,
                "factor_variance": decomposition.factor_variance,
                "idio_variance": decomposition.idio_variance,
                "total_variance": total,
                "sigma_p": scale,
                "residual_weight": decomposition.residual_weight,
                "n_names": decomposition.n_names,
            }
        )
    return pd.DataFrame(rows)


def realized_residual_covariance(
    specific_wide: pd.DataFrame, end: pd.Timestamp, window: int = TRADING_DAYS
) -> pd.DataFrame:
    """Realized covariance of specific returns over a trailing window.

    INPUT: the wide specific return frame, the window end date and the window
    length. OUTPUT: the covariance matrix over the names that have every
    session in the window. The window ends at `end`, so nothing dated after
    the decision date enters the estimate.
    """
    history = specific_wide.loc[: pd.Timestamp(end)].tail(window)
    history = history.dropna(axis=1, how="any")
    if history.shape[0] < 2 or history.empty:
        return pd.DataFrame(index=history.columns, columns=history.columns, dtype=float)
    values = history.to_numpy(dtype=float)
    demeaned = values - values.mean(axis=0)
    return pd.DataFrame(
        demeaned.T @ demeaned / (len(values) - 1),
        index=history.columns,
        columns=history.columns,
    )


def realized_idio_variance(weights: pd.Series, covariance: pd.DataFrame) -> float:
    """w' Sigma_resid w on the names the covariance covers."""
    aligned = weights.reindex(covariance.index).fillna(0.0).to_numpy(dtype=float)
    return float(aligned @ covariance.to_numpy(dtype=float) @ aligned)


def exposure_series(
    days: dict[pd.Timestamp, fx.CrossSection],
    weights_by_date: dict[pd.Timestamp, pd.Series],
    factor_names: list[str],
) -> pd.DataFrame:
    """x = X'w per factor at each rebalance, for one book.

    INPUT: the design by date, the book's weights by date and the factor
    order. OUTPUT: a long frame with one row per date and factor. Only dates
    present in both maps are produced, so a rebalance with no design row is
    absent rather than zero.
    """
    rows: list[dict[str, object]] = []
    for date in sorted(set(days) & set(weights_by_date)):
        day = days[date]
        weights = weights_by_date[date]
        aligned = weights.reindex(day.tickers).fillna(0.0).to_numpy(dtype=float)
        exposures = day.risk_design.T @ aligned
        for name, value in zip(factor_names, exposures, strict=True):
            rows.append(
                {
                    "date": date,
                    "factor": name,
                    "exposure": float(value),
                    "n_names": int(
                        (weights.reindex(day.tickers).fillna(0.0) != 0).sum()
                    ),
                    "weight_in_universe": float(
                        weights.reindex(day.tickers).fillna(0.0).abs().sum()
                    ),
                }
            )
    return pd.DataFrame(rows)


def segment_bias(
    days: dict[pd.Timestamp, fx.CrossSection],
    weights_by_date: dict[pd.Timestamp, pd.Series],
    specific_var: pd.DataFrame,
    factor_returns: pd.DataFrame,
    returns: pd.DataFrame,
    horizon: int = DEFAULT_HORIZON,
    half_life: int = fx.F_HALF_LIFE,
    start: str | None = None,
) -> pd.DataFrame:
    """Monthly realized against model-predicted volatility, point in time.

    At each rebalance the model's predicted horizon volatility comes from the
    factor covariance estimated on factor returns up to that date and the
    specific variance of that date, so the bias statistic never uses a
    covariance that the date could not have known. The realized volatility is
    the book's own return over the next `horizon` sessions.
    """
    rows: list[dict[str, object]] = []
    dates = sorted(days)
    positions = {date: index for index, date in enumerate(dates)}
    for date in sorted(set(days) & set(weights_by_date)):
        weights = weights_by_date[date]
        day = days[date]
        aligned = weights.reindex(day.tickers).fillna(0.0)
        if start is not None and day.date < pd.Timestamp(start):
            continue
        history = factor_returns.loc[: day.date]
        if len(history) < half_life:
            continue
        factor_cov = fx.ewma_factor_cov(history, half_life=half_life)
        variance = specific_var.loc[specific_var["date"] == day.date]
        if variance.empty:
            continue
        specific = variance.set_index("ticker")["specific_var"]
        decomposition = decompose("bias", day.date, aligned, day, factor_cov, specific)
        position = positions[day.date]
        forward = returns.iloc[position + 1 : position + 1 + horizon]
        if len(forward) < horizon:
            continue
        book_return = forward.mul(aligned, axis=1).sum(axis=1, min_count=1)
        realized = float(book_return.std(ddof=1) * np.sqrt(TRADING_DAYS))
        # total_variance is a daily variance, so the annualized prediction for
        # the next `horizon` sessions is sqrt(variance * 252) whatever the
        # horizon is.
        predicted = float(
            np.sqrt(max(decomposition.total_variance, 0.0) * TRADING_DAYS)
        )
        rows.append(
            {
                "date": day.date,
                "predicted_vol_ann": predicted,
                "realized_vol_ann": realized,
                "bias_ratio": realized / predicted if predicted else np.nan,
                "factor_variance": decomposition.factor_variance,
                "idio_variance": decomposition.idio_variance,
                "factor_share": decomposition.factor_share,
                "n_names": decomposition.n_names,
                "residual_weight": decomposition.residual_weight,
                "gross": float(aligned.abs().sum()),
                "net": float(aligned.sum()),
            }
        )
    return pd.DataFrame(rows)
