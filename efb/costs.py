"""Sprint E9: transaction costs and capacity.

The alpha is the E8 synthetic alpha with a known IC, labeled as such,
because no real signal passed RG-Signal. Capacity is a function of the
assumed IC, so the capacity curve and the halving AUM are reported per rho.
Cost parameters that free data cannot pin are stated with their source and
their uncertainty, never as a clean point estimate.
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


def corwin_schultz(prices: pd.DataFrame, window: int = CORWIN_WINDOW) -> pd.Series:
    """The Corwin-Schultz (2012) high-low spread estimator per ticker.

    INPUT: the prices frame (date, ticker) with high, low, close.
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
            spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
            if np.isfinite(spread) and 0 < spread < 1:
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


def cost_curves(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """The half-spread and ADV by size decile, and the spread-size correlation.

    OUTPUT: one row per size decile with the mean half-spread, market cap,
    ADV and name count, plus the Spearman correlation between half-spread
    and size rank that F9.3 scores.
    """
    root = Path(data_root)
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    spread = corwin_schultz(prices)
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
    """The per-rebalance realized specific return of a weight series."""
    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_returns.parquet")
    specific["date"] = pd.to_datetime(specific["date"])
    specific_wide = specific.pivot(
        index="date", columns="ticker", values="specific_return"
    )
    values: list[float] = []
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
    return pd.Series(values)


def capacity_curve(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """The net Sharpe against AUM for the proportional seed book, per rho and k.

    OUTPUT: rows (rho, k, aum, gross_sharpe, net_sharpe) over an AUM grid,
    plus the halving AUM per (rho, k) in a companion frame.
    """
    root = Path(data_root)
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    spread = corwin_schultz(prices)
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
                dates = w_wide.index
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
                for aum in aum_grid:
                    costs: list[float] = []
                    prev = w_wide.iloc[0].fillna(0.0).to_numpy(dtype=float)
                    for index in range(1, len(dates)):
                        current = w_wide.iloc[index].reindex(names).fillna(0.0)
                        current_np = current.to_numpy(dtype=float)
                        prev_np = pd.Series(prev, index=names).reindex(names).to_numpy()
                        delta = current_np - prev_np
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
                        prev = current_np
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


def run(data_root: Path = DATA_ROOT, store: bool = True) -> dict[str, pd.DataFrame]:
    """The full E9 pipeline: cost curves, capacity and the trade-off."""
    curves = cost_curves(data_root, store=store)
    capacity = capacity_curve(data_root, store=store)
    tradeoff = turnover_tradeoff(data_root, store=store)
    return {"cost_curves": curves, "capacity": capacity, "turnover_tradeoff": tradeoff}
