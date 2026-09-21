# Sprint E8 TASKS

Sprint E8, Sizing and Portfolio Construction. Ten tasks, each with a test.
The synthetic alpha is a controlled experiment, never a backtest, and the
label travels with every number. The per-family alternative from Task 0b is
the one every champion-against-alternative comparison uses.

- [ ] Task 1: the synthetic alpha generator (P0)
  - Acceptance: `efb/size.py` builds z(i,t) = rho * standardized(e(i,t+h))
    + sqrt(1 - rho^2) * eps(i,t) over the E5 race grid at rho in
    {0.02, 0.05, 0.10} with five fixed seeds each, and converts it through
    the E7 contract alpha_i = IC * sigma_idio_i * z_i shrunk by kappa.
    Every frame is labeled synthetic. A test checks the measured
    cross-sectional IC of z against forward idio returns is close to rho
    and the seeds are fixed.
  - Files: `efb/size.py`, `tests/test_size.py`

- [ ] Task 2: the proportional and Sharpe rules with vol targeting (P0)
  - Acceptance: `efb/size.py` implements w proportional to alpha/sigma^2
    and to SR/sigma, each scaled to a book-level volatility target. A test
    checks the weights sum in the long/short sense, the ex-ante sigma hits
    the target, and the two rules coincide under the diagonal model.
  - Files: `efb/size.py`, `tests/test_size.py`

- [ ] Task 3: Procedure 6.3 and unconstrained mean-variance (P0)
  - Acceptance: `efb/size.py` sizes on D^-1 alpha, hedges factors with the
    E6 FMPs, and solves the closed form w = Sigma^-1 alpha / lambda. A test
    compares the two and pins F8.1's stored number.
  - Files: `efb/size.py`, `efb/optimize.py`, `tests/test_size.py`

- [ ] Task 4: the constrained optimizer (P0)
  - Acceptance: `efb/optimize.py` solves the cvxpy QP with gross, net,
    position caps, sector-neutral and beta-neutral equalities. A test
    checks every constraint's max violation is below 1e-8 (F8.3).
  - Files: `efb/optimize.py`, `tests/test_optimize.py`

- [ ] Task 5: multiple-signal combination and robustness (P0)
  - Acceptance: `efb/size.py` combines two synthetic signals with a known
    correlation, shrinks alpha by ridge lambda, and resamples with
    IC-consistent noise. A test pins the resampling dispersion and the
    lambda chosen per rho (F8.4).
  - Files: `efb/size.py`, `tests/test_size.py`

- [ ] Task 6: the construction run and artifacts (P0)
  - Acceptance: every construction, rho and seed runs over the grid and
    writes data/portfolios/{rule}/{weights,exposures,decomposition}.parquet
    with the INPUT/OUTPUT labels carried in the columns. A test checks the
    artifacts exist and the realized returns are computable.
  - Files: `efb/size.py`, `data/portfolios/*`, `tests/test_size.py`

- [ ] Task 7: evaluate F8.1 to F8.6 into RESULTS.json (P0)
  - Acceptance: every criterion evaluated with a stored number and written
    to sprints/E8/RESULTS.json, including the transfer-coefficient table
    per construction and rho (F8.5) and the champion-versus-alternative
    difference (F8.6). A test compares stored against recomputed.
  - Files: `efb/evaluate.py`, `sprints/E8/RESULTS.json`, `tests/test_e8_results.py`

- [ ] Task 8: the construction memo and its traceability test (P0)
  - Acceptance: docs/research/E8_construction_memo.md with the rule
    comparison table, the constraint set and rationale, the robustness and
    shrinkage, the exposure report, the stored numbers, the practitioner
    conclusion and "What would falsify this?". A traceability test asserts
    every headline number matches a stored value.
  - Files: `docs/research/E8_construction_memo.md`, `tests/test_e8_memo.py`

- [ ] Task 9: dashboard D7 Sizing and Optimizer (P1)
  - Acceptance: `dashboard/tabs/d07_sizing.py` with an inputs panel (alpha
    source, risk model version, target vol, constraints) and an outputs
    panel (weights, exposures, decomposition, ex-ante IR), every quantity
    labeled INPUT or OUTPUT, the side-by-side rule comparison, and a
    worked-example card following one stock from alpha to weight. Every
    panel builder raises on an empty read.
  - Files: `dashboard/tabs/d07_sizing.py`, `dashboard/app.py`,
    `tests/test_dashboard_d7.py`

- [ ] Task 10: the walkthrough, the render and the engineering close (P0)
  - Acceptance: notebooks/E8_walkthrough.ipynb with the hash cell, the
    synthetic-alpha construction by hand, one section per criterion, the
    G3 confirmation, the D7 panel map and the memo's evidence in citation
    order. Executed in one pass, rendered, published and linked. make
    rebuild-e8 added and make rebuild extended; VERSION.json over E1
    through E8; ledger and open items updated.
  - Files: `notebooks/E8_walkthrough.ipynb`, `Makefile`, `data/VERSION.json`,
    `docs/hygiene_ledger.md`, `docs/open_items.md`,
    `tests/test_e8_walkthrough_notebook.py`

## Order and stops

Tasks run in numeric order. Stop conditions: an earlier stored criterion
(F1.x to F7.x) changes verdict; a build, render or publish step fails in a
way two attempts cannot fix. A failing F8.x is recorded with its mechanism
and the run continues.
