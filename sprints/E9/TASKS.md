# Sprint E9 TASKS

Sprint E9, Transaction Costs and Capacity. Nine tasks, each with a test.
The alpha is the E8 synthetic alpha with a known IC; the synthetic label
travels with every number, and capacity is reported per rho because no real
signal passed RG-Signal.

- [ ] Task 1: the Corwin-Schultz probe and the spread estimates (P0)
  - Acceptance: `efb/costs.py` estimates the half-spread from the stored
    high/low/close panel and prints the probe result first. A test checks
    the estimates are finite on most names and correlate with size rank
    (F9.3) above 0.5.
  - Files: `efb/costs.py`, `tests/test_costs.py`

- [ ] Task 2: the square-root impact model and the cost function (P0)
  - Acceptance: `efb/costs.py` implements cost(delta w) = half_spread *
    |delta w| + k sigma sqrt(|delta w| AUM / ADV) + commission, with ADV
    from the stored volume panel and every parameter stated with its
    source. A test checks the impact term grows with the square root of
    trade size and that doubling AUM raises cost per dollar by about 41%.
  - Files: `efb/costs.py`, `tests/test_costs.py`

- [ ] Task 3: trade-toward-target and the turnover-penalized optimizer (P0)
  - Acceptance: `efb/costs.py` trades a fraction of the gap to target and
    `efb/optimize.py` gains a turnover-penalized objective. A test checks
    the penalized optimizer cuts turnover by more than 50% with less than
    20% ex-ante IR loss (F9.2).
  - Files: `efb/costs.py`, `efb/optimize.py`, `tests/test_costs.py`

- [ ] Task 4: the rebalance-frequency trade-off (P1)
  - Acceptance: `efb/costs.py` computes net IR against the rebalance
    cadence and stores the frontier. A test checks the curve is stored with
    a peak.
  - Files: `efb/costs.py`, `tests/test_costs.py`

- [ ] Task 5: the capacity curve and the halving AUM (P0)
  - Acceptance: `efb/costs.py` builds the net Sharpe versus AUM curve at
    each rho, stores the halving AUM and its sensitivity to the impact
    coefficient k. A test checks net Sharpe is monotone in AUM (F9.1) and
    the halving AUM is stored per rho (F9.4).
  - Files: `efb/costs.py`, `data/costs/*`, `tests/test_costs.py`

- [ ] Task 6: evaluate F9.1 to F9.4 into RESULTS.json (P0)
  - Acceptance: every criterion evaluated with a stored number and written
    to sprints/E9/RESULTS.json. A test compares stored against recomputed.
  - Files: `efb/evaluate.py`, `sprints/E9/RESULTS.json`, `tests/test_e9_results.py`

- [ ] Task 7: the cost and capacity memo and its traceability test (P0)
  - Acceptance: docs/research/E9_tcost_capacity.md with the cost model and
    its uncertainty, cost curves by size decile, the turnover versus IR
    frontier, the recommended cadence, the capacity curve with the halving
    AUM and its sensitivity to k, the practitioner conclusion and "What
    would falsify this?". A traceability test asserts every headline number
    matches a stored value.
  - Files: `docs/research/E9_tcost_capacity.md`, `tests/test_e9_memo.py`

- [ ] Task 8: dashboard D8 Cost and Capacity (P1)
  - Acceptance: `dashboard/tabs/d08_costs.py` with cost curves by size
    decile, pre and post cost Sharpe with SE, the turnover versus ex-ante
    IR frontier, and the capacity curve with the halving point marked.
    Every panel builder raises on an empty read.
  - Files: `dashboard/tabs/d08_costs.py`, `dashboard/app.py`,
    `tests/test_dashboard_d8.py`

- [ ] Task 9: the walkthrough, the render and the engineering close (P0)
  - Acceptance: notebooks/E9_walkthrough.ipynb with the hash cell, the
    Corwin-Schultz algebra by hand, one section per criterion, the capacity
    curve read live, the D8 panel map and the memo's evidence in citation
    order. Executed in one pass, rendered, published and linked. make
    rebuild-e9 added and make rebuild extended; VERSION.json over E1
    through E9; ledger and open items updated.
  - Files: `notebooks/E9_walkthrough.ipynb`, `Makefile`, `data/VERSION.json`,
    `docs/hygiene_ledger.md`, `docs/open_items.md`,
    `tests/test_e9_walkthrough_notebook.py`

## Order and stops

Tasks run in numeric order. Stop conditions: an earlier stored criterion
(F1.x to F8.x) changes verdict; a build, render or publish step fails in a
way two attempts cannot fix. A failing F9.x is recorded with its mechanism
and the run continues.
