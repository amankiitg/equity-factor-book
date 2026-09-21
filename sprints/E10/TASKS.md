# Sprint E10 TASKS

Sprint E10, Dynamic Risk Allocation and Loss Management. Ten tasks, each
with a test. The input is the synthetic book's net returns on corrected
costs, at the (rho, phi) configuration whose net annualized Sharpe is
closest to 1.0, plus the two seed books.

- [ ] Task 1: pick the design book and store its net return series (P0)
  - Acceptance: `efb/allocate.py` finds the (rho, phi) whose net Sharpe is
    closest to 1.0 on the corrected capacity curve, states it, and stores
    the per-rebalance net return series under data/allocation/.
  - Files: `efb/allocate.py`, `tests/test_allocate.py`

- [ ] Task 2: Kelly and fractional Kelly with the SE of SR (P0)
  - Acceptance: full Kelly f* = mu / sigma^2, fractional Kelly with c set
    from the SE of the Sharpe, the growth curve, and the cost of
    over-betting when SR is overstated by one SE. Stored as
    data/allocation/kelly.parquet.
  - Files: `efb/allocate.py`, `tests/test_allocate.py`

- [ ] Task 3: the drawdown distribution, simulated and analytical (P0)
  - Acceptance: the simulated maximum drawdown distribution against the
    Magdon-Ismail analytical approximation at the median, within 10%
    (F10.1). Stored as data/allocation/kelly.parquet drawdown block.
  - Files: `efb/allocate.py`, `tests/test_allocate.py`

- [ ] Task 4: vol targeting and the realized-vol dispersion (P0)
  - Acceptance: scale_t = sigma_target / sigma_hat_t applied to the book,
    the dispersion of realized annual vol across years reduced by more
    than 40% (F10.3). Stored as data/allocation/voltarget.parquet.
  - Files: `efb/allocate.py`, `tests/test_allocate.py`

- [ ] Task 5: stop-loss efficiency with the i.i.d. bootstrap control (P0)
  - Acceptance: the stop-loss does not improve Sharpe on i.i.d.
    bootstrapped returns (the control); on the real book the result is
    reported either way (F10.2). Stored as data/allocation/stoploss.parquet.
  - Files: `efb/allocate.py`, `tests/test_allocate.py`

- [ ] Task 6: drawdowns by VIX regime (P0)
  - Acceptance: drawdown depth and recovery within VIX terciles stored,
    the risk budget written per regime in the memo.
  - Files: `efb/allocate.py`, `tests/test_allocate.py`

- [ ] Task 7: evaluate F10.1 to F10.3 into RESULTS.json (P0)
  - Acceptance: every criterion evaluated with a stored number and written
    to sprints/E10/RESULTS.json.
  - Files: `efb/evaluate.py`, `sprints/E10/RESULTS.json`, `tests/test_e10_results.py`

- [ ] Task 8: the risk policy memo and its traceability test (P0)
  - Acceptance: docs/research/E10_risk_policy.md with the Kelly analysis,
    the drawdown and regime tables, the stop-loss verdict and the
    vol-targeting rule. A traceability test asserts every headline number
    matches a stored value.
  - Files: `docs/research/E10_risk_policy.md`, `tests/test_e10_memo.py`

- [ ] Task 9: dashboard D9 Risk Allocation (P1)
  - Acceptance: the Kelly calculator with labeled inputs and outputs, the
    vol-target simulation, the stop-loss efficiency curves and the
    drawdown distribution against the analytical approximation. Every
    panel builder raises on an empty read.
  - Files: `dashboard/tabs/d09_risk_allocation.py`, `dashboard/app.py`,
    `tests/test_dashboard_d9.py`

- [ ] Task 10: the walkthrough, the render, RG-Operate and the close (P0)
  - Acceptance: notebooks/E10_walkthrough.ipynb with the hash cell, one
    section per criterion, the D9 panel map and the memo's evidence in
    citation order. Executed, rendered, published and linked. make
    rebuild-e10 added; VERSION over E1 through E10; ledger and open items
    updated; RG-Operate answered with stored numbers.
  - Files: `notebooks/E10_walkthrough.ipynb`, `Makefile`, `data/VERSION.json`,
    `docs/hygiene_ledger.md`, `docs/open_items.md`, `docs/research/RG_OPERATE.md`,
    `tests/test_e10_walkthrough_notebook.py`

## Order and stops

Tasks run in numeric order. Stop conditions: an earlier stored criterion
(F1.x to F9.x) changes verdict; a build, render or publish step fails in a
way two attempts cannot fix. A failing F10.x is recorded with its
mechanism and the run continues.
