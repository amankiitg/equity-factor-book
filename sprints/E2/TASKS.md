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

- [x] Task 1: Single-factor market model with OLS and Newey-West SEs (P0)
  - Acceptance: efb/models/timeseries.py fits the market model per stock
    (beta, alpha, R^2, residual vol) from MODEL_START with OLS SEs and
    Newey-West HAC SEs at lag 5; synthetic data with a known beta is
    recovered to tolerance; a NaN or flagged row inside a window is
    dropped, never forward-filled.
  - Test: tests/test_timeseries.py (known-parameter recovery, NW SE on
    autocorrelated residuals, NaN-drop proof).
  - Files: efb/models/timeseries.py, tests/test_timeseries.py

- [x] Task 2: Multi-factor FF5 + MOM loadings, residuals, idio vol (P0)
  - Acceptance: loadings B (N x K) for mkt_rf, smb, hml, rmw, cma, mom
    from MODEL_START with both SE types, residual matrix, idio vol per
    stock; the excluded stale/outlier/NaN row count is printed; short
    histories (under 60 observations) yield NaN rows, never guesses.
  - Test: tests/test_timeseries.py (multifactor recovery, exclusion
    count).
  - Files: efb/models/timeseries.py, tests/test_timeseries.py

- [x] Task 3: Beta shrinkage, rolling and EWMA betas, shift audit (P0)
  - Acceptance: Vasicek (w = sigma_xs^2 / (sigma_xs^2 + SE^2) toward the
    cross-sectional mean) and Blume (0.67/0.33) betas; rolling 252d and
    EWMA-weighted (half-lives 63 and 126) beta histories stored under
    data/models/TS-v1/; a shift test proves a loading dated t was fit on
    data through t-1.
  - Test: tests/test_beta_history.py (shrinkage weights, shift audit).
  - Files: efb/models/timeseries.py, tests/test_beta_history.py,
    data/models/TS-v1/beta_history.parquet

- [x] Task 4: Volatility estimators and QLIKE/MZ evaluation framework (P0)
  - Acceptance: efb/vol.py implements EWMA (0.94, 0.97), realized vol
    (21d, 63d), the QLIKE loss and the Mincer-Zarnowitz regression; an
    out-of-sample split (last 2 years) produces the vol horse race table
    for every name with enough data; GARCH(1,1) via arch is attempted
    and the outcome (works or not on Python 3.14) is recorded in the
    ledger either way.
  - Test: tests/test_vol.py (EWMA recursion, QLIKE values, MZ on
    synthetic GARCH data).
  - Files: efb/vol.py, tests/test_vol.py, data/eval/vol_horse_race.parquet

- [x] Task 5: Portfolio risk decomposition and the two seed books (P0)
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

- [x] Task 6: TS-v1 artifacts, registry entry, rebuild and versioning (P0)
  - Acceptance: data/models/TS-v1/{loadings, loadings_se, residuals,
    idio_vol, factor_cov}.parquet written per the PRD schemas;
    efb/registry.py writes the TS-v1 entry (family timeseries, champion
    false, eligible_for_champion false, universe and data hashes,
    walkthrough, deliverable, results paths); make rebuild-e2 extends the
    E1 rebuild; VERSION.json gains the new artifacts.
  - Test: tests/test_registry.py (entry fields, hash matches the files).
  - Files: efb/registry.py, efb/build.py, Makefile, tests/test_registry.py,
    data/models/registry.json, data/VERSION.json

- [x] Task 7: Dashboard tab D1 Exposures (P0)
  - Acceptance: dashboard/tabs/d01_exposures.py renders the seven D1
    panels from parquet only; loads in under 3 seconds; a regression
    test imports every tab and D0 still renders.
  - Test: tests/test_dashboard_d1.py (panel builders on fixtures, app
    and all tabs import).
  - Files: dashboard/tabs/d01_exposures.py, dashboard/app.py,
    tests/test_dashboard_d1.py

- [x] Task 8: Evaluate F2.0a, F2.0b, F2.0c and F2.1 to F2.6 (P0)
  - Acceptance: every criterion stored in sprints/E2/RESULTS.json with
    threshold, stored number and verdict (pass, fail, or pending with a
    reason); numbers computed from artifacts, never retyped; F2.0c
    includes the events.parquet audit check.
  - Test: tests/test_e2_results.py (all nine keys present, verdicts
    valid).
  - Files: sprints/E2/RESULTS.json, efb/evaluate.py extension,
    tests/test_e2_results.py

- [x] Task 8b: Exclude flagged rows and reused symbols from the E2 panel (P0)
  - Origin: F2.3 investigation. One flagged row, MI's +9542.9% on
    2026-05-18, moved the trailing 252d mean QLIKE from -6.61 to -1.82,
    and the same name turned out to be a spliced series rather than a bad
    day. CPWR, EP and POM are spliced in the same way.
  - Acceptance: volatility, momentum and portfolio code reads returns
    through hygiene.clean_returns; names with reused symbols leave the
    estimation panel and the exclusion is recorded in the TS-v1 registry;
    the successor criterion F2.6 is evaluated, records the four names and
    the 20 offending rows, and fails.
  - Test: tests/test_hygiene.py (clean_returns, series_break_tickers),
    tests/test_build_e2.py (the panel drops a spliced name).
  - Files: efb/hygiene.py, efb/build.py, efb/evaluate.py,
    docs/hygiene_ledger.md, docs/open_items.md

- [x] Task 9: Research deliverable: Beta and Volatility Estimation Study (P0)
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

## Close-out tasks (added 2026-09-10)

Rules for C1 to C4: no criterion already stored in RESULTS.json is
reworded or re-scored; a new finding gets a new ID; every number that
changes is written to docs/hygiene_ledger.md as old value, new value,
date, reason.

- [x] C1: Ticker identity check, registered as F2.6b
  - Acceptance: every ticker on the Wikipedia changes table's removed
    list is compared with the current holder of that symbol on yfinance,
    cached once to data/raw/yf_names.parquet and matched by name token
    overlap after stripping Inc, Corp, Co, Ltd, plc, Class A/B and
    punctuation; the table prints ticker, removed name, current name,
    match score, first and last valid price date and removal date. A
    match means the history is legitimate even if prices continue past
    the removal. No match means the symbol was reused: drop rows before
    the first valid date that belongs to the current company, or drop the
    ticker entirely when that date cannot be determined, and say so. Also
    flag any ticker with a gap above 60 business days between two live
    price segments. CPWR, EP, MI and POM must all be caught. F2.6b passes
    when the flagged list is stored in data/processed/ticker_identity.parquet
    and efb/build.py applies the exclusions itself. F2.6 keeps its
    recorded fail.
  - Test: tests/test_identity.py (token match, reused symbol detected,
    gap detection, exclusions applied by the build, F2.6b stored)
  - Files: efb/identity.py, efb/prices.py, efb/build.py, efb/evaluate.py,
    data/processed/ticker_identity.parquet, sprints/E2/PROBES.md

- [x] C2: Re-store E1 on the corrected data
  - Acceptance: make rebuild-e1 runs, F1.1 to F1.5 and F2.0a to F2.0c are
    re-evaluated, and sprints/E1/RESULTS.json carries a "revisions" key
    with old and new values side by side plus the data hash of each;
    notebooks/E1_walkthrough.ipynb re-executes against the new artifacts
    and re-renders; docs/research/E1_data_note.md gains an Addendum
    section stating what changed and why, with the original sections left
    untouched; the F1.3 and F1.5 numbers print before and after.
  - Test: tests/test_e1_revisions.py (revisions key present, old and new
    recorded, data hashes differ or match explicitly)
  - Files: efb/evaluate.py, sprints/E1/RESULTS.json,
    notebooks/E1_walkthrough.ipynb, docs/research/E1_data_note.md

- [x] C3: F2.3 diagnostic before the verdict is accepted
  - Acceptance: print the exact QLIKE target and the forecast horizon of
    each estimator; whether returns were scaled by 100 before the arch fit
    and how many names failed to converge; the win rate by calendar year
    and with 2020 excluded. Then run the aligned evaluation, one-step
    forecasts against next-day r^2 and 21-day forecasts (GARCH
    multi-step, EWMA flat, trailing flat) against 21-day realized
    variance, both over the same out-of-sample window with flagged rows
    excluded, and register it as F2.3b with the same 60% threshold.
    EWMA(0.97) stays the production estimator unless F2.3b shows GARCH
    winning for more than 70% of names, which becomes an open decision
    for E5 rather than a change now.
  - Test: tests/test_vol_alignment.py (one-step target, 21-day target,
    both stored with the same window and exclusions)
  - Files: efb/vol.py, efb/evaluate.py, sprints/E2/RESULTS.json,
    sprints/E2/PROBES.md

- [x] C4: MOM loading sanity check on the long/short momentum seed book
  - Acceptance: the book's TS-v1 loadings print with Newey-West SEs and
    t-stats; the MOM loading must be positive with |t| > 2, and if it is
    not, the factor share prints with and without MOM in the regressor set
    and the finding goes to the ledger and the deliverable. The seed book
    construction is not changed in E2.
  - Test: tests/test_portfolio_risk.py (MOM loading sign and t-stat on
    the seeded book, factor share both ways)
  - Files: efb/portfolios.py, sprints/E2/PROBES.md,
    docs/research/E2_exposure_study.md

- [x] C5: Close-out
  - Acceptance: make rebuild-e2 runs, VERSION.json and the TS-v1 registry
    entry carry the new data hash, the full test suite passes, and
    docs/research/E2_exposure_study.md gains a Close-out section with the
    C1 to C4 numbers.
  - Files: data/VERSION.json, data/models/registry.json,
    docs/research/E2_exposure_study.md, docs/hygiene_ledger.md

