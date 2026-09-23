"""Shared robust sizing for the live path.

Procedure 6.3 sizes on D^-1 alpha and hedges with the exact in-model FMPs.
The exact hedge solves X'X, which is singular when the kept subset is too
small to span the factor space; the robust variant falls back to the
pseudoinverse, which still recovers the exact hedge when the exposure lies
in the column space of X'X and reports the best achievable hedge otherwise.
"""

from __future__ import annotations

import numpy as np

from efb import size


def hedge_exact_robust(design: np.ndarray, exposures: np.ndarray) -> np.ndarray:
    """The exact in-model FMP hedge, pseudoinverse fallback for rank-deficient
    subsets. The achieved exposure is the caller's to report."""
    try:
        loadings = np.linalg.solve(design.T @ design, exposures)
    except np.linalg.LinAlgError:
        loadings = np.linalg.pinv(design.T @ design) @ exposures
    return -(design @ loadings)


def procedure_6_3_robust(
    alpha: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
) -> np.ndarray:
    """Procedure 6.3 on a subset, with the least-squares hedge fallback."""
    del factor_covariance  # the hedge does not read it, matching procedure_6_3
    sized = size.proportional(alpha, specific)
    exposures = design.T @ sized
    return sized + hedge_exact_robust(design, exposures)


def renormalize(weights: np.ndarray, gross: float = 1.0) -> np.ndarray:
    """Scale weights to a target gross, preserving sign and factor neutrality."""
    total = float(np.abs(weights).sum())
    if total <= 0:
        return weights
    return weights * (gross / total)
