# Sprint E10 PRD: Dynamic Risk Allocation and Loss Management

Sprint E10, 2026-09-21. Tier 3. Gate: RG-Operate. The sprint that
answers the PM question "how much can I lose before the model is wrong
rather than unlucky, and what does the book do at that point?"

## Research framing, copied verbatim from the roadmap

- Academic question: How much risk should a strategy with an estimated Sharpe ratio run, and under what return properties does a stop-loss add value?
- Practitioner question: How much can I lose before the model is wrong rather than unlucky, and what does the book do at that point?
- Research question: Does volatility targeting or a stop-loss improve the seed book's risk-adjusted outcome relative to i.i.d. controls, and how do drawdowns depend on the volatility regime?

Objective. Decide how much risk the book runs over time: Kelly and
fractional Kelly under an estimated Sharpe, volatility targeting, drawdown
control, and the APM stop-loss efficiency analysis tested on the book.

## Input

The synthetic book's net returns on corrected costs. Synthetic Sharpes up
to 5 would make Kelly meaningless, so the engine picks the (rho, phi)
configuration whose net annualized Sharpe is closest to 1.0, states it,
and treats SR as a design parameter. The two seed books (equal-weight and
momentum long/short) run alongside as the real-book sensitivity.

## Formulas, inputs and outputs labeled

- Kelly fraction: f* = mu / sigma^2; growth g(f) = f mu - f^2 sigma^2 / 2.
  INPUT: mean and variance of the per-rebalance return. OUTPUT: full Kelly
  leverage and the growth curve.
- Fractional Kelly: f = c f*, with c set from the standard error of the
  Sharpe estimate. INPUT: SR, SE(SR). OUTPUT: the fractional leverage and
  the cost of over-betting when SR is overstated by one standard error.
- Vol targeting: scale_t = sigma_target / sigma_hat_t, with the realized
  annual volatility dispersion measured across years (F10.3).
- Drawdown approximation: the Magdon-Ismail et al. closed form for the
  expected maximum drawdown as a function of SR and horizon, compared to
  the simulated distribution at the median (F10.1).
- Stop-loss rule and its efficiency: Sharpe with and without the rule on
  bootstrapped i.i.d. returns (the control) and on the real book (F10.2).
- Regime: drawdown depth and recovery within VIX terciles.

## Inherited constraints, all hard

1. F10.1 to F10.3 are copied verbatim from docs/roadmap_v2.md; a stored
   criterion is never reworded.
2. No number in any walkthrough or deliverable is typed by hand.
3. The synthetic input is a controlled experiment, never a backtest; the
   label travels with every number.
4. Evidence covers the fetched inputs; the E10 artifacts are regenerated
   by make rebuild.

## Pre-registered falsification criteria

| ID | criterion | threshold |
| --- | --- | --- |
| F10.1 | Simulated drawdown distribution matches the analytical approximation within 10% at the median for the seed book's SR. | simulated median drawdown within 10% of the analytical value |
| F10.2 | Control: on i.i.d. bootstrapped returns the stop-loss does not improve Sharpe. On the real book the result is reported either way. | stop-loss does not improve Sharpe on the i.i.d. control |
| F10.3 | Vol targeting reduces the dispersion of realized annual vol across years by more than 40%. | dispersion reduction above 40% |

## Deliverables and dashboard increment

- efb/allocate.py
- data/allocation/{kelly,voltarget,stoploss}.parquet
- docs/research/E10_risk_policy.md with a traceability test
- sprints/E10/RESULTS.json with F10.1 to F10.3
- Dashboard tab D9 Risk Allocation
- notebooks/E10_walkthrough.ipynb, rendered and published
- make rebuild-e10, make rebuild extended to E1 through E10

## The memo

Risk Allocation and Drawdown Policy, written for a senior quant or risk
manager: the Kelly analysis with the chosen fraction and the reasoning
from the SE of SR, the drawdown distribution table and the regime table,
the stop-loss verdict and the volatility-targeting rule the book will
run, and a section titled "What would falsify this?". A negative verdict
is a complete deliverable.

## Gate RG-Operate

Answered at the end of this sprint with stored numbers: the champion risk
model with its stress haircut, the hedge policy with its cost, G3, the
cost-model parameters with their uncertainty, and the risk budget per
regime. Two items the roadmap did not have are added: the ongoing
constituent source, and what E11 would trade given RG-Signal returned all
NULL. A negative answer sends the missing item back before E11 runs.
