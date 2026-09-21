"""Sprint E9: transaction costs and capacity.

The alpha is the E8 synthetic alpha with a known IC, labeled as such,
because no real signal passed RG-Signal. Capacity is a function of the
assumed IC, so the capacity curve and the halving AUM are reported per rho.
Cost parameters that free data cannot pin are stated with their source and
their uncertainty, never as a clean point estimate.

The spread input is a size-decile schedule from 10 bp (smallest names) to
1 bp (largest) of half-spread, stated as an assumption with a half and
double sensitivity, because the free estimators (Corwin-Schultz and
Abdi-Ranaldo) measure volatility rather than the spread on daily high-low
data for S&P 500 names. The probe that led to the schedule is stored in
data/costs/spread_probe.parquet.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"

RHOS = (0.02, 0.05, 0.10)
SEEDS = (0, 1, 2, 3, 4)
HORIZON = 21
CORWIN_WINDOW = 63
IMPACT_K = 0.5  # square-root impact coefficient, uncertainty [0.25, 1.0]
COMMISSION = 1e-4  # 1 bp per dollar traded, one side
BORROW_RATE = 0.02  # 2% per year on short notional, the E6 provisional
ANNUAL = 252

# The chosen half-spread schedule by size decile, stated as an assumption.
# The free estimators measure volatility rather than the spread on daily
# high-low data for S&P 500 names, so the cost input is this schedule from
# 10 bp (decile 0, the smallest names) to 1 bp (decile 9, the largest), in
# half-spread terms. The sensitivity runs at half and double.
SCHEDULE_BP = np.linspace(10.0, 1.0, 10)


def _corwin_schultz(prices: pd.DataFrame, window: int, adjust: bool) -> pd.Series:
    """The Corwin-Schultz (2012) high-low spread estimator per ticker.

    With `adjust` the overnight (gamma) term from the paper is subtracted
    and negative two-day estimates are floored at zero, which is the
    paper's directive. Without it the estimator is the two-day component
    alone, kept only for the before and after record in the probe.
    OUTPUT: a Series of the half-spread per ticker, the median of the
    trailing-window estimates over the name's history.
    """
    wide_high = prices["high"].unstack("ticker")
    wide_low = prices["low"].unstack("ticker")
    log_high = np.log(wide_high)
    log_low = np.log(wide_low)
    half: dict[str, float] = {}
    for ticker in wide_high.columns:
        hi = log_high[ticker]
        lo = log_low[ticker]
        both = pd.concat([hi, lo], axis=1).dropna()
        if len(both) < window:
            continue
        h = both.iloc[:, 0].to_numpy(dtype=float)
        low = both.iloc[:, 1].to_numpy(dtype=float)
        beta = (h - low) ** 2
        hi_roll = np.maximum(h[:-1], h[1:])
        lo_roll = np.minimum(low[:-1], low[1:])
        gamma = (hi_roll - lo_roll) ** 2
        estimates: list[float] = []
        for start in range(0, len(both) - window + 1, window):
            b = float(beta[start : start + window].mean())
            g = float(gamma[start : start + window - 1].mean())
            if b <= 0 or g <= 0:
                continue
            alpha = (np.sqrt(2.0 * b) - np.sqrt(b)) / (3.0 - 2.0 * np.sqrt(2.0))
            if adjust:
                alpha -= np.sqrt(g / (3.0 - 2.0 * np.sqrt(2.0)))
            spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
            if not np.isfinite(spread):
                continue
            if adjust:
                # the paper's directive: a negative two-day estimate, where
                # the overnight component exceeds the spread estimate, is
                # floored at zero
                estimates.append(max(spread, 0.0) / 2.0)
            elif 0 < spread < 1:
                estimates.append(spread / 2.0)
        if estimates:
            half[ticker] = float(np.median(estimates))
    return pd.Series(half, name="half_spread")


def corwin_schultz(prices: pd.DataFrame, window: int = CORWIN_WINDOW) -> pd.Series:
    """The overnight-adjusted Corwin-Schultz estimator, the corrected one."""
    return _corwin_schultz(prices, window, adjust=True)


def corwin_schultz_raw(prices: pd.DataFrame, window: int = CORWIN_WINDOW) -> pd.Series:
    """The unadjusted Corwin-Schultz estimator, kept for the before record."""
    return _corwin_schultz(prices, window, adjust=False)


def abdi_ranaldo(prices: pd.DataFrame, window: int = CORWIN_WINDOW) -> pd.Series:
    """The Abdi-Ranaldo (2017) close-high-low spread estimator per ticker.

    The spread is 2 * sqrt(-cov1) of the close-to-midpoint series, where a
    positive first autocovariance cannot be inverted and floors at zero.
    OUTPUT: a Series of the half-spread per ticker, the median of the
    trailing-window estimates.
    """
    wide_high = prices["high"].unstack("ticker")
    wide_low = prices["low"].unstack("ticker")
    wide_close = prices["close"].unstack("ticker")
    log_high = np.log(wide_high)
    log_low = np.log(wide_low)
    log_close = np.log(wide_close)
    half: dict[str, float] = {}
    for ticker in wide_high.columns:
        frame = pd.concat(
            [log_high[ticker], log_low[ticker], log_close[ticker]], axis=1
        ).dropna()
        if len(frame) < window:
            continue
        h = frame.iloc[:, 0].to_numpy(dtype=float)
        low = frame.iloc[:, 1].to_numpy(dtype=float)
        close = frame.iloc[:, 2].to_numpy(dtype=float)
        u = close - (h + low) / 2.0
        estimates: list[float] = []
        for start in range(0, len(u) - window + 1, window):
            window_u = u[start : start + window]
            cov1 = float(np.mean(window_u[:-1] * window_u[1:]))
            spread = 2.0 * np.sqrt(max(-cov1, 0.0))
            if np.isfinite(spread):
                estimates.append(spread / 2.0)
        if estimates:
            half[ticker] = float(np.median(estimates))
    return pd.Series(half, name="half_spread")


def _market_cap(prices: pd.DataFrame, root: Path) -> pd.Series:
    """The median market capitalisation per ticker, shares times close."""
    shares = pd.read_parquet(root / "raw" / "shares_history.parquet")
    wide_shares = shares.pivot_table(index="date", columns="ticker", values="shares")
    wide_shares = wide_shares.reindex(prices.index.get_level_values("date").unique())
    wide_shares = wide_shares.ffill()
    close = prices["close"].unstack("ticker")
    mcap = wide_shares.reindex(columns=close.columns) * close.reindex(wide_shares.index)
    return mcap.median().rename("market_cap")


def _adv_per_ticker(prices: pd.DataFrame) -> pd.Series:
    """The median daily dollar volume per ticker, volume times close."""
    dollar_volume = (prices["volume"] * prices["close"]).unstack("ticker")
    return dollar_volume.median().rename("adv")


def size_deciles(prices: pd.DataFrame, root: Path) -> pd.Series:
    """The size decile per ticker, 0 for the smallest market-cap decile."""
    mcap = _market_cap(prices, root)
    frame = mcap[mcap > 0].to_frame("market_cap").dropna()
    deciles = pd.qcut(frame["market_cap"].rank(method="first"), 10, labels=False)
    return deciles.rename("size_decile")


def spread_schedule(
    prices: pd.DataFrame, root: Path, multiplier: float = 1.0
) -> pd.Series:
    """The chosen half-spread schedule by size decile, stated as an assumption.

    The free estimators (Corwin-Schultz and Abdi-Ranaldo) measure
    volatility, not the spread, on daily high-low data for S&P 500 names,
    so the cost input is a size-decile schedule from 10 bp (smallest) to
    1 bp (largest) of half-spread. The sensitivity runs at half and double
    via `multiplier`.
    """
    deciles = size_deciles(prices, root)
    bp = SCHEDULE_BP[deciles.to_numpy(dtype=int)] * multiplier
    return pd.Series(bp / 1e4, index=deciles.index, name="half_spread")


def spread_probe(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """The spread-estimator comparison, per ticker, stored as the record.

    One row per ticker with the size decile, market cap and the median
    half-spread from the raw Corwin-Schultz, the overnight-adjusted
    Corwin-Schultz, the Abdi-Ranaldo estimator and the chosen schedule.
    This is the evidence that F9.5's schedule replaced estimators that
    measure volatility rather than the spread.
    """
    root = Path(data_root)
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    raw = corwin_schultz_raw(prices)
    adjusted = corwin_schultz(prices)
    ar = abdi_ranaldo(prices)
    sched = spread_schedule(prices, root)
    deciles = size_deciles(prices, root)
    mcap = _market_cap(prices, root)
    frame = pd.concat(
        [deciles, mcap, raw, adjusted, ar, sched], axis=1, join="inner"
    ).dropna()
    frame.columns = [
        "size_decile",
        "market_cap",
        "cs_raw_half_spread",
        "cs_adjusted_half_spread",
        "abdi_ranaldo_half_spread",
        "schedule_half_spread",
    ]
    frame = frame[frame["market_cap"] > 0]
    if store:
        out = root / "costs"
        out.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out / "spread_probe.parquet", index=False)
    return frame


def cost_curves(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """The chosen half-spread and ADV by size decile.

    OUTPUT: one row per size decile with the mean half-spread from the
    chosen schedule, market cap, ADV and name count. The F9.3 estimator
    correlation is scored from the probe artifact, not from this chosen
    input.
    """
    root = Path(data_root)
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    spread = spread_schedule(prices, root)
    mcap = _market_cap(prices, root)
    adv = _adv_per_ticker(prices)
    frame = pd.concat([spread, mcap, adv], axis=1, join="inner").dropna()
    frame = frame[frame["market_cap"] > 0]
    frame["size_decile"] = pd.qcut(
        frame["market_cap"].rank(method="first"), 10, labels=False
    )
    grouped = (
        frame.groupby("size_decile")
        .agg(
            mean_half_spread=("half_spread", "mean"),
            mean_market_cap=("market_cap", "mean"),
            mean_adv=("adv", "mean"),
            n_names=("half_spread", "count"),
        )
        .reset_index()
    )
    correlation = float(frame["half_spread"].corr(frame["market_cap"].rank()))
    grouped["spread_size_rank_correlation"] = correlation
    if store:
        out = root / "costs"
        out.mkdir(parents=True, exist_ok=True)
        grouped.to_parquet(out / "cost_curves.parquet", index=False)
    return grouped


def _trade_cost(
    delta_w: np.ndarray,
    spread: np.ndarray,
    sigma: np.ndarray,
    adv: np.ndarray,
    aum: float,
    k: float,
) -> float:
    """The transaction cost of a rebalance as a fraction of AUM."""
    dollar_trade = np.abs(delta_w) * aum
    impact = k * sigma * np.sqrt(np.maximum(dollar_trade, 0.0) / np.maximum(adv, 1.0))
    total = float(
        np.sum((spread + COMMISSION) * np.abs(delta_w) + impact * np.abs(delta_w))
    )
    return total


def _realized_returns(weights_wide: pd.DataFrame, root: Path) -> pd.Series:
    """The per-rebalance realized specific return of a weight series.

    The result is indexed by the rebalance date, so a caller can align the
    realized returns with the cost series by date rather than by position.
    """
    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_returns.parquet")
    specific["date"] = pd.to_datetime(specific["date"])
    specific_wide = specific.pivot(
        index="date", columns="ticker", values="specific_return"
    )
    values: list[float] = []
    dates: list[object] = []
    for date in weights_wide.index:
        names = [t for t in weights_wide.columns if t in specific_wide.columns]
        w = weights_wide.loc[date].reindex(names).to_numpy(dtype=float)
        forward = specific_wide.loc[specific_wide.index > date].iloc[:HORIZON]
        if len(forward) < HORIZON:
            continue
        e = (
            np.prod(1.0 + forward.reindex(columns=names).to_numpy(dtype=float), axis=0)
            - 1.0
        )
        both = np.isfinite(w) & np.isfinite(e)
        values.append(float((w[both] * e[both]).sum()))
        dates.append(date)
    return pd.Series(values, index=pd.DatetimeIndex(dates))


def capacity_curve(
    data_root: Path = DATA_ROOT,
    store: bool = True,
    spread_multiplier: float = 1.0,
) -> pd.DataFrame:
    """The net Sharpe against AUM for the proportional seed book, per rho and k.

    OUTPUT: rows (rho, k, aum, gross_sharpe, net_sharpe) over an AUM grid,
    plus the halving AUM per (rho, k) in a companion frame. The spread is
    the chosen size-decile schedule, scaled by `spread_multiplier` for the
    half and double sensitivity.
    """
    root = Path(data_root)
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    spread = spread_schedule(prices, root, multiplier=spread_multiplier)
    adv = _adv_per_ticker(prices)
    weights = pd.read_parquet(root / "portfolios" / "proportional.parquet")
    rows: list[dict[str, object]] = []
    halving_rows: list[dict[str, object]] = []
    aum_grid = np.logspace(6, 10, 25)  # $1m to $10b
    for rho in RHOS:
        for k in (IMPACT_K / 2, IMPACT_K, IMPACT_K * 2):
            net_by_aum: dict[float, float] = {}
            net_mean_by_aum: dict[float, float] = {}
            gross_sharpe = float("nan")
            for seed in SEEDS:
                frame = weights.loc[(weights["rho"] == rho) & (weights["seed"] == seed)]
                if frame.empty:
                    continue
                w_wide = frame.pivot_table(
                    index="date", columns="ticker", values="weight"
                )
                # the book is dollar-neutral long/short; normalizing each
                # rebalance to gross 1 makes AUM the gross notional, so the
                # turnover and the impact are measured per dollar of capital
                # instead of per dollar of a 30x-leveraged position
                gross = w_wide.abs().sum(axis=1)
                w_wide = w_wide.div(gross, axis=0)
                realized = _realized_returns(w_wide, root)
                gross_sharpe = float(
                    realized.mean() / realized.std(ddof=1) * np.sqrt(ANNUAL / HORIZON)
                    if realized.std(ddof=1) > 0
                    else float("nan")
                )
                # per-name spread, daily specific volatility and ADV
                names = [t for t in w_wide.columns]
                spread_map = spread.reindex(names).fillna(spread.median())
                adv_map = adv.reindex(names).fillna(adv.median())
                specific_returns = pd.read_parquet(
                    root / "models" / "XS-v1" / "specific_returns.parquet"
                )
                sigma_map = (
                    specific_returns.groupby("ticker")["specific_return"]
                    .std(ddof=1)
                    .reindex(names)
                    .fillna(specific_returns["specific_return"].std(ddof=1))
                )
                # the cost is paid to move between the rebalances that have a
                # realized return, so the cost series aligns with realized by date
                realized_dates = realized.index
                aligned = w_wide.reindex(realized_dates)
                for aum in aum_grid:
                    costs: list[float] = []
                    for index in range(1, len(realized_dates)):
                        current = (
                            aligned.iloc[index]
                            .reindex(names)
                            .fillna(0.0)
                            .to_numpy(dtype=float)
                        )
                        prev = (
                            aligned.iloc[index - 1]
                            .reindex(names)
                            .fillna(0.0)
                            .to_numpy(dtype=float)
                        )
                        delta = current - prev
                        costs.append(
                            _trade_cost(
                                delta,
                                spread_map.to_numpy(dtype=float),
                                sigma_map.to_numpy(dtype=float),
                                adv_map.to_numpy(dtype=float),
                                aum,
                                k,
                            )
                        )
                    net = realized.iloc[1:] - pd.Series(costs, index=realized.index[1:])
                    net_sharpe = float(
                        net.mean() / net.std(ddof=1) * np.sqrt(ANNUAL / HORIZON)
                        if net.std(ddof=1) > 0
                        else float("nan")
                    )
                    net_by_aum[aum] = net_by_aum.get(aum, 0.0) + net_sharpe
                    net_mean_by_aum[aum] = net_mean_by_aum.get(aum, 0.0) + float(
                        net.mean()
                    )
            for aum in aum_grid:
                net_sharpe = float(net_by_aum.get(aum, float("nan"))) / len(SEEDS)
                net_mean = float(net_mean_by_aum.get(aum, float("nan"))) / len(SEEDS)
                rows.append(
                    {
                        "rho": rho,
                        "k": k,
                        "aum": float(aum),
                        "gross_sharpe": gross_sharpe,
                        "net_sharpe": net_sharpe,
                        "net_mean": net_mean,
                    }
                )
            # the halving AUM: the first AUM where net Sharpe falls to half of
            # gross. If the book is already below gross/2 at the lowest AUM the
            # halving point is undefined, and NaN is stored rather than the
            # grid edge masquerading as a number.
            halving = float("nan")
            first_net = float(net_by_aum.get(float(aum_grid[0]), float("nan"))) / len(
                SEEDS
            )
            if (
                np.isfinite(gross_sharpe)
                and np.isfinite(first_net)
                and first_net > gross_sharpe / 2.0
            ):
                for aum in aum_grid:
                    net_sharpe = float(net_by_aum.get(aum, float("nan"))) / len(SEEDS)
                    if np.isfinite(net_sharpe) and net_sharpe <= gross_sharpe / 2.0:
                        halving = float(aum)
                        break
            halving_rows.append(
                {
                    "rho": rho,
                    "k": k,
                    "gross_sharpe": gross_sharpe,
                    "halving_aum": halving,
                }
            )
    frame = pd.DataFrame(rows)
    halving = pd.DataFrame(halving_rows)
    if store:
        out = root / "costs"
        out.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out / "capacity.parquet", index=False)
        halving.to_parquet(out / "capacity_halving.parquet", index=False)
    return frame


def turnover_tradeoff(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """F9.2: the turnover-penalized optimizer versus the full rebalance.

    The penalized optimizer trades only the names whose reconstructed alpha
    is above the cross-sectional median, holding the low-alpha half at its
    previous weight. This cuts the turnover that low-alpha churn carries
    while keeping the high-alpha trades. OUTPUT: the turnover cut and the
    ex-ante IR loss per rho.
    """
    root = Path(data_root)
    weights = pd.read_parquet(root / "portfolios" / "proportional.parquet")
    specific_returns = pd.read_parquet(
        root / "models" / "XS-v1" / "specific_returns.parquet"
    )
    sigma_map = specific_returns.groupby("ticker")["specific_return"].std(ddof=1)
    rows: list[dict[str, object]] = []
    for rho in RHOS:
        turnover_cuts: list[float] = []
        ir_losses: list[float] = []
        for seed in SEEDS:
            frame = weights.loc[(weights["rho"] == rho) & (weights["seed"] == seed)]
            if frame.empty:
                continue
            w_wide = frame.pivot_table(index="date", columns="ticker", values="weight")
            names = [t for t in w_wide.columns]
            sigma = sigma_map.reindex(names).fillna(sigma_map.median()).to_numpy()
            dates = w_wide.index
            prev = w_wide.iloc[0].reindex(names).fillna(0.0).to_numpy(dtype=float)
            for index in range(1, len(dates)):
                current = w_wide.iloc[index].reindex(names).fillna(0.0)
                current_np = current.to_numpy(dtype=float)
                delta = current_np - prev
                full_turnover = float(np.abs(delta).sum())
                if full_turnover <= 0:
                    prev = current_np
                    continue
                # the alpha is reconstructed from the proportional rule:
                # alpha_i proportional to w_i * sigma_i^2 before vol targeting
                alpha = current_np * sigma**2
                median_alpha = float(np.median(np.abs(alpha)))
                keep = np.abs(alpha) >= median_alpha
                penalized_delta = np.where(keep, delta, 0.0)
                penalized_turnover = float(np.abs(penalized_delta).sum())
                turnover_cuts.append(1.0 - penalized_turnover / full_turnover)
                w_penalized = prev + penalized_delta
                ir_full = float(np.sum(alpha * current_np))
                ir_penalized = float(np.sum(alpha * w_penalized))
                ir_losses.append(1.0 - ir_penalized / ir_full if ir_full > 0 else 0.0)
                prev = current_np
        rows.append(
            {
                "rho": rho,
                "turnover_cut": (
                    float(np.mean(turnover_cuts)) if turnover_cuts else float("nan")
                ),
                "ex_ante_ir_loss": (
                    float(np.mean(ir_losses)) if ir_losses else float("nan")
                ),
            }
        )
    frame = pd.DataFrame(rows)
    if store:
        (root / "costs").mkdir(parents=True, exist_ok=True)
        frame.to_parquet(root / "costs" / "turnover_tradeoff.parquet", index=False)
    return frame


def capacity_curve_phi(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """The capacity table in (rho, phi) on the corrected costs.

    The persistent proportional book's net Sharpe against AUM per rho and
    persistence phi at the central impact coefficient k = 0.5, with the
    halving AUM stored beside the gross Sharpe. phi 0 is the i.i.d. book,
    which reproduces the (rho, k = 0.5) column of the F9.1 table.
    """
    root = Path(data_root)
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    spread = spread_schedule(prices, root)
    adv = _adv_per_ticker(prices)
    weights = pd.read_parquet(root / "portfolios" / "persistent_proportional.parquet")
    specific_returns = pd.read_parquet(
        root / "models" / "XS-v1" / "specific_returns.parquet"
    )
    sigma_all = specific_returns.groupby("ticker")["specific_return"].std(ddof=1)
    rows: list[dict[str, object]] = []
    halving_rows: list[dict[str, object]] = []
    aum_grid = np.logspace(6, 10, 25)
    k = IMPACT_K
    for rho in RHOS:
        for phi in (0.0, 0.8, 0.95):
            net_by_aum: dict[float, float] = {}
            net_mean_by_aum: dict[float, float] = {}
            gross_sharpe = float("nan")
            for seed in SEEDS:
                frame = weights.loc[
                    (weights["rho"] == rho)
                    & (weights["phi"] == phi)
                    & (weights["seed"] == seed)
                ]
                if frame.empty:
                    continue
                w_wide = frame.pivot_table(
                    index="date", columns="ticker", values="weight"
                )
                gross = w_wide.abs().sum(axis=1)
                w_wide = w_wide.div(gross, axis=0)
                realized = _realized_returns(w_wide, root)
                gross_sharpe = float(
                    realized.mean() / realized.std(ddof=1) * np.sqrt(ANNUAL / HORIZON)
                    if realized.std(ddof=1) > 0
                    else float("nan")
                )
                names = [t for t in w_wide.columns]
                spread_map = spread.reindex(names).fillna(spread.median())
                adv_map = adv.reindex(names).fillna(adv.median())
                sigma_map = sigma_all.reindex(names).fillna(sigma_all.median())
                realized_dates = realized.index
                aligned = w_wide.reindex(realized_dates)
                for aum in aum_grid:
                    costs: list[float] = []
                    for index in range(1, len(realized_dates)):
                        current = (
                            aligned.iloc[index]
                            .reindex(names)
                            .fillna(0.0)
                            .to_numpy(float)
                        )
                        prev = (
                            aligned.iloc[index - 1]
                            .reindex(names)
                            .fillna(0.0)
                            .to_numpy(float)
                        )
                        delta = current - prev
                        costs.append(
                            _trade_cost(
                                delta,
                                spread_map.to_numpy(float),
                                sigma_map.to_numpy(float),
                                adv_map.to_numpy(float),
                                aum,
                                k,
                            )
                        )
                    net = realized.iloc[1:] - pd.Series(costs, index=realized.index[1:])
                    net_sharpe = float(
                        net.mean() / net.std(ddof=1) * np.sqrt(ANNUAL / HORIZON)
                        if net.std(ddof=1) > 0
                        else float("nan")
                    )
                    net_by_aum[aum] = net_by_aum.get(aum, 0.0) + net_sharpe
                    net_mean_by_aum[aum] = net_mean_by_aum.get(aum, 0.0) + float(
                        net.mean()
                    )
            for aum in aum_grid:
                net_sharpe = float(net_by_aum.get(aum, float("nan"))) / len(SEEDS)
                net_mean = float(net_mean_by_aum.get(aum, float("nan"))) / len(SEEDS)
                rows.append(
                    {
                        "rho": rho,
                        "phi": phi,
                        "aum": float(aum),
                        "gross_sharpe": gross_sharpe,
                        "net_sharpe": net_sharpe,
                        "net_mean": net_mean,
                    }
                )
            halving = float("nan")
            first_net = float(net_by_aum.get(float(aum_grid[0]), float("nan"))) / len(
                SEEDS
            )
            if (
                np.isfinite(gross_sharpe)
                and np.isfinite(first_net)
                and first_net > gross_sharpe / 2.0
            ):
                for aum in aum_grid:
                    net_sharpe = float(net_by_aum.get(aum, float("nan"))) / len(SEEDS)
                    if np.isfinite(net_sharpe) and net_sharpe <= gross_sharpe / 2.0:
                        halving = float(aum)
                        break
            halving_rows.append(
                {
                    "rho": rho,
                    "phi": phi,
                    "gross_sharpe": gross_sharpe,
                    "halving_aum": halving,
                }
            )
    frame = pd.DataFrame(rows)
    halving = pd.DataFrame(halving_rows)
    if store:
        out = root / "costs"
        out.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out / "capacity_phi.parquet", index=False)
        halving.to_parquet(out / "capacity_phi_halving.parquet", index=False)
    return frame


def spread_sensitivity(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """The halving AUM under the half and double spread schedule.

    The chosen schedule is an assumption, so the capacity is re-run with
    the schedule multiplied by 0.5 and by 2.0 and the halving AUM is
    stored at each multiplier, per rho, at the central impact coefficient
    k = 0.5. OUTPUT: rows (rho, multiplier, gross_sharpe, halving_aum).
    """
    root = Path(data_root)
    halving = pd.read_parquet(root / "costs" / "capacity_halving.parquet")
    rows: list[dict[str, object]] = []
    for rho in RHOS:
        base = halving[(halving["rho"] == rho) & (halving["k"] == IMPACT_K)]
        gross_sharpe = (
            float(base["gross_sharpe"].iloc[0]) if not base.empty else float("nan")
        )
        base_halving = (
            float(base["halving_aum"].iloc[0]) if not base.empty else float("nan")
        )
        for multiplier in (0.5, 1.0, 2.0):
            if multiplier == 1.0:
                halving_aum = base_halving
            else:
                frame = capacity_curve(root, store=False, spread_multiplier=multiplier)
                sub = frame[(frame["rho"] == rho) & (frame["k"] == IMPACT_K)]
                # the halving AUM is the first AUM where net Sharpe falls to
                # half of gross; recomputed here to match capacity_curve's
                # own stored companion frame
                halving_aum = float("nan")
                if not sub.empty:
                    aums = sub.sort_values("aum")
                    gross_sharpe = float(aums["gross_sharpe"].iloc[0])
                    first_net = float(aums["net_sharpe"].iloc[0])
                    above_half = (
                        np.isfinite(gross_sharpe)
                        and np.isfinite(first_net)
                        and first_net > gross_sharpe / 2.0
                    )
                    if above_half:
                        for _idx, row in aums.iterrows():
                            if (
                                np.isfinite(row["net_sharpe"])
                                and row["net_sharpe"] <= gross_sharpe / 2.0
                            ):
                                halving_aum = float(row["aum"])
                                break
            rows.append(
                {
                    "rho": rho,
                    "spread_multiplier": multiplier,
                    "gross_sharpe": gross_sharpe,
                    "halving_aum": halving_aum,
                }
            )
    frame = pd.DataFrame(rows)
    if store:
        out = root / "costs"
        out.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out / "capacity_spread_sensitivity.parquet", index=False)
    return frame


def run(data_root: Path = DATA_ROOT, store: bool = True) -> dict[str, pd.DataFrame]:
    """The full E9 pipeline: the probe, cost curves, capacity and trade-off."""
    probe = spread_probe(data_root, store=store)
    curves = cost_curves(data_root, store=store)
    capacity = capacity_curve(data_root, store=store)
    tradeoff = turnover_tradeoff(data_root, store=store)
    sensitivity = spread_sensitivity(data_root, store=store)
    capacity_phi = pd.DataFrame()
    persistent = Path(data_root) / "portfolios" / "persistent_proportional.parquet"
    if persistent.exists():
        capacity_phi = capacity_curve_phi(data_root, store=store)
    return {
        "spread_probe": probe,
        "cost_curves": curves,
        "capacity": capacity,
        "turnover_tradeoff": tradeoff,
        "spread_sensitivity": sensitivity,
        "capacity_phi": capacity_phi,
    }
