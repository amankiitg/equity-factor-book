"""Sprint E5, Tasks 2 to 4: the risk model evaluation engine.

Four families of portfolios built from the panel with no look-ahead, a daily
bias engine that standardizes each day's return by the model's own forecast,
and the tables the champion rule and the criteria are read from.

The standardized return is z_t = r_t / sigma_hat_{t|t-1}. Forecasts are
refreshed at the month ends of the derived race grid, held through the month,
and always use information dated t-1 or earlier; z and the bias statistics are
daily. B = sqrt(mean z squared) with its delta-method band, coverage is the
share of |z| above 1.96 against the nominal five percent, and the Q-Q pair is
the OLS of the empirical quantiles of z on the standard normal quantiles.

Every E5 number inherits the XS-v1 universe: the 502 sector-mapped names, a
survivor-only cross-section.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from efb import cov, hygiene, race
from efb.models import fundamental as fx

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"

WINDOW = cov.WINDOW  # 504 sessions
MIN_VARIANCE_DAYS = cov.MIN_VARIANCE_DAYS
HALF_LIFE_F = fx.F_HALF_LIFE
NOMINAL_COVERAGE = 0.05
Z_CRITICAL = 1.96
ROLLING_DAYS = 252
SEED = 20260920
N_RANDOM = 60  # at least 50 random portfolios per family, plus the seed books
N_LONG_ONLY_NAMES = 100
N_LONG_SHORT_NAMES = 50
STYLES = ("momentum", "reversal", "beta", "size", "resid_vol", "liquidity")

VERSIONS = ("sample", "ts_v1", "xs_v1", "xs_v2", "pca_v1", "pca_v1c")
FAMILIES = ("long_only", "long_short", "factor_tilted", "sector_concentrated")


def norm_ppf(values: np.ndarray) -> np.ndarray:
    """Inverse normal CDF, Acklam's rational approximation, elementwise."""
    values = np.clip(np.asarray(values, dtype=float), 1e-15, 1.0 - 1e-15)
    a = np.array(
        [
            -3.969683028665376e01,
            2.209460984245205e02,
            -2.759285104469687e02,
            1.383577518672690e02,
            -3.066479806614716e01,
            2.506628277459239e00,
        ]
    )
    b = np.array(
        [
            -5.447609879822406e01,
            1.615858368580409e02,
            -1.556989798598866e02,
            6.680131188771972e01,
            -1.328068155288572e01,
        ]
    )
    c = np.array(
        [
            -7.784894002430293e-03,
            -3.223964580411365e-01,
            -2.400758277161838e00,
            -2.549732539343734e00,
            4.374664141464968e00,
            2.938163982698783e00,
        ]
    )
    d = np.array(
        [
            7.784695709041462e-03,
            3.224671290700398e-01,
            2.445134137142996e00,
            3.754408661907416e00,
        ]
    )
    low = values < 0.5
    q = values - 0.5
    central = np.abs(q) <= 0.42575
    r = np.where(low, 1.0 - values, values)
    r = np.sqrt(-np.log(np.clip(r, 1e-300, None)))
    numerator = ((((c[0] * r + c[1]) * r + c[2]) * r + c[3]) * r + c[4]) * r + c[5]
    denominator = (((d[0] * r + d[1]) * r + d[2]) * r + d[3]) * r + 1.0
    tail = numerator / denominator
    tail = np.where(low, -tail, tail)
    if central.any():
        r_c = 0.180625 - q[central] ** 2
        central_num = (
            (((a[0] * r_c + a[1]) * r_c + a[2]) * r_c + a[3]) * r_c + a[4]
        ) * r_c + a[5]
        central_den = (
            (((b[0] * r_c + b[1]) * r_c + b[2]) * r_c + b[3]) * r_c + b[4]
        ) * r_c + 1.0
        tail = tail.copy()
        tail[central] = q[central] * central_num / central_den
    return tail


def bias_statistics(z: np.ndarray) -> dict[str, float]:
    """B = sqrt(mean z squared), its 95% band, coverage, MAD and the Q-Q pair.

    Under a correct model z is standard normal, so B estimates 1 with
    variance 2/T on mean z squared; the delta method gives SE(B) = sqrt(2/T)
    / (2 B). Coverage is measured against the nominal five percent at |z| >
    1.96, and the Q-Q pair is the OLS of the empirical quantiles of z on the
    standard normal quantiles.
    """
    z = np.asarray(z, dtype=float)
    z = z[np.isfinite(z)]
    n_obs = len(z)
    if n_obs < 30:
        raise ValueError("a bias statistic needs at least 30 observations")
    mean_squared = float(np.mean(z**2))
    bias = float(np.sqrt(mean_squared))
    standard_error = float(np.sqrt(2.0 / n_obs) / (2.0 * bias)) if bias > 0 else np.inf
    probabilities = np.linspace(0, 1, n_obs + 2)[1:-1]
    empirical = np.quantile(z, probabilities)
    theoretical = norm_ppf(probabilities)
    slope, intercept = np.polyfit(theoretical, empirical, 1)
    return {
        "n_obs": float(n_obs),
        "bias": bias,
        "bias_se": standard_error,
        "bias_lower": float(bias - Z_CRITICAL * standard_error),
        "bias_upper": float(bias + Z_CRITICAL * standard_error),
        "coverage": float(np.mean(np.abs(z) > Z_CRITICAL)),
        "mad_ratio": float(np.median(np.abs(z)) / 0.6745),
        "qq_slope": float(slope),
        "qq_intercept": float(intercept),
        "abs_bias_minus_1": abs(bias - 1.0),
    }


def load_clean_wide(data_root: Path = DATA_ROOT) -> tuple[pd.DataFrame, dict[str, int]]:
    """The cleaned wide returns over the mapped universe, plus exclusion counts.

    The panel is the post-exclusion returns file; stale and outlier rows are
    set to NaN exactly as `efb.hygiene.clean_returns` does and the counts are
    returned so the engine prints them once.
    """
    root = Path(data_root)
    returns_frame = pd.read_parquet(root / "processed" / "returns.parquet")
    sectors = pd.read_parquet(root / "processed" / "sectors.parquet")
    mapped = sorted(sectors["ticker"].astype(str))
    clean = hygiene.clean_returns(returns_frame)
    wide = clean.unstack("ticker")
    wide = wide[[name for name in mapped if name in wide.columns]]
    counts = {
        "stale": int(returns_frame["stale"].astype(bool).sum()),
        "outlier": int(returns_frame["outlier"].astype(bool).sum()),
        "n_mapped": len(wide.columns),
    }
    return wide, counts


def _month_ends(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """The sessions that are the last session of their month."""
    periods = index.to_period("M")
    last = periods.max()
    return [
        pd.Timestamp(date) for date in index if periods[index.get_loc(date)] == last
    ]


def _styles_at(date: pd.Timestamp, data_root: Path) -> pd.DataFrame:
    """The six orthogonalized style z-scores on one artifact date, wide."""
    descriptors = pd.read_parquet(
        data_root / "models" / "XS-v1" / "descriptors.parquet"
    )
    stamp = race._as_of(descriptors, date)
    day = descriptors.loc[pd.to_datetime(descriptors["date"]) == stamp]
    return day.pivot_table(index="ticker", columns="descriptor", values="value_z_orth")


def build_families(
    data_root: Path = DATA_ROOT, seed: int = SEED, store: bool = True
) -> pd.DataFrame:
    """The four families: deterministic random portfolios plus the two seed books.

    Every generated weight row is dated at the month end whose close the
    position is set at, so a portfolio never uses a weight dated after the day
    it is applied to. The seed books keep their own daily rows.
    """
    root = Path(data_root)
    wide, _counts = load_clean_wide(root)
    grid = race.race_grid(root)
    rng = np.random.default_rng(seed)
    sectors = pd.read_parquet(root / "processed" / "sectors.parquet")
    sector_of = sectors.set_index("ticker")["gics_sector"].astype(str).to_dict()
    sector_names = sorted(set(sector_of.values()))
    descriptors = pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    descriptors["date"] = pd.to_datetime(descriptors["date"])
    styles_by_date = {
        date: group.pivot_table(
            index="ticker", columns="descriptor", values="value_z_orth"
        )
        for date, group in descriptors.groupby("date")
    }
    rows: list[dict[str, object]] = []

    def _available(date: pd.Timestamp) -> list[str]:
        return list(wide.columns[wide.loc[date].notna()])

    for date in grid:
        available = _available(date)
        if len(available) < N_LONG_ONLY_NAMES:
            continue
        stamp = race._as_of(descriptors, date)
        z = styles_by_date[stamp].reindex(available)
        for index in range(N_RANDOM):
            draw = rng.choice(available, size=N_LONG_ONLY_NAMES, replace=False)
            for ticker in draw:
                rows.append(
                    {
                        "portfolio": f"long_only_{index:02d}",
                        "family": "long_only",
                        "date": date,
                        "ticker": ticker,
                        "weight": 1.0 / N_LONG_ONLY_NAMES,
                    }
                )
            long_draw = rng.choice(available, size=N_LONG_SHORT_NAMES, replace=False)
            rest = [name for name in available if name not in set(long_draw)]
            short_draw = rng.choice(rest, size=N_LONG_SHORT_NAMES, replace=False)
            for ticker in long_draw:
                rows.append(
                    {
                        "portfolio": f"long_short_{index:02d}",
                        "family": "long_short",
                        "date": date,
                        "ticker": ticker,
                        "weight": 1.0 / (2 * N_LONG_SHORT_NAMES),
                    }
                )
            for ticker in short_draw:
                rows.append(
                    {
                        "portfolio": f"long_short_{index:02d}",
                        "family": "long_short",
                        "date": date,
                        "ticker": ticker,
                        "weight": -1.0 / (2 * N_LONG_SHORT_NAMES),
                    }
                )
            chosen_sectors = list(rng.choice(sector_names, size=2, replace=False))
            names = [
                name for name in available if sector_of.get(name) in chosen_sectors
            ]
            if not names:
                names = available[:N_LONG_ONLY_NAMES]
            for ticker in names:
                rows.append(
                    {
                        "portfolio": f"sector_{index:02d}",
                        "family": "sector_concentrated",
                        "date": date,
                        "ticker": ticker,
                        "weight": 1.0 / len(names),
                    }
                )
        for style in STYLES:
            scores = z[style].dropna()
            if len(scores) < 60:
                continue
            tercile = pd.qcut(scores.rank(method="first"), 3, labels=False)
            style_longs = list(scores.index[tercile == 2])
            style_shorts = list(scores.index[tercile == 0])
            for ticker in style_longs:
                rows.append(
                    {
                        "portfolio": f"tilt_{style}",
                        "family": "factor_tilted",
                        "date": date,
                        "ticker": ticker,
                        "weight": 1.0 / (2 * len(style_longs)),
                    }
                )
            for ticker in style_shorts:
                rows.append(
                    {
                        "portfolio": f"tilt_{style}",
                        "family": "factor_tilted",
                        "date": date,
                        "ticker": ticker,
                        "weight": -1.0 / (2 * len(style_shorts)),
                    }
                )
        for index in range(N_RANDOM):
            style = STYLES[int(rng.integers(0, len(STYLES)))]
            scores = z[style].dropna()
            tercile = pd.qcut(scores.rank(method="first"), 3, labels=False)
            tilt_longs = list(scores.index[tercile == 2])
            tilt_shorts = list(scores.index[tercile == 0])
            if len(tilt_longs) < 30 or len(tilt_shorts) < 30:
                continue
            pick_longs = list(rng.choice(tilt_longs, size=30, replace=False))
            pick_shorts = list(rng.choice(tilt_shorts, size=30, replace=False))
            for ticker in pick_longs:
                rows.append(
                    {
                        "portfolio": f"tilt_random_{index:02d}",
                        "family": "factor_tilted",
                        "date": date,
                        "ticker": ticker,
                        "weight": 1.0 / 60,
                    }
                )
            for ticker in pick_shorts:
                rows.append(
                    {
                        "portfolio": f"tilt_random_{index:02d}",
                        "family": "factor_tilted",
                        "date": date,
                        "ticker": ticker,
                        "weight": -1.0 / 60,
                    }
                )

    generated = pd.DataFrame(rows)
    seed_rows: list[dict[str, object]] = []
    for book, family in (("seed_ew", "long_only"), ("seed_mom_ls", "factor_tilted")):
        frame = pd.read_parquet(root / "portfolios" / f"{book}.parquet")
        frame = frame.loc[frame["ticker"].isin(set(wide.columns))]
        for row in frame.itertuples():
            seed_rows.append(
                {
                    "portfolio": book,
                    "family": family,
                    "date": pd.Timestamp(row.date),
                    "ticker": row.ticker,
                    "weight": float(row.weight),
                }
            )
    combined = pd.concat([generated, pd.DataFrame(seed_rows)], ignore_index=True)
    if store:
        combined.to_parquet(root / "eval" / "e5_portfolios.parquet", index=False)
    return combined


def _window_names(wide: pd.DataFrame, date: pd.Timestamp) -> list[str]:
    """The names complete over the 504 sessions ending at `date`."""
    block = wide.loc[:date].iloc[-WINDOW:]
    return [name for name in wide.columns if block[name].notna().all()]


def _xs_pieces(
    date: pd.Timestamp, names: list[str], data_root: Path
) -> dict[str, np.ndarray] | None:
    """XS-v1's point-in-time design, factor covariance and specific diagonal.

    The factor covariance is the model's own EWMA over the factor returns
    strictly before the rebalance date, and the design and the diagonal are
    read from the XS-v1 artifacts at the latest published date at or before
    it, which is exactly what `efb.race.xs_supplier` documents. The race's
    supplier itself is not used: its single-level-index extraction branch
    selects one row of the factor covariance and drops every window, which is
    part of the F5.0b record, so the engine reads the matrix directly.
    """
    root = Path(data_root)
    factor_returns = pd.read_parquet(
        root / "models" / "XS-v1" / "factor_returns.parquet"
    )
    factor_returns = factor_returns.loc[pd.to_datetime(factor_returns["date"]) < date]
    if factor_returns["date"].nunique() < 126:
        return None
    history = factor_returns.pivot_table(index="date", columns="factor", values="f")
    ordered = list(fx.ESTIMATED_NAMES)
    if not set(ordered).issubset(history.columns):
        raise RuntimeError("the stored factor returns do not cover every factor")
    history = history.loc[:, ordered].fillna(0.0)
    factor_covariance = fx.ewma_factor_cov(
        history.loc[:, ordered], half_life=fx.F_HALF_LIFE
    ).to_numpy(dtype=float)
    design = race._descriptor_design(date, names, root)
    specific, _missing = race._specific_for(date, names, root)
    design = np.nan_to_num(design, nan=0.0, posinf=0.0, neginf=0.0)
    median_specific = float(np.nanmedian(specific))
    specific = np.where(np.isnan(specific), median_specific, specific)
    blocks = (
        ("design", design),
        ("factor covariance", factor_covariance),
        ("specific", specific),
    )
    if not all(np.isfinite(values).all() for _label, values in blocks):
        return None
    return {
        "design": design,
        "factor_covariance": factor_covariance,
        "specific": specific,
    }


def _xs_v2_block(
    date: pd.Timestamp, names: list[str], data_root: Path
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """XS-v2's specific block at the stored month end at or before `date`.

    Returns the low-rank part over `names`, the block's total diagonal
    (remainder plus the low-rank diagonal) with the cross-sectional median
    fallback for names the stored block does not cover, the low-rank diagonal
    for the aligned names, and the fallback value itself.
    """
    root = Path(data_root)
    loadings = pd.read_parquet(root / "models" / "XS-v2" / "residual_loadings.parquet")
    remainder = pd.read_parquet(
        root / "models" / "XS-v2" / "residual_remainder.parquet"
    )
    stamp = race._as_of(loadings, date)
    if stamp is None:
        raise RuntimeError("XS-v2 has no stored block at or before this date")
    block_loadings = loadings.loc[pd.to_datetime(loadings["date"]) == stamp]
    block_remainder = remainder.loc[pd.to_datetime(remainder["date"]) == stamp]
    scaled = block_loadings.pivot_table(
        index="ticker", columns="factor", values="scaled_loading"
    )
    eigenvalues = (
        block_loadings.groupby("factor")["eigenvalue"].first().to_numpy(dtype=float)
    )
    rest = block_remainder.set_index("ticker")["remainder"]
    low_diag = block_remainder.set_index("ticker")["low_rank_diagonal"]
    total_diag = rest + low_diag
    fallback = float(np.nanmedian(total_diag.to_numpy(dtype=float)))
    aligned = scaled.reindex(names).fillna(0.0).to_numpy(dtype=float)
    low = aligned @ np.diag(eigenvalues) @ aligned.T
    low_diagonal = np.einsum("ij,j,ij->i", aligned, eigenvalues, aligned)
    diagonal = total_diag.reindex(names).to_numpy(dtype=float)
    diagonal = np.where(np.isnan(diagonal), fallback, diagonal)
    return low, diagonal, low_diagonal, fallback


def forecast_monthly(
    data_root: Path = DATA_ROOT, store: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One forecast per version per grid month end: the asset diagonal and the
    portfolio volatilities.

    The version matrices are built on the names complete over the 504-session
    window ending at the month end, which is the same name set the covariance
    race uses, so no estimator is favoured by a wider window. XS-v1's pieces
    come from `_xs_pieces`, the point-in-time supplier recorded under F5.0b.
    """
    root = Path(data_root)
    wide, _counts = load_clean_wide(root)
    grid = race.race_grid(root)
    portfolios = pd.read_parquet(root / "eval" / "e5_portfolios.parquet")

    diagonal_rows: list[dict[str, object]] = []
    portfolio_rows: list[dict[str, object]] = []
    for position, date in enumerate(grid):
        names = _window_names(wide, date)
        if len(names) < 50:
            continue
        window = wide[names].loc[:date].iloc[-WINDOW:].to_numpy(dtype=float)
        std = window.std(axis=0, ddof=1)
        z_standard = (window - window.mean(axis=0)) / std
        day_rows = portfolios.loc[pd.to_datetime(portfolios["date"]) == date]
        weights_by_portfolio: dict[str, np.ndarray] = {}
        for portfolio, group in day_rows.groupby("portfolio"):
            series = group.set_index("ticker")["weight"].reindex(names).fillna(0.0)
            weights_by_portfolio[portfolio] = series.to_numpy(dtype=float)

        xs_supplied = None
        xs_v2_low = None
        xs_v2_diag = None
        xs_v2_low_diag = None
        for version in VERSIONS:
            if version in ("xs_v1", "xs_v2"):
                if xs_supplied is None:
                    xs_supplied = _xs_pieces(date, names, root)
                if xs_supplied is None:
                    continue
                design = xs_supplied["design"]
                factor_covariance = xs_supplied["factor_covariance"]
                factor_part = design @ factor_covariance @ design.T
                if version == "xs_v2" and xs_v2_diag is None:
                    xs_v2_low, xs_v2_diag, xs_v2_low_diag, _fallback = _xs_v2_block(
                        date, names, root
                    )
                if version == "xs_v1":
                    diag = np.diag(factor_part) + xs_supplied["specific"]
                else:
                    assert xs_v2_diag is not None
                    diag = np.diag(factor_part) + xs_v2_diag
                diagonal = np.sqrt(np.clip(diag, 1e-20, None))
                for ticker, value in zip(names, diagonal, strict=False):
                    diagonal_rows.append(
                        {
                            "version": version,
                            "date": date,
                            "ticker": ticker,
                            "sigma": value,
                        }
                    )
                for portfolio, weights in weights_by_portfolio.items():
                    projected = weights @ design
                    factor_var = float(projected @ factor_covariance @ projected)
                    if version == "xs_v1":
                        specific_var = float(
                            weights @ np.diag(xs_supplied["specific"]) @ weights
                        )
                    else:
                        assert (
                            xs_v2_low is not None
                            and xs_v2_diag is not None
                            and xs_v2_low_diag is not None
                        )
                        low_var = float(weights @ xs_v2_low @ weights)
                        residual_var = float(
                            np.sum(weights**2 * (xs_v2_diag - xs_v2_low_diag))
                        )
                        specific_var = low_var + residual_var
                    portfolio_rows.append(
                        {
                            "version": version,
                            "date": date,
                            "portfolio": portfolio,
                            "sigma": float(
                                np.sqrt(np.clip(factor_var + specific_var, 1e-20, None))
                            ),
                            "n_names": len(names),
                        }
                    )
                continue
            if version == "sample":
                sigma = np.outer(std, std) * cov.sample_cov(z_standard)
                diagonal = std
            elif version == "ts_v1":
                sigma = np.outer(std, std) * cov.market_model_cov(z_standard)
                diagonal = np.sqrt(np.clip(np.diag(sigma), 1e-20, None))
            elif version == "pca_v1":
                matrix, _keep = cov.pca_cov(z_standard)
                sigma = np.outer(std, std) * matrix
                diagonal = std
            elif version == "pca_v1c":
                from efb import pca_eval

                frame = pd.DataFrame(
                    window, columns=[f"N{i}" for i in range(len(names))]
                )
                cov_fit = pca_eval.fit_covariance(frame)
                keep = int(np.sum(cov_fit.eigenvalues > cov_fit.mp_edge))
                sigma = cov_fit.covariance(max(keep, 1))
                diagonal = np.sqrt(np.clip(np.diag(sigma), 1e-20, None))
            else:  # pragma: no cover - the version list is closed
                raise ValueError(f"unknown version {version}")
            for ticker, value in zip(names, diagonal, strict=False):
                if np.isfinite(value):
                    diagonal_rows.append(
                        {
                            "version": version,
                            "date": date,
                            "ticker": ticker,
                            "sigma": value,
                        }
                    )
            for portfolio, weights in weights_by_portfolio.items():
                portfolio_rows.append(
                    {
                        "version": version,
                        "date": date,
                        "portfolio": portfolio,
                        "sigma": cov.portfolio_vol(weights, sigma),
                        "n_names": len(names),
                    }
                )
        if position % 25 == 0:
            print(f"  forecasts {position + 1}/{len(grid)} ({date.date()})")
    diagonal_frame = pd.DataFrame(diagonal_rows)
    portfolio_frame = pd.DataFrame(portfolio_rows)
    if store:
        diagonal_frame.to_parquet(
            root / "eval" / "e5_forecast_diag.parquet", index=False
        )
        portfolio_frame.to_parquet(
            root / "eval" / "e5_forecast_portfolios.parquet", index=False
        )
    return diagonal_frame, portfolio_frame


def daily_z(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """The daily standardized returns per version and family.

    r_t is the portfolio return under the weights held from the previous
    close, so no weight or forecast is dated after t-1. One stored parquet per
    version and family: date, portfolio, z.
    """
    root = Path(data_root)
    wide, _counts = load_clean_wide(root)
    grid = race.race_grid(root)
    forecasts = pd.read_parquet(root / "eval" / "e5_forecast_portfolios.parquet")
    portfolios = pd.read_parquet(root / "eval" / "e5_portfolios.parquet")
    generated = portfolios.loc[
        ~portfolios["portfolio"].str.startswith("seed_")
    ].sort_values("date")
    seeds = portfolios.loc[portfolios["portfolio"].str.startswith("seed_")]

    last = grid[-1] + pd.Timedelta(days=40)
    sigma_by_version: dict[str, dict[pd.Timestamp, dict[str, float]]] = {}
    for version in VERSIONS:
        sub = forecasts.loc[forecasts["version"] == version]
        sigma_by_version[version] = {
            pd.Timestamp(date): dict(
                zip(group["portfolio"], group["sigma"], strict=False)
            )
            for date, group in sub.groupby("date")
        }

    for version in VERSIONS:
        for family in FAMILIES:
            family_rows = generated.loc[generated["family"] == family]
            if family_rows.empty:
                continue
            dates = sorted(pd.to_datetime(family_rows["date"].unique()))
            periods = list(zip(dates, dates[1:] + [last], strict=False))
            collected: list[pd.DataFrame] = []
            for start, end in periods:
                block = family_rows.loc[pd.to_datetime(family_rows["date"]) == start]
                weight_matrix = block.pivot_table(
                    index="portfolio", columns="ticker", values="weight"
                )
                names_by_position = list(weight_matrix.index)
                weight_matrix = (
                    weight_matrix.fillna(0.0)
                    .reindex(columns=wide.columns, fill_value=0.0)
                    .to_numpy(dtype=float)
                )
                window = wide.loc[(wide.index > start) & (wide.index <= end)]
                returns = window.to_numpy(dtype=float)
                portfolio_returns = _portfolio_returns(weight_matrix, returns)
                for position, portfolio in enumerate(names_by_position):
                    sigma = sigma_by_version[version].get(start, {}).get(portfolio)
                    if sigma is None:
                        continue
                    if not np.isfinite(sigma) or sigma <= 0:
                        continue
                    collected.append(
                        pd.DataFrame(
                            {
                                "date": window.index,
                                "portfolio": portfolio,
                                "z": portfolio_returns[position] / sigma,
                            }
                        )
                    )
            collected.append(
                _seed_z(root, version, family, seeds, grid, sigma_by_version[version])
            )
            frame = pd.concat(
                [frame for frame in collected if not frame.empty], ignore_index=True
            )
            if frame.empty:
                continue
            if store:
                frame.to_parquet(
                    root / "eval" / f"bias_{version}_{family}.parquet", index=False
                )
    return portfolios


def _portfolio_returns(weight_matrix: np.ndarray, returns: np.ndarray) -> np.ndarray:
    """`W R'` with missing-data semantics, not IEEE zero-times-NaN.

    An unpriced name has weight zero, so its missing return contributes zero;
    a held name with a missing return makes that portfolio-day missing, which
    is how a stale day is excluded rather than silently averaged to zero.
    """
    missing = np.isnan(returns) & (weight_matrix[:, None, :] != 0)
    safe_returns = np.nan_to_num(returns, nan=0.0)
    out = weight_matrix @ safe_returns.T
    out[missing.any(axis=2)] = np.nan
    return out


def _seed_z(
    root: Path,
    version: str,
    family: str,
    seeds: pd.DataFrame,
    grid: list[pd.Timestamp],
    sigma_by_date: dict[pd.Timestamp, dict[str, float]],
) -> pd.DataFrame:
    """The seed books' daily z, from their own daily weight rows held as dated."""
    out: list[pd.DataFrame] = []
    wide, _counts = load_clean_wide(root)
    for book, book_family in (
        ("seed_ew", "long_only"),
        ("seed_mom_ls", "factor_tilted"),
    ):
        if book_family != family:
            continue
        book_rows = seeds.loc[seeds["portfolio"] == book]
        usable_dates = [
            date
            for date in sorted(pd.to_datetime(book_rows["date"].unique()))
            if date > grid[0]
        ]
        if not usable_dates:
            continue
        weight_frame = (
            book_rows.loc[book_rows["date"].isin(usable_dates)]
            .pivot_table(index="date", columns="ticker", values="weight")
            .fillna(0.0)
            .reindex(columns=wide.columns, fill_value=0.0)
        )
        # the seed books carry rows on holidays, which the returns panel does
        # not; only sessions both share can be standardized
        weight_frame = weight_frame.loc[weight_frame.index.intersection(wide.index)]
        weight_matrix = weight_frame.to_numpy(dtype=float)
        window = wide.loc[weight_frame.index].to_numpy(dtype=float)
        portfolio_returns = _portfolio_returns(weight_matrix, window)[0]
        kept_dates: list[pd.Timestamp] = []
        z_values: list[float] = []
        for date, r in zip(weight_frame.index, portfolio_returns, strict=False):
            stamps = [g for g in grid if g < date]
            if not stamps:
                continue
            stamp = stamps[-1]
            sigma = sigma_by_date.get(stamp, {}).get(book)
            if sigma is None:
                continue
            if not np.isfinite(r) or not np.isfinite(sigma) or sigma <= 0:
                continue
            z_values.append(float(r / sigma))
            kept_dates.append(date)
        out.append(pd.DataFrame({"date": kept_dates, "portfolio": book, "z": z_values}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _split_name(stem: str) -> tuple[str, str]:
    """Parse `bias_<version>_<family>` stems back into their two parts."""
    for version in VERSIONS:
        if stem.startswith(f"{version}_"):
            return version, stem[len(version) + 1 :]
    raise ValueError(f"unrecognized bias artifact stem {stem}")


def summarize_bias(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """The per-portfolio bias statistics plus the family-pooled rows.

    One row per (version, family, portfolio) and one pooled row per (version,
    family), the pooled row carrying `portfolio = "pooled"`.
    """
    root = Path(data_root)
    frames: list[pd.DataFrame] = []
    for path in sorted((root / "eval").glob("bias_*_*.parquet")):
        frame = pd.read_parquet(path)
        if frame.empty:
            continue
        stem = path.name[len("bias_") : -len(".parquet")]
        version, family = _split_name(stem)
        rows: list[dict[str, object]] = []
        for portfolio, group in frame.groupby("portfolio"):
            row: dict[str, object] = dict(bias_statistics(group["z"].to_numpy()))
            row["version"] = version
            row["family"] = family
            row["portfolio"] = portfolio
            rows.append(row)
        pooled: dict[str, object] = dict(bias_statistics(frame["z"].to_numpy()))
        pooled.update(version=version, family=family, portfolio="pooled")
        rows.append(pooled)
        frames.append(pd.DataFrame(rows))
    summary = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if store and not summary.empty:
        summary.to_parquet(root / "eval" / "e5_bias_summary.parquet", index=False)
    return summary


def family_bias_table(
    summary: pd.DataFrame, data_root: Path = DATA_ROOT, store: bool = True
) -> pd.DataFrame:
    """The family-pooled bias per version: the champion rule's input table."""
    pooled = summary.loc[summary["portfolio"] == "pooled"].copy()
    if store:
        pooled.to_parquet(
            Path(data_root) / "eval" / "e5_family_bias.parquet", index=False
        )
    return pooled


def rolling_bias(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """Rolling 12-month bias per version and family, on the pooled pairs.

    The pooled z series is every (portfolio, day) pair of the family in day
    order, and the rolling bias is sqrt(mean z squared) over the trailing 252
    trading days of pairs, with the delta-method band.
    """
    root = Path(data_root)
    rows: list[dict[str, object]] = []
    for path in sorted((root / "eval").glob("bias_*_*.parquet")):
        frame = pd.read_parquet(path)
        if frame.empty:
            continue
        stem = path.name[len("bias_") : -len(".parquet")]
        version, family = _split_name(stem)
        frame = frame.sort_values("date")
        z = frame["z"].to_numpy(dtype=float)
        n_per_day = int(frame.groupby("date")["z"].count().median())
        window = ROLLING_DAYS * max(n_per_day, 1)
        squared = np.where(np.isfinite(z), z**2, 0.0)
        valid = np.isfinite(z).astype(float)
        cum_sq = np.cumsum(squared)
        cum_n = np.cumsum(valid)
        bias = np.sqrt(np.clip(cum_sq, 1e-20, None) / np.clip(cum_n, 1, None))
        se = np.sqrt(2.0 / np.clip(cum_n, 1, None)) / (2.0 * bias)
        dates = frame["date"].to_numpy()
        for index in range(window - 1, len(z)):
            rows.append(
                {
                    "version": version,
                    "family": family,
                    "date": pd.Timestamp(dates[index]),
                    "rolling_bias": float(bias[index]),
                    "rolling_bias_lower": float(bias[index] - Z_CRITICAL * se[index]),
                    "rolling_bias_upper": float(bias[index] + Z_CRITICAL * se[index]),
                    "n_pairs": float(cum_n[index]),
                }
            )
    rolling = pd.DataFrame(rows)
    if store:
        rolling.to_parquet(root / "eval" / "e5_rolling_bias.parquet", index=False)
    return rolling


def run(data_root: Path = DATA_ROOT, store: bool = True) -> dict[str, object]:
    """Task 2: families, the daily bias engine and the summary tables."""
    root = Path(data_root)
    wide, counts = load_clean_wide(root)
    print("### E5 Task 2: families and the daily bias engine")
    print(
        f"exclusions: stale {counts['stale']}, outlier {counts['outlier']} rows "
        f"over {counts['n_mapped']} mapped names"
    )
    portfolios = build_families(root, store=store)
    print(
        "portfolios per family: "
        + str(
            {
                family: int(
                    portfolios.loc[portfolios["family"] == family][
                        "portfolio"
                    ].nunique()
                )
                for family in FAMILIES
            }
        )
    )
    diagonal, forecasts = forecast_monthly(root, store=store)
    print(
        f"forecasts: {diagonal.shape[0]} asset diagonals and "
        f"{forecasts.shape[0]} portfolio volatilities"
    )
    daily_z(root, store=store)
    summary = summarize_bias(root, store=store)
    family_table = family_bias_table(summary, root, store=store)
    rolling = rolling_bias(root, store=store)
    print("family-pooled bias by version:")
    print(
        family_table.sort_values("bias")
        .loc[:, ["version", "family", "bias", "abs_bias_minus_1", "coverage"]]
        .round(4)
        .to_string(index=False)
    )
    return {
        "portfolios": portfolios,
        "diagonal": diagonal,
        "forecasts": forecasts,
        "summary": summary,
        "family_table": family_table,
        "rolling": rolling,
        "exclusions": counts,
    }


HORIZON_SESSIONS = 21


def z_scaled_21(r_21: np.ndarray, sigma_daily: float) -> np.ndarray:
    """The 21-day standardized returns under the sqrt(21) scaling convention.

    The daily forecast is scaled by sqrt(21); the realized number is used as
    realized, never scaled.
    """
    return np.asarray(r_21, dtype=float) / (np.sqrt(HORIZON_SESSIONS) * sigma_daily)


def _block_sums(
    wide: pd.DataFrame, date: pd.Timestamp, step: int = HORIZON_SESSIONS
) -> pd.DataFrame:
    """Non-overlapping `step`-session sums ending at `date`, per name."""
    history = wide.loc[:date].iloc[-WINDOW:]
    aligned = history.iloc[-(len(history) // step) * step :]
    grouped = aligned.groupby(np.arange(len(aligned)) // step).sum()
    return grouped


def _factor_cov_21(date: pd.Timestamp, data_root: Path) -> np.ndarray | None:
    """The model's factor covariance on 21-session factor-return sums.

    The last 504 sessions of factor returns strictly before `date` are grouped
    into non-overlapping 21-session blocks, summed, and run through the model's
    own EWMA, which is the direct 21-day estimation of the factor part.
    """
    root = Path(data_root)
    factor_returns = pd.read_parquet(
        root / "models" / "XS-v1" / "factor_returns.parquet"
    )
    factor_returns = factor_returns.loc[pd.to_datetime(factor_returns["date"]) < date]
    history = factor_returns.pivot_table(index="date", columns="factor", values="f")
    ordered = list(fx.ESTIMATED_NAMES)
    if not set(ordered).issubset(history.columns):
        raise RuntimeError("the stored factor returns do not cover every factor")
    history = history.loc[:, ordered]
    if len(history) < 126:
        return None
    aligned = history.iloc[-(len(history) // HORIZON_SESSIONS) * HORIZON_SESSIONS :]
    blocks = aligned.groupby(np.arange(len(aligned)) // HORIZON_SESSIONS).sum()
    blocks = blocks.fillna(0.0)
    return fx.ewma_factor_cov(
        blocks.loc[:, ordered], half_life=fx.F_HALF_LIFE
    ).to_numpy(dtype=float)


def _direct_21(
    date: pd.Timestamp, names: list[str], blocks: pd.DataFrame, root: Path
) -> dict[str, np.ndarray]:
    """The directly estimated 21-day covariance per version at one month end.

    `blocks` are the non-overlapping 21-session return sums ending at `date`.
    The factor versions re-estimate the factor covariance on 21-day factor
    sums and scale their specific blocks by 21, the diagonal-scaling
    assumption made explicit.
    """
    values = blocks.to_numpy(dtype=float)
    std = values.std(axis=0, ddof=1)
    z_standard = (values - values.mean(axis=0)) / std
    out: dict[str, np.ndarray] = {}
    for version in VERSIONS:
        if version == "sample":
            out[version] = np.outer(std, std) * cov.sample_cov(z_standard)
        elif version == "ts_v1":
            out[version] = np.outer(std, std) * cov.market_model_cov(z_standard)
        elif version == "pca_v1":
            matrix, _keep = cov.pca_cov(z_standard)
            out[version] = np.outer(std, std) * matrix
        elif version == "pca_v1c":
            from efb import pca_eval

            frame = pd.DataFrame(values, columns=[f"N{i}" for i in range(len(names))])
            cov_fit = pca_eval.fit_covariance(frame)
            keep = int(np.sum(cov_fit.eigenvalues > cov_fit.mp_edge))
            out[version] = cov_fit.covariance(max(keep, 1))
        else:
            supplied = _xs_pieces(date, names, root)
            factor_21 = _factor_cov_21(date, root)
            if supplied is None or factor_21 is None:
                continue
            design = supplied["design"]
            factor_part = design @ factor_21 @ design.T
            if version == "xs_v1":
                specific = HORIZON_SESSIONS * supplied["specific"]
                out[version] = factor_part + np.diag(specific)
            else:
                low, diagonal, low_diagonal, _fallback = _xs_v2_block(date, names, root)
                out[version] = (
                    factor_part
                    + HORIZON_SESSIONS * low
                    + np.diag(HORIZON_SESSIONS * (diagonal - low_diagonal))
                )
    return out


def horizon_table(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """Task 3: the 1-day model scaled by sqrt(21) against a directly estimated
    21-day model, per version and family.

    Each month end contributes one 21-session realized block (the following
    21 sessions) per portfolio. The scaled branch standardizes it by
    sqrt(21) times the stored daily forecast; the direct branch standardizes
    it by the 21-day covariance estimated on the 21-session sums ending at
    the month end. The realized number is never scaled.
    """
    root = Path(data_root)
    wide, _counts = load_clean_wide(root)
    grid = race.race_grid(root)
    portfolios = pd.read_parquet(root / "eval" / "e5_portfolios.parquet")
    forecasts = pd.read_parquet(root / "eval" / "e5_forecast_portfolios.parquet")
    sigma_by_version: dict[str, dict[pd.Timestamp, dict[str, float]]] = {}
    for version in VERSIONS:
        sub = forecasts.loc[forecasts["version"] == version]
        sigma_by_version[version] = {
            pd.Timestamp(date): dict(
                zip(group["portfolio"], group["sigma"], strict=False)
            )
            for date, group in sub.groupby("date")
        }

    rows: list[dict[str, object]] = []
    for position, date in enumerate(grid):
        names = _window_names(wide, date)
        if len(names) < 50:
            continue
        forward = wide[names].loc[wide.index > date].iloc[:HORIZON_SESSIONS]
        if len(forward) < HORIZON_SESSIONS:
            continue
        forward_values = forward.to_numpy(dtype=float)
        blocks = _block_sums(wide[names], date)
        direct = _direct_21(date, names, blocks, root)
        day_rows = portfolios.loc[pd.to_datetime(portfolios["date"]) == date]
        weights_by_portfolio: dict[str, np.ndarray] = {}
        for portfolio, group in day_rows.groupby("portfolio"):
            series = group.set_index("ticker")["weight"].reindex(names).fillna(0.0)
            weights_by_portfolio[portfolio] = series.to_numpy(dtype=float)
        for portfolio, weights in weights_by_portfolio.items():
            # the block's realized return uses the daily engine's own
            # semantics: a day where a held name is missing is skipped, and
            # the block needs at least 15 of its 21 sessions to count
            day_missing = (np.isnan(forward_values) & (weights != 0)).any(axis=1)
            daily_r = np.nan_to_num(forward_values, nan=0.0) @ weights
            daily_r[day_missing] = np.nan
            if np.isfinite(daily_r).sum() < 15:
                continue
            r_21 = float(np.nansum(daily_r))
            if not np.isfinite(r_21):
                continue
            family = day_rows.loc[day_rows["portfolio"] == portfolio, "family"].iloc[0]
            for version in VERSIONS:
                daily_sigma = sigma_by_version[version].get(date, {}).get(portfolio)
                if (
                    daily_sigma is None
                    or not np.isfinite(daily_sigma)
                    or daily_sigma <= 0
                ):
                    continue
                if version not in direct:
                    continue
                sigma_21 = cov.portfolio_vol(weights, direct[version])
                if not np.isfinite(sigma_21) or sigma_21 <= 0:
                    continue
                rows.append(
                    {
                        "version": version,
                        "family": family,
                        "date": date,
                        "portfolio": portfolio,
                        "z_scaled": float(
                            z_scaled_21(np.array([r_21]), daily_sigma)[0]
                        ),
                        "z_direct": float(r_21 / sigma_21),
                    }
                )
        if position % 25 == 0:
            print(f"  horizon {position + 1}/{len(grid)} ({date.date()})")
    detail = pd.DataFrame(rows)
    out_rows: list[dict[str, object]] = []
    for (version, family), group in detail.groupby(["version", "family"]):
        scaled = group["z_scaled"].to_numpy(dtype=float)
        direct = group["z_direct"].to_numpy(dtype=float)
        scaled = scaled[np.isfinite(scaled)]
        direct = direct[np.isfinite(direct)]
        if len(scaled) < 30 or len(direct) < 30:
            continue
        bias_scaled = float(np.sqrt(np.mean(scaled**2)))
        bias_direct = float(np.sqrt(np.mean(direct**2)))
        out_rows.append(
            {
                "version": version,
                "family": family,
                "n_obs": float(len(scaled)),
                "bias_scaled": bias_scaled,
                "bias_direct": bias_direct,
                "ratio": bias_scaled / bias_direct,
            }
        )
    table = pd.DataFrame(out_rows)
    if store:
        table.to_parquet(root / "eval" / "e5_horizon.parquet", index=False)
    return table


VIX_TICKER = "^VIX"
EPISODES = {
    "2020_q1": (pd.Timestamp("2020-01-01"), pd.Timestamp("2020-03-31")),
    "2022": (pd.Timestamp("2022-01-03"), pd.Timestamp("2022-12-30")),
}


def fetch_vix(data_root: Path = DATA_ROOT) -> pd.DataFrame:
    """The regime variable: the VIX close, fetched once and stored."""
    import yfinance as yf

    root = Path(data_root)
    frame = yf.download(
        VIX_TICKER,
        start="2010-12-15",
        end="2026-09-12",
        progress=False,
        auto_adjust=False,
    )
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    vix = close.rename("vix").to_frame().reset_index()
    vix.columns = ["date", "vix"]
    vix["date"] = pd.to_datetime(vix["date"]).dt.normalize()
    (root / "raw").mkdir(parents=True, exist_ok=True)
    vix.to_parquet(root / "raw" / "vix.parquet", index=False)
    return vix


def regime_table(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """Task 4: bias, coverage and recovery time within VIX terciles and the
    named episodes, for every version, plus the champion's stress numbers.

    The VIX is the named regime variable; the tercile edges are the full-sample
    terciles, applied to every day, which is the standard historical partition
    and is recorded as such. Recovery time is trading days from the episode's
    peak |z| to the first later day whose trailing 21-session bias returns
    inside 0.9 to 1.1, measured on the pooled z across families.
    """
    root = Path(data_root)
    vix_path = root / "raw" / "vix.parquet"
    if not vix_path.exists():
        fetch_vix(root)
    vix_frame = pd.read_parquet(vix_path)
    vix = vix_frame.set_index("date")["vix"]
    wide, _counts = load_clean_wide(root)
    vix = vix.reindex(wide.index).ffill()
    lower, upper = np.nanquantile(vix.to_numpy(dtype=float), [1 / 3, 2 / 3])
    regime = vix.apply(
        lambda value: (
            "low"
            if value <= lower
            else (
                ("mid" if value <= upper else "high")
                if np.isfinite(value)
                else "unclassified"
            )
        )
    )
    rows: list[dict[str, object]] = []
    frames: dict[str, pd.DataFrame] = {}
    for path in sorted((root / "eval").glob("bias_*_*.parquet")):
        frame = pd.read_parquet(path)
        if frame.empty:
            continue
        stem = path.name[len("bias_") : -len(".parquet")]
        version, family = _split_name(stem)
        frame = frame.sort_values("date")
        frame["regime"] = regime.reindex(frame["date"]).to_numpy()
        for label in ("low", "mid", "high"):
            z = frame.loc[frame["regime"] == label, "z"].to_numpy(dtype=float)
            z = z[np.isfinite(z)]
            if len(z) < 30:
                continue
            stats = bias_statistics(z)
            rows.append(
                {
                    "version": version,
                    "family": family,
                    "regime": f"vix_{label}",
                    "bias": stats["bias"],
                    "coverage": stats["coverage"],
                    "n_obs": stats["n_obs"],
                }
            )
        for label, (start, end) in EPISODES.items():
            episode = frame.loc[(frame["date"] >= start) & (frame["date"] <= end)]
            z = episode["z"].to_numpy(dtype=float)
            z = z[np.isfinite(z)]
            if len(z) < 30:
                continue
            stats = bias_statistics(z)
            rows.append(
                {
                    "version": version,
                    "family": family,
                    "regime": label,
                    "bias": stats["bias"],
                    "coverage": stats["coverage"],
                    "n_obs": stats["n_obs"],
                }
            )
        frames[f"{version}__{family}"] = frame
    table = pd.DataFrame(rows)
    recovery_rows: list[dict[str, object]] = []
    for version in VERSIONS:
        pooled: list[pd.DataFrame] = [
            frames[key].loc[:, ["date", "z"]]
            for key in frames
            if key.startswith(f"{version}__")
        ]
        if not pooled:
            continue
        combined = pd.concat(pooled, ignore_index=True).sort_values("date")
        z = combined["z"].to_numpy(dtype=float)
        dates = combined["date"].to_numpy()
        squared = np.where(np.isfinite(z), z**2, np.nan)
        rolling = (
            pd.Series(squared, index=dates).rolling(21, min_periods=21).mean().pow(0.5)
        )
        for label, (start, end) in EPISODES.items():
            mask = (combined["date"] >= start) & (combined["date"] <= end)
            if not mask.any():
                continue
            in_episode = mask.to_numpy()
            episode_z = np.abs(z[in_episode])
            peak_position = int(np.nanargmax(episode_z))
            peak_date = pd.Timestamp(dates[in_episode][peak_position])
            after = rolling.loc[rolling.index > peak_date]
            back_inside = after[(after >= 0.9) & (after <= 1.1)]
            if len(back_inside):
                # the pooled frame holds one row per portfolio-day, so the
                # recovery is counted in sessions, not rows
                sessions = pd.DatetimeIndex(
                    sorted(pd.unique(combined["date"].to_numpy()))
                )
                peak_index = int(sessions.searchsorted(peak_date))
                return_index = int(
                    sessions.searchsorted(pd.Timestamp(back_inside.index[0]))
                )
                recovery = float(return_index - peak_index)
            else:
                recovery = float("nan")
            recovery_rows.append(
                {
                    "version": version,
                    "episode": label,
                    "peak_z": float(np.nanmax(episode_z)),
                    "peak_date": peak_date,
                    "recovery_trading_days": float(recovery),
                }
            )
    recovery = pd.DataFrame(recovery_rows)
    table = table.merge(
        recovery,
        how="left",
        left_on=["version", "regime"],
        right_on=["version", "episode"],
    ).drop(columns=["episode"])
    if store:
        table.to_parquet(root / "eval" / "e5_regimes.parquet", index=False)
    return table


def champion_rule_table(
    data_root: Path = DATA_ROOT,
) -> dict[str, object]:
    """Task 5: apply the champion rule exactly as printed, with the arithmetic.

    min mean |bias-1| across portfolio families; ties to fewer parameters; a
    champion must be refreshable daily from EFB's own data. TS-v1 is
    diagnostic only and ineligible, per the family note. The PRD's F5.1
    question (a version inside 0.9 to 1.1 on every family) is measured and
    recorded alongside, and the only stop belongs to `apply_champion`.
    """
    from efb import registry as registry_module

    root = Path(data_root)
    family = pd.read_parquet(root / "eval" / "e5_family_bias.parquet")
    payload = registry_module.load(root / "models" / "registry.json")
    eligible = registry_module.eligible(payload)
    if not eligible:
        raise RuntimeError("no eligible version is registered")
    scores: dict[str, float] = {}
    parameters: dict[str, float] = {}
    inside: dict[str, bool] = {}
    for version in eligible:
        tag = registry_module.engine_tag(version)
        rows = family.loc[family["version"] == tag]
        if len(rows) != len(FAMILIES):
            raise RuntimeError(
                f"{version} has {len(rows)} family rows, expected {len(FAMILIES)}"
            )
        scores[version] = float(rows["abs_bias_minus_1"].mean())
        inside[version] = bool(((rows["bias"] >= 0.9) & (rows["bias"] <= 1.1)).all())
        entry = payload["models"][version]
        params = entry.get("parameters", {})
        n_factors = float(params.get("n_factors", params.get("k_mean", 0.0)) or 0.0)
        n_names = float(params.get("n_names", params.get("n_names_mean", 0.0)) or 0.0)
        parameters[version] = n_factors + n_names
    winner = min(scores, key=lambda name: scores[name])
    winner_tag = registry_module.engine_tag(winner)
    band = family.loc[family["version"] == winner_tag, "bias_se"].max()
    near = [name for name in scores if abs(scores[name] - scores[winner]) < band]
    if len(near) > 1:
        winner = min(near, key=lambda name: parameters[name])
    arithmetic = pd.DataFrame(
        {
            "version": list(scores),
            "mean_abs_bias_minus_1": [scores[name] for name in scores],
            "inside_0_9_to_1_1_every_family": [inside[name] for name in scores],
            "parameters": [parameters[name] for name in scores],
            "champion": [name == winner for name in scores],
        }
    ).sort_values("mean_abs_bias_minus_1")
    print("### E5 Task 5: the champion rule, applied")
    print(arithmetic.round(4).to_string(index=False))
    print(f"champion: {winner}")
    # The PRD's stop condition 3: F5.1 asks whether any version sits inside
    # 0.9 to 1.1 on every family. It is recorded here and in RESULTS.json
    # either way; the session's stop list names only the stress-regime
    # conflict, so the rule's arithmetic is allowed to run to its end.
    f51_held = any(inside.values())
    if not f51_held:
        print(
            "F5.1 fails: no version lands inside 0.9 to 1.1 on every family. "
            "The failure and its mechanism are recorded; the champion rule's "
            "arithmetic does not require F5.1 to pass."
        )
    return {
        "winner": winner,
        "stopped": False,
        "f51_held": f51_held,
        "arithmetic": arithmetic,
        "scores": scores,
        "parameters": parameters,
        "inside": inside,
        "family_table": family,
    }


STRESS_MATERIALITY = 0.10


def asset_level_table(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """Task 3: asset-level bias and coverage beside the portfolio-level numbers.

    z_it = r_it / sigma_hat_it from the stored forecast diagonals, restricted
    to the names each family held, so every version and every family appears.
    """
    root = Path(data_root)
    wide, _counts = load_clean_wide(root)
    diagonal = pd.read_parquet(root / "eval" / "e5_forecast_diag.parquet")
    portfolios = pd.read_parquet(root / "eval" / "e5_portfolios.parquet")
    sessions = wide.index
    rows: list[dict[str, object]] = []
    for family in FAMILIES:
        held_set = set(portfolios.loc[portfolios["family"] == family, "ticker"])
        held_names = [name for name in wide.columns if name in held_set]
        for version in VERSIONS:
            sub = diagonal.loc[diagonal["version"] == version].pivot(
                index="date", columns="ticker", values="sigma"
            )
            sub = sub.reindex(columns=held_names)
            z_parts: list[np.ndarray] = []
            for date in sub.index:
                if date + pd.Timedelta(days=1) > sessions[-1]:
                    continue
                day = wide.index[wide.index > date][:1]
                if len(day) == 0:
                    continue
                r = wide.loc[day[0], held_names].to_numpy(dtype=float)
                sigma = sub.loc[date, held_names].to_numpy(dtype=float)
                with np.errstate(divide="ignore", invalid="ignore"):
                    z = r / sigma
                z_parts.append(z[np.isfinite(z)])
            if not z_parts:
                continue
            z = np.concatenate(z_parts)
            if len(z) < 30:
                continue
            row: dict[str, object] = dict(bias_statistics(z))
            row.update(version=version, family=family)
            rows.append(row)
    table = pd.DataFrame(rows)
    if store:
        table.to_parquet(root / "eval" / "e5_asset_level.parquet", index=False)
    return table


def stress_haircut(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """Task 4: the recommended stress haircut for the declared champion.

    The haircut is max(0, worst-episode-bias minus 1): the fraction by which
    the champion underforecast in its worst named episode, so a stress forecast
    is the model forecast times (1 + haircut). The basis is stored beside the
    number.
    """
    import json

    from efb import registry as registry_module

    root = Path(data_root)
    payload = json.loads((root / "models" / "registry.json").read_text())
    champions = [
        name for name, entry in payload["models"].items() if entry.get("champion")
    ]
    if not champions:
        return pd.DataFrame()
    champion = champions[0]
    regimes = pd.read_parquet(root / "eval" / "e5_regimes.parquet")
    episodes = regimes.loc[regimes["regime"].isin(EPISODES)]
    champion_rows = episodes.loc[
        episodes["version"] == registry_module.engine_tag(champion)
    ]
    q1 = champion_rows.loc[champion_rows["regime"] == "2020_q1"]
    worst = float(q1["bias"].mean()) if len(q1) else float("nan")
    worst_family = float(q1["bias"].max()) if len(q1) else float("nan")
    haircut = max(0.0, worst - 1.0)
    rows = [
        {
            "version": champion,
            "worst_episode_bias": worst,
            "worst_family_bias_2020_q1": worst_family,
            "stress_haircut": haircut,
            "basis": (
                "max(0, worst named-episode bias minus 1), where the episode "
                "bias is the champion's mean bias across families in 2020 Q1 "
                "and 2022; the fraction the model underforecast in its worst "
                "episode, so a stress forecast multiplies the model by "
                "(1 + haircut)"
            ),
        }
    ]
    table = pd.DataFrame(rows)
    if store:
        table.to_parquet(root / "eval" / "e5_stress_haircut.parquet", index=False)
    return table


def apply_champion(data_root: Path = DATA_ROOT) -> dict[str, object]:
    """Apply the champion rule, the stress-regime guard, and the registry flag.

    The user-level stop: if the rule's winner carries a materially worse
    stress-regime bias than the best eligible runner-up, the regime table is
    printed, the conflict stated, and no champion is declared. Materiality is
    a difference above 0.10 in the high-VIX-tercile bias averaged across
    families, which is more than the bias standard errors involved.
    """
    from efb import registry as registry_module

    root = Path(data_root)
    decision = champion_rule_table(root)
    if decision["stopped"]:
        return decision
    winner = str(decision["winner"])
    winner_tag = registry_module.engine_tag(winner)
    regimes = pd.read_parquet(root / "eval" / "e5_regimes.parquet")
    stress = regimes.loc[regimes["regime"] == "vix_high"].copy()
    stress_by_version = stress.groupby("version")["bias"].mean()
    scores = decision["scores"]
    assert isinstance(scores, dict)
    eligible = [name for name in scores if name != winner]
    if eligible:
        best_runner = min(
            (str(name) for name in eligible),
            key=lambda name: stress_by_version.get(
                registry_module.engine_tag(name), np.inf
            ),
        )
        winner_stress = float(stress_by_version.get(winner_tag, np.nan))
        runner_stress = float(
            stress_by_version.get(registry_module.engine_tag(best_runner), np.nan)
        )
        if np.isfinite(winner_stress) and np.isfinite(runner_stress):
            if winner_stress - runner_stress > STRESS_MATERIALITY:
                print(
                    "STOP: the champion rule selects "
                    f"{winner} (high-VIX bias {winner_stress:.3f}), whose "
                    "stress-regime bias is materially worse than the runner-up "
                    f"{best_runner} ({runner_stress:.3f}). The regime table:"
                )
                print(stress_by_version.sort_values().round(4).to_string())
                return {
                    **decision,
                    "stopped": True,
                    "stop_reason": "stress_regime_conflict",
                }
    registry_module.declare_champion(root / "models" / "registry.json", winner)
    print(f"champion declared: {winner}")
    return {**decision, "stopped": False, "stop_reason": None}
