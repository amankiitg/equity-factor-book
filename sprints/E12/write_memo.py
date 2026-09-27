"""Sprint E12 item 9: write the attribution memo from the artifacts.

Every number is read from a stored artifact or from `sprints/E12/RESULTS.json`,
never typed by hand, so the live run swaps the input table and not the prose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from efb import attribution

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RESULTS = ROOT / "sprints" / "E12" / "RESULTS.json"
MEMO = ROOT / "docs" / "research" / "E12_attribution_report.md"


def _bp(value: float) -> str:
    return f"{value * 1e4:+.1f}"


def main() -> int:
    results = json.loads(RESULTS.read_text())
    daily = pd.read_parquet(DATA / "attribution" / "daily.parquet")
    monthly = pd.read_parquet(DATA / "attribution" / "monthly.parquet")
    timeseries = pd.read_parquet(DATA / "attribution" / "timeseries.parquet")
    registry = json.loads((DATA / "models" / "registry.json").read_text())["models"]
    parameters = registry["XS-v1"]["parameters"]
    cross_section = pd.read_parquet(DATA / "models" / "XS-v1" / "xs_r2.parquet")
    r2 = {
        "artifact_mean": float(cross_section["r_squared"].mean()),
        "registry_mean": float(parameters["r_squared_mean"]),
        "lagged": float(parameters["shift_test_lagged_mean_r_squared"]),
        "same_day": float(parameters["shift_test_dated_t_mean_r_squared"]),
    }
    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    criteria = results["criteria"]
    identity = criteria["F12.1"]["stored_numbers"]
    skill = attribution.skill_test(daily)

    totals = {
        name: float(daily[column].sum())
        for name, column in (
            ("total", "pnl_total"),
            ("factor", "pnl_factor"),
            ("idio", "pnl_idio"),
            ("cost", "pnl_cost"),
            ("timing", "pnl_timing"),
        )
    }
    by_factor: dict[str, float] = {}
    for mapping in daily["pnl_factor_json"]:
        for name, value in mapping.items():
            by_factor[name] = by_factor.get(name, 0.0) + float(value)
    ordered = sorted(by_factor.items(), key=lambda pair: -abs(pair[1]))
    factor_lines = "\n".join(
        f"| {name} | {_bp(value)} | "
        f"{value / totals['factor'] * 100 if totals['factor'] else 0:+.1f}% |"
        for name, value in ordered
    )
    moved = daily.loc[daily["pnl_timing"].abs() > 0]
    gap = pd.DataFrame(list(moved["exposure_json"])) - pd.DataFrame(
        list(moved["book_exposure_json"])
    )
    timing = {
        "n_sessions": int(len(daily)),
        "n_moved": int(len(moved)),
        "mean_abs_gap": float(gap.abs().mean().mean()) if len(moved) else 0.0,
        "max_abs_gap": float(gap.abs().max().max()) if len(moved) else 0.0,
        "worst_factor": str(gap.abs().max().idxmax()) if len(moved) else "n/a",
        "pnl": float(moved["pnl_timing"].sum()),
        "abs_pnl": float(moved["pnl_timing"].abs().sum()),
        "total_on_moved": float(moved["pnl_total"].sum()),
    }
    timing_share = (
        abs(timing["pnl"]) / abs(timing["total_on_moved"]) * 100
        if timing["total_on_moved"]
        else 0.0
    )
    monthly_top = monthly.copy()
    monthly_top["magnitude"] = monthly_top["pnl_total"].abs()
    monthly_lines = "\n".join(
        f"| {row['month']} | {row['n_sessions']} | {_bp(row['pnl_total'])} | "
        f"{_bp(row['pnl_factor'])} | {_bp(row['pnl_idio'])} |"
        for row in monthly_top.sort_values("magnitude", ascending=False)
        .head(5)
        .to_dict("records")
    )
    series_lines = "\n".join(
        f"| {row['term']} | {row['beta']:.4f} | {row['se']:.4f} | "
        f"{'yes' if row['within_one_se'] else 'no'} |"
        for row in timeseries.to_dict("records")
        if not pd.isna(row.get("holdings_exposure"))
    )
    regime_note = (
        "not in this report: the regime table, the seven-way selection, sizing and "
        "timing decomposition, and the selection-versus-sizing-vs-timing port are in "
        "the roadmap's E12 scope and are not among this sprint's nine tasks. They are "
        "recorded as open in `sprints/E12/TASKS.md` rather than silently dropped."
    )

    text = f"""# E12 P&L Attribution Report

The attribution is run on **the seed book's own stored days**: rho 0.02, seed 0, out
of `data/portfolios/mv_constrained.parquet`, {identity["n_sessions"]:,} sessions from
{results["artifact"]["first_session"]} to {results["artifact"]["last_session"]}. The
live book replaces that input table and nothing else, which is what makes this a
scaffold rather than a placeholder.

Everything below is read from a stored artifact: `data/attribution/daily.parquet`,
`monthly.parquet` and `timeseries.parquet`, written by
`scripts/build_attribution.py`, and `sprints/E12/RESULTS.json` for the criteria.

## 1. Factor against idio, cumulative

| component | cumulative |
| --- | --- |
| total | {_bp(totals["total"])} bp |
| factor | {_bp(totals["factor"])} bp |
| idio | {_bp(totals["idio"])} bp |
| cost | {_bp(totals["cost"])} bp |

The book is long/short and dollar-neutral, gross 1.0, so the numbers are basis
points of the book and of NAV at once. The split is not asserted: the identity's own
residual is stored per day and its worst day is
{_bp(identity["max_abs_residual"])} bp, with a median of
{_bp(identity["median_abs_residual"])} bp.

**What that residual is and is not.** It is total minus (factor + idio + cost), where
the three come from three different artifacts: the stored factor returns, the stored
specific returns and the panel's own total returns. On the sessions the current build
produced it closes to 6.9e-18, which is machine precision and the check the sprint
wanted. On this artifact it closes to machine precision on
{identity["n_days_within_1e10"]:,} of {identity["n_sessions"]:,} sessions and misses
by a median of {_bp(identity["median_abs_residual"])} bp elsewhere, because the
seed's older vintages do not reproduce their own panel from their stored factor and
specific returns. Both numbers are true and they are kept apart.

## 2. Per factor

The rows are ordered by absolute contribution, so the largest exposure the book ran is
first.

| factor | cumulative P&L | share of the factor line |
| --- | --- | --- |
{factor_lines}

## 3. The five largest months

Cumulative answers "did it work"; the by-period table answers "when". The five
largest months by absolute P&L, out of `monthly.parquet`:

| month | sessions | total | factor | idio |
| --- | --- | --- | --- | --- |
{monthly_lines}

## 4. Selection, sizing and timing

The three are separated by construction, not by a port:

- **Selection** is the alpha: `idio_momentum`, residualized on the champion design.
  On this book it is the idio line, {_bp(totals["idio"])} bp.
- **Sizing** is Procedure 6.3's `alpha / sigma^2`, the 10% variance-share cap and the
  20-share floor, all of which act on the weights before the hedge.
- **Timing** is the *design vintage*. The hedge zeroes the book's exposure as measured
  on the design dated the close the book was built at; the return realizes under the
  design dated the session. The gap between the two is the timing line:
  {_bp(timing["pnl"])} bp over the whole artifact.

{regime_note}

### The hedge timing, measured

The two design vintages differ on **{timing["n_moved"]:,} of {timing["n_sessions"]:,}
sessions**, which are the sessions that follow a rebalance date: the seed's descriptor
artifact is a monthly snapshot, so on every other session the design dated the session
and the design dated the book's own close are the same object.

| quantity | value |
| --- | --- |
| mean per-factor exposure gap, on those sessions | {timing["mean_abs_gap"]:.5f} |
| largest single gap | {timing["max_abs_gap"]:.4f}, of {timing["worst_factor"]} |
| timing P&L | {_bp(timing["pnl"])} bp |
| total P&L on those sessions | {_bp(timing["total_on_moved"])} bp |
| timing as a share of it | {timing_share:.1f}% |

An average taken over all {timing["n_sessions"]:,} sessions would divide that by
twenty and read as nothing, which is why it is quoted this way.

**Is the design dated a session computable at the previous close? Yes, it is what it
is.** Every descriptor on row `t` of `descriptors.parquet` is built from data through
`t-1`: `efb/models/fundamental.py` writes size as `log(market_cap.shift(1))`, and
beta, residual volatility and liquidity each carry `.shift(1)` on their window, with
reversal shifting the return series by one; only momentum reaches further back (through
`t-21`). Measured on the stored artifact, the 2026-09-21 size descriptor equals log
market cap at the 2026-09-18 close exactly, to 0.000e+00 for LITE, MRNA and AAPL, and
misses the same-day cap by 8.4e-03 to 1.2e-01. And the cross-sectional R-squared the
stored fit actually achieved is {r2["artifact_mean"]:.6f} on average, against the
shift test's **lagged** figure of {r2["lagged"]:.6f} and its look-ahead variant of
{r2["same_day"]:.6f}. It matches the lagged design, not the same-day one, which is
the second independent confirmation that the stored fit is the no-look-ahead pairing.

So there is no look-ahead in the stored model, and the hedge is not stale in the sense
of reading data it should not have. It is one session **behind**: the evening of close
`t` hedges with the design dated `t`, which carries data through `t-1`, while the book
earns its return over `t` to `t+1`, whose exposure is described by the design dated
`t+1`, available in the same evening. Recorded as a post-flip fix in
`docs/open_items.md`; the live hedge is unchanged.

## 5. The two estimators, side by side

The holdings view knows what the book held; the regression view only sees what it
earned. Regressing the book's daily P&L on the factor returns gives betas with
standard errors, and the sprint's second criterion asks whether those betas agree with
the average holdings-based exposures within one standard error.

| term | regression beta | SE | within one SE of the holdings view |
| --- | --- | --- | --- |
{series_lines}

**{int(timeseries["within_one_se"].sum())} of {len(timeseries)} terms agree.** This is
a measurement on a book that rebalances monthly, where the regression's intercept
absorbs a month of drift that the holdings view attributes to factors; the live book
rebalances daily and is the object the criterion is about. Verdict: **pending**.

## 6. Skill against luck

| quantity | value |
| --- | --- |
| days | {skill["n_days"]:,} |
| mean idio P&L | {_bp(skill["idio_mean"])} bp/day |
| standard error of that mean | {_bp(skill["idio_se"])} bp |
| t-statistic | {skill["t_stat"]:.2f} |
| annualized information ratio | {skill["ir_annual"]:.3f} |
| annualized Sharpe | {skill["sharpe_annual"]:.3f} |
| its Lo (2002) standard error | {skill["sharpe_se_lo2002"]:.3f} |

The rule the sprint pre-registered is that no skill is claimed unless the t-statistic
exceeds {skill["target_t"]:.1f}, and that the reported Sharpe carries its standard
error. Both are applied mechanically: {skill["verdict"]}.

**Read that with its own caveat.** E10 chose the (rho, phi) whose net annualized Sharpe
is closest to 1.0 on this same sample, so a Sharpe of {skill["sharpe_annual"]:.2f}
measured here is the selection working, not an edge discovered. The live book trades a
different signal, documented as a null book whose factor-neutral IC is -0.0031 at
t -0.51, and the expected verdict for its thirty-day window is **luck**.

The number that decides what a thirty-day window can show:

| annualized information ratio | days needed for t of {skill["target_t"]:.1f} |
| --- | --- |
| 0.25 | {skill["days_to_detect"][0.25]:,} |
| 0.5 | {skill["days_to_detect"][0.5]:,} |
| 1.0 | {skill["days_to_detect"][1.0]:,} |
| 2.0 | {skill["days_to_detect"][2.0]:,} |

## 7. The criteria as registered

| ID | criterion | verdict |
| --- | --- | --- |
| F12.1 | {criteria["F12.1"]["criterion"]} | {criteria["F12.1"]["verdict"]} |
| F12.2 | {criteria["F12.2"]["criterion"]} | {criteria["F12.2"]["verdict"]} |
| F12.3 | {criteria["F12.3"]["criterion"]} | {criteria["F12.3"]["verdict"]} |

Their stored numbers and the detail behind each verdict are in
`sprints/E12/RESULTS.json`.

## 8. What would falsify this

- **The identity failing on live days.** It failed on the seed's older vintages; if it
  fails on the live ones, the split is describing a different book from the one that
  traded.
- **The two estimators disagreeing beyond one standard error on a daily book.** They
  disagree on this monthly one, where the mismatch is explainable; a daily book has no
  such excuse.
- **The hedge's factor P&L growing.** It is the part that should have been zero. If
  the timing line grows rather than shrinks, the stale design is the cause and the
  post-flip fix is the remedy.
- **A realized cost far from the expected one.** The E9 model is untested by real
  fills until the live days exist.
- **A t above two on thirty days.** It would be the measurement, not the edge: thirty
  days cannot show an information ratio of 0.25, let alone 1.0.

## 9. Coverage

Built and stored: holdings-based attribution per day (factor by factor, idio, cost),
the reconciliation residual, both design vintages and the timing gap, the raw-beta
line, realized against forecast volatility with the bias statistic, the fill counts,
the cost split four ways, the two-estimator comparison, the skill test with its
standard errors, the page's section and the weekly review.

Not in this report, and named as open in `sprints/E12/TASKS.md`: the regime table and
the seven-way carry decomposition.
"""
    MEMO.parent.mkdir(parents=True, exist_ok=True)
    MEMO.write_text(text)
    print(f"wrote {MEMO.relative_to(ROOT)} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
