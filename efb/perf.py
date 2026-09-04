"""Performance-metrics library (Sprint E1, Task 5).

Every later sprint reports Sharpe with its standard error. Formulas follow
the PRD:

- Sharpe: SR = mean(x) / std(x, ddof=1), annualized by sqrt(252) under
  i.i.d. only.
- i.i.d. standard error: sqrt((1 + SR^2 / 2) / T).
- Lo (2002) autocorrelation-consistent standard error:
  sqrt((1 / T) * (A + (SR^2 / 2) * B)) where
  A = 1 + 2 * sum_k w_k * rho_k (rho_k = autocorrelation of x),
  B = 1 + 2 * sum_k w_k * phi_k (phi_k = autocorrelation of x^2),
  w_k = 1 - k / (q + 1), default q = 5. Reduces to the i.i.d. formula
  when all autocorrelations are zero.
- Max drawdown: D_t = W_t / max_{s <= t} W_s - 1, MDD = min_t D_t.
- Hit rate: fraction of positive periods.
- Slugging: mean positive return / abs(mean negative return).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def sharpe_ratio(excess: pd.Series) -> float:
    """Daily Sharpe ratio of an excess-return series (zero mean floor)."""
    x = excess.dropna()
    std = x.std(ddof=1)
    if std == 0 or np.isnan(std):
        return float("nan")
    return float(x.mean() / std)


def annualized_sharpe(excess: pd.Series) -> float:
    """Sharpe annualized by sqrt(252); correct only under i.i.d."""
    return sharpe_ratio(excess) * np.sqrt(TRADING_DAYS)


def sharpe_se_iid(excess: pd.Series) -> float:
    """Daily standard error of SR under i.i.d.: sqrt((1 + SR^2 / 2) / T)."""
    x = excess.dropna()
    sr = sharpe_ratio(x)
    return float(np.sqrt((1 + sr**2 / 2) / len(x)))


def _newy_west_acf_sum(values: np.ndarray, q: int) -> float:
    """Sum of Newey-West weighted autocorrelations of a zero-mean series."""
    x = values - values.mean()
    var = float(np.dot(x, x)) / len(x)
    if var == 0:
        return 0.0
    total = 0.0
    for k in range(1, q + 1):
        w = 1.0 - k / (q + 1)
        total += w * float(np.dot(x[:-k], x[k:]) / len(x)) / var
    return total


def sharpe_se_lo2002(excess: pd.Series, q: int = 5) -> float:
    """Daily standard error of SR with Lo (2002) autocorrelation correction.

    Uses the autocorrelation of excess returns (rho_k) for the mean term
    and the autocorrelation of squared excess returns (phi_k) for the
    volatility term, with Newey-West weights w_k = 1 - k / (q + 1).
    """
    x = excess.dropna()
    sr = sharpe_ratio(x)
    a = 1.0 + 2.0 * _newy_west_acf_sum(x.to_numpy(), q)
    b = 1.0 + 2.0 * _newy_west_acf_sum((x**2).to_numpy(), q)
    return float(np.sqrt((a + (sr**2 / 2) * b) / len(x)))


def drawdown_series(wealth: pd.Series) -> pd.Series:
    """Running drawdown: D_t = W_t / max_{s <= t} W_s - 1."""
    w = wealth.dropna()
    peak = w.cummax()
    return w / peak - 1.0


def max_drawdown(wealth: pd.Series) -> float:
    """Maximum drawdown as a negative number (min of the drawdown path)."""
    dd = drawdown_series(wealth)
    return float(dd.min()) if len(dd) else float("nan")


def hit_rate(excess: pd.Series) -> float:
    """Fraction of periods with positive excess return."""
    x = excess.dropna()
    return float((x > 0).mean()) if len(x) else float("nan")


def slugging_ratio(excess: pd.Series) -> float:
    """Mean positive return divided by absolute mean negative return."""
    x = excess.dropna()
    wins = x[x > 0]
    losses = x[x < 0]
    if wins.empty or losses.empty or losses.mean() == 0:
        return float("nan")
    return float(wins.mean() / abs(losses.mean()))
