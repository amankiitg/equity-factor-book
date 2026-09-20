"""Statistical factor models: PCA on total returns and on XS-v1 residuals.

Sprint E4, Task 1. The model family is deliberately plain: standardize each
name's returns over the window to unit variance, eigendecompose the resulting
correlation matrix, keep k factors, and leave the discarded eigenvalues in a
diagonal residual variance. That is the PCA model of the roadmap,
`Sigma_k = V_k Lambda_k V_k' + diag(residual variance)`.

Three factor counts are produced for the same spectrum and all three are
stored, because they answer different questions. Scree is what an analyst sees.
The Marchenko-Pastur edge is what random matrix theory says is signal at this N
and T, and it is computed from the N and T the window actually used rather than
from round numbers. Cross-validated likelihood is the one that costs compute
and asks whether the extra factors pay for themselves out of sample.

The residual PCA is the missing-factor detector: the same procedure applied to
the specific returns XS-v1 leaves behind. A large residual eigenvalue above its
own edge means the fundamental model is missing something common.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from efb import hygiene

PCA_WINDOW = 504
MAX_FACTORS = 20
DEFAULT_KS = tuple(range(1, 13))


@dataclass
class PcaFit:
    """One eigendecomposition of a standardized return block."""

    tickers: list[str]
    n_names: int
    n_days: int
    eigenvalues: np.ndarray
    eigenvectors: np.ndarray
    explained_share: np.ndarray
    mean: pd.Series
    std: pd.Series

    @property
    def n_over_t(self) -> float:
        return self.n_names / self.n_days

    @property
    def mp_edge(self) -> float:
        """The Marchenko-Pastur upper edge for a correlation matrix."""
        return (1.0 + np.sqrt(self.n_over_t)) ** 2

    def loadings(self, n_factors: int) -> np.ndarray:
        return self.eigenvectors[:, :n_factors]

    def factor_returns(self, z: np.ndarray, n_factors: int) -> np.ndarray:
        """Factor returns scaled so each column is a unit-exposure portfolio."""
        return z @ self.eigenvectors[:, :n_factors]

    def residual_variance(self, n_factors: int) -> np.ndarray:
        """Diagonal residual variance of the rank-k approximation.

        On a correlation matrix the diagonal is 1, so the residual for name i
        is one minus the variance the kept factors give that name: the standard
        PCA factor model's Psi, and it is name specific rather than a constant.
        """
        load = self.loadings(n_factors)
        kept = np.einsum("ij,j,ij->i", load, self.eigenvalues[:n_factors], load)
        return np.clip(1.0 - kept, 1e-10, None)

    def covariance(self, n_factors: int) -> np.ndarray:
        load = self.loadings(n_factors)
        return load @ np.diag(self.eigenvalues[:n_factors]) @ load.T + np.diag(
            self.residual_variance(n_factors)
        )


@dataclass
class FactorCounts:
    """The three counts, plus the numbers a reader needs to judge them."""

    scree: int
    marchenko_pastur: int
    cross_validated: int | None
    edge: float
    n_over_t: float
    cv_scores: dict[int, float] = field(default_factory=dict)

    @property
    def selected(self) -> int:
        """The count that prices risk: the Marchenko-Pastur count, floored at 1."""
        return max(self.marchenko_pastur, 1)


def clean_wide(returns_frame: pd.DataFrame) -> pd.DataFrame:
    """The pane's clean returns, wide: dates down, names across.

    Stale and outlier rows are set to NaN by `efb.hygiene.clean_returns`, so
    every window in this module excludes them without a second rule.
    """
    cleaned = hygiene.clean_returns(returns_frame)
    return cleaned.unstack("ticker")


def complete_block(
    wide: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    window: int = PCA_WINDOW,
) -> pd.DataFrame:
    """The estimation block: `window` sessions ending at `as_of`, whole names.

    A name enters the block only with a complete history inside the window, so
    N is a clean number for the Marchenko-Pastur edge and no window is spliced
    across a gap. Nothing is imputed, which is why the block is narrower than
    the panel.
    """
    frame = wide.dropna(how="all")
    if as_of is not None:
        frame = frame.loc[:as_of]
    block = frame.iloc[-window:]
    block = block.loc[:, block.notna().all(axis=0)]
    return block


def standardize(block: pd.DataFrame) -> tuple[np.ndarray, pd.Series, pd.Series]:
    """Cross-time standardization of a complete block, column by column."""
    mean = block.mean()
    std = block.std(ddof=1).replace(0.0, np.nan)
    z = (block - mean) / std
    if not np.isfinite(z.to_numpy()).all():
        raise ValueError("the block carries a zero-variance or missing column")
    return z.to_numpy(dtype=float), mean, std


def fit(block: pd.DataFrame) -> PcaFit:
    """Eigendecompose the correlation matrix of a standardized block."""
    z, mean, std = standardize(block)
    n_days, n_names = z.shape
    if n_names < 2 or n_days < 2:
        raise ValueError("a factor model needs at least two names and two days")
    matrix = z.T @ z / n_days
    values, vectors = np.linalg.eigh(matrix)
    order = np.argsort(values)[::-1]
    values = np.clip(values[order], 0.0, None)
    vectors = vectors[:, order]
    total = float(values.sum())
    return PcaFit(
        tickers=list(block.columns),
        n_names=n_names,
        n_days=n_days,
        eigenvalues=values,
        eigenvectors=vectors,
        explained_share=values / total,
        mean=mean,
        std=std,
    )


def mp_edge(n_names: int, n_days: int) -> float:
    """`(1 + sqrt(N/T))^2`, the upper edge of the MP support for a correlation."""
    return (1.0 + np.sqrt(n_names / n_days)) ** 2


def count_mp(fit: PcaFit) -> int:
    edge = fit.mp_edge
    return int(np.sum(fit.eigenvalues > edge))


def count_scree(fit: PcaFit, max_factors: int = MAX_FACTORS) -> int:
    """The elbow of the log spectrum: the largest drop after the leading one.

    The first gap is always the largest for equity returns, so including it
    would make this rule return 1 for every window and say nothing. The elbow
    is therefore taken over the gaps from the second eigenvalue on, and it is
    stored as a diagnostic rather than as a criterion.
    """
    values = fit.eigenvalues[1 : max_factors + 2]
    if len(values) < 2:
        return 1
    drops = np.log(np.maximum(values[:-1], 1e-12)) - np.log(
        np.maximum(values[1:], 1e-12)
    )
    return int(np.argmax(drops) + 2)


def held_out_log_likelihood(
    fit_train: PcaFit, z_test: np.ndarray, n_factors: int
) -> float:
    """Gaussian log-likelihood of held-out standardized rows under Sigma_k."""
    sigma = fit_train.covariance(n_factors)
    sign, log_det = np.linalg.slogdet(sigma)
    if sign <= 0:
        return -np.inf
    solved = np.linalg.solve(sigma, z_test.T)
    quadratic = np.einsum("ij,ji->i", z_test, solved)
    n_test, n_names = z_test.shape
    normalizer = n_names * np.log(2.0 * np.pi)
    return float(-0.5 * n_test * (normalizer + log_det) - 0.5 * quadratic.sum())


def count_cv(
    block: pd.DataFrame,
    ks: tuple[int, ...] = DEFAULT_KS,
    n_folds: int = 4,
) -> tuple[int, dict[int, float]]:
    """Cross-validated likelihood over contiguous time folds.

    Folds are contiguous blocks of sessions rather than random rows, because
    the rows are a time series and a random split would leak the same names'
    neighbouring days into the held-out set.
    """
    n_days = len(block)
    if n_days < n_folds * 20:
        return 0, {}
    bounds = np.linspace(0, n_days, n_folds + 1).astype(int)
    scores: dict[int, float] = {}
    for k in ks:
        total = 0.0
        for fold in range(n_folds):
            test_idx = np.arange(bounds[fold], bounds[fold + 1])
            train_idx = np.setdiff1d(np.arange(n_days), test_idx)
            train = block.iloc[train_idx]
            test = block.iloc[test_idx]
            z_train, mean, std = standardize(train)
            train_fit = fit(train)
            z_test = ((test - mean) / std).to_numpy(dtype=float)
            total += held_out_log_likelihood(train_fit, z_test, k)
        scores[k] = total
    best = max(scores, key=lambda key: scores[key])
    return int(best), scores


def rotate_varimax(
    loadings: np.ndarray, n_iter: int = 100, tol: float = 1e-8
) -> np.ndarray:
    """Varimax rotation of a loading matrix, so the factors can be named."""
    matrix = loadings.copy()
    n_cols = matrix.shape[1]
    if n_cols < 2:
        return matrix
    rotation = np.eye(n_cols)
    previous = 0.0
    for _ in range(n_iter):
        transformed = matrix @ rotation
        column_norms = np.sum(transformed**2, axis=0)
        centred = transformed**3 - transformed @ np.diag(column_norms) / n_cols
        u, singular, vh = np.linalg.svd(matrix.T @ centred)
        rotation = u @ vh
        objective = float(np.sum(singular))
        if abs(objective - previous) < tol:
            break
        previous = objective
    return matrix @ rotation


def spectrum_frame(fit: PcaFit, label: str) -> pd.DataFrame:
    """The stored spectrum: one row per eigenvalue, with the counts beside it."""
    return pd.DataFrame(
        {
            "model": label,
            "index": np.arange(1, fit.n_names + 1),
            "eigenvalue": fit.eigenvalues,
            "explained_share": fit.explained_share,
            "cumulative_share": np.cumsum(fit.explained_share),
            "mp_edge": fit.mp_edge,
            "n_names": fit.n_names,
            "n_days": fit.n_days,
            "n_over_t": fit.n_over_t,
            "above_edge": fit.eigenvalues > fit.mp_edge,
        }
    )


def loadings_frame(fit: PcaFit, n_factors: int, label: str) -> pd.DataFrame:
    """The stored loadings, unrotated and rotated, long by (factor, ticker)."""
    raw = fit.loadings(n_factors)
    rotated = rotate_varimax(raw)
    rows: list[dict[str, object]] = []
    for position in range(n_factors):
        name = f"{label}_{position + 1:02d}"
        for index, ticker in enumerate(fit.tickers):
            rows.append(
                {
                    "model": label,
                    "factor": name,
                    "ticker": ticker,
                    "loading": float(raw[index, position]),
                    "loading_rotated": float(rotated[index, position]),
                    "eigenvalue": float(fit.eigenvalues[position]),
                    "explained_share": float(fit.explained_share[position]),
                }
            )
    return pd.DataFrame(rows)


def factor_returns_frame(
    fit: PcaFit, block: pd.DataFrame, n_factors: int, label: str
) -> pd.DataFrame:
    """Factor returns from the standardized block, one row per (date, factor)."""
    z, _, _ = standardize(block)
    values = fit.factor_returns(z, n_factors)
    rows: list[dict[str, object]] = []
    for position in range(n_factors):
        name = f"{label}_{position + 1:02d}"
        for row, date in enumerate(block.index):
            rows.append(
                {
                    "model": label,
                    "date": date,
                    "factor": name,
                    "f": float(values[row, position]),
                }
            )
    return pd.DataFrame(rows)


def run(
    returns_frame: pd.DataFrame,
    specific_frame: pd.DataFrame | None = None,
    as_of: pd.Timestamp | None = None,
    window: int = PCA_WINDOW,
    ks: tuple[int, ...] = DEFAULT_KS,
    tickers: list[str] | None = None,
    label: str = "total",
    with_residuals: bool = True,
) -> dict[str, Any]:
    """Fit the factor model on one universe and return every stored frame.

    INPUT: the panel's long returns frame, optionally the XS-v1 specific
    return frame, and optionally the ticker list that defines the universe.
    OUTPUT: the spectrum, the loadings and the factor returns, plus a
    diagnostics block with the three factor counts, the edge and the residual
    audit. The caller decides the universe, so the build can run the same
    procedure on the sector-mapped model universe and on the wider panel and
    store both spectra side by side.
    """
    wide = clean_wide(returns_frame)
    if tickers is not None:
        keep = [name for name in wide.columns if name in set(tickers)]
        wide = wide[keep]
    block = complete_block(wide, as_of=as_of, window=window)
    if block.empty:
        raise ValueError("no complete block at this as_of and window")

    total_fit = fit(block)
    counts = FactorCounts(
        scree=count_scree(total_fit),
        marchenko_pastur=count_mp(total_fit),
        cross_validated=None,
        edge=total_fit.mp_edge,
        n_over_t=total_fit.n_over_t,
    )
    if len(ks) > 1:
        counts.cross_validated, counts.cv_scores = count_cv(block, ks=ks)
    n_factors = counts.selected

    frames: dict[str, object] = {
        "spectrum": spectrum_frame(total_fit, label),
        "loadings": loadings_frame(total_fit, n_factors, label),
        "factor_returns": factor_returns_frame(total_fit, block, n_factors, label),
        "diagnostics": {"total": counts, "fit": total_fit, "label": label},
    }

    if with_residuals and specific_frame is not None and not specific_frame.empty:
        specific_wide = specific_frame.pivot(
            index="date", columns="ticker", values="specific_return"
        )
        specific_block = complete_block(specific_wide, as_of=as_of, window=window)
        if not specific_block.empty:
            residual_fit = fit(specific_block)
            residual_counts = FactorCounts(
                scree=count_scree(residual_fit),
                marchenko_pastur=count_mp(residual_fit),
                cross_validated=None,
                edge=residual_fit.mp_edge,
                n_over_t=residual_fit.n_over_t,
            )
            residual_k = residual_counts.selected
            frames["residual_spectrum"] = spectrum_frame(residual_fit, "specific")
            frames["residual_loadings"] = loadings_frame(
                residual_fit, residual_k, "specific"
            )
            frames["residual_factor_returns"] = factor_returns_frame(
                residual_fit, specific_block, residual_k, "specific"
            )
            frames["residual_diagnostics"] = {
                "counts": residual_counts,
                "fit": residual_fit,
                "largest_eigenvalue": float(residual_fit.eigenvalues[0]),
                "edge": float(residual_fit.mp_edge),
                "above_edge": bool(residual_fit.eigenvalues[0] > residual_fit.mp_edge),
            }
    return frames


RESIDUAL_FLOOR = 1e-12


@dataclass
class ResidualCovariance:
    """XS-v2's specific block: k residual PCs plus the shrunk diagonal remainder.

    The fit is the project's residual PCA, a correlation fit on the specific
    returns with k by the Marchenko-Pastur count, rescaled by each name's
    sample specific standard deviation so the low-rank block is a covariance of
    the same returns the diagonal D is a variance of. The shrunk diagonal
    remainder is XS-v1's D minus the variance the k factors already carry on
    the diagonal, clipped at a floor. With k = 0 the block is exactly diag(D);
    with k > 0 the diagonal never falls below D and the off-diagonal specific
    covariance the k factors carry is added on top.
    """

    tickers: list[str]
    n_names: int
    n_days: int
    k: int
    edge: float
    eigenvalues: np.ndarray  # the k kept correlation eigenvalues
    loadings: np.ndarray  # N x k unit eigenvectors
    std: np.ndarray  # sample specific standard deviations over the window
    diagonal: np.ndarray  # D, the XS-v1 shrunk specific variance
    floor: float

    def low_rank_diagonal(self) -> np.ndarray:
        kept = np.einsum("ij,j,ij->i", self.loadings, self.eigenvalues, self.loadings)
        return self.std**2 * kept

    @property
    def remainder(self) -> np.ndarray:
        return np.clip(self.diagonal - self.low_rank_diagonal(), self.floor, None)

    def low_rank(self) -> np.ndarray:
        scaled = self.loadings * self.std[:, None]
        return scaled @ np.diag(self.eigenvalues) @ scaled.T

    def matrix(self) -> np.ndarray:
        return self.low_rank() + np.diag(self.remainder)

    @property
    def trace_diagonal(self) -> float:
        return float(np.sum(self.diagonal))

    @property
    def trace_total(self) -> float:
        return float(self.low_rank().trace() + np.sum(self.remainder))


def residual_covariance(
    specific_block: pd.DataFrame,
    diagonal: pd.Series,
    k: int | None = None,
    floor: float = RESIDUAL_FLOOR,
) -> ResidualCovariance:
    """XS-v2's replacement for the XS-v1 specific diagonal D.

    INPUT: a complete wide block of specific returns (dates down, names
    across) and the shrunk specific variance D for those names at the same
    as-of date. OUTPUT: the low-rank plus diagonal block, with k by the
    Marchenko-Pastur count `count_mp` unless one is given, which is the same
    rule the residual audit already uses on the same data.
    """
    if specific_block.empty:
        raise ValueError("a residual covariance needs a specific-return block")
    if specific_block.isna().any().any():
        raise ValueError("the specific-return block must be complete")
    fitted = fit(specific_block)
    if k is None:
        k = count_mp(fitted)
    k = int(max(k, 0))
    diagonal_values = diagonal.reindex(specific_block.columns).to_numpy(dtype=float)
    if not np.isfinite(diagonal_values).all():
        raise ValueError("the specific variance diagonal carries NaN")
    return ResidualCovariance(
        tickers=list(specific_block.columns),
        n_names=fitted.n_names,
        n_days=fitted.n_days,
        k=k,
        edge=fitted.mp_edge,
        eigenvalues=fitted.eigenvalues[:k].copy(),
        loadings=fitted.eigenvectors[:, :k].copy(),
        std=fitted.std.to_numpy(dtype=float),
        diagonal=diagonal_values,
        floor=floor,
    )
