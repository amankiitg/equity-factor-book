# E7 Signal Report: short_term_reversal

Verdict against the RG-Signal checklist: **NULL**. The number that
decided it: neutral out-of-sample t -0.312,
out-of-sample spread Sharpe -0.485, break-even
cost -3.97 bp per rebalance
against a realistic 5 bp.

## Hypothesis and economic rationale

Liquidity provision: a week of selling overshoots and reverts as market makers are compensated.

## Construction

Point-in-time by construction: the signal at t uses data through t-1 or
earlier, which is exactly what the shift audit verifies. Missing values stay
NaN, never filled.

## IC and decay

| horizon | mean IC |
| --- | --- |
| ic_h1 | 0.012031 |
| ic_h5 | 0.016125 |
| ic_h21 | 0.011110 |
| ic_h63 | 0.009637 |

## Factor-neutral IC

The signal is residualized on the champion design at each rebalance date,
s_perp = s - X (X'X)^-1 X' s. Mean neutral IC 0.002796,
out-of-sample mean -0.002581 with t
-0.312.

## Regime IC

| regime | mean IC | n days |
| --- | --- | --- |
| pooled | 0.012031 | 4187 |
| vix_low | 0.013611 | 1321 |
| vix_mid | 0.010819 | 1318 |
| vix_high | 0.011093 | 1314 |

## Quantile spread

Hit rate 0.4505, turnover share per rebalance
0.7852, out-of-sample spread Sharpe
-0.485.

## RG-Signal answers

Q1. Answer: yes
Q2. Answer: yes with the survivor-only universe caveat
Q3. Answer: False
Q4. Answer: False
Q5. Answer: False
Q6. Answer: partially: equal-weight quintiles only; the decay range is stored
Q7. Answer: yes, on paper

## Champion against alternative

The raw IC is shared by both models; the stored difference is in the converted alpha under the champion's idio volatility and the alternative's, which is the quantity the models actually move.
