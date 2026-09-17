# Sprint E3: PRD: Cross-Sectional Fundamental Model and Risk Decomposition

Dates: Mon Sep 14 to Sun Sep 20, 2026. Seven days. Tier 1. Gate: G1, Sep 20.
Stage: Quant researcher to risk researcher: the cross-section, and what a
portfolio is really made of.

## Overview

Build the Barra-style cross-sectional model. Standardized descriptors and
sector dummies dated t-1, one daily weighted cross-sectional regression,
factor-mimicking portfolios, factor covariance and specific risk, the full
covariance matrix, and the APM risk decomposition tables. Register XS-v1 as
the first fundamental model version, eligible for champion because it is
refreshable daily from EFB's own data. The sprint ends with dashboard tab D2,
the Factor Model Research Note and the Factor Exposure and Risk Report, and
gate G1.

## Goals

- Descriptors from data through t-1 only: Market, Size, Beta, Momentum,
  Reversal, Residual volatility, Liquidity, and 11 GICS sector dummies.
- Standardize cross-sectionally, orthogonalize where the specification says
  so, and estimate r_t = X_{t-1} f_t + e_t by weighted least squares with the
  identification constraint that cap-weighted sector factor returns sum to
  zero.
- Factor covariance F, specific variance D, and Sigma = X F X' + D, with the
  Euler risk decomposition (MCR, contribution, factor share, exposures).
- Fama-MacBeth premia with Newey-West t statistics, full sample and
  subperiods, reported whatever the verdict.
- XS-v1 artifacts in data/models/XS-v1/, the registry entry, extend make
  rebuild to E1 through E3, and hash every artifact into VERSION.json.
- F3.1 to F3.9 evaluated with stored numbers in sprints/E3/RESULTS.json,
  research deliverables written and linked from the Methodology tab, D2 loads
  in under 3 seconds, and every earlier tab still renders.

## Inherited constraints (E1 and E2 findings this sprint must carry, requirements not commentary)

1. MODEL_START is 2010 for the time-series models. The first calendar year
   with at least 300 point-in-time members with price coverage is 2010 (354
   covered names), so the threshold does not shorten the window (Hygiene
   Ledger, 2026-09-10). For XS-v1 the Task 0 probe sets the start one year
   later: momentum needs 231 observations ending at t-21, so no name is
   complete on 2010-12-31 and 252 sessions sit below the 300-name floor.
   XS-v1 estimates from 2011-01-03, the first session with at least 300
   complete descriptor rows, and that date and the table are recorded in the
   ledger. The cross-section then holds 428 to 497 names.
2. The panel is the post-exclusion returns.parquet, never prices.parquet. The
   exclusion list is the 33 tickers in the TS-v1 registry parameter
   identity_dropped, plus the three truncated series (FOX 2019-03-13,
   FOXA 2019-03-12, PCG 2022-10-03) restored by the F2.6c review. Descriptors
   for an excluded ticker are absent, never imputed, and the coverage effect
   is printed.
3. The estimation panel is 825 names; 502 of them carry a GICS sector, because
   sectors are known only for current members. The sector dummies therefore
   restrict the XS-v1 universe to the 502 sector-mapped names, of which 428
   (2010) to 501 (2026) have a return on a given day. This is a survivorship
   restriction on the historical cross-section and it is the largest known
   bias in the sprint, so it is measured rather than mentioned: in 2010 an
   average of 503.9 point-in-time members a day, 292.6 of them in the sector
   file, so 41.9% of the index by name and 8.85% by market cap are outside
   the model's universe, decaying to 4.8% by name and 0.24% by cap in 2025
   (sprints/E3/PROBES.md). Both numbers are stated in the research note as a
   limitation, and the name share is a new open item for E4. Nothing here is
   repaired inside E3.
4. Survivorship is measured, not fixed. F1.5 stores
   fraction_recovered 0.447887323943662, naive_minus_pit_bp_per_year
   365.10364348332297 and naive_minus_ff_market_bp_per_year
   375.3717302558671. The missing deletions are disproportionately failures,
   so the lower tail of specific returns is thin and specific risk on the
   loser side is biased downward. Every long-only output carries
   survivorship_caveat true.
5. Shares outstanding are not point-in-time before 2015-10. The Task 0
   probe found that the vendor shares history is dated at filing dates and is
   not split-adjusted (AAPL steps from 4,275,630,080 on 2020-08-28 to
   17,102,499,840 on 2020-08-31, exactly 4x, at the 2020 4-for-1 split),
   which is better than the E1 ledger assumed, but the filed coverage starts
   thin and fills late: 1 name has a filed count in 2013-04, 22 by 2015-09,
   149 by 2015-10, 396 by 2015-11, 435 by 2015-12 and 502 by 2017. 61,002
   fetched rows (14.3%) are duplicate dates and are dropped by keeping the
   largest value on a date, and 341 split-sized steps are visible. Size (log
   market cap) and the sqrt(mcap) weights therefore carry a per-row
   look_ahead flag, and 1,245,448 name-days (36% of the panel) are a backfill
   of a name's first filing. The flagged window is priced as a sensitivity in
   the research note. The Hygiene Ledger gains a dated correction entry, old
   text and new evidence, never an edit of the old entry.
6. The daily risk-free series ends 2026-07-31 (the Kenneth French 202607
   vintage), so returns.parquet excess is all NaN after that date while r runs
   to 2026-09-03. XS-v1 therefore regresses the total return r, not the excess
   return, and the Market factor is a total-return factor. The premium table
   is labelled accordingly, and F3.4's comparison runs on the overlap.
7. The E2 artifacts are not a daily beta or a daily residual panel.
   beta_history.parquet carries 201 month-end rows and loadings.parquet is a
   single cross-section (825 rows); residuals.parquet ends 2026-07-31 because
   TS-v1 needs the FF factors. XS-v1 therefore computes its own daily Beta and
   its own residual volatility from the EFB market proxy, so that it stays
   refreshable daily from EFB's own data, which the pre-registered
   champion_rule requires. The TS-v1 estimator is reused unchanged, and the
   difference against the FF-based beta is stored as a number on the overlap.
8. Volatility and the momentum exposure. The production volatility estimator
   is EWMA(0.97). F2.3, F2.3b and F2.3c failed and are not revisited. The
   momentum seed book's MOM exposure is -0.016190070548666415 on full-sample
   name-level betas, 0.09681972392333447 on the last month's static name-level
   factor share, 0.2884639400639966 as a regression loading (t
   29.104952622365634), and +0.06978002876927968 aggregated from rolling
   252-day betas at each of 195 rebalances, range -0.3322050420277022 to
   +0.3904549841533205, positive at 73.9 percent of rebalances.
9. Stale and outlier rows are excluded from every estimation window (E2
   excluded 6179 stale and 59 outlier rows) and the excluded count is printed.
   Interior NaN rows (302, the F2.0b set) are dropped, never forward-filled.
   Names with fewer than 60 usable observations in a window produce NaN, never
   an extrapolated number.
10. The champion rule is not edited.
    data/models/registry.json already holds champion_rule "min mean |bias-1|
    across portfolio families; ties to fewer parameters; a champion must be
    refreshable daily from EFB's own data", family_notes that make
    external-factor models diagnostic only, and a TS-v1 entry. The roadmap's
    sketch of an XS-v1 registry block must not overwrite the champion field
    with a model name. E3 adds an XS-v1 entry with champion false and
    eligible_for_champion true.
11. The two open items E3 owns are tasks in this sprint. From
    docs/open_items.md: price the momentum book from descriptor exposures
    recomputed at each rebalance rather than from full-sample betas (F3.9),
    and replace the diagonal D with the realized residual covariance
    (F3.8).
12. A stored criterion is never reworded. F3.1 to F3.7 are copied verbatim
    from docs/roadmap_v2.md. F3.8 and F3.9 are new criteria defined by the
    sprint brief, with new IDs, and they coexist with whatever E5 later adds.

## Research framing (copied verbatim from the roadmap)

Academic. How can cross-sectional equity returns be decomposed into
systematic factor exposures and idiosyncratic returns, and are the factor
premia (Fama-MacBeth) distinguishable from zero?

Practitioner. If I hold this portfolio, how much of my risk is actually coming
from unintended factor exposures, and which position reduces risk fastest if
trimmed?

Research. Does the proposed risk model explain realized portfolio returns and
volatility adequately enough to support portfolio decisions?

Research deliverable. Factor Model Research Note XS-v1 and Factor Exposure and
Risk Report (docs/research/E3_factor_model_note.md,
docs/research/E3_risk_report.md): model specification, standardization and
orthogonalization choices with the sensitivity tables; Fama-MacBeth premia
table with the interpretation a PM needs, which factors are priced and which
are only risk; the APM risk decomposition table for both seed books with
commentary on the unintended bet, the top MCR names and the idio share; the
idio share both ways per F3.8; the F3.9 reconciliation; a one-paragraph
verdict on whether XS-v1 can support decisions pending E5; and a section
titled "What would falsify this?". A negative verdict is a complete
deliverable.

## User stories

- As a PM, I want to know how much of my portfolio's risk is factor rather
  than idio, so that I can tell a stock pick from a factor bet.
- As a PM, I want the per-factor contribution table and the top MCR names, so
  that I know which position to trim to reduce risk fastest.
- As a risk manager, I want the model validated by identity checks (F3.2,
  F3.3, F3.5) before I read any attribution number.
- As a researcher, I want premia with Newey-West t statistics reported whether
  or not they are significant, so that nobody can select the story after the
  fact.
- As a later sprint author, I want XS-v1 registered with champion false,
  eligible_for_champion true, its parameters and its data hash, so that E5's
  champion rule runs on honest inputs.
- As a PM, I want the momentum book's XS-v1 exposure measured at every
  rebalance, so that the E2 finding about exposure timing becomes a number
  this model produces rather than a caveat.

## Technical architecture

```
returns.parquet (r, flags)        -> efb/models/fundamental.py -> XS-v1/descriptors
sectors.parquet (11 GICS)             standardization, WLS
prices.parquet (close, volume)        X'w identification
shares history (as filed)             ->
                                      XS-v1/factor_returns, specific_returns,
                                      fmp_weights, xs_r2
beta and resid vol from EFB's own cap-weighted universe total return
                                      same module       -> XS-v1/factor_cov,
                                                           XS-v1/specific_var
factor_returns + descriptors      -> efb/risk.py        -> Sigma, MCR,
                                      decompose, mcr, tables, exposures
data/portfolios/ (seed books)     -> efb/risk.py        -> eval/xs_risk_decomposition
                                                           eval/xs_bias, eval/xs_exposure
                                      efb/evaluate.py   -> sprints/E3/RESULTS.json
                                      efb/registry.py   -> registry XS-v1
all artifacts                     -> efb/build.py       -> data/VERSION.json
parquet only                      -> dashboard/tabs/d02_factor_risk.py (D2)
```

make rebuild extends the E1 and E2 rebuild and stays the single entry point
for the full pipeline. The dashboard reads parquet only and never fits a
model.

## Descriptors (every one dated t-1, every window on data through t-1)

| Descriptor | Definition | Window and minimum | Source | Flag |
| --- | --- | --- | --- | --- |
| market | constant 1 | none | constructed | none |
| size | log(market cap), market cap = close x shares | none | prices.parquet close, shares history | look_ahead true before the name's first share count |
| beta | shrunk rolling market beta, TS-v1 estimator | 252d, at least 126 usable returns | returns.parquet r vs the cap-weighted universe total return | none |
| momentum | cumulative return from t-252 to t-21 | 252d, at least 231 usable returns | returns.parquet r | none |
| reversal | return from t-21 to t-1 | 21d, at least 20 usable returns | returns.parquet r | none |
| resid_vol | annualized realized vol of the residual of a rolling 252d one-factor market model | 63d of residuals, all 63 required | returns.parquet r vs the same market proxy | none |
| liquidity | log of the mean 63d dollar volume, dollar volume = close x volume | 63d, at least 42 usable | prices.parquet | none |
| sector_10 to sector_60 | 11 GICS sector dummies, 1 if member, else 0 | none | processed/sectors.parquet | current vintage, not point-in-time: sectors are known only for current members |

Value (book to price) is not reachable point-in-time (probe (d): the only
source returns five quarters of retained earnings and book value at period-end
dates, with no filing date, and info book value is current only). It stays an
EXPERIMENTAL variant in the optional backlog and is written into the research
note as pending with that reason.

The cap-weighted universe total return is the EFB market proxy:
r_mkt_t = sum_i mcap_i,t-1 r_i,t / sum_i mcap_i,t-1 over the names with a
return that day, using market caps dated t-1. F1.3 stores the correlation of
its excess counterpart with the FF market return at 0.9563597974375629.

INPUT: data/processed/returns.parquet column r, data/raw/prices.parquet
columns close and volume, data/processed/sectors.parquet column gics_sector,
data/raw/shares_history.parquet.
OUTPUT: data/models/XS-v1/descriptors.parquet.

## Standardization

Cross-sectionally, for each descriptor on each day, over the day's universe:

1. Winsorize at plus or minus 3 MAD: x_w = clip(x, median - 3 MAD,
   median + 3 MAD), MAD the median absolute deviation from the median.
2. z-score with a cap-weighted mean and an equal-weighted standard deviation:
   z = (x_w - sum_i w_i x_w,i) / std_ew(x_w), where w_i is the name's share of
   the day's total market cap and std_ew is the equal-weighted standard
   deviation. This makes the cap-weighted market portfolio carry zero style
   exposure.
3. Orthogonalize where the map says so: regress the standardized descriptor on
   the other standardized descriptors it should not proxy for across the day's
   cross-section and keep the residual, then re-standardize the residual.
   The map is momentum on (beta, size) and resid_vol on (beta). The registry
   records it, the artifacts store both the pre-orthogonalization and the
   post-orthogonalization value, and the factor returns are reported both ways
   as the sensitivity.

Sector dummies are 0 or 1 and are not standardized.

## The regression and the identification constraint

Model: r_t = X_{t-1} f_t + e_t.

X_{t-1} is N_t x K with the first seven columns the standardized descriptors
(market, size, beta, momentum, reversal, resid_vol, liquidity) and the last 11
the sector dummies, K = 18. W = diag(sqrt(mcap_{t-1})) normalized so the
weights average 1, computed over the same N_t names.

Unconstrained solution: f_uncon = (X'WX)^-1 X'W r. Its rows are the
factor-mimicking portfolios, A = (X'WX)^-1 X'W, and by the normal equations
X' A' = I exactly, which is F3.2.

Identification. The market column of ones plus 11 sector dummies are collinear,
so the solution set is an affine line along the null direction
delta = (a, 0, 0, 0, 0, 0, 0, b, ..., b) with b = -a. The constraint is that
cap-weighted sector factor returns sum to zero, C f = 0 with C the 1 x K row
vector whose first seven entries are 0 and whose last 11 entries are the
sector cap weights w_s = (sum of market cap over the sector) / (total market
cap), so sum_s w_s = 1. The constrained estimate is

f_hat = f_uncon - M C' (C M C')^-1 C f_uncon, with M = (X'WX)^-1,

and it equals the projection of f_uncon onto the constraint along the null
direction, so X f_hat = X f_uncon and the fitted values and specific returns
are identical to the constrained weighted least squares solution. The
implementation solves the unconstrained problem, removes the null direction
with a = sum_s w_s f_sector,s, adds a to the market factor and subtracts a
from each sector factor, and asserts on a sample of days that the result
matches an explicit constrained solve and that C f_hat is below 1e-12.

Interpretation. After identification the market factor is the cap-weighted
universe total return less the cap-weighted mean specific return, and the
sector factor returns are deviations from it, so they sum to zero when cap
weighted. Because the adjustment lies in the null space of X, X F X' and every
total risk number are invariant to it; only the attribution between the market
factor and the sector factors moves. The research note states this with the
numbers.

FMP identity and the two weight sets. fmp_weights.parquet stores kind =
"unconstrained" (the rows of A, where X' w_FMP = e_k within 1e-8, the object
F3.2 tests) and kind = "identified" (the rows after the adjustment, whose
returns are the reported factor returns, the object F3.3 tests), for the last
trading day of each month.

Cross-sectional R squared: ratio of the weighted explained variance to the
weighted total variance on the day, with the same weights W.

INPUT: data/models/XS-v1/descriptors.parquet, returns.parquet column r.
OUTPUT: data/models/XS-v1/factor_returns.parquet,
data/models/XS-v1/specific_returns.parquet, data/models/XS-v1/xs_r2.parquet,
data/models/XS-v1/fmp_weights.parquet.

## Covariance and specific risk

- F, the factor covariance: EWMA covariance of the reported daily factor
  returns with half-life 90 business days, plus the Newey-West lag 2
  correction of the covariance estimate. 18 x 18, stored as a matrix.
- D, the specific variance: EWMA of squared specific returns with half-life 42
  business days, then Bayesian shrinkage toward the mean of the name's
  sector-size bucket, bucket = (GICS sector, size tercile by market cap
  within the day), 33 buckets. The shrinkage weight is
  n_i / (n_i + k) with n_i the name's usable observations and k = 60, both
  recorded in the registry, and both the raw and the shrunk value are stored.
- Sigma = X F X' + D for the day's X.
- Decomposition, for any weight vector w (a seed book or an uploaded CSV):
  sigma_p = sqrt(w' Sigma w); MCR_i = (Sigma w)_i / sigma_p; contribution
  w_i MCR_i with sum_i w_i MCR_i = sigma_p; percent of variance
  w_i MCR_i / sigma_p; factor contribution k = x_k (F x)_k / sigma_p with the
  exposure vector x = X'w; idio share = w' D w / (w' Sigma w). Every table is
  produced for both seed books, and the residual weight of any name without a
  descriptor row is reported rather than dropped silently.

INPUT: factor_returns.parquet, specific_returns.parquet, descriptors.parquet,
data/portfolios/*.parquet.
OUTPUT: data/models/XS-v1/factor_cov.parquet,
data/models/XS-v1/specific_var.parquet,
data/eval/xs_risk_decomposition.parquet.

## Fama-MacBeth premia

lambda_k = mean_t f_k,t over the sample, with the Newey-West standard error at
lag 2, a t statistic per factor, and the same table for the subperiods
2011-01-03 to 2015-12-31, 2016-01-01 to 2020-12-31 and 2021-01-01 to
2026-09-03, the first of which starts at the first complete cross-section the
Task 0 probe found. The table is produced for every factor whether or not the
premium is significant, a premium with |t| below 2 is labelled unpriced and
kept, and the premia are total-return premia because the regressand is r. The
model does not need the premia; they are the academic layer of the same
regression.

INPUT: factor_returns.parquet.
OUTPUT: data/eval/xs_fm_premia.parquet.

## Artifact schemas

| Artifact | Format | Columns |
| --- | --- | --- |
| data/raw/shares_history.parquet | long | ticker, date, shares, source, fetched_at, n_duplicate_dates_dropped |
| data/processed/market_cap.parquet | long | date, ticker, close, shares, shares_as_of, market_cap, look_ahead |
| models/XS-v1/descriptors.parquet | long | date, ticker, descriptor, value_raw, value_winsor, value_z, value_z_orth, n_obs, look_ahead |
| models/XS-v1/factor_returns.parquet | long | date, factor, f, f_pre_identification, is_sector, n_names |
| models/XS-v1/specific_returns.parquet | long | date, ticker, specific_return, weight, fitted |
| models/XS-v1/fmp_weights.parquet | long | date, factor, ticker, weight, kind |
| models/XS-v1/xs_r2.parquet | one row per day | date, r_squared, n_names, n_descriptors, fmp_identity_max_abs_error, sector_cap_weighted_sum, rank_deficient |
| models/XS-v1/factor_cov.parquet | 18 x 18 matrix | factor names as index and columns |
| models/XS-v1/specific_var.parquet | long | date, ticker, specific_var_raw, specific_var, bucket, bucket_mean, n_obs |
| eval/xs_fm_premia.parquet | long | factor, period, premium_daily, premium_annualized, nw_se, t_stat, n_days, priced |
| eval/xs_risk_decomposition.parquet | long | book, date, factor, exposure, factor_variance, idio_variance, total_variance, sigma_p, contribution, percent_of_variance, mcr_top_names |
| eval/xs_bias.parquet | long | book, year_month, realized_vol, predicted_vol, bias, n_days |
| eval/xs_exposure_timeseries.parquet | long | book, date, factor, exposure, n_names, weight_in_universe |
| eval/xs_residual_covariance.parquet | long | book, window_end, factor_share_diagonal, factor_share_realized, total_variance, factor_variance_diagonal, idio_variance_diagonal, idio_variance_realized |

## Registry entry XS-v1

data/models/registry.json gains one entry under models, key XS-v1, with the
same top-level fields as TS-v1 (version, family, parameters, universe_hash,
data_hash, built_at, champion, eligible_for_champion, walkthrough,
deliverable, results). champion is false and eligible_for_champion is true.
The top-level champion_rule and family_notes fields are not touched.

parameters: family "fundamental", assets "equity", universe_rule
"sector-mapped panel names with a return and a complete descriptor row",
model_start 2010, n_factors 18, descriptors [market, size, beta, momentum,
reversal, resid_vol, liquidity], sector_source
"processed/sectors.parquet", sector_scheme "gics", n_sectors 11,
identification "cap_weighted_sector_factor_returns_sum_to_zero",
estimator "wls", weights "sqrt_mcap", winsorize "3mad", zscore_mean
"cap_weighted", zscore_std "equal_weighted", orthogonalization
{"momentum": ["beta", "size"], "resid_vol": ["beta"]}, beta_source
"cap_weighted_universe_total_return", beta_window 252, beta_min_obs 126,
beta_shrinkage "vasicek", resid_vol_source "one_factor_market_model_residual",
resid_vol_window 63, momentum_window [252, 21], reversal_window 21,
liquidity_window 63, f_half_life 90, n_lags 2, d_half_life 42, d_shrink
"sector_size", d_shrink_k 60, size_shares_source
"yfinance_get_shares_full", size_shares_first_filed "2013-04",
size_shares_dense_from "2015-10", size_look_ahead true,
size_look_ahead_note as in constraint 5, xs_start "2011-01-03", n_days,
n_names_mean, r_squared_mean, data_hash, artifacts_hash.

## Regression design rules

- Every descriptor is dated t-1 and uses only data through t-1. A shift test
  proves that replacing X_{t-1} with X_t reduces the cross-sectional R
  squared, and the two R squared series are printed.
- Returns flagged stale or outlier are excluded from every window and the
  count is printed. Interior NaN rows are dropped, never filled.
- A name enters the cross-section only with all its descriptors present. A
  missing descriptor is never imputed, and the daily universe count is stored
  so a coverage gap cannot silently change the universe.
- The share count used on date t is the last filing-dated observation at or
  before t-1, so no share count is used before it was filed.
- Standardization and orthogonalization use only the day's cross-section.
- The daily factor return series is the only input to F, and F is the only
  input to the factor part of Sigma.

## Falsification criteria (thresholds written before the numbers are seen)

| ID | Criterion |
| --- | --- |
| F3.1 | Average daily cross-sectional R squared above 20%. Below 15% means descriptor construction or weighting is wrong, not that the market is unusual. |
| F3.2 | FMP check: X' w_FMP(k) equals the unit vector e_k within 1e-8 for every factor k. |
| F3.3 | Identification: cap-weighted sector factor returns sum to zero within 1e-10 on every day. |
| F3.4 | Agreement with the time-series world: XS-v1 momentum factor return vs FF MOM daily correlation above 0.6; market factor vs Mkt-RF above 0.9. |
| F3.5 | Decomposition adds up: factor variance plus idio variance equals w' Sigma w to machine precision; contributions sum to sigma_p. |
| F3.6 | Bias statistic for both seed portfolios, monthly 2015 to 2026, between 0.8 and 1.25. |
| F3.7 | The Fama-MacBeth premia table is produced with Newey-West t-stats for every factor and subperiod, whatever the verdict; a premium with \|t\| below 2 is reported as unpriced, not dropped. |
| F3.8 | Realized residual covariance is computed for both seed portfolios and the factor share is reported both ways, with the diagonal D and with the realized residual covariance. The criterion passes when both numbers are stored, whatever they show. |
| F3.9 | The XS-v1 exposure time series for the momentum book is stored and reconciled to the E2 measurements in writing. |

F3.1 to F3.7 are copied verbatim from docs/roadmap_v2.md. The modulus bars in
F3.7 are backslash-escaped only so the markdown table renders; the stored text
carries the modulus bars themselves, and tests/test_e3_results.py compares the
stored criterion strings against the roadmap text with the escapes removed.
F3.8 and F3.9 are defined by the sprint brief and take new IDs, so they
coexist with whatever E5 later adds. Every criterion is evaluated with a
stored number in sprints/E3/RESULTS.json.

The F3.4 market comparison regresses the daily market factor on a constant and
the FF market total return (Mkt-RF + RF) and reports the correlation; the
momentum comparison is the daily correlation of the two momentum series. Both
run on the overlap through 2026-07-31.

The F3.6 window is the criterion's own, monthly 2015 to 2026, which is
evaluable in full because XS-v1 starts at the first complete cross-section in
2011 rather than at the first share count.

## Dashboard tab D2 spec (Factor Model and Risk)

Reads parquet only, never fits a model.

1. Factor returns daily and cumulative, with the factor selector
   (factor_returns.parquet).
2. t statistics table from the Fama-MacBeth premia (eval/xs_fm_premia.parquet)
   with the priced and unpriced labels shown.
3. Cross-sectional R squared over time, plus the FMP identity error series as
   the model health line (xs_r2.parquet).
4. Descriptor distributions and coverage: the per-day coverage count and the
   standardized distributions by year (descriptors.parquet, xs_r2.parquet).
5. Factor covariance heatmap and correlation matrix (factor_cov.parquet).
6. FMP explorer: the largest long and short holdings of each factor-mimicking
   portfolio, with the kind selector (fmp_weights.parquet).
7. Risk Decomposition panel: portfolio selector for the two seed books plus an
   uploaded CSV of weights in the same schema; variance split pie (factor
   against idio); per-factor contribution table; top 20 idio contributors by
   contribution; MCR bar chart; and exposures x = X'w against limits read from
   a documented constant table (eval/xs_risk_decomposition.parquet).
8. Exposure timing panel: the momentum book's exposure time series from the
   rebalancing of the current model, next to the E2 rolling-beta aggregate
   (eval/xs_exposure_timeseries.parquet).

D2 loads in under 3 seconds. Every earlier tab (D0, Methodology, D1) still
renders; a regression test asserts it.

## One command rebuild and gate G1

The Makefile today has rebuild-e1, rebuild-e2, and a rebuild-e3 stub that
prints "make rebuild-e3 is implemented in Sprint E3" and exits 1. There is no
rebuild target. This sprint implements rebuild-e3 as the XS-v1 build alone
(what the sprint iterates on), keeps rebuild-e1 and rebuild-e2 as they are,
and adds rebuild as the E1 through E3 entry point, so that G1's "make rebuild
runs E1 through E3 from raw parquet to dashboard D2 in one command" is a
single target rather than a documented sequence. efb/build.py hashes every new
artifact into data/VERSION.json with its previous_data_hash, and the XS-v1
registry entry carries the same data_hash and its own artifacts_hash. make
publish copies docs/research into dashboard/static/docs and the Methodology
tab links each document by path, so the link opens the file rather than
reloading the dashboard.

Gate G1 (Sep 20), verbatim: "make rebuild runs E1 through E3 from raw parquet
to dashboard D2 in one command; registry holds TS-v1 and XS-v1 with data
hashes; all F1 to F3 criteria evaluated with stored numbers; all three
walkthroughs rendered and linked. Steps 1 through 3 of the build order are
running. Research deliverable written and linked from the Methodology tab."

## Out of scope

- No champion selection and no bias comparison across families: XS-v1 is
  registered with champion false and eligible_for_champion true, and E5
  applies the champion rule.
- No transaction costs, sizing or hedging: E8 to E10.
- No estimator changes to TS-v1 or the E2 volatility work; F2.3, F2.3b and
  F2.3c stay as they are.
- No point-in-time sector history and no filed share history before 2013-04
  that is dense before 2015-10; both are flagged and priced as sensitivities,
  not fixed.
- The E11 constituent source: tracked in docs/open_items.md only.
- A concentrated 20-name long-only book is not built. The roadmap's sketch
  named it as a second seed book; the brief reuses seed_ew and seed_mom_ls so
  that the E2 and E3 risk numbers are comparable on the same books. This is a
  deliberate deviation and it is recorded in the research note. The existing
  seed_mom_ls is already sector neutral by construction, which the sprint
  asserts as evidence (per-sector net weights sum to zero) rather than
  building a second book.

## Optional backlog (dropped first when time is short, last in TASKS.md)

1. EXPERIMENTAL value variant (book to price). Deferred: probe (d) shows the
   only reachable source covers five quarters at period-end dates with no
   filing date, so no point-in-time panel exists.
2. Orthogonalization sensitivity table (factor returns with and without
   orthogonalization) and the equal-weighting and top-300 universe
   sensitivities. The orthogonalization itself is in the main path; only the
   side by side tables are optional.
3. The two-pass residual volatility variant (residual vol from XS-v1's own
   specific returns instead of the one-factor market model residual).
4. The sector-size bucket granularity study (finer or coarser than 3 size
   buckets by 11 sectors).

A deferred item is written into the research note as pending with the reason,
never dropped silently. The Fama-MacBeth subperiod breakdown is NOT in this
backlog: F3.7 names subperiods explicitly, so deferring them would fail a
stored criterion to save one pass over the same factor return matrix.

## Risks and pre-registered expectations

- F3.6 is expected to fail for the momentum seed book. Its 21-day bias
  statistic in E2 was 1.8544 on average with every year above 1.0 (1.1063 in
  2012, 2.9259 in 2026). F3.6 asks for 0.8 to 1.25 monthly on both books, so
  a fail on that book is pre-registered here as a finding, not softened, and
  the research note must say what it means for sizing.
- F3.1 depends on the descriptor set. With 18 columns and a 500-name
  cross-section the average R squared can land between 15 and 20 percent; the
  criterion's fail band is a construction diagnostic and the note reports
  which descriptors carry it.
- Multicollinearity. Beta, size, liquidity and residual vol are correlated.
  The sprint computes VIF per factor per year and reports any factor year
  above 5, with the sign-swap diagnostic that follows from it.
- Descriptor coverage gaps changing the universe day to day. The daily
  universe count is stored and the minimum is printed; the first and last
  weeks of the sample are expected to be the thin ones.
- Look-ahead in market cap. 1,245,448 name-days before a name's first filing
  carry a backfilled count. The flagged window is priced by re-estimating on
  2015-10-01 onward, where at least 149 names have a filed count, and
  reporting the difference in the Size factor returns and the premia.
- Specific returns still correlated within industries: the sector granularity
  is too coarse and idio risk is overstated. F3.8's realized residual
  covariance measures exactly this, and it is the reason the criterion passes
  on being stored rather than on a threshold.

## Dependencies

- Sprint E1 and E2 artifacts: returns.parquet, prices.parquet,
  sectors.parquet, universe_membership.parquet, factors_ff.parquet,
  data/portfolios/seed_ew.parquet and seed_mom_ls.parquet, efb/build.py,
  efb/registry.py, efb/evaluate.py, efb/models/timeseries.py, efb/risk.py is
  new this sprint, efb/models/fundamental.py is new this sprint.
- dashboard/tabs/d01_exposures.py, publish.py and methodology.py as the
  patterns for D2 and the link list.
- Network at build time: the shares history download (made rebuild-e1 already
  needs the network for Wikipedia and Ken French).
- Optional: none. The sprint needs no new package.

## Book connection

APM Ch5 (fundamental factor models, factor-mimicking portfolios), APM Ch7
(factor risk, exposures), EQI Ch6 (fundamental factor models, factor
covariance, specific risk).

Understand before implementing: why a characteristic can serve as an exposure
(the Barra view) instead of an estimated beta (the time-series view), and what
each assumes; why a constraint is needed to identify the market factor next to
sector dummies; and what Fama-MacBeth standard errors correct.

What the implementation teaches that the book cannot: standardization and
orthogonalization choices move factor returns by more than the textbook
suggests, and how much of a stock-picker portfolio is factor once measured,
with sector neutrality arising by construction.

## Schedule

Seven days (Sep 14 to Sep 20), ending on the gate. The sprint is the densest
one in the roadmap, so scope is cut inside the sprint by dropping the optional
backlog items, never by moving the gate date or by narrowing a stored
criterion.

## Output

- sprints/E3/PRD.md
- sprints/E3/TASKS.md
- sprints/E3/PROBES.md (Task 0 tables)
- sprints/E3/RESULTS.json (F3.1 to F3.9 with stored numbers)
- data/models/XS-v1/ (seven artifacts), data/models/registry.json entry
- data/eval/ (premia, decomposition, bias, exposure, residual covariance)
- Makefile (rebuild-e3 implemented in place of the stub, rebuild added)
- notebooks/E3_walkthrough.ipynb and .html, linked from the Methodology tab
- docs/research/E3_factor_model_note.md, docs/research/E3_risk_report.md
- docs/hygiene_ledger.md (the shares correction entry and the XS-v1
  parameters), docs/open_items.md (the two E3 items closed with their numbers,
  any new finding added)
