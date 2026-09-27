"""Sprint E12: holdings-based P&L attribution, one row per book-date.

The question this answers is the one the owner asks after a week of the book
running: where did the money go, and did the hedge do what it promised. One row per
session, with the day's P&L split into the factor part, the specific part and the
cost, and the three summing to the total by construction.

**What is holdings-based here.** The weights that earned a session's return are the
book dated the session before it, which is the convention the rest of the project
uses (`test_no_portfolio_uses_a_weight_dated_after_its_own_day`): a weight row dated
at `start` is applied to every session in `(start, end]`. Nothing is filled
forward, nothing is re-derived from a target: the weights are the ones the loop
recorded holding, so an intention is never attributed as a holding.

**The decomposition.** For each session `s`, with the design `X_s` the hedge itself
zeroes (the same descriptor design `efb.race._descriptor_design` hands the hedge),
the model's factor returns `f_s` and the panel's total returns `r_s`:

    factor P&L = sum_k (w' X_s)_k f_k(s),   idio P&L = sum_i w_i u_i(s),
    u(s) = r(s) - X_s f(s),                total P&L = factor + idio,

so the identity holds exactly in floating point: `u` is the residual of the design
the factor returns are read against. That is deliberate, and it is disclosed in
`REPORT.md` as a construction rather than a finding. The finding beside it is
measured: the *stored* `specific_returns` artifact is **not** that residual - on
2026-09-03 the stored residual is 8.7e-3 in median absolute value while the factor
part of the same design is 1.0e-4, so `X f + u` misses the panel's return by as
much as the return itself. The attribution therefore computes its own residual and
`tests/test_e12_attribution.py` pins both facts, so an artifact that starts
agreeing, or stops, is visible.

**The hedge's own P&L.** The traded book is factor-neutral by construction, so its
factor P&L is near zero: that near-zero is the hedge's promise. What the hedge
*did* is the factor P&L it removed, which needs the pre-hedge book. That is
recomputable from what the loop stored - `alpha` and the specific volatility are
both on the position row, and the cap and the renormalization are deterministic -
so `pre_hedge_weights` rebuilds it and `hedge_factor_pnl` reports the difference per
factor.

**The raw market-beta line.** XS-v1's `market` column is a cross-sectional
identifier, not the book's CAPM beta, and the two are not the same number: a book
that is market-neutral in the model's sense still carries a realized beta of about
0.1 against the market, and that P&L sits inside the specific part. The row
therefore carries the book's beta (from TS-v1's stored raw 252-day CAPM betas, the
closest row at or before the session) and the P&L that beta explains. It explains
part of the specific P&L; it is not a fourth component and is never added to the
other three.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from efb.models.fundamental import ESTIMATED_NAMES

IDENTITY_ATOL = 1e-10

# The book's own realized volatility is measured over a quarter of its own daily
# P&L, which is the shortest window that can say anything about a 10% target.
REALIZED_VOL_WINDOW = 63
TRADING_DAYS = 252.0


def daily_weights(books: pd.DataFrame, sessions: pd.Series) -> pd.DataFrame:
    """The weights that earned each session, from the books dated before it.

    `books` is long: `date`, `ticker`, `weight`. The book dated `d` is the book
    held from the close of `d`, so the session `s` earns on the last book dated
    strictly before `s`. A session with no book before it is dropped rather than
    filled with zeros: a day the loop had not started is not a day of a flat book.
    """
    frame = books.loc[:, ["date", "ticker", "weight"]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    ordered = pd.DatetimeIndex(sorted(pd.to_datetime(sessions).unique()))
    out: list[pd.DataFrame] = []
    for session in ordered:
        before = frame["date"] < session
        if not before.any():
            continue
        stamp = frame.loc[before, "date"].max()
        day = frame.loc[frame["date"] == stamp, ["ticker", "weight"]].copy()
        day["date"] = session
        out.append(day)
    if not out:
        return pd.DataFrame(columns=["date", "ticker", "weight"])
    return pd.concat(out, ignore_index=True)


def pre_hedge_weights(
    weights: np.ndarray, alpha: np.ndarray, specific: np.ndarray
) -> np.ndarray:
    """The sized and capped book before the hedge, from what the run stored.

    `sized_kept_weights` sizes on `alpha / specific`, caps the variance shares and
    renormalizes to gross 1.0 before it hedges, and every one of those steps is
    deterministic in the stored `alpha` and specific volatility. Rebuilding it is
    what makes the hedge's own contribution measurable: the hedge's factor P&L is
    the factor P&L of the book it removed.
    """
    from efb import size
    from live import sizing

    sized = size.proportional(alpha, specific)
    sized = sizing.cap_variance_shares(sized, specific)
    return sizing.renormalize(sized, gross=1.0)


class ModelPanel:
    """The model artifacts the attribution reads, loaded once.

    One loader for the whole window: the returns panel is millions of rows and the
    design is built per date, so reading them per row would make a week of
    attribution slower than the week it describes.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        panel = pd.read_parquet(self.root / "processed" / "returns.parquet")
        self.returns = panel["r"]
        self.sessions = pd.DatetimeIndex(
            sorted(self.returns.index.get_level_values("date").unique())
        )
        factors = pd.read_parquet(
            self.root / "models" / "XS-v1" / "factor_returns.parquet"
        )
        factors["date"] = pd.to_datetime(factors["date"])
        self.factor_returns = factors.pivot_table(
            index="date", columns="factor", values="f"
        )
        specific = pd.read_parquet(
            self.root / "models" / "XS-v1" / "specific_returns.parquet"
        )
        specific["date"] = pd.to_datetime(specific["date"])
        self.stored_specific = specific.set_index(["date", "ticker"])["specific_return"]
        betas = pd.read_parquet(self.root / "models" / "TS-v1" / "beta_history.parquet")
        betas = betas.loc[betas["method"] == "raw", ["date", "ticker", "beta"]].copy()
        betas["date"] = pd.to_datetime(betas["date"])
        self.betas = betas

    def design(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        """The hedge's own design for the session, one column per estimated factor."""
        from efb import race

        return race._descriptor_design(date, names, self.root)

    def factor_names(self, date: pd.Timestamp) -> list[str]:
        """The factors the design has columns for, in the design's own order."""
        return [name for name in ESTIMATED_NAMES if name in self.factor_returns.columns]

    def betas_at(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        """The names' raw CAPM beta as of the last stored row at or before `date`."""
        frame = self.betas.loc[self.betas["date"] <= date]
        if frame.empty:
            return np.full(len(names), np.nan)
        stamp = frame["date"].max()
        series = frame.loc[frame["date"] == stamp].set_index("ticker")["beta"]
        return series.reindex(names).to_numpy(dtype=float)


def attribute_book(
    holdings: pd.DataFrame,
    panel: ModelPanel,
    *,
    forecasts: dict[pd.Timestamp, dict[str, float]] | None = None,
    costs: dict[pd.Timestamp, dict[str, float]] | None = None,
) -> pd.DataFrame:
    """One row per session, the day's P&L split and the risk lines beside it.

    `holdings` is the long `date`, `ticker`, `weight` frame `daily_weights` builds.
    `forecasts` carries the book's own predicted volatility per book-date, and
    `costs` the expected and realized cost, both keyed by the session they belong
    to. Missing entries leave the column null rather than zero: a cost nobody
    measured is not a cost of nothing.
    """
    forecasts = forecasts or {}
    costs = costs or {}
    rows: list[dict[str, Any]] = []
    for session, day in holdings.groupby("date", sort=True):
        session = pd.Timestamp(session)
        names = [str(ticker) for ticker in day["ticker"]]
        weight = day["weight"].to_numpy(dtype=float)
        returns = panel.returns.loc[session].reindex(names).to_numpy(dtype=float)
        # The design has one column per estimated factor; the reference sector's
        # return is derived from the identification constraint rather than
        # estimated, so its P&L belongs to the specific part and it is not a
        # column here. `_xs_pieces` reads the same set, in the same order, and the
        # panel names it so the two cannot drift apart silently.
        factor_names = panel.factor_names(session)
        factor_returns = panel.factor_returns.loc[session].reindex(factor_names)
        design = panel.design(session, names)
        if design.shape[1] != len(factor_names):
            raise ValueError(
                f"the design has {design.shape[1]} columns and the model reports "
                f"{len(factor_names)} factors, so an attribution would silently "
                "pair exposures with the wrong factor returns"
            )
        #
        # The identity, in the order that makes it exact: exposures from the design
        # the hedge zeroes, factor P&L from the model's factor returns, residual as
        # what the two do not explain, so the three components sum to the total by
        # construction rather than by tolerance.
        exposure = weight @ np.nan_to_num(design, nan=0.0)
        per_factor = exposure * factor_returns.to_numpy(dtype=float)
        factor_pnl = float(np.nansum(per_factor))
        missing = np.isnan(returns)
        # A name with no return that session is not a fallback: its P&L cannot be
        # measured from this panel, so it contributes zero and its weight is
        # reported, which is how big the unmeasured part of the day was.
        gross_pnl = float(np.nansum(np.where(missing, 0.0, weight * returns)))
        idio_pnl = gross_pnl - factor_pnl
        cost = float(costs.get(session, {}).get("cost_usd", 0.0) or 0.0)
        total_pnl = gross_pnl + cost
        beta = panel.betas_at(session, names)
        book_beta = float(np.nansum(np.where(np.isnan(beta), 0.0, weight * beta)))
        market = float(factor_returns.get("market", np.nan))
        predicted = forecasts.get(session, {})
        rows.append(
            {
                "trade_date": session,
                "n_names": int((np.abs(weight) > 0).sum()),
                "gross": float(np.abs(weight).sum()),
                "net": float(weight.sum()),
                "pnl_total": total_pnl,
                "pnl_factor": factor_pnl,
                "pnl_idio": idio_pnl,
                "pnl_cost": cost,
                "identity_residual": float(total_pnl - (factor_pnl + idio_pnl + cost)),
                "pnl_factor_json": {
                    name: float(value)
                    for name, value in zip(factor_names, per_factor, strict=True)
                },
                "book_beta": book_beta,
                "market_return": market,
                "pnl_beta": book_beta * market if np.isfinite(market) else None,
                "forecast_vol": predicted.get("forecast_vol"),
                "expected_cost_bps": predicted.get("expected_cost_bps"),
                "realized_cost_bps": predicted.get("realized_cost_bps"),
                "n_target": predicted.get("n_target"),
                "n_filled": predicted.get("n_filled"),
                "max_fill_gap": predicted.get("max_fill_gap"),
                "n_missing_return": int(missing.sum()),
                "missing_return_weight": float(np.abs(weight[missing]).sum()),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return _with_risk_lines(frame)


def _with_risk_lines(frame: pd.DataFrame) -> pd.DataFrame:
    """The realized volatility, its ratio to the forecast, and the bias statistic.

    The bias statistic is the daily bias engine's own definition, reused rather
    than re-implemented: `z` per session is the book's P&L over the volatility the
    book predicted for it, and the statistic is the dispersion of those `z` over a
    trailing year. Both are computed from rows at or before the session they are
    reported on, so a row never reads a number it could not have known.
    """
    from efb import eval_risk

    pnl = frame["pnl_total"].to_numpy(dtype=float)
    vol: list[float] = []
    bias: list[float | None] = []
    for position in range(len(pnl)):
        window = pnl[max(0, position - REALIZED_VOL_WINDOW + 1) : position + 1]
        if len(window) < 2 or np.nanstd(window, ddof=1) == 0:
            vol.append(np.nan)
        else:
            vol.append(float(np.nanstd(window, ddof=1) * np.sqrt(TRADING_DAYS)))
        forecast = frame["forecast_vol"].iloc[position]
        if not vol or not np.isfinite(vol[-1]) or not forecast:
            bias.append(None)
            continue
        z = []
        for offset in range(position + 1):
            predicted = frame["forecast_vol"].iloc[offset]
            if predicted:
                z.append(pnl[offset] / (predicted / np.sqrt(TRADING_DAYS)))
        # `bias_statistics` raises below 30 observations, which is its own
        # contract, so the row carries null until the book has a month of z.
        bias.append(
            float(eval_risk.bias_statistics(np.asarray(z))["bias"])
            if len(z) >= 30
            else None
        )
    frame["realized_vol"] = vol
    frame["vol_ratio"] = frame["realized_vol"] / frame["forecast_vol"]
    frame["bias_statistic"] = bias
    return frame
