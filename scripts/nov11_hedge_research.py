"""The hedge's concentration: three constructions, on the live books and on the backtest.

Read-only. Item 24's research question, plus the turnover and the names each hedge
creates that the item asks for.

    .venv/bin/python scripts/nov11_hedge_research.py --scope live
    .venv/bin/python scripts/nov11_hedge_research.py --scope backtest

The three constructions, all starting from the same sized book `u`:

- **`exact`**: the live hedge. `w = u - X (X'X)^-1 X'u` (`live/sizing.py:24`), the
  unconstrained projection that zeroes the factor exposures with no penalty on
  specific variance.
- **`mv`**: minimum-variance factor neutralization. `w = u - D^-1 X (X' D^-1 X)^-1 X'u`,
  which zeroes the same exposures while putting the correction where the specific
  variance is smallest. This is the hedge the item asks to compare: it is the same
  neutrality with an inverse-specific-variance weighting.
- **`cap_then_rehedge`**: the live cap applied and then neutrality restored, to a
  fixed point (three passes): `w = cap(w); w = w - X (X'X)^-1 X'w`, repeated. The
  item's question is whether both conditions can hold at once, so both are
  measured at the end rather than assumed.

For each construction: hedged annualized vol (`X F X' + D`, the same decomposition
the live loop is built against), the split between factor and specific risk, the
largest single name's share of predicted specific variance, the number of names the
hedge *creates* (|u| < 1e-4 and |w| > 1e-3) or flips, and the turnover the
construction implies at each rebalance.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
TRADING_DAYS = 252
LIVE_START = "2026-10-01"


def live_books() -> tuple[pd.DataFrame, pd.DataFrame]:
    """The live pre-hedge book per close, rebuilt from the stored alpha and variance.

    `efb.positions` carries, per close and name, the `alpha` and the `idio_vol` the
    sizing used, and `efb/attribution.pre_hedge_weights` is the project's own
    reconstruction of the sized-and-capped book the hedge acted on.
    """
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    from live import store

    frame = store.select("positions")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.loc[frame["trade_date"] >= pd.Timestamp(LIVE_START)]
    rows: list[dict[str, object]] = []
    for stamp, group in frame.groupby("trade_date", sort=True):
        group = group.dropna(subset=["alpha", "idio_vol"])
        group = group.loc[group["idio_vol"] > 0]
        alpha = group["alpha"].to_numpy(dtype=float)
        sigma = np.sqrt(group["idio_vol"].to_numpy(dtype=float))
        specific_var = group["idio_vol"].to_numpy(dtype=float)
        from efb import size as size_mod
        from live import sizing

        sized = size_mod.proportional(alpha, sigma)
        sized = sizing.cap_variance_shares(sized, specific_var)
        sized = sizing.renormalize(sized, gross=1.0)
        for ticker, weight in zip(group["ticker"], sized, strict=True):
            rows.append({"date": stamp, "ticker": ticker, "weight": float(weight)})
    return pd.DataFrame(rows), frame


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


def pieces_at(stamp: pd.Timestamp, names: list[str]) -> dict[str, object] | None:
    """Design, factor covariance and specific variance for one close.

    `efb.eval_risk._xs_pieces` is the live loop's own supplier and is used whenever
    it answers, which it does for every stored backtest date. It cannot answer for
    the live closes after the committed panel's end (2026-10-02): it wants the row
    the model will date with the session *after* the close, and that session is not
    in the artifact. For those closes the pieces are rebuilt the same way from the
    row the artifact does carry at or before the close - the same design function,
    the same EWMA covariance over the factor returns strictly before the close and
    the same median-filled diagonal - so a live date is measured with the vintage
    the live tree would have had a day earlier rather than not measured at all.
    """
    from efb import eval_risk, race
    from efb.models import fundamental as fx

    try:
        return eval_risk._xs_pieces(pd.Timestamp(stamp), names, DATA)
    except KeyError:
        pass
    factor_returns = pd.read_parquet(DATA / "models" / "XS-v1" / "factor_returns.parquet")
    factor_returns = factor_returns.loc[pd.to_datetime(factor_returns["date"]) < stamp]
    if factor_returns["date"].nunique() < 126:
        return None
    history = factor_returns.pivot_table(index="date", columns="factor", values="f")
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
    }


def variants(u: np.ndarray, design: np.ndarray, specific: np.ndarray) -> dict[str, np.ndarray]:
    """The three hedged books, all from the same sized vector."""
    from live import sizing

    exposures = design.T @ u
    exact = u + sizing.hedge_exact_robust(design, exposures)
    inverse_var = 1.0 / np.maximum(specific, 1e-12)
    weighted = design * inverse_var[:, None]
    try:
        loadings = np.linalg.solve(design.T @ weighted, exposures)
    except np.linalg.LinAlgError:
        loadings = np.linalg.pinv(design.T @ weighted) @ exposures
    mv = u - weighted @ loadings
    current = exact.copy()
    for _ in range(3):
        current = sizing.cap_variance_shares(current, specific)
        beta = np.linalg.lstsq(design.T @ design, design.T @ current, rcond=None)[0]
        current = current - design @ beta
    return {"exact": exact, "mv": mv, "cap_then_rehedge": current}


def measure(
    weight: np.ndarray, design: np.ndarray, covariance: np.ndarray, specific: np.ndarray
) -> dict[str, float]:
    """Vol, the split, and the largest name's share of predicted specific variance."""
    projected = weight @ design
    factor_var = float(projected @ covariance @ projected)
    idio_var = float(np.sum(weight**2 * specific))
    total = factor_var + idio_var
    shares = weight**2 * specific / total if total > 0 else np.zeros_like(weight)
    return {
        "vol": float(np.sqrt(total * TRADING_DAYS)),
        "factor_share": factor_var / total if total > 0 else float("nan"),
        "max_variance_share": float(np.max(shares)) if len(shares) else float("nan"),
        "exposure_abs_max": float(np.abs(design.T @ weight).max()),
    }


def run(scope: str) -> dict[str, object]:
    frames = live_books()[0] if scope == "live" else backtest_books()
    dates = sorted(pd.to_datetime(frames["date"].unique()))
    print(f"{scope}: {len(dates)} dates {dates[0].date()} -> {dates[-1].date()}")
    previous: dict[str, pd.Series] = {}
    rows: list[dict[str, object]] = []
    for stamp in dates:
        block = frames.loc[frames["date"] == stamp]
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
        for label, raw in variants(u, design, specific).items():
            # The three constructions do not agree on gross - the projection
            # removes a large part of a dollar-neutral book and the inverse-variance
            # correction adds to it - so each is measured at gross 1, which is the
            # only way the volatilities are comparable, and the gross it produced is
            # reported beside it.
            gross_raw = float(np.abs(raw).sum())
            weight = raw / gross_raw if gross_raw > 0 else raw
            stats = measure(weight, design, covariance, specific)
            series = pd.Series(weight, index=names)
            prior = previous.get(label)
            turnover = (
                float(
                    (series.reindex(series.index.union(prior.index)).fillna(0.0)
                     - prior.reindex(series.index.union(prior.index)).fillna(0.0)).abs().sum()
                )
                if prior is not None
                else float("nan")
            )
            previous[label] = series
            held = np.abs(u) > 1e-4
            significant = np.abs(weight) > 1e-3
            stats.update(
                {
                    "date": str(stamp.date()),
                    "variant": label,
                    "turnover": turnover,
                    "created": int((~held & significant).sum()),
                    "flipped": int((held & significant & (np.sign(weight) != np.sign(u))).sum()),
                    "n_names": int(significant.sum()),
                    "gross": gross_raw,
                    "gross_normalized": float(np.abs(weight).sum()),
                }
            )
            rows.append(stats)
        pre = measure(u, design, covariance, specific)
        # The pre-hedge book's own turnover is the baseline the hedge's own turnover
        # is read against: the difference between a construction's turnover and this
        # one is what the construction itself trades.
        u_series = pd.Series(u, index=names)
        prior_u = previous.get("pre_hedge")
        u_turnover = (
            float(
                (u_series.reindex(u_series.index.union(prior_u.index)).fillna(0.0)
                 - prior_u.reindex(u_series.index.union(prior_u.index)).fillna(0.0)).abs().sum()
            )
            if prior_u is not None
            else float("nan")
        )
        previous["pre_hedge"] = u_series
        rows.append(
            {
                "date": str(stamp.date()),
                "variant": "pre_hedge",
                "vol": pre["vol"],
                "factor_share": pre["factor_share"],
                "max_variance_share": pre["max_variance_share"],
                "exposure_abs_max": pre["exposure_abs_max"],
                "turnover": u_turnover,
                "created": 0,
                "flipped": 0,
                "n_names": int((np.abs(u) > 1e-3).sum()),
                "gross": float(np.abs(u).sum()),
                "gross_normalized": 1.0,
            }
        )
    table = pd.DataFrame(rows)
    summary = (
        table.groupby("variant")
        .agg(
            vol=("vol", "mean"),
            factor_share=("factor_share", "mean"),
            factor_share_p95=("factor_share", lambda series: float(np.nanpercentile(series, 95))),
            max_variance_share=("max_variance_share", "mean"),
            max_variance_share_max=("max_variance_share", "max"),
            exposure_abs_max=("exposure_abs_max", "max"),
            turnover=("turnover", "mean"),
            created=("created", "mean"),
            flipped=("flipped", "mean"),
            n_names=("n_names", "mean"),
            gross=("gross", "mean"),
            gross_normalized=("gross_normalized", "mean"),
        )
        .reset_index()
    )
    print("\n" + summary.to_string(index=False, float_format=lambda value: f"{value:,.5f}"))
    worst = (
        table.loc[table["variant"] == "exact"]
        .nlargest(6, "max_variance_share")
        .loc[:, ["date", "max_variance_share", "vol"]]
    )
    print("\nworst single-name variance shares, exact hedge:")
    print(worst.to_string(index=False, float_format=lambda value: f"{value:,.5f}"))
    out = ROOT / "docs" / "research" / f"nov11_hedge_{scope}_numbers.json"
    out.write_text(json.dumps({"summary": summary.to_dict("records"), "rows": rows}, indent=1, default=float))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return {"summary": summary.to_dict("records")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("live", "backtest"), default="live")
    args = parser.parse_args()
    run(args.scope)


if __name__ == "__main__":
    main()
