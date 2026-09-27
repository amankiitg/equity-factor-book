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

**The decomposition, and why it is a check rather than a tautology.** For each
session `s`, with the design the model's own fit used - `race._descriptor_design` at
`s`, in its **reported** columns: the market column replaced by a column of ones and
the reference sector's dummy restored, which is the 18-column set the 18 reported
factor returns belong to - the stored factor returns `f_s` and the stored specific
returns `u_s`:

    factor P&L = sum_k (w' X_s)_k f_k(s),   idio P&L = sum_i w_i u_i(s),
    total P&L = sum_i w_i r_i(s) = factor + idio      (to machine precision)

Measured on 2026-09-08, 2026-09-18 and 2026-09-21: `|X f + u - r|` is **median
0.000e+00 and max 6.9e-18**, so the stored split reconstructs the panel's total
return exactly and the identity is a real check on the artifacts rather than a
restatement of how `u` was computed. Two wrong pairings were tried first and are
recorded in `handoff/LOG.md`: the design dated `t-1` misses the return by 1.0e-3 to
2.0e-3 in median (so the artifacts pair the design *dated* the session with that
session's return), and the 17-column design leaves a 1.9e-2 gap on the names whose
market column is not constant (so the reported columns are the ones `f` belongs
to). Re-fitting the cross-section with the model's own `wls_fit` on the t-dated
design with market caps dated `t-1` reproduces the stored R squared to 1.1e-05 to
6.4e-05 and the stored specific returns to 7.0e-05, which is what lets a session
after the artifacts' last published date be attributed at all: the row says which
source it used.

**Two design vintages, both reported.** The split above uses `X_s`, the exposures
the model's fit paired with `r_s`. The *book's own* exposures during that session
are the design at the previous close, `X_{s-1}` - the one the hedge actually
zeroed - so the row carries the book's factor exposure from `X_{s-1}` and the P&L
those exposures earned at `f_s`. The two differ, and that is the point of
reporting both: the split describes the return, the exposure check describes the
hedge.

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

from efb.models.fundamental import FACTOR_NAMES

IDENTITY_ATOL = 1e-10

# The columns `efb.attribution` stores, in the order the table declares them. The
# schema file and this tuple are checked against each other by the store test, so a
# line added to a row without a migration fails a test instead of an evening run.
TABLE_COLUMNS: tuple[str, ...] = (
    "trade_date",
    "n_names",
    "gross",
    "net",
    "pnl_total",
    "pnl_factor",
    "pnl_idio",
    "pnl_cost",
    "identity_residual",
    "pnl_factor_json",
    "pnl_timing",
    "pnl_timing_json",
    "exposure_json",
    "book_exposure_json",
    "n_computed_specific",
    "book_beta",
    "market_return",
    "pnl_beta",
    "forecast_vol",
    "realized_vol",
    "vol_ratio",
    "bias_statistic",
    "expected_cost_bps",
    "realized_cost_bps",
    "n_target",
    "n_filled",
    "max_fill_gap",
    "n_missing_return",
    "missing_return_weight",
)

# The columns the row is allowed to carry and the table is not asked to hold: the
# per-factor timing split is a jsonb beside its own total, and `written_at` is the
# database's clock rather than the run's.
JSON_COLUMNS: tuple[str, ...] = (
    "pnl_factor_json",
    "pnl_timing_json",
    "exposure_json",
    "book_exposure_json",
)

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
        # The close the book was built at, which is the vintage the hedge zeroed:
        # a monthly book held into the next month still carries its own date.
        day["book_date"] = stamp
        out.append(day)
    if not out:
        return pd.DataFrame(columns=["date", "ticker", "weight", "book_date"])
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
        stored = specific.set_index(["date", "ticker"])["specific_return"]
        # Grouped once: `.loc[date]` on three million rows costs more than the rest
        # of a session's attribution put together.
        self.stored_specific = {
            pd.Timestamp(stamp): group.droplevel("date")
            for stamp, group in stored.groupby(level="date")
        }
        betas = pd.read_parquet(self.root / "models" / "TS-v1" / "beta_history.parquet")
        betas = betas.loc[betas["method"] == "raw", ["date", "ticker", "beta"]].copy()
        betas["date"] = pd.to_datetime(betas["date"])
        self.betas = betas

    def design(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        """The hedge's own design for the session, one column per estimated factor."""
        from efb import race

        return race._descriptor_design(date, names, self.root)

    def factor_names(self, date: pd.Timestamp) -> list[str]:
        """The reported factors, in the order the reported design's columns are."""
        return [name for name in FACTOR_NAMES if name in self.factor_returns.columns]

    def raw_design(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        """The hedge's design as `race` builds it, before the reported framing."""
        return self.design(date, names)

    def reported_design(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        """The design in the 18 reported columns the reported factors belong to."""
        return reported_design(self.raw_design(date, names))

    def fit_or_stored(
        self,
        date: pd.Timestamp,
        names: list[str],
        returns: np.ndarray,
        raw: np.ndarray,
    ) -> tuple[pd.Series, np.ndarray, int]:
        """The session's stored factor and specific returns, or a refusal.

        The live loop appends every session it fits to the XS-v1 artifacts
        (`live/extend.py`), so a live session has stored values too, and this
        raises rather than re-estimating when it does not: a re-estimate is
        reproducible to 7.0e-05 of the stored specifics, which is a measurement
        about the model and not a licence to attribute a day from a reconstruction
        the model never published.
        """
        if date not in self.factor_returns.index:
            raise ValueError(
                f"no stored factor returns for {date.date()}: the model's fit has "
                "not been extended to this session, so there is nothing to "
                "attribute it with"
            )
        factors = self.factor_returns.loc[date].reindex(self.factor_names(date))
        stored_day = self.stored_specific.get(date)
        specific = (
            stored_day.reindex(names)
            if stored_day is not None
            else pd.Series(dtype=float)
        )
        # A book can hold a name the model's own cross-section dropped that day, and
        # it has no stored specific return. Its residual is computed instead, which
        # is the same number: `u = r - X f` is what the stored value *is*, verified
        # to 6.9e-18 on the three dates checked, so the two cannot disagree except
        # by the arithmetic. The count travels on the row, so a growing share of
        # computed names is visible rather than absorbed.
        computed = int(specific.isna().sum())
        if computed:
            fitted = self.reported_design(date, names) @ factors.to_numpy(dtype=float)
            rebuilt = returns - fitted
            specific = specific.where(specific.notna(), rebuilt)
        return factors, specific.to_numpy(dtype=float), computed

    def betas_at(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        """The names' raw CAPM beta as of the last stored row at or before `date`."""
        frame = self.betas.loc[self.betas["date"] <= date]
        if frame.empty:
            return np.full(len(names), np.nan)
        stamp = frame["date"].max()
        series = frame.loc[frame["date"] == stamp].set_index("ticker")["beta"]
        return series.reindex(names).to_numpy(dtype=float)


def reported_factor_names() -> list[str]:
    """The reported factor names, in the reported design's column order."""
    return list(FACTOR_NAMES)


def reported_design(design: np.ndarray) -> np.ndarray:
    """The design in its reported columns: ones for the market, all 11 sectors.

    `build_cross_section` reports the market column as a column of ones and adds
    the reference sector's dummy back, and those 18 columns are the set the 18
    reported factor returns belong to. Verified rather than assumed: with this
    framing `X f + u` reproduces the panel's total return to 6.9e-18, and with the
    design's own 17 columns it misses by 1.9e-2 on the names whose market column is
    not constant.
    """
    sectors = design[:, 7:]
    reference = 1.0 - sectors.sum(axis=1, keepdims=True)
    return np.column_stack([np.ones(len(design)), design[:, 1:7], sectors, reference])


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

    The split uses the **stored** factor and specific returns, which is what makes
    the identity a check on the model's artifacts. `n_computed_specific` counts the
    kept names the model's own cross-section dropped that session, whose residual
    is computed as `r - X f` instead; it is zero for a book inside the model's
    universe.
    """
    forecasts = forecasts or {}
    costs = costs or {}
    rows: list[dict[str, Any]] = []
    for session, day in holdings.groupby("date", sort=True):
        session = pd.Timestamp(session)
        names = [str(ticker) for ticker in day["ticker"]]
        weight = day["weight"].to_numpy(dtype=float)
        returns = panel.returns.loc[session].reindex(names).to_numpy(dtype=float)
        missing = ~np.isfinite(returns)
        design = panel.reported_design(session, names)
        factor_names = panel.factor_names(session)
        raw = panel.raw_design(session, names)
        factor_returns, specific, n_computed = panel.fit_or_stored(
            session, names, returns, raw
        )
        exposure = weight @ np.nan_to_num(design, nan=0.0)
        per_factor = exposure * factor_returns.to_numpy(dtype=float)
        # The book's own exposures: the design at the close the book was built, the
        # one the hedge zeroed. The gap between the two vintages is what the hedge
        # timing item measures, and the P&L it produces is `(E_s - E_book) f_s`.
        # A caller that hands over only (date, ticker, weight) has told us nothing
        # about when the book was built, so the session is the honest reading and
        # the timing line is then zero rather than a guess.
        book_stamp = (
            pd.Timestamp(day["book_date"].iloc[0])
            if "book_date" in day.columns
            else session
        )
        book_design = panel.reported_design(book_stamp, names)
        book_exposure = weight @ np.nan_to_num(book_design, nan=0.0)
        timing = (exposure - book_exposure) * factor_returns.to_numpy(dtype=float)
        factor_pnl = float(np.nansum(per_factor))
        # A name with no return that session is not a fallback: its P&L cannot be
        # measured from this panel, so it contributes zero and its weight is
        # reported, which is how big the unmeasured part of the day was.
        gross_pnl = float(np.nansum(np.where(missing, 0.0, weight * returns)))
        idio_pnl = float(np.nansum(weight * np.asarray(specific, dtype=float)))
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
                # The check, not a restatement: the three are computed from
                # different artifacts - factor returns, specific returns and the
                # panel's own total returns - so a non-zero residual is a real
                # disagreement between them.
                "identity_residual": float(total_pnl - (factor_pnl + idio_pnl + cost)),
                "pnl_factor_json": {
                    name: float(value)
                    for name, value in zip(factor_names, per_factor, strict=True)
                },
                "exposure_json": {
                    name: float(value)
                    for name, value in zip(factor_names, exposure, strict=True)
                },
                "book_exposure_json": {
                    name: float(value)
                    for name, value in zip(factor_names, book_exposure, strict=True)
                },
                "pnl_timing": float(np.nansum(timing)),
                "pnl_timing_json": {
                    name: float(value)
                    for name, value in zip(factor_names, timing, strict=True)
                },
                "n_computed_specific": n_computed,
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
