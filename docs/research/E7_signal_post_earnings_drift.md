# E7 Signal Report: post_earnings_drift

Verdict against the RG-Signal checklist: **NULL**. The number that
decided it: neutral out-of-sample t 1.034,
out-of-sample spread Sharpe 0.035, break-even
cost nan bp per rebalance
against a realistic 5 bp.

## Hypothesis and economic rationale

Earnings surprises are incorporated only gradually because attention is limited around announcements.

## Construction

Point-in-time by construction: the signal at t uses data through t-1 or
earlier, which is exactly what the shift audit verifies. Missing values stay
NaN, never filled.

## IC and decay

| horizon | mean IC |
| --- | --- |
| ic_h1 | 0.123986 |
| ic_h5 | 0.105174 |
| ic_h21 | 0.102950 |
| ic_h63 | 0.071382 |

## Factor-neutral IC

The signal is residualized on the champion design at each rebalance date,
s_perp = s - X (X'X)^-1 X' s. Mean neutral IC 0.009876,
out-of-sample mean 0.011988 with t
1.034.

## Regime IC

| regime | mean IC | n days |
| --- | --- | --- |
| pooled | 0.123986 | 715 |
| vix_low | 0.126904 | 239 |
| vix_mid | 0.128630 | 238 |
| vix_high | 0.116412 | 238 |

## Quantile spread

Hit rate 0.3952, turnover share per rebalance
nan, out-of-sample spread Sharpe
0.035.

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
