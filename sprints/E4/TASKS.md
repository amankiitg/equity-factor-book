# Sprint E4 TASKS

Sprint E4, Statistical Factor Models and the Covariance Lab. Ten tasks
including Task 0, each with a test. A stored criterion is never reworded and no
number in a walkthrough is typed by hand. Stop conditions are marked where they
belong in the order.

- [x] Task 0: the three probes, before any estimation (P0)
  - Acceptance: eigenvalue feasibility with N, N/T and the MP edge for both
    universes; the sector and constituent source probe for ten known delisted
    names with the EDGAR parser and the yfinance identity check; the momentum
    factor's realized volatility by exposure tercile. All three printed in
    full, recorded in `sprints/E4/PROBES.md`, and seven offline tests pass.
  - Files: `efb/probes.py`, `tests/test_e4_probes.py`, `sprints/E4/PROBES.md`
  - Completed: 2026-09-20. Commit `21d983e`. Two brief numbers were corrected:
    the predicted-vol swing is 0.003656 max minus min, not 0.0055, and the
    quiet-factor explanation is refuted.

- [x] Task 1: PCA and the registration of PCA-v1 (P0)
  - Acceptance: `efb/models/statistical.py` with standardization to the
    correlation matrix, SVD eigendecomposition, the k-factor covariance, and
    three factor counts (scree, MP edge from the window's own N and T,
    cross-validated held-out likelihood). Varimax rotation and a correlation
    matrix against the XS-v1 factors. Residual PCA on the XS-v1 specific
    returns with the largest residual eigenvalue reported against its own MP
    edge. `data/models/PCA-v1/{loadings,factor_returns,eigenvalues}.parquet`
    written and the registry entry created with the parameters the run used.
    Tests: the eigendecomposition reproduces the sample covariance to machine
    precision at full rank, the MP edge matches `(1 + sqrt(N/T))^2`, the
    factor returns are unit-variance portfolios, the held-out likelihood is
    maximized at the selected k, and the residual eigenvalue against the edge
    is reported.
  - Files: `efb/models/statistical.py`, `efb/build.py`, `efb/registry.py`,
    `data/models/PCA-v1/`, `tests/test_statistical.py`

- [x] Task 2: the covariance laboratory and the out-of-sample test (P0)
  - Acceptance: `efb/cov.py` with sample, EWMA, Ledoit-Wolf linear shrinkage
    with the intensity estimated from the data, constant correlation,
    eigenvalue clipping, and the three factor estimators TS-v1, XS-v1 and
    PCA-v1. Each returns a matrix, a condition number and a parameter count.
    The out-of-sample minimum-variance portfolio test on rolling 504-day
    windows applied to the next 21 sessions with no re-estimation, written to
    `data/eval/cov_horse_race.parquet` and printed as the comparison table.
    Tests: each estimator is symmetric and positive definite on a random
    window, the shrinkage intensity lands in [0, 1], clipping leaves the
    largest eigenvalues untouched, the minimum-variance weights sum to one
    and reproduce the closed-form volatility, and the horse race is stable
    under a repeated run.
  - Files: `efb/cov.py`, `efb/build.py`, `data/cov/`,
    `data/eval/cov_horse_race.parquet`, `tests/test_cov.py`
  - STOP CONDITION 2: if the sample covariance wins the out-of-sample
    minimum-variance test, that is an estimation bug, print the table and stop.

- [x] Task 3: where the momentum book's miss lives, four measurements (P0)
  - Acceptance: 3a the predicted variance decomposition by source within each
    tercile, momentum contribution, every other factor and idio, with the
    implied momentum share tested against the 5 percent estimate; 3b the
    confound check, tercile membership by calendar year and the market
    factor's realized volatility by tercile, with an explicit statement of
    whether the reading is an exposure or a period effect; 3c the
    orthogonality test, the realized covariance between the book's factor
    component and its specific component overall and by tercile, explaining
    how realized total volatility of 0.029207 can sit below a predicted factor
    component of about 0.052; 3d the half-life sweep at 21, 42 and 90 with the
    bias by tercile at each, reported as secondary. F4.5 stored.
  - Files: `efb/cov.py`, `data/eval/xs_momentum_tercile_decomposition.parquet`,
    `data/eval/xs_halflife_sweep.parquet`, `tests/test_tercile_diagnostics.py`

- [x] Task 4: the survivor restriction as a measurement (P0)
  - Acceptance: 4a the same-period style-only design, the full 825-name panel
    against the 502 sector-mapped names over identical dates, comparing style
    factor returns, Fama-MacBeth premia, mean cross-sectional R squared and
    mean specific variance; 4b the 2020-onward comparison labelled as
    confounding universe with period; 4c the excluded names' return and
    volatility differential against the included names for 2010 to 2016. All
    three stored. F4.6 stored.
  - Files: `efb/models/fundamental.py` (style-only entry point),
    `data/eval/xs_survivor_measurement.parquet`,
    `tests/test_survivor_measurement.py`

- [x] Task 5: registry v1, the dashboard version selector and D3 (P1)
  - Acceptance: `efb/registry.py` v1 with a schema carrying the champion flag,
    the champion rule untouched and one entry per version; a selector in
    `st.session_state` wired into D0 through D3 so every tab renders under any
    version; `dashboard/tabs/d03_covariance.py` with the eigenvalue spectrum
    against the MP edge, the explained variance curve, the PCA against
    fundamental correlation matrix, the estimator comparison table with
    condition number and parameter count, the Task 3 half-life comparison, and
    the selector. Tests: every D3 panel builder raises on an empty read, every
    earlier tab's builder still renders under each registered version, and the
    registry schema validates.
  - Files: `efb/registry.py`, `dashboard/app.py`, `dashboard/tabs/d03_covariance.py`,
    `tests/test_registry.py`, `tests/test_dashboard_d3.py`

- [x] Task 6: evaluate every criterion into RESULTS.json (P0)
  - Acceptance: F4.1 to F4.6 evaluated with a stored number each and written
    to `sprints/E4/RESULTS.json` with the previous criteria untouched, the
    revisions block reporting any moved number, and the data hash. STOP
    CONDITION 3 applies to F4.2: a count outside 3 to 15 prints the spectrum,
    the edge and N/T and stops the sprint.
  - Files: `efb/evaluate.py`, `sprints/E4/RESULTS.json`,
    `tests/test_e4_results.py`

- [x] Task 7: the research deliverable (P0)
  - Acceptance: `docs/research/E4_covariance_memo.md` with the PM answer in
    one paragraph, the horse-race table with a recommendation per use for the
    optimizer, hedging and risk reporting, the residual factor audit, the Task
    3 verdict with its four measurements, the Task 4 numbers, the E5 candidate
    versions, and a "What would falsify this?" section. Every number read from
    an artifact.
  - Files: `docs/research/E4_covariance_memo.md`, `docs/open_items.md`

- [x] Task 8: the walkthrough and its render (P0)
  - Acceptance: `notebooks/E4_walkthrough.ipynb` with cell 1 asserting the data
    hash against the registry, every figure read from an artifact and asserted
    against its stored value, the forbidden-literal scan over every code cell,
    the by-hand derivations (eigendecomposition and MP edge, Ledoit-Wolf
    intensity, one out-of-sample minimum-variance portfolio, the Task 3 tercile
    recomputation at one alternative half-life), one section per criterion, the
    D3 panel-to-column map with the non-empty guard, the E5 inheritance
    section and the credit port note. Rendered to HTML, published, and the
    Methodology link checked.
  - Files: `notebooks/E4_walkthrough.ipynb`, `notebooks/E4_walkthrough.html`,
    `dashboard/tabs/methodology.py`, `tests/test_e4_walkthrough_notebook.py`

- [x] Task 9: engineering, ledger, open items, commit and push (P0)
  - Acceptance: `make rebuild-e4` and `make rebuild` both run E1 through E4
    end to end; `VERSION.json` and the registry share one artifacts hash; the
    hygiene ledger carries an entry with old value, new value, date and reason
    for every policy decision this sprint made; `docs/open_items.md` restates
    the survivor restriction and the equal-weight coverage item with the Task 4
    numbers and closes or restates the momentum bias item with the Task 3
    verdict; full suite and lint clean; committed and pushed.
  - Files: `Makefile`, `data/VERSION.json`, `docs/hygiene_ledger.md`,
    `docs/open_items.md`

## Order and stops

Tasks run in numeric order. Task 0 is done. Tasks 1 and 2 are the P0 pair whose
result decides whether the sprint continues: the estimator comparison table is
printed and checked against STOP CONDITION 2 before Task 3 starts. STOP
CONDITION 3 is evaluated inside Task 6 and reported before Tasks 7 to 9 run.
