# E7 Signal Report: idio_momentum

Verdict against the RG-Signal checklist: **NULL**. The number that
decided it: neutral out-of-sample t -0.936,
out-of-sample spread Sharpe 0.532, break-even
cost 8.00 bp per rebalance
against a realistic 5 bp.

## Hypothesis and economic rationale

Stock-specific news travels slowly after the common factors are removed, so residual momentum is information the factors miss.

## Construction

Point-in-time by construction: the signal at t uses data through t-1 or
earlier, which is exactly what the shift audit verifies. Missing values stay
NaN, never filled.

## IC and decay

| horizon | mean IC |
| --- | --- |
| ic_h1 | 0.012538 |
| ic_h5 | 0.012855 |
| ic_h21 | 0.008334 |
| ic_h63 | 0.004385 |

## Factor-neutral IC

The signal is residualized on the champion design at each rebalance date,
s_perp = s - X (X'X)^-1 X' s. Mean neutral IC -0.004506,
out-of-sample mean -0.009297 with t
-0.936.

## Regime IC

| regime | mean IC | n days |
| --- | --- | --- |
| pooled | 0.012538 | 3710 |
| vix_low | 0.009274 | 1233 |
| vix_mid | 0.016181 | 1230 |
| vix_high | 0.011155 | 1232 |

## Quantile spread

Hit rate 0.5294, turnover share per rebalance
0.3853, out-of-sample spread Sharpe
0.532.

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
