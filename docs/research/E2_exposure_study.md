# Beta and Volatility Estimation Study

Sprint E2 research deliverable, 2026-09-10. Written for a senior quant or
risk manager who has not seen the code. No em dashes.

## PM answer

When the risk system says a stock has beta 1.3, believe the direction and
the order of magnitude, not the second decimal. The full-sample market
beta has a standard error near 0.02 to 0.03, but the rolling 252-day beta
moves much more than that and is the number a hedge actually faces: XOM's
full-sample beta is 0.78 while its most recent 252-day beta is -0.49. Use
the shrinkage-adjusted rolling beta with a Newey-West standard error next
to it, re-estimate monthly for hedging, and size positions off the
idiosyncratic volatility from the FF5 plus momentum model, not off total
volatility. Volatility forecasts should come from EWMA(0.97) on own
returns: it has the best average QLIKE of every method tested and needs
no external factor feed, so it can refresh daily. The honest bad news is
that no method beats a trailing 252-day volatility estimate on a
name-by-name majority, so F2.3 fails, and the pre-registered claim that
GARCH and EWMA(0.94) would beat trailing volatility for more than 60% of
names is rejected.

## Research questions

- Academic question: How is a stock's exposure to observed factors
  estimated by time-series regression, how uncertain is the estimate, and
  when does shrinkage improve it?
- Practitioner question: When the risk system says a stock has beta 1.3,
  how much should I believe it, how fast does it move, and what is its
  residual (idio) return?
- Research question: Do shrunk, exponentially weighted betas forecast
  next-quarter realized betas and portfolio volatility better than raw OLS
  betas, and do GARCH or EWMA forecasts beat trailing volatility?

## Methodology

Sample. Every regression starts at MODEL_START = 2010, the first calendar
year with at least 300 point-in-time members with price coverage (2010
has 354, rising to 511 by 2026; the table is in sprints/E2/PROBES.md).
The panel is 4,193 business days by 858 tickers.

Exclusions. Rows flagged stale or outlier in returns.parquet are excluded
from every estimation window: 9,542 stale rows and 220 outlier rows. NaN
rows, which include the 302 interior gaps and the delisting tails, are
dropped and never forward-filled; 1,138,521 rows in total.

Estimators. OLS with an intercept, standard errors from the classical
formula and Newey-West HAC at lag 5 with weights 1 - j/6. Shrinkage:
Vasicek toward the cross-sectional mean with weight sigma_xs^2 /
(sigma_xs^2 + SE^2), and Blume with 0.67 and 0.33. Rolling 252-day and
exponentially weighted betas with half-lives 63 and 126 days. Every
rolling or EWMA estimate dated t is fit on data through t-1; a shift test
proves it. Volatility: EWMA(0.94) and EWMA(0.97), trailing variance over
21, 63 and 252 days, and GARCH(1,1) via the arch package, which installed
and fit cleanly on Python 3.14. Forecasts are evaluated out of sample
from 2024-09-03 with QLIKE, ln(sigma_hat^2) + r^2 / sigma_hat^2.

## Stored numbers

Falsification criteria, evaluated from the artifacts and stored in
sprints/E2/RESULTS.json.

| ID | Threshold | Stored number | Verdict |
| --- | --- | --- | --- |
| F2.0a | coverage table stored and MODEL_START recorded | MODEL_START 2010, 17 years stored, current members 100% | pass |
| F2.0b | NaN rows dropped, never imputed | 302 interior NaN rows, dropped by the fit (n_obs equals valid count) | pass |
| F2.0c | audit mean below 0.1 bp, every day above 50 bp in events with a cause | mean 0.0178 bp, 1 day above 50 bp, 1 matched (BKR 2017-07-05 special distribution) | pass |
| F2.1 | full-sample vs mean rolling beta correlation above 0.9 | 0.9123 | pass |
| F2.2 | mean pairwise FF5+MOM residual correlation below 0.05 | 0.0183 on 150 names | pass |
| F2.3 | GARCH and EWMA(0.94) each beat trailing 252d QLIKE for more than 60% of names | GARCH 46.7% of 45 names, EWMA(0.94) 36.4% of 514 names | fail |
| F2.4 | equal-weight seed book bias ratio between 0.8 and 1.2 across calendar years | mean 1.023, per-year range 0.68 (2012) to 1.40 (2020) | pass |
| F2.5 | Newey-West SE exceeds OLS SE for more than 80% of names | 95.4% | pass |

Reference loadings, full sample. AAPL beta 1.074 (OLS SE 0.0182, Newey-West
SE 0.0265), alpha 0.00046, R squared 0.455. XOM beta 0.777 (0.0183,
0.0335), R squared 0.302. JPM beta 1.130 (0.0165, 0.0293), R squared
0.529. Mean R squared across the universe is 0.364, in the expected 0.2
to 0.4 range. Newey-West widens the market beta standard error by roughly
45 to 80 percent for these names, so autocorrelated residuals are the
norm, not the exception.

## Beta horse race

Predictors at each month end fit on data through t-1; target is the
realized beta over the next 63 trading days. 191 month ends, about
112,000 name-dates. Vasicek uses the rolling window's own standard error
for its weight and the cross-sectional beta dispersion for its shrink
target.

| Method | RMSE | Mean bias |
| --- | --- | --- |
| Vasicek | 0.4228 | +0.0072 |
| Raw rolling 252d | 0.4272 | +0.0182 |
| EWMA 126d | 0.4280 | +0.0258 |
| Blume | 0.4338 | +0.0156 |
| EWMA 63d | 0.4385 | +0.0165 |

Read this table carefully. Vasicek is the best on both RMSE and bias: it
cuts the bias by 60 percent relative to the raw rolling beta, which is
what a hedge cares about. But the RMSE advantage is small, 1 percent, and
the raw rolling beta is only 1 percent behind; shrinkage is not
decoration, but it is not a large effect either. The 63-day EWMA beta is
the worst of the five, which is the horizon lesson: a short half-life
fits recent noise and forecasts the next quarter worse than a 126-day or
252-day window.

## Volatility horse race

Out of sample from 2024-09-03 to 2026-09-03, QLIKE lower is better.

| Method | Mean QLIKE | Names | Win share vs trailing 252d |
| --- | --- | --- | --- |
| EWMA(0.97) | -6.676 | 514 | 52.7% |
| GARCH(1,1) | -6.661 | 45 | 46.7% |
| EWMA(0.94) | -6.621 | 514 | 36.4% |
| Trailing 63d | -4.622 | 638 | 37.2% |
| Trailing 252d (baseline) | -1.823 | 632 | baseline |
| Trailing 21d | +3.019 | 644 | 16.3% |

Two readings, and they disagree. On the average loss, every adaptive
method crushes trailing volatility, and EWMA(0.97) is the best; the mean
QLIKE gap between EWMA(0.97) and trailing 252d is nearly 5 units, which
is enormous. On the name-by-name win share, no method clears 60 percent:
EWMA(0.97) wins on 52.7 percent of names, GARCH on 46.7 percent, and
EWMA(0.94) on only 36.4 percent. The gap between the two readings comes
from a small number of names where a stale trailing estimate is very
wrong and QLIKE is unbounded above; those names dominate the mean. The
pre-registered F2.3 threshold was written on the win share, so F2.3
fails, and the study reports that rather than switching to the friendlier
statistic after the fact.

## Recommended estimator per use

- Hedging: Vasicek-shrunk rolling 252-day market beta, refit monthly,
  with the Newey-West standard error attached. It has the lowest forecast
  RMSE and the lowest bias, and the shrink weight uses the estimate's own
  standard error, so a noisy name is pulled toward the cross-section.
  Treat betas older than a quarter as stale: XOM's rolling beta moved
  from 0.78 full sample to -0.49 over the last year.
- Risk: EWMA(0.97) for volatility, EWMA half-life 90 days for the factor
  covariance. EWMA has the best average QLIKE, is refreshable daily from
  EFB's own returns with no external feed, and needs one parameter.
  GARCH(1,1) does not beat it on the mean or on the win share, so per the
  pre-registered falsification test, production uses EWMA and simplicity
  wins.
- Sizing: the FF5 plus momentum decomposition, with idiosyncratic
  variance from the TS-v1 residuals. For the equal-weight seed book the
  factor share of variance is 99.2 percent, so the book is a factor
  position, not a collection of idio bets; for the sector-neutral
  momentum long/short seed book the factor share is only 9.4 percent, so
  its risk is almost entirely idiosyncratic and must be sized on the
  residual. Carry the E1 caveat: the short side's specific risk is biased
  downward because missing deletions are disproportionately failures.

Portfolio risk at the last date, from sigma_p^2 = w' B F B' w + w' D w:

| Book | Predicted vol (ann) | Factor variance | Idio variance | Factor share |
| --- | --- | --- | --- | --- |
| Equal-weight seed (survivorship caveat true) | 13.4% | 7.10e-05 | 1.00e-06 | 99.2% |
| Momentum long/short seed (caveat false) | 2.5% | 1.04e-06 | 1.00e-05 | 9.4% |

The bias statistic for the equal-weight seed book averages 1.023 across
calendar years, inside the 0.8 to 1.2 band, but the yearly values swing
from 0.68 in 2012 to 1.40 in 2020. The model is right on average and
wrong in any given year, which is the honest summary of a one-factor
scaled covariance on a long-only equity book.

## Residual correlation structure

The mean pairwise correlation of FF5 plus momentum residuals is 0.0183 on
a seeded sample of 150 names with at least 500 overlapping observations,
well below the 0.05 bar. The observed factor set is adequate for this
universe: there is no dominant missing common factor, and idiosyncratic
risk is not materially overstated by treating the residual as specific.
The finding does not retire E3, because a cross-sectional model can add
value with a small residual correlation, but it does remove the strongest
argument for E3, and F2.2 stays below the threshold that would have
forced the question. The residual correlation also says the sector and
style clustering in this universe is largely captured by SMB, HML, RMW,
CMA and MOM once the market factor is included.

## What would falsify this?

If shrunk betas did not beat raw betas out of sample, shrinkage would be
decoration and TS-v2 would drop it. Measured: Vasicek RMSE 0.4228 against
raw 0.4272 and bias +0.0072 against +0.0182. The claim survives, but
narrowly, and a single quarter of different data could flip the RMSE
ordering; the bias improvement is the more robust result. If residual
correlations exceeded 0.05, the observed-factor set would be inadequate
and the finding would carry into E3; at 0.0183 the test does not fire. If
GARCH did not beat EWMA meaningfully on QLIKE, production would use EWMA
and simplicity would win; that is exactly what happened, with EWMA(0.97)
ahead of GARCH on both the mean and the win share. And if the
pre-registered F2.3 threshold failed, the study must say so: it failed,
and the deliverable records that no volatility method beat trailing
volatility on a name-by-name majority, which is a negative verdict and a
complete one.

## Open questions

- The beta horse race uses month-end rebalancing and a 63-day target. A
  quarter is the hedging horizon assumed here; a weekly or annual horizon
  could reorder the methods.
- GARCH was fit on 60 names, of which 45 are usable out of sample, so its
  win share is noisier than the EWMA numbers. A full-universe fit would
  settle whether GARCH's average advantage is real.
- Shrinkage targets the cross-sectional beta mean. A sector-conditional
  or volatility-scaled target is the natural TS-v2 improvement.
- The predicted portfolio vol uses a single market factor in the history
  and the full six-factor model at the last date; the multifactor
  decomposition is a snapshot, not a time series.
- The loser-side idio bias from E1 remains: tracking a delisting-return
  source in docs/open_items.md is a prerequisite for trusting long/short
  specific-risk numbers.
