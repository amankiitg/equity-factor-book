# Sprint E12: ex-post performance attribution (PRD)

Source: `docs/roadmap_v2.md`, "Sprint E12: Ex-Post Performance Attribution".
Tier 3. Needs E11: the live book has to exist before its P&L can be attributed.

## Research questions

**Academic.** How is realized P&L decomposed into factor and idiosyncratic
components under a factor model, and how are skill and luck separated
statistically?

**Practitioner.** Why did I make or lose money, was it the bet I intended, and
would a risk manager agree with my story?

**Research.** Is the book's P&L explained by intended idio bets, does
holdings-based attribution agree with the returns-based view, and is any of it
distinguishable from zero?

## Objective

Explain every dollar the book made or lost: factor versus idio P&L from holdings,
selection versus sizing versus timing, time-series attribution as a cross-check,
the seven-way decomposition ported from the ETF book, and an honest skill-versus-
luck verdict with Sharpe standard errors.

## Foundation

The roadmap's formula, and the one change this sprint had to make to it, measured
before anything was built:

    Factor P&L_t = (X_{t-1}' w_{t-1})' f_t by factor
    idio P&L_t   = w_{t-1}' e_t
    total = factor + idio + cost, reconciled to 1e-10

The exposures are the design the hedge zeroed, dated the previous close, and the
holdings are the book that close put on. The reconciliation, however, is only
exact when the factor returns and the specific returns are read against the
**session-dated** design: measured on 2026-09-08, 2026-09-18 and 2026-09-21,
`|X_t f_t + u_t - r_t|` is 0.000e+00 median and 6.9e-18 max, while the roadmap's
`X_{t-1}` pairing misses the panel's total return by 1.0e-03 to 2.0e-03 in median
and up to 2.2e-02. Both numbers are reported: the session-dated design is what the
model priced and what reconciles, and the previous-close design is what the hedge
actually held. The gap between them is the subject of the hedge-timing item, not a
correction to either.

## Implementation scope

- `efb/attribution.py`: holdings-based attribution, one row per session - factor
  P&L by factor, idio P&L, cost, the reconciliation residual, the book's own
  exposures under both design vintages, the raw CAPM-beta line, realized versus
  forecast volatility with the bias statistic, and the fill and cost columns.
- `data/attribution/{daily,monthly,timeseries}.parquet`: the sprint's stored
  artifacts, built from the seed books now and from the live store after the flip.
- The `efb.attribution` table and the evening wiring: after each evening run,
  attribute every stored day not yet attributed, from stored positions and the
  XS-v1 artifacts. A failure is logged and never stops the trading run.
- The live page's attribution section: cumulative P&L split into factor, idio and
  cost, the hedge's factor P&L per day, the raw-beta line, and realized versus
  expected cost.
- `scripts/review_week.py`: the week's P&L per day, realized factor P&L against the
  near-zero the hedge promises, cost realized versus expected, fill differences and
  forecast versus realized volatility, with a plain-English summary, working on
  however many days exist.
- `docs/research/E12_attribution_report.md` and `notebooks/E12_walkthrough.ipynb`,
  scaffolded on the seed books so the live run only swaps inputs.

## Pre-registered falsification criteria

Numeric thresholds written before the numbers were seen; each is evaluated with a
stored number in `sprints/E12/RESULTS.json`.

| ID | Criterion | Status |
| --- | --- | --- |
| F12.1 | Holdings-based factor P&L plus idio P&L plus costs equals total P&L to 1e-10 every day. | Exercised on the seed books; re-evaluated every live day |
| F12.2 | Time-series attribution betas agree with average holdings-based exposures within one standard error. | Pending: needs 30 live days |
| F12.3 | The reported Sharpe carries its SE and no skill is claimed unless t exceeds 2. The expected verdict is luck; write it down. | Machinery built; verdict pending 30 live days |

The thresholds are the roadmap's, copied verbatim, and they are not restated.
F12.2 and F12.3 are evaluated on the live book and cannot be closed on seed data:
the seed books are a research construction with no account, no costs and no
fills, and the sprint's own intuition says what 30 days can and cannot show.

**F12.3's expected verdict, written before the live numbers exist: luck.** Thirty
days cannot distinguish a 1.0 Sharpe from zero at any useful power, and the
sprint's exit condition is that the report says so with a number rather than with
an adjective.

## Deliverables

- `efb/attribution.py` and its tests.
- `data/attribution/daily.parquet` (one row per session), `monthly.parquet` (the
  same rows aggregated by month) and `timeseries.parquet` (the returns-based
  cross-check: book P&L regressed on the factor returns).
- The `efb.attribution` table, created with the SQL in `TASKS.md`.
- The evening wiring and its failure isolation.
- The live page's attribution section.
- `scripts/review_week.py`.
- `docs/research/E12_attribution_report.md` and the walkthrough.

## Failure modes to look for

The roadmap's, unchanged: exposures from the wrong date breaking the
reconciliation; costs omitted; the seven-way port mislabeling carry. The first one
is measured in this sprint rather than argued about: the reconciliation uses the
session-dated design because that is what the stored artifacts are exact against,
and the previous-close design's contribution is reported as its own number.

## What would falsify this

Reconciliation fails; the two methods disagree beyond standard error; P&L
concentrated in one regime or one name; performance disappearing after controlling
for known factors.

## Exit criteria

F12 evaluated; D11 rendered; walkthrough rendered; the APM and EQI coverage map
checked off in the attribution report; the research deliverable written and linked.
