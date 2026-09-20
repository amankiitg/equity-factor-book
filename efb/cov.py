"""The covariance laboratory: estimators, and the test that separates them.

Sprint E4, Task 2. Eight estimators, each returning a matrix with a stated
parameter count and a condition number, and one out-of-sample experiment: build
a minimum-variance portfolio from a 504-day window, hold it for the next 21
sessions without re-estimating, and measure what came out. The estimator that
wins in sample is not the estimator that wins out of sample, which is the whole
point of the exercise.

Every formula is written out rather than imported, so the walkthrough can
reproduce each one by hand:

- sample:            `S = Z' Z / T` on standardized window returns
- EWMA:              exponentially weighted second moments, half-life 63
- Ledoit-Wolf:      `delta F + (1 - delta) S`, `F` the constant-correlation
                     target, `delta` the plug-in intensity
- constant corr:    `F` itself, with the sample variances on the diagonal
- clip:              eigenvalues below the Marchenko-Pastur edge replaced by
                     their mean, the rest kept
- TS-v1:             `beta beta' var(market) + diag(specific variance)`
- XS-v1:             `X F X' + D` from the stored descriptors, factor
                     covariance and specific variance
- PCA-v1:            `V_k Lambda_k V_k' + diag(residual variance)` from Task 1

The shrinkage intensity deserves a note because it is easy to get wrong. With
the sample covariance as the estimator and a target built from it, the
`rho` term of the Ledoit-Wolf plug-in vanishes exactly, because the sample
second moment of the standardized window is the sample covariance by
construction. What remains is `delta = pi / gamma`, clipped into [0, 1], where
`pi` is the total sampling variance of the covariance entries and `gamma` is
the total distance between the target and the sample matrix.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from efb.models import statistical as st

EWMA_HALF_LIFE = 63
MIN_VARIANCE_DAYS = 21
WINDOW = st.PCA_WINDOW


@dataclass
class EstimatorResult:
    """One estimator's matrix and the numbers a comparison table needs."""

    name: str
    matrix: np.ndarray
    parameter_count: int
    condition_number: float
    extra: dict[str, float] = field(default_factory=dict)


def _as_matrix(values: np.ndarray) -> np.ndarray:
    return np.asarray(values, dtype=float)


def condition_number(matrix: np.ndarray) -> float:
    values = np.linalg.eigvalsh((matrix + matrix.T) / 2.0)
    smallest = float(np.min(values))
    if smallest <= 0:
        return float("inf")
    return float(np.max(values) / smallest)


def parameter_count(name: str, n_names: int, n_factors: int | None = None) -> int:
    """The number of free parameters each estimator spends."""
    if name in {"sample", "ewma"}:
        return n_names * (n_names + 1) // 2
    if name == "constant_correlation":
        return n_names + 1
    if name == "ledoit_wolf":
        return 2
    if name == "clip":
        return n_names + (n_factors or 0)
    if name == "ts_v1":
        return 2 * n_names
    if name in {"xs_v1", "pca_v1", "pca_v1c"}:
        return (n_factors or 0) + n_names
    raise ValueError(f"unknown estimator {name}")


def sample_cov(z: np.ndarray) -> np.ndarray:
    n_days = z.shape[0]
    return z.T @ z / n_days


def ewma_cov(z: np.ndarray, half_life: int = EWMA_HALF_LIFE) -> np.ndarray:
    """Exponentially weighted second moments, most recent day weighted most."""
    n_days = z.shape[0]
    decay = 0.5 ** (1.0 / half_life)
    ages = np.arange(n_days)[::-1]
    weights = decay**ages
    weights = weights / weights.sum()
    return (z * weights[:, None]).T @ z


def constant_correlation_target(sample: np.ndarray) -> tuple[np.ndarray, float]:
    """The constant-correlation target: sample variances, one average rho."""
    variances = np.diag(sample).copy()
    std = np.sqrt(np.maximum(variances, 1e-18))
    correlation = sample / np.outer(std, std)
    n_names = sample.shape[0]
    off_diagonal = ~np.eye(n_names, dtype=bool)
    mean_rho = float(correlation[off_diagonal].mean())
    target = mean_rho * np.outer(std, std)
    np.fill_diagonal(target, variances)
    return target, mean_rho


def shrinkage_intensity(
    z: np.ndarray, sample: np.ndarray, target: np.ndarray
) -> dict[str, float]:
    """The Ledoit-Wolf plug-in intensity for a target built from the sample.

    `pi` is the total sampling variance of the covariance entries, computed
    from the second moment of the outer products, and `gamma` is the total
    distance between the target and the sample matrix. The intensity carries a
    `1/T`, which is what turns a ratio of two totals into the weight the
    shrinkage actually needs: without it the ratio is O(T) too large and clips
    at one, which silently replaces the estimator by its target.

    `rho` is the cross term. With the sample covariance as the estimator it is
    close to zero by cancellation rather than exactly zero, so it is returned
    rather than assumed.
    """
    n_days = z.shape[0]
    squared = z**2
    second_moment = squared.T @ squared / n_days
    pi_hat = float(np.sum(second_moment - sample**2))
    rho_hat = float(np.sum((second_moment - sample) * (target - sample)))
    gamma_hat = float(np.sum((target - sample) ** 2))
    if gamma_hat <= 0:
        return {"delta": 0.0, "pi": pi_hat, "rho": rho_hat, "gamma": gamma_hat}
    delta = float(np.clip((pi_hat - rho_hat) / (gamma_hat * n_days), 0.0, 1.0))
    return {"delta": delta, "pi": pi_hat, "rho": rho_hat, "gamma": gamma_hat}


def ledoit_wolf(z: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
    sample = sample_cov(z)
    target, mean_rho = constant_correlation_target(sample)
    parts = shrinkage_intensity(z, sample, target)
    delta = parts["delta"]
    shrunk = delta * target + (1.0 - delta) * sample
    parts["mean_rho"] = mean_rho
    return shrunk, parts


def constant_correlation(z: np.ndarray) -> np.ndarray:
    target, _ = constant_correlation_target(sample_cov(z))
    return target


def clip_eigenvalues(
    z: np.ndarray, n_keep: int | None = None
) -> tuple[np.ndarray, int]:
    """Eigenvalues below the MP edge replaced by their mean, the rest kept.

    The count above the edge is what the criterion F4.2 stores, and it is
    computed from this window's own N and T.
    """
    sample = sample_cov(z)
    values, vectors = np.linalg.eigh(sample)
    order = np.argsort(values)[::-1]
    values = np.clip(values[order], 0.0, None)
    vectors = vectors[:, order]
    n_names, n_days = sample.shape
    edge = st.mp_edge(n_names, n_days)
    above = int(np.sum(values > edge))
    keep = above if n_keep is None else n_keep
    if keep < n_names:
        noise = values[keep:]
        replacement = float(noise.mean()) if len(noise) else 0.0
        values = np.concatenate([values[:keep], np.full(n_names - keep, replacement)])
    return vectors @ np.diag(values) @ vectors.T, above


def market_model_cov(z: np.ndarray, market: np.ndarray | None = None) -> np.ndarray:
    """TS-v1's shape: one market factor with stock betas and specific variance."""
    if market is None:
        market = z.mean(axis=1)
    market_variance = float(np.var(market, ddof=1))
    betas = np.array(
        [
            float(np.cov(z[:, j], market, ddof=1)[0, 1] / market_variance)
            for j in range(z.shape[1])
        ]
    )
    specific = z - np.outer(market, betas)
    specific_variance = np.var(specific, axis=0, ddof=1)
    return market_variance * np.outer(betas, betas) + np.diag(specific_variance)


def factor_cov(
    design: np.ndarray, factor_covariance: np.ndarray, specific: np.ndarray
) -> np.ndarray:
    """The generic factor estimator: `X F X' + diag(D)`."""
    return design @ factor_covariance @ design.T + np.diag(specific)


def pca_cov(z: np.ndarray, n_factors: int | None = None) -> tuple[np.ndarray, int]:
    """PCA-v1 on the window: keep the factors above the MP edge."""
    frame = pd.DataFrame(z, columns=[f"N{i}" for i in range(z.shape[1])])
    fit = st.fit(frame)
    keep = st.count_mp(fit) if n_factors is None else n_factors
    return fit.covariance(max(keep, 1)), keep


def min_variance_weights(matrix: np.ndarray) -> np.ndarray:
    """`w = Sigma^-1 1 / (1' Sigma^-1 1)`, the analytic minimum-variance book."""
    n_names = matrix.shape[0]
    ones = np.ones(n_names)
    solved = np.linalg.solve(matrix, ones)
    return solved / float(ones @ solved)


def portfolio_vol(weights: np.ndarray, matrix: np.ndarray) -> float:
    return float(np.sqrt(weights @ matrix @ weights))


def realized_vol(
    weights: np.ndarray, forward: np.ndarray, annualize: bool = True
) -> float:
    """Volatility of the held weights over the forward window."""
    daily = float(np.sqrt(weights @ np.cov(forward, rowvar=False, ddof=1) @ weights))
    return daily * np.sqrt(252.0) if annualize else daily


def estimator_from_window(
    window: np.ndarray,
    name: str,
    design: np.ndarray | None = None,
    factor_covariance: np.ndarray | None = None,
    specific: np.ndarray | None = None,
) -> EstimatorResult:
    """Build one named estimator on a window of raw returns.

    The window enters in return units, because a minimum-variance portfolio
    needs volatilities, not correlations. Every estimator that is defined on a
    correlation matrix is computed on the standardized window and then rescaled
    by the sample standard deviations, which is what keeps the comparison fair:
    all eight matrices are covariances of the same returns by the time they
    reach the optimizer.

    The factor estimators (`ts_v1`, `xs_v1`) build covariances directly and are
    never rescaled.
    """
    values = _as_matrix(window)
    mean = values.mean(axis=0)
    std = values.std(axis=0, ddof=1)
    if np.any(std <= 0):
        raise ValueError("a zero-variance column cannot be standardized")
    z = (values - mean) / std
    extra: dict[str, float] = {}
    rescaled = True
    if name == "sample":
        matrix = sample_cov(z)
        k = None
    elif name == "ewma":
        matrix = ewma_cov(z)
        k = None
    elif name == "ledoit_wolf":
        matrix, parts = ledoit_wolf(z)
        extra = {"delta": parts["delta"], "mean_rho": parts["mean_rho"]}
        k = None
    elif name == "constant_correlation":
        matrix = constant_correlation(z)
        k = None
    elif name == "clip":
        matrix, above = clip_eigenvalues(z)
        extra = {"n_above_edge": float(above)}
        k = above
    elif name == "ts_v1":
        matrix = market_model_cov(z)
        k = None
    elif name == "pca_v1":
        matrix, keep = pca_cov(z)
        extra = {"n_factors": float(keep)}
        k = keep
    elif name == "pca_v1c":
        # the covariance variant, which is the object every other estimator in
        # the lab works on: no standardization, so the factors keep their scale
        from efb import pca_eval

        frame = pd.DataFrame(values, columns=[f"N{i}" for i in range(values.shape[1])])
        cov_fit = pca_eval.fit_covariance(frame)
        keep = int(np.sum(cov_fit.eigenvalues > cov_fit.mp_edge))
        matrix = cov_fit.covariance(max(keep, 1))
        extra = {"n_factors": float(keep)}
        k = keep
        rescaled = False
    elif name == "xs_v1":
        if design is None or factor_covariance is None or specific is None:
            raise ValueError(
                "xs_v1 needs the design, the factor covariance, the specific variance"
            )
        matrix = factor_cov(design, factor_covariance, specific)
        k = factor_covariance.shape[0]
        rescaled = False
    else:
        raise ValueError(f"unknown estimator {name}")
    if rescaled:
        matrix = np.outer(std, std) * matrix
    matrix = (matrix + matrix.T) / 2.0
    return EstimatorResult(
        name=name,
        matrix=matrix,
        parameter_count=parameter_count(name, values.shape[1], k),
        condition_number=condition_number(matrix),
        extra=extra,
    )


ESTIMATORS = (
    "sample",
    "ewma",
    "ledoit_wolf",
    "constant_correlation",
    "clip",
    "ts_v1",
    "pca_v1",
    "pca_v1c",
    "xs_v1",
)


def horse_race(
    returns_frame: pd.DataFrame,
    rebalances: list[pd.Timestamp],
    xs_supplier: object | None = None,
    estimators: tuple[str, ...] = ESTIMATORS,
    window: int = WINDOW,
    horizon: int = MIN_VARIANCE_DAYS,
    min_names: int = 50,
    universe: set[str] | None = None,
) -> pd.DataFrame:
    """The out-of-sample minimum-variance horse race.

    For each rebalance date: standardize the previous `window` sessions, build
    every estimator's covariance on the names that are complete in both the
    training window and the forward horizon, take the analytic minimum-variance
    weights, and measure the realized volatility of holding them for `horizon`
    sessions with no re-estimation. Nothing is refitted inside the holding
    period, which is what makes the realized number a test rather than a
    restatement of the estimate.

    `universe` restricts every estimator to the same names, which is what makes
    the row-to-row comparison honest: XS-v1 can only price the sector-mapped
    names, so the whole race is run on those.

    `xs_supplier` is a callable `(date, names) -> dict` returning the design,
    the factor covariance and the specific variance for the XS-v1 estimator. It
    is the only estimator that cannot be built from the window alone.
    """
    wide = st.clean_wide(returns_frame)
    if universe is not None:
        wide = wide[[column for column in wide.columns if column in universe]]
    rows: list[dict[str, object]] = []
    for date in rebalances:
        train = wide.loc[:date].iloc[-window:]
        forward = wide.loc[date:].iloc[1 : horizon + 1]
        if len(train) < window or len(forward) < horizon:
            continue
        names = [
            column
            for column in wide.columns
            if train[column].notna().all() and forward[column].notna().all()
        ]
        if len(names) < min_names:
            continue
        training = train[names].to_numpy(dtype=float)
        realized = forward[names].to_numpy(dtype=float)
        supplied: dict[str, object] = {}
        if callable(xs_supplier):
            supplied = xs_supplier(date, names) or {}
        for name in estimators:
            if name == "xs_v1" and not supplied:
                continue
            try:
                result = estimator_from_window(training, name, **supplied)  # type: ignore[arg-type]
            except np.linalg.LinAlgError:
                # a singular window is a real numerical outcome and the row is
                # dropped; a configuration error must not be swallowed, which
                # is how a requested estimator once produced zero rows in
                # silence
                continue
            weights = min_variance_weights(result.matrix)
            realized_volatility = realized_vol(weights, realized)
            predicted = portfolio_vol(weights, result.matrix) * np.sqrt(252.0)
            rows.append(
                {
                    "date": date,
                    "estimator": name,
                    "n_names": len(names),
                    "realized_vol": realized_volatility,
                    "predicted_vol": predicted,
                    "bias": (
                        realized_volatility / predicted if predicted > 0 else np.nan
                    ),
                    "condition_number": result.condition_number,
                    "parameter_count": result.parameter_count,
                    "gross_exposure": float(np.abs(weights).sum()),
                    **result.extra,
                }
            )
    return pd.DataFrame(rows)


def summarize(race: pd.DataFrame, baseline: str = "sample") -> pd.DataFrame:
    """The comparison table: mean and median realized volatility, per estimator."""
    grouped = race.groupby("estimator")
    table = pd.DataFrame(
        {
            "windows": grouped["realized_vol"].size(),
            "mean_realized_vol": grouped["realized_vol"].mean(),
            "median_realized_vol": grouped["realized_vol"].median(),
            "mean_predicted_vol": grouped["predicted_vol"].mean(),
            "mean_bias": grouped["bias"].mean(),
            "median_condition_number": grouped["condition_number"].median(),
            "parameter_count": grouped["parameter_count"].median(),
            "mean_gross_exposure": grouped["gross_exposure"].mean(),
            "mean_n_names": grouped["n_names"].mean(),
        }
    )
    if baseline in table.index:
        table["ratio_to_sample"] = (
            table["mean_realized_vol"] / table.loc[baseline, "mean_realized_vol"]
        )
        table["beat_sample_by"] = 1.0 - table["ratio_to_sample"]
    return table.sort_values("mean_realized_vol")
