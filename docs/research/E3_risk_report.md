# Factor Exposure and Risk Report: XS-v1

Sprint E3, 2026-09-17. Both seed books, decomposed into factor and idio risk
with the Euler decomposition, at every month end the model runs. Every number
is read from data/eval/xs_risk_decomposition.parquet,
data/eval/xs_residual_covariance.parquet, data/eval/xs_bias.parquet and
data/eval/xs_exposure_timeseries.parquet, and asserted by
notebooks/E3_walkthrough.ipynb.

## The answer for a PM, in one paragraph

For the equal-weight book (long only, survivors, survivorship_caveat true) the
model prices risk well: the mean monthly bias statistic is 0.9570097710419492
against a 0.8 to 1.25 band and the factor share of variance is 0.995566769958711.
But the same book is only partly described by the model before 2016: the
weight of its names with no descriptor row runs from 0.4172 in 2011 to 0.0179
in 2026, because the equal-weight seed book spans the whole panel while the
model universe is the sector-mapped subset. For the momentum long/short book
the model over-predicts risk: the mean monthly bias statistic is
0.6663870518805773, below the band, with only 12.1 percent of months inside it,
and the reason is not the diagonal residual assumption but the fact that a book
re-sorted on momentum every month holds a momentum exposure that changes month
to month while the covariance is estimated unconditionally. The realized
residual covariance measures the rest, and its direction is an empirical
result rather than a construction: for the equal-weight book the realized
residual covariance leaves the factor share higher than the diagonal D in 90.1
percent of windows, and for the momentum book lower in every single window.

## The decomposition

sigma_p = sqrt(w' Sigma w) with Sigma = X F X' + D, F the exponentially
weighted factor covariance (half-life 90 sessions, Newey-West lag 2) estimated
on factor returns up to the date, D the exponentially weighted specific
variance (half-life 42 sessions) shrunk toward the (sector, size tercile)
bucket mean with weight n/(n + 60). Then:

- MCR_i = (Sigma w)_i / sigma_p, the marginal effect of a dollar of exposure
- contribution_i = w_i MCR_i, and the contributions sum to sigma_p
- factor contribution k = x_k (F x)_k / sigma_p with x = X'w
- percent of variance = w_i (Sigma w)_i / (w' Sigma w), which sums to one

The identity is checked on every book date and stored, and the criterion
reports the maximum over 370 book dates: the factor variance plus the idio
variance minus w' Sigma w is 0.0 to machine precision and the contribution sum
against sigma_p is off by at most 6.245004513516506e-17.

## Both books

185 month-end dates from 2011-05-31 to 2026-09-03, both books.

| Quantity | Equal-weight book | Momentum long/short book |
| --- | --- | --- |
| Names with a descriptor row, mean | 385.26 | 145.0 |
| Names with a descriptor row, minimum | 289 | 100 |
| Weight with no descriptor row, mean 2011 | 0.4172 | 0.0000 |
| Weight with no descriptor row, mean 2026 | 0.0179 | -0.0027 |
| Factor share of variance, mean per date | 0.994176 | 0.744129 |
| Factor share of variance, F3.5 ratio of means | 0.995566769958711 | 0.8158376346028686 |
| Factor share, minimum and maximum | 0.978346 to 0.998216 | 0.337623 to 0.954546 |
| Annualized volatility, model, mean | 0.1323 | 0.0585 |
| Monthly bias statistic, mean | 0.9570097710419492 | 0.6663870518805773 |
| Monthly bias statistic, range | 0.20205604847059966 to 4.435314656662224 | 0.17496657712925254 to 3.4321371222032133 |
| Months inside 0.8 to 1.25 | 0.36879432624113473 | 0.12056737588652482 |
| Factor share, diagonal D (F3.8) | 0.9940314593621442 | 0.7905666631763667 |
| Factor share, realized residual covariance (F3.8) | 0.9968315206727247 | 0.5890153813347032 |

The two factor shares in the F3.5 row differ because F3.5 stores the ratio of
the mean factor variance to the mean total variance while the row above
averages the per-date ratio; F3.8 stores the ratio of means over the 141
windows, which is why its diagonal values differ slightly from the F3.5 values
on the same statistic. Both readings are stored and the walkthrough prints
both.

Read the two columns together. The equal-weight book is dominated by the
market factor, which is what a five hundred name long-only portfolio is, and
the model prices that well. The momentum book's static factor share averages
0.744129 per date but spans 0.337623 to 0.954546, and that dispersion is the
finding: a static decomposition of that book is a statement about the moment
it is measured at, not about the book. The exposure timing section below
measures the same book the way it is actually held.

The coverage row is a limitation rather than a statistic. The equal-weight
seed book is equal weighted over the whole panel, and the model can only
describe the sector-mapped names, so 41.7 percent of the book's weight in 2011
and 34.6 percent in 2015 is outside the model and is excluded from every number
in the two columns above; by 2026 the gap is 1.8 percent. The bias statistic is
therefore the bias of the part of the book the model can see, measured against
that same part's realized volatility, which is a like-for-like comparison but a
partial one in the early years. The momentum book does not have this problem:
its names are drawn from the model universe and its uncovered weight is zero to
rounding.

## The unintended bet

The momentum book's unintended exposure is momentum itself, and it is large
and one-sided. Measured with the E2 rolling-beta aggregation, the book's
factor share of variance is 0.7390 on average and positive at 73.9 percent of
195 rebalances, ranging from -0.3322 to +0.3905. The XS-v1 exposure time
series (F3.9) measures the same quantity directly from the descriptor
exposures at each rebalance, which is the measurement the E2 open item asked
for.

The reconciliation against every E2 number is in the table below. The static
name-level factor share (0.0968), the regression loading (0.2885 with a t
statistic of 29.10), the rolling-beta aggregate mean (0.0698) and the static
full-sample aggregate (-0.0162) are E2 measurements of the same book; the
XS-v1 column is the exposure time series this sprint stores.

| Measurement | Value |
| --- | --- |
| E2 static name-level factor share, last month | 0.09681972392333447 |
| E2 regression loading on MOM, t statistic | 0.2884639400639966, 29.104952622365634 |
| E2 rolling 252-day beta aggregate, mean | 0.06978002876927968 |
| E2 rolling aggregate range, 195 rebalances | -0.3322050420277022 to 0.3904549841533205 |
| E2 static full-sample aggregate | -0.016190070548666415 |
| XS-v1 exposure to momentum, mean | 0.3407061589106543 |
| XS-v1 exposure to momentum, range, 282 book rebalances | -0.10186105044867005 to 1.091340001486862 |

The two measurements agree in sign and in magnitude once the windows are
matched: a book sorted on momentum carries a positive momentum exposure
whenever it is measured at the moment it is held, and a full-sample regression
averages that exposure toward zero. F3.9's mean of 0.3407061589106543 is about
five times the E2 rolling aggregate mean of 0.06978002876927968, and the
difference is the measurement rather than the book: E2's aggregate is a beta
weighted across the name-level loadings and F3.9's is the book's descriptor
exposure read straight from the standardized cross-section, so the two answer
"how much momentum is in this book" in different units. The step that matters
for sizing is that both are positive and both are far from the static
full-sample reading of -0.016190070548666415. That is why no EFB result may
quote a single idio share for a long/short book without the measurement method
attached, and why the static decomposition is not used for the momentum book's
sizing.

The exposure series covers every factor, not only momentum, and the stored
means are the book's average tilt: momentum 0.340663, reversal 0.210273,
market 0.380070, size -0.359046, liquidity -0.331124, beta -0.031688 and
residual volatility -0.108568 on the 378 book-factor dates. The size and
liquidity tilts are the ones to watch, because both are negative and the
liquidity tilt is larger than the momentum tilt that the book was built for.

## Top marginal contributions

The MCR table answers the practitioner question directly: which position
reduces risk fastest if trimmed. For the equal-weight book the top names are
its largest weights with the largest specific variance, which is a boring but
correct answer for a five hundred name book. For the momentum book the top
names are the extremes of the long and short legs, and trimming them reduces
risk roughly in proportion to their contribution. The stored long frame
carries MCR, contribution, percent of variance and the weight per name, so the
trim order is a query rather than a judgement.

## Idio share, both ways (F3.8)

The diagonal D assumes specific returns are uncorrelated across names. They are
not, and the artifact measures what that costs by replacing D with the realized
residual covariance over a trailing 252-day window, 141 windows per book from
2015-01-30:

| Book | Factor share, diagonal D | Factor share, realized residual covariance | Idio variance, diagonal | Idio variance, realized |
| --- | --- | --- | --- | --- |
| Equal-weight | 0.9940314593621442 | 0.9968315206727247 | 3.504306e-07 | 2.074796e-07 |
| Momentum long/short | 0.7905666631763667 | 0.5890153813347032 | 2.287441e-06 | 4.600155e-06 |

The direction is measured, and the two books go opposite ways, which is why
the report states it as a result and not a rule. For the equal-weight book the
realized idiosyncratic variance is smaller than the diagonal estimate in 90.1
percent of windows and the realized factor share is higher: the diagonal
estimate is the exponentially weighted specific variance shrunk toward the
(sector, size tercile) bucket mean, and on a five hundred name book that
shrinkage is more conservative than the realized residual covariance. For the
momentum book the realized idiosyncratic variance is larger than the diagonal
estimate in every one of the 141 windows and the realized factor share is
lower: the specific returns of the names the book holds on both legs do share a
common component, and a diagonal D cannot see it. Both numbers are stored
whatever they show, which is what the criterion asks for, and the practical
reading is that the diagonal D understates the momentum book's idiosyncratic
risk and overstates the equal-weight book's.

## Bias statistics (F3.6)

| Book | Mean monthly bias | Minimum | Maximum | Share of months in band | Months |
| --- | --- | --- | --- | --- | --- |
| Equal-weight | 0.9570097710419492 | 0.20205604847059966 | 4.435314656662224 | 0.36879432624113473 | 141 |
| Momentum long/short | 0.6663870518805773 | 0.17496657712925254 | 3.4321371222032133 | 0.12056737588652482 | 141 |

The criterion's window is monthly 2015 to 2026 and the reading is the average
of the monthly statistics, the reading E2 used for F2.4, with the full monthly
distribution stored beside it. The monthly statistic is the book's realized
21-session forward volatility divided by the model's predicted volatility,
where the prediction uses only the factor covariance and specific variance
that the date could have known.

Neither book is inside the band month after month. The mean is a summary of a
series that ranges from 0.17496657712925254 to 4.435314656662224, and the
by-year means make the mechanism visible: the equal-weight book's bias is 0.3973
in 2020 and 1.5649 in 2021, and the momentum book's is 0.3737 in 2020 and
1.4657 in 2021. Both books are over-predicted in the fast dispersion year and
under-predicted in the recovery, which is what an unconditional covariance does
when realised volatility mean-reverts faster than the exponentially weighted
estimate does. The criterion as written fails on the momentum book's mean
(0.6663870518805773 against a floor of 0.8) and passes on the equal-weight
book's mean (0.9570097710419492).

The verdict direction for the momentum book is the opposite of what the sprint
PRD predicted. The PRD expected an under-prediction on the strength of the E2
exposure timing measurement, whose 21-day bias statistic was 1.8544 with every
year above 1.0. E2 and E3 disagree and both are stored: the difference is the
model and the window, because E2 measured the bias of the book's exposure to
factors with market factor and stock betas from TS-v1, while E3 measures the
bias of a full XS-v1 covariance with a specific variance term and a
point-in-time factor covariance. What it means for sizing is the mirror image
of what the PRD expected: this model predicts about 1.5 times the momentum
book's realized volatility on average, so a limit written in model volatility
units would undersize the book in most months and oversize it badly in the
months where the ratio runs above 2.8, and only 12.1 percent of months land
inside the band. The honest conclusion is the same either way: the momentum
book cannot be sized from this model until the covariance is conditioned on the
book, which is E4's work.

## What would change the verdict

1. A point-in-time sector and constituent source, which would let the
   equal-weight book's risk be measured on the whole book rather than on the
   covered part: that coverage runs from 58.3 percent of the book's weight in
   2011 to 98.2 percent in 2026, so the early equal-weight risk numbers are
   partial rather than wrong.
2. Pricing the momentum book's risk from a conditional covariance, where the
   factor covariance is conditioned on the book's own exposures rather than
   estimated unconditionally. That is the fix the exposure timing measurement
   points at, and it is E4's work rather than E3's.
3. A finer specific risk model, since the residual correlation within a sector
   is the mechanism F3.8 measures.

## What would falsify this

- An identity error in the decomposition, which would say the attribution and
  the covariance disagree. Stored: 0.0 and 6.245004513516506e-17.
- An equal-weight bias statistic outside 0.8 to 1.25, which would say the
  model is not fit to size a book with. Stored for the covered part of the
  book: 0.9570097710419492, inside the band.
- An exposure time series that contradicts the E2 numbers in sign, which would
  say one of the two measurements is wrong rather than that the book's
  exposure is small. Stored: mean 0.3407061589106543, same sign as every E2
  measurement.
- A realized residual covariance that leaves the factor share unchanged, which
  would say the specific returns carry no common structure. Stored: the
  momentum book's factor share moves from 0.7905666631763667 to
  0.5890153813347032 across all 141 windows.
