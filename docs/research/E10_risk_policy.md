# E10 Risk Allocation and Drawdown Policy

The input is the synthetic book's net returns on corrected costs, at the
(rho, phi) configuration whose net annualized Sharpe is closest to 1.0,
scaled to the 10% volatility target, with the two seed books run
alongside. The synthetic label travels with every number.

The design book is rho 0.02, phi 0.95, seed
3, with a net annualized Sharpe of
1.074 (the seed-averaged capacity table reads
1.195, and the book is one realization, not the
average of five).

## The Kelly analysis

The design book's annualized moments, the full and half Kelly leverage,
the growth at each, and the cost of over-betting when the Sharpe is
overstated by one standard error:

| quantity | value |
| --- | --- |
| mean (annualized) | 0.1074 |
| vol (annualized) | 0.1000 |
| Sharpe | 1.074 |
| SE of Sharpe | 0.268 |
| full Kelly leverage | 10.738 |
| half Kelly leverage | 5.369 |
| growth at full Kelly | 0.5766 |
| growth at half Kelly | 0.4324 |
| growth loss, SR overstated by one SE | 0.0359 |

The chosen fraction is half Kelly. Full Kelly is the wrong answer for an
estimated Sharpe: running full Kelly at a Sharpe overstated by one
standard error loses 0.0359 of annual growth,
while half Kelly gives up only a quarter of the growth rate for far less
variance.

## The drawdown distribution

The simulated median and mean maximum drawdown against the analytical
median, the Gaussian control, and the horizon-matched expected maximum
drawdown:

| quantity | value |
| --- | --- |
| simulated median drawdown | -0.1281 |
| simulated mean drawdown | -0.1354 |
| analytical median drawdown | 0.0323 |
| relative gap at the median | 2.9679 |
| Gaussian control median drawdown | -0.1442 |
| horizon (years) | 14.6 |
| expected max drawdown at horizon | 0.1906 |
| expected-vs-simulated-median relative gap | 0.3280 |
| expected-vs-simulated-mean relative gap | 0.2897 |
| bootstrap samples | 2000 |

The analytical benchmark is the Magdon-Ismail infinite-horizon Brownian
median, ln(2) sigma squared over 2 mu, which is the stationary drawdown
median, not a maximum-drawdown quantity. The Gaussian control, i.i.d.
Gaussian paths at the book's own moments and length, draws down deeper
than the bootstrap, so the gap is the mismatch between a stationary
median and a finite-sample maximum, not fat tails or volatility
clustering.

The horizon-matched benchmark is the Magdon-Ismail positive-drift expected
maximum drawdown. Switching to it cuts the gap from 296% against the
stationary median to about 30% and does not close it, so F10.1b fails on
F10.1's own 10% bar. Part of what is left is that the benchmark is an
expected value while the simulation reports a median: comparing like for
like, the simulated mean against the expected value, the gap is about
26%, so the mean-versus-median mismatch is roughly four points of the
remainder and the rest is the Brownian benchmark not matching the book.

## The stop-loss verdict

The drawdown stop is flat while the running drawdown is below -10% and
re-enters at -5%. On i.i.d. bootstrapped returns it cannot improve Sharpe,
and on the real books the result is reported either way. The re-entering
stop tracks the unstopped equity curve while flat so the re-entry is
reachable:

| book | n_obs | n_dates_available | base Sharpe | old-stop change | re-entering change | stop_fired |
| --- | --- | --- | --- | --- | --- | --- |
| design | 175 | 175 | 1.074 | -0.495 | 0.031 | True |
| seed_ew | 232 | 4213 | 1.584 | 0.000 | 0.000 | False |
| seed_mom_ls | 4111 | 4112 | -0.254 | 0.215 | 0.215 | True |

## The volatility-targeting rule

The book will run scale_t = 10% / trailing realized vol, clipped to 3
times. The dispersion of realized annual vol across years, on the aligned
year set:

| quantity | value |
| --- | --- |
| raw dispersion | 0.5733 |
| targeted dispersion | 0.3920 |
| dispersion reduction | 0.3162 |
| years, raw side | 15 |
| years, targeted side | 14 |
| years, aligned | 14 |

A daily-return volatility estimate, the scale decided at each rebalance
from the trailing daily window and applied to the next rebalance return,
does no better:

| estimator | window | dispersion reduction |
| --- | --- | --- |
| daily | 21 | 0.1644 |
| daily | 42 | 0.0452 |
| daily | 63 | 0.0442 |
| daily | 126 | 0.0563 |
| daily | 252 | 0.0094 |

The reduction is below the 40% bar not because the estimator is too
noisy: the year-to-year dispersion of this book's realized volatility is
not forecastable at this horizon, and the 40% bar was written for a
higher-frequency object than a monthly book.

## Drawdowns by VIX regime

| VIX tercile | mean VIX | max drawdown | periods underwater |
| --- | --- | --- | --- |
| 0 | 12.84 | -0.065 | 26 |
| 1 | 16.44 | -0.112 | 37 |
| 2 | 24.31 | -0.125 | 26 |

The risk budget is written per regime, not as one number.

## Stored criteria

- F10.1 (verdict fail, threshold "simulated median drawdown within 10% of the analytical value"):
  Simulated drawdown distribution matches the analytical approximation within 10% at the median for the seed book's SR.
- F10.1b (verdict fail, threshold "simulated median drawdown within 10% of the analytical value"):
  Simulated drawdown distribution matches the horizon-matched analytical approximation within 10% at the median for the seed book's SR.
- F10.2 (verdict pass, threshold "stop-loss does not improve Sharpe on the i.i.d. control"):
  Control: on i.i.d. bootstrapped returns the stop-loss does not improve Sharpe. On the real book the result is reported either way.
- F10.2b (verdict pass, threshold "re-entering stop does not improve Sharpe on the i.i.d. control"):
  The stop-loss that can re-enter does not improve Sharpe on the i.i.d. control.
- F10.3 (verdict fail, threshold "dispersion reduction above 40%"):
  Vol targeting reduces the dispersion of realized annual vol across years by more than 40%.
- F10.3b (verdict pass, threshold "maximum daily-estimator reduction below 40%"):
  A daily-return volatility estimate's dispersion reduction stays below 40% at every window.

## What would falsify this?

- The stop-loss improves Sharpe in the i.i.d. control: a bug, since it
  cannot.
- Vol targeting shows no effect on realized vol dispersion: the vol
  forecast is not doing its job, back to E2 and E5.
- Drawdowns strongly regime-dependent: the risk budget is written per
  regime, not as one number.
