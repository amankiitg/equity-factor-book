"""The turnover question, measured on the stored books: what the backtest trades,
what the live cost model charges for it, and what a turnover control would buy.

Read-only. It reads the committed research artifacts and writes only its own
JSON beside the research note.

    .venv/bin/python scripts/nov11_turnover_research.py

1. **The backtest's own turnover.** The research panel's book is a stored monthly
   weight series (`data/portfolios/persistent_proportional.parquet`, 176 dates
   from 2012-01-31 to 2026-08-31) and the convention every other module uses is
   that a book dated `d` is held from that close until the next book date, so the
   trade at each rebalance is the difference between two consecutive books.

2. **The same book net of the live cost model**, not the research engine's own
   corrected cost: spread + commission + impact is the trading half and borrow is
   the short leg's holding cost over one 21-session horizon, exactly as
   `live/evening_job.py::_cost_decomposition` computes it. The one modelling
   choice worth stating twice: **the live model charges spread and commission on
   the book that is *held*, per rebalance, and only the impact on the trade.** At
   a monthly rebalance that is the same order as charging them on the trade; at a
   five-session rebalance it is four times as much, so every frequency reading is
   printed both ways.

3. **Turnover controls, applied to the same stored books** so the difference is
   the control and nothing else: the stored persistence `phi`, a no-trade band,
   and the live construction's 20-share floor with an entry/exit band (item 12).

What this cannot answer, and says so: the panel's signal is monthly, so a 2- or
5-session *signal* cannot be built from it. What can be measured is what a higher
rebalance frequency costs when the target is fixed and the book is returned to
it, which is the schedule half of the question.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
NAV = 1_000_000.0
REFERENCE_AUM = 1e8
FLOOR_SHARES = 20
TRADING_DAYS = 252
HORIZON = 21
IMPACT_K = 0.5
COMMISSION = 1e-4
BORROW_RATE = 0.02
SPREAD_FLOOR = 1e-4


def design_config() -> dict[str, float]:
    from efb import allocate

    return allocate.pick_design_config(DATA)


def load_books(rho: float, phi: float, seed: float) -> pd.DataFrame:
    """One stored book: rebalance dates by ticker, renormalized to unit gross."""
    frame = pd.read_parquet(DATA / "portfolios" / "persistent_proportional.parquet")
    frame = frame.loc[(frame["rho"] == rho) & (frame["phi"] == phi) & (frame["seed"] == seed)]
    frame["date"] = pd.to_datetime(frame["date"])
    wide = frame.pivot_table(index="date", columns="ticker", values="weight")
    wide = wide.sort_index().fillna(0.0)
    gross = wide.abs().sum(axis=1)
    return wide.div(gross.where(gross > 0, 1.0), axis=0)


def load_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = pd.read_parquet(DATA / "processed" / "returns.parquet")
    returns = panel["r"].unstack("ticker").sort_index()
    prices = pd.read_parquet(DATA / "raw" / "prices.parquet")
    close = prices["close"].unstack("ticker").sort_index()
    return returns, close


def cost_inputs() -> tuple[pd.Series, pd.Series]:
    from efb import costs

    prices = pd.read_parquet(DATA / "raw" / "prices.parquet")
    spread = costs.spread_schedule(prices, DATA).clip(lower=SPREAD_FLOOR)
    return spread, costs.trailing_adv(prices)


_SPECIFIC_CACHE: dict[str, pd.Series] = {}


def _specific_blocks() -> dict[pd.Timestamp, pd.Series]:
    """The stored specific-variance block, one frame per artifact date."""
    if not _SPECIFIC_CACHE:
        frame = pd.read_parquet(DATA / "models" / "XS-v1" / "specific_var.parquet")
        frame["date"] = pd.to_datetime(frame["date"])
        for stamp, group in frame.groupby("date"):
            _SPECIFIC_CACHE[str(stamp)] = group.set_index("ticker")["specific_var"]
    return {pd.Timestamp(key): value for key, value in _SPECIFIC_CACHE.items()}


_SPECIFIC_STD: dict[str, float] = {}


def specific_return_std(names: list[str]) -> pd.Series:
    """The per-name specific-return standard deviation, the research model's sigma."""
    if not _SPECIFIC_STD:
        frame = pd.read_parquet(DATA / "models" / "XS-v1" / "specific_returns.parquet")
        for ticker, value in frame.groupby("ticker")["specific_return"].std(ddof=1).items():
            _SPECIFIC_STD[str(ticker)] = float(value)
    return pd.Series(_SPECIFIC_STD).reindex(names)


def research_cost_per_rebalance(
    books: pd.DataFrame, previous: pd.DataFrame, spread: pd.Series, adv: pd.Series, aum: float
) -> pd.DataFrame:
    """The research engine's own cost: spread + commission + impact on the trade.

    `efb/costs.py::_trade_cost`, called per rebalance. No borrow, and the spread
    is charged on the trade rather than on the held book, which are the two
    differences from the live model that the report turns on.
    """
    from efb import costs

    names = list(books.columns)
    spread_map = spread.reindex(names).fillna(spread.median()).to_numpy(dtype=float)
    adv_map = adv.reindex(names).fillna(adv.median()).to_numpy(dtype=float)
    sigma_map = specific_return_std(names).fillna(0.0).to_numpy(dtype=float)
    rows: list[dict[str, float]] = []
    for stamp in books.index:
        weights = books.loc[stamp].to_numpy(dtype=float)
        prior = (
            previous.loc[stamp].to_numpy(dtype=float)
            if stamp in previous.index
            else np.zeros_like(weights)
        )
        delta = weights - prior
        total = costs._trade_cost(delta, spread_map, sigma_map, adv_map, aum, IMPACT_K)
        rows.append(
            {
                "date": stamp,
                "turnover": float(np.abs(delta).sum()),
                "trading_bps": float(total) * 1e4,
                "borrow_bps": 0.0,
                "total_bps": float(total) * 1e4,
                "n_names": float((np.abs(weights) > 1e-12).sum()),
            }
        )
    return pd.DataFrame(rows).set_index("date")


def specific_vol(names: list[str], stamp: pd.Timestamp) -> pd.Series:
    """The specific volatility in force at `stamp`: the latest block at or before it."""
    blocks = _specific_blocks()
    usable = [date for date in blocks if date <= stamp]
    if not usable:
        return pd.Series(0.0, index=names)
    block = blocks[max(usable)]
    return np.sqrt(block.reindex(names).astype(float).clip(lower=0.0))


def alignment(returns: pd.DataFrame, books: pd.DataFrame) -> np.ndarray:
    """For each session, the book row it earns on (`-1` before the first book)."""
    return books.index.searchsorted(returns.index, side="left") - 1


def gross_series(returns: pd.DataFrame, books: pd.DataFrame, rows: np.ndarray) -> pd.Series:
    """The book's gross return per session on the weights it held."""
    names = books.columns
    aligned = returns.reindex(columns=names).to_numpy(dtype=float)
    values = np.zeros(len(returns))
    for index, row in enumerate(rows):
        if row < 0:
            continue
        day = aligned[index]
        mask = np.isfinite(day)
        values[index] = float((books.iloc[row].to_numpy(dtype=float)[mask] * day[mask]).sum())
    return pd.Series(values, index=returns.index, name="gross")


def cost_per_rebalance(
    books: pd.DataFrame,
    previous: pd.DataFrame,
    spread: pd.Series,
    adv: pd.Series,
    aum: float,
    *,
    charge_spread_on_trade: bool,
) -> pd.DataFrame:
    """The live cost split at each rebalance, in basis points of NAV."""
    names = list(books.columns)
    spread_map = spread.reindex(names).fillna(spread.median()).to_numpy(dtype=float)
    adv_map = adv.reindex(names).fillna(adv.median()).to_numpy(dtype=float)
    rows: list[dict[str, float]] = []
    for stamp in books.index:
        weights = books.loc[stamp].to_numpy(dtype=float)
        prior = (
            previous.loc[stamp].to_numpy(dtype=float)
            if stamp in previous.index
            else np.zeros_like(weights)
        )
        delta = weights - prior
        sigma = specific_vol(names, stamp).fillna(0.0).to_numpy(dtype=float)
        dollar_trade = np.abs(delta) * aum
        impact = IMPACT_K * sigma * np.sqrt(
            np.maximum(dollar_trade, 0.0) / np.maximum(adv_map, 1.0)
        )
        base = np.abs(delta) if charge_spread_on_trade else np.abs(weights)
        spread_bps = float(np.sum(spread_map * base)) * 1e4
        commission_bps = float(COMMISSION * base.sum()) * 1e4
        impact_bps = float(np.sum(impact * np.abs(delta))) * 1e4
        short_gross = float(np.maximum(-weights, 0.0).sum())
        borrow_bps = BORROW_RATE * short_gross * (HORIZON / TRADING_DAYS) * 1e4
        rows.append(
            {
                "date": stamp,
                "turnover": float(np.abs(delta).sum()),
                "spread_bps": spread_bps,
                "commission_bps": commission_bps,
                "impact_bps": impact_bps,
                "borrow_bps": borrow_bps,
                "trading_bps": spread_bps + commission_bps + impact_bps,
                "total_bps": spread_bps + commission_bps + impact_bps + borrow_bps,
                "n_names": float((np.abs(weights) > 1e-12).sum()),
            }
        )
    return pd.DataFrame(rows).set_index("date")


def run(
    books: pd.DataFrame,
    returns: pd.DataFrame,
    spread: pd.Series,
    adv: pd.Series,
    *,
    aum: float = NAV,
    charge_spread_on_trade: bool = True,
    cost_model: str = "live",
) -> dict[str, float]:
    """Every figure for one book series, under one reading of the cost model."""
    rows = alignment(returns, books)
    gross = gross_series(returns, books, rows)
    previous = books.shift(1).dropna(how="all")
    costs = (
        research_cost_per_rebalance(books, previous, spread, adv, aum)
        if cost_model == "research"
        else cost_per_rebalance(
            books, previous, spread, adv, aum,
            charge_spread_on_trade=charge_spread_on_trade,
        )
    )
    cost_by_session = pd.Series(0.0, index=gross.index)
    for stamp, row in costs.iterrows():
        if stamp in cost_by_session.index:
            cost_by_session.loc[stamp] = -row["total_bps"] * 1e-4
    net = gross + cost_by_session
    live = np.asarray(rows) >= 0
    gross_live = gross[live]
    net_live = net[live]
    days = int(live.sum())
    annual = TRADING_DAYS / days
    per_year = TRADING_DAYS / HORIZON
    return {
        "sessions": float(days),
        "rebalances": float(len(books)),
        "ann_gross": float(gross_live.mean() * TRADING_DAYS),
        "ann_net": float(net_live.mean() * TRADING_DAYS),
        "geom_gross": float(np.prod(1.0 + gross_live.to_numpy()) ** annual - 1.0),
        "geom_net": float(np.prod(1.0 + net_live.to_numpy()) ** annual - 1.0),
        "vol": float(gross_live.std(ddof=1) * np.sqrt(TRADING_DAYS)),
        "sharpe_gross": float(gross_live.mean() / gross_live.std(ddof=1) * np.sqrt(TRADING_DAYS)),
        "sharpe_net": float(net_live.mean() / gross_live.std(ddof=1) * np.sqrt(TRADING_DAYS)),
        "turnover_mean": float(costs["turnover"].mean()),
        "turnover_annual": float(costs["turnover"].mean() * per_year),
        "cost_bps_annual": float(costs["total_bps"].mean() * per_year),
        "trading_bps_annual": float(costs["trading_bps"].mean() * per_year),
        "borrow_bps_annual": float(costs["borrow_bps"].mean() * per_year),
        "n_names": float(costs["n_names"].mean()),
        "gross_drift": float(np.abs(books.abs().sum(axis=1) - 1.0).max()),
    }


def banded(books: pd.DataFrame, band: float) -> pd.DataFrame:
    """Hold a name whose own change is inside `band` (a fraction of gross)."""
    names = books.columns
    held = books.iloc[0].reindex(names).fillna(0.0)
    out: dict[pd.Timestamp, pd.Series] = {books.index[0]: held}
    for stamp in books.index[1:]:
        target = books.loc[stamp].reindex(names).fillna(0.0)
        current = target.where((target - held).abs() > band, held)
        out[stamp] = current
        held = current
    return pd.DataFrame(out).T


def quantized(books: pd.DataFrame, close: pd.DataFrame, *, release: float) -> pd.DataFrame:
    """The live construction: whole shares at NAV, a 20-share floor, and a band.

    A name is admitted at the floor and released only when its own shares fall
    below `release` times the floor - item 12's entry/exit band. `release` of 1.0
    is the rule as it stands (`live/construction_table.py`).
    """
    out: dict[pd.Timestamp, pd.Series] = {}
    admitted: set[str] = set()
    for stamp in books.index:
        row = books.loc[stamp]
        price = close.reindex(columns=row.index).ffill().loc[:stamp].iloc[-1]
        usable = row.notna() & price.notna() & (price > 0)
        shares = np.floor(np.abs(row.where(usable, 0.0)) * NAV / price.where(usable))
        inside = {name for name in shares.index if shares.get(name, 0.0) >= FLOOR_SHARES}
        still = {name for name in admitted if shares.get(name, 0.0) >= release * FLOOR_SHARES}
        keep = inside | still
        kept = row.where(row.index.isin(keep), 0.0)
        gross = float(kept.abs().sum())
        if gross > 0:
            kept = kept * (float(row.abs().sum()) / gross)
        out[stamp] = kept
        admitted = keep
    return pd.DataFrame(out).T


def table(rows: dict[str, dict[str, float]], label: str) -> str:
    lines = [
        "| variant | gross ann | net ann | vol | Sharpe gross | Sharpe net | turnover/reb | "
        "turnover/yr | cost bp/yr | trading | borrow | names |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, row in rows.items():
        if not row:
            continue
        lines.append(
            f"| {name} | {row['ann_gross'] * 100:.2f}% | {row['ann_net'] * 100:.2f}% | "
            f"{row['vol'] * 100:.2f}% | {row['sharpe_gross']:.2f} | {row['sharpe_net']:.2f} | "
            f"{row['turnover_mean'] * 100:.1f}% | {row['turnover_annual'] * 100:.0f}% | "
            f"{row['cost_bps_annual']:.0f} | {row['trading_bps_annual']:.0f} | "
            f"{row['borrow_bps_annual']:.0f} | {row['n_names']:.0f} |"
        )
    lines.append("")
    lines.append(f"{label}")
    return "\n".join(lines)


def main() -> None:
    config = design_config()
    rho, phi, seed = float(config["rho"]), float(config["phi"]), int(config["seed"])
    print(f"design config: rho={rho} phi={phi} seed={seed}")
    returns, close = load_panel()
    spread, adv = cost_inputs()
    books = load_books(rho, phi, seed)
    print(
        f"books: {len(books)} rebalance dates {books.index[0].date()} -> "
        f"{books.index[-1].date()}, {books.shape[1]} tickers, "
        f"panel {returns.shape[0]} sessions {returns.index[0].date()} -> {returns.index[-1].date()}"
    )

    research_reading = run(books, returns, spread, adv, cost_model="research")
    trade_reading = run(books, returns, spread, adv, charge_spread_on_trade=True)
    live_reading = run(books, returns, spread, adv, charge_spread_on_trade=False)
    print("\n## three cost stacks on the same book and the same trades\n")
    print(table({
        "research engine: spread+commission+impact on the trade, no borrow": research_reading,
        "live model, spread on the trade (adds borrow)": trade_reading,
        "live model as written (spread+commission on the held book)": live_reading,
    }, "NAV $1,000,000"))

    ref = run(books, returns, spread, adv, aum=REFERENCE_AUM, charge_spread_on_trade=True)
    print("\n## the same book at E6's reference AUM (impact scales with size)\n")
    print(table({"spread+commission on the trade, AUM $100m": ref}, "NAV $100,000,000"))

    print("\n## persistence, which the stored artifacts already carry\n")
    rows = {f"phi = {value}": run(load_books(rho, value, seed), returns, spread, adv)
            for value in (0.0, 0.8, 0.95)}
    print(table(rows, "NAV $1,000,000"))

    print("\n## a no-trade band on each name's own change\n")
    rows = {"band 0 bp (the stored book)": trade_reading}
    rows.update({f"band {bp} bp": run(banded(books, bp / 1e4), returns, spread, adv)
                 for bp in (1, 2, 5, 10, 25, 50)})
    print(table(rows, "NAV $1,000,000"))

    print("\n## the live construction: whole shares, a 20-share floor, an entry/exit band\n")
    rows = {}
    churn: dict[str, int] = {}
    for release in (1.0, 0.75, 0.5, 0.33):
        quant = quantized(books, close, release=release)
        rows[f"release at {release:.2f} x floor"] = run(quant, returns, spread, adv)
        present = quant.abs() > 0
        churn[f"{release:.2f}"] = int(present.sum().sum())
    print(table(rows, "NAV $1,000,000"))

    summary = {
        "config": config,
        "book_dates": int(len(books)),
        "book_first": str(books.index[0].date()),
        "book_last": str(books.index[-1].date()),
        "panel_sessions": int(returns.shape[0]),
        "research_reading": research_reading,
        "live_reading": live_reading,
        "trade_reading": trade_reading,
        "reference_aum": ref,
        "name_dates": churn,
    }
    (ROOT / "docs" / "research").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "research" / "nov11_turnover_numbers.json").write_text(
        json.dumps(summary, indent=1, default=float)
    )
    print("\nwrote docs/research/nov11_turnover_numbers.json")


if __name__ == "__main__":
    main()
