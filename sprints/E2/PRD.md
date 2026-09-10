# Sprint E2: PRD: Time-Series Factor Models and Volatility

Dates: Sep 10 to Sep 14, 2026. Four working days. Tier 1. Stage: Quant
researcher: estimating exposures and knowing their error.

## Overview

Estimate per-stock exposures to observed factors by time-series
regression, with honest standard errors and shrinkage, and build the
volatility estimators the risk model needs. Register TS-v1 as the first
model version (family: timeseries, diagnostic only, not champion
eligible). The sprint ends with dashboard tab D1 Exposures, the registry
entry for TS-v1, and the Beta and Volatility Estimation Study.

## Goals

- Every regression in E2 starts at MODEL_START, the first calendar year
  with at least 300 point-in-time members with recoverable prices,
  determined by the Task 0 coverage probe and recorded in the ledger.
- Single-factor market model and FF5 + MOM multi-factor model with OLS
  and Newey-West standard errors, shrinkage (Vasicek, Blume), rolling
  252d and EWMA-weighted betas.
- Volatility estimators (EWMA 0.94 and 0.97, realized 21d and 63d, and
  GARCH(1,1) as an optional extra) compared out of sample with QLIKE and
  Mincer-Zarnowitz.
- Portfolio risk under the time-series model for two seed portfolios:
  the equal-weight seed book (long-only, survivorship_caveat true) and a
  sector-neutral long/short momentum quintile seed book, the second seed
  book for E3.
- TS-v1 artifacts in data/models/TS-v1/ with documented schemas, the
  registry entry, make rebuild-e2, and VERSION.json hashes.
- F2.0a, F2.0b, F2.0c and F2.1 to F2.5 evaluated with stored numbers in
  sprints/E2/RESULTS.json; research deliverable written and linked from
  the Methodology tab; D1 loads in under 3 seconds and every earlier tab
  still renders.

## E1 findings this sprint must carry forward (requirements, not commentary)

1. Survivorship. Only 44.8% of deleted S&P 500 names have recoverable
   prices; the measured bias is 349 bp per year (F1.5).
   a) Task 0 is a probe: count point-in-time members with price coverage
      by calendar year, print the table into sprints/E2/PROBES.md, and
      set MODEL_START to the first year with at least 300 covered names.
      MODEL_START and the table are recorded in the Hygiene Ledger.
      Every regression in E2 starts at MODEL_START.
   b) Any artifact computed on a long-only portfolio carries a
      survivorship_caveat field set to true. The equal-weight seed
      portfolio is long-only, so its rows carry it. The long/short
      momentum seed portfolio carries the field set to false.
   c) The ledger gains one paragraph stating that the missing deletions
      are disproportionately failures, so the lower tail of residual
      returns is thin and specific risk on the loser side is biased
      downward. This is context for E3 and E5, not something E2 fixes.
2. Successor criteria. F1.1, F1.2 and F1.4 failed on threshold
   calibration, not on data quality. A criterion is never reworded after
   the number is seen; successors carry new IDs and are evaluated in
   this sprint: F2.0a, F2.0b, F2.0c as listed in the criteria section.
3. Pre-registration before any model exists. Kenneth French factors lag
   by roughly a month and FRED is unreachable, so a time-series model on
   FF factors cannot be refreshed daily in production. Before any
   estimator is written, data/models/registry.json is created with the
   champion_rule and family_notes below and no model entries. This is
   written now so that E5 cannot be accused of choosing the rule after
   seeing the numbers.
4. RG-Operate open item. The Wikipedia changes table is pinned to
   revision 1368675864 and freezes membership at 2026-08-05.
   docs/open_items.md gains: "E11 requires an ongoing constituent source
   before the book runs". No work on it in E2.
5. Walkthrough requirement. The E1 walkthrough reported the Lo (2002)
   Sharpe standard error below the i.i.d. standard error because the FF
   market factor has a negative lag-1 autocorrelation (-0.10), a ratio
   of 0.922. The E2 walkthrough must restate this with the numbers when
   it introduces Newey-West standard errors for betas, since the same
   mechanism decides the direction of F2.5.

## User stories

- As a researcher, I want a beta with a standard error next to it, so
  that I know whether 1.3 and 1.1 are different numbers.
- As a PM, I want shrunk, rolling and EWMA betas side by side, so that I
  can see how fast a stock's exposure moves and pick the overlay my
  horizon needs.
- As a risk manager, I want portfolio variance split into factor and
  idio parts, so that I can see what a hedge removes and what remains.
- As a later sprint author, I want TS-v1 registered with its data hash
  and its diagnostic-only status, so that E5's champion rule has honest
  inputs.
- As a PM, I want the volatility horse race on QLIKE, so that the
  production vol estimator is chosen by evidence, not taste.

## Technical architecture

```
returns.parquet (excess, flags) ──▶ efb/models/timeseries.py ──▶ TS-v1/loadings,
factors_ff.parquet (mkt_rf..mom)      TS-v1/loadings_se, TS-v1/residuals,
                                      TS-v1/idio_vol
factors_ff.parquet              ──▶ EWMA half-life 90d ──▶ TS-v1/factor_cov
returns.parquet (r)             ──▶ efb/vol.py ──▶ vol forecasts, QLIKE and
                                      Mincer-Zarnowitz tables
universe_membership + sectors   ──▶ seed portfolios ──▶ data/portfolios/
TS-v1 artifacts                 ──▶ efb/registry.py ──▶ data/models/registry.json
all artifacts                   ──▶ efb/build.py ──▶ data/VERSION.json,
                                      sprints/E2/RESULTS.json
parquet only                    ──▶ dashboard/tabs/d01_exposures.py (D1)
```

make rebuild-e2 extends the E1 rebuild and stays the single entry point
for the full pipeline. The dashboard reads parquet only and never fits a
model.

## Regression design rules

- Regressions use returns at t against factors at t (contemporaneous).
- Rolling and EWMA windows used for forecasting end at t-1; a shift test
  proves that a loading dated t was fit on data through t-1.
- Rows flagged stale or outlier in returns.parquet are excluded from
  estimation windows; the excluded count is printed.
- Interior NaN rows (the 302 rows across 13 tickers documented by F2.0b)
  are dropped by every regression window, never forward-filled.
- Names with fewer than 60 usable observations in a window produce NaN
  loadings, never an extrapolated number.

## Formulas (every input and output labeled)

- OLS: beta_hat = (X'X)^-1 X'y; residuals e = y - X beta_hat; R^2;
  residual vol sigma_eps.
  INPUT: returns.parquet excess, factors_ff.parquet factor columns.
  OUTPUT: TS-v1/loadings.parquet, TS-v1/residuals.parquet,
  TS-v1/idio_vol.parquet.
- Newey-West covariance of beta_hat with lag L = 5:
  V = (X'X)^-1 S (X'X)^-1,
  S = Gamma_0 + sum_{j=1..L} (1 - j/(L+1)) (Gamma_j + Gamma_j'),
  Gamma_j = sum_t u_t u_{t-j} x_t x_{t-j}'.
  SE_NW = sqrt(diag(V)). OUTPUT: TS-v1/loadings_se.parquet.
- Vasicek shrinkage: beta_s = w * beta_hat + (1 - w) * beta_bar with
  w = sigma_xs^2 / (sigma_xs^2 + SE^2), sigma_xs^2 the cross-sectional
  variance of beta_hat across the universe.
- Blume shrinkage: beta_s = 0.67 * beta_hat + 0.33.
- EWMA vol: sigma_t^2 = lambda sigma_{t-1}^2 + (1 - lambda) r_{t-1}^2,
  lambda in {0.94, 0.97}. Half-lives for beta weighting: 63 and 126
  trading days.
- GARCH(1,1): sigma_t^2 = omega + a r_{t-1}^2 + b sigma_{t-1}^2, fit via
  the arch package (OPTIONAL; the outcome of the install is recorded
  either way).
- QLIKE loss: QLIKE(sigma_hat_t, r_t) = ln sigma_hat_t^2 + r_t^2 /
  sigma_hat_t^2, averaged over the out-of-sample window.
- Mincer-Zarnowitz: r_t^2 = a + b sigma_hat_t^2 + e; a near 0 and b near
  1 means an unbiased forecast.
- Portfolio variance under the time-series model:
  sigma_p^2 = w' B F B' w + w' D w, with F the EWMA factor covariance
  (half-life 90d), D the diagonal idio variance matrix.
  OUTPUT: data/portfolios/seed_ew_risk.parquet,
  data/portfolios/seed_mom_ls_risk.parquet.

## Parquet schemas (data/models/TS-v1/)

loadings.parquet: index ticker (string). Columns mkt_rf, smb, hml, rmw,
cma, mom (st_rev optional, added only if the OPTIONAL task lands),
alpha, r_squared. All float64. Row per stock, full sample from
MODEL_START.

loadings_se.parquet: index ticker (string). Columns are a MultiIndex
(method, statistic): method in {ols, nw_l5}, statistic in {mkt_rf, smb,
hml, rmw, cma, mom, alpha} (st_rev optional). All float64.

residuals.parquet: long format, index (date, ticker), column residual
(float64). Dates from MODEL_START; rows excluded by flags are NaN with
the exclusion count stored in the registry entry.

idio_vol.parquet: index ticker (string). Columns idio_vol (daily),
idio_vol_ann (sqrt(252) scaled), n_obs (int), from MODEL_START.

factor_cov.parquet: K x K float64, index and columns the factor names,
EWMA half-life 90d on the factor returns.

## Registry schema (data/models/registry.json)

Top level: champion_rule (string, pre-registered), family_notes (string,
pre-registered), models (map). Each model entry: version id, family,
parameters (map), universe_hash (sha256 of
universe_membership.parquet), data_hash (sha256 of the data inputs),
built_at, champion (false), eligible_for_champion (false), walkthrough
(path), deliverable (path), results (path).

## Pre-registered falsification criteria (copied verbatim)

F2.0a to F2.0c are successors to F1.1, F1.2 and F1.4 and are copied
from the E2 brief verbatim. F2.1 to F2.5 are copied verbatim from the
roadmap. Numeric thresholds are written before the numbers are seen;
each is evaluated with a stored number in sprints/E2/RESULTS.json.

| ID | Criterion |
| --- | --- |
| F2.0a | coverage is reported per universe rather than as one threshold: current members 100%, point-in-time members with prices by year (the Task 0 table); the criterion passes if the table is stored and MODEL_START is recorded. |
| F2.0b | interior NaN return rows (302 rows, 13 tickers) are excluded from every regression window and never forward-filled; the criterion passes if a test proves a regression window containing a NaN row drops that row rather than imputing it. |
| F2.0c | adjusted-close audit mean below 0.1 bp, and every audited day with an absolute difference above 50 bp appears in events.parquet with a cause (the 221 bp BKR day is a merger). Passes when both hold. |
| F2.1 | Full-sample OLS beta vs mean of rolling 252d betas: cross-sectional correlation above 0.9. |
| F2.2 | Mean pairwise correlation of FF5+MOM residuals across the universe below 0.05. Higher means a missing common factor; carry the finding into E3. |
| F2.3 | GARCH(1,1) and EWMA(0.94) each beat trailing 252d vol on out-of-sample QLIKE for more than 60% of names. |
| F2.4 | For the equal-weight seed portfolio, bias statistic (realized 63d forward vol over model-predicted vol) averages between 0.8 and 1.2 across calendar years. |
| F2.5 | Newey-West SE exceeds OLS SE at lag 5 for more than 80% of names. If not, document the direction and why. |

## Dashboard tab D1 spec (Exposures)

Reads parquet only, never fits a model.

1. Per-stock loadings table with standard errors (TS-v1/loadings.parquet
   and loadings_se.parquet).
2. Rolling beta chart for a selected name with raw, Vasicek and Blume
   overlays (from the beta history artifact built this sprint and stored
   under data/models/TS-v1/).
3. R squared distribution histogram (loadings.parquet r_squared).
4. Idio vol vs total vol scatter (idio_vol.parquet vs realized total
   vol from returns).
5. Volatility estimator comparison with the QLIKE table (data/eval/
   vol_horse_race.parquet).
6. Portfolio exposure panel for the selected seed portfolio (weights
   times loadings, data/portfolios/).
7. Beta horse-race table: RMSE of raw, Vasicek, Blume and EWMA betas
   against next-quarter realized betas (data/eval/beta_horse_race.parquet).

D1 loads in under 3 seconds. Every earlier tab (D0, Methodology) still
renders; a regression test asserts it.

## Out of scope

- No cross-sectional model: that is E3, motivated by F2.2.
- No champion selection: TS-v1 is diagnostic only and
  eligible_for_champion is false by pre-registration.
- No transaction costs, sizing or hedging: E8 to E10.
- The E11 constituent source: tracked in docs/open_items.md only.
- GARCH(1,1) and the short-term reversal regressor are OPTIONAL and are
  the first items dropped when time is short.

## Dependencies

- Sprint E1 artifacts: data/raw/prices.parquet, data/raw/factors_ff.parquet,
  data/processed/{returns, universe_membership, sectors, events}.parquet,
  efb/perf.py, efb/hygiene.py, efb/build.py, dashboard D0 and Methodology.
- efb/models/timeseries.py and efb/vol.py are new this sprint; efb/registry.py
  is new this sprint.
- Optional: the arch package on Python 3.14.

## Research framing (copied verbatim from the roadmap)

- Academic question: How is a stock's exposure to observed factors
  estimated by time-series regression, how uncertain is the estimate,
  and when does shrinkage improve it?
- Practitioner question: When the risk system says a stock has beta 1.3,
  how much should I believe it, how fast does it move, and what is its
  residual (idio) return?
- Research question: Do shrunk, exponentially weighted betas forecast
  next-quarter realized betas and portfolio volatility better than raw
  OLS betas, and do GARCH or EWMA forecasts beat trailing volatility?
- Research deliverable: docs/research/E2_exposure_study.md, the Beta and
  Volatility Estimation Study, written for a senior quant or risk
  manager: the PM answer in one paragraph at the top, methodology, the
  stored numbers, the beta and volatility horse-race tables with a
  recommended estimator per use (hedging, risk, sizing), one paragraph on
  what the residual correlation structure says about the factor set, and
  a section titled "What would falsify this?". A negative verdict (for
  example, shrinkage does not beat raw betas out of sample) is a complete
  deliverable.
- The TASKS.md must include one task that produces the deliverable and
  one that evaluates every falsification criterion listed below.

## Schedule

Four working days (Sep 10 to Sep 14) so that E3 keeps its full week
before the September 20 gate. Scope is cut inside the sprint by dropping
OPTIONAL tasks, never by moving the date.

## Output

- sprints/E2/PRD.md
- sprints/E2/TASKS.md
- sprints/E2/PROBES.md (Task 0 coverage table)
- data/models/registry.json (champion_rule and family_notes only, no
  model entries yet)
- docs/open_items.md
