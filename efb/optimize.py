"""Sprint E8: the constrained mean-variance optimizer (cvxpy).

The objective is maximize alpha'w - (lambda / 2) w' Sigma w with
Sigma = X F X' + D, subject to gross, net, position caps, sector-neutral
and beta-neutral equalities. lambda is set so the unconstrained solution
hits the book's volatility target, which keeps the constrained book
comparable to the unconstrained one.
"""

from __future__ import annotations

from pathlib import Path

import cvxpy as cp
import numpy as np
import pandas as pd

from efb import size as size_mod

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"

POSITION_CAP = 0.05  # per-name cap as a share of gross
GROSS_CAP = 1.0


def _sector_columns(date: pd.Timestamp, names: list[str], root: Path) -> np.ndarray:
    """One-hot sector dummies for the names, reference sector dropped."""
    sectors = pd.read_parquet(root / "processed" / "sectors.parquet")
    sector_col = [c for c in sectors.columns if c != "ticker"][0]
    codes = sectors.set_index("ticker")[sector_col].reindex(names).astype(str)
    unique = sorted(set(codes.dropna()))
    if not unique:
        return np.zeros((len(names), 0))
    reference = unique[-1]  # the model's dropped reference sector
    kept = [sector for sector in unique if sector != reference]
    out = np.zeros((len(names), len(kept)))
    for column, sector in enumerate(kept):
        out[:, column] = (codes == sector).to_numpy(dtype=float)
    return out


def _risk_aversion(
    alpha: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
) -> float:
    """lambda = sqrt(alpha' Sigma^-1 alpha) / target_vol, the unconstrained scale."""
    d_inv = 1.0 / np.maximum(specific, 1e-12)
    xd = design * d_inv[:, None]
    inner = np.linalg.inv(factor_covariance) + design.T @ xd
    v = np.linalg.solve(inner, design.T @ (d_inv * alpha))
    inv_alpha = d_inv * alpha - d_inv * (design @ v)
    var = float(alpha @ inv_alpha)
    if not np.isfinite(var) or var <= 0:
        return 1.0
    return float(np.sqrt(var) / size_mod.TARGET_VOL)


def constrained_mv(
    alpha: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
    date: pd.Timestamp,
    names: list[str],
    root: Path,
) -> np.ndarray:
    """The constrained mean-variance weights on one rebalance date.

    Constraints: gross <= 1, net = 0 (long/short), |w_i| <= cap,
    sector-neutral, beta-neutral to the five non-market styles. The market
    column is the intercept the design carries, so beta-neutrality to it is
    the net constraint itself.
    """
    n = len(alpha)
    alpha = np.where(np.isfinite(alpha), alpha, 0.0)
    specific = np.where(
        np.isfinite(specific) & (specific > 0), specific, float(np.nanmedian(specific))
    )
    sector_columns = _sector_columns(date, names, root)
    style_columns = design[:, 1:6]  # the five non-market styles
    lam = _risk_aversion(alpha, design, factor_covariance, specific)
    w = cp.Variable(n)
    risk = cp.quad_form(w, design @ factor_covariance @ design.T + np.diag(specific))
    objective = cp.Maximize(alpha @ w - 0.5 * lam * risk)
    constraints = [
        cp.norm1(w) <= GROSS_CAP,
        cp.sum(w) == 0,
        cp.abs(w) <= POSITION_CAP,
    ]
    if sector_columns.shape[1]:
        constraints.append(sector_columns.T @ w == 0)
    constraints.append(style_columns.T @ w == 0)
    problem = cp.Problem(objective, constraints)
    try:
        problem.solve(solver=cp.OSQP, max_iter=400_000, eps_abs=1e-11, eps_rel=1e-11)
    except Exception:  # pragma: no cover - a numeric failure falls back
        return np.zeros(n)
    if w.value is None:
        return np.zeros(n)
    return np.asarray(w.value, dtype=float)


def constraint_violations(
    weights: np.ndarray,
    design: np.ndarray,
    date: pd.Timestamp,
    names: list[str],
    root: Path,
    cap: float = POSITION_CAP,
) -> dict[str, float]:
    """The maximum violation of each constraint (F8.3)."""
    sector_columns = _sector_columns(date, names, root)
    style_columns = design[:, 1:6]
    return {
        "gross": float(max(np.abs(weights).sum() - GROSS_CAP, 0.0)),
        "net": float(abs(weights.sum())),
        "position_cap": float(max(np.abs(weights).max() - cap, 0.0)),
        "sector_neutral": (
            float(np.abs(sector_columns.T @ weights).max())
            if sector_columns.shape[1]
            else 0.0
        ),
        "beta_neutral": float(np.abs(style_columns.T @ weights).max()),
    }
