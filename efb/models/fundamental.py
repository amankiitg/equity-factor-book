"""Cross-sectional fundamental model XS-v1 (Sprint E3, Tasks 1 to 6).

The model is r_t = X_{t-1} f_t + e_t, estimated one cross-section at a time
by weighted least squares with the identification constraint that
cap-weighted sector factor returns sum to zero.

Conventions that every function here obeys, because they are the sprint's
design rules:

- Every descriptor is dated t-1 and is computed from data through t-1 only.
  Rolling windows are taken over the frame and then shifted one session, so a
  descriptor dated t never sees row t.
- A descriptor is NaN, never filled, when its window is short or a row inside
  it is missing. The cross-section drops the name rather than imputing.
- Weights are sqrt(market cap) normalized to mean one, and the market cap used
  on date t is dated t-1.
- Factor returns are reported after the identification adjustment; the
  factor-mimicking portfolios are reported both before it (where
  X' w = e_k holds exactly) and after it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

BETA_WINDOW = 252
BETA_MIN_OBS = 126
MOMENTUM_SKIP = 21
MOMENTUM_WINDOW = 231
REVERSAL_WINDOW = 20
RESID_VOL_WINDOW = 63
LIQUIDITY_WINDOW = 63
LIQUIDITY_MIN_OBS = 42
MIN_NAMES = 50
WINSOR_MAD = 3.0
F_HALF_LIFE = 90
D_HALF_LIFE = 42
D_SHRINK_K = 60
NW_LAG = 2
TRADING_DAYS = 252

STYLE_NAMES = (
    "market",
    "size",
    "beta",
    "momentum",
    "reversal",
    "resid_vol",
    "liquidity",
)

# GICS sector codes, 11 sectors, in code order so the factor names are stable.
SECTOR_CODES: dict[str, int] = {
    "Energy": 10,
    "Materials": 15,
    "Industrials": 20,
    "Consumer Discretionary": 25,
    "Consumer Staples": 30,
    "Health Care": 35,
    "Financials": 40,
    "Information Technology": 45,
    "Communication Services": 50,
    "Utilities": 55,
    "Real Estate": 60,
}
SECTOR_NAMES = tuple(SECTOR_CODES)
SECTOR_FACTORS = tuple(f"sector_{SECTOR_CODES[s]}" for s in SECTOR_NAMES)
# The design estimates one column per style plus one per sector except the
# reference sector, whose dummy is dropped so that the market column and the
# sector block are not collinear. The reference sector's factor return is then
# derived from the constraint instead of estimated, which is what makes
# X' w_FMP = I an identity rather than a projection.
REFERENCE_SECTOR = SECTOR_NAMES[-1]
SECTOR_FACTORS_ESTIMATED = tuple(f"sector_{SECTOR_CODES[s]}" for s in SECTOR_NAMES[:-1])
FACTOR_NAMES = tuple(STYLE_NAMES) + SECTOR_FACTORS
ESTIMATED_NAMES = tuple(STYLE_NAMES) + SECTOR_FACTORS_ESTIMATED
N_ESTIMATED = len(ESTIMATED_NAMES)

DEFAULT_ORTHOGONALIZATION: dict[str, list[str]] = {
    "momentum": ["beta", "size"],
    "resid_vol": ["beta"],
}


@dataclass
class CrossSection:
    """One day's design matrix after the descriptor filters.

    `design` is the estimated design: seven style columns and ten sector
    dummies, the reference sector dropped so the market column and the sector
    block are not collinear. `reported_design` carries all eleven sector
    dummies and is what the risk decomposition uses, because the factor
    covariance is estimated on the identified factor returns over all eleven
    sectors. A small hand-built cross-section in a test may leave it None, in
    which case the estimated design is used and the two agree by construction.
    """

    date: pd.Timestamp
    tickers: pd.Index
    design: np.ndarray
    weights: np.ndarray
    returns: np.ndarray
    sector_names: np.ndarray
    reported_design: np.ndarray | None = None

    @property
    def risk_design(self) -> np.ndarray:
        return self.design if self.reported_design is None else self.reported_design


@dataclass
class FitResult:
    """The weighted least squares solution for one cross-section."""

    factor_returns: np.ndarray
    fmp_weights: np.ndarray
    precision: np.ndarray
    fitted: np.ndarray
    specific: np.ndarray
    r_squared: float


@dataclass
class Identified:
    """Factor returns after the cap-weighted sector constraint is imposed."""

    market: float
    styles: np.ndarray
    sector: np.ndarray
    n_styles: int

    def as_vector(self) -> np.ndarray:
        return np.concatenate([[self.market], self.styles, self.sector])


@dataclass
class DesignResult:
    """The full panel's design, one cross-section per usable day."""

    factor_names: list[str]
    days: list[CrossSection]
    standardized: dict[str, pd.DataFrame]
    stats: pd.DataFrame
    raw: dict[str, pd.DataFrame] = field(default_factory=dict)
    standard_pre: dict[str, pd.DataFrame] = field(default_factory=dict)
    winsorized: dict[str, pd.DataFrame] = field(default_factory=dict)

    @property
    def dates(self) -> list[pd.Timestamp]:
        return [day.date for day in self.days]


def market_cap(close: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    """Market cap = unadjusted close x share count usable that day."""
    return close * shares.reindex_like(close)


def market_proxy(returns: pd.DataFrame, mcap: pd.DataFrame) -> pd.Series:
    """Cap-weighted universe total return, market caps dated t-1.

    INPUT: returns (wide), mcap (wide, usable on the same date).
    OUTPUT: one series. A name contributes only where both exist.
    """
    weight = mcap.shift(1).where(returns.notna())
    total = weight.sum(axis=1)
    return (weight * returns).sum(axis=1) / total.replace(0, np.nan)


def _rolling(frame: pd.DataFrame, window: int, min_periods: int) -> pd.DataFrame:
    return frame.rolling(window, min_periods=min_periods)


def raw_descriptors(
    returns: pd.DataFrame,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    market_cap: pd.DataFrame,
    proxy: pd.Series,
) -> dict[str, pd.DataFrame]:
    """The seven style descriptors, each dated t-1, plus beta diagnostics.

    OUTPUT keys: the seven STYLE_NAMES, plus `beta_raw`, `beta_se` and
    `resid_model` for the walkthrough and the diagnostics. `market` is the
    constant column and is not standardized.
    """
    clean = returns.where(proxy.notna(), other=np.nan)
    mean_r = _rolling(clean, BETA_WINDOW, BETA_MIN_OBS).mean().shift(1)
    mean_m = _rolling(proxy, BETA_WINDOW, BETA_MIN_OBS).mean().shift(1)
    mean_rm = (
        _rolling(clean.mul(proxy, axis=0), BETA_WINDOW, BETA_MIN_OBS).mean().shift(1)
    )
    mean_m2 = _rolling(proxy**2, BETA_WINDOW, BETA_MIN_OBS).mean().shift(1)
    mean_r2 = _rolling(clean**2, BETA_WINDOW, BETA_MIN_OBS).mean().shift(1)
    count = _rolling(clean, BETA_WINDOW, BETA_MIN_OBS).count().shift(1)

    var_m = (mean_m2 - mean_m**2).where(lambda f: f > 0)
    cov = mean_rm.sub(mean_r.mul(mean_m, axis=0))
    beta_raw = cov.div(var_m, axis=0)
    var_r = (mean_r2 - mean_r**2).clip(lower=0)
    resid_var = (var_r - beta_raw.pow(2).mul(var_m, axis=0)).clip(lower=0)
    beta_se = np.sqrt(resid_var.div(count.mul(var_m, axis=0), axis=0))
    alpha = mean_r.sub(beta_raw.mul(mean_m, axis=0))

    beta_shrunk = _vasicek_beta(beta_raw, beta_se)
    resid_model = clean - alpha - beta_raw.mul(proxy, axis=0)
    resid_vol = (
        _rolling(resid_model, RESID_VOL_WINDOW, RESID_VOL_WINDOW)
        .std(ddof=1)
        .shift(1)
        .mul(np.sqrt(TRADING_DAYS))
    )
    log_returns = np.log1p(returns)
    momentum = np.expm1(
        _rolling(log_returns.shift(MOMENTUM_SKIP), MOMENTUM_WINDOW, MOMENTUM_WINDOW)
        .sum()
        .shift(0)
    )
    reversal = np.expm1(
        _rolling(log_returns.shift(1), REVERSAL_WINDOW, REVERSAL_WINDOW).sum()
    )
    dollar = close * volume
    liquidity = np.log(
        _rolling(dollar, LIQUIDITY_WINDOW, LIQUIDITY_MIN_OBS)
        .mean()
        .shift(1)
        .where(lambda frame: frame > 0)
    )
    return {
        "market": pd.DataFrame(1.0, index=returns.index, columns=returns.columns),
        # a zero or negative market cap is a missing value, not minus
        # infinity, so it is masked before the log rather than after
        "size": np.log(market_cap.shift(1).where(lambda frame: frame > 0)),
        "beta": beta_shrunk,
        "momentum": momentum,
        "reversal": reversal,
        "resid_vol": resid_vol,
        "liquidity": liquidity,
        "beta_raw": beta_raw,
        "beta_se": beta_se,
        "resid_model": resid_model,
        "obs_count": count,
    }


def _vasicek_beta(beta_raw: pd.DataFrame, beta_se: pd.DataFrame) -> pd.DataFrame:
    """Shrink each day's raw betas toward the day's cross-sectional mean.

    w = sigma_xs^2 / (sigma_xs^2 + SE^2), the E2 Vasicek weight, with
    sigma_xs the equal-weighted dispersion of raw betas that day.
    """
    out = beta_raw.copy() * np.nan
    for date, row in beta_raw.iterrows():
        ok = row.notna() & beta_se.loc[date].notna()
        if ok.sum() < 3:
            continue
        raw = row[ok].to_numpy()
        se = beta_se.loc[date][ok].to_numpy()
        sigma_xs = float(np.std(raw, ddof=0))
        if sigma_xs == 0:
            out.loc[date, ok] = raw
            continue
        weight = sigma_xs**2 / (sigma_xs**2 + se**2)
        out.loc[date, ok] = weight * raw + (1.0 - weight) * float(raw.mean())
    return out


def standardize(
    frame: pd.DataFrame, mask: pd.DataFrame, mcap: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Winsorize at plus or minus 3 MAD, then z score per cross-section.

    The mean is cap weighted and the standard deviation is equal weighted, so
    the cap-weighted market portfolio carries zero style exposure by
    construction. INPUT: raw descriptor, a usable-name mask, market cap usable
    on that date. OUTPUT: the standardized frame, a per-day stats table and the
    winsorized values, which the artifact stores so a reader can see what the
    clipping did.
    """
    out = frame.copy() * np.nan
    winsorized = frame.copy() * np.nan
    rows: list[dict[str, object]] = []
    for date, row in frame.iterrows():
        ok = row.notna() & mask.loc[date].fillna(False)
        if mcap is not None:
            ok = ok & mcap.loc[date].reindex(row.index).notna()
        n_ok = int(ok.sum())
        if n_ok < 5:
            rows.append(
                {"date": date, "n_names": n_ok, "median": np.nan, "mad": np.nan}
            )
            continue
        values = row[ok]
        weights = mcap.loc[date].reindex(values.index)
        median = float(values.median())
        mad = float((values - median).abs().median())
        if mad == 0:
            mad = float(values.std(ddof=0)) or 1.0
        lower, upper = median - WINSOR_MAD * mad, median + WINSOR_MAD * mad
        clipped = values.clip(lower, upper)
        winsorized.loc[date, ok] = clipped
        cap_mean = float((clipped * weights).sum() / weights.sum())
        spread = float(clipped.std(ddof=0))
        out.loc[date, ok] = (clipped - cap_mean) / spread if spread > 0 else 0.0
        rows.append(
            {
                "date": date,
                "n_names": n_ok,
                "median": median,
                "mad": mad,
                "cap_weighted_mean": cap_mean,
                "equal_weighted_std": spread,
                "lower": lower,
                "upper": upper,
            }
        )
    return out, pd.DataFrame(rows), winsorized


def orthogonalize(
    standard: dict[str, pd.DataFrame], mapping: dict[str, list[str]]
) -> dict[str, pd.DataFrame]:
    """Replace a descriptor with the residual of a cross-sectional regression.

    The residual is re-standardized, so an orthogonalized descriptor stays
    comparable in units across days. INPUT: the standardized descriptors and
    the map. OUTPUT: a copy where the mapped keys are residualized.
    """
    out = {key: frame.copy() for key, frame in standard.items()}
    for target, regressors in mapping.items():
        if target not in standard:
            continue
        residual = standard[target].copy() * np.nan
        for date, row in standard[target].iterrows():
            cols = [row] + [standard[name].loc[date] for name in regressors]
            ok = pd.concat(cols, axis=1).notna().all(axis=1)
            if int(ok.sum()) < 5:
                continue
            y = row[ok].to_numpy(dtype=float)
            design = np.column_stack(
                [
                    np.ones(int(ok.sum())),
                    *[
                        standard[name].loc[date][ok].to_numpy(dtype=float)
                        for name in regressors
                    ],
                ]
            )
            coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
            resid = y - design @ coefficients
            spread = float(np.std(resid, ddof=0))
            residual.loc[date, ok] = (
                (resid - resid.mean()) / spread if spread > 0 else 0.0
            )
        out[target] = residual
    return out


def build_cross_section(
    date: pd.Timestamp,
    styles: dict[str, pd.DataFrame],
    returns: pd.DataFrame,
    mcap: pd.DataFrame,
    sectors: pd.Series,
) -> CrossSection | None:
    """One day's design matrix, or None when too few names are usable.

    INPUT: standardized style frames, the return frame, market cap already
    dated t-1 (the caller shifts it), and the sector map. OUTPUT: the design,
    the sqrt(mcap) weights normalized to mean one, the returns and the sector
    label per name.
    """
    names = returns.columns
    ok = returns.loc[date].reindex(names).notna()
    for name in STYLE_NAMES:
        ok = ok & styles[name].loc[date].reindex(names).notna()
    ok = ok & pd.Series([ticker in set(sectors.index) for ticker in names], index=names)
    usable = pd.Index(names[ok])
    if len(usable) < MIN_NAMES:
        return None
    weights = mcap.loc[date].reindex(usable).to_numpy(dtype=float)
    if not np.all(np.isfinite(weights)) or (weights <= 0).any():
        good = np.isfinite(weights) & (weights > 0)
        usable = usable[good]
        weights = weights[good]
        if len(usable) < MIN_NAMES:
            return None
    columns = [
        styles[name].loc[date].reindex(usable).to_numpy(dtype=float)
        for name in STYLE_NAMES
    ]
    sector_labels = sectors.reindex(usable).to_numpy()
    for sector in SECTOR_NAMES[:-1]:
        columns.append((sector_labels == sector).astype(float))
    design = np.column_stack(columns)
    reported = [np.ones(len(usable))]
    reported.extend(columns[1 : len(STYLE_NAMES)])
    for sector in SECTOR_NAMES:
        reported.append((sector_labels == sector).astype(float))
    return CrossSection(
        date=pd.Timestamp(date),
        tickers=usable,
        design=design,
        weights=weights,
        returns=returns.loc[date].reindex(usable).to_numpy(dtype=float),
        sector_names=sector_labels,
        reported_design=np.column_stack(reported),
    )


def build_design(
    returns: pd.DataFrame,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    market_cap: pd.DataFrame,
    sectors: pd.Series,
    proxy: pd.Series,
    orthogonalization: dict[str, list[str]] | None = None,
) -> DesignResult:
    """The whole panel: raw descriptors, standardization, design matrices."""
    raw = raw_descriptors(returns, close, volume, market_cap, proxy)
    usable = returns.notna()
    standard: dict[str, pd.DataFrame] = {}
    winsorized: dict[str, pd.DataFrame] = {}
    stats: list[pd.DataFrame] = []
    for name in STYLE_NAMES:
        if name == "market":
            standard[name] = raw[name]
            winsorized[name] = raw[name]
            continue
        frame, table, clipped = standardize(raw[name], usable, market_cap.shift(1))
        frame.columns = returns.columns
        clipped.columns = returns.columns
        standard[name] = frame
        winsorized[name] = clipped
        table["descriptor"] = name
        stats.append(table)
    table = pd.concat(stats, ignore_index=True) if stats else pd.DataFrame()
    standard_pre = {key: value.copy() for key, value in standard.items()}
    standard = orthogonalize(standard, orthogonalization or DEFAULT_ORTHOGONALIZATION)
    lagged_cap = market_cap.shift(1)
    days: list[CrossSection] = []
    for date in returns.index:
        day = build_cross_section(date, standard, returns, lagged_cap, sectors)
        if day is not None:
            days.append(day)
    return DesignResult(
        factor_names=list(FACTOR_NAMES),
        days=days,
        standardized=standard,
        stats=table,
        raw=raw,
        standard_pre=standard_pre,
        winsorized=winsorized,
    )


def wls_fit(design: np.ndarray, returns: np.ndarray, weights: np.ndarray) -> FitResult:
    """Weighted least squares for one cross-section.

    INPUT: design (N x K), returns (N), weights sqrt(market cap) up to scale.
    OUTPUT: factor returns, the factor-mimicking portfolio weights (K x N,
    the rows of (X'WX)^-1 X'W), the precision matrix, fitted and specific
    returns, and the weighted cross-sectional R squared.

    The pseudo-inverse is used rather than a solve because the market column
    and the sector dummies are collinear by construction: the solution is
    defined up to the null direction, and `identify` picks the representative
    the constraint requires.
    """
    scale = np.sqrt(weights / weights.mean())
    weighted_design = design * scale[:, None]
    weighted_returns = returns * scale
    precision = np.linalg.pinv(weighted_design.T @ weighted_design)
    factor_returns = precision @ (weighted_design.T @ weighted_returns)
    # A = (X'WX)^-1 X'W, so the rows satisfy X' A' = I exactly. The extra
    # scale column is what turns the weighted design back into X.
    fmp_weights = (precision @ weighted_design.T) * scale[None, :]
    fitted = design @ factor_returns
    specific = returns - fitted
    weighted_mean = float(np.average(returns, weights=scale**2))
    total = float(np.sum((scale * (returns - weighted_mean)) ** 2))
    residual = float(np.sum((scale * specific) ** 2))
    r_squared = 1.0 - residual / total if total > 0 else float("nan")
    return FitResult(
        factor_returns=factor_returns,
        fmp_weights=fmp_weights,
        precision=precision,
        fitted=fitted,
        specific=specific,
        r_squared=r_squared,
    )


def sector_cap_weights(day: CrossSection) -> np.ndarray:
    """Each sector's share of the cross-section's market cap, in code order."""
    total = float(day.weights.sum())
    weights = []
    for sector in SECTOR_NAMES:
        mask = day.sector_names == sector
        weights.append(float(day.weights[mask].sum()) / total if total else 0.0)
    return np.array(weights)


def identify(
    estimated: np.ndarray, sector_weights: np.ndarray, n_styles: int
) -> Identified:
    """Re-express the sector block so cap-weighted sector returns sum to zero.

    INPUT: the estimated factor returns of the reduced design (styles first,
    then the sectors other than the reference sector), the eleven sector cap
    weights in code order, and the number of style columns including the
    market.

    OUTPUT: the Identified factor returns over all eleven sectors. The
    reference sector is absorbed into the market by the design, so it enters
    the re-expression as a zero sector return; the cap-weighted mean of that
    block is then moved into the market factor, which makes the market factor
    the cap-weighted market return and makes the eleven sector returns sum to
    zero when cap weighted. Fitted values and specific returns are unchanged,
    because the reference sector's fitted value loses exactly what the market
    factor gains for a reference-sector name.
    """
    sector_estimated = estimated[n_styles:].copy()
    styles = estimated[1:n_styles].copy()
    all_sectors = np.concatenate([sector_estimated, [0.0]])
    shift = float(all_sectors @ sector_weights)
    return Identified(
        market=float(estimated[0]) + shift,
        styles=styles,
        sector=all_sectors - shift,
        n_styles=n_styles,
    )


def identified_transform(sector_weights: np.ndarray) -> np.ndarray:
    """The matrix that maps estimated factor returns to the reported ones.

    Shape (18, 17): the eleven reported sector returns and the market factor
    are a linear re-expression of the seventeen estimated ones, with the
    cap-weighted sector mean moved into the market. The same matrix converts
    the estimated factor-mimicking portfolios into the reported ones.
    """
    n_styles = len(STYLE_NAMES)
    transform = np.zeros((len(FACTOR_NAMES), N_ESTIMATED))
    transform[:N_ESTIMATED, :] = np.eye(N_ESTIMATED)
    cap = np.zeros(N_ESTIMATED)
    cap[n_styles:] = sector_weights[:-1]
    transform[0] += cap
    transform[n_styles:] -= cap
    return transform


def fit_panel(
    design: DesignResult, min_names: int = MIN_NAMES
) -> dict[str, pd.DataFrame]:
    """Fit every cross-section and return the factor, specific and R2 tables.

    OUTPUT: three long frames, one row per day and factor, one per day and
    name, and one per day.
    """
    factor_rows: list[dict[str, object]] = []
    specific_rows: list[dict[str, object]] = []
    quality_rows: list[dict[str, object]] = []
    for day in design.days:
        if len(day.tickers) < min_names:
            continue
        fit = wls_fit(day.design, day.returns, day.weights)
        weights = sector_cap_weights(day)
        identified = identify(fit.factor_returns, weights, n_styles=len(STYLE_NAMES))
        identified_vector = identified.as_vector()
        exposure = day.design.T @ fit.fmp_weights.T
        identity_error = float(np.max(np.abs(exposure - np.eye(day.design.shape[1]))))
        sector_sum = float(identified.sector @ weights)
        for index, name in enumerate(design.factor_names):
            factor_rows.append(
                {
                    "date": day.date,
                    "factor": name,
                    "f": float(identified_vector[index]),
                    "f_pre_identification": (
                        float(fit.factor_returns[index])
                        if index < N_ESTIMATED
                        else float("nan")
                    ),
                    "estimation": "derived" if index >= N_ESTIMATED else "estimated",
                    "is_sector": index >= len(STYLE_NAMES),
                    "is_reference_sector": name
                    == f"sector_{SECTOR_CODES[REFERENCE_SECTOR]}",
                    "n_names": len(day.tickers),
                }
            )
        for ticker, value in zip(day.tickers, fit.specific, strict=True):
            specific_rows.append(
                {"date": day.date, "ticker": ticker, "specific_return": float(value)}
            )
        quality_rows.append(
            {
                "date": day.date,
                "r_squared": float(fit.r_squared),
                "n_names": len(day.tickers),
                "n_descriptors": int(day.design.shape[1]),
                "fmp_identity_max_abs_error": identity_error,
                "sector_cap_weighted_sum": sector_sum,
                "rank_deficient": bool(
                    np.linalg.matrix_rank(day.design) < day.design.shape[1]
                ),
            }
        )
    return {
        "factor_returns": pd.DataFrame(factor_rows),
        "specific_returns": pd.DataFrame(specific_rows),
        "xs_r2": pd.DataFrame(quality_rows),
    }


def ewma_factor_cov(
    factor_returns: pd.DataFrame, half_life: int = F_HALF_LIFE, nw_lag: int = NW_LAG
) -> pd.DataFrame:
    """EWMA factor covariance with a Newey-West lag correction.

    INPUT: the wide factor return frame, one column per factor, no NaN.
    OUTPUT: the K x K covariance matrix as a labelled frame.

    The estimate is Cov = Gamma_0 + sum_l (1 - l/(L+1)) (Gamma_l + Gamma_l'),
    where Gamma_l is the exponentially weighted autocovariance at lag l with
    weight (1-alpha)^(T-1-i) for row i, alpha = 1 - 0.5^(1/half_life). The
    decorator is the fixed-lag decay the PRD records as n_lags, so the
    correction ages in the same way the covariance does.
    """
    values = factor_returns.to_numpy(dtype=float)
    n_rows = values.shape[0]
    alpha = 1.0 - 0.5 ** (1.0 / half_life)
    # decay[i] is the weight of row i, so the most recent row gets weight one
    # and the oldest (1 - alpha)^(T-1)
    decay = (1.0 - alpha) ** np.arange(n_rows, dtype=float)[::-1]
    decay = decay / decay.sum()
    mean = (values * decay[:, None]).sum(axis=0)
    demeaned = values - mean
    covariance = (demeaned * decay[:, None]).T @ demeaned
    for lag in range(1, nw_lag + 1):
        weight = 1.0 - lag / (nw_lag + 1)
        left = demeaned[:-lag] * decay[:-lag, None]
        right = demeaned[lag:]
        autocovariance = left.T @ right
        covariance = covariance + weight * (autocovariance + autocovariance.T)
    return pd.DataFrame(
        covariance, index=factor_returns.columns, columns=factor_returns.columns
    )


def fama_macbeth(factor_returns: pd.DataFrame, nw_lag: int = NW_LAG) -> pd.DataFrame:
    """Premium, Newey-West standard error and t statistic per factor.

    INPUT: the wide factor return frame. OUTPUT: one row per factor with the
    daily and annualized premium, the standard error, the t statistic and the
    `priced` flag, which is true when the absolute t statistic reaches 2. A
    premium that is not priced is reported, never dropped.
    """
    rows: list[dict[str, object]] = []
    for name in factor_returns.columns:
        series = factor_returns[name].dropna().to_numpy(dtype=float)
        n_obs = len(series)
        premium = float(series.mean()) if n_obs else float("nan")
        demeaned = series - series.mean()
        gamma0 = float(demeaned @ demeaned) / n_obs if n_obs else float("nan")
        variance = gamma0
        for lag in range(1, nw_lag + 1):
            decay = 1.0 - lag / (nw_lag + 1)
            autocovariance = float(demeaned[:-lag] @ demeaned[lag:]) / n_obs
            variance += 2.0 * decay * autocovariance
        standard_error = float(np.sqrt(max(variance, 0.0) / n_obs)) if n_obs else np.nan
        statistic = premium / standard_error if standard_error else float("nan")
        rows.append(
            {
                "factor": name,
                "premium_daily": premium,
                "premium_annualized": premium * TRADING_DAYS,
                "nw_se": standard_error,
                "t_stat": statistic,
                "n_days": n_obs,
                "priced": (
                    bool(abs(statistic) >= 2.0) if np.isfinite(statistic) else False
                ),
            }
        )
    return pd.DataFrame(rows)


def specific_variance(
    specific_returns: pd.DataFrame,
    sectors: pd.Series,
    market_cap: pd.DataFrame,
    dates: list[pd.Timestamp] | None = None,
    half_life: int = D_HALF_LIFE,
    shrink_k: int = D_SHRINK_K,
    n_buckets: int = 3,
) -> pd.DataFrame:
    """EWMA specific variance, shrunk toward the sector-size bucket mean.

    Buckets are (sector, market cap tercile within the cross-section). The
    shrinkage weight is n / (n + k) with n the name's usable observations, so
    a short history is pulled to its bucket and a long one keeps its own
    number. OUTPUT: a long frame with the raw and shrunk values, the bucket
    label, the bucket mean and the observation count, restricted to `dates`
    when one is given, because the callers only read month ends.
    """
    squared = specific_returns**2
    decayed = squared.ewm(halflife=half_life, adjust=True).mean()
    counts = squared.notna().cumsum()
    lagged_cap = market_cap.shift(1)
    tercile = np.ceil(lagged_cap.rank(axis=1, pct=True) * n_buckets).clip(1, n_buckets)
    sector_label = pd.Series(sectors)
    selected = decayed.index if dates is None else decayed.index.intersection(dates)
    levels = tercile.reindex(selected)
    rows: list[dict[str, object]] = []
    for date in selected:
        raw = decayed.loc[date].dropna()
        if raw.empty:
            continue
        names = raw.index
        level_row = levels.loc[date].reindex(names) if date in levels.index else None
        label_rows = [
            (
                f"{sector_label.get(ticker)}|{int(level_row[ticker])}"
                if level_row is not None and pd.notna(level_row[ticker])
                else f"{sector_label.get(ticker)}|NA"
            )
            for ticker in names
        ]
        bucket = pd.Series(label_rows, index=names)
        bucket_mean = raw.groupby(bucket).transform("mean")
        n_obs = counts.loc[date].reindex(names)
        weight = n_obs / (n_obs + shrink_k)
        shrunk = weight * raw + (1.0 - weight) * bucket_mean
        for ticker in names:
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "specific_var_raw": float(raw[ticker]),
                    "specific_var": float(shrunk[ticker]),
                    "bucket": bucket[ticker],
                    "bucket_mean": float(bucket_mean[ticker]),
                    "n_obs": float(n_obs[ticker]),
                }
            )
    return pd.DataFrame(rows)
