# Sprint E4 PRD: Statistical Factor Models and the Covariance Lab

Sprint E4 of the Equity Factor Book, 2026-09-20. Tier 2, Mon Sep 21 to Sun Sep
27 in the roadmap. No em dashes in any file. Every number in this PRD is read
from a stored artifact or from `sprints/E4/PROBES.md`.

## Objective

Add statistical factor models as the third model family, build a covariance
laboratory that compares estimators on the same universe, register PCA-v1,
formalize the registry with a champion flag and a dashboard version selector,
and settle the two open items E3 handed over. The sprint ends with dashboard
tab D3.

No champion is declared in this sprint. The champion flag is built here and the
decision is E5's. The champion rule in `data/models/registry.json` is not
edited in this sprint.

## Research questions, copied verbatim from the roadmap

- Academic question: How many common factors are in equity returns, and how
  should a large covariance matrix be estimated when N is comparable to T?
- Practitioner question: Which covariance estimator gives portfolios that
  behave out of sample the way the estimator predicted?
- Research question: Do statistical factors capture risk the fundamental model
  misses, and does a blended model beat either alone?
- Research deliverable: `docs/research/E4_covariance_memo.md`, the Covariance
  Estimator Comparison and Residual Factor Audit, written for a senior quant or
  risk manager: the PM answer in one paragraph at the top, the horse-race table
  with a recommendation per use (optimizer, hedging, risk reporting), the
  residual factor audit saying what if anything XS-v1 is missing, the task 3
  verdict on where the momentum book's miss lives, the task 4 number on the
  survivor distortion, which versions are candidates for E5, and a section
  titled "What would falsify this?".

## Inherited constraints, all hard

1. MODEL_START is 2011-01-03 for the cross-section. The panel is the
   post-exclusion returns file. Stale, outlier and interior-NaN rows are
   excluded from every window and the counts are printed. The stored counts are
   6,179 stale rows, 62 outlier rows and 302 interior NaN rows in the panel.
2. XS-v1 is the incumbent fundamental model, champion false,
   eligible_for_champion true. TS-v1 is diagnostic only, eligible false. The
   champion rule is not edited and no champion is declared here.
3. The production volatility estimator is EWMA(0.97). F2.3, F2.3b and F2.3c are
   closed.
4. The regressand is the total return, because the risk-free series ends
   2026-07-31. The two-way measurement is stored in `sprints/E3/PROBES.md`.
5. Size and the sqrt(mcap) weights carry a documented look-ahead before
   2015-10-23.
6. A stored criterion is never reworded. F4.1 to F4.4 are copied verbatim. New
   findings take new IDs, F4.5 and F4.6.
7. No number in any walkthrough is typed by hand.

## Task 0, completed and accepted

The probe record is `sprints/E4/PROBES.md`, the code is in `efb/probes.py` and
the tests are in `tests/test_e4_probes.py`. The three results this sprint is
built on:

1. Eigenvalue feasibility. The model universe holds a median of 473 names and
   the panel 584, over 3,941 sessions. At T = 504 that is N/T 0.938 and an MP
   edge of 3.876 in the model universe, and N/T 1.159 with an edge of 4.312 in
   the panel. The lab runs at T = 504 and every factor count is quoted against
   the edge for its own N and T.
2. Sector sources. No point-in-time GICS sector source is reachable. The
   changes table dates membership and names the issuer; EDGAR returns an
   issuer-level SIC code for 4 of 10 delisted names with dated filings, behind
   an issuer-identity step the project does not have; the Wikipedia REST
   summary is prose, not a taxonomy, and was rate limited on the run; the
   yfinance sector field answered for 4 of 10 and in every case described the
   current holder of the symbol, which would re-inject the reused-symbol
   contamination F2.6 removed. The survivor restriction stays open.
3. The tercile diagnostic. The momentum factor's own forward 21-day realized
   volatility rises monotonically with the book's exposure, 0.044215 in the low
   tercile to 0.053178 in the high one, while the book's own realized
   volatility falls from 0.047864 to 0.029207 and the model's predicted
   volatility moves 0.003656 (max minus min) or 0.003440 (low to high). The
   earlier 0.0055 figure was wrong and is carried nowhere. The quiet-factor
   explanation is refuted by the measurement.

## Correction 2: Task 4's window rule

The Task 4 window rule in the first brief, "years where the sector-mapped share
is above 90 percent by market cap", is withdrawn because it selects every year:
2010 is already 91.1 percent inside by market cap, and the share outside by
name only falls below 10 percent in 2024 to 2026, which is too short to
re-estimate on. Task 4 is specified below as a same-period design.

## Task 1: statistical factor models (PCA-v1)

PCA on total returns and on the XS-v1 specific returns, both at T = 504.

Method. Standardize each name's returns over the window to unit variance, so
the eigendecomposition is of a correlation matrix and the MP edge applies to
it. Eigendecomposition via SVD of the standardized matrix `Z = U S V'`, with
`S` the covariance, eigenvalues `lambda_i = s_i^2 / T`, loadings `V` and factor
returns `U S / sqrt(T)`, scaled so a factor return is the return of a
unit-exposure portfolio. The k-factor model is
`Sigma_k = V_k Lambda_k V_k' + diag(residual variance)`, with the residual
variance from the discarded eigenvalues and the diagonal of the sample matrix.

Factor count, three ways, all stored:
- Scree: the last k before the eigenvalue decline flattens, by the largest
  ratio gap in the sorted spectrum.
- Marchenko-Pastur: the count of eigenvalues above
  `(1 + sqrt(N/T))^2` computed from the same N and T the window actually used.
- Cross-validated likelihood: split the window into a training block and a
  held-out block, fit k factors on the training block, and score the held-out
  Gaussian log-likelihood under `Sigma_k`; the selected k maximizes the
  held-out score.

Rotation. Varimax on the loadings, so the factors can be named, and a
correlation matrix between rotated PCA factors and the XS-v1 factors, so the
reader can see which fundamental factor each statistical factor resembles.

Residual PCA as a missing-factor detector. The same procedure on the XS-v1
specific returns. If the largest specific-return eigenvalue sits above its own
MP edge, XS-v1 is missing a factor common to its residuals, which is a finding
and not a failure of the criterion.

Registration. `data/models/PCA-v1/{loadings,factor_returns,eigenvalues}.parquet`
and a registry entry with the parameters the run used: window, the three
counts, N/T, the MP edge, the rotation and the data hash.

## Task 2: the covariance laboratory

`efb/cov.py` carries the estimators, each returning a matrix with a stated
parameter count and condition number:

| Estimator | Definition | Parameters |
| --- | --- | --- |
| sample | `S = (1/T) R'R` on the window returns | N(N+1)/2 |
| ewma | exponentially weighted, half-life 63, EWMA(0.97)-consistent decay for the volatility scaling | N(N+1)/2 + 1 |
| ledoit_wolf | `delta F + (1 - delta) S` with `F` the constant-correlation target and `delta` the Ledoit-Wolf intensity estimated from the data | 2 + 1 |
| constant_correlation | a single average correlation with the sample variances | N + 1 |
| clip | eigenvalues below the MP edge replaced by their mean, above kept | k + N |
| ts_v1 | `beta beta' var_market + diag(specific)` from the TS-v1 market model | 2N |
| xs_v1 | `X F X' + D` from the XS-v1 factor covariance and specific variance | 18 factors |
| pca_v1 | `V_k Lambda_k V_k' + diag(residual)` from Task 1 | k + N |

Test. The out-of-sample minimum-variance portfolio:
`w = Sigma^-1 1 / (1' Sigma^-1 1)`, weights built on a 504-day window and
applied to the next 21 sessions with no re-estimation, realized volatility by
estimator, rolling. Reported for each estimator: mean and median realized
volatility, the ratio to the sample covariance, the condition number and the
parameter count. F4.3 requires shrinkage and factor estimators to beat the
sample covariance by more than 10 percent.

STOP CONDITION 2. If the sample covariance wins the out-of-sample
minimum-variance test, that is an estimation bug, because with N near T theory
says it cannot, and the sprint does not continue past it. The table is printed
and the sprint stops.

## Task 3, reframed: where the momentum book's miss lives

Explanation (ii) is refuted and recorded: the factor's own forward volatility
rises with exposure, so it was not quiet in the high-exposure months. The probe
sharpened the question, and the arithmetic that follows is the reason the
section is ordered as it is. Exposure rises about 55 percent from the low to
the high tercile and the factor's own forward volatility about 20 percent, so
the momentum contribution to predicted variance should be roughly 3.5 times
larger in the high tercile, while predicted total variance moves about 1.13
times. Backing out the implied share puts momentum at roughly 5 percent of
predicted variance in the low tercile. If that arithmetic is right, the
prediction is flat because momentum is a small slice of what the model
predicts, and no half-life can fix a 5 percent slice.

Four measurements, in this order, all on stored artifacts, with no estimator
change to XS-v1:

- 3a. Decompose predicted variance by source within each tercile: the momentum
  factor contribution, each other factor's contribution, and idio. This is the
  direct answer to why the prediction is flat. It either confirms the 5 percent
  estimate or shows the arithmetic is wrong; the deliverable reports which,
  with the numbers.
- 3b. The confound check, before anything else is interpreted. Tercile
  membership by calendar year and the market factor's realized volatility
  within each tercile. If high-exposure months cluster in calm periods, the
  falling realized book volatility is a period effect rather than an exposure
  effect, and the whole tercile reading changes. The deliverable says
  explicitly which it is.
- 3c. The orthogonality test. The model assumes the book's factor component and
  its specific component are uncorrelated, so the predicted variance is their
  sum. Compute the realized covariance between `x'f` and `w'e` for this book,
  overall and by tercile. The motivating arithmetic: realized total volatility
  in the high tercile is 0.029207 while the predicted factor component alone is
  about 0.052 using the F3.8 diagonal factor share of 0.7906. Realized total
  below the predicted factor part alone cannot happen under orthogonality, so
  either that covariance is materially negative or the factor part is badly
  overstated. The deliverable prints which, with the number.
- 3d. The half-life sweep at 21, 42 and 90, recomputing the book's bias by
  tercile at each. Kept because it is cheap, reported as secondary, and it does
  not lead the section. A better half-life becomes XS-v2 with its own registry
  entry and never an edit to XS-v1's stored parameters.

F4.5 passes when all four are measured and the deliverable names which
explanation the evidence supports.

## Task 4, reframed: the survivor restriction as a measurement

The path is confirmed by Task 0b and all three findings are recorded: no
point-in-time GICS source is reachable, the SEC SIC route needs an issuer
identity step the project does not have, and the yfinance sector field
describes the current holder of the symbol.

- 4a. Primary, same-period design. A style-only model, no sector dummies, on
  the full 825-name panel, and the same style-only model on the 502
  sector-mapped names, over identical dates. Two universes and one period, so
  the difference is the restriction and nothing else. Compared: style factor
  returns, Fama-MacBeth premia, mean cross-sectional R squared and mean
  specific variance.
- 4b. Secondary, labelled as confounding universe with period. The 2020-onward
  re-estimation against the full sample.
- 4c. Third, the direct quantity. The excluded names' own return and volatility
  differential against the included names for 2010 to 2016, which the panel
  supports.

F4.6 passes when 4a, 4b and 4c are stored, whatever they show.

## Task 5: registry v1, the version selector and D3

Registry v1 adds a schema with the champion flag, `champion_rule` untouched,
and one entry per model version with its parameters, artifacts hash and
eligibility. A dashboard-wide version selector, held in `st.session_state`, is
wired into D0 through D3, and every earlier tab must still render under every
version. D3 reads parquet only and carries: the eigenvalue spectrum against the
MP edge, the explained variance curve, the PCA against fundamental factor
correlation matrix, the estimator comparison table with out-of-sample
minimum-variance volatility, condition number and parameter count, the Task 3
half-life comparison, and the version selector. Every D3 panel builder gets a
test that fails on an empty read.

## Criteria

Copied verbatim from the roadmap:

- F4.1 First principal component vs the market factor: correlation above 0.95.
- F4.2 Marchenko-Pastur edge isolates between 3 and 15 significant factors; the
  count is stored.
- F4.3 OOS minimum-variance vol: shrinkage and factor estimators beat the
  sample covariance by more than 10%. If the sample covariance wins, that is an
  estimation bug.
- F4.4 PCA-v1 with k factors explains at least as much cross-sectional variance
  as XS-v1 on a held-out residual test; both numbers stored.

New in this sprint:

- F4.5 Task 3 as reframed: passes when 3a, 3b, 3c and 3d are measured and the
  deliverable names which explanation the evidence supports.
- F4.6 Task 4 as reframed: passes when 4a, 4b and 4c are stored.

STOP CONDITION 3. If F4.2 returns fewer than 3 or more than 15 factors, print
the eigenvalue spectrum, the MP edge and the N/T ratio, and report before
continuing. A count outside that band usually means the window or the
standardization is wrong rather than the market being unusual.

## Deliverables

- `efb/models/statistical.py`, `efb/cov.py`, `efb/registry.py` v1
- `data/models/PCA-v1/{loadings,factor_returns,eigenvalues}.parquet`
- `data/cov/{estimator}/` artifacts and `data/eval/cov_horse_race.parquet`
- `dashboard/tabs/d03_covariance.py`
- `docs/research/E4_covariance_memo.md`
- `notebooks/E4_walkthrough.ipynb` and its render
- `sprints/E4/{PRD,TASKS,PROBES,RESULTS}.json`

## Engineering

`make rebuild-e4` and `make rebuild` extended to E1 through E4. `VERSION.json`
and every registry entry share one artifacts hash. Full test suite and lint
clean. A ledger entry for every policy decision with old value, new value, date
and reason. `docs/open_items.md` updated with the two E3 items closed or
restated with their numbers.

## Walkthrough rules

`notebooks/E4_walkthrough.ipynb`, same rules as E2 and E3. Cell 1 asserts the
data hash against the registry. Every figure is read from an artifact and
asserted against its stored value, with the forbidden-literal scan over all
code cells. Derive by hand on a small sub-universe: the eigendecomposition and
the MP edge, the Ledoit-Wolf shrinkage intensity, one out-of-sample
minimum-variance portfolio, and the Task 3 tercile recomputation at one
alternative half-life. One section per criterion, the D3 panel-to-column map
with the non-empty guard, the evidence section for the deliverable, what E5
inherits, and a credit port note covering how N over T and the factor count
behave when the daily cross-section is a few hundred bonds rather than five
hundred stocks.

## Out of scope

- Declaring a champion. That is E5.
- Changing XS-v1. A better half-life or an added descriptor becomes a new
  version.
- Repairing the survivor restriction. The measurement is in scope, the repair
  needs an identity source the project does not have.
- GraphVAE, graphical lasso and probabilistic PCA are optional and only if the
  eight mandatory estimators are done and tested.

## Dependencies

E1 prices, universe, returns and the hygiene ledger. E2 TS-v1 betas and the
seed books. E3 XS-v1 descriptors, factor returns, specific returns, factor
covariance, specific variance, the bias and exposure artifacts, and the four
open items E4 owns. The pinned Wikipedia changes table and, for Task 0 only,
network access to EDGAR.
