# E10 Risk Allocation and Drawdown Policy

The input is the synthetic book's net returns on corrected costs, at the
(rho, phi) configuration whose net annualized Sharpe is closest to 1.0,
scaled to the 10% volatility target, with the two seed books run
alongside. The synthetic label travels with every number.

The design book is rho 0.02, phi 0.95, seed
1, with a net annualized Sharpe of
0.978 (the seed-averaged capacity table reads
1.174, and the book is one realization, not the
average of five).

## The Kelly analysis

The design book's annualized moments, the full and half Kelly leverage,
the growth at each, and the cost of over-betting when the Sharpe is
overstated by one standard error:

| quantity | value |
| --- | --- |
| mean (annualized) | 0.0978 |
| vol (annualized) | 0.1000 |
| Sharpe | 0.978 |
| SE of Sharpe | 0.268 |
| full Kelly leverage | 9.781 |
| half Kelly leverage | 4.891 |
| growth at full Kelly | 0.4784 |
| growth at half Kelly | 0.3588 |
| growth loss, SR overstated by one SE | 0.0359 |

The chosen fraction is half Kelly. Full Kelly is the wrong answer for an
estimated Sharpe: running full Kelly at a Sharpe overstated by one
standard error loses 0.0359 of annual growth,
while half Kelly gives up only a quarter of the growth rate for far less
variance.

## The drawdown distribution

The simulated median maximum drawdown against the analytical median:

| quantity | value |
| --- | --- |
| simulated median drawdown | -0.1403 |
| analytical median drawdown | 0.0354 |
| relative gap at the median | 4.9598 |
| bootstrap samples | 2000 |

The analytical benchmark is the Magdon-Ismail infinite-horizon Brownian
median, ln(2) sigma squared over 2 mu. The gap measures the fat tails and
volatility clustering the Brownian benchmark does not have.

## The stop-loss verdict

The drawdown stop is flat while the running drawdown is below -10% and
re-enters at -5%. On i.i.d. bootstrapped returns it cannot improve Sharpe,
and on the real books the result is reported either way:

| book | base Sharpe | real-book Sharpe change |
| --- | --- | --- |
| design | 0.978 | -0.394 |
| seed_ew | 2.207 | 0.000 |
| seed_mom_ls | -0.248 | 0.226 |

## The volatility-targeting rule

The book will run scale_t = 10% / trailing realized vol, clipped to 3
times. The dispersion of realized annual vol across years:

| quantity | value |
| --- | --- |
| raw dispersion | 0.2663 |
| targeted dispersion | 0.2338 |
| dispersion reduction | 0.1220 |

## Drawdowns by VIX regime

| VIX tercile | mean VIX | max drawdown | periods underwater |
| --- | --- | --- | --- |
| 0 | 12.81 | -0.097 | 48 |
| 1 | 16.44 | -0.131 | 38 |
| 2 | 24.31 | -0.064 | 28 |

The risk budget is written per regime, not as one number.

## Stored criteria

- F10.1 (verdict fail): the simulated median
  drawdown is within 10% of the analytical median, or the gap is the
  fat-tail and clustering the Brownian benchmark does not have.
- F10.2 (verdict pass): the stop-loss does not
  improve Sharpe on the i.i.d. control, and the real book is reported
  either way.
- F10.3 (verdict fail): vol targeting reduces
  the dispersion of realized annual vol across years by
  0.1220.

## What would falsify this?

- The stop-loss improves Sharpe in the i.i.d. control: a bug, since it
  cannot.
- Vol targeting shows no effect on realized vol dispersion: the vol
  forecast is not doing its job, back to E2 and E5.
- Drawdowns strongly regime-dependent: the risk budget is written per
  regime, not as one number.
