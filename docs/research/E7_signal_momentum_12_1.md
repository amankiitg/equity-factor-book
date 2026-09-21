# E7 Signal Report: momentum_12_1

Verdict against the RG-Signal checklist: **NULL**. The number that
decided it: neutral out-of-sample t -1.639,
out-of-sample spread Sharpe 0.271, break-even
cost 5.71 bp per rebalance
against a realistic 5 bp.

## Hypothesis and economic rationale

Underreaction: winners of the past year, skipping the last month, keep drifting as information is incorporated slowly.

## Construction

Point-in-time by construction: the signal at t uses data through t-1 or
earlier, which is exactly what the shift audit verifies. Missing values stay
NaN, never filled.

## IC and decay

| horizon | mean IC |
| --- | --- |
| ic_h1 | 0.015076 |
| ic_h5 | 0.015680 |
| ic_h21 | 0.010644 |
| ic_h63 | 0.008241 |

## Factor-neutral IC

The signal is residualized on the champion design at each rebalance date,
s_perp = s - X (X'X)^-1 X' s. Mean neutral IC -0.010684,
out-of-sample mean -0.018138 with t
-1.639.

## Regime IC

| regime | mean IC | n days |
| --- | --- | --- |
| pooled | 0.015076 | 3941 |
| vix_low | 0.014945 | 1317 |
| vix_mid | 0.018176 | 1310 |
| vix_high | 0.012118 | 1314 |

## Quantile spread

Hit rate 0.5320, turnover share per rebalance
0.3897, out-of-sample spread Sharpe
0.271.

## RG-Signal answers

Q1. Answer: yes
Q2. Answer: yes with the survivor-only universe caveat
Q3. Answer: False
Q4. Answer: False
Q5. Answer: True
Q6. Answer: partially: equal-weight quintiles only; the decay range is stored
Q7. Answer: yes, on paper

## Champion against alternative

The raw IC is shared by both models; the stored difference is in the converted alpha under the champion's idio volatility and the alternative's, which is the quantity the models actually move.
