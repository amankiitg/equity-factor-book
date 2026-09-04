---
description: Generate the PRD and TASKS for an EFB sprint. Usage: /quant-prd E1
argument-hint: [E1..E13]
---

Read `docs/roadmap_v2.md` first (or the docx it was extracted from). If earlier
sprints exist, read the latest sprint's `WALKTHROUGH.md` and `PRD.md` before
writing anything.

Determine the sprint number from `$ARGUMENTS` (for example `E1`). If none is
given, use the sprint after the highest `sprints/E<n>/` folder that exists.
Work sequentially: never write Sprint N+1 before Sprint N's exit criteria are
met, its walkthrough is rendered, and its research deliverable is written.

Rules that apply to every sprint:
- Max 10 atomic tasks, each with a test. Two of the tasks are always the
  research deliverable and the evaluation of every falsification criterion.
- Falsification criteria are copied verbatim from the roadmap and are never
  reworded after the number is seen. If a threshold turns out to be wrong, the
  next sprint registers a new criterion with a new ID.
- Output: `sprints/E<n>/PRD.md`, `sprints/E<n>/TASKS.md`, and
  `sprints/E<n>/PROBES.md` where the roadmap asks for probes.
- Copy the sprint's research framing (three questions plus the research
  deliverable) into the PRD verbatim.

For E1 use the verbatim prompt below. For E2 and E3 copy the
`/quant-prd, Sprint E<n>` block verbatim from `docs/roadmap_v2.md`. For E4
onward copy that sprint's `/quant-prd` block and follow the same structure:
objective, focus areas, requirements, research framing, output.

---

## Verbatim prompt for Sprint E1

/quant-prd
This is Sprint E1 of the Equity Factor Book (EFB) project. Nothing exists
yet except the repo skeleton and the engineering standards in the roadmap
appendix.
Objective:
Build the reproducible daily equity data layer and the Hygiene Ledger that
every later sprint reads from. The sprint ends with parquet artifacts, a
written ledger of every data decision, a performance-metrics library, and
dashboard tab D0. No model is fitted in this sprint.
Task 0 (before anything else): probe scripts. For each source below,
print row count, first and last date, ticker coverage, NaN share, and
paste the printed output into sprints/E1/PROBES.md. A source is not
"available" until its probe has printed rows.
- yfinance daily OHLCV and adjusted close, S&P 500 members (current plus
  recoverable deleted names), 2010 to today
- Wikipedia S&P 500 constituents table and the "Selected changes" table
- Kenneth French library: FF5 daily, Momentum daily, Short-term reversal
  daily, 12 industry portfolios daily
- GICS sector per ticker
- Shares outstanding via yfinance: record whether history is returned or
  only the current value
- Risk-free rate: FF RF column, cross-checked against FRED DTB3
Focus areas:
- Universe membership matrix (date x ticker) rebuilt from the changes
  table; survivorship bias measured, not assumed away
- Adjusted close audit (splits, dividends); total vs price return
- Returns: simple, log, excess over daily RF; aggregation rules (EQI Ch2)
- Stylized-facts panel: fat tails, vol clustering, autocorrelation of r
  and r^2 (EQI Ch2)
- Hygiene Ledger docs/hygiene_ledger.md: missing-data policy, stale-price
  detection (zero-return runs >= 5 days), outlier policy (|r| > 50%
  flagged, never silently winsorized in raw), delisting handling,
  timezone and date alignment, point-in-time flag per field
- efb/perf.py: Sharpe with standard error (i.i.d. and Lo 2002),
  annualization, max drawdown, hit rate, slugging (EQI Ch3, APM Ch3, Ch8)
Requirements:
- Exact formulas with every input and output labeled
- Parquet schemas (columns, dtypes, index) for data/raw/prices.parquet,
  data/processed/returns.parquet, universe_membership.parquet,
  factors_ff.parquet, sectors.parquet
- data/VERSION.json with a content hash of every artifact
- Pre-registered falsification criteria F1.1 to F1.5 copied verbatim from
  the roadmap, each with its numeric threshold
- Dashboard tab D0 spec: coverage heatmap (ticker x month), missing and
  stale counts, universe size over time, corporate-action and outlier
  event log, ledger rendered in-app, data version in sidebar; reads
  parquet only, never recomputes
- Max 10 atomic tasks, each with a test
- One command rebuilds everything: make rebuild-e1
Output:
- sprints/E1/PRD.md
- sprints/E1/TASKS.md
- sprints/E1/PROBES.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: What is a return, and which definition (simple, log,
  excess) is correct for which operation: aggregation through time,
  aggregation across assets, and risk measurement?
- Practitioner question: Can I trust the prices, the universe and the
  risk-free rate underneath every number this book will ever show?
- Research question: Is a free, survivorship-affected universe good enough
  to support factor-model research, and how large is the bias it
  introduces, in basis points per year?
- Research deliverable: Data Quality and Universe Note, written for
  a senior quant or risk manager; it must contain the methodology, the
  stored numbers, the practitioner conclusion, and a section titled
  "What would falsify this?". A negative verdict is a complete
  deliverable.
- The TASKS.md must include one task that produces the deliverable and
  one that evaluates every falsification criterion listed below.
