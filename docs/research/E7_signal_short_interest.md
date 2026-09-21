# E7 Signal Report: short_interest

Verdict against the RG-Signal checklist: **NULL**. The number that
decided it: neutral out-of-sample t 2.103,
out-of-sample spread Sharpe 0.855, break-even
cost 21.02 bp per rebalance
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
| ic_h1 | 0.002677 |
| ic_h5 | 0.005749 |
| ic_h21 | 0.010431 |
| ic_h63 | 0.013702 |

## Factor-neutral IC

The signal is residualized on the champion design at each rebalance date,
s_perp = s - X (X'X)^-1 X' s. Mean neutral IC 0.008518,
out-of-sample mean 0.015815 with t
2.103.

## Regime IC

| regime | mean IC | n days |
| --- | --- | --- |
| pooled | 0.002677 | 1930 |
| vix_low | 0.005541 | 644 |
| vix_mid | 0.003775 | 646 |
| vix_high | -0.001312 | 640 |

## Quantile spread

Hit rate 0.3670, turnover share per rebalance
0.1471, out-of-sample spread Sharpe
0.855.

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
