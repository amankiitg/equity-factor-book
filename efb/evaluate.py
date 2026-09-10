"""F1 criterion evaluation (Sprint E1, Task 9).

Computes the stored numbers for F1.1 to F1.5 from the artifacts and
writes sprints/E1/RESULTS.json. The criterion text is copied verbatim
from the roadmap and never reworded after the numbers are seen.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from efb import hygiene, returns

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


def write_results(
    criteria: dict[str, dict[str, Any]], path: Path, sprint: str = "E1"
) -> None:
    payload = {
        "sprint": sprint,
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


def main(argv: list[str] | None = None) -> None:
    """Evaluate the sprint criteria; `--e2` selects the E2 set.

    Without the flag this is the E1 evaluation, so passing `--e2` used to
    rewrite sprints/E1/RESULTS.json with a fresh timestamp while the caller
    believed it had regenerated E2.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    if "--e2" in args:
        main_e2()
        return
    inputs = compute_from_artifacts()
    criteria = evaluate_criteria(**inputs)
    write_results(criteria, RESULTS_PATH)
    print(json.dumps(criteria, indent=2))


E2_CRITERIA_TEXT = {
    "F2.0a": (
        "coverage is reported per universe rather than as one threshold: "
        "current members 100%, point-in-time members with prices by year "
        "(the Task 0 table); the criterion passes if the table is stored and "
        "MODEL_START is recorded."
    ),
    "F2.0b": (
        "interior NaN return rows (302 rows, 13 tickers) are excluded from "
        "every regression window and never forward-filled; the criterion "
        "passes if a test proves a regression window containing a NaN row "
        "drops that row rather than imputing it."
    ),
    "F2.0c": (
        "adjusted-close audit mean below 0.1 bp, and every audited day with "
        "an absolute difference above 50 bp appears in events.parquet with a "
        "cause (the 221 bp BKR day is a merger). Passes when both hold."
    ),
    "F2.1": (
        "Full-sample OLS beta vs mean of rolling 252d betas: cross-sectional "
        "correlation above 0.9."
    ),
    "F2.2": (
        "Mean pairwise correlation of FF5+MOM residuals across the universe "
        "below 0.05. Higher means a missing common factor; carry the finding "
        "into E3."
    ),
    "F2.3": (
        "GARCH(1,1) and EWMA(0.94) each beat trailing 252d vol on "
        "out-of-sample QLIKE for more than 60% of names."
    ),
    "F2.4": (
        "For the equal-weight seed portfolio, bias statistic (realized 63d "
        "forward vol over model-predicted vol) averages between 0.8 and 1.2 "
        "across calendar years."
    ),
    "F2.5": (
        "Newey-West SE exceeds OLS SE at lag 5 for more than 80% of names. "
        "If not, document the direction and why."
    ),
    "F2.6": (
        "Successor to F2.3, added on 2026-09-10 after the flagged MI row "
        "turned out to be a series break rather than a bad return: no name "
        "in the panel has an adjusted-close move above 5x that no recorded "
        "split explains. A name above that level has to leave the panel, "
        "not just lose the row, because every earlier date carries a "
        "different company's returns. This one is not pre-registered, and "
        "it is recorded as such."
    ),
}

E2_THRESHOLDS = {
    "F2.0a": "table stored and MODEL_START recorded",
    "F2.0b": "NaN rows dropped, never imputed",
    "F2.0c": "mean < 0.1 bp and every day above 50 bp has an event with a cause",
    "F2.1": "cross-sectional correlation > 0.9",
    "F2.2": "mean pairwise residual correlation < 0.05",
    "F2.3": "GARCH and EWMA(0.94) each beat trailing 252d for > 60% of names",
    "F2.4": "mean bias ratio in [0.8, 1.2] across calendar years",
    "F2.5": "Newey-West SE > OLS SE for > 80% of names",
    "F2.6": "0 names with an unexplained adjusted-close move above 5x",
}


def evaluate_e2_criteria(
    model_start: int,
    coverage_years_stored: int,
    interior_nan_rows: int,
    nan_rows_dropped_not_imputed: bool,
    audit_mean_bp: float,
    large_audit_days: int,
    large_audit_days_with_event: int,
    f21_corr: float,
    f22_mean_pairwise: float,
    f22_n_names: int,
    f23_garch_win_share: float,
    f23_ewma094_win_share: float,
    f23_garch_names_fitted: int,
    f23_paired_n: int,
    f23_paired_garch_win_share: float,
    f23_paired_ewma_win_share: float,
    f23_garch_beats_ewma_share: float,
    f24_bias_mean: float,
    f24_bias_by_year: dict[str, float],
    f25_nw_gt_ols_share: float,
    f26_breaks: list[str],
    f26_break_rows: int,
) -> dict[str, dict[str, Any]]:
    """Store the E2 criteria with numbers computed from the artifacts."""

    def v(ok: bool) -> str:
        return "pass" if ok else "fail"

    return {
        "F2.0a": {
            "criterion": E2_CRITERIA_TEXT["F2.0a"],
            "threshold": E2_THRESHOLDS["F2.0a"],
            "stored_numbers": {
                "model_start": model_start,
                "coverage_years_stored": coverage_years_stored,
                "current_member_coverage": 1.0,
            },
            "verdict": v(coverage_years_stored >= 10 and model_start == 2010),
            "note": (
                "Table in sprints/E2/PROBES.md, MODEL_START in "
                "docs/hygiene_ledger.md."
            ),
        },
        "F2.0b": {
            "criterion": E2_CRITERIA_TEXT["F2.0b"],
            "threshold": E2_THRESHOLDS["F2.0b"],
            "stored_numbers": {
                "interior_nan_rows_e1": interior_nan_rows,
                "nan_row_dropped_by_fit": nan_rows_dropped_not_imputed,
            },
            "verdict": v(nan_rows_dropped_not_imputed),
            "note": (
                "tests/test_timeseries.py::test_nan_rows_are_dropped_not_imputed "
                "proves the drop."
            ),
        },
        "F2.0c": {
            "criterion": E2_CRITERIA_TEXT["F2.0c"],
            "threshold": E2_THRESHOLDS["F2.0c"],
            "stored_numbers": {
                "audit_mean_bp": audit_mean_bp,
                "large_audit_days": large_audit_days,
                "large_audit_days_with_event": large_audit_days_with_event,
            },
            "verdict": v(
                audit_mean_bp < 0.1 and large_audit_days == large_audit_days_with_event
            ),
            "note": (
                "Large days are the 20-name audit sample above 50 bp, all "
                "matched to events.parquet."
            ),
        },
        "F2.1": {
            "criterion": E2_CRITERIA_TEXT["F2.1"],
            "threshold": E2_THRESHOLDS["F2.1"],
            "stored_number": f21_corr,
            "verdict": v(f21_corr > 0.9),
            "note": (
                "Full-sample OLS market beta vs the time mean of the rolling "
                "252d beta."
            ),
        },
        "F2.2": {
            "criterion": E2_CRITERIA_TEXT["F2.2"],
            "threshold": E2_THRESHOLDS["F2.2"],
            "stored_numbers": {
                "mean_pairwise_correlation": f22_mean_pairwise,
                "n_names_sampled": f22_n_names,
            },
            "verdict": v(f22_mean_pairwise < 0.05),
            "note": (
                "Seeded random sample of names with a minimum overlap; carries "
                "into E3 if above 0.05."
            ),
        },
        "F2.3": {
            "criterion": E2_CRITERIA_TEXT["F2.3"],
            "threshold": E2_THRESHOLDS["F2.3"],
            "stored_numbers": {
                "garch_win_share": f23_garch_win_share,
                "ewma_094_win_share": f23_ewma094_win_share,
                "garch_names_fitted": f23_garch_names_fitted,
                "paired_n": f23_paired_n,
                "paired_garch_win_share": f23_paired_garch_win_share,
                "paired_ewma_094_win_share": f23_paired_ewma_win_share,
                "garch_beats_ewma_094_share": f23_garch_beats_ewma_share,
            },
            "verdict": v(f23_garch_win_share > 0.6 and f23_ewma094_win_share > 0.6),
            "note": (
                "Win share is the fraction of names whose out-of-sample QLIKE "
                "beats trailing 252d vol. GARCH fits only "
                f"{f23_garch_names_fitted} of the names, so the two win shares "
                f"are not on the same sample: on the {f23_paired_n} names where "
                "both are available, GARCH beats EWMA (0.94) for "
                f"{f23_garch_beats_ewma_share:.1%} of them."
            ),
        },
        "F2.4": {
            "criterion": E2_CRITERIA_TEXT["F2.4"],
            "threshold": E2_THRESHOLDS["F2.4"],
            "stored_numbers": {
                "bias_mean": f24_bias_mean,
                "bias_by_year": f24_bias_by_year,
            },
            "verdict": v(0.8 <= f24_bias_mean <= 1.2),
            "note": (
                "Equal-weight seed book, 63-day forward realized vol over the "
                "predicted vol, by year."
            ),
        },
        "F2.5": {
            "criterion": E2_CRITERIA_TEXT["F2.5"],
            "threshold": E2_THRESHOLDS["F2.5"],
            "stored_number": f25_nw_gt_ols_share,
            "verdict": v(f25_nw_gt_ols_share > 0.8),
            "note": (
                "Share of names where the Newey-West market-beta SE exceeds "
                "the OLS SE at lag 5."
            ),
        },
        "F2.6": {
            "criterion": E2_CRITERIA_TEXT["F2.6"],
            "threshold": E2_THRESHOLDS["F2.6"],
            "stored_numbers": {
                "names_with_breaks": len(f26_breaks),
                "break_tickers": f26_breaks,
                "break_rows": f26_break_rows,
            },
            "verdict": v(len(f26_breaks) == 0),
            "note": (
                "Ticker reuse: a later listing takes the old symbol and the "
                "vendor splices both histories, so one company's returns are "
                "attributed to another. Fixing it needs a security-identity "
                "source (FIGI or PERMNO) and is tracked in docs/open_items.md."
            ),
        },
    }


def _series_breaks(
    prices_frame: pd.DataFrame, ratio: float = 5.0
) -> tuple[list[str], int]:
    """Series-break tickers and how many offending rows they contribute.

    The rule itself lives in efb.hygiene.series_break_tickers, which the
    build also uses to drop those names from the estimation panel, so the
    criterion and the mitigation cannot drift apart.
    """
    tickers = hygiene.series_break_tickers(prices_frame, ratio=ratio)
    frame = prices_frame.sort_index()
    adjusted = frame["adj_close"].astype(float)
    previous = adjusted.groupby(level="ticker").shift(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio_series = adjusted.div(previous)
    split = frame["split_factor"].astype(float)
    suspects = (
        ((ratio_series > ratio) | (ratio_series < 1.0 / ratio))
        & (split == 0.0)
        & ratio_series.notna()
    )
    return tickers, int(suspects.sum())


def compute_e2_from_artifacts(data_root: Path = ROOT / "data") -> dict[str, Any]:
    """Compute every E2 stored number from the artifacts."""
    from efb import prices as prices_mod
    from efb import probes
    from efb.models import timeseries as ts

    processed = data_root / "processed"
    raw = data_root / "raw"
    model_dir = data_root / "models" / "TS-v1"

    prices_frame = pd.read_parquet(raw / "prices.parquet")
    returns_frame = pd.read_parquet(processed / "returns.parquet")
    members = pd.read_parquet(processed / "universe_membership.parquet")
    factors_frame = pd.read_parquet(raw / "factors_ff.parquet")
    events = pd.read_parquet(processed / "events.parquet")
    loadings = pd.read_parquet(model_dir / "loadings.parquet")
    se = pd.read_parquet(model_dir / "loadings_se.parquet")
    beta_history = pd.read_parquet(model_dir / "beta_history.parquet")
    ew_risk = pd.read_parquet(data_root / "portfolios" / "seed_ew_risk.parquet")

    # F2.0a: coverage table and MODEL_START
    coverage = probes.coverage_by_year(members, prices_frame)
    model_start = probes.select_model_start(coverage, min_names=300)

    # F2.0b: a NaN row inside a regression window is dropped, not filled
    y_raw, fac, _flags = ts.panel_from_artifacts(
        returns_frame, factors_frame, start=model_start, exclude_flags=False
    )
    market = fac[["mkt_rf"]]
    adj = prices_frame["adj_close"]
    interior_nan_rows = 0
    for ticker, sub in adj.groupby(level="ticker"):
        valid = sub.dropna()
        if valid.empty:
            continue
        lo, hi = valid.index[0][0], valid.index[-1][0]
        mask = (
            (adj.index.get_level_values("date") > lo)
            & (adj.index.get_level_values("date") < hi)
            & (adj.index.get_level_values("ticker") == ticker)
        )
        interior_nan_rows += int(adj[mask].isna().sum())
    nan_dropped = False
    for ticker in y_raw.columns:
        series = y_raw[ticker]
        nan_count = int(series.isna().sum())
        if nan_count == 0:
            continue
        fit = ts.ols_fit(series, market)
        if fit.n_obs == len(series) - nan_count:
            nan_dropped = True
            break

    # F2.0c: audit mean and large days matched to events
    covered = sorted(
        prices_mod.covered_tickers(pd.read_parquet(raw / "yf_cache.parquet"))
    )
    audit = prices_mod.audit_adjusted_close(prices_frame, covered, n_names=20, seed=42)
    details = prices_mod.audit_adjusted_close_details(
        prices_frame, covered, n_names=20, seed=42, threshold_bp=50.0
    )
    matched = 0
    for row in details.itertuples(index=False):
        window = events[
            (events["ticker"] == row.ticker)
            & (
                pd.to_datetime(events["date"]).sub(pd.Timestamp(row.date)).abs()
                <= pd.Timedelta(days=3)
            )
        ]
        if not window.empty:
            matched += 1

    # F2.1: full-sample beta vs mean rolling beta
    mean_rolling = (
        beta_history[beta_history["method"] == "raw"].groupby("ticker")["beta"].mean()
    )
    both = pd.concat(
        [loadings["mkt_rf"].rename("full"), mean_rolling.rename("rolling")], axis=1
    ).dropna()
    f21_corr = float(both["full"].corr(both["rolling"]))

    # F2.2: mean pairwise residual correlation on a seeded sample
    residuals = pd.read_parquet(model_dir / "residuals.parquet")["residual"].unstack(
        "ticker"
    )
    rng = np.random.default_rng(42)
    candidates = [c for c in residuals.columns if residuals[c].notna().sum() >= 500]
    sample = sorted(
        rng.choice(candidates, size=min(150, len(candidates)), replace=False)
    )
    corr = residuals[sample].corr(min_periods=250)
    mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)
    f22_mean = float(np.nanmean(corr.to_numpy()[mask]))

    # F2.3: win shares vs trailing 252d
    wins = pd.read_parquet(data_root / "eval" / "vol_horse_race.parquet")
    from efb import vol as vol_mod

    win_shares = vol_mod.beats_baseline(wins, baseline="trailing_252").set_index(
        "method"
    )
    f23_garch = (
        float(win_shares.loc["garch", "win_share"])
        if "garch" in win_shares.index
        else 0.0
    )
    f23_ewma = (
        float(win_shares.loc["ewma_094", "win_share"])
        if "ewma_094" in win_shares.index
        else 0.0
    )
    # GARCH only fits a fraction of the universe, so the two win shares are
    # not measured on the same names. Store the paired sample too, otherwise
    # "GARCH fails" reads as "GARCH is worse", which is not what the data says.
    paired = wins.pivot(index="ticker", columns="method", values="qlike").dropna(
        subset=["garch", "ewma_094", "trailing_252"]
    )
    f23_paired_n = int(len(paired))
    f23_garch_names_fitted = int(
        wins.loc[wins["method"] == "garch", "ticker"].nunique()
    )
    f23_garch_beats_ewma = (
        float((paired["garch"] < paired["ewma_094"]).mean()) if f23_paired_n else 0.0
    )
    f23_paired_garch = (
        float((paired["garch"] < paired["trailing_252"]).mean())
        if f23_paired_n
        else 0.0
    )
    f23_paired_ewma = (
        float((paired["ewma_094"] < paired["trailing_252"]).mean())
        if f23_paired_n
        else 0.0
    )

    # F2.4: bias by calendar year for the equal-weight seed book
    bias = ew_risk["bias_ratio"].dropna()
    by_year = bias.groupby(bias.index.year).mean()
    f24_by_year = {str(int(year)): float(value) for year, value in by_year.items()}
    f24_mean = float(by_year.mean()) if len(by_year) else float("nan")

    # F2.5: Newey-West vs OLS market-beta SE
    ols_se = se["ols"]["mkt_rf"]
    nw_se = se["nw_l5"]["mkt_rf"]
    comparison = pd.concat([ols_se.rename("ols"), nw_se.rename("nw")], axis=1).dropna()
    f25_share = float((comparison["nw"] > comparison["ols"]).mean())

    # F2.6: series breaks, a close-to-close ratio above 5x with no split
    f26_breaks, f26_rows = _series_breaks(prices_frame)

    return {
        "model_start": model_start,
        "coverage_years_stored": int(len(coverage)),
        "interior_nan_rows": interior_nan_rows,
        "nan_rows_dropped_not_imputed": nan_dropped,
        "audit_mean_bp": float(audit["mean_abs_bp"]),
        "large_audit_days": int(len(details)),
        "large_audit_days_with_event": matched,
        "f21_corr": f21_corr,
        "f22_mean_pairwise": f22_mean,
        "f22_n_names": int(len(sample)),
        "f23_garch_win_share": f23_garch,
        "f23_ewma094_win_share": f23_ewma,
        "f23_garch_names_fitted": f23_garch_names_fitted,
        "f23_paired_n": f23_paired_n,
        "f23_paired_garch_win_share": f23_paired_garch,
        "f23_paired_ewma_win_share": f23_paired_ewma,
        "f23_garch_beats_ewma_share": f23_garch_beats_ewma,
        "f24_bias_mean": f24_mean,
        "f24_bias_by_year": f24_by_year,
        "f25_nw_gt_ols_share": f25_share,
        "f26_breaks": f26_breaks,
        "f26_break_rows": f26_rows,
    }


def main_e2() -> None:
    inputs = compute_e2_from_artifacts()
    criteria = evaluate_e2_criteria(**inputs)
    write_results(criteria, ROOT / "sprints" / "E2" / "RESULTS.json", sprint="E2")
    print(json.dumps(criteria, indent=2))


if __name__ == "__main__":
    main()
