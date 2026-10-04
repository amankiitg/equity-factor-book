# E7 Signal Report: short_interest

Verdict against the RG-Signal checklist: **NULL**. The number that
decided it: neutral out-of-sample t 2.290,
out-of-sample spread Sharpe 0.971, break-even
cost 24.70 bp per rebalance
against a realistic 5 bp.

## Hypothesis and economic rationale

High short interest marks stocks where informed pessimism is crowded and the borrow is expensive; the classic signal is short interest as a negative predictor.

## Construction

Point-in-time by construction: the signal at t uses data through t-1 or
earlier, which is exactly what the shift audit verifies. Missing values stay
NaN, never filled.

## IC and decay

| horizon | mean IC |
| --- | --- |
| ic_h1 | 0.003485 |
| ic_h5 | 0.006925 |
| ic_h21 | 0.012439 |
| ic_h63 | 0.015711 |

## Factor-neutral IC

The signal is residualized on the champion design at each rebalance date,
s_perp = s - X (X'X)^-1 X' s. Mean neutral IC 0.009448,
out-of-sample mean 0.017023 with t
2.290.

## Regime IC

| regime | mean IC | n days |
| --- | --- | --- |
| pooled | 0.003485 | 1950 |
| vix_low | 0.005648 | 646 |
| vix_mid | 0.004243 | 644 |
| vix_high | -0.000628 | 645 |

## Quantile spread

Hit rate 0.3730, turnover share per rebalance
0.1457, out-of-sample spread Sharpe
0.971.

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
