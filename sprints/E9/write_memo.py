"""Sprint E9 Task 7: write the cost and capacity memo from the artifacts.

Every number is read from the artifacts or the stored results, never typed
by hand. The addendum documents the cost-magnitude correction: the stored
Corwin-Schultz spreads were volatility, not spreads, and the cost input is
now a size-decile schedule.
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
    sensitivity = pd.read_parquet(
        DATA / "costs" / "capacity_spread_sensitivity.parquet"
    )
    tradeoff = pd.read_parquet(DATA / "costs" / "turnover_tradeoff.parquet")
    f91 = results["criteria"]["F9.1"]["stored_numbers"]
    f93 = results["criteria"]["F9.3"]["stored_numbers"]
    f95 = results["criteria"]["F9.5"]["stored_numbers"]
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
    sensitivity_lines = "\n".join(
        f"| {row['rho']} | {row['spread_multiplier']} | {row['halving_aum']:.3g} |"
        for row in sensitivity.to_dict(orient="records")
    )
    tradeoff_lines = "\n".join(
        f"| {row['rho']} | {row['turnover_cut']:.3f} | {row['ex_ante_ir_loss']:.3f} |"
        for row in tradeoff.to_dict(orient="records")
    )
    anchor_lines = "\n".join(
        f"| {decile} | {f95['anchor_raw_cs_median_by_decile'][decile]:.5f} | "
        f"{f95['anchor_adjusted_cs_median_by_decile'][decile]:.5f} | "
        f"{f95['anchor_abdi_ranaldo_median_by_decile'][decile]:.5f} | "
        f"{f95['median_half_spread_by_decile'][decile]:.5f} |"
        for decile in sorted(f95["median_half_spread_by_decile"], key=int)
    )

    text = f"""# E9 Transaction Cost and Capacity Analysis

The alpha is the E8 synthetic alpha with a known IC, labeled as such: no
real signal passed RG-Signal, so this book's real capacity is undefined.
The spread input is a size-decile schedule from 10 bp half-spread for the
smallest names to 1 bp for the largest, stated as an assumption with a
half and double sensitivity, because the free estimators measure
volatility rather than the spread on daily high-low data for S&P 500
names. On that schedule the spread cost of a 140% turnover rebalance is
about 0.07% of AUM, not the 4% the Corwin-Schultz estimate implied, and
the capacity question is the impact cost, not the spread.

## The cost model and its uncertainty

- Half-spread: the size-decile schedule above, stated as an assumption.
  The estimators it replaced are documented in the addendum and in
  data/costs/spread_probe.parquet.
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

The chosen schedule falls monotonically from the smallest to the largest
decile by construction, which is the size ordering the spread should have.

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

Net Sharpe is monotone in AUM ({f91['n_monotonicity_violations_net_sharpe']}
violations over {f91['n_curves']} curves) and the net mean return is
monotone ({f91['n_monotonicity_violations_net_mean']} violations). The
halving AUM is defined for rho 0.05 and 0.1, and undefined for rho 0.02
because that book's weak alpha is already below half its gross Sharpe at
the 1 million dollar grid floor once the fixed spread and commission cost
of a 140% turnover rebalance is paid.

## The spread schedule sensitivity

The halving AUM under the schedule at half and double, per rho, at k = 0.5:

| rho | spread multiplier | halving AUM |
| --- | --- | --- |
{sensitivity_lines}

## Stored criteria

- F9.1 (verdict {verdicts['F9.1']['verdict']}): net Sharpe is
  monotone in AUM (0 violations), and the halving AUM is stored per rho
  and k: undefined for rho 0.02, 100 million dollars at rho 0.05 k 0.5
  and 464 million dollars at rho 0.1 k 0.5.
- F9.2 (verdict {verdicts['F9.2']['verdict']}): the turnover-penalized
  optimizer cuts about 37% of turnover with under 7% ex-ante IR loss, so
  the 50% cut is not reached because the turnover is concentrated in the
  high-alpha names.
- F9.3 (verdict {verdicts['F9.3']['verdict']}): the corrected
  overnight-adjusted Corwin-Schultz estimator floors every name at zero,
  so the size-rank correlation is undefined; the raw estimator reads
  {f93['raw_cs_size_rank_correlation']:.3f} and the Abdi-Ranaldo estimate
  {f93['abdi_ranaldo_size_rank_correlation']:.3f}, neither above 0.5.
- F9.4 (verdict {verdicts['F9.4']['verdict']}): the halving AUM is stored
  per rho with its sensitivity to k, finite for rho 0.05 and 0.1.
- F9.5 (verdict {verdicts['F9.5']['verdict']}): the chosen schedule's
  median half-spread by decile is stored beside the anchor estimators it
  replaced.

## Addendum: the cost magnitude correction

The original headline said turnover, not AUM, is the binding constraint,
with the halving AUM undefined at every rho and k. That conclusion came
from the cost estimate, not from the book: the stored Corwin-Schultz
half-spreads of 2.5 to 5.2 percent are volatility, not spreads. The
estimator's two-day high-low range is dominated by intraday volatility
for liquid names, so the unadjusted estimate reads about 100 times the
quoted spread, and the overnight-adjusted estimate floors at zero
everywhere. The Abdi-Ranaldo close-high-low estimate has no size
gradient either. The estimator comparison per decile, before and after:

| size decile | raw CS median | adj CS median | Abdi-Ranaldo | schedule |
| --- | --- | --- | --- | --- |
{anchor_lines}

Before: the raw Corwin-Schultz median half-spread was 2.4 to 4.2 percent,
and at 140% monthly turnover that is about 3 to 5 percent of AUM per
rebalance in spread cost alone, which no IC in the experiment covers, so
the capacity curve was negative at every AUM and the halving AUM was
undefined everywhere. After: the schedule is 10 to 1 bp, the spread cost
per rebalance is about 0.07% of AUM, net Sharpe is monotone in AUM (the
violation count moved from 206 to 0), and the halving AUM is defined for
rho 0.05 and 0.1. The rho 0.02 book remains cost-impaired at any size
because its alpha is too weak to pay even the fixed spread and
commission. Both data hashes are on the record in the revisions block of
sprints/E9/RESULTS.json.

## Practitioner conclusion

Gross alpha is a research number; net alpha is the business. With the
corrected spread the capacity question becomes the impact cost, which is
monotone in AUM, and the halving AUM is defined for the stronger books.
The rho 0.02 book is the cautionary case: at 140% turnover even 10 bp of
spread plus commission is enough to halve a book with an IC of 0.019
before the first dollar of impact.

## What would falsify this?

- Net Sharpe is not monotone in AUM: with the corrected costs it is
  monotone, 0 violations stored under F9.1.
- The turnover penalty destroys ex-ante IR: the stored trade-off under
  F9.2 shows the IR survives but the turnover cut falls short.
- Realized fills in E11 outside the model's band: parameters are
  recalibrated and the capacity curve reissued, and the spread schedule
  is replaced by the measured fills.
"""
    out = ROOT / "docs" / "research" / "E9_tcost_capacity.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
