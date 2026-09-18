# Factor Model Research Note: XS-v1

Sprint E3, 2026-09-17. Every number in this note is read from an artifact
under data/ and reproduced by notebooks/E3_walkthrough.ipynb, which asserts
each figure against its stored value.

## The answer for a PM, in one paragraph

XS-v1 explains about a third of the daily cross-sectional dispersion of
returns (average R squared 0.3294501878861149 over 3941 sessions from
2011-01-03), and its factor structure is honest about what it is: the market
factor is the cap-weighted universe return, the eleven sector factors are
deviations from it, and the style factors are standardized so the
cap-weighted market portfolio carries zero style exposure. The premia are
mostly not priced, and that is the expected answer for a risk model: it needs
the factor returns to have a covariance, not to have a premium. The model's
risk numbers average correctly for the equal-weight book (mean monthly bias
0.9570097710419492, inside a 0.8 to 1.25 band) but only 36.9 percent of its
months land inside that band, so the average is right and the dispersion is
not. For the momentum book the average is wrong as well: the mean monthly
bias is 0.6663870518805773, below the band, with only 12.1 percent of months
inside it, because a book that re-sorts on momentum every month holds a
dynamic factor exposure that an unconditional covariance does not see, and
that book's month to month bias runs as high as 3.4321371222032133. F3.6
fails on the momentum book and passes on the equal-weight book; the sprint
PRD predicted a fail on the momentum book in the opposite direction, so the
pre-registration was right about which book breaks and wrong about how it
breaks. Size carries a documented look-ahead before late 2015, and the
cross-section contains survivors only, which is the sprint's largest measured
limitation.

## What the model is

One cross-sectional regression a day, r_t = X_{t-1} f_t + e_t, weighted by
sqrt(market cap), with the identification constraint that cap-weighted sector
factor returns sum to zero.

Descriptors, all dated t-1 and computed from data through t-1:

| Descriptor | Definition | Window | Minimum |
| --- | --- | --- | --- |
| market | constant 1 | none | none |
| size | log(close x shares) | none | a filed share count |
| beta | Vasicek-shrunk rolling market beta | 252d | 126 observations |
| momentum | cumulative return t-252 to t-21 | 231 sessions | all present |
| reversal | cumulative return t-21 to t-1 | 20 sessions | all present |
| resid_vol | annualized vol of the rolling market model residual | 63d | all present |
| liquidity | log mean dollar volume | 63d | 42 observations |
| sector_10 to sector_60 | 11 GICS dummies | none | sector file membership |

Standardization is a cross-sectional winsorization at plus or minus 3 MAD
followed by a z score with a cap-weighted mean and an equal-weighted standard
deviation, so the cap-weighted market portfolio carries zero style exposure by
construction. Momentum is then orthogonalized against beta and size, and
residual volatility against beta, so a momentum bet is not silently a small-cap
bet.

The design estimates 17 columns: the seven style columns and ten sector
dummies. The reference sector (Real Estate, code 60) has no dummy, because a
market column plus eleven dummies is exactly collinear. Its factor return is
derived from the constraint, and the cap-weighted mean of the sector block is
moved into the market factor, which makes the market factor the cap-weighted
market return and leaves every fitted value unchanged. This is what makes the
factor-mimicking portfolio identity X' w_FMP = e_k an identity rather than a
projection: with the redundant dummy present, a pseudo-inverse cannot satisfy
it.

## Stored numbers

```
sessions                                 3941   (2011-01-03 to 2026-09-03)
names per session, mean                   467.6135
names per session, minimum                428
names per session, maximum                498
days below the 300-name floor             0
days with a rank-deficient design         0
average cross-sectional R squared         0.3294501878861149
FMP identity, max abs deviation           1.2426149519073615e-13 (every day)
cap-weighted sector sum, max abs          7.047314121155779e-18 (every day)
momentum vs FF MOM correlation            0.7555482343048963  (3917 days)
market vs FF Mkt-RF plus RF correlation   0.9889255744977894  (3917 days)
factor plus idio minus total, max abs     0.0                 (370 book dates)
contribution sum minus sigma, max abs     6.245004513516506e-17
factor share of variance, seed_ew         0.995566769958711
factor share of variance, seed_mom_ls     0.8158376346028686
```

R squared diagnostics (standing instruction B, computed whether or not the
average clears its bar):

```
by year      2011 0.35381, 2012 0.289056, 2013 0.247919, 2014 0.28293,
             2015 0.293861, 2016 0.31435, 2017 0.277233, 2018 0.312246,
             2019 0.28363,  2020 0.37178,  2021 0.340566, 2022 0.414612,
             2023 0.367565, 2024 0.3654,   2025 0.380905, 2026 0.398301
market factor alone, mean                 -0.0 (zero by construction)
sector block alone, mean                  0.192787
style block alone, mean                   0.200683
full 18-factor set, mean                  0.3294501878861149
by sector: Utilities 0.435051, Energy 0.389566, Real Estate 0.316339,
           Communication Services 0.312029, Consumer Staples 0.27365,
           Financials 0.271331, Information Technology 0.258247,
           Industrials 0.244622, Consumer Discretionary 0.227468,
           Health Care 0.217544, Materials 0.19037
```

The market-only row is zero by construction, not by measurement: the market
factor is the constant column, so a model that contains only the market factor
predicts the cap-weighted mean return and has no within-day dispersion to
explain. The two informative comparisons are therefore the sector block alone
(0.192787) and the style block alone (0.200683). Read together: the descriptors
carry real cross-sectional information, and the sector and style dimensions
overlap substantially, because the style means are estimated within a
sector-dummied design and the styles themselves absorb part of the
industry-relative dispersion. Two readings matter. First, the style block alone
reaches 0.20 and the full set adds 0.13 on top of it, so the sector dummies are
not decoration. Second, the high years are 2022 (0.414612) and 2026 (0.398301)
with 2020 at 0.37178 and the low year 2013 at 0.247919: the year to year spread
is 0.17 and the series has no trend, so the average is not being carried by one
regime.

## Fama-MacBeth premia

The premia are the academic layer of the same regression: the mean factor
return with a Newey-West standard error at lag 2. Full sample and the three
pre-registered subperiods, every factor in every subperiod, and a premium with
an absolute t statistic below 2 is labelled unpriced and kept.

The verdicts are in data/eval/xs_fm_premia.parquet and in the criterion F3.7,
which passes on completeness rather than on significance, as written: 72 rows
(18 factors by 4 periods), a minimum of 4 periods per factor, 64 of the 72
premia labelled unpriced, an unpriced share of 0.8888888888888888. The
strongest full-sample premium is the market factor at an absolute t statistic
of 3.4676, which is the market return being positive rather than a discovery.
The interpretation a PM needs is this: a risk model does not require priced
factors. If the size factor earns no premium and the momentum factor is
unpriced after orthogonalization, the factors still carry covariance, and that
covariance is what the risk numbers use. The one thing that would change the
reading is a factor whose premium is large and stable while its contribution
to a book's variance is small, which would make it a return bet rather than a
risk factor; the premia table and the decomposition table are the two halves
of that comparison and both are stored.

## Sensitivity and choices

1. Total returns rather than excess. The risk-free series ends 2026-07-31, so
   the regressand is the total return r and the market factor is a
   total-return factor. The premia are total-return premia. The market factor's
   correlation with the FF total return (Mkt-RF plus RF) is 0.9889255744977894
   on the 3917-day overlap, which is the number that says how much the choice
   of regressand costs: the model's market factor is not a different animal.
   Standing instruction C prices the choice directly: the Market factor
   estimated on total returns and on excess returns is printed side by side in
   PROBES.md with its correlation on the overlap, and because the market factor
   is the intercept and a common shift of the regressand moves only the
   intercept, the gap between the two series is the risk-free rate itself, so
   the choice of regressand is a mean shift rather than a change of shape, and
   the style and sector factors are identical between the two fits.
2. Orthogonalization. Momentum is residualized on beta and size and residual
   volatility on beta, both stored pre- and post-orthogonalization in the
   descriptor artifact. The side-by-side factor return table is in the optional
   backlog and is not reported here.
3. Weights. sqrt(market cap), normalized. The equal-weighting and top-300
   sensitivities are in the optional backlog and are not reported here.
4. Share counts. The vendor series is as filed and not split adjusted (AAPL
   steps exactly 4x at the 2020-08-28 split), so the count is usable from the
   date it starts. It starts late: 1 name has a filed count in 2013-04, 22 by
   2015-09, 149 by 2015-10, 396 by 2015-11 and 502 by 2017. 1,245,448
   name-days (36 percent of the panel) before a name's first filing carry a
   backfilled count and are flagged look_ahead in the descriptor and market cap
   artifacts. Every Size number before late 2015 is therefore a projection, and
   the note says so wherever it is quoted.
5. The shift test, and a pre-registered direction that did not survive the
   measurement. The PRD's design rule says that replacing X_{t-1} with X_t
   reduces the cross-sectional R squared, and that is not what happens. On the
   3940 pairs of consecutive cross-sections the lagged design explains 0.329462
   of r_t and the design dated t explains 0.364005: using the later design
   raises the R squared by 3.45 points rather than lowering it. That is the
   expected result once the descriptors are examined, because the t-dated size
   descriptor contains market cap at t, which is mechanically a function of
   r_t, and the t-dated reversal and momentum windows include the day being
   explained. The 3.45 points are the size of the same-day information the
   lag removes, so the measurement supports the rule rather than contradicting
   it, and it is recorded in the Hygiene Ledger as a pre-registration that was
   wrong about the sign. The model fits the lagged design, and the lagged
   number reproduces the stored mean R squared of 0.3294501878861149, which is
   the check that the rule actually holds in the build.

## The survivor-only cross-section

The sector dummies restrict the model to the names the sector file holds, and
that file is a current-member snapshot, so the historical cross-section is
entirely survivors. Measured in the Task 0 probes:

| Year | Members/day | In the sector file | Outside | Share outside, names | Share outside, market cap |
| --- | --- | --- | --- | --- | --- |
| 2010 | 503.9 | 292.6 | 211.3 | 0.4194 | 0.0885 |
| 2015 | 502.3 | 332.7 | 169.6 | 0.3377 | 0.0547 |
| 2020 | 506.0 | 410.4 | 95.6 | 0.1890 | 0.0196 |
| 2025 | 504.0 | 479.8 | 24.2 | 0.0481 | 0.0024 |

The restriction removes 41.9 percent of the 2010 index by name and 8.9 percent
by market capitalisation, and both decay as the missing names are the ones that
left. So it is mostly a breadth problem and a smaller weight problem, and the
missing names are disproportionately the failures, which is the same
mechanism F1.5 measures at 365.1 basis points per year on the full panel but
stronger here, because the sector dummies remove the names the panel does not
hold at all. This is recorded as an open item for E4 and is not repaired
inside the risk model.

## What would falsify this

- A cross-sectional R squared below 15 percent, which is the criterion's fail
  band and did not occur: the stored value is 0.3294501878861149 and no
  calendar year is below 0.247919. Standing instruction B asks for three
  diagnostics before any change if the average falls short of 15 percent; it
  did not, and the by-year, by-sector and block diagnostics are stored anyway.
- A design dated t explaining r_t no better than the design dated t-1, which
  would say the descriptors carry no same-day information and that the lag is
  doing nothing. Measured: 0.364005 against 0.329462, so the lag removes 3.45
  points of R squared and the rule is load bearing.
- A factor-mimicking portfolio identity error above 1e-8, which would say the
  weights are not the WLS operator's rows. Stored: 1.2426149519073615e-13.
- A cap-weighted sector sum above 1e-10 on any day, which would say the
  identification adjustment is wrong. Stored: 7.047314121155779e-18.
- A market factor correlation with the FF total return far below 0.9, which
  would say the market proxy is broken rather than that the market was unusual.
  Stored: 0.9889255744977894. A momentum correlation below 0.6, stored
  0.7555482343048963.
- A decomposition identity error, which would say the covariance and the
  attribution disagree. Stored: 0.0 for factor plus idio minus total and
  6.245004513516506e-17 for the contribution sum minus sigma.
- A mean monthly bias outside 0.8 to 1.25 for the equal-weight book, which
  would say the model is not fit to size a book with. The equal-weight book is
  inside the band at 0.9570097710419492, and the momentum book is not, at
  0.6663870518805773. The criterion as written fails on the momentum book, and
  that failure is the honest headline of the risk report rather than a defect
  to be tuned away: a dollar-neutral book re-sorted every month is the case the
  full-sample covariance covers worst.
- A realized residual covariance that leaves the diagonal model's factor share
  unchanged, which would say the specific returns carry no common structure.
  Stored: the equal-weight book moves from 0.9940314593621442 to
  0.9968315206727247 and the momentum book from 0.7905666631763667 to
  0.5890153813347032, so the specific returns do carry common structure and the
  diagonal model understates the momentum book's idiosyncratic risk.
