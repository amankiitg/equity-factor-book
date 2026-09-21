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
real signal passed RG-Signal, so this book's real capacity is undefined and
the capacity table answers the useful question instead, what IC a strategy
needs to support a given AUM under these costs.

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
{f93['spread_size_rank_correlation']:.3f}: smaller names are wider.

## The turnover versus IR trade-off

| rho | turnover cut | ex-ante IR loss |
| --- | --- | --- |
{tradeoff_lines}

## The capacity table

The halving AUM per rho and impact coefficient:

| rho | k | gross Sharpe | halving AUM |
| --- | --- | --- | --- |
{capacity_lines}

Net Sharpe is monotone in AUM ({f91['n_monotonicity_violations']} violations
over {f91['n_curves']} curves).

## Stored criteria

- F9.1 (verdict {verdicts['F9.1']['verdict']}): net Sharpe declines
  monotonically with AUM and the halving AUM is stored.
- F9.2 (verdict {verdicts['F9.2']['verdict']}): the turnover-penalized
  optimizer cuts turnover by more than 50% with less than 20% ex-ante IR
  loss, holding the low-alpha half of the book at its previous weight.
- F9.3 (verdict {verdicts['F9.3']['verdict']}): the spread-size-rank
  correlation is above 0.5.
- F9.4 (verdict {verdicts['F9.4']['verdict']}): the halving AUM is stored
  per rho with its sensitivity to k; doubling k roughly quarters the
  halving AUM under the square-root law.

## Practitioner conclusion

Gross alpha is a research number; net alpha is the business. At a realistic
IC the book's capacity is the AUM at which net Sharpe halves, and the
table in rho is the honest answer while no real signal has passed
RG-Signal. The rebalance cadence and the turnover budget follow from the
trade-off table.

## What would falsify this?

- Net Sharpe is not monotone in AUM: the cost model is mis-specified. The
  stored curves are checked for this under F9.1.
- The turnover penalty destroys ex-ante IR: the signal horizon is wrong for
  the cost regime. The stored trade-off is checked under F9.2.
- Realized fills in E11 outside the model's band: parameters are
  recalibrated and the capacity curve reissued.
"""
    out = ROOT / "docs" / "research" / "E9_tcost_capacity.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
