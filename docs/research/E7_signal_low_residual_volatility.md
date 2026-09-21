# E7 Signal Report: low_residual_volatility

Verdict against the RG-Signal checklist: **NULL**. The number that
decided it: neutral out-of-sample t 0.358,
out-of-sample spread Sharpe -0.871, break-even
cost -20.09 bp per rebalance
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
| ic_h1 | -0.001400 |
| ic_h5 | -0.012976 |
| ic_h21 | -0.028309 |
| ic_h63 | -0.054505 |

## Factor-neutral IC

The signal is residualized on the champion design at each rebalance date,
s_perp = s - X (X'X)^-1 X' s. Mean neutral IC 0.001865,
out-of-sample mean 0.003477 with t
0.358.

## Regime IC

| regime | mean IC | n days |
| --- | --- | --- |
| pooled | -0.001400 | 3878 |
| vix_low | -0.020430 | 1297 |
| vix_mid | -0.000521 | 1290 |
| vix_high | 0.016840 | 1291 |

## Quantile spread

Hit rate 0.2788, turnover share per rebalance
0.3179, out-of-sample spread Sharpe
-0.871.

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
