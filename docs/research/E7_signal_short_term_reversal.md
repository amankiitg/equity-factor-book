# E7 Signal Report: short_term_reversal

Verdict against the RG-Signal checklist: **NULL**. The number that
decided it: neutral out-of-sample t -0.408,
out-of-sample spread Sharpe -0.461, break-even
cost -3.80 bp per rebalance
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
| ic_h1 | 0.011923 |
| ic_h5 | 0.015978 |
| ic_h21 | 0.011229 |
| ic_h63 | 0.010595 |

## Factor-neutral IC

The signal is residualized on the champion design at each rebalance date,
s_perp = s - X (X'X)^-1 X' s. Mean neutral IC 0.001806,
out-of-sample mean -0.003253 with t
-0.408.

## Regime IC

| regime | mean IC | n days |
| --- | --- | --- |
| pooled | 0.011923 | 4207 |
| vix_low | 0.013246 | 1322 |
| vix_mid | 0.010881 | 1322 |
| vix_high | 0.010998 | 1314 |

## Quantile spread

Hit rate 0.4478, turnover share per rebalance
0.7851, out-of-sample spread Sharpe
-0.461.

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
