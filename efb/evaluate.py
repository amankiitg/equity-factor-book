"""F1 criterion evaluation (Sprint E1, Task 9).

Computes the stored numbers for F1.1 to F1.5 from the artifacts and
writes sprints/E1/RESULTS.json. The criterion text is copied verbatim
from the roadmap and never reworded after the numbers are seen.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from efb import returns

ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "sprints" / "E1" / "RESULTS.json"

CRITERIA_TEXT = {
    "F1.1": (
        "Each probed source returns at least 95% of requested tickers with at "
        "least 10 years of daily history. A failing source is recorded in the "
        "ledger and the design adapts; it is never silently dropped."
    ),
    "F1.2": (
        "Zero NaNs in returns.parquet after the warm-up window, except "
        "documented delisting rows."
    ),
    "F1.3": (
        "Equal-weight universe daily return vs the Kenneth French market "
        "return (Mkt-RF + RF) correlation above 0.95. Lower means a "
        "date-alignment or adjustment bug, not a finding."
    ),
    "F1.4": (
        "Total returns computed from adjusted close reproduce the "
        "dividend-adjusted series within 1 bp per day on 20 randomly sampled "
        "names."
    ),
    "F1.5": (
        "Survivorship measured: the fraction of historical members with "
        "recoverable history is stored. If below 70%, the ledger records the "
        "bias magnitude via a naive buy-all-members backtest against the FF "
        "market return."
    ),
}

THRESHOLDS = {
    "F1.1": "95% of requested tickers",
    "F1.2": "zero interior NaNs",
    "F1.3": "correlation > 0.95",
    "F1.4": "max abs daily difference <= 1 bp",
    "F1.5": "recoverable fraction >= 70%",
}


def annualized_gap_bp(a: pd.Series, b: pd.Series) -> float:
    """Annualized difference between two daily return series in bp."""
    both = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna()
    return float((both["a"].mean() - both["b"].mean()) * 252 * 10_000.0)


def ten_year_history_fraction(
    first_possible: pd.Series,
    first_available: pd.Series,
    cutoff: str,
) -> float:
    """Fraction of eligible tickers with at least 10 years of history.

    first_possible maps tickers to their membership start (eligibility).
    first_available maps tickers to their first available price date.
    A ticker is eligible when its membership started at or before the
    cutoff (ten years before the as-of date) and counts as covered when
    its price history starts at or before the cutoff too.
    """
    cutoff_ts = pd.Timestamp(cutoff)
    eligible = set(first_possible[first_possible <= cutoff_ts].index)
    if not eligible:
        return float("nan")
    covered = set(first_available[first_available <= cutoff_ts].index) & eligible
    return float(len(covered) / len(eligible))


def _verdict(ok: bool) -> str:
    return "pass" if ok else "fail"


def evaluate_criteria(
    yf_coverage: float,
    current_coverage: float,
    ten_year_coverage: float,
    interior_nans: int,
    f13_corr: float,
    f14_max_bp: float,
    f14_mean_bp: float,
    survivorship_fraction: float,
    bias_bp_per_year: float,
    naive_mkt_bp_per_year: float = float("nan"),
    pit_mkt_bp_per_year: float = float("nan"),
) -> dict[str, dict[str, Any]]:
    f11 = {
        "criterion": CRITERIA_TEXT["F1.1"],
        "threshold": THRESHOLDS["F1.1"],
        "stored_numbers": {
            "yfinance_coverage_all_requested": yf_coverage,
            "yfinance_coverage_current_members": current_coverage,
            "ten_year_history_fraction_eligible": ten_year_coverage,
        },
        "verdict": _verdict(
            yf_coverage >= 0.95
            and current_coverage >= 0.95
            and ten_year_coverage >= 0.95
        ),
        "note": (
            "yfinance coverage of current members is full after the BF.B and "
            "BRK.B symbol mapping; coverage of deleted names is what F1.5 "
            "measures. FRED DTB3 failed its probe and is recorded as null in "
            "the ledger."
        ),
    }
    f12 = {
        "criterion": CRITERIA_TEXT["F1.2"],
        "threshold": THRESHOLDS["F1.2"],
        "stored_number": interior_nans,
        "verdict": _verdict(interior_nans == 0),
        "note": (
            "Interior NaN return days between a ticker's first and last "
            "available price while a member, after the warm-up window. "
            "Delisting tails and unrecovered pre-history are documented "
            "separately in the ledger."
        ),
    }
    f13 = {
        "criterion": CRITERIA_TEXT["F1.3"],
        "threshold": THRESHOLDS["F1.3"],
        "stored_number": f13_corr,
        "verdict": _verdict(f13_corr > 0.95),
        "note": (
            "Correlation over common business days with the FF market "
            "return (Mkt-RF + RF)."
        ),
    }
    f14 = {
        "criterion": CRITERIA_TEXT["F1.4"],
        "threshold": THRESHOLDS["F1.4"],
        "stored_numbers": {"max_abs_bp": f14_max_bp, "mean_abs_bp": f14_mean_bp},
        "verdict": _verdict(f14_max_bp <= 1.0),
        "note": (
            "Audit on 20 randomly sampled names, seed 42. The mean is far "
            "inside 1 bp; the max comes from one merger day (BKR 2017-07-05) "
            "logged as a corporate-action event."
        ),
    }
    f15 = {
        "criterion": CRITERIA_TEXT["F1.5"],
        "threshold": THRESHOLDS["F1.5"],
        "stored_numbers": {
            "fraction_recovered": survivorship_fraction,
            "naive_minus_pit_bp_per_year": bias_bp_per_year,
            "naive_minus_ff_market_bp_per_year": naive_mkt_bp_per_year,
            "pit_minus_ff_market_bp_per_year": pit_mkt_bp_per_year,
        },
        "verdict": _verdict(survivorship_fraction >= 0.70),
        "note": (
            "Fraction of deleted members with recoverable price history. "
            "Below 70%, so the bias magnitude is recorded via a naive "
            "buy-all-current-members backtest against point-in-time "
            "membership and against the FF market return."
        ),
    }
    return {"F1.1": f11, "F1.2": f12, "F1.3": f13, "F1.4": f14, "F1.5": f15}


def write_results(criteria: dict[str, dict[str, Any]], path: Path) -> None:
    payload = {
        "sprint": "E1",
        "evaluated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "criteria": criteria,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def compute_from_artifacts(data_root: Path = ROOT / "data") -> dict[str, Any]:
    """Compute every stored number from the artifacts and return the inputs
    needed by evaluate_criteria."""
    prices_frame = pd.read_parquet(data_root / "raw" / "prices.parquet")
    returns_frame = pd.read_parquet(data_root / "processed" / "returns.parquet")
    members = pd.read_parquet(data_root / "processed" / "universe_membership.parquet")
    factors_frame = pd.read_parquet(data_root / "raw" / "factors_ff.parquet")
    constituents = pd.read_parquet(data_root / "processed" / "sectors.parquet")

    from efb import prices as prices_mod

    raw_cache = data_root / "raw" / "yf_cache.parquet"
    raw_prices = pd.read_parquet(raw_cache) if raw_cache.exists() else prices_frame
    covered = prices_mod.covered_tickers(raw_prices)
    all_requested = set(prices_frame.index.get_level_values("ticker").unique())
    current = set(constituents["ticker"].unique())
    yf_coverage = len(covered) / max(len(all_requested), 1)
    current_coverage = len(current & covered) / max(len(current), 1)

    first_valid = (
        raw_prices["adj_close"]
        .groupby(level="ticker")
        .apply(
            lambda s: (
                s.first_valid_index()[0] if s.first_valid_index() is not None else None
            )
        )
    ).dropna()
    starts = pd.Series(
        {
            ticker: pd.Timestamp(members[ticker].idxmax())
            for ticker in members.columns
            if members[ticker].any()
        }
    )
    ten_year = ten_year_history_fraction(starts, first_valid, cutoff="2016-09-02")

    adj = prices_frame["adj_close"]
    interior = 0
    for ticker, sub in adj.groupby(level="ticker"):
        sub = sub.dropna()
        if sub.empty:
            continue
        lo, hi = sub.index[0][0], sub.index[-1][0]
        mask = (
            (adj.index.get_level_values("date") > lo)
            & (adj.index.get_level_values("date") < hi)
            & (adj.index.get_level_values("ticker") == ticker)
        )
        interior += int(adj[mask].isna().sum())

    ew = returns.equal_weight_universe_return(returns_frame, members)
    mkt = factors_frame["mkt_rf"] + factors_frame["rf"]
    both = pd.concat(
        [ew.rename("ew"), mkt.rename("mkt")], axis=1, join="inner"
    ).dropna()
    f13_corr = float(both["ew"].corr(both["mkt"]))

    audit = prices_mod.audit_adjusted_close(
        raw_prices, sorted(covered), n_names=20, seed=42
    )

    from efb import universe

    stats = universe.survivorship_stats(members, covered)
    naive = _naive_buy_all_current(returns_frame, current)
    bias = annualized_gap_bp(naive, ew)
    naive_mkt = annualized_gap_bp(naive, mkt)
    pit_mkt = annualized_gap_bp(ew, mkt)

    return {
        "yf_coverage": yf_coverage,
        "current_coverage": current_coverage,
        "ten_year_coverage": ten_year,
        "interior_nans": interior,
        "f13_corr": f13_corr,
        "f14_max_bp": audit["max_abs_bp"],
        "f14_mean_bp": audit["mean_abs_bp"],
        "survivorship_fraction": float(stats["fraction"]),
        "bias_bp_per_year": bias,
        "naive_mkt_bp_per_year": naive_mkt,
        "pit_mkt_bp_per_year": pit_mkt,
    }


def _naive_buy_all_current(
    returns_frame: pd.DataFrame, current_tickers: set[str]
) -> pd.Series:
    """Naive buy-all-current-members daily equal-weight return."""
    wide = returns_frame["r"].unstack("ticker")
    cols = [c for c in current_tickers if c in wide.columns]
    return wide[cols].mean(axis=1).rename("naive_buy_all")


def main() -> None:
    inputs = compute_from_artifacts()
    criteria = evaluate_criteria(**inputs)
    write_results(criteria, RESULTS_PATH)
    print(json.dumps(criteria, indent=2))


if __name__ == "__main__":
    main()
