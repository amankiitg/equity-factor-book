# Sprint E13 TASKS

Sprint E13, Credit Port Design, a document-only sprint. Nine tasks. Task 1
produces the deliverable; task 8 evaluates every falsification criterion; the
rest build the parts of the note the roadmap's scope list and F13.1 require. No
task writes model code, and no task touches an E1 to E12 artifact.

- [ ] Task 1: the design note that produces the deliverable
  - Acceptance: `docs/credit_port_design.md` exists, states its audience and its
    premise, marks the mathematics that is asset-class agnostic against the data
    that is not, and states plainly that it cites no credit data.
  - Files: `docs/credit_port_design.md`

- [ ] Task 2: the schematic credit X matrix and the return column
  - Acceptance: a three-bond matrix with named columns and units, an excess return
    over a duration-matched Treasury as the return column, and the three candidate
    return definitions with what each one breaks.
  - Files: `docs/credit_port_design.md`

- [ ] Task 3: the factor mapping table, with what breaks
  - Acceptance: every row of the roadmap's Appendix A appears with its credit
    counterpart and its formula status, plus a column naming what actually breaks,
    and the rows the roadmap marks unchanged are tested rather than repeated.
  - Files: `docs/credit_port_design.md`

- [ ] Task 4: the required topic sections
  - Acceptance: universe and identity, survivorship with defaults and fallen
    angels, the return definition, the factor model with DTS, specific risk at
    issuer and bond level, hedging with CDX and Treasury futures, costs from
    TRACE, and the live loop with staleness and illiquid pricing each appear as
    its own section, each closing with what transfers, what changes and what
    breaks.
  - Files: `docs/credit_port_design.md`

- [ ] Task 5: the module map, every module with a status and a reason
  - Acceptance: every module in the repository appears in the map with one of
    unchanged, re-specified or dropped, and one sentence of reason.
  - Files: `docs/credit_port_design.md`

- [ ] Task 6: the open questions, each tied to an EFB number
  - Acceptance: every question names the EFB result that motivates it, with the
    stored file it was read from, so a question with no evidence behind it cannot
    survive review.
  - Files: `docs/credit_port_design.md`

- [ ] Task 7: the defect classes and the phased build plan
  - Acceptance: every defect class this project hit appears with its credit form
    and the file it is recorded in, and the build plan gives each phase exit
    evidence as a stored number.
  - Files: `docs/credit_port_design.md`, `handoff/PROJECT_CONTEXT.md`,
    `handoff/LOG.md`, `handoff/REPORT.md`, `docs/hygiene_ledger.md`,
    `docs/open_items.md`

- [ ] Task 8: evaluate every falsification criterion and register the verdict
  - Acceptance: F13.1, the falsification statement and the exit criteria are
    copied verbatim from the roadmap into `sprints/E13/RESULTS.json`, each is
    evaluated with a stored number, and the module count registered there is the
    count the test measures. Also asserts that every citation in the note resolves
    to a file in the repository and that the note carries no em dashes.
  - Files: `sprints/E13/RESULTS.json`, `tests/test_e13_design_note.py`

- [ ] Task 9: the sprint files and the Methodology tab link
  - Acceptance: the PRD and TASKS exist with the research framing and the criteria
    copied verbatim, and the design note is linked from the Methodology tab, whose
    own test asserts every linked document exists.
  - Files: `sprints/E13/PRD.md`, `sprints/E13/TASKS.md`,
    `dashboard/tabs/methodology.py`, `tests/test_dashboard_docs.py`
