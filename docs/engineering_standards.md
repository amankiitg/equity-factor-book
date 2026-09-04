# Engineering standards (Roadmap Appendix B)

Copied from the roadmap so the standards live next to the code. The roadmap is
the source of truth: `docs/Equity_Factor_Book_Roadmap_v2.docx` (searchable text:
`docs/roadmap_v2.md`).

## Repository structure

```text
equity-factor-book/
  data/
    raw/            prices.parquet, factors_ff.parquet
    processed/      returns.parquet, universe_membership.parquet, sectors.parquet
    models/         TS-v1/, XS-v1/, PCA-v1/, ...
    cov/ eval/ hedge/ alpha/ portfolios/ costs/ allocation/ attribution/
    VERSION.json
  efb/
    perf.py vol.py registry.py risk.py cov.py eval_risk.py hedge.py
    alpha.py hygiene.py size.py optimize.py costs.py allocate.py
    attribution.py
    models/ timeseries.py fundamental.py statistical.py
  dashboard/
    app.py          global sidebar, version and regime selectors, tab router
    tabs/           d00_data.py ... d11_attribution.py, methodology.py
  live/             evening_job.py, morning_job.py (from v8.x)
  notebooks/        E1_walkthrough.ipynb ... E12_walkthrough.ipynb
  sprints/          E1/ ... E13/  (PRD.md, TASKS.md, RESULTS.json, PROBES.md)
  docs/
    hygiene_ledger.md, multiple_testing_ledger.md, credit_port_design.md
    research/       E1_data_note.md ... E12_attribution_report.md
  tests/
  Makefile          rebuild, rebuild-e1, ..., test, dashboard
```

## Engineering discipline

- Typed, documented, tested: pytest coverage above 70%; mypy, black, ruff in
  pre-commit; the test suite never shrinks.
- Reproducible: fixed seeds; every artifact carries the data hash of its
  inputs; `make rebuild` reproduces the registry from raw.
- No look-ahead: anything used as a forecast at t is computed from data
  through t-1; every sprint runs a shift audit.
- Dashboard reads parquet and Supabase only; it never fits a model. A tab
  that needs a number not in parquet is a missing artifact, not a dashboard
  feature.
- Numbers over adjectives: every `/quant-dev` output prints values; every
  walkthrough reconciles to 1e-8.
- Ledgers are append-only and timestamped: the Hygiene Ledger (E1 onward) and
  the multiple-testing ledger (E7 onward).
- Research deliverables live in `docs/research/` and follow one template:
  research questions, methodology, stored numbers, practitioner conclusion,
  what would falsify this, open questions.
- No em dashes in any artifact: documents, notebooks, prompts, docstrings,
  dashboard text.

## Sprint exit checklist

- All `TASKS.md` items closed, each with a passing test
- Every F criterion evaluated with a stored number in `RESULTS.json` (pass,
  fail, or explicitly pending with a reason)
- Parquet schemas stable and documented in the PRD
- Registry entry written for any new model version
- Dashboard tab renders in under 3 seconds with full history; every earlier
  tab still renders
- Walkthrough notebook rendered to HTML and linked from the Methodology tab
- Research deliverable written, with its What-would-falsify-this section, and
  linked from the Methodology tab
- Ledger entries for every policy decision made during the sprint
- The sprint's PM question answered in one paragraph at the top of the
  deliverable

## Gates

- RG-Data, end of E1, before any model is fit
- RG-Signal, end of E7, before a signal feeds construction (E8) or the book
  (E11); synthetic-alpha fallback so a null signal still validates the
  construction machinery
- RG-Operate, end of E10, before the book runs (E11)

A gate that returns a negative answer has done its job: the number goes into
`RESULTS.json` and the research deliverable, and the next sprint adapts.
