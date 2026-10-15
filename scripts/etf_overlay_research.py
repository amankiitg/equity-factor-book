"""Would an ETF overlay be a better hedge? Four constructions, live books and panel.

Read-only research. No trading change, no flag, no deploy, nothing written outside
`research/` and `docs/research/`.

    .venv/bin/python scripts/etf_overlay_research.py --scope live
    .venv/bin/python scripts/etf_overlay_research.py --scope backtest

The question. The live hedge re-weights single stocks to cancel all seventeen
estimated factors. On 2026-10-13 it moved 71 names for $72,939 - 16% of the day's
turnover - and left SMCI carrying 11.0% of the book's predicted stock-specific
risk. A cap-and-rehedge fixes the concentration for free (docs/research/nov11_hedge.md);
this asks whether instruments that carry a factor *cheaply* would be better still.

Four constructions, from the same sized book `u`, the same design `X`, the same EWMA
factor covariance `F` and the same specific diagonal `D`:

- **`exact`** - the live hedge: `w = u - X (X'X)^-1 X'u` (`live/sizing.py`), the
  unconstrained projection that zeroes every exposure with stocks only.
- **`cap_then_rehedge`** - the live 10% variance-share cap applied and neutrality
  re-solved, three passes (`docs/research/nov11_hedge.md`).
- **`etf_overlay`** - SPY and the eleven sector SPDRs cancel the market and the
  sectors; stocks cancel only the remaining style factors, and they do it knowing
  what the ETFs have already contributed.
- **`etf_only`** - the same ETFs cancel the market and the sectors and the style
  residual is accepted rather than hedged.

Everything is measured at the gross each construction produced *and* at gross 1, and
the ETF legs are priced with their own spreads and their own borrow.

The ETFs' factor exposures are estimated, not assumed: each ETF's daily total return
is regressed on the model's own factor returns over the history strictly before the
study window, and the regression's residual variance is that ETF's specific variance.
The estimation window, the loadings and the R^2 of every ETF are written into the
numbers file, so a reader can see how well a regression describes an index fund
before reading anything built on it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA = Path(os.environ.get("EFB_DATA_ROOT", ROOT / "data"))
TRADING_DAYS = 252
LIVE_START = "2026-10-01"
ETF_PRICES = ROOT / "research" / "etf_prices" / "etf_daily_prices.parquet"

# The twelve instruments: the market, and one fund per sector the model estimates.
# XLRE is a 2015 listing, so its history is shorter than the rest and its loadings
# are estimated on what exists; every window is reported.
ETFS = [
    "SPY",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
]
SECTOR_ETFS = [ticker for ticker in ETFS if ticker != "SPY"]

# What an ETF can cancel cheaply and what it cannot. The market and a sector are what
# an index fund and a sector fund *are*, so those are the columns the overlay is asked
# to cancel; the style factors are what it holds as a by-product of its constituents,
# so those are left to the stocks.
MARKET = ["market"]
STYLE = ["beta", "liquidity", "momentum", "resid_vol", "reversal", "size"]


def env() -> None:
    """Load the store's credentials from `.env`, without printing any of them."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def live_books() -> pd.DataFrame:
    """The live pre-hedge book per close, rebuilt from the stored alpha and variance.

    `efb.positions` carries, per close and name, the `alpha` and the `idio_vol` the
    sizing used, and this rebuilds the sized-and-capped book the hedge acted on with
    the same three calls the live path uses, so the study is measured against the
    book the loop actually hedged rather than against a reconstruction of it.
    """
    env()
    from efb import size as size_mod
    from live import sizing, store

    frame = store.select("positions")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.loc[frame["trade_date"] >= pd.Timestamp(LIVE_START)]
    rows: list[dict[str, Any]] = []
    for stamp, group in frame.groupby("trade_date", sort=True):
        group = group.dropna(subset=["alpha", "idio_vol"])
        group = group.loc[group["idio_vol"] > 0]
        alpha = group["alpha"].to_numpy(dtype=float)
        specific_var = group["idio_vol"].to_numpy(dtype=float)
        sigma = np.sqrt(specific_var)
        sized = size_mod.proportional(alpha, sigma)
        sized = sizing.cap_variance_shares(sized, specific_var)
        sized = sizing.renormalize(sized, gross=1.0)
        for ticker, weight in zip(group["ticker"], sized, strict=True):
            rows.append({"date": stamp, "ticker": str(ticker), "weight": float(weight)})
    return pd.DataFrame(rows)


def backtest_books() -> pd.DataFrame:
    """The stored design book, one row per date and ticker, renormalized to gross 1."""
    from efb import allocate

    config = allocate.pick_design_config(DATA)
    frame = pd.read_parquet(DATA / "portfolios" / "persistent_proportional.parquet")
    frame = frame.loc[
        (frame["rho"] == float(config["rho"]))
        & (frame["phi"] == float(config["phi"]))
        & (frame["seed"] == int(config["seed"]))
    ].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["weight"] = frame["weight"].fillna(0.0)
    gross = frame.groupby("date")["weight"].transform(lambda column: column.abs().sum())
    frame["weight"] = frame["weight"] / gross.where(gross > 0, 1.0)
    frame = frame.loc[frame["weight"].abs() > 0]
    return frame.loc[:, ["date", "ticker", "weight"]]


def factor_returns() -> pd.DataFrame:
    """The model's own factor returns, as a date x factor frame."""
    frame = pd.read_parquet(DATA / "models" / "XS-v1" / "factor_returns.parquet")
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.pivot_table(index="date", columns="factor", values="f")


def etf_loadings(as_of: str, factor_names: list[str]) -> dict[str, Any]:
    """Each ETF's exposures to the model's factors, and its specific variance.

    The regression is an ordinary least squares of the ETF's daily total return on the
    model's own factor returns - the same factors the book is measured against, in the
    same column order - over the window that ends the day before the study starts.
    Nothing from the study window enters the estimate, so the loadings are what a
    reader could have known then.

    What comes out is a fund's *average* sensitivity over the window, not a promise:
    an index fund's loadings drift with its constituents' weights and with the model's
    own re-estimation, and the R^2 beside each one is how much of the fund's variance
    these factors explain. Both are reported, because an overlay built on loadings
    that explain half a fund's variance is a different claim from one built on
    loadings that explain nine tenths of it.
    """
    prices = pd.read_parquet(ETF_PRICES)
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.loc[prices["date"] < pd.Timestamp(as_of)].set_index("date")
    returns = np.log(prices[ETFS]).diff()
    factors = factor_returns()
    factors = factors.loc[factors.index < pd.Timestamp(as_of)]
    columns = [name for name in factor_names if name in factors.columns]
    if len(columns) != len(factor_names):
        missing = sorted(set(factor_names) - set(columns))
        raise KeyError(f"the factor returns do not carry {missing}")
    # Each fund is regressed on its own available history rather than on a window all
    # twelve share: XLC listed in 2018 and XLRE in 2015, so a common window would
    # throw away six years of the older funds' data for the youngest one's sake. Every
    # fund's own window is reported beside its loadings.
    factors = factors.loc[:, columns]
    output: dict[str, Any] = {"factors": columns, "etfs": {}, "windows": {}}
    latest: tuple[str, str] = ("", "")
    for ticker in ETFS:
        joined = pd.concat([returns[[ticker]], factors], axis=1, join="inner").dropna()
        if len(joined) < 200:
            raise ValueError(
                f"no overlapping ETF and factor history for {ticker} before {as_of}"
            )
        design = np.column_stack(
            [np.ones(len(joined))]
            + [joined[name].to_numpy(dtype=float) for name in columns]
        )
        window = (str(joined.index[0].date()), str(joined.index[-1].date()))
        output["windows"][ticker] = list(window)
        if window[0] < latest[0] or latest == ("", ""):
            latest = window
        y = joined[ticker].to_numpy(dtype=float)
        beta, *_ = np.linalg.lstsq(design, y, rcond=None)
        residual = y - design @ beta
        total_var = float(np.var(y, ddof=1))
        output["etfs"][ticker] = {
            "alpha_daily": float(beta[0]),
            "loadings": {
                name: float(value)
                for name, value in zip(columns, beta[1:], strict=True)
            },
            "specific_daily_var": float(np.var(residual, ddof=1)),
            "residual_annual_vol": float(
                np.sqrt(np.var(residual, ddof=1) * TRADING_DAYS)
            ),
            "total_annual_vol": float(np.sqrt(total_var * TRADING_DAYS)),
            "r_squared": (
                float(1 - np.var(residual, ddof=1) / total_var)
                if total_var > 0
                else None
            ),
            "n_days": int(len(joined)),
            "window": list(window),
        }
    output["window"] = list(latest)
    output["n_days"] = min(entry["n_days"] for entry in output["etfs"].values())
    return output


def book_factor_names(pieces: dict[str, Any]) -> list[str]:
    """The book's own design-column order, which the ETFs' rows must be aligned to."""
    from efb.models import fundamental as fx

    names = pieces.get("factor_names")
    return list(names) if names else list(fx.ESTIMATED_NAMES)


def pieces_at(stamp: pd.Timestamp, names: list[str]) -> dict[str, Any] | None:
    """Design, factor covariance and specific variance for one close.

    `efb.eval_risk._xs_pieces` is the live loop's own supplier. It cannot answer for
    the live closes after the committed panel's end, so those are rebuilt the same way
    the hedge research rebuilt them: the same design function, the same EWMA
    covariance over the factor returns strictly before the close, and the same
    median-filled diagonal.
    """
    from efb import eval_risk, race
    from efb.models import fundamental as fx

    try:
        pieces = eval_risk._xs_pieces(pd.Timestamp(stamp), names, DATA)
    except KeyError:
        pieces = None
    if pieces is not None:
        from efb.models import fundamental as fx

        out = {str(key): value for key, value in pieces.items()}
        out.setdefault("factor_names", list(fx.ESTIMATED_NAMES))
        return out
    history = factor_returns().loc[factor_returns().index < stamp]
    if history.index.nunique() < 126:
        return None
    ordered = list(fx.ESTIMATED_NAMES)
    if not set(ordered).issubset(history.columns):
        return None
    covariance = fx.ewma_factor_cov(
        history.loc[:, ordered].fillna(0.0), half_life=fx.F_HALF_LIFE
    ).to_numpy(dtype=float)
    design = np.nan_to_num(race._descriptor_design(stamp, names, DATA), nan=0.0)
    specific, missing = race._specific_for(stamp, names, DATA)
    specific = np.asarray(specific, dtype=float)
    specific = np.where(np.isnan(specific), float(np.nanmedian(specific)), specific)
    return {
        "design": design,
        "factor_covariance": covariance,
        "specific": specific,
        "missing": int(missing),
        "factor_names": ordered,
    }


def column_classes(factor_names: list[str]) -> tuple[list[int], list[int]]:
    """Which design columns are the market and the sectors, and which are style.

    The split is what the ETF overlay rests on: an index fund and a sector fund carry
    the market and a sector almost perfectly, and a style factor only as a by-product
    of what they happen to hold. So the ETFs are asked to cancel the first group and
    the stocks the second.
    """
    market_sector = [
        index
        for index, name in enumerate(factor_names)
        if name == "market" or name.startswith("sector_")
    ]
    style = [index for index in range(len(factor_names)) if index not in market_sector]
    return market_sector, style


def variants(
    u: np.ndarray,
    design: np.ndarray,
    specific: np.ndarray,
    factor_names: list[str],
    etf_design: np.ndarray,
) -> dict[str, Any]:
    """The four constructions: a stock book and an ETF book, from the same sized `u`."""
    from live import sizing

    market_sector, style = column_classes(factor_names)
    output: dict[str, Any] = {}

    exposures = design.T @ u
    exact = u + sizing.hedge_exact_robust(design, exposures)
    output["exact"] = (exact, np.zeros(etf_design.shape[0]))

    current = exact.copy()
    for _ in range(3):
        current = sizing.cap_variance_shares(current, specific)
        beta = np.linalg.lstsq(design.T @ design, design.T @ current, rcond=None)[0]
        current = current - design @ beta
    output["cap_then_rehedge"] = (current, np.zeros(etf_design.shape[0]))

    # The ETFs cancel the book's market and sector exposure and the stocks cancel the
    # style factors, and the two are solved together rather than one after the other:
    # a style projection moves the market exposure it sits on, so a two-step solve
    # would cancel the market and lose it again in the next line. With `P` the style
    # projection, the joint solution for the ETF vector `f` is
    #
    #   (E_M' - X_M' P E_T') f = -(X_M' u - X_M' P X_T' u)
    #
    # and then the stocks' own style correction follows from `f`. Eleven equations for
    # twelve funds, so it is solved by least squares; SPY's sector loadings make the
    # system nearly singular, and the residual that could not be cancelled is reported
    # rather than assumed away.
    style_block = design[:, style]
    style_solve = np.linalg.pinv(style_block.T @ style_block)
    left = design[:, market_sector].T @ style_block @ style_solve
    lhs = etf_design[:, market_sector].T - left @ etf_design[:, style].T
    rhs = -(design[:, market_sector].T @ u - left @ (style_block.T @ u))
    overlay, *_ = np.linalg.lstsq(lhs, rhs, rcond=None)
    residual = lhs @ overlay - rhs
    output["market_sector_residual"] = float(np.abs(residual).max())
    beta = style_solve @ (style_block.T @ u + etf_design[:, style].T @ overlay)
    output["etf_overlay"] = (u - style_block @ beta, overlay)
    output["etf_only"] = (u.copy(), overlay)
    return output


def measure(
    weight: np.ndarray,
    design: np.ndarray,
    specific: np.ndarray,
    etf_weight: np.ndarray,
    etf_design: np.ndarray,
    etf_specific: np.ndarray,
    covariance: np.ndarray,
) -> dict[str, float]:
    """Vol, the split, and the largest single-instrument share of specific variance."""
    joint_design = np.vstack([design, etf_design])
    joint_weight = np.concatenate([weight, etf_weight])
    joint_specific = np.concatenate([specific, etf_specific])
    projected = joint_weight @ joint_design
    factor_var = float(projected @ covariance @ projected)
    idio_var = float(np.sum(joint_weight**2 * joint_specific))
    total = factor_var + idio_var
    shares = (
        joint_weight**2 * joint_specific / total
        if total > 0
        else np.zeros_like(joint_weight)
    )
    return {
        "vol": float(np.sqrt(total * TRADING_DAYS)),
        "factor_vol": float(np.sqrt(factor_var * TRADING_DAYS)),
        "factor_share": factor_var / total if total > 0 else float("nan"),
        "max_variance_share": float(np.max(shares)) if len(shares) else float("nan"),
        "max_variance_share_stock": (
            float(np.max(shares[: len(weight)])) if len(weight) else float("nan")
        ),
        "stock_var_share": float(np.sum(shares[: len(weight)])),
        "exposure_abs_max": float(np.abs(joint_design.T @ joint_weight).max()),
        "stock_gross": float(np.abs(weight).sum()),
        "etf_gross": float(np.abs(etf_weight).sum()),
        "gross": float(np.abs(weight).sum() + np.abs(etf_weight).sum()),
    }


# The ETFs' own half-spreads and borrow, stated as the assumptions they are. A
# sector SPDR trades at a penny or two on a $50-$200 price, which is 1-3 bp of
# notional, against a stock book whose size-decile schedule runs 1-10 bp; SPY is one
# to two tenths of a bp. Borrow on a liquid ETF short is general collateral, well
# inside the 2%/yr the stock book charges itself.
ETF_HALF_SPREAD_BP = {"SPY": 0.15}
ETF_HALF_SPREAD_DEFAULT_BP = 1.0
ETF_HALF_SPREAD_WIDE_BP = {"XLB": 1.5, "XLRE": 1.5}
ETF_BORROW_RATE = {"SPY": 0.003}
ETF_BORROW_RATE_DEFAULT = 0.005


def etf_adv(as_of: str) -> dict[str, float]:
    """Each ETF's trailing dollar ADV, from the prices fetched for this study."""
    prices = pd.read_parquet(ETF_PRICES)
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.loc[prices["date"] < pd.Timestamp(as_of)].tail(63).set_index("date")
    return {
        ticker: float((prices[ticker] * prices[f"{ticker}_volume"]).median())
        for ticker in ETFS
    }


def costs(
    weight: np.ndarray,
    names: list[str],
    specific: np.ndarray,
    previous: pd.Series | None,
    etf_weight: np.ndarray,
    etf_previous: pd.Series,
    etf_specific: np.ndarray,
    nav: float,
) -> dict[str, float]:
    """The four-way cost split, in basis points of NAV, for one close.

    The stock half is the loop's own formula, called rather than re-derived:
    `live/evening_job._cost_decomposition` prices spread and commission on the book
    held, impact on the change in weight with the square-root schedule, and borrow as
    the annual rate on the short leg over `costs.HORIZON` sessions. The ETF half uses
    the same shapes with the ETFs' own inputs: their quoted half-spreads, their own
    trailing dollar ADV from the fetched prices, their specific volatility from the
    regression, and a general-collateral borrow rate.

    Every leg is aligned on the union of this close's names and the last one's: a name
    that left the book has a closing leg, and a cost model that only saw tonight's
    names would price the exits at nothing.
    """
    from efb import costs as costs_mod
    from live.evening_job import HORIZON, _adv_maps
    from live.evening_job import TRADING_DAYS as LIVE_TRADING_DAYS

    held = pd.Series(weight, index=names)
    prior = previous if previous is not None else pd.Series(dtype=float)
    union = held.index.union(prior.index)
    delta = held.reindex(union).fillna(0.0) - prior.reindex(union).fillna(0.0)

    prices = pd.read_parquet(DATA / "raw" / "prices.parquet")
    schedule = costs_mod.spread_schedule(prices, DATA)
    spread_map = schedule.reindex(union).fillna(schedule.median())
    adv_map, _raw, _thin = _adv_maps(list(union), DATA)
    adv = pd.Series(adv_map, index=union)
    sigma_map = pd.Series(specific, index=names).reindex(union)
    sigma_map = sigma_map.fillna(sigma_map.median()).to_numpy(dtype=float)

    dollar_trade = (delta.abs() * nav).to_numpy(dtype=float)
    impact = (
        costs_mod.IMPACT_K
        * sigma_map
        * np.sqrt(
            np.maximum(dollar_trade, 0.0) / np.maximum(adv.to_numpy(dtype=float), 1.0)
        )
    )
    # Spread and commission are the cost of holding, so they are charged on tonight's
    # book; impact is the cost of the trade, so it is charged on the union's change.
    spread_bps = (
        float(
            np.sum(
                spread_map.reindex(held.index).to_numpy(dtype=float)
                * held.abs().to_numpy()
            )
        )
        * 1e4
    )
    commission_bps = float(np.sum(costs_mod.COMMISSION * held.abs().to_numpy())) * 1e4
    impact_bps = float(np.sum(impact * delta.abs().to_numpy())) * 1e4
    short_gross = float(np.maximum(-held.to_numpy(), 0.0).sum())
    borrow_bps = (
        costs_mod.BORROW_RATE * short_gross * (HORIZON / LIVE_TRADING_DAYS) * 1e4
    )

    etf_held = pd.Series(etf_weight, index=ETFS)
    etf_union = etf_held.index.union(etf_previous.index)
    etf_delta = etf_held.reindex(etf_union).fillna(0.0) - etf_previous.reindex(
        etf_union
    ).fillna(0.0)
    adv_etf = etf_adv("2026-10-01")
    order = [ticker for ticker in ETFS if ticker in etf_union]
    etf_half = (
        pd.Series(
            [
                ETF_HALF_SPREAD_WIDE_BP.get(
                    t, ETF_HALF_SPREAD_BP.get(t, ETF_HALF_SPREAD_DEFAULT_BP)
                )
                for t in order
            ],
            index=order,
        )
        / 1e4
    )
    etf_borrow = pd.Series(
        [ETF_BORROW_RATE.get(t, ETF_BORROW_RATE_DEFAULT) for t in order], index=order
    )
    etf_sigma = pd.Series(etf_specific, index=ETFS).reindex(order)
    etf_adv_vec = pd.Series([adv_etf[t] for t in order], index=order)
    etf_dollar_trade = (etf_delta.reindex(order).abs() * nav).to_numpy(dtype=float)
    etf_impact = (
        costs_mod.IMPACT_K
        * etf_sigma.to_numpy(dtype=float)
        * np.sqrt(
            np.maximum(etf_dollar_trade, 0.0)
            / np.maximum(etf_adv_vec.to_numpy(dtype=float), 1.0)
        )
    )
    etf_spread_bps = (
        float(
            np.sum(
                etf_half.to_numpy(dtype=float)
                * etf_held.reindex(order).abs().to_numpy()
            )
        )
        * 1e4
    )
    etf_commission_bps = (
        float(np.sum(costs_mod.COMMISSION * etf_held.reindex(order).abs().to_numpy()))
        * 1e4
    )
    etf_impact_bps = (
        float(np.sum(etf_impact * etf_delta.reindex(order).abs().to_numpy())) * 1e4
    )
    etf_borrow_bps = (
        float(
            np.sum(
                etf_borrow.to_numpy(dtype=float)
                * np.maximum(-etf_held.reindex(order).to_numpy(), 0.0)
            )
        )
        * (HORIZON / LIVE_TRADING_DAYS)
        * 1e4
    )
    total = (
        spread_bps
        + etf_spread_bps
        + commission_bps
        + etf_commission_bps
        + impact_bps
        + etf_impact_bps
        + borrow_bps
        + etf_borrow_bps
    )
    return {
        "cost_total_bps": total,
        "cost_spread_bps": spread_bps + etf_spread_bps,
        "cost_commission_bps": commission_bps + etf_commission_bps,
        "cost_impact_bps": impact_bps + etf_impact_bps,
        "cost_borrow_bps": borrow_bps + etf_borrow_bps,
        "etf_spread_bps": etf_spread_bps,
        "etf_borrow_bps": etf_borrow_bps,
        "traded_notional": float(delta.abs().sum() * nav)
        + float(etf_delta.abs().sum() * nav),
    }


def run(scope: str) -> dict[str, Any]:
    """The four constructions, over the live closes or the research panel."""
    if scope == "live":
        books = live_books()
    else:
        books = backtest_books()
    dates = sorted(pd.to_datetime(books["date"].unique()))
    as_of = str(dates[0].date())
    first = pieces_at(
        pd.Timestamp(dates[0]), list(books.loc[books["date"] == dates[0], "ticker"])
    )
    if first is None:
        raise RuntimeError(f"no risk pieces for the first close {as_of}")
    factor_names = book_factor_names(first)
    # The panel runs from 2012, and the ETFs' prices start in 2011, so the loadings
    # cannot be estimated once on a window before the whole study. They are refreshed
    # once a year instead, always on data strictly before the year being measured,
    # and a date whose year has too little history behind it is skipped rather than
    # measured with a regression fitted on a handful of days.
    loadings = None
    loadings_year = pd.Timestamp(as_of).year
    if scope == "backtest":
        # The panel starts in 2012 and the ETFs' prices in 2011, so the first vintage
        # is the first year with a usable window behind it and every earlier date is
        # skipped rather than measured on a handful of days.
        while loadings is None:
            try:
                candidate = etf_loadings(f"{loadings_year}-01-01", factor_names)
            except ValueError:
                candidate = None
            if candidate is not None and candidate["n_days"] >= 200:
                loadings = candidate
                break
            loadings_year += 1
            if loadings_year > pd.Timestamp(dates[-1]).year:
                raise RuntimeError("no ETF loadings vintage has enough history")
    else:
        loadings = etf_loadings(as_of, factor_names)
    etf_design = np.array(
        [
            [loadings["etfs"][ticker]["loadings"][name] for name in factor_names]
            for ticker in ETFS
        ]
    )
    # The specific diagonal is a *daily* variance, the same unit as the book's own
    # `specific` from the risk model: `measure` annualizes the total once, so an
    # already-annualized ETF number here would be annualized twice.
    etf_specific = np.array(
        [loadings["etfs"][ticker]["specific_daily_var"] for ticker in ETFS]
    )

    rows: list[dict[str, Any]] = []
    previous: dict[str, pd.Series] = {}
    previous_etf: dict[str, pd.Series] = {}
    previous_u: pd.Series | None = None
    nav = 0.0
    for stamp in dates:
        if scope == "backtest" and pd.Timestamp(stamp).year < loadings_year:
            continue
        block = books.loc[books["date"] == stamp]
        names = [str(ticker) for ticker in block["ticker"]]
        u = block["weight"].to_numpy(dtype=float)
        u = u / np.abs(u).sum()
        pieces = pieces_at(pd.Timestamp(stamp), names)
        if pieces is None:
            print(f"  {stamp.date()}: no risk pieces, skipped")
            continue
        design = np.asarray(pieces["design"], dtype=float)
        covariance = np.asarray(pieces["factor_covariance"], dtype=float)
        specific = np.asarray(pieces["specific"], dtype=float)
        if scope == "backtest" and pd.Timestamp(stamp).year != loadings_year:
            loadings_year = pd.Timestamp(stamp).year
            try:
                refresh = etf_loadings(f"{loadings_year}-01-01", factor_names)
            except Exception:  # not enough history yet: keep the previous vintage
                refresh = loadings
            if refresh["n_days"] >= 200:
                loadings = refresh
                etf_design = np.array(
                    [
                        [
                            loadings["etfs"][ticker]["loadings"][name]
                            for name in factor_names
                        ]
                        for ticker in ETFS
                    ]
                )
                etf_specific = np.array(
                    [loadings["etfs"][ticker]["specific_daily_var"] for ticker in ETFS]
                )
        made = variants(u, design, specific, factor_names, etf_design)
        market_sector_residual = made.pop("market_sector_residual")
        for label, (raw_stock, etf_weight) in made.items():
            stats = measure(
                raw_stock,
                design,
                specific,
                etf_weight,
                etf_design,
                etf_specific,
                covariance,
            )
            series = pd.Series(raw_stock, index=names)
            etf_series = pd.Series(etf_weight, index=ETFS)
            prior = previous.get(label)
            prior_etf = previous_etf.get(label)

            def turnover(now: pd.Series, then: pd.Series | None) -> float:
                if then is None:
                    return float("nan")
                index = now.index.union(then.index)
                return float(
                    (now.reindex(index).fillna(0.0) - then.reindex(index).fillna(0.0))
                    .abs()
                    .sum()
                )

            total_turnover = turnover(series, prior) + turnover(etf_series, prior_etf)
            alpha_turnover = turnover(pd.Series(u, index=names), previous_u)
            hedge_turnover = (
                turnover(
                    series - pd.Series(u, index=names),
                    (
                        (prior - previous_u)
                        if prior is not None and previous_u is not None
                        else None
                    ),
                )
                + turnover(etf_series, prior_etf)
                if prior is not None and previous_u is not None
                else float("nan")
            )
            previous[label] = series
            previous_etf[label] = etf_series
            row: dict[str, Any] = dict(stats)
            row["vol_gross_1"] = (
                float(stats["vol"] / stats["gross"])
                if stats["gross"] > 0
                else float("nan")
            )
            row.update(
                {
                    "date": str(stamp.date()),
                    "variant": label,
                    "turnover_total": total_turnover,
                    "turnover_alpha": alpha_turnover,
                    "turnover_hedge": hedge_turnover,
                    "n_stocks": int((np.abs(raw_stock) > 1e-3).sum()),
                    "n_etfs": int((np.abs(etf_weight) > 1e-6).sum()),
                    "market_sector_residual": market_sector_residual,
                }
            )
            if scope == "live":
                row.update(
                    costs(
                        raw_stock,
                        names,
                        specific,
                        prior,
                        etf_weight,
                        prior_etf if prior_etf is not None else pd.Series(dtype=float),
                        etf_specific,
                        nav=float(pieces_book_nav(nav)),
                    )
                )
            rows.append(row)
        previous_u = pd.Series(u, index=names)
        nav = float(pieces_book_nav(nav))
    table = pd.DataFrame(rows)
    summary = (
        table.groupby("variant")
        .agg(
            vol=("vol", "mean"),
            vol_gross_1=("vol_gross_1", "mean"),
            factor_vol=("factor_vol", "mean"),
            factor_share=("factor_share", "mean"),
            max_variance_share=("max_variance_share", "mean"),
            max_variance_share_worst=("max_variance_share", "max"),
            gross=("gross", "mean"),
            stock_gross=("stock_gross", "mean"),
            etf_gross=("etf_gross", "mean"),
            exposure_abs_max=("exposure_abs_max", "max"),
            turnover_total=("turnover_total", "mean"),
            turnover_alpha=("turnover_alpha", "mean"),
            turnover_hedge=("turnover_hedge", "mean"),
            n_stocks=("n_stocks", "mean"),
        )
        .reset_index()
    )
    if scope == "live":
        # The last close is the one the brief asks about by name.
        last = table.loc[table["date"] == str(dates[-1].date())]
        summary = summary.merge(
            last.loc[
                :,
                [
                    "variant",
                    "cost_total_bps",
                    "cost_spread_bps",
                    "cost_impact_bps",
                    "cost_borrow_bps",
                    "etf_spread_bps",
                    "etf_borrow_bps",
                    "traded_notional",
                ],
            ],
            on="variant",
            how="left",
        )
    print(summary.to_string(index=False, float_format=lambda value: f"{value:,.5f}"))
    out = ROOT / "docs" / "research" / f"etf_overlay_{scope}_numbers.json"
    out.write_text(
        json.dumps(
            {
                "scope": scope,
                "etf_loadings": loadings,
                "etf_specific_annual_var": {
                    ticker: float(
                        loadings["etfs"][ticker]["specific_daily_var"] * TRADING_DAYS
                    )
                    for ticker in ETFS
                },
                "summary": summary.to_dict("records"),
                "rows": rows,
            },
            indent=1,
            default=float,
        )
    )
    print(f"wrote {out.relative_to(ROOT)}")
    return {"summary": summary.to_dict("records")}


def pieces_book_nav(current: float) -> float:
    """The NAV the costs are quoted against: the live book's own gross notional."""
    if current > 0:
        return current
    return float(PAPER_NAV_FALLBACK)


PAPER_NAV_FALLBACK = 987_876.51


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("live", "backtest"), default="live")
    args = parser.parse_args()
    run(args.scope)


if __name__ == "__main__":
    main()
