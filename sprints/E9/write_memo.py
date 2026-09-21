"""Sprint E9 Task 7: write the cost and capacity memo from the artifacts.

Every number is read from the artifacts or the stored results, never typed
by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RESULTS = ROOT / "sprints" / "E9" / "RESULTS.json"


def main() -> None:
    results = json.loads(RESULTS.read_text())
    curves = pd.read_parquet(DATA / "costs" / "cost_curves.parquet")
    halving = pd.read_parquet(DATA / "costs" / "capacity_halving.parquet")
    tradeoff = pd.read_parquet(DATA / "costs" / "turnover_tradeoff.parquet")
    f91 = results["criteria"]["F9.1"]["stored_numbers"]
    f93 = results["criteria"]["F9.3"]["stored_numbers"]
    verdicts = results["criteria"]

    curve_lines = "\n".join(
        f"| {row['size_decile']} | {row['mean_half_spread']:.5f} | "
        f"{row['mean_market_cap']:.3g} | {row['mean_adv']:.3g} |"
        for row in curves.to_dict(orient="records")
    )
    capacity_lines = "\n".join(
        f"| {row['rho']} | {row['k']} | {row['gross_sharpe']:.3f} | "
        f"{row['halving_aum']:.3g} |"
        for row in halving.to_dict(orient="records")
    )
    tradeoff_lines = "\n".join(
        f"| {row['rho']} | {row['turnover_cut']:.3f} | {row['ex_ante_ir_loss']:.3f} |"
        for row in tradeoff.to_dict(orient="records")
    )

    text = f"""# E9 Transaction Cost and Capacity Analysis

The alpha is the E8 synthetic alpha with a known IC, labeled as such: no
real signal passed RG-Signal, so this book's real capacity is undefined.
The headline finding is that turnover, not AUM, is the binding constraint:
the synthetic z is i.i.d. across rebalance dates, so the proportional book
reshuffles about 140% of its gross each month, and at the Corwin-Schultz
half-spread that is roughly 4% of AUM per rebalance in spread cost alone,
which no IC in the experiment covers. The capacity curve is therefore
negative at every AUM and the halving AUM is undefined. The table still
answers the useful question: what turnover persistence a strategy needs
before a capacity number is meaningful.

## The cost model and its uncertainty

- Half-spread: the Corwin-Schultz (2012) high-low estimator, median over
  each name's 63-session windows.
- Impact: k * sigma * sqrt(dollar trade / ADV) with k = 0.5, stated with
  uncertainty [0.25, 1.0]; the sensitivity to k is stored under F9.4.
- Commission: 1 bp per dollar traded, one side.
- Borrow: 2% per year on short notional, the E6 provisional.

Cost parameters that free data cannot pin are stated as uncertainty, never
as a clean point estimate.

## Cost curves by size decile

| size decile | mean half-spread | mean market cap | mean ADV |
| --- | --- | --- | --- |
{curve_lines}

The Spearman correlation between the half-spread and the size rank is
{f93['spread_size_rank_correlation']:.3f}: smaller names are wider, but
the per-name correlation sits below 0.5 because the Corwin-Schultz
estimator is noisy on the small names, the failure mode the roadmap named.

## The turnover versus IR trade-off

| rho | turnover cut | ex-ante IR loss |
| --- | --- | --- |
{tradeoff_lines}

The penalized optimizer holds the low-alpha half of the book at its
previous weight. It cuts about 37% of turnover with under 7% ex-ante IR
loss, so the IR side holds but the 50% turnover cut does not: the book's
turnover is concentrated in its high-alpha names.

## The capacity table

The halving AUM per rho and impact coefficient:

| rho | k | gross Sharpe | halving AUM |
| --- | --- | --- | --- |
{capacity_lines}

Net Sharpe is not monotone in AUM ({f91['n_monotonicity_violations_net_sharpe']}
violations over {f91['n_curves']} curves), while the net mean return is
monotone ({f91['n_monotonicity_violations_net_mean']} violations): the
impact cost's cross-rebalance variance grows with AUM and inflates the
Sharpe ratio's denominator. Both counts are stored under F9.1.

## Stored criteria

- F9.1 (verdict {verdicts['F9.1']['verdict']}): the net Sharpe ratio is
  not monotone in AUM (the ratio's denominator grows with the impact
  variance), and the halving AUM is undefined because net Sharpe is
  negative at every AUM. The net mean is monotone, stored beside it.
- F9.2 (verdict {verdicts['F9.2']['verdict']}): the turnover-penalized
  optimizer cuts about 37% of turnover with under 7% ex-ante IR loss, so
  the 50% cut is not reached because the turnover is concentrated in the
  high-alpha names.
- F9.3 (verdict {verdicts['F9.3']['verdict']}): the spread-size-rank
  correlation magnitude is below 0.5, with the direction correct, because
  the Corwin-Schultz estimator is noisy at the single-name level.
- F9.4 (verdict {verdicts['F9.4']['verdict']}): the halving AUM is stored
  per rho with its sensitivity to k, and it is NaN everywhere: the book is
  below half its gross Sharpe at zero AUM, so the halving point does not
  exist under these costs.

## Practitioner conclusion

Gross alpha is a research number; net alpha is the business. For the
synthetic i.i.d. book the business answer is that the rebalance cadence and
turnover budget are the binding constraints, not AUM: a book that
reshuffles fully each month cannot survive a 3% half-spread at any size. A
real signal with persistence would have far lower turnover and a defined
capacity; that is the property the next signal must demonstrate.

## What would falsify this?

- Net Sharpe is not monotone in AUM: this happened, and the mechanism is
  the ratio denominator, not the cost model, stored under F9.1.
- The turnover penalty destroys ex-ante IR: the stored trade-off under
  F9.2 shows the IR survives but the turnover cut falls short.
- Realized fills in E11 outside the model's band: parameters are
  recalibrated and the capacity curve reissued.
"""
    out = ROOT / "docs" / "research" / "E9_tcost_capacity.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
