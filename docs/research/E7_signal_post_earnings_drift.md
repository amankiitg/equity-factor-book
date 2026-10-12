# E7 Signal Report: post_earnings_drift

Verdict against the RG-Signal checklist: **NULL**. The number that
decided it: neutral out-of-sample t 0.999,
out-of-sample spread Sharpe 0.071, break-even
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
| ic_h1 | 0.123252 |
| ic_h5 | 0.102243 |
| ic_h21 | 0.104212 |
| ic_h63 | 0.071396 |

## Factor-neutral IC

The signal is residualized on the champion design at each rebalance date,
s_perp = s - X (X'X)^-1 X' s. Mean neutral IC 0.007738,
out-of-sample mean 0.010626 with t
0.999.

## Regime IC

| regime | mean IC | n days |
| --- | --- | --- |
| pooled | 0.123252 | 721 |
| vix_low | 0.126919 | 241 |
| vix_mid | 0.127712 | 240 |
| vix_high | 0.115110 | 240 |

## Quantile spread

Hit rate 0.3947, turnover share per rebalance
nan, out-of-sample spread Sharpe
0.071.

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
