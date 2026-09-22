# RG-Operate

The gate before the book runs (E11). Each checklist item is answered with
stored numbers, never with reasoning standing in for a measurement. The
answer to each is positive unless stated.

## 1. Has a champion risk model passed E5 with a stated stress haircut?

Yes, with the haircut stored. The champion is XS-v1. E5 failed F5.1 (no
version is inside 0.9 to 1.1 on every family), so the champion is
provisional, and the stored stress haircut is 1.8471: the fraction the
model underforecast in its worst named episode (2020 Q1 and 2022), so a
stress forecast multiplies the model by 1 + 1.8471. Source:
data/eval/e5_stress_haircut.parquet.

## 2. Is the hedge policy from E6 written down with its cost?

Yes. The hedge is the exact in-model FMP hedge, never the capped FMPs. The
exact hedge drives the worst post-hedge exposure to 5.8e-15 and the idio
share after the hedge to 100.0%, at the cost of trading 461.9 names on
average per rebalance. Its mean cost is 0.1053% of notional per rebalance
for the momentum long/short book and 0.1655% for the equal-weight book.
The as-stored quarterly capped FMPs are not a hedge: their worst residual
exposure is 0.7552, worse than unhedged. Source:
data/hedge/hedge_metrics.parquet.

## 3. Has G3 passed: does the construction stack run end to end under the
champion model with the constraint set from E8?

Yes. The stack runs alpha to hedged, sized book on synthetic alpha with a
known IC. F8.2 passes (the proportional book's idio share after the FMP
hedge is 1.0000). F8.3 passes (the constrained optimizer's worst violation
is 3.95e-09 with zero solver fallbacks). F8.1b passes (with alpha
GLS-neutralized in the D^-1 metric, unconstrained mean-variance, the
proportional rule and Procedure 6.3 are the same vector to 6.4e-17). The
champion construction is the proportional rule hedged with the exact FMPs.

## 4. Are the cost-model parameters stated with their uncertainty (E9),
and is the risk budget written per regime (E10)?

The cost parameters are stated with their uncertainty:

- Spread: a size-decile schedule from 10 bp half-spread (smallest names)
  to 1 bp (largest), stated as an assumption with a half and double
  sensitivity, because free daily OHLC data cannot measure spreads for
  S&P 500 names (F9.3 is recorded not evaluable).
- Impact: k * sigma * sqrt(dollar trade / ADV) with k = 0.5, stated with
  uncertainty [0.25, 1.0].
- Commission: 1 bp per dollar traded, one side.
- Borrow: 2% per year on short notional.

The risk budget is written per VIX regime, not as one number:

| VIX tercile | mean VIX | max drawdown | periods underwater |
| --- | --- | --- | --- |
| 0 | 12.81 | -0.0967 | 48 |
| 1 | 16.44 | -0.1309 | 38 |
| 2 | 24.31 | -0.0636 | 28 |

Source: data/allocation/regime.parquet. The middle VIX tercile carries the
deepest drawdown; the high-VIX tercile's drawdown is shallower because the
design book's persistent alpha re-sizes away from the risk.

## 5. Added: an ongoing constituent source

Negative, and it blocks E11. The universe is frozen at the pinned Wikipedia
revision 1368675864 (2026-08-05); a paper-traded book cannot run on a
frozen universe. E11 must secure an ongoing constituent source (a vendor
feed or a maintained open source) and re-run the universe reconstruction
before the book goes live. Tracked in docs/open_items.md.

## 6. Added: what E11 would trade given RG-Signal returned all NULL

A documented-null book on the best-behaved signal, labeled as such.
RG-Signal returned all six signals NULL. The best-behaved is momentum_12_1:
its horizon-1 IC survives both the forward shift (0.0151 to 0.0149) and the
extra-day lag (0.0151 to 0.0152), so its edge is persistent rather than
leaked, which is what a paper-trading instrument needs. The book runs on
synthetic alpha with a known IC as the controlled construction input, and
the expected E12 verdict is luck, written down before E11 starts.

## Verdict

RG-Operate is not cleared: item 5 (the ongoing constituent source) is
negative. The missing item is finished first; the book waits. Everything
else (1, 2, 3, 4, 6) is answered with stored numbers.
