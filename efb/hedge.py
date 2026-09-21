"""Sprint E6: the hedging toolkit.

Beta hedges, factor-neutral hedges through the FMPs, minimum-variance hedges
with a restricted instrument set, partial hedges, and the cost of each. The
champion is provisional (F5.1 failed), so every headline result is computed
under the champion Sigma (XS-v1) and under the alternative (XS-v2) and the
difference is stored: that sensitivity is a number in this sprint, never an
assumption. Efficacy is measured on realized factor P&L and realized beta,
not on in-model exposures alone.

The missing-data semantics from E5's 0 times NaN defect apply everywhere: a
missing weight or exposure is never silently zeroed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from efb import eval_risk, race

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"

INSTRUMENTS = (
    "SPY",
    "IWM",
    "QQQ",
    "XLK",
    "XLF",
    "XLE",
    "XLI",
    "XLP",
    "XLU",
    "XLV",
    "XLY",
    "XLB",
    "XLRE",
    "XLC",
)

# E9 provisional constants, stated once with their source: replaced by the E9
# cost model when it exists.
COST_PER_TURNOVER = 5e-4  # 5 bps per unit of hedge turnover
BORROW_RATE = 0.02  # 2 percent per year on short notional
COST_PARAMETERS = {
    "cost_per_turnover": COST_PER_TURNOVER,
    "borrow_rate_per_year": BORROW_RATE,
    "source": "E9 provisional constants, replaced by the E9 transaction cost model",
}

FACTOR_WINDOW = 504
BETA_WINDOW = 252
MIN_FACTOR_HISTORY = 126


def fetch_etf_prices(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """The instrument set's adjusted closes, fetched once and stored.

    The E1 rules apply: missing prices stay NaN, never imputed, and coverage is
    reported per instrument.
    """
    import yfinance as yf

    root = Path(data_root)
    frame = yf.download(
        list(INSTRUMENTS),
        start="2009-12-15",
        end="2026-09-12",
        progress=False,
        auto_adjust=False,
    )
    close = frame["Adj Close"]
    if isinstance(close.columns, pd.MultiIndex):
        close = close.droplevel(0, axis=1)
    long = close.stack(future_stack=True).rename("adj_close").reset_index()
    long.columns = ["date", "ticker", "adj_close"]
    long["date"] = pd.to_datetime(long["date"]).dt.normalize()
    if store:
        (root / "raw").mkdir(parents=True, exist_ok=True)
        long.to_parquet(root / "raw" / "etf_prices.parquet", index=False)
    return long


def load_etf_returns(data_root: Path = DATA_ROOT) -> pd.DataFrame:
    """Wide instrument returns, dates down, instruments across, NaN kept."""
    root = Path(data_root)
    frame = pd.read_parquet(root / "raw" / "etf_prices.parquet")
    wide = frame.pivot(index="date", columns="ticker", values="adj_close")
    wide = wide.reindex(columns=list(INSTRUMENTS))
    returns = wide.pct_change(fill_method=None)
    returns = returns.loc[returns.index >= pd.Timestamp("2010-12-15")]
    return returns


def _seed_book_returns(
    book: str, wide: pd.DataFrame, portfolios: pd.DataFrame
) -> pd.Series:
    """The seed book's daily returns under the E5 missing-data semantics."""
    rows = portfolios.loc[portfolios["portfolio"] == book].sort_values("date")
    weight_frame = (
        rows.pivot_table(index="date", columns="ticker", values="weight")
        .fillna(0.0)
        .reindex(columns=wide.columns, fill_value=0.0)
    )
    weight_frame = weight_frame.loc[weight_frame.index.intersection(wide.index)]
    weights = weight_frame.to_numpy(dtype=float)
    window = wide.loc[weight_frame.index].to_numpy(dtype=float)
    returns = eval_risk._portfolio_returns(weights, window)[0]
    return pd.Series(returns, index=weight_frame.index)


def beta_hedge(
    book_returns: pd.Series, spy_returns: pd.Series, window: int = BETA_WINDOW
) -> float:
    """h = -beta_p: the one-instrument case. INPUT: book and SPY returns."""
    joined = pd.concat([book_returns, spy_returns], axis=1, join="inner").dropna()
    if len(joined) < 60:
        return float("nan")
    values = joined.to_numpy(dtype=float)
    covariance = np.cov(values[-window:], rowvar=False, ddof=1)
    variance = float(covariance[1, 1])
    if variance <= 0 or not np.isfinite(variance):
        return float("nan")
    return float(-covariance[0, 1] / variance)


def partial_hedge(h: float, c: float) -> float:
    """h = -c beta_p for c in [0, 1]."""
    if not 0.0 <= c <= 1.0:
        raise ValueError("the partial hedge fraction c must be inside [0, 1]")
    return float(h * c)


def fmp_hedge(
    exposures: np.ndarray,
    fmp_frame: pd.DataFrame,
    factor_names: list[str],
) -> tuple[np.ndarray, list[str], int]:
    """The FMP hedge: subtract sum_k x_k FMP_k.

    INPUT: the book's factor exposures x = X'w and the FMP weights at the
    rebalance date. OUTPUT: the hedge weight vector over the FMP frame's own
    ticker order, that order, and its name count. Exact in-model and
    expensive in names, which is why the name count is returned rather than
    hidden.
    """
    wide = fmp_frame.pivot_table(index="ticker", columns="factor", values="weight")
    wide = wide.reindex(columns=factor_names).fillna(0.0)
    tickers = list(wide.index)
    hedge = -(wide.to_numpy(dtype=float) @ exposures)
    held = np.abs(hedge) > 1e-12
    return hedge, tickers, int(held.sum())


def fmp_hedge_exact(
    design: np.ndarray,
    exposures: np.ndarray,
) -> tuple[np.ndarray, int]:
    """The exact in-model FMP hedge: h = -X (X'X)^-1 x.

    The FMPs are the columns of X (X'X)^-1, so subtracting x_k of each drives
    the post-hedge exposure X'(w + h) to zero by construction. Exact in model
    and unusable in practice: every name in the design is traded, which is
    why the name count is returned. The as-stored quarterly capped FMPs keep
    their cap drift, which is basis risk and is stored beside this.
    """
    factor_loadings = np.linalg.solve(design.T @ design, exposures)
    hedge = -(design @ factor_loadings)
    held = np.abs(hedge) > 1e-12
    return hedge, int(held.sum())


def min_variance_hedge(
    sigma_hh: np.ndarray,
    sigma_hw: np.ndarray,
) -> np.ndarray:
    """h* = -(H' Sigma H)^-1 H' Sigma w.

    INPUT: the instrument-block covariance and the instrument-book cross
    covariance. OUTPUT: the hedge weights per instrument.
    """
    solved = np.linalg.solve(sigma_hh, sigma_hw)
    return -solved


def hedge_cost(
    turnover: float, short_notional: float, horizon_days: float = 21.0
) -> float:
    """Turnover times the provisional cost model plus borrow on shorts."""
    return float(
        turnover * COST_PER_TURNOVER
        + short_notional * BORROW_RATE * horizon_days / 252.0
    )


def _instrument_betas(
    date: pd.Timestamp, instrument_returns: pd.DataFrame, root: Path
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Each instrument's regression exposure to the model's factors.

    Fitted on the trailing FACTOR_WINDOW sessions before the rebalance date;
    the specific part is the regression residual variance. Returns None when
    the history is too short, which is recorded, never filled.
    """
    from efb.models import fundamental as fx

    factor_returns = pd.read_parquet(
        root / "models" / "XS-v1" / "factor_returns.parquet"
    )
    factor_returns = factor_returns.loc[pd.to_datetime(factor_returns["date"]) < date]
    history = factor_returns.pivot_table(index="date", columns="factor", values="f")
    ordered = list(fx.ESTIMATED_NAMES)
    if not set(ordered).issubset(history.columns):
        raise RuntimeError("the stored factor returns do not cover every factor")
    history = history.loc[:, ordered].iloc[-FACTOR_WINDOW:].fillna(0.0)
    if len(history) < MIN_FACTOR_HISTORY:
        return None, None
    available = instrument_returns.loc[instrument_returns.index < date].dropna(
        how="all"
    )
    aligned = available.reindex(history.index).dropna(how="all")
    if len(aligned) < MIN_FACTOR_HISTORY:
        return None, None
    y = aligned.to_numpy(dtype=float)
    x = history.loc[aligned.index].to_numpy(dtype=float)
    betas: list[np.ndarray] = []
    idio: list[float] = []
    for column in range(y.shape[1]):
        design = np.column_stack([np.ones(len(x)), x])
        fitted, *_ = np.linalg.lstsq(design, y[:, column], rcond=None)
        betas.append(fitted[1:])
        residual = y[:, column] - design @ fitted
        idio.append(float(np.var(residual, ddof=1)))
    return np.column_stack(betas), np.array(idio)


def run(data_root: Path = DATA_ROOT, store: bool = True) -> dict[str, object]:
    """The full E6 pipeline: hedges on the seed books, efficacy and decay."""
    from efb.models import fundamental as fx

    root = Path(data_root)
    wide, counts = eval_risk.load_clean_wide(root)
    portfolios = pd.read_parquet(root / "eval" / "e5_portfolios.parquet")
    instrument_returns = load_etf_returns(root)
    factor_names = list(fx.ESTIMATED_NAMES)
    fmp = pd.read_parquet(root / "models" / "XS-v1" / "fmp_weights.parquet")
    fmp_by_date = {pd.Timestamp(d): g for d, g in fmp.groupby("date")}
    grid = race.race_grid(root)
    spy = instrument_returns["SPY"]

    position_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    exposure_rows: list[dict[str, object]] = []
    book_returns_cache = {
        book: _seed_book_returns(book, wide, portfolios)
        for book in ("seed_ew", "seed_mom_ls")
    }
    for position, date in enumerate(grid):
        names = eval_risk._window_names(wide, date)
        if len(names) < 50:
            continue
        supplied = eval_risk._xs_pieces(date, names, root)
        if supplied is None:
            continue
        design = supplied["design"]
        factor_covariance = supplied["factor_covariance"]
        specific_v1 = supplied["specific"]
        low, diag_v2, low_diag, _fallback = eval_risk._xs_v2_block(date, names, root)
        betas, idio = _instrument_betas(date, instrument_returns, root)
        if betas is None or idio is None:
            continue
        # an instrument whose prices do not span the factor window cannot be
        # regressed: its beta column and idio variance are NaN. It is dropped
        # from the hedge on that date and the count is stored, never filled.
        usable = np.isfinite(betas).all(axis=0) & np.isfinite(idio)
        if usable.sum() < 2:
            continue
        betas_used = betas[:, usable]
        idio_used = idio[usable]
        n_instruments = int(usable.sum())
        sigma_hh = betas_used.T @ factor_covariance @ betas_used + np.diag(idio_used)
        stamp = race._as_of(fmp, date)
        if stamp is None:
            continue
        fmp_at = fmp_by_date[pd.Timestamp(stamp)]
        for book in ("seed_ew", "seed_mom_ls"):
            rows = portfolios.loc[
                (portfolios["portfolio"] == book)
                & (pd.to_datetime(portfolios["date"]) == date)
            ]
            if rows.empty:
                continue
            weights = (
                rows.set_index("ticker")["weight"]
                .reindex(names)
                .fillna(0.0)
                .to_numpy(dtype=float)
            )
            exposures = design.T @ weights
            sigma_hw = betas_used.T @ factor_covariance @ exposures
            h_star = min_variance_hedge(sigma_hh, sigma_hw)
            h_full = pd.Series(h_star, index=np.array(INSTRUMENTS)[usable])
            h_full = h_full.reindex(list(INSTRUMENTS)).to_numpy(dtype=float)
            # beta hedge: h = -beta_p against SPY over the trailing window
            # of data strictly before the rebalance date, point-in-time like
            # the instrument regressions
            book_returns = book_returns_cache[book]
            book_before = book_returns.loc[book_returns.index < date]
            spy_before = spy.loc[spy.index < date]
            h_spy = beta_hedge(book_before, spy_before)
            # the FMP hedge has two forms. The exact in-model one subtracts
            # sum_k x_k FMP_k with the FMPs rebuilt on the rebalance date's own
            # design, which drives the exposure to zero by construction: that
            # is the number F6.1 scores. The as-stored one uses the quarterly
            # capped FMP weights and keeps the cap drift, which is basis risk
            # and is reported, not hidden.
            exact_hedge, exact_names = fmp_hedge_exact(design, exposures)
            capped_hedge_weights, _tickers, _capped_names = fmp_hedge(
                exposures, fmp_at, factor_names
            )
            capped_on_names = (
                pd.Series(capped_hedge_weights, index=_tickers)
                .reindex(names)
                .fillna(0.0)
                .to_numpy(dtype=float)
            )
            exposure_after_fmp = design.T @ (weights + exact_hedge)
            exposure_after_fmp_capped = design.T @ (weights + capped_on_names)
            exposure_after_mv = exposures + betas_used @ h_star
            for factor, before, after_fmp, after_capped, after_mv in zip(
                factor_names,
                exposures,
                exposure_after_fmp,
                exposure_after_fmp_capped,
                exposure_after_mv,
                strict=True,
            ):
                exposure_rows.append(
                    {
                        "book": book,
                        "date": date,
                        "factor": factor,
                        "exposure_before": float(before),
                        "exposure_after_fmp": float(after_fmp),
                        "exposure_after_fmp_capped": float(after_capped),
                        "exposure_after_min_variance": float(after_mv),
                    }
                )
            factor_variance_before = float(exposures @ factor_covariance @ exposures)
            factor_variance_removed = float(
                sigma_hw @ np.linalg.solve(sigma_hh, sigma_hw)
            )
            for model, specific in (("xs_v1", specific_v1), ("xs_v2", diag_v2)):
                idio_before = float(weights @ np.diag(specific) @ weights)
                total_before = factor_variance_before + idio_before
                residual = float(
                    weights @ design @ factor_covariance @ design.T @ weights
                    + weights @ np.diag(specific) @ weights
                    - factor_variance_removed
                )
                short_notional = float(np.abs(h_star[h_star < 0]).sum())
                turnover = float(np.abs(h_star).sum())
                metric_rows.append(
                    {
                        "book": book,
                        "method": "min_variance",
                        "date": date,
                        "model": model,
                        "h_spy_beta": h_spy,
                        "factor_variance_before": factor_variance_before,
                        "factor_variance_removed": factor_variance_removed,
                        "factor_variance_removed_share": (
                            factor_variance_removed / factor_variance_before
                            if factor_variance_before > 0
                            else float("nan")
                        ),
                        "residual_variance": residual,
                        "idio_share_after": float(
                            (total_before - factor_variance_removed) / total_before
                            if total_before > 0
                            else float("nan")
                        ),
                        "turnover": turnover,
                        "short_notional": short_notional,
                        "cost": hedge_cost(turnover, short_notional),
                        "n_instruments": n_instruments,
                    }
                )
                for instrument, value in zip(INSTRUMENTS, h_full, strict=True):
                    position_rows.append(
                        {
                            "book": book,
                            "method": "min_variance",
                            "date": date,
                            "model": model,
                            "instrument": instrument,
                            "weight": float(value) if np.isfinite(value) else None,
                        }
                    )
            # FMP and beta rows are model-independent in their weights but the
            # metrics are stored under both models
            for model, specific in (("xs_v1", specific_v1), ("xs_v2", diag_v2)):
                hedged_book_weights = weights + exact_hedge
                idio_after = float(
                    hedged_book_weights @ np.diag(specific) @ hedged_book_weights
                )
                factor_after = float(
                    exposure_after_fmp @ factor_covariance @ exposure_after_fmp
                )
                total_after = factor_after + idio_after
                metric_rows.append(
                    {
                        "book": book,
                        "method": "fmp",
                        "date": date,
                        "model": model,
                        "h_spy_beta": h_spy,
                        "factor_variance_before": factor_variance_before,
                        "factor_variance_removed": factor_variance_before
                        - factor_after,
                        "factor_variance_removed_share": float(
                            (factor_variance_before - factor_after)
                            / factor_variance_before
                            if factor_variance_before > 0
                            else float("nan")
                        ),
                        "residual_variance": idio_after,
                        "idio_share_after": float(
                            idio_after / total_after
                            if total_after > 0
                            else float("nan")
                        ),
                        "turnover": float(np.abs(exact_hedge).sum()),
                        "short_notional": float(
                            np.abs(exact_hedge[exact_hedge < 0]).sum()
                        ),
                        "cost": hedge_cost(
                            float(np.abs(exact_hedge).sum()),
                            float(np.abs(exact_hedge[exact_hedge < 0]).sum()),
                        ),
                        "name_count": int(exact_names),
                        "name_count_capped": int(
                            (np.abs(capped_on_names) > 1e-12).sum()
                        ),
                        "exposure_after_fmp_capped_worst": float(
                            np.abs(exposure_after_fmp_capped).max()
                        ),
                    }
                )
            beta_obs = int(
                pd.concat([book_before, spy_before], axis=1, join="inner")
                .dropna()
                .tail(BETA_WINDOW)
                .shape[0]
            )
            metric_rows.append(
                {
                    "book": book,
                    "method": "beta",
                    "date": date,
                    "model": "shared",
                    "h_spy_beta": h_spy,
                    "factor_variance_before": factor_variance_before,
                    "factor_variance_removed": float("nan"),
                    "factor_variance_removed_share": float("nan"),
                    "residual_variance": float("nan"),
                    "idio_share_after": float("nan"),
                    "turnover": abs(h_spy),
                    "short_notional": max(0.0, -h_spy),
                    "cost": hedge_cost(abs(h_spy), max(0.0, -h_spy)),
                    "n_obs": beta_obs,
                }
            )
        if position % 25 == 0:
            print(f"  hedges {position + 1}/{len(grid)} ({date.date()})")
    metrics = pd.DataFrame(metric_rows)
    positions = pd.DataFrame(position_rows)
    exposures = pd.DataFrame(exposure_rows)
    efficacy = _realized_efficacy(
        root, metrics, positions, wide, portfolios, instrument_returns, grid
    )
    decay = _decay_curve(root, wide, portfolios, instrument_returns, grid)
    if store:
        (root / "hedge").mkdir(parents=True, exist_ok=True)
        metrics.to_parquet(root / "hedge" / "hedge_metrics.parquet", index=False)
        positions.to_parquet(root / "hedge" / "hedge_positions.parquet", index=False)
        exposures.to_parquet(root / "hedge" / "e6_exposures.parquet", index=False)
        efficacy.to_parquet(root / "hedge" / "e6_efficacy.parquet", index=False)
        decay.to_parquet(root / "hedge" / "e6_decay.parquet", index=False)
    return {
        "metrics": metrics,
        "positions": positions,
        "exposures": exposures,
        "efficacy": efficacy,
        "decay": decay,
        "exclusions": counts,
    }


def _realized_efficacy(
    root: Path,
    metrics: pd.DataFrame,
    positions: pd.DataFrame,
    wide: pd.DataFrame,
    portfolios: pd.DataFrame,
    instrument_returns: pd.DataFrame,
    grid: list[pd.Timestamp],
) -> pd.DataFrame:
    """Realized factor P&L and realized beta to Mkt-RF, 2018 to 2026."""
    ff = pd.read_parquet(root / "raw" / "factors_ff.parquet")
    mkt = ff["mkt_rf"] if "mkt_rf" in ff.columns else ff["Mkt-RF"]
    start = pd.Timestamp("2018-01-01")
    rows_out: list[dict[str, object]] = []
    for book in ("seed_ew", "seed_mom_ls"):
        book_returns = _seed_book_returns(book, wide, portfolios)
        unhedged = book_returns.loc[(book_returns.index >= start)]
        joined = pd.concat([unhedged, mkt.reindex(unhedged.index)], axis=1).dropna()
        if len(joined) > 60:
            cov_u = np.cov(joined.to_numpy(dtype=float).T, ddof=1)
            beta_u = float(cov_u[0, 1] / cov_u[1, 1])
        else:
            beta_u = float("nan")
        for method in ("beta", "fmp", "min_variance"):
            for model in ("xs_v1", "xs_v2"):
                if method == "min_variance":
                    sub = positions.loc[
                        (positions["book"] == book) & (positions["model"] == model)
                    ]
                    hedged = _apply_instrument_hedge(
                        sub, book, wide, portfolios, instrument_returns, grid
                    )
                elif method == "fmp":
                    hedged = _apply_fmp_hedge(book, wide, portfolios, grid)
                else:
                    hedged = _apply_beta_hedge(
                        book, wide, portfolios, instrument_returns, grid
                    )
                if hedged.empty:
                    continue
                sample = hedged.loc[hedged.index >= start]
                joined = pd.concat([sample, mkt.reindex(sample.index)], axis=1).dropna()
                beta = float("nan")
                if len(joined) > 60:
                    cov = np.cov(joined.to_numpy(dtype=float).T, ddof=1)
                    beta = float(cov[0, 1] / cov[1, 1])
                rows_out.append(
                    {
                        "book": book,
                        "method": method,
                        "model": model,
                        "realized_beta_to_mkt_rf": beta,
                        "unhedged_realized_beta_to_mkt_rf": beta_u,
                        "n_days": float(len(joined)),
                    }
                )
    return pd.DataFrame(rows_out)


def _apply_instrument_hedge(
    sub: pd.DataFrame,
    book: str,
    wide: pd.DataFrame,
    portfolios: pd.DataFrame,
    instrument_returns: pd.DataFrame,
    grid: list[pd.Timestamp],
) -> pd.Series:
    from efb import eval_risk as er

    book_returns = _seed_book_returns(book, wide, portfolios)
    dates = sorted(pd.to_datetime(sub["date"].unique()))
    collected: list[pd.Series] = []
    last = grid[-1] + pd.Timedelta(days=40)
    for start, end in zip(dates, dates[1:] + [last], strict=True):
        block = sub.loc[pd.to_datetime(sub["date"]) == start]
        h = (
            block.set_index("instrument")["weight"]
            .reindex(list(INSTRUMENTS))
            .fillna(0.0)
            .to_numpy(dtype=float)
        )
        window = instrument_returns.loc[
            (instrument_returns.index > start) & (instrument_returns.index <= end)
        ]
        hedge_return = er._portfolio_returns(h[None, :], window.to_numpy(dtype=float))[
            0
        ]
        collected.append(pd.Series(hedge_return, index=window.index))
    hedge_series = pd.concat(collected) if collected else pd.Series(dtype=float)
    return book_returns.reindex(hedge_series.index).add(hedge_series)


def _apply_fmp_hedge(
    book: str,
    wide: pd.DataFrame,
    portfolios: pd.DataFrame,
    grid: list[pd.Timestamp],
) -> pd.Series:
    from efb import eval_risk as er

    root = DATA_ROOT
    dates = sorted(pd.Timestamp(d) for d in grid)
    collected: list[pd.Series] = []
    last = grid[-1] + pd.Timedelta(days=40)
    for start, end in zip(dates, dates[1:] + [last], strict=True):
        names = er._window_names(wide, start)
        supplied = er._xs_pieces(start, names, root)
        if supplied is None:
            continue
        rows = portfolios.loc[
            (portfolios["portfolio"] == book)
            & (pd.to_datetime(portfolios["date"]) == start)
        ]
        if rows.empty:
            continue
        weights_on_names = (
            rows.set_index("ticker")["weight"]
            .reindex(names)
            .fillna(0.0)
            .to_numpy(dtype=float)
        )
        weights = (
            rows.set_index("ticker")["weight"]
            .reindex(wide.columns)
            .fillna(0.0)
            .to_numpy(dtype=float)
        )
        exposures = supplied["design"].T @ weights_on_names
        exact_hedge, _ = fmp_hedge_exact(supplied["design"], exposures)
        hedge = (
            pd.Series(exact_hedge, index=names)
            .reindex(wide.columns)
            .fillna(0.0)
            .to_numpy(dtype=float)
        )
        window = wide.loc[(wide.index > start) & (wide.index <= end)]
        book_part = er._portfolio_returns(
            weights[None, :], window.to_numpy(dtype=float)
        )[0]
        hedge_part = er._portfolio_returns(
            hedge[None, :], window.to_numpy(dtype=float)
        )[0]
        collected.append(pd.Series(book_part + hedge_part, index=window.index))
    if not collected:
        return pd.Series(dtype=float)
    return pd.concat(collected)


def _apply_beta_hedge(
    book: str,
    wide: pd.DataFrame,
    portfolios: pd.DataFrame,
    instrument_returns: pd.DataFrame,
    grid: list[pd.Timestamp],
    frequency: int = 21,
) -> pd.Series:
    book_returns = _seed_book_returns(book, wide, portfolios)
    spy = instrument_returns["SPY"]
    collected: list[pd.Series] = []
    last = grid[-1] + pd.Timedelta(days=40)
    # rebalance the beta hedge at the chosen frequency over the whole sample
    sessions = wide.index[(wide.index > grid[0]) & (wide.index <= last)]
    rebalances = [sessions[0]] + [
        sessions[i] for i in range(frequency, len(sessions), frequency)
    ]
    for start, end in zip(
        rebalances, rebalances[1:] + [sessions[-1] + pd.Timedelta(days=1)], strict=False
    ):
        h = beta_hedge(
            book_returns.loc[book_returns.index < start], spy.loc[spy.index < start]
        )
        if not np.isfinite(h):
            continue
        window = spy.loc[(spy.index >= start) & (spy.index < end)]
        book_window = book_returns.reindex(window.index)
        collected.append(
            pd.Series(
                book_window.to_numpy() + h * window.to_numpy(), index=window.index
            )
        )
    if not collected:
        return pd.Series(dtype=float)
    return pd.concat(collected)


def _decay_curve(
    root: Path,
    wide: pd.DataFrame,
    portfolios: pd.DataFrame,
    instrument_returns: pd.DataFrame,
    grid: list[pd.Timestamp],
) -> pd.DataFrame:
    """Beta-hedge efficacy against rebalancing frequency: a stored curve."""
    ff = pd.read_parquet(root / "raw" / "factors_ff.parquet")
    mkt = ff["mkt_rf"] if "mkt_rf" in ff.columns else ff["Mkt-RF"]
    start = pd.Timestamp("2018-01-01")
    rows: list[dict[str, object]] = []
    for book in ("seed_ew", "seed_mom_ls"):
        for frequency in (5, 21, 63):
            hedged = _apply_beta_hedge(
                book, wide, portfolios, instrument_returns, grid, frequency
            )
            sample = hedged.loc[hedged.index >= start]
            joined = pd.concat([sample, mkt.reindex(sample.index)], axis=1).dropna()
            beta = float("nan")
            if len(joined) > 60:
                covariance = np.cov(joined.to_numpy(dtype=float).T, ddof=1)
                beta = float(covariance[0, 1] / covariance[1, 1])
            rows.append(
                {
                    "book": book,
                    "rebalance_frequency": float(frequency),
                    "realized_beta_to_mkt_rf": beta,
                    "n_days": float(len(joined)),
                }
            )
    return pd.DataFrame(rows)
