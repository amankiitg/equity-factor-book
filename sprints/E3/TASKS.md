# Sprint E3: Tasks

## Status: In Progress (Task 0 complete)

Rules: ten atomic tasks including Task 0, each with a test, worked in order.
Task 7 evaluates every F criterion and lands the walkthrough; Task 9 produces
the research deliverables. The two inherited open items are Task 8 (the
realized residual covariance, F3.8) and Task 9 (the conditional exposure time
series, F3.9), which is why the evaluation sits at Task 7 and is re-run by
Tasks 8 and 9 rather than being the last artefact to land. A criterion whose
artifact does not exist yet is written as fail with the note "artifact not
built yet", never omitted. OPTIONAL work sits in the Optional backlog at the
end and is dropped first when the seven-day schedule tightens; the gate date
never moves and a stored criterion is never narrowed.

- [x] Task 0: Probes for every descriptor, the shares source, and the E1 reference values (P0)
  - Acceptance: four probes printed with their tables into
    sprints/E3/PROBES.md. (a) Descriptor coverage: for each year end from
    2010 to 2026, the universe count and the number of names carrying each of
    size, beta, momentum, reversal, residual vol, liquidity and sector, plus
    the count with a complete descriptor row; the risk-free and factor tail
    (excess is all NaN after 2026-07-31 while r runs to 2026-09-03) reported
    in the same table. (b) Shares: download the shares history for the
    sector-mapped names, cache it to data/raw/shares_history.parquet, count
    the duplicate-dated rows and the de-duplication rule, count the
    split-sized steps as the as-filed evidence, print the first available date
    per name and the monthly ramp of names with a share count, and print the
    first trading day on which at least 300 names carry a complete descriptor
    row including a share count. (c) Sector: the mapped name count, the
    members per sector summary, and the number of days on which a sector has
    fewer than 5 members. (d) Value: book value reachability. A descriptor is
    not available until its probe has printed rows. The same task moves the E1
    Sharpe reference values out of prose: sprints/E1/RESULTS.json gains a
    reference_values block (annualized Sharpe, i.i.d. standard error, Lo
    (2002) standard error, their ratio, the market lag-1 autocorrelation), the
    E1 walkthrough asserts the recomputed values against that block instead of
    against the markdown, and docs/hygiene_ledger.md gains the dated shares
    correction entry (old text, new evidence, reason) plus the XS-v1
    parameters.
  - Test: tests/test_e3_probes.py (coverage table on fixtures, shares
    de-duplication and look_ahead flagging, the E1 reference block round trip
    including the notebook assert).
  - Files: efb/probes.py, sprints/E3/PROBES.md, sprints/E1/RESULTS.json,
    notebooks/E1_walkthrough.ipynb, docs/hygiene_ledger.md,
    tests/test_e3_probes.py
  - Completed: 2026-09-17. Tables appended to sprints/E3/PROBES.md as
    "Task 0, run 2026-09-17", 27 tests in tests/test_e3_probes.py. Findings
    that changed the design: XS-v1's first complete cross-section is
    2011-01-03 (momentum is the binding warm-up, 252 sessions below the
    300-name floor), not 2010-01-05; the vendor shares history is as filed
    rather than current-vintage, with 826 names asked and 773 returning a
    history, 61,002 duplicate rows dropped, 341 split-sized steps and
    1,245,448 look-ahead name-days, corrected into docs/hygiene_ledger.md as
    a dated entry; the sector restriction removes 41.9% of the 2010 index by
    name and 8.85% by market cap, now a new open item for E4; the value
    variant stays deferred on five quarters of period-end data. The E1
    reference_values block is stored in sprints/E1/RESULTS.json (additive
    edit, everything else byte-identical) and notebooks/E1_walkthrough.ipynb
    now reads it, prints it and asserts against it instead of the prose in
    docs/research/E1_data_note.md.

- [ ] Task 1: Market cap and the seven style descriptors through t-1 (P0)
  - Acceptance: market cap = close x shares, the share count on t being the
    last observation dated at or before t-1 (never a count filed later),
    forward-filled from each name's first observation and backfilled before it
    with a per-row look_ahead true; data/processed/market_cap.parquet with its
    schema; the seven style descriptors computed from data through t-1 with
    the windows and minimums in the PRD, the cap-weighted universe total
    return as the market proxy, and the 11 sector dummies; excluded tickers
    absent and never imputed; NaN never filled; descriptors.parquet written in
    the long schema; per-descriptor coverage printed.
  - Test: tests/test_fundamental_descriptors.py (momentum and reversal
    hand-computed on a fixture, the shift test that no descriptor row at t
    reads data after t-1, look-ahead flag boundaries, the stale/outlier/NaN
    exclusion counts).
  - Files: efb/models/fundamental.py, tests/test_fundamental_descriptors.py,
    data/models/XS-v1/descriptors.parquet

- [ ] Task 2: Standardization and orthogonalization (P0)
  - Acceptance: winsorization at plus or minus 3 MAD, then the z-score with a
    cap-weighted mean and an equal-weighted standard deviation, so the
    cap-weighted market portfolio's mean style exposure is zero to 1e-12;
    orthogonalization per the map, momentum on (beta, size) and residual vol
    on (beta), by cross-sectional regression with the residual
    re-standardized; both value_z and value_z_orth stored; the
    orthogonalization map read from the registry and recorded in the artifact.
  - Test: tests/test_fundamental_standardize.py (winsor bounds, cap-weighted
    zero mean, the orthogonalized descriptor uncorrelated with its regressors
    to 1e-10, a degenerate cross-section stays finite).
  - Files: efb/models/fundamental.py, tests/test_fundamental_standardize.py

- [ ] Task 3: Constrained weighted least squares, factor-mimicking portfolios, identification (P0)
  - Acceptance: f_uncon = (X'WX)^-1 X'W r with W = diag(sqrt mcap) normalized;
    the FMP rows A = (X'WX)^-1 X'W satisfy X' w_FMP(k) = e_k within 1e-8 for
    every factor k; the null direction is removed with a = sum_s w_s f_sector,s
    so cap-weighted sector factor returns sum to zero within 1e-12 on every
    day; the equivalence with an explicit constrained solve is asserted on a
    sample of days; fitted values and specific returns are identical with and
    without the identification; a rank-deficient cross-section is reported
    rather than silently solved.
  - Test: tests/test_fundamental_wls.py (recovery of known factor returns from
    synthetic data where the identity holds by construction, the constraint
    sum, the equivalence proof, the collinear-column case).
  - Files: efb/models/fundamental.py, tests/test_fundamental_wls.py

- [ ] Task 4: Factor returns, specific returns, cross-sectional R squared, exposures (P0)
  - Acceptance: factor_returns.parquet (f and f_pre_identification per factor
    per day), specific_returns.parquet, xs_r2.parquet with the daily R
    squared plus the model health columns (FMP identity maximum absolute
    error, the cap-weighted sector sum, the name count, the descriptor count);
    the shift test printed both ways proves X_{t-1} explains more than X_t;
    the daily universe count is stored and days below 300 names are reported
    and excluded; the exposure vector x = X'w is exposed as a function for any
    weight vector.
  - Test: tests/test_fundamental_factor_returns.py (R squared on synthetic
    data, the shift test direction, specific returns plus fitted equals the
    realized return, the thin-day rule).
  - Files: efb/models/fundamental.py,
    tests/test_fundamental_factor_returns.py

- [ ] Task 5: Factor covariance, specific variance, Sigma, the risk decomposition, the registry entry (P0)
  - Acceptance: F the EWMA factor covariance at half-life 90 business days
    with the Newey-West lag 2 correction, stored as an 18 x 18 matrix; D the
    EWMA specific variance at half-life 42 days shrunk toward the mean of the
    33 (sector, size tercile) buckets with the shrinkage weight n/(n+k), k =
    60, both raw and shrunk stored; Sigma = X F X' + D; the decomposition
    tables for both seed books with sigma_p, MCR_i = (Sigma w)_i / sigma_p,
    w_i MCR_i, percent of variance, the factor contributions x_k (F x)_k /
    sigma_p and x = X'w; factor variance plus idio variance equals w' Sigma w
    to machine precision and the contributions sum to sigma_p; the residual
    weight of names without descriptors reported; the registry gains XS-v1
    with champion false, eligible_for_champion true, the parameter block and
    the hashes, with champion_rule and family_notes unedited; efb/build.py
    gains build_e3_artifacts and rebuild_e3, hashes every new artifact into
    data/VERSION.json with previous_data_hash, and the Makefile implements
    rebuild-e3 in place of the stub that currently exits 1 and adds rebuild
    as the E1 through E3 entry point, which is the G1 one-command
    requirement.
  - Test: tests/test_risk.py (F symmetric positive definite, the variance
    identity, the MCR sum identity, shrinkage toward the bucket mean, the
    registry diff proving champion_rule is byte-identical) and
    tests/test_build_e3.py (the artifact set and its hashes, the hash round
    trip, the registry entry schema, and that rebuild-e3 no longer exits 1).
  - Files: efb/models/fundamental.py, efb/risk.py, efb/registry.py,
    efb/build.py, Makefile, tests/test_risk.py, tests/test_build_e3.py,
    data/eval/xs_risk_decomposition.parquet
- [ ] Task 6: Fama-MacBeth premia and dashboard tab D2 (P0)
  - Acceptance: data/eval/xs_fm_premia.parquet with the daily and annualized
    premium, the Newey-West lag 2 standard error, the t statistic, the day
    count and the priced label for every factor for the full sample and for
    the three pre-registered subperiods (2011-01-03 to 2015-12-31, 2016-01-01
    to 2020-12-31, 2021-01-01 to 2026-09-03), with every factor present in
    every subperiod and a premium with abs(t) below 2 labelled unpriced and
    kept; the D2 tab with the eight panels of the PRD spec reading parquet
    only, including the CSV upload path and the exposures against limits; D2
    loads in under 3 seconds and D0, Methodology and D1 still render.
  - Test: tests/test_fm_premia.py (Newey-West standard error on a synthetic
    autocorrelated series, every factor in every subperiod, the unpriced label
    survives), tests/test_dashboard_d2.py (every panel maps to a parquet
    column, the earlier tabs render).
  - Files: efb/models/fundamental.py, dashboard/tabs/d02_factor_risk.py,
    dashboard/app.py, tests/test_fm_premia.py, tests/test_dashboard_d2.py

- [ ] Task 7: Evaluate F3.1 to F3.9, render the walkthrough, publish the docs (P0)
  - Acceptance: sprints/E3/RESULTS.json holds every criterion with its
    threshold, stored numbers, verdict and note, plus the revisions block with
    data_hash, previous_data_hash, the changed list and an append-only
    history; a second run over unchanged artifacts reports changed false and
    appends no history entry; the evaluator reads every number from an
    artifact, and a criterion whose artifact does not exist is fail with the
    note "artifact not built yet"; notebooks/E3_walkthrough.ipynb runs end to
    end with no number typed by hand, every figure printed and asserted
    against its stored value, prints the closing checklist (criteria covered,
    asserts passed, the data hash, and confirmation that nothing was
    hardcoded), renders to HTML, and is linked from the Methodology tab with
    the two research notes, with the link opening the file rather than
    reloading the dashboard.
  - Test: tests/test_e3_results.py (the changed-detection over two identical
    runs, the criterion set is exactly F3.1 to F3.9, every stored number is
    reproducible from an artifact), tests/test_e3_walkthrough_notebook.py (the
    notebook exists, has no typed literal for any stored number, covers every
    criterion in the loop), tests/test_e3_docs_links.py (every link target
    exists in dashboard/static/docs and no file contains an em dash).
  - Files: efb/evaluate.py, sprints/E3/RESULTS.json,
    notebooks/E3_walkthrough.ipynb, dashboard/tabs/methodology.py,
    dashboard/publish.py, tests/test_e3_results.py,
    tests/test_e3_walkthrough_notebook.py, tests/test_e3_docs_links.py

- [ ] Task 8: Realized residual covariance for both seed books, F3.8 (P1, inherited open item 1)
  - Acceptance: the realized covariance of XS-v1 specific returns over
    trailing 252-day windows is computed for both seed books; the factor share
    of variance is reported twice for each book, once with the diagonal D and
    once with the realized residual covariance,
    w' Sigma_resid w replacing w' D w; both numbers are stored in
    data/eval/xs_residual_covariance.parquet and in sprints/E3/RESULTS.json;
    the evaluator is re-run and F3.8 passes when both numbers are stored,
    whatever they show; the average pairwise specific-return correlation
    within each sector is stored next to them, because it is the mechanism the
    difference measures; the risk report explains the difference with the
    numbers and states whether the diagonal assumption overstates or
    understates idio risk for each book.
  - Test: tests/test_residual_covariance.py (on synthetic specific returns
    with a known one-factor structure the realized covariance recovers the
    off-diagonal terms and the diagonal-only version does not; the window
    never reads past its end date).
  - Files: efb/risk.py, efb/evaluate.py,
    tests/test_residual_covariance.py,
    data/eval/xs_residual_covariance.parquet

- [ ] Task 9: Conditional exposure time series for the momentum book, F3.9, and the research deliverables (P1, inherited open item 2)
  - Acceptance: x_t = X_{t-1}' w for the momentum book is stored at every
    rebalance in data/eval/xs_exposure_timeseries.parquet, with the book's
    XS-v1 exposure to momentum and to size, so the book is priced from
    descriptor exposures recomputed at each rebalance rather than from
    full-sample betas; the stored series is reconciled in writing to every E2
    measurement (static name-level factor share 0.09681972392333447,
    regression loading 0.2884639400639966 with t 29.104952622365634,
    rolling-beta aggregate mean 0.06978002876927968 over 195 rebalances with
    range -0.3322050420277022 to +0.3904549841533205, static full-sample
    aggregate -0.016190070548666415), and the reconciliation says why a book
    that sorts on momentum every month carries a large dynamic exposure while
    full-sample name-level betas average it away; the evaluator is re-run and
    F3.9 passes; docs/research/E3_factor_model_note.md and
    docs/research/E3_risk_report.md are written with the sections the roadmap
    lists, the PM answer in one paragraph at the top, the premia table with
    the PM interpretation, the APM decomposition table for both books with
    the unintended bet and the top MCR names, the idio share both ways from
    Task 8, the verdict paragraph on XS-v1 pending E5, the deferred optional
    items with their reasons, and a section titled "What would falsify
    this?".
  - Test: tests/test_exposure_timeseries.py (the exposure series is linear in
    the weights, the reconciliation table covers every E2 number, no number in
    the notes is typed without an artifact source),
    tests/test_e3_research_note.py (the required sections exist, the notes
    quote only stored values, no em dashes).
  - Files: efb/risk.py, efb/evaluate.py,
    docs/research/E3_factor_model_note.md, docs/research/E3_risk_report.md,
    tests/test_exposure_timeseries.py, tests/test_e3_research_note.py

## Optional backlog (dropped first when the seven days tighten, in this order)

- [ ] OPTIONAL 1: The EXPERIMENTAL value variant (book to price). Deferred by
      Task 0 probe (d): the only reachable source returns five quarters at
      period-end dates with no filing date and the in info book value is
      current only, so no point-in-time panel exists. Written into the
      research note as pending with that reason.
- [ ] OPTIONAL 2: The two-pass residual volatility variant, residual vol from
      XS-v1's own specific returns instead of the one-factor market model
      residual, with the iteration count recorded.
- [ ] OPTIONAL 3: The orthogonalization sensitivity table (factor returns with
      and without orthogonalization) and the equal-weighting and top-300
      universe sensitivities. The orthogonalization itself stays in the main
      path; only the side-by-side tables are optional.
- [ ] OPTIONAL 4: The sector-size bucket granularity study, finer or coarser
      than 3 size terciles by 11 sectors.

## Gate checklist (G1, Sep 20)

- [ ] make rebuild runs E1 through E3 from raw parquet in one command
- [ ] registry holds TS-v1 and XS-v1 with their data hashes, champion_rule
      unedited
- [ ] F1 to F3 criteria all evaluated with stored numbers in the three
      RESULTS.json files
- [ ] all three walkthroughs rendered as HTML and linked from the Methodology
      tab, each opening the file
- [ ] research deliverable written and linked
- [ ] make lint and make test clean, and no em dashes in any file the sprint
      writes
