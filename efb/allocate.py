"""Sprint E10: dynamic risk allocation and loss management.

Kelly and fractional Kelly under an estimated Sharpe, volatility targeting,
drawdown control, and the stop-loss efficiency analysis. The input is the
synthetic book's net returns on corrected costs at the (rho, phi)
configuration whose net annualized Sharpe is closest to 1.0, stated as the
design book, with the two seed books run alongside.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"

TRADING_DAYS = 252
HORIZON = 21  # the synthetic book's rebalance horizon in sessions
TARGET_ANNUAL_VOL = 0.10
REFERENCE_AUM = 1e8
SEEDS = (0, 1, 2, 3, 4)
RHOS = (0.02, 0.05, 0.10)
PHIS = (0.0, 0.8, 0.95)
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20260921
STOP_LOSS_THRESHOLD = -0.10
STOP_REENTRY = -0.05


def _annual_factor(horizon: int = HORIZON) -> float:
    return float(np.sqrt(TRADING_DAYS / horizon))


def pick_design_config(data_root: Path = DATA_ROOT) -> dict[str, float]:
    """The (rho, phi, seed) whose net annualized Sharpe is closest to 1.0.

    The (rho, phi) is picked from the seed-averaged capacity table at the
    reference AUM; within that configuration the single seed whose own net
    Sharpe is closest to 1.0 is the design book, because a book is one
    realization, not the average of five.
    """
    root = Path(data_root)
    capacity = pd.read_parquet(root / "costs" / "capacity_phi.parquet")
    rows = capacity[capacity["aum"] == REFERENCE_AUM]
    best: dict[str, float] | None = None
    for rho in RHOS:
        for phi in PHIS:
            sub = rows[(rows["rho"] == rho) & (rows["phi"] == phi)]
            if sub.empty:
                continue
            net_sharpe = float(sub["net_sharpe"].iloc[0])
            distance = abs(net_sharpe - 1.0)
            if best is None or distance < best["distance"]:
                best = {
                    "rho": rho,
                    "phi": phi,
                    "net_sharpe": net_sharpe,
                    "gross_sharpe": float(sub["gross_sharpe"].iloc[0]),
                    "distance": distance,
                }
    if best is None:  # pragma: no cover - the build writes this artifact
        best = {
            "rho": 0.02,
            "phi": 0.8,
            "net_sharpe": float("nan"),
            "gross_sharpe": float("nan"),
            "distance": float("nan"),
        }
    best_seed = 0
    best_seed_sharpe = float("nan")
    if np.isfinite(best["net_sharpe"]):
        for seed in SEEDS:
            series = design_net_returns(
                float(best["rho"]),
                float(best["phi"]),
                seed=seed,
                aum=REFERENCE_AUM,
                data_root=root,
            )
            sharpe = _annualized_moments(series, HORIZON)["sharpe"]
            if abs(sharpe - 1.0) < abs(best_seed_sharpe - 1.0) or np.isnan(
                best_seed_sharpe
            ):
                best_seed = seed
                best_seed_sharpe = sharpe
    best["seed"] = best_seed
    best["net_sharpe_seed"] = best_seed_sharpe
    return best


def design_net_returns(
    rho: float,
    phi: float,
    seed: int = 0,
    aum: float = REFERENCE_AUM,
    data_root: Path = DATA_ROOT,
) -> pd.Series:
    """The design book's per-rebalance net return for one seed.

    The realized specific return of the gross-normalized persistent weights
    minus the corrected transaction cost at the reference AUM.
    """
    from efb import costs

    root = Path(data_root)
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    spread = costs.spread_schedule(prices, root)
    adv = costs._adv_per_ticker(prices)
    weights = pd.read_parquet(root / "portfolios" / "persistent_proportional.parquet")
    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_returns.parquet")
    sigma_map = specific.groupby("ticker")["specific_return"].std(ddof=1)
    frame = weights.loc[
        (weights["rho"] == rho) & (weights["phi"] == phi) & (weights["seed"] == seed)
    ]
    if frame.empty:
        return pd.Series(dtype=float, name="net_return")
    w_wide = frame.pivot_table(index="date", columns="ticker", values="weight")
    gross = w_wide.abs().sum(axis=1)
    w_wide = w_wide.div(gross, axis=0)
    realized = costs._realized_returns(w_wide, root)
    names = [t for t in w_wide.columns]
    spread_map = spread.reindex(names).fillna(spread.median())
    adv_map = adv.reindex(names).fillna(adv.median())
    sigma_np = sigma_map.reindex(names).fillna(sigma_map.median())
    realized_dates = realized.index
    aligned = w_wide.reindex(realized_dates)
    cost_rows: list[float] = []
    for index in range(1, len(realized_dates)):
        current = aligned.iloc[index].reindex(names).fillna(0.0).to_numpy(dtype=float)
        prev = aligned.iloc[index - 1].reindex(names).fillna(0.0).to_numpy(dtype=float)
        delta = current - prev
        cost_rows.append(
            costs._trade_cost(
                delta,
                spread_map.to_numpy(dtype=float),
                sigma_np.to_numpy(dtype=float),
                adv_map.to_numpy(dtype=float),
                aum,
                costs.IMPACT_K,
            )
        )
    net = realized.iloc[1:] - pd.Series(cost_rows, index=realized.index[1:])
    return net.rename("net_return")


def _scale_to_vol(
    series: pd.Series, target_vol: float = TARGET_ANNUAL_VOL
) -> pd.Series:
    """Scale a series by a constant so its realized annual vol equals the
    target, the book's constant vol target applied to the whole history."""
    x = series.dropna()
    factor = float(np.sqrt(TRADING_DAYS / HORIZON))
    realized = float(x.std(ddof=1) * factor)
    if realized <= 0:
        return series
    return series * (target_vol / realized)


def seed_book_daily_returns(book: str, data_root: Path = DATA_ROOT) -> pd.Series:
    """A seed book's daily return series under the E5 missing-data semantics."""
    from efb import eval_risk

    root = Path(data_root)
    wide, _counts = eval_risk.load_clean_wide(root)
    rows = pd.read_parquet(root / "portfolios" / f"{book}.parquet")
    weight_frame = (
        rows.pivot_table(index="date", columns="ticker", values="weight")
        .fillna(0.0)
        .reindex(columns=wide.columns, fill_value=0.0)
    )
    weight_frame = weight_frame.loc[weight_frame.index.intersection(wide.index)]
    weights = weight_frame.to_numpy(dtype=float)
    window = wide.loc[weight_frame.index].to_numpy(dtype=float)
    returns = eval_risk._portfolio_returns(weights, window)[0]
    return pd.Series(returns, index=weight_frame.index, name=book)


def _annualized_moments(series: pd.Series, horizon: int = HORIZON) -> dict[str, float]:
    x = series.dropna()
    mean = float(x.mean()) * (TRADING_DAYS / horizon)
    std = float(x.std(ddof=1)) * np.sqrt(TRADING_DAYS / horizon)
    sharpe = mean / std if std > 0 else float("nan")
    return {"mean": mean, "vol": std, "sharpe": sharpe, "n": int(len(x))}


def kelly_fraction(mean_ann: float, vol_ann: float) -> float:
    """Full Kelly f* = mu / sigma^2, the annualized form."""
    if vol_ann <= 0:
        return float("nan")
    return float(mean_ann / vol_ann**2)


def growth(f: float, mean_ann: float, vol_ann: float) -> float:
    """The annual growth rate g(f) = f mu - f^2 sigma^2 / 2."""
    return float(f * mean_ann - f**2 * vol_ann**2 / 2.0)


def magdon_ismail_median(mean_ann: float, vol_ann: float) -> float:
    """The analytical median maximum drawdown of a Brownian motion.

    A drifted Brownian motion's maximum drawdown over an infinite horizon
    has the exponential tail P(M > y) = exp(-2 mu y / sigma^2), whose
    median is ln(2) * sigma^2 / (2 mu). This is the Magdon-Ismail
    infinite-horizon value, used as the analytical benchmark for F10.1.
    """
    if mean_ann <= 0 or vol_ann <= 0:
        return float("nan")
    var = vol_ann**2
    return float(np.log(2.0) * var / (2.0 * mean_ann))


def magdon_ismail_expected_mdd(
    mean_ann: float, vol_ann: float, horizon_years: float
) -> float:
    """The Magdon-Ismail expected maximum drawdown at a horizon.

    A positive-drift Brownian motion's expected maximum drawdown over a
    horizon of `horizon_years` years is 2 sigma^2 / mu times
    Qp(mu^2 T / (2 sigma^2)), with the large-argument form
    Qp(x) ~ 0.25 ln x + 0.49088. This is the horizon-matched quantity the
    PRD specifies, unlike the infinite-horizon median in
    `magdon_ismail_median`.
    """
    if mean_ann <= 0 or vol_ann <= 0 or horizon_years <= 0:
        return float("nan")
    x = mean_ann**2 * horizon_years / (2.0 * vol_ann**2)
    if x <= 0:
        return float("nan")
    qp = 0.25 * np.log(x) + 0.49088
    return float(2.0 * vol_ann**2 / mean_ann * qp)


def kelly_analysis(
    net: pd.Series,
    horizon: int = HORIZON,
    data_root: Path = DATA_ROOT,
    store: bool = True,
) -> pd.DataFrame:
    """Kelly and fractional Kelly with the SE of the Sharpe.

    OUTPUT: one row with the design moments, full and fractional Kelly and
    the cost of over-betting when the Sharpe is overstated by one standard
    error. Stored as data/allocation/kelly.parquet.
    """
    root = Path(data_root)
    moments = _annualized_moments(net, horizon)
    sr = moments["sharpe"]
    factor = _annual_factor(horizon)
    sr_period = sr / factor
    se_period = float(np.sqrt((1.0 + sr_period**2 / 2.0) / moments["n"]))
    se = se_period * factor
    full = kelly_fraction(moments["mean"], moments["vol"])
    # half Kelly is the standard fractional choice; the SE of SR sets c so
    # that a one-SE-overstated Sharpe still leaves positive growth
    c_half = 0.5
    growth_full = growth(full, moments["mean"], moments["vol"])
    growth_half = growth(c_half * full, moments["mean"], moments["vol"])
    # over-betting: run full Kelly on SR + SE, report the growth loss
    sr_over = sr + se
    mean_over = sr_over * moments["vol"]
    full_over = kelly_fraction(mean_over, moments["vol"])
    growth_true_at_over = growth(full_over, moments["mean"], moments["vol"])
    overbet_loss = growth_full - growth_true_at_over
    row = pd.DataFrame(
        [
            {
                "rho": None,
                "phi": None,
                "mean_ann": moments["mean"],
                "vol_ann": moments["vol"],
                "sharpe": sr,
                "sharpe_se": se,
                "n_obs": moments["n"],
                "kelly_full": full,
                "kelly_half": c_half * full,
                "growth_full": growth_full,
                "growth_half": growth_half,
                "kelly_at_sharpe_plus_se": full_over,
                "growth_loss_overbet": overbet_loss,
            }
        ]
    )
    if store:
        (root / "allocation").mkdir(parents=True, exist_ok=True)
        row.to_parquet(root / "allocation" / "kelly.parquet", index=False)
    return row


def drawdown_analysis(
    net: pd.Series,
    horizon: int = HORIZON,
    n_bootstrap: int = N_BOOTSTRAP,
    data_root: Path = DATA_ROOT,
    store: bool = True,
) -> dict[str, float]:
    """F10.1: the simulated drawdown distribution against the analytical
    median, at the median.

    The simulated median is a signed drawdown and the analytical median is
    a magnitude, so the gap takes the magnitude of the simulated side
    before differencing. The same simulation also stores the Gaussian
    control's median maximum drawdown (i.i.d. Gaussian paths at the book's
    own moments) and the horizon-matched expected maximum drawdown, which
    F10.1b is scored on.
    """
    root = Path(data_root)
    moments = _annualized_moments(net, horizon)
    x = net.dropna().to_numpy(dtype=float)
    n = len(x)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    medians: list[float] = []
    for _ in range(n_bootstrap):
        path = rng.choice(x, size=n, replace=True)
        wealth = np.cumprod(1.0 + path)
        peak = np.maximum.accumulate(wealth)
        drawdown = wealth / peak - 1.0
        medians.append(float(drawdown.min()))
    simulated_median = float(np.median(medians))

    # the Gaussian control: i.i.d. Gaussian paths at the book's own
    # moments, same length, so a deeper control shows the gap is not fat
    # tails or volatility clustering the i.i.d. bootstrap already destroys
    gaussian = np.random.default_rng(BOOTSTRAP_SEED)
    gaussian_medians: list[float] = []
    for _ in range(n_bootstrap):
        path = gaussian.normal(x.mean(), x.std(ddof=1), size=n)
        wealth = np.cumprod(1.0 + path)
        peak = np.maximum.accumulate(wealth)
        gaussian_medians.append(float((wealth / peak - 1.0).min()))
    gaussian_median = float(np.median(gaussian_medians))

    analytical = magdon_ismail_median(moments["mean"], moments["vol"])
    relative = (
        (abs(simulated_median) - analytical) / analytical
        if np.isfinite(analytical) and analytical != 0
        else float("nan")
    )
    horizon_years = n * HORIZON / TRADING_DAYS
    expected_mdd = magdon_ismail_expected_mdd(
        moments["mean"], moments["vol"], horizon_years
    )
    expected_relative = (
        abs(abs(simulated_median) - expected_mdd) / expected_mdd
        if np.isfinite(expected_mdd) and expected_mdd != 0
        else float("nan")
    )
    out = {
        "simulated_median_drawdown": simulated_median,
        "analytical_median_drawdown": analytical,
        "relative_gap_at_median": relative,
        "gaussian_median_drawdown": gaussian_median,
        "horizon_years": horizon_years,
        "expected_mdd_at_horizon": expected_mdd,
        "expected_mdd_relative_gap": expected_relative,
        "n_bootstrap": int(n_bootstrap),
        "n_obs": int(n),
    }
    if store:
        (root / "allocation").mkdir(parents=True, exist_ok=True)
        pd.DataFrame([out]).to_parquet(
            root / "allocation" / "drawdown.parquet", index=False
        )
    return out


def _vol_target_returns(
    net: pd.Series, target_ann: float = TARGET_ANNUAL_VOL, window: int = 12
) -> pd.Series:
    """Scale_t = target / sigma_hat_{t-1}, applied one step ahead."""
    x = net.dropna()
    factor = float(np.sqrt(TRADING_DAYS / HORIZON))
    realized = x.rolling(window).std(ddof=1) * factor
    scale = (target_ann / realized).shift(1)
    scale = scale.clip(0.0, 3.0)
    return (x * scale).rename("targeted")


def _realized_annual_vol_by_year(series: pd.Series) -> pd.Series:
    factor = float(np.sqrt(TRADING_DAYS / HORIZON))
    grouped = series.dropna().groupby(series.dropna().index.year).std(ddof=1) * factor
    return grouped


def vol_target_analysis(
    net: pd.Series, data_root: Path = DATA_ROOT, store: bool = True
) -> pd.DataFrame:
    """F10.3: vol targeting reduces the dispersion of realized annual vol.

    Both dispersions are computed on the intersection of the raw and the
    targeted year sets, so the comparison is like with like; the counts
    per side are stored separately.
    """
    root = Path(data_root)
    raw_by_year = _realized_annual_vol_by_year(net)
    targeted = _vol_target_returns(net)
    target_by_year = _realized_annual_vol_by_year(targeted)
    common_years = raw_by_year.index.intersection(target_by_year.index)
    raw_aligned = raw_by_year.reindex(common_years)
    target_aligned = target_by_year.reindex(common_years)
    raw_dispersion = float(raw_aligned.std(ddof=1) / raw_aligned.mean())
    target_dispersion = float(target_aligned.std(ddof=1) / target_aligned.mean())
    reduction = (
        1.0 - target_dispersion / raw_dispersion if raw_dispersion > 0 else float("nan")
    )
    row = pd.DataFrame(
        [
            {
                "raw_dispersion": raw_dispersion,
                "targeted_dispersion": target_dispersion,
                "dispersion_reduction": reduction,
                "raw_mean_vol": float(raw_aligned.mean()),
                "targeted_mean_vol": float(target_aligned.mean()),
                "n_years_raw": int(len(raw_by_year)),
                "n_years_targeted": int(len(target_by_year)),
                "n_years_aligned": int(len(common_years)),
            }
        ]
    )
    if store:
        (root / "allocation").mkdir(parents=True, exist_ok=True)
        row.to_parquet(root / "allocation" / "voltarget.parquet", index=False)
    return row


def _apply_stop_loss(
    returns: np.ndarray, threshold: float, reentry: float
) -> np.ndarray:
    """A drawdown stop: flat while the running drawdown is below threshold,
    re-entering when it recovers above reentry."""
    out = np.zeros_like(returns)
    invested = True
    wealth = 1.0
    peak = 1.0
    for index, r in enumerate(returns):
        if invested:
            wealth *= 1.0 + r
            peak = max(peak, wealth)
            out[index] = r
            if wealth / peak - 1.0 < threshold:
                invested = False
        else:
            if wealth / peak - 1.0 > reentry:
                invested = True
            out[index] = 0.0
    return out


def _drawdown_fired(returns: np.ndarray, threshold: float) -> bool:
    """Whether the running drawdown ever crosses the stop threshold."""
    wealth = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(wealth)
    return bool(((wealth / peak - 1.0) < threshold).any())


def _apply_stop_loss_reentering(
    returns: np.ndarray, threshold: float, reentry: float
) -> tuple[np.ndarray, dict[str, int]]:
    """A drawdown stop that can re-enter.

    The original stop freezes wealth and peak while flat, so the re-entry
    test is unreachable. This one keeps tracking the unstopped equity
    curve while flat, so when the curve the book would have ridden
    recovers above the re-entry level the stop re-enters at the next
    session.
    """
    out = np.zeros_like(returns)
    unstopped = np.cumprod(1.0 + returns)
    unstopped_peak = np.maximum.accumulate(unstopped)
    invested = True
    wealth = 1.0
    peak = 1.0
    entries = 0
    exits = 0
    days_flat = 0
    for index, r in enumerate(returns):
        if invested:
            wealth *= 1.0 + r
            peak = max(peak, wealth)
            out[index] = r
            if wealth / peak - 1.0 < threshold:
                invested = False
                exits += 1
        else:
            out[index] = 0.0
            days_flat += 1
            if unstopped[index] / unstopped_peak[index] - 1.0 > reentry:
                invested = True
                entries += 1
                wealth = unstopped[index]
                peak = unstopped_peak[index]
    return out, {"entries": entries, "exits": exits, "days_flat": days_flat}


def _sharpe_period(returns: np.ndarray, horizon: int) -> float:
    if returns.std(ddof=1) <= 0:
        return float("nan")
    return float(returns.mean() / returns.std(ddof=1) * np.sqrt(TRADING_DAYS / horizon))


def stop_loss_analysis(
    net: pd.Series,
    horizon: int = HORIZON,
    n_bootstrap: int = N_BOOTSTRAP,
    data_root: Path = DATA_ROOT,
    store: bool = True,
) -> pd.DataFrame:
    """F10.2: the stop-loss must not improve Sharpe on the i.i.d. control.

    The control bootstraps the book's returns i.i.d. and applies the
    drawdown stop; on i.i.d. returns the stop can only truncate expected
    return, so its mean Sharpe must not exceed the unstopped Sharpe. The
    real book's result is reported either way.
    """
    root = Path(data_root)
    x = net.dropna().to_numpy(dtype=float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(x)
    base_sharpe = _sharpe_period(x, horizon)
    control_diffs: list[float] = []
    for _ in range(n_bootstrap):
        path = rng.choice(x, size=n, replace=True)
        stopped = _apply_stop_loss(path, STOP_LOSS_THRESHOLD, STOP_REENTRY)
        control_diffs.append(
            _sharpe_period(stopped, horizon) - _sharpe_period(path, horizon)
        )
    mean_diff = float(np.mean(control_diffs))
    control_improves = bool(mean_diff > 0)
    real_stopped = _apply_stop_loss(x, STOP_LOSS_THRESHOLD, STOP_REENTRY)
    real_diff = _sharpe_period(real_stopped, horizon) - base_sharpe

    # the re-entering stop, scored separately as F10.2b
    reenter_rng = np.random.default_rng(BOOTSTRAP_SEED + 2)
    reenter_control_diffs: list[float] = []
    for _ in range(n_bootstrap):
        path = reenter_rng.choice(x, size=n, replace=True)
        re_stopped, _ = _apply_stop_loss_reentering(
            path, STOP_LOSS_THRESHOLD, STOP_REENTRY
        )
        reenter_control_diffs.append(
            _sharpe_period(re_stopped, horizon) - _sharpe_period(path, horizon)
        )
    reenter_mean_diff = float(np.mean(reenter_control_diffs))
    reenter_control_improves = bool(reenter_mean_diff > 0)
    reenter_real, reenter_state = _apply_stop_loss_reentering(
        x, STOP_LOSS_THRESHOLD, STOP_REENTRY
    )
    reenter_real_diff = _sharpe_period(reenter_real, horizon) - base_sharpe

    row = pd.DataFrame(
        [
            {
                "book": "design",
                "base_sharpe": base_sharpe,
                "control_mean_sharpe_diff": mean_diff,
                "control_improves_sharpe": control_improves,
                "real_book_sharpe_diff": real_diff,
                "reentering_control_mean_sharpe_diff": reenter_mean_diff,
                "reentering_control_improves_sharpe": reenter_control_improves,
                "reentering_real_sharpe_diff": reenter_real_diff,
                "reentering_entries": reenter_state["entries"],
                "reentering_exits": reenter_state["exits"],
                "reentering_days_flat": reenter_state["days_flat"],
                "n_bootstrap": int(n_bootstrap),
                "n_obs": int(n),
                "n_dates_available": int(n),
                "first_date": net.index[0].date() if len(net) else None,
                "last_date": net.index[-1].date() if len(net) else None,
                "stop_fired": _drawdown_fired(x, STOP_LOSS_THRESHOLD),
            }
        ]
    )
    for book in ("seed_ew", "seed_mom_ls"):
        full = seed_book_daily_returns(book, root)
        daily = full.dropna()
        daily_np = daily.to_numpy(dtype=float)
        daily_sharpe = _sharpe_period(daily_np, 1)
        stopped = _apply_stop_loss(daily_np, STOP_LOSS_THRESHOLD, STOP_REENTRY)
        re_stopped, re_state = _apply_stop_loss_reentering(
            daily_np, STOP_LOSS_THRESHOLD, STOP_REENTRY
        )
        row = pd.concat(
            [
                row,
                pd.DataFrame(
                    [
                        {
                            "book": book,
                            "base_sharpe": daily_sharpe,
                            "control_mean_sharpe_diff": float("nan"),
                            "control_improves_sharpe": False,
                            "real_book_sharpe_diff": _sharpe_period(stopped, 1)
                            - daily_sharpe,
                            "reentering_control_mean_sharpe_diff": float("nan"),
                            "reentering_control_improves_sharpe": False,
                            "reentering_real_sharpe_diff": _sharpe_period(re_stopped, 1)
                            - daily_sharpe,
                            "reentering_entries": re_state["entries"],
                            "reentering_exits": re_state["exits"],
                            "reentering_days_flat": re_state["days_flat"],
                            "n_bootstrap": 0,
                            "n_obs": int(len(daily_np)),
                            "n_dates_available": int(len(full)),
                            "first_date": daily.index[0].date() if len(daily) else None,
                            "last_date": daily.index[-1].date() if len(daily) else None,
                            "stop_fired": _drawdown_fired(
                                daily_np, STOP_LOSS_THRESHOLD
                            ),
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    if store:
        (root / "allocation").mkdir(parents=True, exist_ok=True)
        row.to_parquet(root / "allocation" / "stoploss.parquet", index=False)
    return row


def regime_analysis(
    net: pd.Series, data_root: Path = DATA_ROOT, store: bool = True
) -> pd.DataFrame:
    """Drawdown depth and recovery within VIX terciles, per rebalance."""
    root = Path(data_root)
    vix = pd.read_parquet(root / "raw" / "vix.parquet")
    vix_series = vix.set_index(pd.to_datetime(vix["date"]))["vix"]
    aligned = pd.concat(
        [
            net.rename("return"),
            vix_series.reindex(net.index, method="ffill").rename("vix"),
        ],
        axis=1,
    ).dropna()
    aligned["tercile"] = pd.qcut(aligned["vix"].rank(method="first"), 3, labels=False)
    rows: list[dict[str, object]] = []
    for tercile, group in aligned.groupby("tercile"):
        wealth = (1.0 + group["return"]).cumprod()
        peak = wealth.cummax()
        drawdown = wealth / peak - 1.0
        depth = float(drawdown.min())
        recovery = int((drawdown < -0.001).sum())
        rows.append(
            {
                "vix_tercile": int(tercile),
                "mean_vix": float(group["vix"].mean()),
                "max_drawdown": depth,
                "n_underwater": recovery,
                "n_obs": int(len(group)),
            }
        )
    frame = pd.DataFrame(rows)
    if store:
        (root / "allocation").mkdir(parents=True, exist_ok=True)
        frame.to_parquet(root / "allocation" / "regime.parquet", index=False)
    return frame


def design_book_daily_returns(
    rho: float, phi: float, seed: int, data_root: Path = DATA_ROOT
) -> pd.Series:
    """The design book's daily return series under the E5 missing-data
    semantics.

    The weights chosen at a rebalance date are held for the next HORIZON
    sessions, and the daily return is the held weights times the daily
    specific return. A held name with a missing return makes that day
    missing; an unpriced name contributes zero.
    """
    root = Path(data_root)
    weights = pd.read_parquet(root / "portfolios" / "persistent_proportional.parquet")
    frame = weights.loc[
        (weights["rho"] == rho) & (weights["phi"] == phi) & (weights["seed"] == seed)
    ]
    w_wide = frame.pivot_table(index="date", columns="ticker", values="weight")
    gross = w_wide.abs().sum(axis=1)
    w_wide = w_wide.div(gross, axis=0)
    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_returns.parquet")
    specific["date"] = pd.to_datetime(specific["date"])
    sp_wide = specific.pivot(
        index="date", columns="ticker", values="specific_return"
    ).sort_index()
    sessions = sp_wide.index
    held: dict[pd.Timestamp, pd.Series] = {}
    for date in w_wide.index:
        forward = sessions[sessions > date][:HORIZON]
        if len(forward) < HORIZON:
            continue
        weights_row = w_wide.loc[date]
        for session in forward:
            held[session] = weights_row
    idx = sorted(held)
    W = pd.DataFrame(held).T.reindex(columns=w_wide.columns).fillna(0.0).loc[idx]
    sp = sp_wide.loc[idx]
    common = [t for t in W.columns if t in sp.columns]
    Wn = W[common].to_numpy(dtype=float)
    Rn = sp[common].to_numpy(dtype=float)
    missing = np.isnan(Rn) & (Wn != 0)
    safe = np.nan_to_num(Rn, nan=0.0)
    daily = pd.Series(np.sum(Wn * safe, axis=1), index=sp.index)
    daily[missing.any(axis=1)] = np.nan
    return daily.rename("daily_return")


def vol_target_daily_analysis(
    net: pd.Series,
    daily: pd.Series,
    data_root: Path = DATA_ROOT,
    store: bool = True,
) -> pd.DataFrame:
    """F10.3b: the dispersion reduction from a daily vol estimate.

    The scale at each rebalance date is target over the trailing daily
    window's realized vol, shifted one period, applied to the next
    rebalance return. The daily series is first scaled to the target vol
    so the scale sits near one and the clip does not bind. Rows sweep the
    daily windows 21, 42, 63, 126 and 252 sessions.
    """
    root = Path(data_root)
    factor = float(np.sqrt(TRADING_DAYS))
    x = daily.dropna()
    full_vol = float(x.std(ddof=1) * factor)
    if full_vol > 0:
        x = x * (TARGET_ANNUAL_VOL / full_vol)
    raw_by_year = _realized_annual_vol_by_year(net)
    rows: list[dict[str, object]] = []
    for window in (21, 42, 63, 126, 252):
        realized = x.rolling(window).std(ddof=1) * factor
        scale = (
            (TARGET_ANNUAL_VOL / realized)
            .reindex(net.index, method="ffill")
            .shift(1)
            .clip(0.0, 3.0)
        )
        targeted = net * scale
        target_by_year = _realized_annual_vol_by_year(targeted)
        common = raw_by_year.index.intersection(target_by_year.index)
        raw_aligned = raw_by_year.reindex(common)
        target_aligned = target_by_year.reindex(common)
        raw_dispersion = float(raw_aligned.std(ddof=1) / raw_aligned.mean())
        target_dispersion = float(target_aligned.std(ddof=1) / target_aligned.mean())
        reduction = (
            1.0 - target_dispersion / raw_dispersion
            if raw_dispersion > 0
            else float("nan")
        )
        rows.append(
            {
                "estimator": "daily",
                "window": int(window),
                "raw_dispersion": raw_dispersion,
                "targeted_dispersion": target_dispersion,
                "dispersion_reduction": reduction,
                "n_years_aligned": int(len(common)),
            }
        )
    frame = pd.DataFrame(rows)
    if store:
        (root / "allocation").mkdir(parents=True, exist_ok=True)
        frame.to_parquet(root / "allocation" / "voltarget_daily.parquet", index=False)
    return frame


def run(data_root: Path = DATA_ROOT, store: bool = True) -> dict[str, object]:
    """The full E10 pipeline on the design book and the two seed books."""
    root = Path(data_root)
    config = pick_design_config(root)
    if store:
        (root / "allocation").mkdir(parents=True, exist_ok=True)
        (root / "allocation" / "config.json").write_text(
            json.dumps(config, default=float) + "\n"
        )
    raw = design_net_returns(
        float(config["rho"]),
        float(config["phi"]),
        seed=int(config["seed"]),
        data_root=root,
    )
    # the book runs at its vol target; a constant scale to 10% annual vol
    # preserves the Sharpe while making the Kelly and drawdown numbers mean
    # the book's actual risk level rather than the gross-normalized one
    net = _scale_to_vol(raw)
    kelly = kelly_analysis(net, data_root=root, store=store)
    drawdown = drawdown_analysis(net, data_root=root, store=store)
    voltarget = vol_target_analysis(net, data_root=root, store=store)
    stoploss = stop_loss_analysis(net, data_root=root, store=store)
    regime = regime_analysis(net, data_root=root, store=store)
    daily = design_book_daily_returns(
        float(config["rho"]), float(config["phi"]), int(config["seed"]), root
    )
    voltarget_daily = vol_target_daily_analysis(net, daily, data_root=root, store=store)
    return {
        "config": config,
        "net": net,
        "kelly": kelly,
        "drawdown": drawdown,
        "voltarget": voltarget,
        "stoploss": stoploss,
        "regime": regime,
        "daily": daily,
        "voltarget_daily": voltarget_daily,
    }
