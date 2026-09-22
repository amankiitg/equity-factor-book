# Sprint E11 TASKS

Sprint E11, The Book: Daily Long/Short Paper Trading. Ten tasks, each
with a test. The book trades `idio_momentum` as a null book through the
full stack, paper only, on the SPY-archive universe. The clock is the
critical path: prefer a loop that runs today over a loop that is complete.

- [ ] Task 1: the evening job skeleton with trading-day and idempotency
  - Acceptance: `live/evening_job.py` skips non-trading days and never
    re-runs the same day twice; the run marker is written only on success.
  - Files: `live/evening_job.py`, `tests/test_e11_evening.py`

- [ ] Task 2: the live universe comes from the SPY archive, asserted
  - Acceptance: the evening job reads the universe from the SPY archive
    (2026-09-18 forward), never the frozen Wikipedia history, and asserts
    the source rather than assuming it.
  - Files: `live/evening_job.py`, `tests/test_e11_evening.py`

- [ ] Task 3: proposal from the full stack, stored with input hashes
  - Acceptance: `idio_momentum` alpha, Procedure 6.3 sizing under XS-v1,
    the exact FMP hedge, the E8 constraint set, E9 costs and the E10 vol
    scale produce a dated proposal artifact whose idio share after the
    hedge is stored alongside the hashes of every input.
  - Files: `live/evening_job.py`, `tests/test_e11_proposal.py`

- [ ] Task 4: Option A governance, nothing discretionary
  - Acceptance: the loop proposes and the rules decide; a dated decision
    (approve or reject) gates execution, overrides are logged and dated,
    and there is no path that executes without a decision.
  - Files: `live/morning_job.py`, `tests/test_e11_governance.py`

- [ ] Task 5: the two fail-safe guards, each proven to fire
  - Acceptance: the position-size cap (NAV-relative) and the
    traded-notional brake (absolute) are ported and named, each with a
    test that trips it and asserts the order is rejected and never
    submitted.
  - Files: `live/morning_job.py`, `tests/test_e11_guards.py`

- [ ] Task 6: paper submit and fill reconciliation
  - Acceptance: the proposal is submitted to Alpaca paper under the
    guards, fills are polled and reconciled against targets, and the dry
    run path records every order without credentials.
  - Files: `live/morning_job.py`, `tests/test_e11_execution.py`

- [ ] Task 7: daily reconciliation, forecast against outcome
  - Acceptance: ex-ante risk vs realized, realized slippage vs the E9
    model, and exposures vs limits are stored every day, append-only and
    idempotent on re-run.
  - Files: `live/reconcile.py`, `tests/test_e11_reconcile.py`

- [ ] Task 8: dashboard D10, the strategy-review view
  - Acceptance: leads with the answer and the null-book framing, every
    number carries n and units, one idea per panel, and every panel
    builder raises on an empty read.
  - Files: `dashboard/tabs/d10_book.py`, `tests/test_dashboard_d10.py`

- [ ] Task 9: start the thirty-trading-day clock
  - Acceptance: day 1 is recorded with its date and the thirty-day end
    date, stored in an artifact the report reads.
  - Files: `live/clock.py`, `tests/test_e11_clock.py`

- [ ] Task 10: evaluate F11.x and render the walkthrough
  - Acceptance: F11.1 to F11.3 are copied verbatim from the roadmap into
    `sprints/E11/RESULTS.json`, evaluated with stored numbers, and
    `notebooks/E11_walkthrough.ipynb` builds, executes and renders.
  - Files: `efb/evaluate.py`, `sprints/E11/RESULTS.json`,
    `sprints/E11/build_walkthrough.py`, `tests/test_e11_results.py`
