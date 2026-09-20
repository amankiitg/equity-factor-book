# Covariance Estimator Comparison and Residual Factor Audit

Sprint E4, 2026-09-20. Every number below is read from an artifact under `data/`.
The criteria table and the stored numbers behind each claim are in
`sprints/E4/RESULTS.json`; the probes are in `sprints/E4/PROBES.md`.

## The answer, in two sentences

The model understates the risk of a concentrated long/short book, because the
specific component is treated as diagonal while eleven of the momentum book's
residual directions are shared and the top five of them carry more than half of
the book's specific variance (largest residual eigenvalue 22.303 against an edge
of 3.952, 23 above it). Separately, and not as a caveat, everything the model
reports about size and liquidity is measured on a universe that excludes the
names those descriptors are about: the 323 excluded names are the small,
illiquid end of the cross-section, and dropping them correlates the size factor
return at 0.577780 between the two universes.

## Finding 1: the residual structure, which a diagonal cannot represent

XS-v1's specific returns are not idiosyncratic. A principal component analysis
of the correlation matrix of those specific returns, fitted on the same 504-day
window as the model, returns a largest eigenvalue of 22.303 against a
Marchenko-Pastur edge of 3.952, with 23 eigenvalues above the edge. Under the
null of no common structure the largest of roughly 500 would sit at the edge.

The consequence is measurable at the portfolio level rather than only in the
spectrum. Projecting the momentum book's own specific returns onto their
residual principal components, the top direction carries 0.226 to 0.255 of the
book's specific variance, the top three 0.441 to 0.466 and the top five 0.553 to
0.577, with about eleven effective directions across 151 names in the cross
section. The realized specific variance is 0.016155 to 0.017539 against a
diagonal estimate of 0.000002, which is not a small correction: the diagonal
number is a variance of the per-name residual, and the portfolio number is what
survives the covariance among them.

The factorization matters as much as the level. The realized covariance between
the book's factor component and its specific component is negative in the
high-exposure tercile (-1.039161e-06, correlation -0.091661) and positive in the
low one (1.290002e-06, correlation 0.052040), so the two components partly
offset where momentum exposure is highest. A covariance built as
`X S X' + D` cannot express that offset at all; it assumes the two terms are
independent. This is the through-line of the sprint, and it is why the E5
candidate is not a new descriptor list but a residual covariance.

The held-out test says the same thing from the other side. On 503 days after
2024-08-30, with sqrt(market cap) weights and exposures dated t-1:

| configuration | mean cross-sectional R squared |
| --- | --- |
| (i) XS-v1 refitted daily, as stored | 0.385727 |
| (ii) XS-v1 descriptors frozen | 0.253997 |
| (iii) PCA frozen, k at the MP edge | 0.271055 |
| (iii) PCA frozen, k = 17 | 0.305658 |
| (iv) PCA rolling refit | 0.313303 |
| (v) XS-v1 plus top 3 residual PCs | 0.292699 |
| (v) XS-v1 plus top 5 residual PCs | 0.312404 |

Adding three residual principal components to a frozen XS-v1 is worth 3.9
points of held-out R squared (0.253997 to 0.292699) without touching a single
descriptor, and five components are worth 5.8 points. The residual structure is
not a diagnostic curiosity; it is where the explanatory power is.

## Finding 2: the survivor restriction, which is a data problem

The XS-v1 universe is the 502 names with a sector mapping. The panel has 825.
The missing 323 names have no point-in-time sector source: no GICS history is
reachable, the SEC SIC route needs an issuer identity step the project does not
have, and the yfinance sector field describes the current holder of the symbol
rather than the company that was in the index (Task 0b, `sprints/E4/PROBES.md`).

This is a measurement, not a repair. Task 4a estimates one style-only model, the
market column plus six style descriptors and no sector dummies, twice over
identical dates: 189 month ends from 2011-01-31 to 2026-09-03.

| factor | correlation panel vs mapped | premium panel | premium mapped | t panel | t mapped |
| --- | --- | --- | --- | --- | --- |
| market | 0.997009 | 0.000201 | 0.000146 | 0.156 | 0.115 |
| size | 0.577780 | -0.000032 | -0.000173 | -0.074 | -0.578 |
| beta | 0.988961 | -0.000259 | -0.000255 | -0.457 | -0.468 |
| momentum | 0.982820 | 0.000309 | 0.000276 | 0.910 | 0.824 |
| reversal | 0.980173 | -0.000519 | -0.000466 | -1.770 | -1.732 |
| resid_vol | 0.893133 | 0.000102 | 0.000120 | 0.348 | 0.488 |
| liquidity | 0.625560 | -0.000012 | -0.000030 | -0.029 | -0.099 |

The restriction is concentrated in the two descriptors that are about the
missing names. Size and liquidity fall to 0.577780 and 0.625560 while market,
beta, momentum and reversal stay above 0.98. The 323 excluded names are the
small, illiquid, failed end of the cross-section, so removing them truncates the
dispersion those descriptors are built to measure. The size premium deepens from
-0.000032 to -0.000173 and its t statistic from -0.074 to -0.578, mean
cross-sectional R squared rises from 0.133530 to 0.142526, and mean specific
variance falls from 2.9172148211e-04 to 2.2854110873e-04.

The excluded names differ in the way that matters, over 2010 to 2016 when they
were still a large share of the index: 0.199281 annualized volatility against
0.166796 for the included names, 0.360978 mean cross-sectional volatility
against 0.275396, and 0.020141 a year less in annualized return.

Stated plainly: XS-v1's premia, its R squared and its specific variance are all
flattered by the restriction, and every E4 and E5 number computed on the mapped
universe carries it. This is the difference between the two findings. The
residual structure is a model specification problem that XS-v2 can fix. The
restriction is a data problem that no model can fix and that only a
point-in-time source would close.

## The covariance horse race

Nine estimators, 175 rolling 504-day windows, each applied to the next 21
sessions with no re-estimation, scored by realized minimum-variance portfolio
volatility. Read in medians and win counts, because the mean is a tail
statistic here.

| estimator | median realized vol | windows won | median condition number | fitted quantities | median ratio to sample |
| --- | --- | --- | --- | --- | --- |
| clip | 0.086042 | 24 | 1239.68 | 475 | 0.327858 |
| pca_v1 | 0.086674 | 33 | 3062.06 | 476 | 0.330506 |
| pca_v1c | 0.087318 | 29 | 1928.59 | 477 | 0.342014 |
| xs_v1 | 0.088007 | 59 | 2716.33 | 484 | 0.323037 |
| ledoit_wolf | 0.094102 | 27 | 2784.87 | 2 | 0.341831 |
| ts_v1 | 0.150948 | 3 | 1296.09 | 932 | 0.560764 |
| constant_correlation | 0.160254 | 0 | 921.05 | 467 | 0.601425 |
| sample | 0.280404 | 0 | 2650148 | 108811 | 1.000000 |
| ewma | 0.298494 | 0 | 16580780 | 108811 | 1.056944 |

`fitted quantities` is the median count of free quantities the estimator
estimates for the window: one for Ledoit-Wolf, two for the constant-correlation
target and its intensity, and the full symmetric matrix (N(N+1)/2, 108811 at 466
names) for the sample covariance and EWMA. Ledoit-Wolf's median shrinkage
intensity is 0.197345.

The sample covariance won no window and its median is 3.05 times the best
estimator's (ratio 1.000000 against clip's 0.327858), which is the estimation-error result the theory predicts at N/T
near one: with 494 names and 504 days, an optimizer given the sample covariance
buys the noise directions. EWMA is worse than the sample covariance, the
clearest sign that a covariance estimator has to be structured rather than
merely down-weighted, and the reason is arithmetic rather than tuning: a
half-life of 63 days implies an effective sample size of 181.78 days against a
median 466 names on those windows, so the EWMA matrix is estimated from 39.0
percent of the observations its dimension requires and is rank deficient by
construction (notebook section 8). TS-v1 is the weakest of the factor models, at 0.150948
with three windows won, which is consistent with a six-factor model fitted to a
short window.

One sentence on the mean, which is what a vendor table usually shows: the mean
ranking reorders the top four by about a tenth of a percentage point while the
membership of that top four is unchanged.

Recommendation per use:

- **Optimizer.** XS-v1 is the default, on win count: 59 of 175 windows, the most
  of any estimator, and its median is within 2.3 percent of the best. Clip and
  PCA-v1 have lower medians but win fewer windows, which is what a PM should
  expect from an estimator whose advantage is concentrated in the tail windows.
  Whatever is chosen, the sample covariance must not be, and EWMA is worse.
- **Hedging.** PCA-v1 and PCA-v1c are not usable. Their components are
  statistical and their signs are indeterminate across windows; a hedge built on
  a factor that can flip sign is not a hedge. XS-v1's named factors are the only
  ones a desk can be told to hedge with.
- **Risk reporting.** Report the condition number beside every number: the
  constant-correlation matrix at 921.05 and the sample at 2650148 describe the
  same universe, and EWMA at 16580780 is the worst-conditioned matrix in the
  race. For specific risk, report the residual-structure caveat of Finding 1
  with the number: the diagonal understates a concentrated book.

## The criteria

| ID | criterion | threshold | stored number | verdict |
| --- | --- | --- | --- | --- |
| F4.1 | First principal component vs the market factor | correlation above 0.95 | PCA-v1 0.797019, PCA-v1c 0.930599 | fail |
| F4.2 | Marchenko-Pastur edge isolates between 3 and 15 significant factors | 3 to 15, STOP CONDITION 3 | 13 (scree 2, CV 12) | pass |
| F4.3 | OOS minimum-variance vol: shrinkage and factor estimators beat the sample by more than 10% | every ratio 0.90 or below | worst ratio 0.5715 | pass |
| F4.4 | PCA-v1 explains at least as much held-out cross-sectional variance as XS-v1 | PCA rolling at or above XS daily | 0.313303 against 0.385727 | fail |
| F4.5 | Task 3's four measurements, explanation named | 3a, 3b, 3c, 3d present | momentum share 0.319808 to 0.561267 | pass |
| F4.6 | Task 4's three measurements stored | 4a, 4b, 4c present | size correlation 0.577780 | pass |
| F4.7 | Registered 2026-09-20: PCA-v1c measured on its own terms | both PC1 objects measured and named | 16 above the covariance edge | pass |

F4.1's threshold was written for an estimator the sprint did not end up
specifying. It asks for the first principal component against the market, and
the sprint built two PC1s, neither of which is a market portfolio: the
correlation PCA's first component correlates 0.989144 with the equal-weight mean
and 0.797019 with the market, and the covariance PCA's correlates 0.930599 with
the market and 0.943251 with the equal weight. The market factor itself
correlates 0.855646 with the equal-weight mean over the same 504 days, and the
full-sample correlation of the first component with the market is 0.945035. No
PC1 of either kind had a correlation above 0.95 available to it. A third PCA was
deliberately not built to chase the threshold. The conflict is recorded in the
hygiene ledger; the criterion is not reworded.

F4.4 fails by 7.2 points on the comparison it names, and that is the honest
reading of it: PCA loses to a daily-refitted XS-v1. The row that matters is (v),
which is the finding of the memo rather than a defence of PCA.

Both PCA counts appear in this document, and they are different objects. F4.2
governs the correlation PCA's 13 factors on the model universe (494 names, 504
days, N/T 0.9802, edge 3.9602, inside the registered 3 to 15 band); the panel
universe puts 14 above its own edge. PCA-v1c's 16 is the count above a
covariance spectrum's edge, which is a different matrix in different units, and
it is stored under F4.7 and never scored against F4.2's band.

## The period confound, quoted wherever the tercile result appears

Momentum's share of the book's predicted variance rises with exposure, from
0.319808 in the low tercile to 0.465699 in the middle and 0.561267 in the high,
while styles hold 0.758281 to 0.806952 and the residual share falls from 0.241614
to 0.192166. Read alone that is a story about concentration.

It is partly a calendar effect. The high-exposure tercile sits in months whose
forward market volatility is 0.168191 against 0.219286 in the low tercile, and
membership clusters in 2024 and in 2016 and 2022. The book's own realized
volatility falls from 0.049093 in the low tercile to 0.030110 and then 0.027775
against a predicted volatility that is flat at 0.054010, 0.057698 and 0.054729,
so the momentum book's realized-to-predicted bias falls from 0.8960 to 0.5841
and 0.5191: the model is at its worst for the book it is most exposed to.

The finding survives the confound. The book's realized volatility falls 43.4
percent across terciles against a 23.3 percent difference in the market's own
forward volatility, and the covariance-form reading of the same book rises
slightly, from 0.059045 to 0.064068. The half-life sweep is the test of whether
this is a calibration problem with a knob: at 21, 42 and 90 days the
high-tercile bias reads 0.521876, 0.520948 and 0.524749, a total movement of
0.003. The half-life is measured and rejected as the explanation; a reader
should not retry it.

## Seven carry-throughs

1. **Medians and win counts, never means, in every horse-race table.** The mean
   reorders the top four by about a tenth of a percentage point without changing
   membership, and it hides the tail that decides an optimizer's drawdown.
2. **The realized-volatility definition collision.** The stored F3.6 definition
   of the momentum book's realized volatility (0.027775 in the high tercile) is
   authoritative; the covariance form (0.064068) is kept as a labelled column
   beside it. Two definitions of one phrase, recorded rather than reconciled.
3. **The period confound**, quoted in full in the section above wherever the
   tercile number appears.
4. **The E3 open item on the momentum bias**, restated with the Task 3 verdict
   and the half-life sweep recorded as measured and rejected at 0.003. E3 ordered
   a conditional exposure fix first and a residual covariance second; Task 3
   reverses that order, and the reversal is the sprint's main finding.
5. **The F4.1 specification conflict**, above.
6. **The two swallowed-error defects**: Ledoit-Wolf's missing `1/T`, which made
   the shrinkage intensity clip at exactly 1.0 in all 175 windows and collapsed
   the estimator onto its constant-correlation target, and the bare `except`
   around the estimator dispatch, which dropped PCA-v1c from the race and printed
   a well-formed eight-row table.
7. **The withdrawn stop threshold** from Task 4: a hand-written guard, withdrawn
   with its reason in `docs/hygiene_ledger.md`, never registered as a criterion
   and not scored in `RESULTS.json`.

## What XS-v1 is missing, and the E5 candidates

XS-v1 is missing a covariance for its specific returns, and it is missing the
325-ish names whose sectors nobody can date. The first is fixable in a sprint;
the second is a data purchase or a research project of its own.

E5 candidates, from the registry (`data/models/registry.json`, all four entries
`champion: false`; the champion rule is unchanged and no E5 champion is implied
here):

- **XS-v2, XS-v1 with a residual covariance.** Adding three residual principal
  components to a frozen XS-v1 is worth 3.9 points of held-out R squared, and the
  residual spectrum says the structure is real at 22.303 against an edge of
  3.952. This is the recommendation.
- **XS-v1**, the incumbent, eligible, and the best win count in the race at 59 of
  175 windows.
- **PCA-v1 and PCA-v1c**, eligible, kept for the covariance they provide to the
  optimizer and excluded from hedging.
- **TS-v1**, not eligible: 0.150948 median and three windows won.

## What would falsify this?

- **The residual covariance is a window artefact.** Refit the residual spectrum
  on non-overlapping 504-day windows and on the panel universe; if the largest
  eigenvalue falls to its edge, Finding 1 is a property of one window and XS-v2
  should not be built. (The panel universe already reads 14 above edge, so this
  test has a live chance of passing for the wrong reason and must be read on the
  eigenvalue, not the count.)
- **The held-out gain disappears out of sample in time.** Run (v) on a second
  held-out period and on a different portfolio family, not only the momentum
  book. If the 3.9 points are specific to 2024-08-30 onward, the E5 candidate is
  a period.
- **The survivor restriction is a descriptor problem rather than a universe
  problem.** If the excluded names can be assigned a sector and the size
  correlation between the universes does not move back towards the other styles,
  then the restriction is in the descriptors, not in who is missing.
- **The sample covariance wins a rebuild.** That would be an estimation bug
  before it was a result.
- **EWMA beating the structured estimators on win counts.** Nine estimators and
  no wins for EWMA is the expected shape; a reversal would point at a defect in
  the structure.

## Closing: one habit, three entries

Three of this sprint's hygiene entries are the same failure. Ledoit-Wolf
collapsed onto its own target because the intensity clipped at 1.0 in every
window. The horse race printed eight rows because a bare `except` swallowed the
error raised by the ninth estimator. The survivor comparison printed two
identical universes because the function that fitted them never received the
universe. In each case the output was well formed and every number in it was
plausible, and in each case the reason the reader trusted it was the same: it
looked finished.

The check that catches all three is not a better review of the code. It is that
every comparison stores the sample size it was computed on, and that two things
claimed to differ must be shown to differ before their difference is
interpreted. The first Task 4 table failed that test the moment anyone asked how
many names were in each fit; the Ledoit-Wolf row failed it the moment anyone
asked what the intensity was; the horse race failed it the moment anyone counted
the rows. That is now a property of the artifacts rather than of the reader's
attention, which is the only version of this lesson that survives a busy week.
