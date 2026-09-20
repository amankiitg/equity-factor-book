"""F4.1 and F4.4: the two PCA comparisons, and the covariance variant PCA-v1c.

F4.1 compares PC1 with the market factor, and a correlation PCA cannot satisfy
it because standardizing each name to unit variance makes PC1 the equal-weight
common factor instead of the cap-weighted market. The resolution is not to
change the correlation PCA: PCA-v1 stays as it is, F4.1 is recorded as a fail
with its mechanism, and a covariance PCA on raw excess returns is registered
separately as PCA-v1c, because every other estimator in the lab works on a
covariance and the correlation PCA is the odd one out in the horse race.

F4.4 compares held-out cross-sectional variance explained. The first version of
the test handicapped PCA twice over, by leaving its loadings in standardized
units and by comparing a frozen model with XS-v1's daily refit. This module
rebuilds it as five rows on one protocol: sqrt(market cap) weights everywhere,
exposures dated t-1 everywhere, and only the fitting window and the exposure
set changing between rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from efb.models import fundamental as fx
from efb.models import statistical as st

WINDOW = st.PCA_WINDOW
HOLDOUT_START = pd.Timestamp("2024-08-30")


@dataclass
class CovarianceFit:
    """PCA on the covariance matrix of demeaned raw returns."""

    tickers: list[str]
    n_names: int
    n_days: int
    eigenvalues: np.ndarray
    eigenvectors: np.ndarray
    explained_share: np.ndarray
    mean_variance: float

    @property
    def mp_edge(self) -> float:
        """The covariance-case edge: sigma^2 (1 + sqrt(N/T))^2."""
        ratio = self.n_names / self.n_days
        return self.mean_variance * (1.0 + np.sqrt(ratio)) ** 2

    def loadings(self, n_factors: int) -> np.ndarray:
        return self.eigenvectors[:, :n_factors]

    def factor_returns(self, demeaned: np.ndarray, n_factors: int) -> np.ndarray:
        return demeaned @ self.eigenvectors[:, :n_factors]

    def covariance(self, n_factors: int) -> np.ndarray:
        load = self.loadings(n_factors)
        kept = load @ np.diag(self.eigenvalues[:n_factors]) @ load.T
        total = self.eigenvectors @ np.diag(self.eigenvalues) @ self.eigenvectors.T
        residual = np.clip(np.diag(total) - np.diag(kept), 1e-12, None)
        return kept + np.diag(residual)


def fit_covariance(block: pd.DataFrame) -> CovarianceFit:
    """Eigendecompose the covariance of demeaned raw returns."""
    values = block.to_numpy(dtype=float)
    demeaned = values - values.mean(axis=0)
    n_days, n_names = demeaned.shape
    matrix = demeaned.T @ demeaned / n_days
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = np.clip(eigenvalues[order], 0.0, None)
    eigenvectors = eigenvectors[:, order]
    total = float(eigenvalues.sum())
    return CovarianceFit(
        tickers=list(block.columns),
        n_names=n_names,
        n_days=n_days,
        eigenvalues=eigenvalues,
        eigenvectors=eigenvectors,
        explained_share=eigenvalues / total,
        mean_variance=float(np.mean(np.diag(matrix))),
    )


def spectrum_frame(fit: CovarianceFit, label: str) -> pd.DataFrame:
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
            "n_over_t": fit.n_names / fit.n_days,
            "above_edge": fit.eigenvalues > fit.mp_edge,
        }
    )


def _weighted_r_squared(
    target: np.ndarray, design: np.ndarray, weights: np.ndarray
) -> float:
    """Weighted R squared of one cross-sectional fit.

    A rank-deficient or numerically hostile design on a single day returns NaN
    rather than raising: one bad cross-section out of 503 must not take the
    whole comparison down, and the rows report their own day counts.
    """
    if not np.isfinite(target).all() or not np.isfinite(design).all():
        return np.nan
    keep = np.abs(design).sum(axis=0) > 1e-12
    design = design[:, keep]
    if design.shape[1] < 2:
        return np.nan
    weighted = design * np.sqrt(weights)[:, None]
    try:
        solution, *_ = np.linalg.lstsq(weighted, target * np.sqrt(weights), rcond=None)
    except np.linalg.LinAlgError:
        return np.nan
    fitted = design @ solution
    residual = float(np.sum(weights * (target - fitted) ** 2))
    total = float(np.sum(weights * (target - np.average(target, weights=weights)) ** 2))
    return 1.0 - residual / total if total > 0 else np.nan


def _market_cap_weights(path: str, date: pd.Timestamp, names: list[str]) -> pd.Series:
    frame = pd.read_parquet(path)
    block = frame.loc[frame["date"] == date]
    caps = block.set_index("ticker")["market_cap"].reindex(names)
    caps = caps.fillna(caps.median())
    caps = caps.clip(lower=caps[caps > 0].min())
    return np.sqrt(caps)


def held_out_comparison(
    data_root: str = "data",
    train_end: pd.Timestamp = HOLDOUT_START,
    window: int = WINDOW,
) -> pd.DataFrame:
    """F4.4 rebuilt: five rows, one protocol, sqrt(mcap) weights everywhere.

    (i) XS-v1 as stored, daily descriptors, 17 columns, read from its R squared
    artifact. (ii) XS-v1 with descriptors frozen at the training end, its
    handicap made explicit. (iii) PCA frozen at the training end, scaled by
    each name's training sigma, at the MP count and at 17 columns. (iv) PCA
    refit on a rolling window at the same cadence as XS-v1, which is the
    like-for-like pair the criterion is scored on. (v) XS-v1 augmented with the
    top three and top five residual principal components.
    """
    from pathlib import Path

    root = Path(data_root)
    returns = pd.read_parquet(root / "processed" / "returns.parquet")
    sectors = pd.read_parquet(root / "processed" / "sectors.parquet")
    descriptors = pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_returns.parquet")
    xs_r2 = pd.read_parquet(root / "models" / "XS-v1" / "xs_r2.parquet")
    mapped = list(sectors["ticker"])
    names_all = list(fx.FACTOR_NAMES)
    styles = [name for name in names_all if not name.startswith("sector")]
    sector_of = sectors.set_index("ticker")["gics_sector"]
    dummies = {
        name: {
            s for s, code in fx.SECTOR_CODES.items() if code == int(name.split("_")[1])
        }
        for name in names_all
        if name.startswith("sector")
    }

    wide = st.clean_wide(returns)
    wide = wide[[column for column in wide.columns if column in set(mapped)]]
    train = st.complete_block(wide, as_of=train_end, window=window)
    train_fit = st.fit(train)
    k_mp = max(st.count_mp(train_fit), 1)
    sigma_train = train.std(ddof=1)
    correlation_exposures = pd.DataFrame(
        train_fit.loadings(k_mp), index=train_fit.tickers
    )
    correlation_exposures = correlation_exposures.multiply(sigma_train, axis=0)
    wide_exposures = pd.DataFrame(
        train_fit.loadings(17), index=train_fit.tickers
    ).multiply(sigma_train, axis=0)
    residual_block = st.complete_block(
        specific.pivot(index="date", columns="ticker", values="specific_return"),
        as_of=train_end,
        window=window,
    )
    residual_fit = st.fit(residual_block)
    residual_exposures = {}
    for k_res in (3, 5):
        frame = pd.DataFrame(residual_fit.loadings(k_res), index=residual_fit.tickers)
        residual_exposures[k_res] = frame

    frozen_date = descriptors["date"].drop_duplicates().sort_values()
    frozen_date = frozen_date[frozen_date <= train_end].iloc[-1]
    frozen = descriptors.loc[descriptors["date"] == frozen_date]
    frozen_wide = frozen.pivot(
        index="ticker", columns="descriptor", values="value_z_orth"
    )

    def frozen_design(names: list[str]) -> np.ndarray | None:
        frame = frozen_wide.reindex(index=names, columns=styles)
        if frame.isna().to_numpy().any():
            return None
        blocks = [frame.to_numpy(dtype=float)]
        for wanted in dummies.values():
            blocks.append(
                np.array(
                    [[1.0 if sector_of.get(name) in wanted else 0.0] for name in names]
                )
            )
        return np.column_stack(blocks)

    held_days = [date for date in wide.loc[train_end:].index if date > train_end]
    rows: dict[str, list[float]] = {
        "(i) XS-v1 daily refit, as stored": [],
        "(ii) XS-v1 descriptors frozen": [],
        "(iii) PCA frozen k=MP": [],
        "(iii) PCA frozen k=17": [],
        "(iv) PCA rolling refit": [],
        "(v) XS-v1 plus top 3 residual PCs": [],
        "(v) XS-v1 plus top 5 residual PCs": [],
    }
    for date in held_days:
        row = wide.loc[date].dropna()
        names = [name for name in row.index if name in correlation_exposures.index]
        if len(names) < 50:
            continue
        target = row[names].to_numpy(dtype=float)
        weights = _market_cap_weights(
            str(root / "processed" / "market_cap.parquet"), date, names
        )
        weights = weights.to_numpy(dtype=float)
        stored = xs_r2.loc[xs_r2["date"] == date, "r_squared"]
        if len(stored):
            rows["(i) XS-v1 daily refit, as stored"].append(float(stored.iloc[0]))
        design_frozen = frozen_design(names)
        if design_frozen is not None:
            rows["(ii) XS-v1 descriptors frozen"].append(
                _weighted_r_squared(target, design_frozen, weights)
            )
            for k_res, frame in residual_exposures.items():
                # a name outside the residual PCA window carries no residual
                # exposure, which is zero rather than a missing value
                extra = frame.reindex(names).fillna(0.0).to_numpy(dtype=float)
                rows[f"(v) XS-v1 plus top {k_res} residual PCs"].append(
                    _weighted_r_squared(
                        target, np.column_stack([design_frozen, extra]), weights
                    )
                )
        for label, frame in (
            ("(iii) PCA frozen k=MP", correlation_exposures),
            ("(iii) PCA frozen k=17", wide_exposures),
        ):
            design = frame.reindex(names).to_numpy(dtype=float)
            rows[label].append(_weighted_r_squared(target, design, weights))
        # (iv) rolling refit: the window ends the session before the target day
        position = wide.index.get_loc(date)
        rolling = st.complete_block(
            wide.iloc[:position], as_of=None, window=window
        ).reindex(columns=names)
        rolling = rolling.loc[:, rolling.notna().all(axis=0)]
        if rolling.shape[1] >= 50:
            rolling_fit = st.fit(rolling)
            k_roll = max(st.count_mp(rolling_fit), 1)
            frame = pd.DataFrame(
                rolling_fit.loadings(k_roll), index=rolling_fit.tickers
            )
            frame = frame.multiply(rolling.std(ddof=1), axis=0)
            keep = [name for name in names if name in frame.index]
            rows["(iv) PCA rolling refit"].append(
                _weighted_r_squared(
                    row[keep].to_numpy(dtype=float),
                    frame.reindex(keep).to_numpy(dtype=float),
                    weights[[names.index(name) for name in keep]],
                )
            )
    summary = pd.DataFrame(
        {
            "row": list(rows),
            "mean_r_squared": [
                float(np.mean(values)) if values else np.nan for values in rows.values()
            ],
            "days": [len(values) for values in rows.values()],
        }
    )
    return summary


def run(data_root: str = "data") -> dict[str, object]:
    """F4.1 both ways, PCA-v1c registered, and F4.4 rebuilt."""
    from efb import registry

    root = Path(data_root) if (Path(data_root)).exists() else Path("data")
    returns = pd.read_parquet(root / "processed" / "returns.parquet")
    sectors = pd.read_parquet(root / "processed" / "sectors.parquet")
    factor_returns = pd.read_parquet(
        root / "models" / "XS-v1" / "factor_returns.parquet"
    )
    mapped = list(sectors["ticker"])
    market = (
        factor_returns.loc[factor_returns["factor"] == "market"]
        .set_index("date")["f"]
        .sort_index()
    )
    wide = st.clean_wide(returns)
    wide = wide[[column for column in wide.columns if column in set(mapped)]]
    block = st.complete_block(wide, as_of=pd.Timestamp("2026-09-03"), window=WINDOW)

    correlation = st.fit(block)
    covariance = fit_covariance(block)
    z, _, _ = st.standardize(block)
    pc1_correlation = pd.Series(z @ correlation.eigenvectors[:, 0], index=block.index)
    demeaned = block.to_numpy(dtype=float) - block.to_numpy(dtype=float).mean(axis=0)
    pc1_covariance = pd.Series(
        demeaned @ covariance.eigenvectors[:, 0], index=block.index
    )
    equal_weight = block.mean(axis=1)
    market_aligned = market.reindex(block.index)

    f4_1_correlation = float(pc1_correlation.corr(market_aligned))
    f4_1_covariance = float(pc1_covariance.corr(market_aligned))
    print("### F4.1 both PCAs, same 504 days")
    print(
        f"PCA-v1  correlation PCA: PC1 vs cap-weighted market {f4_1_correlation:.4f}, "
        f"vs equal-weight mean {pc1_correlation.corr(equal_weight):.4f}"
    )
    print(
        f"PCA-v1c covariance  PCA: PC1 vs cap-weighted market {f4_1_covariance:.4f}, "
        f"vs equal-weight mean {pc1_covariance.corr(equal_weight):.4f}"
    )
    print(f"market factor vs equal-weight mean {market_aligned.corr(equal_weight):.4f}")
    print(
        f"PCA-v1c counts: N {covariance.n_names}, T {covariance.n_days}, "
        f"N/T {covariance.n_names / covariance.n_days:.4f}, "
        f"MP edge (covariance) {covariance.mp_edge:.3e}, "
        f"factors above edge {int(np.sum(covariance.eigenvalues > covariance.mp_edge))}"
    )

    long_block = st.complete_block(
        wide, as_of=pd.Timestamp("2026-09-03"), window=len(wide)
    )
    z_long, _, _ = st.standardize(long_block)
    fit_long = st.fit(long_block)
    pc1_long = pd.Series(z_long @ fit_long.eigenvectors[:, 0], index=long_block.index)
    f4_1_full = float(pc1_long.corr(market.reindex(pc1_long.index)))
    print(
        f"PCA-v1 full sample: PC1 vs market {f4_1_full:.4f} over {len(pc1_long)} days"
    )

    cov_spectrum = spectrum_frame(covariance, "covariance")
    target_dir = root / "models" / "PCA-v1c"
    target_dir.mkdir(parents=True, exist_ok=True)
    cov_spectrum.to_parquet(target_dir / "eigenvalues.parquet", index=False)
    pd.DataFrame(
        {
            "factor": [f"pca_c{i + 1:02d}" for i in range(covariance.n_names)],
            "eigenvalue": covariance.eigenvalues,
        }
    ).to_parquet(target_dir / "spectrum.parquet", index=False)
    loadings = pd.DataFrame(covariance.eigenvectors, index=covariance.tickers)
    loadings.columns = [f"pca_c{i + 1:02d}" for i in range(covariance.n_names)]
    loadings.reset_index(names="ticker").to_parquet(
        target_dir / "loadings.parquet", index=False
    )
    factor_frame = pd.DataFrame(
        covariance.factor_returns(demeaned, covariance.n_names),
        index=block.index,
        columns=[f"pca_c{i + 1:02d}" for i in range(covariance.n_names)],
    )
    factor_frame.reset_index(names="date").melt(
        id_vars="date", var_name="factor", value_name="f"
    ).to_parquet(target_dir / "factor_returns.parquet", index=False)
    entry = registry.model_entry(
        version="PCA-v1c",
        family="statistical",
        parameters={
            "family": "statistical",
            "estimator": "principal component analysis on the covariance matrix",
            "window": WINDOW,
            "n_names": covariance.n_names,
            "n_days": covariance.n_days,
            "n_over_t": covariance.n_names / covariance.n_days,
            "mp_edge_covariance": covariance.mp_edge,
            "mean_variance": covariance.mean_variance,
            "n_factors": int(np.sum(covariance.eigenvalues > covariance.mp_edge)),
            "pc1_vs_market": f4_1_covariance,
            "pc1_vs_equal_weight": float(pc1_covariance.corr(equal_weight)),
        },
        universe_path=root / "processed" / "universe_membership.parquet",
        data_paths=[
            root / "processed" / "returns.parquet",
            root / "processed" / "sectors.parquet",
        ],
        walkthrough="notebooks/E4_walkthrough.html",
        deliverable="docs/research/E4_covariance_memo.md",
        results="sprints/E4/RESULTS.json",
        champion=False,
        eligible_for_champion=True,
    )
    registry.write_registry(root / "models" / "registry.json", entry)
    print(f"PCA-v1c registered: {target_dir}")

    print()
    print("### F4.4 rebuilt, five rows, sqrt(mcap) weights, exposures dated t-1")
    summary = held_out_comparison(str(root))
    print(summary.round(6).to_string(index=False))
    return {
        "f4_1_correlation_pca": f4_1_correlation,
        "f4_1_covariance_pca": f4_1_covariance,
        "f4_1_full_sample": f4_1_full,
        "pc1_vs_equal_weight": float(pc1_correlation.corr(equal_weight)),
        "covariance_factors_above_edge": int(
            np.sum(covariance.eigenvalues > covariance.mp_edge)
        ),
        "f4_4": summary,
    }
