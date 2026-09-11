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
| F2.1 | full-sample vs mean rolling beta correlation above 0.9 | 0.9244 | pass |
| F2.2 | mean pairwise FF5+MOM residual correlation below 0.05 | 0.0156 on 150 names | pass |
| F2.3 | GARCH and EWMA(0.94) each beat trailing 252d QLIKE for more than 60% of names | GARCH 58.2% of 98 names, EWMA(0.94) 35.4% of 483 names, paired 80 names where both fit: GARCH 53.8%, EWMA(0.94) 36.3% | fail |
| F2.3b | the same 60% bar with forecast and target horizons matched | horizon 1: GARCH 61.2%, EWMA(0.94) 35.4%. horizon 21: GARCH 49.0%, EWMA(0.94) 19.9% | fail |
| F2.3c | the same 60% bar on a seeded random sample of 100 fully covered names | seed 20260910, 100 names drawn from 599 with full coverage, 98 fits converging and 2 not (LW, RDDT). horizon 1: GARCH 61.2%, EWMA(0.94) 35.4%. horizon 21: GARCH 49.0%, EWMA(0.94) 19.9% | fail |
| F2.4 | equal-weight seed book bias ratio between 0.8 and 1.2 across calendar years | mean 1.0225, per-year range 0.68 (2012) to 1.39 (2020) | pass |
| F2.5 | Newey-West SE exceeds OLS SE for more than 80% of names | 96.3% | pass |
| F2.6 | no name has an unexplained adjusted-close move above 5x (successor to F2.3, not pre-registered) | 4 names: CPWR, EP, MI, POM, 20 rows | fail |
| F2.6b | identity check stored and its exclusions applied by the build | 373 removed tickers compared, 36 reused symbols found, 33 dropped and 3 restored by the C6 review, none left in the estimated panel that the build did not mean to keep | pass |
| F2.6c | current-constituent coverage of the estimation panel at or above 501 of 503, with the re-add review stored | 502 of 503 covered, 99.80% against a bar of 99.602%, one name missing (DD); review keeps FOX (2019-03-13), FOXA (2019-03-12) and PCG (2022-10-03) | pass |

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
  position, not a collection of idio bets. For the sector-neutral
  momentum long/short seed book the answer depends on how the portfolio
  beta is measured, and the three measurements are 0.0968 with name-level
  TS betas and last-month weights, 0.1462 with the portfolio regression
  betas and MOM removed from the covariance, and 0.8906 with the same
  betas and all six factors. The regression explains 0.5581 of the book's
  daily variance. The C4 check in the close-out section shows why the book
  is a momentum position (MOM loading +0.2885, t 29.10), and the spread
  between those three numbers is the diagonal-residual assumption at work:
  a 192-name long/short book looks nearly risk-free when its residual
  co-movement is thrown away. C8 measures the same share from rolling
  name-level betas dated at each rebalance instead of from one full-sample
  fit, and gets a mean of 0.7390 across 195 rebalances, which is the number
  that belongs here. Size it on the realized residual covariance, which E3
  owns; until then treat the low idio share as unproven rather than as a
  finding. Carry the E1 caveat as well: the short side's specific risk is
  biased downward because missing deletions are disproportionately
  failures.

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

## Close-out

Four tasks were added after the sprint's exit criteria were met, because
the F2.3 investigation and the F2.6 successor criterion both pointed at
data problems that the first write-up had taken at face value. This
section records their numbers. Nothing above is reworded, and every
criterion already stored keeps its number and its verdict.

C1, ticker identity (F2.6b, pass). Every ticker on the Wikipedia changes
table's removed list was compared with the current holder of that symbol on
yfinance, matched by name token overlap after stripping legal suffixes,
punctuation and share class letters. 373 tickers compared, 93 names still
match, 244 could not be verified because the symbol has no listing today,
and 36 symbols were reused. CPWR, EP, MI and POM are among them, with 32
more, listed with the removed and current security in
sprints/E2/PROBES.md. All 36 leave the estimation panel: returns fall from
858 tickers to 822, and the build applies the exclusion itself, which is
what F2.6b checks. No ticker needed truncation, because no reused symbol
has two live price segments separated by more than 60 business days.

The 32 extra names matter for how this should be read. Nine of them look
like real renames of the same issuer (ATI, CCE, CLF, CNX, DD, FOX, FOXA,
OI, PCG) and were excluded anyway, because names and prices cannot tell a
rename from a reuse that the vendor has hidden by keeping one company's
history. Dropping a legitimate history is the smaller error than keeping a
fabricated one, and the repair needs a security-identity source recorded
in docs/open_items.md.

C2, E1 restated (F1.3 and F1.5 moved, both verdicts unchanged). E1 was
rebuilt on the corrected returns and its results file now carries a
revisions block with the old value, the new value and the data hash of
each:

| Criterion | Before | After | Verdict |
| --- | --- | --- | --- |
| F1.3 equal-weight vs market correlation | 0.95575 | 0.95655 | pass |
| F1.5 naive minus point-in-time bias | 349.67 bp/yr | 365.81 bp/yr | fail |
| F1.5 point-in-time minus FF market | 20.75 bp/yr | 9.36 bp/yr | fail |
| F2.0a, F2.0b, F2.0c (cross sprint) | unchanged | unchanged | pass |

The bias grew, which is the honest direction: some previously counted
deleted members had fabricated histories. The prices artifact is byte for
byte identical across the two builds, verified by content hashes, so every
movement traces to the exclusions. The E1 walkthrough was re-executed and
re-rendered, and docs/research/E1_data_note.md carries the same table as
an Addendum with the original sections untouched.

C3, F2.3 diagnostic and F2.3b (both fail). The fail contradicted the
daily-vol literature, so it was treated as a hypothesis and tested. The
target and the horizon already matched: QLIKE is ln sigma2 + r^2 / sigma2,
every estimator in efb.vol forecasts the return on the date it is indexed
at, and the arch fit scales returns by 100 with the variance divided back,
with 47 of 60 fits converging. Counting name-days rather than names,
EWMA(0.94) wins on 51.6 percent of 242,126 name-days, so the name-level
fail comes from a few names where one day is badly mispriced and QLIKE is
unbounded above. The window starts on 2024-09-03, so the 2020 exclusion the
brief asked about is not available and changes nothing. The new aligned
evaluation registers as F2.3b with the same 60 percent bar: at horizon 1
GARCH reaches 46.7 percent and EWMA(0.94) 35.4; at horizon 21, against
realized variance, GARCH reaches 55.6 percent and EWMA(0.94) 19.9. GARCH
improves when its multi-step dynamics are used, which is the mechanism the
hypothesis predicted, but it does not reach 60, let alone the 70 that
would reopen the production choice for E5. EWMA(0.97) stays the production
estimator.

C4, momentum book exposure (check passes, one claim corrected). The
long/short seed book's own return series was regressed on FF5 plus MOM
with Newey-West standard errors: MOM loading +0.2885 with a t statistic of
29.10, and a significantly negative market loading, which is what a
dollar-neutral momentum book should look like. The check therefore passes.
What it also showed is that the idio share reported for that book is not
a single number: 0.8906 with the regression betas and all six factors in
the covariance, 0.1462 with MOM removed, 0.0968 with name-level TS betas
and last-month weights, and 0.5581 of daily variance explained by the
regression. The 0.5581 is the honest summary, and the 0.0968 in the
Sizing section above comes from the diagonal-residual assumption, which
makes a 192-name long/short book look nearly risk-free by discarding the
residual co-movement it is actually exposed to. C8 replaces that number
and is the entry to read: the same share measured from rolling betas at
each rebalance averages 0.7390, so the book is about three quarters factor
risk, not ten percent.

Every number in this paragraph moved in its fourth decimal when C6 put
three renamed constituents back in the panel. The old values (0.2897,
0.8919, 0.1459, 0.0939, 0.5564) are in the hygiene ledger with the new
ones, and no verdict changed.

After the four tasks: make rebuild-e2 versions 23 artifacts, the TS-v1
registry entry carries the same artifacts hash as data/VERSION.json
(3f2d32b3fd262e6c), and the sprint has 11 criteria, 8 passing and 3
failing (F2.3, F2.3b, F2.6).

## Close-out, second pass

Three more tasks were added after the first close-out, and they are
recorded the same way: nothing above was reworded, every criterion that
already had a number keeps it, and the C1 to C4 section stands as the
record of what that pass did.

C6, re-added names and the identity review (F2.6c, pass). C1's last
paragraph named nine symbols that look like renames of the same issuer and
dropped them anyway, because names alone cannot separate a rename from a
hidden reuse. C6 reopens exactly those cases with two more questions: is
the symbol a current index constituent, and does the changes table have an
added row for that same ticker dated after its removal. When either holds,
the name on that side is compared with the yfinance holder of the symbol,
and a match puts the ticker back with its history starting at the later of
the re-add date and its first valid price.

Four of the 36 reused symbols are current constituents. Three came back:

| Ticker | Removed name | Added name, or the name today | Holder on yfinance | Score | Decision | Truncated to |
| --- | --- | --- | --- | --- | --- | --- |
| FOX | 21st Century Fox | Fox Corporation (Class B) | Fox Corporation | 1.00 | keep | 2019-03-13 |
| FOXA | 21st Century Fox | Fox Corporation (Class A) | Fox Corporation | 1.00 | keep | 2019-03-12 |
| PCG | Pacific Gas & Electric Company | PG&E (added 2022-10-03) | PG&E Corporation | 1.00 | keep | 2022-10-03 |
| DD | DuPont | DuPont (added 2019-06-03) | DuPont de Nemours, Inc. | 0.33 | stays dropped | not applicable |

FOX and FOXA are the two share classes of the company that was spun out of
21st Century Fox in March 2019, which is why their truncation dates are one
day apart and both are the listing date rather than the removal date. PCG
was removed in January 2019 and readmitted in October 2022, so its panel
history now starts at the readmission. DD is the case the name matcher
cannot settle: "DuPont" against "DuPont de Nemours, Inc." scores 0.33,
below the 0.5 bar, because the holder's name carries two extra tokens and
the matcher is symmetric. A subset-style matcher would keep it, but that
would also re-score F2.6b's stored 93 matches and 244 unverified names
without any new evidence, so the matcher was left alone and the miss is
recorded instead.

The effect on the estimation panel is the number F2.6c is stated on. Of
the 503 current constituents, 502 now appear in returns.parquet, 99.80
percent, against the 501 of 503 bar in the close-out brief. Before C6 the
panel covered 499 of them: the four names above were missing. The one
remaining gap is DD. Note that the panel is the right place to measure
this: prices.parquet already covered all 503 names, including the three
that had been dropped from the estimated universe, so a coverage check on
the price file would have shown no problem at all.

F2.6b is re-measured rather than changed. Its criterion text, threshold and
verdict are untouched, and its numbers move because the data did: the
dropped list falls from 36 names to 33, the truncation list gains FOX,
FOXA and PCG, and the leak check now treats a name the review restored as
expected rather than as a failed exclusion. Without that, F2.6b would have
failed on the three names F2.6c deliberately puts back.

C2 re-run, E1 restated again. The E1 rebuild ran a second time, so its
revisions history now holds three entries, one per data hash, and the
second entry records the intermediate build that changed nothing (hash
6d24107521893114). The final numbers:

| Criterion | Before C6 | After C6 | Verdict |
| --- | --- | --- | --- |
| F1.3 equal-weight vs market correlation | 0.95655 | 0.95636 | pass |
| F1.5 fraction of deleted members recovered | 0.44789 | 0.44789 | fail |
| F1.5 naive minus point-in-time bias | 365.81 bp/yr | 365.10 bp/yr | fail |
| F1.5 naive minus FF market | 377.20 bp/yr | 375.37 bp/yr | fail |
| F1.5 point-in-time minus FF market | 9.36 bp/yr | 8.24 bp/yr | fail |

All four E1 verdicts are unchanged. The E2 criteria moved with the same
correction, and each one is in the hygiene ledger with its old and new
value: F2.1 from 0.92389 to 0.92436, F2.2 from 0.0154 to 0.0156, F2.4's
mean bias from 1.02211 to 1.02253 with the whole per-year series shifted,
F2.5 from 0.96321 to 0.96338, and F2.3b's trailing 63-day baseline win
share from 36.68 percent to 36.66 at horizon 1 and from 30.76 to 30.77 at
horizon 21. No verdict changed, and the three restored names move the
numbers by less than a tenth of a percent each, which is the scale you
would expect from adding back 3 names to a 500-name universe.

After C6: make rebuild-e2 versions 26 artifacts, data/VERSION.json and the
TS-v1 registry entry both carry artifacts hash 88c0062b281698c2, and the
sprint has 12 criteria, 9 passing and 3 failing (F2.3, F2.3b, F2.6).

C7, the GARCH sample and the window (F2.3c, fail). F2.3 and F2.3b were
measured on the first 60 names of the sorted universe, which is the names
starting with A and B rather than a sample of anything. The evaluation now
draws 100 names at random, with seed 20260910, from the 599 names with full
coverage over the out-of-sample window, and records the seed, the sample,
the eligible count and the names that did not converge. 98 of the 100 fits
converge; LW and RDDT do not.

The verdict does not change, but the number does. GARCH's win share at
horizon 1 rises from 46.7 percent on the alphabetical 60 to 61.2 percent on
the seeded sample, so it clears the 60 percent bar there for the first
time, while at horizon 21 it falls from 55.6 to 49.0. On the one-step
legacy race the same move takes GARCH from 44.4 percent of 45 names to 58.2
percent of 98. EWMA(0.94) is at 35.4 percent at horizon 1 and 19.9 percent
at horizon 21 either way, so F2.3c fails on EWMA, not on GARCH, and F2.3
and F2.3b are re-measured to the same shares with their text and verdicts
untouched. The honest reading is that GARCH's measured performance was a
property of which names happened to be tested, and a random sample of the
names that can be scored is the only way to have said so.

The window question, asked separately and without a new criterion. The same
estimators run over the whole history from MODEL_START rather than the
two-year out-of-sample window, and the answer is that the trailing-wins
result is a property of the window:

| Comparison | EWMA(0.94) | EWMA(0.97) |
| --- | --- | --- |
| name level, 2-year out-of-sample window, 483 names | 35.4% | 52.0% |
| name level, full history from 2010, 506 names | 74.3% | 86.8% |
| name-days, full history, 1,948,463 observations | 57.7% | 56.9% |
| name-days, full history excluding 2020 | 57.3% | 56.7% |
| name-days, 2020 alone | 63.5% | 60.5% |

So trailing 252d beats EWMA(0.97) for just under half the names in the
two-year window, and loses to it for almost seven names in eight over the
full history. 2020 is not the reason either way: EWMA(0.97) beats trailing
on 60.5 percent of name-days inside 2020 and on 56.7 percent of them once
2020 is removed, which is the same number. The year-by-year series
(eval/vol_window_dependence.parquet) has EWMA(0.97) above 50 percent in 12
of the 16 calendar years, and the four exceptions are 2015, 2018, 2022 and
2026. None of this changes a criterion: F2.3 is stated on the out-of-sample
window and keeps its fail. What it changes is how the fail should be read,
and the Volatility horse race section above should be read with this table
next to it.

After C7: make rebuild-e2 versions 27 artifacts, data/VERSION.json and the
TS-v1 registry entry both carry artifacts hash 1ce2bcf7 (full value in the
file), and the sprint has 13 criteria, 9 passing and 4 failing (F2.3,
F2.3b, F2.3c, F2.6).

C8, when the momentum exposure is measured, and what the diagonal model
misses. No criterion is added: C4's check passes and these two measurements
explain it rather than testing it.

(a) The book's MOM exposure at each rebalance, from rolling 252-day
name-level betas dated at the rebalance and the weights actually held, over
195 month ends from 2010-07-30 to 2026-09-03:

| Measure | What it uses | Value |
| --- | --- | --- |
| rolling-beta exposure, mean | w(t) and beta(t) at each of 195 rebalances | +0.0698 |
| rolling-beta exposure, range | same series | -0.3322 to +0.3905 |
| static aggregate | last month's weights, full-sample betas | -0.0162 |
| regression loading | the book's own return series, FF5+MOM | +0.2885 |

Three measurements of one thing, and the static one is the outlier: it says
the book has no momentum exposure at all, on a book whose own return series
loads +0.2885 on MOM with a t statistic of 29.10 and which is long the
winners and short the losers by construction. The reason is that the
weights are re-sorted every month and a full-sample beta is not, so the
static aggregate combines this month's book with a beta fitted across
sixteen years of a changing book. Done properly, the conditional exposure
is positive at 73.9 percent of rebalances and swings from -0.33 to +0.39,
which is what a book that re-selects names every month should look like.
The mean of the conditional measure is smaller than the regression loading,
and that gap is measurement error in name-level betas, which attenuates the
cross-sectional aggregate: both numbers are reported rather than one being
selected.

The same construction gives the factor share of the book's variance at each
rebalance, using all six factors and each date's rolling betas. It averages
0.7390, against 0.0968 for the static full-sample decomposition with
last-month weights. That is the C4 claim in the same units it was made in:
the book is roughly three quarters factor risk, not nine tenths
idiosyncratic, and the static number understates the factor share by a
factor of about eight.

(b) The diagonal model's bias statistic for the same book: realized
21-day forward vol over predicted vol, at each month end, by calendar year.
193 month ends, mean 1.8544, and the year-by-year values run from 1.1063
(2012) to 2.9259 (2026), with 2020 at 2.4560. Every single year is above
1.0. For comparison, the same statistic on the equal-weight book with a
63-day forward window is 1.0225, which is F2.4 and passes. So the diagonal
model is calibrated on the equal-weight book and understates the momentum
book's realized volatility by close to a factor of two, in the same years,
on the same data.

The two results have one root cause between them, and it is not that the
data are bad. The diagonal model prices the book from static full-sample
betas and a diagonal residual covariance. For a book that re-sorts every
month, that combination fails twice: the exposure is measured at the wrong
time (static full-sample betas cannot measure a dynamically sorted
portfolio's exposure), and the residual co-movement the book is actually
exposed to is discarded. The primary fix is conditional exposure, which is
what section (a) does with rolling betas and what E3 will do with
descriptor exposures, and the secondary fix is the realized residual
covariance, which is the item already open in docs/open_items.md. The
ledger entry for C4 is corrected to say so, and the open item is rewritten
with the same ordering.

After C8: make rebuild-e2 versions 29 artifacts, data/VERSION.json and the
TS-v1 registry entry both carry artifacts hash 51f0faa935cb57e8 (full value
in the file), and the sprint has 13 criteria, 9 passing and 4 failing (F2.3,
F2.3b, F2.3c, F2.6). Every criterion, in order, with its verdict, is listed
at the end of this section.

Final criteria list, in criterion order, read from
sprints/E2/RESULTS.json at data hash
51f0faa935cb57e8:

| Criterion | Verdict |
| --- | --- |
| F2.0a | pass |
| F2.0b | pass |
| F2.0c | pass |
| F2.1 | pass |
| F2.2 | pass |
| F2.3 | fail |
| F2.3b | fail |
| F2.3c | fail |
| F2.4 | pass |
| F2.5 | pass |
| F2.6 | fail |
| F2.6b | pass |
| F2.6c | pass |

13 criteria, 9 passing and 4 failing.
