"""Build the E12 attribution artifacts from a stored book, and measure the concepts.

Run:

    .venv/bin/python scripts/build_attribution.py

Writes `data/attribution/daily.parquet` (one row per session), `monthly.parquet`
(the same rows aggregated by month) and `timeseries.parquet` (the returns-based
cross-check: the book's own daily P&L regressed on the factor returns), then prints
the three measurements the sprint's report quotes:

1. the reconciliation residual, `total - (factor + idio + cost)`, per session;
2. the hedge timing gap: the book's factor exposure under the design dated the
   session against the design at the close the book was built, and the P&L that
   difference produces;
3. whether the session-dated design is computable a close earlier, measured on the
   size column: its correlation with the same day's market cap against the previous
   day's.

A book is a stored weight series - the seed's own `data/portfolios` book by default -
so the live run later swaps the input and nothing else.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from efb import attribution

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOOK = ROOT / "data" / "portfolios" / "mv_constrained.parquet"
OUT_ROOT = ROOT / "data" / "attribution"


def load_book(path: Path, rho: float, seed: int, start: str | None) -> pd.DataFrame:
    """One book out of a stored portfolio artifact, renormalized to unit gross."""
    frame = pd.read_parquet(path)
    frame = frame.loc[(frame["rho"] == rho) & (frame["seed"] == seed)].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    if start:
        frame = frame.loc[frame["date"] >= pd.Timestamp(start)]
    gross = frame.groupby("date")["weight"].transform(lambda column: column.abs().sum())
    frame["weight"] = frame["weight"] / gross
    return frame.loc[:, ["date", "ticker", "weight"]]


def monthly(daily: pd.DataFrame) -> pd.DataFrame:
    """The daily rows aggregated by month: the same numbers, summed by period."""
    frame = daily.copy()
    frame["month"] = pd.to_datetime(frame["trade_date"]).dt.to_period("M").astype(str)
    numeric = [
        column
        for column in frame.columns
        if frame[column].dtype.kind == "f" and column != "identity_residual"
    ]
    grouped = frame.groupby("month").agg(
        {**{column: "sum" for column in numeric}, "identity_residual": "sum"}
    )
    grouped["n_sessions"] = frame.groupby("month").size()
    return grouped.reset_index()


def timeseries(daily: pd.DataFrame, panel: attribution.ModelPanel) -> pd.DataFrame:
    """The returns-based cross-check: book P&L regressed on the factor returns.

    The point of running both estimators is that they answer different questions -
    the holdings view knows what the book held, the regression only sees what it
    earned - and the sprint compares the fitted betas with the average
    holdings-based exposures. The betas are ordinary least squares with an
    intercept, and each one carries its own standard error.
    """
    dates = [pd.Timestamp(day) for day in daily["trade_date"]]
    factors = panel.factor_returns.reindex(dates).fillna(0.0)
    y = daily["pnl_total"].to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(dates)), factors.to_numpy(dtype=float)])
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    residual = y - x @ beta
    dof = max(len(dates) - x.shape[1], 1)
    sigma2 = float(residual @ residual) / dof
    covariance = sigma2 * np.linalg.pinv(x.T @ x)
    error = np.sqrt(np.diag(covariance))
    rows = [
        {"term": "intercept", "beta": float(beta[0]), "se": float(error[0])},
        {
            "term": "realized_vol",
            "beta": float(np.std(residual, ddof=1) * np.sqrt(attribution.TRADING_DAYS)),
            "se": float("nan"),
        },
    ]
    for position, name in enumerate(factors.columns, start=1):
        rows.append(
            {"term": name, "beta": float(beta[position]), "se": float(error[position])}
        )
    frame = pd.DataFrame(rows)
    # The holdings view's average exposure over the same sessions, for the compare.
    exposures = pd.DataFrame(list(daily["exposure_json"])).mean()
    frame["holdings_exposure"] = frame["term"].map(exposures)
    frame["within_one_se"] = (
        (frame["beta"] - frame["holdings_exposure"]).abs() <= frame["se"]
    )
    return frame


def timing(daily: pd.DataFrame) -> pd.DataFrame:
    """The exposure gap between the two design vintages, per factor."""
    session = pd.DataFrame(list(daily["exposure_json"]))
    book = pd.DataFrame(list(daily["book_exposure_json"]))
    gap = session - book
    return pd.DataFrame(
        {
            "factor": session.columns,
            "mean_session_exposure": session.mean().to_numpy(),
            "mean_book_exposure": book.mean().to_numpy(),
            "mean_gap": gap.mean().to_numpy(),
            "max_abs_gap": gap.abs().max().to_numpy(),
        }
    )


def size_column_check(panel: attribution.ModelPanel, daily: pd.DataFrame) -> dict:
    """Is the session-dated design computable one close earlier?

    Measured on the size column, which the model's own `shift_test` documents as the
    log of market capitalisation at the session - that is, the previous cap times one
    plus the return being explained - so its contents were not knowable before the
    session. The correlation with the same day's cap against the previous day's says
    which one it actually carries.
    """
    prices = pd.read_parquet(ROOT / "data" / "raw" / "prices.parquet")
    close = prices["close"].unstack("ticker")
    shares = pd.read_parquet(ROOT / "data" / "raw" / "shares_history.parquet")
    shares = shares.pivot_table(index="date", columns="ticker", values="shares")
    shares = shares.reindex(close.index).ffill()
    from efb.models import fundamental as fx

    mcap = fx.market_cap(close, shares)
    date = pd.Timestamp(daily["trade_date"].iloc[-1])
    previous = panel.sessions[panel.sessions < date][-1]
    names = sorted(panel.returns.loc[date].dropna().index)
    design = panel.raw_design(date, names)
    size = design[:, 1]  # the size column, in the design's own order
    same = np.log(mcap.loc[date].reindex(names).to_numpy(dtype=float))
    lagged = np.log(mcap.loc[previous].reindex(names).to_numpy(dtype=float))
    ok = np.isfinite(size) & np.isfinite(same) & np.isfinite(lagged)
    return {
        "date": str(date.date()),
        "correlation_with_same_day_cap": float(np.corrcoef(size[ok], same[ok])[0, 1]),
        "correlation_with_previous_close_cap": float(
            np.corrcoef(size[ok], lagged[ok])[0, 1]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", type=Path, default=DEFAULT_BOOK)
    parser.add_argument("--rho", type=float, default=0.02)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--start", default=None)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    args = parser.parse_args()

    panel = attribution.ModelPanel(args.data_root)
    books = load_book(args.book, args.rho, args.seed, args.start)
    sessions = pd.Series(
        [
            day
            for day in panel.sessions
            if books["date"].min() < day <= books["date"].max()
        ]
    )
    holdings = attribution.daily_weights(books, sessions)
    daily = attribution.attribute_book(holdings, panel)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    monthly_frame = monthly(daily)
    timeseries_frame = timeseries(daily, panel)
    daily.to_parquet(OUT_ROOT / "daily.parquet", index=False)
    monthly_frame.to_parquet(OUT_ROOT / "monthly.parquet", index=False)
    timeseries_frame.to_parquet(OUT_ROOT / "timeseries.parquet", index=False)

    gap = timing(daily)
    residual = daily["identity_residual"].abs()
    print(f"sessions attributed: {len(daily)} "
          f"({daily['trade_date'].min().date()} to "
          f"{daily['trade_date'].max().date()})")
    print(f"reconciliation |total - (factor + idio + cost)|: "
          f"median {residual.median():.3e} max {residual.max():.3e}")
    print(f"cumulative P&L: total {daily['pnl_total'].sum():.6f} = factor "
          f"{daily['pnl_factor'].sum():.6f} + idio {daily['pnl_idio'].sum():.6f} + "
          f"cost {daily['pnl_cost'].sum():.6f}")
    print(f"hedge timing: mean |gap| {gap['max_abs_gap'].max():.3e} max, "
          f"mean per factor {gap['mean_gap'].abs().mean():.3e}, "
          f"timing P&L sum {daily['pnl_timing'].sum():.6f}")
    print("largest exposure gaps:")
    print(gap.reindex(gap["mean_gap"].abs().sort_values(ascending=False).index).head(5).to_string(index=False))
    print("size column: " + json.dumps(size_column_check(panel, daily)))
    print(f"timeseries: {int(timeseries_frame['within_one_se'].sum())} of "
          f"{len(timeseries_frame)} terms agree with the holdings view within one SE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
