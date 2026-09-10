# Sprint E2: Tasks

## Status: In Progress

Rules: ten atomic tasks including Task 0, each with a test. Task 8
evaluates every F criterion; Task 9 produces the research deliverable.
OPTIONAL work sits in the Optional backlog at the end and is dropped
first when the four-day schedule tightens; the date never moves.

- [x] Task 0: Coverage probe by calendar year and MODEL_START (P0)
  - Acceptance: count point-in-time members with price coverage by
    calendar year (a member counts when at least half of the year's
    business days have a non-null adjusted close), print the table into
    sprints/E2/PROBES.md, set MODEL_START to the first year with at
    least 300 covered names, and record MODEL_START plus the table in
    docs/hygiene_ledger.md. Every later task reads MODEL_START from the
    ledger entry.
  - Test: tests/test_e2_probe.py (coverage table and MODEL_START
    selection on fixtures).
  - Files: efb/probes.py (extended), sprints/E2/PROBES.md,
    docs/hygiene_ledger.md, tests/test_e2_probe.py

- [ ] Task 1: Single-factor market model with OLS and Newey-West SEs (P0)
  - Acceptance: efb/models/timeseries.py fits the market model per stock
    (beta, alpha, R^2, residual vol) from MODEL_START with OLS SEs and
    Newey-West HAC SEs at lag 5; synthetic data with a known beta is
    recovered to tolerance; a NaN or flagged row inside a window is
    dropped, never forward-filled.
  - Test: tests/test_timeseries.py (known-parameter recovery, NW SE on
    autocorrelated residuals, NaN-drop proof).
  - Files: efb/models/timeseries.py, tests/test_timeseries.py

- [ ] Task 2: Multi-factor FF5 + MOM loadings, residuals, idio vol (P0)
  - Acceptance: loadings B (N x K) for mkt_rf, smb, hml, rmw, cma, mom
    from MODEL_START with both SE types, residual matrix, idio vol per
    stock; the excluded stale/outlier/NaN row count is printed; short
    histories (under 60 observations) yield NaN rows, never guesses.
  - Test: tests/test_timeseries.py (multifactor recovery, exclusion
    count).
  - Files: efb/models/timeseries.py, tests/test_timeseries.py

- [ ] Task 3: Beta shrinkage, rolling and EWMA betas, shift audit (P0)
  - Acceptance: Vasicek (w = sigma_xs^2 / (sigma_xs^2 + SE^2) toward the
    cross-sectional mean) and Blume (0.67/0.33) betas; rolling 252d and
    EWMA-weighted (half-lives 63 and 126) beta histories stored under
    data/models/TS-v1/; a shift test proves a loading dated t was fit on
    data through t-1.
  - Test: tests/test_beta_history.py (shrinkage weights, shift audit).
  - Files: efb/models/timeseries.py, tests/test_beta_history.py,
    data/models/TS-v1/beta_history.parquet

- [ ] Task 4: Volatility estimators and QLIKE/MZ evaluation framework (P0)
  - Acceptance: efb/vol.py implements EWMA (0.94, 0.97), realized vol
    (21d, 63d), the QLIKE loss and the Mincer-Zarnowitz regression; an
    out-of-sample split (last 2 years) produces the vol horse race table
    for every name with enough data; GARCH(1,1) via arch is attempted
    and the outcome (works or not on Python 3.14) is recorded in the
    ledger either way.
  - Test: tests/test_vol.py (EWMA recursion, QLIKE values, MZ on
    synthetic GARCH data).
  - Files: efb/vol.py, tests/test_vol.py, data/eval/vol_horse_race.parquet

- [ ] Task 5: Portfolio risk decomposition and the two seed books (P0)
  - Acceptance: sigma_p^2 = w' B F B' w + w' D w with F the EWMA
    half-life 90d factor covariance, computed for the equal-weight seed
    portfolio (long-only, survivorship_caveat true) and for a
    sector-neutral long/short momentum quintile seed portfolio built from
    returns.parquet and sectors.parquet (long top quintile, short bottom
    quintile within each GICS sector, past 126d momentum, monthly
    rebalance, survivorship_caveat false); weights and risk rows stored
    in data/portfolios/.
  - Test: tests/test_portfolio_risk.py (known B, F, D reproduce the
    variance split by hand; the momentum book is sector neutral).
  - Files: efb/portfolios.py or extension of efb/models/timeseries.py,
    tests/test_portfolio_risk.py, data/portfolios/seed_ew.parquet,
    data/portfolios/seed_mom_ls.parquet

- [ ] Task 6: TS-v1 artifacts, registry entry, rebuild and versioning (P0)
  - Acceptance: data/models/TS-v1/{loadings, loadings_se, residuals,
    idio_vol, factor_cov}.parquet written per the PRD schemas;
    efb/registry.py writes the TS-v1 entry (family timeseries, champion
    false, eligible_for_champion false, universe and data hashes,
    walkthrough, deliverable, results paths); make rebuild-e2 extends the
    E1 rebuild; VERSION.json gains the new artifacts.
  - Test: tests/test_registry.py (entry fields, hash matches the files).
  - Files: efb/registry.py, efb/build.py, Makefile, tests/test_registry.py,
    data/models/registry.json, data/VERSION.json

- [ ] Task 7: Dashboard tab D1 Exposures (P0)
  - Acceptance: dashboard/tabs/d01_exposures.py renders the seven D1
    panels from parquet only; loads in under 3 seconds; a regression
    test imports every tab and D0 still renders.
  - Test: tests/test_dashboard_d1.py (panel builders on fixtures, app
    and all tabs import).
  - Files: dashboard/tabs/d01_exposures.py, dashboard/app.py,
    tests/test_dashboard_d1.py

- [ ] Task 8: Evaluate F2.0a, F2.0b, F2.0c and F2.1 to F2.5 (P0)
  - Acceptance: every criterion stored in sprints/E2/RESULTS.json with
    threshold, stored number and verdict (pass, fail, or pending with a
    reason); numbers computed from artifacts, never retyped; F2.0c
    includes the events.parquet audit check.
  - Test: tests/test_e2_results.py (all eight keys present, verdicts
    valid).
  - Files: sprints/E2/RESULTS.json, efb/evaluate.py extension,
    tests/test_e2_results.py

- [ ] Task 9: Research deliverable: Beta and Volatility Estimation Study (P0)
  - Acceptance: docs/research/E2_exposure_study.md answers the PM
    question in one paragraph at the top, contains the methodology, the
    stored numbers, the beta and volatility horse-race tables with a
    recommended estimator per use (hedging, risk, sizing), one paragraph
    on what the residual correlation structure says about the factor
    set, and a section titled "What would falsify this?"; a negative
    verdict is a complete deliverable; linked from the Methodology tab;
    no em dashes.
  - Test: tests/test_e2_data_note.py (sections present, no em dashes,
    cites stored numbers).
  - Files: docs/research/E2_exposure_study.md, tests/test_e2_data_note.py

## Optional backlog (dropped first when time is short)

- [ ] OPTIONAL: GARCH(1,1) production rows in the vol horse race and D1
  - Acceptance: arch fits on Python 3.14, one-step forecasts enter the
    QLIKE table; otherwise the install outcome is the recorded result.
  - Test: tests/test_vol.py gains a GARCH case (marked skipif no arch).
- [ ] OPTIONAL: short-term reversal as a seventh regressor
  - Acceptance: st_rev column in loadings, loadings_se and factor_cov
    when time allows; schema already reserves the column.

## Exit criteria (roadmap)

All F2 criteria evaluated with stored numbers in sprints/E2/RESULTS.json;
registry contains TS-v1 with a data hash; D1 loads under 3 seconds;
walkthrough rendered; research deliverable written and linked from the
Methodology tab.
