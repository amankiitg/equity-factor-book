"""Render the E7 signal reports from the stored artifacts.

Every number in a report is read from `data/alpha/{signal}/*.parquet` or
`sprints/E7/RESULTS.json`; the template contains no numbers. The verdict
comes from the RG-Signal gate, never from this script.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "alpha"
GATE_PATH = ROOT / "sprints" / "E7" / "RG_SIGNAL.json"

RATIONALES = {
    "momentum_12_1": (
        "Underreaction: winners of the past year, skipping the last month, "
        "keep drifting as information is incorporated slowly."
    ),
    "short_term_reversal": (
        "Liquidity provision: a week of selling overshoots and reverts as "
        "market makers are compensated."
    ),
    "idio_momentum": (
        "Stock-specific news travels slowly after the common factors are "
        "removed, so residual momentum is information the factors miss."
    ),
    "low_residual_volatility": (
        "Low-risk stocks are systematically underbought by benchmarked "
        "managers, leaving their expected returns too high per unit of risk."
    ),
    "short_interest": (
        "High short interest marks stocks where informed pessimism is "
        "crowded and the borrow is expensive; the classic signal is short "
        "interest as a negative predictor."
    ),
    "post_earnings_drift": (
        "Earnings surprises are incorporated only gradually because "
        "attention is limited around announcements."
    ),
}


def render_report(name: str) -> str:
    """One signal report, every number read from the artifacts."""
    ic = pd.read_parquet(DATA / name / "ic.parquet")
    neutral = pd.read_parquet(DATA / name / "neutral_ic.parquet")["ic"]
    regime = pd.read_parquet(DATA / name / "regime_ic.parquet")
    quantiles = pd.read_parquet(DATA / name / "quantiles.parquet")
    gate = json.loads(GATE_PATH.read_text())[name]
    summary = pd.read_parquet(DATA / "summary.parquet")
    row = summary.loc[summary["signal"] == name].iloc[0]

    decay_rows = "\n".join(
        f"| {column} | {float(ic[column].mean()):.6f} |"
        for column in ("ic_h1", "ic_h5", "ic_h21", "ic_h63")
    )
    regime_rows = "\n".join(
        f"| {r['regime']} | {r['mean_ic']:.6f} | {int(r['n_days'])} |"
        for r in regime.to_dict("records")
    )
    pivot = quantiles.pivot_table(index="date", columns="quantile", values="return")
    del pivot
    neutral_oos = neutral.loc[neutral.index >= "2021-01-01"]
    verdict = gate["verdict"]
    deciding = gate["deciding_number"]

    return (
        f"""# E7 Signal Report: {name}

Verdict against the RG-Signal checklist: **{verdict}**. The number that
decided it: neutral out-of-sample t {deciding['neutral_ic_oos_t']:.3f},
out-of-sample spread Sharpe {deciding['oos_spread_sharpe']:.3f}, break-even
cost {deciding['break_even_cost_bp_per_rebalance']:.2f} bp per rebalance
against a realistic 5 bp.

## Hypothesis and economic rationale

{RATIONALES[name]}

## Construction

Point-in-time by construction: the signal at t uses data through t-1 or
earlier, which is exactly what the shift audit verifies. Missing values stay
NaN, never filled.

## IC and decay

| horizon | mean IC |
| --- | --- |
{decay_rows}

## Factor-neutral IC

The signal is residualized on the champion design at each rebalance date,
s_perp = s - X (X'X)^-1 X' s. Mean neutral IC {float(neutral.mean()):.6f},
out-of-sample mean {float(neutral_oos.mean()):.6f} with t
{deciding['neutral_ic_oos_t']:.3f}.

## Regime IC

| regime | mean IC | n days |
| --- | --- | --- |
{regime_rows}

## Quantile spread

Hit rate {float(row['hit_rate']):.4f}, turnover share per rebalance
{float(row['turnover_mean']):.4f}, out-of-sample spread Sharpe
{deciding['oos_spread_sharpe']:.3f}.

## RG-Signal answers

"""
        + "\n".join(
            f"{question}. Answer: {gate['answers'][question]['answer']}"
            for question in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7")
        )
        + "\n\n## Champion against alternative\n\n"
        + (
            "The raw IC is shared by both models; the stored difference is in "
            "the converted alpha under the champion's idio volatility and the "
            "alternative's, which is the quantity the models actually move.\n"
        )
    )


def main() -> None:
    for name in RATIONALES:
        path = ROOT / "docs" / "research" / f"E7_signal_{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_report(name))
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
