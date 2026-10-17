# E7 Signal Report: low_residual_volatility

Verdict against the RG-Signal checklist: **NULL**. The number that
decided it: neutral out-of-sample t 0.594,
out-of-sample spread Sharpe -0.779, break-even
cost -17.92 bp per rebalance
against a realistic 5 bp.

## Hypothesis and economic rationale

Low-risk stocks are systematically underbought by benchmarked managers, leaving their expected returns too high per unit of risk.

## Construction

Point-in-time by construction: the signal at t uses data through t-1 or
earlier, which is exactly what the shift audit verifies. Missing values stay
NaN, never filled.

## IC and decay

| horizon | mean IC |
| --- | --- |
| ic_h1 | -0.001527 |
| ic_h5 | -0.013105 |
| ic_h21 | -0.028049 |
| ic_h63 | -0.054162 |

## Factor-neutral IC

The signal is residualized on the champion design at each rebalance date,
s_perp = s - X (X'X)^-1 X' s. Mean neutral IC 0.002515,
out-of-sample mean 0.005566 with t
0.594.

## Regime IC

| regime | mean IC | n days |
| --- | --- | --- |
| pooled | -0.001527 | 3898 |
| vix_low | -0.020874 | 1298 |
| vix_mid | -0.000446 | 1294 |
| vix_high | 0.017160 | 1291 |

## Quantile spread

Hit rate 0.4497, turnover share per rebalance
0.3173, out-of-sample spread Sharpe
-0.779.

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
