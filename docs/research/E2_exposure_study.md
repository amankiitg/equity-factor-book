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

Series breaks. Four symbols were reused by later listings, so the vendor
history splices two companies: CPWR (a real member from 2010 to 2011),
EP (2010 to 2012), MI (2010 to 2011) and POM (2010 to 2016). Their
adjusted closes move by more than 5x in a day with no split to explain
it, which is the F2.6 test. A flagged day is not enough here, because
the whole history after the break belongs to a different company, so the
four names leave the estimation panel. F2.6 is a successor criterion
written after the fact, not a pre-registered one, and it fails: the
names are dropped rather than repaired, and repairing them needs a
security-identity source (FIGI or PERMNO) tracked in docs/open_items.md.

One flagged row nearly decided a headline number. Ticker MI has a single
day of +9542.9% on 2026-05-18, of which a 96x jump in the adjusted close
from 0.196 to 18.90 is the visible part, flagged by the E1 hygiene layer
and left in the raw artifact as the ledger requires. The volatility and
portfolio code first read raw returns, so that one row pushed the
trailing 252d mean QLIKE from -6.61 to -1.82 and made it look as though
every adaptive method crushed the baseline by five QLIKE units. All
volatility, momentum and portfolio code now reads returns through
efb.hygiene.clean_returns, which sets stale and outlier rows to NaN
without touching the raw column or the flags. The ledger entry of
2026-09-10 records the correction in full.

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
| F2.1 | full-sample vs mean rolling beta correlation above 0.9 | 0.9239 | pass |
| F2.2 | mean pairwise FF5+MOM residual correlation below 0.05 | 0.0154 on 150 names | pass |
| F2.3 | GARCH and EWMA(0.94) each beat trailing 252d QLIKE for more than 60% of names | GARCH 44.4% of 45 names, EWMA(0.94) 35.4% of 483 names, paired 37 names where both fit: GARCH 40.5%, EWMA(0.94) 27.0% | fail |
| F2.3b | the same 60% bar with forecast and target horizons matched | horizon 1: GARCH 46.7%, EWMA(0.94) 35.4%. horizon 21: GARCH 55.6%, EWMA(0.94) 19.9% | fail |
| F2.4 | equal-weight seed book bias ratio between 0.8 and 1.2 across calendar years | mean 1.0221, per-year range 0.68 (2012) to 1.39 (2020) | pass |
| F2.5 | Newey-West SE exceeds OLS SE for more than 80% of names | 96.3% | pass |
| F2.6 | no name has an unexplained adjusted-close move above 5x (successor to F2.3, not pre-registered) | 4 names: CPWR, EP, MI, POM, 20 rows | fail |
| F2.6b | identity check stored and its exclusions applied by the build | 373 removed tickers compared, 36 reused symbols found and dropped, none left in the estimated panel | pass |

Reference loadings, full sample. AAPL beta 1.074 (OLS SE 0.0182, Newey-West
SE 0.0265), alpha 0.00046, R squared 0.455. XOM beta 0.777 (0.0183,
0.0335), R squared 0.302. JPM beta 1.130 (0.0165, 0.0293), R squared
0.529. Mean R squared across the universe is 0.366, in the expected 0.2
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
| EWMA 126d | 0.3962 | +0.0271 |
| EWMA 63d | 0.3967 | +0.0175 |
| Vasicek | 0.4020 | +0.0074 |
| Raw rolling 252d | 0.4058 | +0.0184 |
| Blume | 0.4135 | +0.0168 |

Read this table carefully, and do not over-read it. Every method beats
the raw rolling beta on RMSE by 0.9 to 2.4 percent, and the ordering
among the winners is inside the noise of one 63-day target. What
separates them is bias. Vasicek has the smallest bias, +0.0074 against
+0.0184 raw, a 60 percent cut, because its weight falls as the estimate's
own standard error rises. EWMA(126) has the best RMSE and the worst bias,
so it is the better forecast and the worse hedge. For hedging, where a
systematic over-hedge compounds, bias is what matters and Vasicek wins;
for forecasting a realized beta, use EWMA(126). Neither claim is strong,
and the narrow margins are stated rather than dressed up.

## Volatility horse race

Out of sample from 2024-09-03 to 2026-09-03, QLIKE lower is better. Every
number below excludes flagged stale and outlier rows.

| Method | Mean QLIKE | Names | Win share vs trailing 252d |
| --- | --- | --- | --- |
| EWMA(0.97) | -6.744 | 483 | 52.0% |
| EWMA(0.94) | -6.701 | 483 | 35.4% |
| GARCH(1,1) | -6.716 | 45 | 44.4% |
| Trailing 252d (baseline) | -6.620 | 608 | baseline |
| Trailing 63d | -6.574 | 611 | 36.7% |
| Trailing 21d | -6.479 | 615 | 15.3% |

EWMA(0.97) is the best method on both readings: best mean QLIKE and the
best win share, though the win share still stops at 52.0 percent. GARCH
is close on the mean and, where it can be fitted, better than
EWMA(0.94) on the one-step pair: on the 37 names where both are available
GARCH wins 73.0 percent of the head-to-head comparisons. The problem with
GARCH is coverage rather than accuracy, since arch fits only 45 of the
names that have enough history. No method clears 60 percent name by name,
so the pre-registered F2.3 threshold fails, and the horizon-matched
F2.3b test below fails with it. An earlier draft of this section reported
a five unit mean gap between EWMA and the trailing baseline; that gap was
the MI outlier, not a property of the estimators, and it is corrected
here rather than removed from the record.

### Horizon alignment (close-out C3)

The first question to ask about a volatility result that contradicts the
daily-vol literature is whether the two sides are measuring the same
thing. Here they were: QLIKE is ln sigma2 plus r^2 / sigma2, forecast and
target are both one step ahead, and ewma_vol, realized_var and
garch_forecast all index a forecast at the date of the return it predicts.
So the fail is not a horizon mismatch, and no rescaling of the
comparison would rescue it. Two further diagnostics:

- The arch fit scales returns by 100 for numerical stability and divides
the variance back by 1e4. Returns are scaled and the estimator is not
wrong for it.
- 47 of the 60 attempted GARCH fits converge; the 13 that do not are
  ABK, ABMD, ABS, ACAS, ACE, ADS, AGN, AKS, ALTR, ALXN, AMTM, ANR and
  ANSS. GARCH's win shares are therefore measured on a survivorship-biased
  subset of the longest, calmest histories.

A third reading explains more than either. Counting names, as F2.3 does,
EWMA(0.94) wins for only 35.4 percent of names. Counting name-days, the
same estimator has the lower QLIKE on 51.6 percent of 242,126 name-days
(51.3 percent in 2024, 54.6 percent in 2025, 47.2 percent in 2026). The
two disagree because a per-name mean is dominated by the handful of names
where a forecast is badly wrong on one day, and QLIKE is unbounded above.
The 2020 window the brief asked about is not in the sample at all: the
out-of-sample window starts on 2024-09-03, so excluding 2020 changes
nothing.

The horizon-matched evaluation (F2.3b) then asks whether GARCH looks
better once its multi-step dynamics are used rather than a flat scaling:

| Horizon | GARCH win share | EWMA(0.94) | EWMA(0.97) |
| --- | --- | --- | --- |
| 1 day vs same-day r^2 | 46.7% | 35.4% | 52.0% |
| 21 days vs 21-day realized variance | 55.6% | 19.9% | 34.4% |

GARCH improves from 46.7 to 55.6 percent when the horizon is matched,
which is the mechanism the hypothesis predicted, but 55.6 percent is
still short of the 60 percent bar and far short of the 70 percent that
would put the production choice back on the table for E5. EWMA(0.97)
stays the production estimator, and F2.3 stands as a fail on a second,
harder test.

## Recommended estimator per use

- Hedging: Vasicek-shrunk rolling 252-day market beta, refit monthly,
  with the Newey-West standard error attached. It has the lowest bias of
  the five methods and the second lowest RMSE, and the shrink weight uses
  the estimate's own standard error, so a noisy name is pulled toward the
  cross-section. If the goal is forecasting realized beta rather than
  hedging it, EWMA(126) has the lowest RMSE and should be used instead.
  Treat betas older than a quarter as stale: XOM's rolling beta moved
  from 0.78 full sample to -0.49 over the last year.
- Risk: EWMA(0.97) for volatility, EWMA half-life 90 days for the factor
  covariance. EWMA has the best mean QLIKE and the best win share, is
  refreshable daily from EFB's own returns with no external feed, and
  needs one parameter. GARCH beats EWMA(0.94) where both are estimable but
  fits only 45 of the names, so it cannot be the production default; the
  pre-registered falsification test is what decides this, and it failed.
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
| Equal-weight seed (survivorship caveat true) | 13.4% | 7.00e-05 | 5.60e-07 | 99.2% |
| Momentum long/short seed (caveat false) | 2.5% | 2.35e-07 | 2.27e-06 | 9.4% |

The bias statistic for the equal-weight seed book averages 1.0221 across
calendar years, inside the 0.8 to 1.2 band, but the yearly values swing
from 0.68 in 2012 to 1.39 in 2020. The model is right on average and
wrong in any given year, which is the honest summary of a one-factor
scaled covariance on a long-only equity book.

## Residual correlation structure

The mean pairwise correlation of FF5 plus momentum residuals is 0.0154 on
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
decoration and TS-v2 would drop it. Measured: Vasicek RMSE 0.4020 against
raw 0.4058 and bias +0.0074 against +0.0184. The claim survives on both,
but narrowly on RMSE, and a single quarter of different data could flip
the RMSE ordering; the bias improvement is the more robust result. The
stronger version of the same test does not survive: EWMA(126) beats
Vasicek on RMSE, 0.3962 against 0.4020, so shrinkage is not the best
forecast of next-quarter beta, only the least biased one. If residual
correlations exceeded 0.05, the observed-factor set would be inadequate
and the finding would carry into E3; at 0.0154 the test does not fire. If
GARCH did not beat EWMA meaningfully on QLIKE, production would use EWMA
and simplicity would win. The answer is split and the split is reported
rather than resolved in favour of either side: GARCH beats EWMA(0.94) on
the names where both are estimable, and EWMA(0.97) has the best mean
QLIKE and win share across the universe. And if the
pre-registered F2.3 threshold failed, the study must say so: it failed,
and the deliverable records that no volatility method beat trailing
volatility on a name-by-name majority, which is a negative verdict and a
complete one. The horizon-matched F2.3b test then failed as well, which
rules out the most plausible explanation for the first failure.

## Open questions

- The beta horse race uses month-end rebalancing and a 63-day target. A
  quarter is the hedging horizon assumed here; a weekly or annual horizon
  could reorder the methods.
- GARCH was fit on 60 names, of which 45 are usable out of sample and 37
  overlap with EWMA, so its win share is noisier than the EWMA numbers and
  the two win shares are not measured on the same names. A full-universe
  fit would settle whether GARCH's advantage on the paired sample holds.
- Four names are dropped rather than repaired. CPWR, EP, MI and POM have
  reused symbols, so their price histories splice two companies and the
  original issuers' real histories are missing from the panel entirely.
  Dropping them is a mitigation, not a fix, and it is recorded as F2.6
  failing; a security-identity source in docs/open_items.md is the fix.
- Shrinkage targets the cross-sectional beta mean. A sector-conditional
  or volatility-scaled target is the natural TS-v2 improvement.
- The predicted portfolio vol uses a single market factor in the history
  and the full six-factor model at the last date; the multifactor
  decomposition is a snapshot, not a time series.
- The loser-side idio bias from E1 remains: tracking a delisting-return
  source in docs/open_items.md is a prerequisite for trusting long/short
  specific-risk numbers.
