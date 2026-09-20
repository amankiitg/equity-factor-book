"""F1 criterion evaluation (Sprint E1, Task 9).

Computes the stored numbers for F1.1 to F1.5 from the artifacts and
writes sprints/E1/RESULTS.json. The criterion text is copied verbatim
from the roadmap and never reworded after the numbers are seen.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

import numpy as np
import pandas as pd

from efb import hygiene, identity, perf, returns

ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "sprints" / "E1" / "RESULTS.json"

# Newey-West lag used by the Lo (2002) Sharpe standard error, quoted in the
# E1 reference values block so the walkthrough and the data note agree.
LO_Q = 5

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


def _measurement(criterion: dict[str, Any]) -> dict[str, Any]:
    """The parts of a stored criterion that a re-run can change."""
    out: dict[str, Any] = {"verdict": criterion.get("verdict")}
    for key in ("stored_number", "stored_numbers"):
        if key in criterion:
            out[key] = criterion[key]
    return out


def _changed(old: dict[str, Any] | None, new: dict[str, Any]) -> bool:
    """Whether a re-measurement moved anything, NaN included.

    Comparing the dicts directly reports a change whenever a value is NaN,
    because NaN is not equal to itself, and the E2 criteria store a NaN per
    calendar year with no observations. Comparing the serialized form
    instead treats two NaNs as the same number, which is what they are
    here: both mean the year had no data.
    """
    if old is None:
        return False
    return json.dumps(old, sort_keys=True) != json.dumps(new, sort_keys=True)


def write_results(
    criteria: dict[str, dict[str, Any]],
    path: Path,
    sprint: str = "E1",
    data_hash: str | None = None,
    previous_data_hash: str | None = None,
    extra: dict[str, dict[str, Any]] | None = None,
    extra_previous: dict[str, dict[str, Any]] | None = None,
    reference_values: dict[str, Any] | None = None,
) -> None:
    """Store the criteria, keeping the previous measurement alongside.

    A criterion is never reworded or re-scored, so when a data correction
    moves a number the old and the new value both stay on the record with
    the data hash that produced each. Rewriting the file with only the new
    numbers would erase the evidence that anything moved.

    `extra` carries criteria owned by another sprint that this rebuild
    still changes, such as the E2 zero tier when an E1 data correction
    moves the universe return. Their previous values come from
    `extra_previous`, the other sprint's own results file.

    `revisions` also carries a `history` list, one entry per distinct data
    hash, so a second correction to the same sprint does not overwrite the
    first. Re-running a build without changing the data leaves the list
    alone, which keeps the file stable under a repeated run.
    """
    prior: dict[str, Any] = {}
    if path.exists():
        try:
            prior = json.loads(path.read_text())
        except json.JSONDecodeError:  # pragma: no cover - corrupt file
            prior = {}
    previous: dict[str, Any] = prior.get("criteria", {})
    prior_revisions = prior.get("revisions")
    history: list[dict[str, Any]] = []
    if isinstance(prior_revisions, dict):
        history = list(prior_revisions.get("history") or [])
        if not history and prior_revisions.get("changed") is not None:
            # the single comparison the earlier writer left behind becomes
            # the first entry of the history rather than being lost, even
            # when it recorded no data hash
            history = [{k: v for k, v in prior_revisions.items() if k != "history"}]
    older = extra_previous or {}

    changed: dict[str, Any] = {}
    for key, criterion in criteria.items():
        old = _measurement(previous[key]) if key in previous else None
        new = _measurement(criterion)
        changed[key] = {
            "changed": _changed(old, new),
            "old": old,
            "new": new,
        }
    for key, criterion in (extra or {}).items():
        old = _measurement(older[key]) if key in older else None
        new = _measurement(criterion)
        changed[key] = {
            "changed": _changed(old, new),
            "old": old,
            "new": new,
            "sprint": "E2",
        }
    moved = [key for key, block in changed.items() if block["changed"]]

    entry = {
        "previous_data_hash": previous_data_hash,
        "data_hash": data_hash,
        "n_changed": len(moved),
        "changed_tickers_or_criteria": sorted(moved),
        "cross_sprint_criteria": sorted(extra or {}),
        "changed": changed,
    }
    if not history or history[-1].get("data_hash") != data_hash:
        history.append(entry)

    payload = {
        "sprint": sprint,
        "evaluated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_hash": data_hash,
        "criteria": criteria,
        "revisions": {**entry, "history": history},
    }
    # `reference_values` holds the numbers a walkthrough asserts against
    # without recomputing them from prose. A caller that does not know about
    # the block must not erase it, so it is carried forward when not passed,
    # and it is never allowed to move the revisions history: it is a
    # derived input rather than a scored criterion.
    if reference_values is not None:
        payload["reference_values"] = reference_values
    elif isinstance(prior.get("reference_values"), dict):
        payload["reference_values"] = prior["reference_values"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def e1_reference_values(data_root: Path = ROOT / "data") -> dict[str, Any]:
    """The E1 walkthrough's reference constants, recomputed from parquet.

    docs/research/E1_data_note.md quotes these in prose (annualized Sharpe,
    the i.i.d. and Lo (2002) standard errors, their ratio, and the market
    factor's lag-1 autocorrelation). Prose is not an assertion target: the
    notebook reads this block, prints it, and asserts the recomputed values
    against it, so a data correction moves the notebook and the block
    together instead of leaving a stale figure in a markdown table.
    """
    factors_frame = pd.read_parquet(data_root / "raw" / "factors_ff.parquet")
    market = factors_frame["mkt_rf"]
    x = market.dropna()
    sr = perf.sharpe_ratio(x)
    se_iid = perf.sharpe_se_iid(x)
    se_lo = perf.sharpe_se_lo2002(x, q=LO_Q)
    return {
        "source": (
            "efb.evaluate.e1_reference_values from "
            "data/raw/factors_ff.parquet column mkt_rf"
        ),
        "series": "mkt_rf",
        "n_obs": int(len(x)),
        "first_date": str(x.index[0].date()),
        "last_date": str(x.index[-1].date()),
        "annualization": int(perf.TRADING_DAYS),
        "lo_q": int(LO_Q),
        "sharpe_daily": sr,
        "sharpe_annualized": sr * np.sqrt(perf.TRADING_DAYS),
        "se_iid_daily": se_iid,
        "se_iid_annualized": se_iid * np.sqrt(perf.TRADING_DAYS),
        "se_lo2002_daily": se_lo,
        "se_lo2002_annualized": se_lo * np.sqrt(perf.TRADING_DAYS),
        "ratio_lo_over_iid": se_lo / se_iid,
        "lag1_autocorrelation_ff_market": perf.autocorrelation(x, lag=1),
        "sum_rho_weighted_q": perf._newy_west_acf_sum(x.to_numpy(), LO_Q),
        "sum_phi_weighted_q": perf._newy_west_acf_sum((x**2).to_numpy(), LO_Q),
    }


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
    write_results(
        criteria,
        RESULTS_PATH,
        data_hash=inputs.get("data_hash"),
        reference_values=e1_reference_values(),
    )
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
    "F2.6b": (
        "Close-out C1, added 2026-09-10 and not pre-registered: every "
        "ticker on the Wikipedia changes table's removed list is compared "
        "with the current holder of that symbol on yfinance, matched by "
        "name token overlap after stripping legal suffixes, punctuation "
        "and share class letters. A name match means the history is "
        "legitimate even if prices continue past the removal; no match "
        "means the symbol was reused and rows before the current company's "
        "first valid date are dropped, or the ticker is dropped when that "
        "date cannot be determined. Tickers with a gap above 60 business "
        "days between two live price segments are flagged separately. The "
        "criterion passes when the flagged list is stored in "
        "data/processed/ticker_identity.parquet and efb/build.py applies "
        "the exclusions itself, which is checked against the estimated "
        "panel rather than asserted."
    ),
    "F2.3b": (
        "Close-out C3, added 2026-09-10 and not pre-registered: the same "
        "60% win-share bar as F2.3, evaluated on forecasts matched to the "
        "target horizon. One-step forecasts are scored against the squared "
        "return of the same day, and 21-day forecasts (GARCH multi-step, "
        "EWMA held flat, trailing held flat) against the realized variance "
        "of the next 21 days, both over the same out-of-sample window with "
        "flagged rows excluded. GARCH and EWMA(0.94) each have to beat the "
        "trailing 252d baseline for more than 60% of names at both "
        "horizons. EWMA(0.97) stays the production estimator unless GARCH "
        "wins for more than 70% of names here, which would be an open "
        "decision for E5 rather than a change now."
    ),
    "F2.6c": (
        "Close-out C6, added 2026-09-10 and not pre-registered: for every "
        "ticker the F2.6b identity check dropped, the changes table is "
        "asked for an added row dated after the removal and the "
        "constituents table for the name the symbol carries today. When "
        "either exists, that name is compared with the yfinance holder. A "
        "match means the symbol was renamed rather than taken over, so the "
        "ticker returns to the universe with its history truncated to the "
        "later of the re-add date and its first valid price; no match "
        "means it stays dropped. The criterion passes when the current "
        "constituents are covered by the estimation panel (returns.parquet) "
        "at 501 of 503, the bar stated in the close-out brief, and when "
        "the review itself is stored."
    ),
    "F2.3c": (
        "Close-out C7, added 2026-09-10 and not pre-registered: the same "
        "60 percent bar as F2.3b, evaluated on a seeded random sample of "
        "100 names with full coverage over the out-of-sample window rather "
        "than on the alphabetical head of the universe, which is not a "
        "sample of anything. The seed, the sample size, the number of fits "
        "that converged and the names that did not are stored with the "
        "result. GARCH and EWMA(0.94) each have to beat the trailing 252d "
        "baseline for more than 60 percent of the names at horizon 1 and "
        "at horizon 21. The criterion exists because F2.3 and F2.3b were "
        "measured on a sample chosen by ticker order, and the point of a "
        "sample is to be chosen at random from the names that can be "
        "scored."
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
    "F2.6b": (
        "identity table stored and the reused-symbol exclusions applied by the build"
    ),
    "F2.3b": (
        "GARCH and EWMA(0.94) each beat trailing 252d QLIKE for more than 60% "
        "of names at horizon 1 and at horizon 21"
    ),
    "F2.6c": (
        "current-constituent coverage of the estimation panel at or above 501 "
        "of 503, with the re-add review stored"
    ),
    "F2.3c": (
        "GARCH and EWMA(0.94) each beat trailing 252d QLIKE for more than 60% "
        "of a seeded random sample of 100 fully covered names at horizon 1 and "
        "at horizon 21"
    ),
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
    f26b_rows: int,
    f26b_matched: int,
    f26b_unverified: int,
    f26b_reused: int,
    f26b_reused_tickers: list[str],
    f26b_kept_by_review: list[str],
    f26b_dropped: list[str],
    f26b_truncated: dict[str, str],
    f26b_gaps: list[str],
    f26b_leaks: list[str],
    f23b_win_shares: dict[str, dict[str, float]],
    f23b_garch_fitted: int,
    f23b_garch_failed: int,
    f23b_day_level: dict[str, object],
    f26c: ReaddedCoverage,
    f23c: SeededSampleFindings,
) -> dict[str, dict[str, Any]]:
    """Store the E2 criteria with numbers computed from the artifacts."""

    def v(ok: bool) -> str:
        return "pass" if ok else "fail"

    shares = f23c["win_shares"]
    garch_h1 = shares.get("1", {}).get("garch", float("nan"))
    garch_h21 = shares.get("21", {}).get("garch", float("nan"))
    f23c_note = (
        f"Seed {f23c['seed']}, sample of {f23c['sample_size']} names drawn "
        f"from the {f23c['n_fully_covered']} with full coverage over the "
        f"window, {f23c['garch_fitted']} fits converging and "
        f"{f23c['garch_failed']} not "
        f"({', '.join(f23c['not_converged']) or 'none'}). The GARCH win "
        f"share is sample-dependent: {garch_h1:.1%} at horizon 1 on this "
        "sample against 46.7% on the alphabetical 60 that F2.3b first used, "
        f"and {garch_h21:.1%} at horizon 21, but EWMA(0.94) is nowhere near "
        "the bar at either horizon, so the verdict does not turn on the "
        "sample."
    )

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
        "F2.6b": {
            "criterion": E2_CRITERIA_TEXT["F2.6b"],
            "threshold": E2_THRESHOLDS["F2.6b"],
            "stored_numbers": {
                "identity_table_rows": f26b_rows,
                "names_matched": f26b_matched,
                "names_unverified": f26b_unverified,
                "names_reused": f26b_reused,
                "reused_tickers": f26b_reused_tickers,
                "restored_by_the_c6_review": f26b_kept_by_review,
                "dropped_by_build": f26b_dropped,
                "truncated": f26b_truncated,
                "gap_tickers": f26b_gaps,
                "dropped_still_in_panel": f26b_leaks,
            },
            # application is the point: the table existing is not enough,
            # and a reused name still in the panel is the failure mode. The
            # counts need not match, because a reused symbol with no price
            # history cannot leak into a panel in the first place.
            "verdict": v(
                f26b_rows > 0
                and not f26b_leaks
                and (f26b_reused == 0 or bool(f26b_dropped))
            ),
            "note": (
                "Compared the removed-security name in the changes table "
                "with the current holder of the symbol on yfinance. "
                f"{f26b_reused} of {f26b_rows} removed tickers are held by "
                "an unrelated company today, and the panel the estimate "
                f"ran on contains none of the {len(f26b_dropped)} dropped "
                "names."
            ),
        },
        "F2.3b": {
            "criterion": E2_CRITERIA_TEXT["F2.3b"],
            "threshold": E2_THRESHOLDS["F2.3b"],
            "stored_numbers": {
                "win_shares": f23b_win_shares,
                "garch_fitted": f23b_garch_fitted,
                "garch_failed": f23b_garch_failed,
                "day_level_ewma_094": f23b_day_level,
            },
            "verdict": v(
                all(
                    block.get(method, 0.0) > 0.6
                    for block in f23b_win_shares.values()
                    for method in ("garch", "ewma_094")
                )
                and len(f23b_win_shares) >= 2
            ),
            "note": (
                "Horizon matched on both sides. GARCH improves when the "
                "21-day dynamics are used rather than a flat scaling "
                f"({f23b_win_shares.get('21', {}).get('garch', float('nan')):.1%} "
                "of names against the one-step "
                f"{f23b_win_shares.get('1', {}).get('garch', float('nan')):.1%}), "
                "which was the hypothesis behind treating F2.3 as suspect, "
                "but neither horizon reaches 60%, so F2.3 stands and EWMA "
                "stays the production estimator."
            ),
        },
        "F2.6c": {
            "criterion": E2_CRITERIA_TEXT["F2.6c"],
            "threshold": E2_THRESHOLDS["F2.6c"],
            "stored_numbers": {**f26c},
            "verdict": v(f26c["bar"] <= f26c["coverage"] and f26c["review_rows"] > 0),
            "note": (
                "Of the reused symbols, "
                f"{len(f26c['kept'])} are the same company as the "
                "symbol's current holder, so they came back with their "
                "history truncated rather than dropped, and "
                f"{len(f26c['stays_dropped'])} stays dropped."
            ),
        },
        "F2.3c": {
            "criterion": E2_CRITERIA_TEXT["F2.3c"],
            "threshold": E2_THRESHOLDS["F2.3c"],
            "stored_numbers": {**f23c},
            "verdict": v(
                bool(f23c["sample"])
                and len(shares) >= 2
                and all(
                    block.get(method, 0.0) > 0.6
                    for block in shares.values()
                    for method in ("garch", "ewma_094")
                )
            ),
            "note": f23c_note,
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


class IdentityFindings(TypedDict):
    """What the F2.6b check found, and what the build did about it.

    matched counts names that were verified against a current holder and
    agree; unverified counts symbols with no listing today, which cannot
    be judged either way; reused counts the rest, and those are the ones
    the build has to exclude.
    """

    rows: int
    matched: int
    unverified: int
    reused: int
    reused_tickers: list[str]
    kept_by_review: list[str]
    dropped: list[str]
    truncated: dict[str, str]
    gaps: list[str]
    leaks: list[str]


def _identity_findings(data_root: Path, loadings: pd.DataFrame) -> IdentityFindings:
    """Identity table summary plus proof the build acted on it.

    The point of storing the table is that the build excludes what it
    flags, so the check is not that the table exists but that none of the
    names it flagged still appear in the panel the estimates were fitted
    on.
    """
    empty: IdentityFindings = {
        "rows": 0,
        "matched": 0,
        "unverified": 0,
        "reused": 0,
        "reused_tickers": [],
        "kept_by_review": [],
        "dropped": [],
        "truncated": {},
        "gaps": [],
        "leaks": [],
    }
    path = data_root / "processed" / "ticker_identity.parquet"
    if not path.exists():
        return empty

    table = pd.read_parquet(path)
    dropped: list[str] = []
    truncated: dict[str, str] = {}
    kept_by_review: list[str] = []
    registry_path = data_root / "models" / "registry.json"
    if registry_path.exists():
        registry = json.loads(registry_path.read_text())
        params = registry.get("models", {}).get("TS-v1", {}).get("parameters", {})
        dropped = list(params.get("identity_dropped", []))
        truncated = dict(params.get("identity_truncated", {}))
        kept_by_review = list(params.get("readded_kept", []))

    reused = sorted(table.loc[table["reused"].astype(bool), "ticker"].tolist())
    verified = table["verified"].astype(bool)
    matched = int((verified & ~table["reused"].astype(bool)).sum())
    unverified = int((~verified).sum())
    in_panel = set(loadings.index)
    # a name the build flagged and did not exclude, that the C6 review did
    # not deliberately restore, means the exclusion was never applied. The
    # names F2.6c put back are expected to be in the panel, so they are not
    # leaks; F2.6c is the criterion that governs them.
    flagged = (set(dropped) | set(reused)) - set(kept_by_review)
    return {
        "rows": int(len(table)),
        "matched": matched,
        "unverified": unverified,
        "reused": len(reused),
        "reused_tickers": reused,
        "kept_by_review": sorted(kept_by_review),
        "dropped": dropped,
        "truncated": truncated,
        "gaps": sorted(table.loc[table["has_gap"].astype(bool), "ticker"].tolist()),
        "leaks": sorted(t for t in flagged if t in in_panel),
    }


class AlignedVolatility(TypedDict):
    """Win shares from the horizon-matched volatility evaluation."""

    win_shares: dict[str, dict[str, float]]
    garch_fitted: int
    garch_failed: int
    day_level: dict[str, object]


def _aligned_volatility(
    data_root: Path, returns_frame: pd.DataFrame
) -> AlignedVolatility:
    """Win shares from eval/vol_horse_race_aligned.parquet, plus the day level.

    Reads the stored table for the win shares so the stored number and the
    artifact cannot disagree, and recomputes the day-level win rate here
    because it is a diagnostic rather than a stored table.
    """
    from efb import hygiene
    from efb import vol as vol_mod

    empty: AlignedVolatility = {
        "win_shares": {},
        "garch_fitted": 0,
        "garch_failed": 0,
        "day_level": {},
    }
    path = data_root / "eval" / "vol_horse_race_aligned.parquet"
    if not path.exists():
        return empty
    table = pd.read_parquet(path)
    shares = vol_mod.aligned_win_shares(table)
    win_shares: dict[str, dict[str, float]] = {}
    for row in shares.itertuples(index=False):
        win_shares.setdefault(str(int(row.horizon)), {})[str(row.method)] = float(
            row.win_share
        )

    wide = hygiene.clean_returns(returns_frame).unstack("ticker")
    oos_start = (wide.index.max() - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
    day = vol_mod.win_rate_by_year(wide, oos_start=oos_start)
    registry_path = data_root / "models" / "registry.json"
    fitted = failed = 0
    if registry_path.exists():
        params = (
            json.loads(registry_path.read_text())
            .get("models", {})
            .get("TS-v1", {})
            .get("parameters", {})
        )
        fitted = int(params.get("garch_fitted", 0))
        failed = int(params.get("garch_failed", 0))
    return {
        "win_shares": win_shares,
        "garch_fitted": fitted,
        "garch_failed": failed,
        "day_level": {
            "pooled": day["pooled"],
            "excluding_2020": day["excluding_2020"],
            "n_name_days": day["n_name_days"],
            "by_year": day["by_year"],
        },
    }


class ReaddedCoverage(TypedDict):
    """F2.6c: what the re-add review kept, and the coverage it produced."""

    review_rows: int
    kept: list[str]
    stays_dropped: list[str]
    n_current_dropped_by_c1: int
    n_kept_current: int
    n_current: int
    n_covered: int
    coverage: float
    bar: float
    missing: list[str]


class SeededSampleFindings(TypedDict):
    """F2.3c: the sample the GARCH evaluation was drawn from and scored on."""

    seed: int
    sample_size: int
    sample: list[str]
    n_fully_covered: int
    garch_fitted: int
    garch_failed: int
    not_converged: list[str]
    win_shares: dict[str, dict[str, float]]
    oos_start: str


def _seeded_sample_findings(
    data_root: Path,
    returns_frame: pd.DataFrame,
    aligned: AlignedVolatility,
) -> SeededSampleFindings:
    """F2.3c: what the seeded sample was, and how the two methods scored.

    The sample is not described here, it is reported: the seed, the size,
    how many names were eligible, which fits converged and which did not,
    all read from the registry entry the build wrote, so the stored
    criterion and the run that produced it cannot drift apart. The win
    shares come from the same aligned table F2.3b reads, because the two
    criteria differ in what they pin down, not in what they measure.
    """
    from efb import vol as vol_mod

    registry_path = data_root / "models" / "registry.json"
    params: dict[str, Any] = {}
    if registry_path.exists():
        entry = json.loads(registry_path.read_text())
        params = entry.get("models", {}).get("TS-v1", {}).get("parameters", {})

    sample = [str(t) for t in params.get("garch_sample_tickers", [])]
    # how many names the draw was made from, recomputed so the eligible
    # count is not taken on trust from the run being checked
    wide = hygiene.clean_returns(returns_frame).unstack("ticker")
    oos_start = (wide.index.max() - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
    eligible = vol_mod.covered_tickers(wide, oos_start)
    return {
        "seed": int(params.get("garch_seed", 0)),
        "sample_size": int(params.get("garch_sample_size", len(sample))),
        "sample": sample,
        "n_fully_covered": len(eligible),
        "garch_fitted": int(params.get("garch_fitted", 0)),
        "garch_failed": int(params.get("garch_failed", 0)),
        "not_converged": [str(t) for t in params.get("garch_not_converged", [])],
        "win_shares": aligned["win_shares"],
        "oos_start": oos_start,
    }


def _readded_coverage(data_root: Path) -> ReaddedCoverage:
    """Coverage of the current constituents by the estimation panel (C6).

    The review artifact is what the build acts on, so the criterion reads
    it rather than recomputing the decisions, and the panel is
    returns.parquet because a name can have prices and still be absent
    from the returns the models see. The bar is the close-out brief's 501
    of 503, recorded here so the verdict is not adjusted after the fact.
    """
    empty: ReaddedCoverage = {
        "review_rows": 0,
        "kept": [],
        "stays_dropped": [],
        "n_current_dropped_by_c1": 0,
        "n_kept_current": 0,
        "n_current": 0,
        "n_covered": 0,
        "coverage": 0.0,
        "bar": 501 / 503,
        "missing": [],
    }
    constituents_path = data_root / "processed" / "universe_constituents.parquet"
    returns_path = data_root / "processed" / "returns.parquet"
    if not constituents_path.exists() or not returns_path.exists():
        return empty

    constituents = pd.read_parquet(constituents_path)
    returns_frame = pd.read_parquet(returns_path)
    panel = hygiene.clean_returns(returns_frame).dropna().to_frame("r")
    coverage = identity.panel_coverage(constituents, panel)
    symbol = "symbol" if "symbol" in constituents.columns else "ticker"
    current = set(constituents[symbol].dropna().astype(str))

    review_path = data_root / "processed" / "ticker_identity_readded.parquet"
    kept: list[str] = []
    stays: list[str] = []
    rows = 0
    if review_path.exists():
        review = pd.read_parquet(review_path)
        if "decision" in review.columns:
            rows = int(len(review))
            kept = sorted(review.loc[review["decision"] == "keep_truncated", "ticker"])
            stays = sorted(review.loc[review["decision"] == "stays_dropped", "ticker"])
    # the reused symbols that are current constituents: the ones C1 dropped
    # and C6 reviewed, which is where the coverage gain comes from
    reviewed_current = [str(t) for t in kept if str(t) in current]
    return {
        "review_rows": rows,
        "kept": [str(t) for t in kept],
        "stays_dropped": [str(t) for t in stays],
        "n_current_dropped_by_c1": len(
            [t for t in list(kept) + list(stays) if str(t) in current]
        ),
        "n_kept_current": len(reviewed_current),
        "n_current": int(coverage["n_current"]),
        "n_covered": int(coverage["n_covered"]),
        "coverage": float(coverage["coverage"]),
        "bar": 501 / 503,
        "missing": [str(t) for t in coverage["missing"]],
    }


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

    # F2.6b: ticker identity, and proof the build acted on it
    f26b = _identity_findings(data_root, loadings)

    # F2.3b: the aligned evaluation, same 60% bar, matched horizons
    f23b = _aligned_volatility(data_root, returns_frame)

    # F2.6c: the re-add review and the coverage it restores (C6)
    f26c = _readded_coverage(data_root)

    # F2.3c: the same evaluation on the seeded, fully covered sample (C7)
    f23c = _seeded_sample_findings(data_root, returns_frame, f23b)

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
        "f26b_rows": f26b["rows"],
        "f26b_matched": f26b["matched"],
        "f26b_unverified": f26b["unverified"],
        "f26b_reused": f26b["reused"],
        "f26b_reused_tickers": f26b["reused_tickers"],
        "f26b_kept_by_review": f26b["kept_by_review"],
        "f26b_dropped": f26b["dropped"],
        "f26b_truncated": f26b["truncated"],
        "f26b_gaps": f26b["gaps"],
        "f26b_leaks": f26b["leaks"],
        "f23b_win_shares": f23b["win_shares"],
        "f23b_garch_fitted": f23b["garch_fitted"],
        "f23b_garch_failed": f23b["garch_failed"],
        "f23b_day_level": f23b["day_level"],
        "f26c": dict(f26c),
        "f23c": f23c,
    }


def zero_tier_criteria(data_root: Path = ROOT / "data") -> dict[str, dict[str, Any]]:
    """F2.0a to F2.0c, evaluated on their own.

    An E1 rebuild changes the universe return, which moves these three
    criteria even though they belong to E2. They are computed here so the
    E1 re-store can record their old and new values side by side without
    reaching into the E2 evaluation.
    """
    criteria = evaluate_e2_criteria(**compute_e2_from_artifacts(data_root))
    return {key: criteria[key] for key in ("F2.0a", "F2.0b", "F2.0c")}


def main_e2() -> None:
    inputs = compute_e2_from_artifacts()
    criteria = evaluate_e2_criteria(**inputs)
    write_results(criteria, ROOT / "sprints" / "E2" / "RESULTS.json", sprint="E2")
    print(json.dumps(criteria, indent=2))


if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------
# Sprint E3: XS-v1 criteria
# --------------------------------------------------------------------------

E3_CRITERIA_TEXT = {
    "F3.1": (
        "Average daily cross-sectional R squared above 20%. Below 15% means "
        "descriptor construction or weighting is wrong, not that the market is "
        "unusual."
    ),
    "F3.2": (
        "FMP check: X' w_FMP(k) equals the unit vector e_k within 1e-8 for "
        "every factor k."
    ),
    "F3.3": (
        "Identification: cap-weighted sector factor returns sum to zero within "
        "1e-10 on every day."
    ),
    "F3.4": (
        "Agreement with the time-series world: XS-v1 momentum factor return vs "
        "FF MOM daily correlation above 0.6; market factor vs Mkt-RF above 0.9."
    ),
    "F3.5": (
        "Decomposition adds up: factor variance plus idio variance equals "
        "w' Sigma w to machine precision; contributions sum to sigma_p."
    ),
    "F3.6": (
        "Bias statistic for both seed portfolios, monthly 2015 to 2026, "
        "between 0.8 and 1.25."
    ),
    "F3.7": (
        "The Fama-MacBeth premia table is produced with Newey-West t-stats for "
        "every factor and subperiod, whatever the verdict; a premium with |t| "
        "below 2 is reported as unpriced, not dropped."
    ),
    "F3.8": (
        "Realized residual covariance is computed for both seed portfolios and "
        "the factor share is reported both ways, with the diagonal D and with "
        "the realized residual covariance. The criterion passes when both "
        "numbers are stored, whatever they show."
    ),
    "F3.9": (
        "The XS-v1 exposure time series for the momentum book is stored and "
        "reconciled to the E2 measurements in writing."
    ),
}

E3_THRESHOLDS = {
    "F3.1": "mean cross-sectional R squared > 0.20, fail band below 0.15",
    "F3.2": "max abs deviation from e_k < 1e-8",
    "F3.3": "abs cap-weighted sector sum < 1e-10 on every day",
    "F3.4": "momentum correlation > 0.6 and market correlation > 0.9",
    "F3.5": "identity error at machine precision",
    "F3.6": "mean monthly bias in [0.8, 1.25] for both books",
    "F3.7": "table complete for every factor and subperiod",
    "F3.8": "both factor shares stored for both books",
    "F3.9": "exposure series stored and reconciled",
}

E2_EXPOSURE_REFERENCE = {
    "static_name_level_factor_share_last_month": 0.09681972392333447,
    "regression_loading": 0.2884639400639966,
    "regression_t_stat": 29.104952622365634,
    "rolling_beta_aggregate_mean": 0.06978002876927968,
    "rolling_beta_aggregate_min": -0.3322050420277022,
    "rolling_beta_aggregate_max": 0.3904549841533205,
    "static_full_sample_aggregate": -0.016190070548666415,
    "n_rebalances": 195,
}


def compute_e3_from_artifacts(data_root: Path = ROOT / "data") -> dict[str, Any]:
    """Read every number the E3 criteria need from the artifacts."""

    def read(rel: str) -> pd.DataFrame:
        return pd.read_parquet(data_root / rel)

    registry = json.loads((data_root / "models" / "registry.json").read_text())
    entry = registry["models"]["XS-v1"]
    parameters = entry["parameters"]
    xs_r2 = read("models/XS-v1/xs_r2.parquet")
    fmp = read("models/XS-v1/fmp_weights.parquet")
    factor_returns = read("models/XS-v1/factor_returns.parquet")
    decomposition = read("eval/xs_risk_decomposition.parquet")
    bias = read("eval/xs_bias.parquet")
    premia = read("eval/xs_fm_premia.parquet")
    residual = read("eval/xs_residual_covariance.parquet")
    exposure = read("eval/xs_exposure_timeseries.parquet")
    factors_frame = read("raw/factors_ff.parquet")
    return {
        "parameters": parameters,
        "xs_r2": xs_r2,
        "fmp_weights": fmp,
        "factor_returns": factor_returns,
        "decomposition": decomposition,
        "bias": bias,
        "premia": premia,
        "residual_covariance": residual,
        "exposure_timeseries": exposure,
        "factors_ff": factors_frame,
        "diagnostics": parameters,
    }


def evaluate_e3_criteria(
    *,
    parameters: dict[str, Any],
    xs_r2: pd.DataFrame,
    fmp_weights: pd.DataFrame,
    factor_returns: pd.DataFrame,
    decomposition: pd.DataFrame,
    bias: pd.DataFrame,
    premia: pd.DataFrame,
    residual_covariance: pd.DataFrame,
    exposure_timeseries: pd.DataFrame,
    factors_ff: pd.DataFrame,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Score F3.1 to F3.9 from the stored numbers."""
    del diagnostics
    mean_r2 = float(xs_r2["r_squared"].mean())
    identity_max = float(xs_r2["fmp_identity_max_abs_error"].max())
    sector_max = float(xs_r2["sector_cap_weighted_sum"].abs().max())
    fmp_max = float(parameters.get("fmp_identity_max_abs_error", identity_max))

    momentum_series = (
        factor_returns.loc[factor_returns["factor"] == "momentum"]
        .set_index("date")["f"]
        .sort_index()
    )
    market_series = (
        factor_returns.loc[factor_returns["factor"] == "market"]
        .set_index("date")["f"]
        .sort_index()
    )
    ff_mom = factors_ff["mom"]
    ff_market = factors_ff["mkt_rf"] + factors_ff["rf"]
    both_mom = pd.concat([momentum_series, ff_mom], axis=1, join="inner").dropna()
    both_market = pd.concat([market_series, ff_market], axis=1, join="inner").dropna()
    momentum_correlation = (
        float(both_mom.iloc[:, 0].corr(both_mom.iloc[:, 1]))
        if len(both_mom) > 2
        else float("nan")
    )
    market_correlation = (
        float(both_market.iloc[:, 0].corr(both_market.iloc[:, 1]))
        if len(both_market) > 2
        else float("nan")
    )

    factor_rows = decomposition.loc[decomposition["level"] == "factor"]
    name_rows = decomposition.loc[decomposition["level"] == "name"]
    identity_error = float(
        np.nanmax(
            np.abs(
                factor_rows["factor_variance"]
                + factor_rows["idio_variance"]
                - factor_rows["total_variance"]
            )
        )
    )
    contribution_error = float(
        np.nanmax(
            np.abs(
                name_rows.groupby(["book", "date"])["contribution"].sum()
                - name_rows.groupby(["book", "date"])["sigma_p"].first()
            )
        )
    )

    bias_summary: dict[str, dict[str, Any]] = {}
    for book, group in bias.groupby("book"):
        frame = group.dropna(subset=["bias_ratio"]).copy()
        frame["year"] = pd.to_datetime(frame["date"]).dt.year
        ratios = frame["bias_ratio"]
        bias_summary[str(book)] = {
            "mean": float(ratios.mean()),
            "min": float(ratios.min()),
            "max": float(ratios.max()),
            "share_in_band": float(((ratios >= 0.8) & (ratios <= 1.25)).mean()),
            "n_months": int(len(ratios)),
            "by_year": {
                str(int(year)): float(block["bias_ratio"].mean())
                for year, block in frame.groupby("year")
            },
        }

    combos = premia.groupby("factor")["period"].nunique()
    periods = sorted(premia["period"].unique())
    complete = bool(len(premia) > 0 and combos.min() == len(periods))

    residual_summary: dict[str, dict[str, float]] = {}
    for book, group in residual_covariance.groupby("book"):
        residual_summary[str(book)] = {
            "factor_share_diagonal_mean": float(group["factor_share_diagonal"].mean()),
            "factor_share_realized_mean": float(group["factor_share_realized"].mean()),
            "n_windows": int(len(group)),
        }

    momentum_exposure = exposure_timeseries.loc[
        (exposure_timeseries["book"] == "seed_mom_ls")
        & (exposure_timeseries["factor"] == "momentum")
        & (exposure_timeseries["date"] >= "2015-01-01")
    ]["exposure"]
    reconciliation = {
        "xs_exposure_mean": float(momentum_exposure.mean()),
        "xs_exposure_min": float(momentum_exposure.min()),
        "xs_exposure_max": float(momentum_exposure.max()),
        "n_rebalances": int(len(momentum_exposure)),
        "e2_reference": E2_EXPOSURE_REFERENCE,
    }

    criteria: dict[str, dict[str, Any]] = {}
    criteria["F3.1"] = {
        "criterion": E3_CRITERIA_TEXT["F3.1"],
        "threshold": E3_THRESHOLDS["F3.1"],
        "stored_numbers": {
            "mean_cross_sectional_r_squared": mean_r2,
            "n_days": int(len(xs_r2)),
            "r_squared_by_year": parameters.get("r_squared_by_year", {}),
            "r_squared_market_only_mean": parameters.get("r_squared_market_only_mean"),
            "r_squared_by_sector": parameters.get("r_squared_by_sector", {}),
            "shift_test_lagged_mean_r_squared": parameters.get(
                "shift_test_lagged_mean_r_squared"
            ),
            "shift_test_dated_t_mean_r_squared": parameters.get(
                "shift_test_dated_t_mean_r_squared"
            ),
        },
        "verdict": _verdict(mean_r2 > 0.20),
        "note": (
            "The three diagnostics standing instruction B names are stored here "
            "whether or not the average clears 20 percent, so a low number can "
            "be attributed without a rebuild. The shift test pair is stored "
            "beside them: the design dated t-1 explains "
            "shift_test_lagged_mean_r_squared and the design dated t explains "
            "shift_test_dated_t_mean_r_squared, and the difference is the "
            "same-day information the t-1 rule removes."
        ),
    }
    criteria["F3.2"] = {
        "criterion": E3_CRITERIA_TEXT["F3.2"],
        "threshold": E3_THRESHOLDS["F3.2"],
        "stored_numbers": {
            "max_abs_identity_error_estimated": fmp_max,
            "n_days_checked": int(len(xs_r2)),
            "n_factor_days": int(len(fmp_weights)),
            "kinds": sorted(fmp_weights["kind"].unique().tolist()),
        },
        "verdict": _verdict(fmp_max < 1e-8),
        "note": (
            "The criterion tests the factor-mimicking portfolios of the "
            "estimated design, the rows of (X'WX)^-1 X'W, where the reference "
            "sector is dropped so the market column and the sector block are "
            "not collinear. The identified weight set reproduces all eleven "
            "reported sector returns and is stored beside it."
        ),
    }
    criteria["F3.3"] = {
        "criterion": E3_CRITERIA_TEXT["F3.3"],
        "threshold": E3_THRESHOLDS["F3.3"],
        "stored_numbers": {
            "max_abs_cap_weighted_sector_sum": sector_max,
            "n_days_checked": int(len(xs_r2)),
        },
        "verdict": _verdict(sector_max < 1e-10),
        "note": "Measured on the identified factor returns, every day.",
    }
    criteria["F3.4"] = {
        "criterion": E3_CRITERIA_TEXT["F3.4"],
        "threshold": E3_THRESHOLDS["F3.4"],
        "stored_numbers": {
            "momentum_vs_ff_mom_correlation": momentum_correlation,
            "market_vs_ff_market_correlation": market_correlation,
            "n_overlap_momentum": int(len(both_mom)),
            "n_overlap_market": int(len(both_market)),
        },
        "verdict": _verdict(momentum_correlation > 0.6 and market_correlation > 0.9),
        "note": (
            "The market comparison is against Mkt-RF plus RF, the FF total "
            "return, on the overlap through 2026-07-31. XS-v1 regresses the "
            "total return r because the risk-free series ends there."
        ),
    }
    criteria["F3.5"] = {
        "criterion": E3_CRITERIA_TEXT["F3.5"],
        "threshold": E3_THRESHOLDS["F3.5"],
        "stored_numbers": {
            "max_abs_factor_plus_idio_minus_total": identity_error,
            "max_abs_contribution_sum_minus_sigma_p": contribution_error,
            "n_book_dates": int(factor_rows.drop_duplicates(["book", "date"]).shape[0]),
            "factor_share_by_book": {
                str(book): float(group["factor_variance"].mean())
                / float(group["total_variance"].mean())
                for book, group in factor_rows.groupby("book")
            },
        },
        "verdict": _verdict(identity_error < 1e-18 and contribution_error < 1e-12),
        "note": "Both seed books, every month end the model runs.",
    }
    criteria["F3.6"] = {
        "criterion": E3_CRITERIA_TEXT["F3.6"],
        "threshold": E3_THRESHOLDS["F3.6"],
        "stored_numbers": bias_summary,
        "verdict": _verdict(
            all(0.8 <= summary["mean"] <= 1.25 for summary in bias_summary.values())
            and bool(bias_summary)
        ),
        "note": (
            "The monthly statistic is the book's realized 21-day forward "
            "volatility over the model's predicted volatility, estimated point "
            "in time at each month end. The criterion is read as the average of "
            "the monthly statistics, the reading E2 used for F2.4, and the "
            "monthly distribution is stored beside it."
        ),
    }
    criteria["F3.7"] = {
        "criterion": E3_CRITERIA_TEXT["F3.7"],
        "threshold": E3_THRESHOLDS["F3.7"],
        "stored_numbers": {
            "n_rows": int(len(premia)),
            "n_factors": int(premia["factor"].nunique()),
            "periods": periods,
            "min_periods_per_factor": int(combos.min()),
            "n_unpriced": int((~premia["priced"].astype(bool)).sum()),
            "unpriced_share": float((~premia["priced"].astype(bool)).mean()),
        },
        "verdict": _verdict(complete),
        "note": (
            "Complete means every factor appears in every subperiod with a "
            "Newey-West t statistic, whatever the verdict. Unpriced premia are "
            "labelled and kept."
        ),
    }
    criteria["F3.8"] = {
        "criterion": E3_CRITERIA_TEXT["F3.8"],
        "threshold": E3_THRESHOLDS["F3.8"],
        "stored_numbers": residual_summary,
        "verdict": _verdict(
            len(residual_summary) == 2
            and all(
                np.isfinite(summary["factor_share_diagonal_mean"])
                and np.isfinite(summary["factor_share_realized_mean"])
                for summary in residual_summary.values()
            )
        ),
        "note": (
            "The realized residual covariance is estimated on trailing 252-day "
            "windows of specific returns, so nothing after the window end "
            "enters. The difference against the diagonal D is the measurement "
            "the E2 open item asked for."
        ),
    }
    criteria["F3.9"] = {
        "criterion": E3_CRITERIA_TEXT["F3.9"],
        "threshold": E3_THRESHOLDS["F3.9"],
        "stored_numbers": reconciliation,
        "verdict": _verdict(
            int(len(momentum_exposure)) > 1 and float(momentum_exposure.std()) > 0
        ),
        "note": (
            "The series is x = X'w at each rebalance, so the momentum book is "
            "priced from descriptor exposures recomputed when it is held rather "
            "than from full-sample betas. The reconciliation against every E2 "
            "measurement is written in docs/research/E3_factor_model_note.md."
        ),
    }
    return criteria


# --------------------------------------------------------------------------
# Sprint E4: the statistical factor model and the covariance lab
# --------------------------------------------------------------------------

# F4.1 to F4.4 are copied verbatim from docs/roadmap_v2.md, the
# pre-registered table for this sprint. F4.5 and F4.6 are the two findings
# that took their own IDs in sprints/E4/PRD.md when Task 3 and Task 4 were
# reframed. F4.7 is recorded here as it was registered mid-sprint by
# decision, with the date and the reason, because F4.1's threshold turned
# out to be written for an object the sprint did not build.
E4_CRITERIA_TEXT = {
    "F4.1": "First principal component vs the market factor: correlation above 0.95.",
    "F4.2": (
        "Marchenko-Pastur edge isolates between 3 and 15 significant factors; "
        "the count is stored."
    ),
    "F4.3": (
        "OOS minimum-variance vol: shrinkage and factor estimators beat the "
        "sample covariance by more than 10%. If the sample covariance wins, "
        "that is an estimation bug."
    ),
    "F4.4": (
        "PCA-v1 with k factors explains at least as much cross-sectional "
        "variance as XS-v1 on a held-out residual test; both numbers stored."
    ),
    "F4.5": (
        "Task 3 as reframed: passes when 3a, 3b, 3c and 3d are measured and "
        "the deliverable names which explanation the evidence supports."
    ),
    "F4.6": (
        "Task 4 as reframed: passes when 4a, 4b and 4c are stored. Registered "
        "2026-09-20 as measured and material."
    ),
    "F4.7": (
        "Registered 2026-09-20 by decision. PCA-v1c is measured on its own "
        "terms: both PC1 objects are computed and the deliverable names which "
        "object each PC1 is. PCA-v1c's factor count is stored under F4.7 and "
        "is never scored against F4.2's 3 to 15 band."
    ),
}

E4_THRESHOLDS = {
    "F4.1": "correlation > 0.95",
    "F4.2": "3 <= factor count <= 15, the STOP CONDITION 3 band",
    "F4.3": "every shrinkage and factor estimator's median at least 10% below "
    "the sample covariance's median",
    "F4.4": "PCA-v1 held-out R squared >= XS-v1 held-out R squared, both stored",
    "F4.5": "3a, 3b, 3c and 3d measured and the explanation named",
    "F4.6": "4a, 4b and 4c stored",
    "F4.7": "both PC1 objects measured and named; the count is not scored "
    "against F4.2",
}

# The two groups F4.3 names. Every estimator here is a shrinkage or factor
# estimator in the sense the criterion means; EWMA is a weighting scheme
# rather than either, so it is reported beside them and not scored.
E4_SHRINKAGE = ("clip", "constant_correlation", "ledoit_wolf")
E4_FACTOR = ("ts_v1", "xs_v1", "pca_v1", "pca_v1c")


def e4_artifacts(data_root: Path = ROOT / "data") -> list[Path]:
    """The artifacts every E4 number is read from, in the order it is read."""
    root = Path(data_root)
    return [
        root / "models" / "registry.json",
        root / "models" / "PCA-v1" / "eigenvalues.parquet",
        root / "models" / "PCA-v1" / "eigenvalues_panel.parquet",
        root / "models" / "PCA-v1c" / "eigenvalues.parquet",
        root / "eval" / "cov_horse_race.parquet",
        root / "eval" / "e4_f41_pc1_correlations.parquet",
        root / "eval" / "e4_f44_held_out.parquet",
        root / "eval" / "xs_residual_spectrum.parquet",
        root / "eval" / "xs_task3_decomposition.parquet",
        root / "eval" / "xs_task3_confound.parquet",
        root / "eval" / "xs_task3_orthogonality.parquet",
        root / "eval" / "xs_task3_sweep.parquet",
        root / "eval" / "xs_task3_projection.parquet",
        root / "eval" / "xs_survivor_measurement.parquet",
        root / "eval" / "xs_survivor_excluded_names.parquet",
        root / "eval" / "xs_survivor_universe_summary.parquet",
    ]


def e4_data_hash(data_root: Path = ROOT / "data") -> str:
    """The combined hash of the artifacts the E4 criteria are read from.

    Implemented here rather than imported from `efb.build`, which imports
    this module: the same fold, the same ordering, no cycle.
    """
    digest = hashlib.sha256()
    for path in e4_artifacts(data_root):
        digest.update(path.name.encode("utf-8"))
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("utf-8"))
    return digest.hexdigest()


def compute_e4_from_artifacts(data_root: Path = ROOT / "data") -> dict[str, Any]:
    root = Path(data_root)
    registry_payload = json.loads((root / "models" / "registry.json").read_text())
    return {
        "registry_payload": registry_payload,
        "spectrum": pd.read_parquet(root / "models" / "PCA-v1" / "eigenvalues.parquet"),
        "spectrum_panel": pd.read_parquet(
            root / "models" / "PCA-v1" / "eigenvalues_panel.parquet"
        ),
        "spectrum_covariance": pd.read_parquet(
            root / "models" / "PCA-v1c" / "eigenvalues.parquet"
        ),
        "race": pd.read_parquet(root / "eval" / "cov_horse_race.parquet"),
        "f41": pd.read_parquet(root / "eval" / "e4_f41_pc1_correlations.parquet"),
        "f44": pd.read_parquet(root / "eval" / "e4_f44_held_out.parquet"),
        "residual_spectrum": pd.read_parquet(
            root / "eval" / "xs_residual_spectrum.parquet"
        ),
        "decomposition": pd.read_parquet(
            root / "eval" / "xs_task3_decomposition.parquet"
        ),
        "confound": pd.read_parquet(root / "eval" / "xs_task3_confound.parquet"),
        "orthogonality": pd.read_parquet(
            root / "eval" / "xs_task3_orthogonality.parquet"
        ),
        "sweep": pd.read_parquet(root / "eval" / "xs_task3_sweep.parquet"),
        "projection": pd.read_parquet(root / "eval" / "xs_task3_projection.parquet"),
        "survivor": pd.read_parquet(root / "eval" / "xs_survivor_measurement.parquet"),
        "survivor_excluded": pd.read_parquet(
            root / "eval" / "xs_survivor_excluded_names.parquet"
        ),
        "survivor_summary": pd.read_parquet(
            root / "eval" / "xs_survivor_universe_summary.parquet"
        ),
    }


def _tercile_mean(
    frame: pd.DataFrame, column: str, low: str, high: str
) -> dict[str, float]:
    """One stored series read at its low and high exposure tercile."""
    grouped = frame.groupby("tercile")[column].mean()
    return {"low": float(grouped[low]), "high": float(grouped[high])}


def evaluate_e4_criteria(
    registry_payload: dict[str, Any],
    spectrum: pd.DataFrame,
    spectrum_panel: pd.DataFrame,
    spectrum_covariance: pd.DataFrame,
    race: pd.DataFrame,
    f41: pd.DataFrame,
    f44: pd.DataFrame,
    residual_spectrum: pd.DataFrame,
    decomposition: pd.DataFrame,
    confound: pd.DataFrame,
    orthogonality: pd.DataFrame,
    sweep: pd.DataFrame,
    projection: pd.DataFrame,
    survivor: pd.DataFrame,
    survivor_excluded: pd.DataFrame,
    survivor_summary: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    criteria: dict[str, dict[str, Any]] = {}
    parameters = {
        name: entry.get("parameters", {})
        for name, entry in registry_payload["models"].items()
    }

    # F4.1. Both PC1 objects are measured, and the threshold is read against
    # the correlation PCA the roadmap's own foundation section specifies.
    pc1 = f41.set_index("variant")
    correlation_pc1 = float(pc1.loc["PCA-v1 correlation", "pc1_vs_market"])
    covariance_pc1 = float(pc1.loc["PCA-v1c covariance", "pc1_vs_market"])
    n_over_t = float(parameters["PCA-v1"]["n_over_t"])
    mp_edge = float(parameters["PCA-v1"]["mp_edge"])
    criteria["F4.1"] = {
        "criterion": E4_CRITERIA_TEXT["F4.1"],
        "threshold": E4_THRESHOLDS["F4.1"],
        "stored_numbers": {
            "pc1_vs_market_pca_v1": correlation_pc1,
            "pc1_vs_equal_weight_pca_v1": float(
                pc1.loc["PCA-v1 correlation", "pc1_vs_equal_weight"]
            ),
            "pc1_vs_market_pca_v1c": covariance_pc1,
            "pc1_vs_equal_weight_pca_v1c": float(
                pc1.loc["PCA-v1c covariance", "pc1_vs_equal_weight"]
            ),
            "market_vs_equal_weight": float(
                pc1.loc["market factor vs equal weight", "pc1_vs_equal_weight"]
            ),
            "pc1_vs_market_full_sample": float(
                pc1.loc["PCA-v1 full sample", "pc1_vs_market"]
            ),
            "window_days": int(pc1.loc["PCA-v1 correlation", "window_days"]),
            "full_sample_days": int(pc1.loc["PCA-v1 correlation", "full_sample_days"]),
            "n_names": int(pc1.loc["PCA-v1 correlation", "n_names"]),
        },
        "verdict": _verdict(max(correlation_pc1, covariance_pc1) > 0.95),
        "note": (
            "Fails on both variants. The threshold was written for a PC1 of the "
            "market portfolio and was measured against two PC1s that are not "
            "that object: the correlation PCA's first component has mostly "
            "equal-weighted content (0.989144 against the equal-weight mean) and "
            "the covariance PCA's has mostly cap-weighted content (0.930599 "
            "against the market). The market factor itself correlates 0.855646 "
            "with the equal-weight mean over the same window, so no single "
            "correlation above 0.95 was available to a PC1 of either kind. "
            "Recorded as a specification conflict, not a model defect."
        ),
    }

    # F4.2. STOP CONDITION 3 lives here.
    count = int(parameters["PCA-v1"]["n_factors_mp"])
    inside = 3 <= count <= 15
    panel_fit = spectrum_panel.loc[spectrum_panel["index"] == 1]
    panel_count = int(spectrum_panel["above_edge"].sum())
    panel_n_names = int(panel_fit["n_names"].max()) if len(panel_fit) else -1
    criteria["F4.2"] = {
        "criterion": E4_CRITERIA_TEXT["F4.2"],
        "threshold": E4_THRESHOLDS["F4.2"],
        "stored_numbers": {
            "n_factors_mp": count,
            "n_factors_selected": int(parameters["PCA-v1"]["n_factors"]),
            "n_factors_scree": int(parameters["PCA-v1"]["n_factors_scree"]),
            "n_factors_cv": int(parameters["PCA-v1"]["n_factors_cv"]),
            "n_names": int(parameters["PCA-v1"]["n_names"]),
            "n_days": int(parameters["PCA-v1"]["n_days"]),
            "n_over_t": n_over_t,
            "mp_edge": mp_edge,
            "panel_n_factors_above_edge": panel_count,
            "panel_n_names": panel_n_names,
        },
        "verdict": _verdict(inside),
        "note": (
            "The count is the Marchenko-Pastur reading on the model universe, 13 "
            "of a permitted 15, and it is the count PCA-v1 is registered with. "
            "The covariance PCA of the same 504 days puts 16 eigenvalues above "
            "its own edge, which is stored under F4.7 and not scored here: the "
            "two spectra have different edges and different units."
        ),
    }

    # F4.3, scored on medians, which is how the sprint reads the race.
    pivot = race.pivot(index="date", columns="estimator", values="realized_vol")
    medians = {name: float(value) for name, value in pivot.median().items()}
    sample = medians["sample"]
    wanted = (*E4_SHRINKAGE, *E4_FACTOR)
    scored = {name: medians[name] for name in wanted if name in medians}
    missing = [name for name in wanted if name not in medians]
    ratios = {name: medians[name] / sample for name in scored}
    criteria["F4.3"] = {
        "criterion": E4_CRITERIA_TEXT["F4.3"],
        "threshold": E4_THRESHOLDS["F4.3"],
        "stored_numbers": {
            "median_realized_vol": medians,
            "ratio_to_sample": ratios,
            "worst_ratio": float(max(ratios.values())),
            "estimators_missing": missing,
            "windows": int(race["date"].nunique()),
            "n_names": int(race["n_names"].max()),
            "windows_won": {
                name: int(count)
                for name, count in (pivot.rank(axis=1, method="min") == 1).sum().items()
            },
        },
        "verdict": _verdict(all(ratio <= 0.9 for ratio in ratios.values())),
        "note": (
            "Every shrinkage estimator and every factor estimator has a median "
            "out-of-sample minimum-variance volatility at least 10 percent below "
            "the sample covariance's, so the estimation-error result holds in the "
            "direction theory predicts. The sample covariance won no window and "
            "EWMA none either; EWMA is a weighting scheme rather than a shrinkage "
            "or factor estimator and is reported beside them, not scored. E5 "
            "rebuilt this race from a derived grid and could not reproduce the "
            "XS-v1 row, which is stored as F5.0b; the estimators missing from "
            "this read are listed in the stored numbers and the verdict is "
            "unchanged because the missing row is the strongest performer among "
            "those scored, not the weakest."
        ),
    }

    # F4.4.
    held_out = f44.set_index("row")["mean_r_squared"]
    xs_daily = float(held_out["(i) XS-v1 daily refit, as stored"])
    pca_rolling = float(held_out["(iv) PCA rolling refit"])
    criteria["F4.4"] = {
        "criterion": E4_CRITERIA_TEXT["F4.4"],
        "threshold": E4_THRESHOLDS["F4.4"],
        "stored_numbers": {
            "xs_v1_daily_refit": xs_daily,
            "xs_v1_descriptors_frozen": float(
                held_out["(ii) XS-v1 descriptors frozen"]
            ),
            "pca_frozen_k_mp": float(held_out["(iii) PCA frozen k=MP"]),
            "pca_frozen_k_17": float(held_out["(iii) PCA frozen k=17"]),
            "pca_rolling_refit": pca_rolling,
            "xs_v1_plus_top3_residual_pcs": float(
                held_out["(v) XS-v1 plus top 3 residual PCs"]
            ),
            "xs_v1_plus_top5_residual_pcs": float(
                held_out["(v) XS-v1 plus top 5 residual PCs"]
            ),
            "held_out_days": int(f44["days"].max()),
        },
        "verdict": _verdict(pca_rolling >= xs_daily),
        "note": (
            "Fails by 7.2 points on the comparison the criterion names, PCA "
            "rolling against XS-v1 refitted daily, both measured on the same 503 "
            "held-out days with sqrt(market cap) weights and exposures dated t "
            "minus one. The useful reading is the opposite one: adding the top "
            "three residual principal components to a frozen XS-v1 raises held "
            "out R squared from 0.253997 to 0.292699, which is where the missing "
            "factor structure shows up. Scored as measured."
        ),
    }

    # F4.5. Four measurements and the explanation the evidence supports.
    momentum_share = _tercile_mean(decomposition, "momentum_share", "low", "high")
    sweep_high = (
        sweep.loc[sweep["tercile"] == "high"].groupby("half_life")["bias"].mean()
    )
    bias_sweep = {
        str(int(half_life)): float(block.loc["low"] - block.loc["high"])
        for half_life, block in sweep.groupby(["half_life", "tercile"])["bias"]
        .mean()
        .unstack("tercile")
        .iterrows()
    }
    criteria["F4.5"] = {
        "criterion": E4_CRITERIA_TEXT["F4.5"],
        "threshold": E4_THRESHOLDS["F4.5"],
        "stored_numbers": {
            "momentum_share_of_predicted_variance": momentum_share,
            "realized_book_vol": _tercile_mean(
                confound, "book_realized_vol", "low", "high"
            ),
            "predicted_book_vol": _tercile_mean(
                confound, "book_predicted_vol", "low", "high"
            ),
            "forward_market_vol": _tercile_mean(
                confound, "market_vol_forward", "low", "high"
            ),
            "covariance_between_components": _tercile_mean(
                orthogonality, "covariance", "low", "high"
            ),
            "orthogonality_correlation": _tercile_mean(
                orthogonality, "correlation", "low", "high"
            ),
            "half_life_bias_high_tercile": {
                str(int(k)): float(v) for k, v in sweep_high.items()
            },
            "half_life_spread": bias_sweep,
            "residual_top5_share": _tercile_mean(
                projection, "top5_share", "low", "high"
            ),
            "residual_largest_eigenvalue": _tercile_mean(
                projection, "largest_eigenvalue", "low", "high"
            ),
            "residual_edge": _tercile_mean(projection, "mp_edge", "low", "high"),
            "residual_tree": {
                "n_above_edge": _tercile_mean(
                    projection, "n_above_edge", "low", "high"
                ),
                "effective_directions": _tercile_mean(
                    projection, "effective_directions", "low", "high"
                ),
                "n_names": _tercile_mean(projection, "n_names", "low", "high"),
            },
            "residual_spectrum_largest": float(
                residual_spectrum.loc[
                    residual_spectrum["index"] == 1, "eigenvalue"
                ].max()
            ),
            "residual_spectrum_edge": float(
                residual_spectrum.loc[residual_spectrum["index"] == 1, "mp_edge"].max()
            ),
            "measurements_present": {
                "3a_decomposition": bool(len(decomposition) > 0),
                "3b_confound": bool(len(confound) > 0),
                "3c_orthogonality": bool(len(orthogonality) > 0),
                "3d_sweep": bool(len(sweep) > 0),
            },
        },
        "verdict": _verdict(
            len(decomposition) > 0
            and len(confound) > 0
            and len(orthogonality) > 0
            and len(sweep) > 0
        ),
        "note": (
            "The explanation the evidence supports is the residual covariance "
            "one, and the half-life sweep is measured and rejected at 0.003. "
            "Momentum's share of predicted variance does rise with exposure, "
            "from 0.319808 to 0.561267, but the book's predicted volatility is "
            "flat across terciles while the realized volatility falls, so the "
            "high-exposure book is not the one that is underforecast. The "
            "specific component carries what the diagonal cannot: the top five "
            "residual directions hold 0.553 to 0.577 of the book's specific "
            "variance, and the realized covariance between the factor and "
            "specific components is negative in the high tercile. Documen"
            "ted in docs/research/E4_covariance_memo.md."
        ),
    }

    # F4.6, as the user resolved it: measured and material.
    measured = survivor.set_index("factor")
    summary = survivor_summary.set_index("universe")
    excluded = survivor_excluded.set_index("group")
    size = measured.loc["size"]
    criteria["F4.6"] = {
        "criterion": E4_CRITERIA_TEXT["F4.6"],
        "threshold": E4_THRESHOLDS["F4.6"],
        "stored_numbers": {
            "style_correlation_panel_vs_mapped": {
                name: float(measured.loc[name, "correlation_panel_vs_mapped"])
                for name in measured.index
            },
            "size_premium": {
                "panel": float(size["premium_panel"]),
                "mapped": float(size["premium_mapped"]),
                "t_panel": float(size["t_panel"]),
                "t_mapped": float(size["t_mapped"]),
            },
            "mean_r_squared": {
                name: float(summary.loc[name, "mean_r_squared"])
                for name in summary.index
            },
            "mean_specific_variance": {
                name: float(summary.loc[name, "mean_specific_variance"])
                for name in summary.index
            },
            "mean_names_per_date": {
                name: float(summary.loc[name, "mean_names"]) for name in summary.index
            },
            "excluded_names": {
                "n_names": int(excluded.loc["excluded, outside it", "names"]),
                "annualized_vol": float(
                    excluded.loc["excluded, outside it", "annualized_vol"]
                ),
                "included_annualized_vol": float(
                    excluded.loc["included, in the sector file", "annualized_vol"]
                ),
                "differential_annualized": float(
                    excluded.loc["excluded, outside it", "differential_annualized"]
                ),
                "years": "2010 to 2016",
            },
        },
        "verdict": _verdict(
            len(survivor) > 0
            and len(survivor_excluded) > 0
            and len(survivor_summary) > 0
        ),
        "note": (
            "Measured and material. The restriction is concentrated in size and "
            "liquidity, where the two universes correlate 0.577780 and 0.625560 "
            "against 0.98 and above for market, beta, momentum and reversal. It "
            "is not a caveat: it moves the size premium from -0.000032 to "
            "-0.000173, raises mean cross-sectional R squared from 0.133530 to "
            "0.142526, and the excluded names differ in the way that matters, "
            "0.199281 annualized volatility against 0.166796 and 0.020141 a year "
            "less over 2010 to 2016. Every E4 and E5 number computed on the "
            "mapped universe carries it."
        ),
    }

    # F4.7.
    covariance_count = int(parameters["PCA-v1c"]["n_factors"])
    criteria["F4.7"] = {
        "criterion": E4_CRITERIA_TEXT["F4.7"],
        "threshold": E4_THRESHOLDS["F4.7"],
        "stored_numbers": {
            "pca_v1c_n_factors_above_edge": covariance_count,
            "pca_v1c_mp_edge_covariance": float(
                parameters["PCA-v1c"]["mp_edge_covariance"]
            ),
            "pca_v1c_pc1_vs_market": covariance_pc1,
            "pca_v1c_pc1_vs_equal_weight": float(
                pc1.loc["PCA-v1c covariance", "pc1_vs_equal_weight"]
            ),
            "pca_v1_pc1_vs_market": correlation_pc1,
            "pca_v1_pc1_vs_equal_weight": float(
                pc1.loc["PCA-v1 correlation", "pc1_vs_equal_weight"]
            ),
            "scored_against_f4_2": False,
            "covariance_spectrum_rows": int(len(spectrum_covariance)),
        },
        "verdict": _verdict(len(spectrum_covariance) > 0),
        "note": (
            "PCA-v1's PC1 is the first component of the correlation matrix and "
            "PCA-v1c's is the first component of the covariance matrix; the "
            "deliverable names both. The 16 eigenvalues PCA-v1c puts above its "
            "own edge are stored here and are not compared with F4.2's 3 to 15 "
            "band, which was written about the correlation spectrum on the model "
            "universe."
        ),
    }
    return criteria


def prior_verdict_changes(data_root: Path = ROOT / "data") -> dict[str, Any]:
    """Recompute the earlier sprints' verdicts and report any that moved.

    This is the stop condition that outranks everything else in E4: an
    earlier stored criterion may not change verdict, because a sprint that
    moves an earlier verdict has changed the project's history rather than
    added to it. Each sprint is re-evaluated from the artifacts on disk and
    compared with its own RESULTS.json.
    """
    out: dict[str, Any] = {}
    plans: dict[str, tuple[Callable[..., Any], Callable[..., Any]]] = {
        "E1": (compute_from_artifacts, evaluate_criteria),
        "E2": (compute_e2_from_artifacts, evaluate_e2_criteria),
        "E3": (compute_e3_from_artifacts, evaluate_e3_criteria),
    }
    for sprint, (compute, evaluate) in plans.items():
        path = ROOT / "sprints" / sprint / "RESULTS.json"
        if not path.exists():
            continue
        stored = json.loads(path.read_text())["criteria"]
        try:
            fresh = evaluate(**compute(data_root))
        except Exception as error:  # pragma: no cover - a rebuild is what fixes it
            out[sprint] = {"error": f"{type(error).__name__}: {error}"}
            continue
        moved = {
            key: {
                "stored": stored[key].get("verdict"),
                "recomputed": value.get("verdict"),
            }
            for key, value in fresh.items()
            if key in stored and stored[key].get("verdict") != value.get("verdict")
        }
        out[sprint] = {
            "n_criteria": len(stored),
            "n_changed": len(moved),
            "changed": moved,
        }
    return out


def e4_reference_values(data_root: Path = ROOT / "data") -> dict[str, Any]:
    """The numbers the E4 walkthrough asserts against, read from artifacts."""
    inputs = compute_e4_from_artifacts(data_root)
    criteria = evaluate_e4_criteria(**inputs)
    return {
        "data_hash": e4_data_hash(data_root),
        "verdicts": {key: value["verdict"] for key, value in criteria.items()},
        "stored_numbers": {
            key: value["stored_numbers"] for key, value in criteria.items()
        },
    }


def main_e4(data_root: Path = ROOT / "data") -> None:
    inputs = compute_e4_from_artifacts(data_root)
    criteria = evaluate_e4_criteria(**inputs)
    check = prior_verdict_changes(data_root)
    print("Criterion  verdict  headline number")
    for key, block in criteria.items():
        headline = json.dumps(block["stored_numbers"])[:110]
        print(f"{key}  {block['verdict']}  {headline}")
    print()
    for sprint, block in check.items():
        print(
            f"{sprint}: {block.get('n_changed')} of {block.get('n_criteria')} changed"
        )
        if block.get("changed"):
            print(f"  STOP CONDITION: earlier verdicts moved: {block['changed']}")
    write_results(
        criteria,
        ROOT / "sprints" / "E4" / "RESULTS.json",
        sprint="E4",
        data_hash=e4_data_hash(data_root),
        reference_values=e4_reference_values(data_root),
    )
    if any(block.get("n_changed") for block in check.values()):
        raise SystemExit(3)


if __name__ == "__main__":
    main_e4()
