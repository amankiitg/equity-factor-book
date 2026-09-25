# Equity Factor Book (EFB)

Learn the theory in Paleologo's *APM* and *EQI*, build the machinery, and develop
the judgment to run a systematic book. This repository implements the 13-sprint
roadmap in
[`docs/Equity_Factor_Book_Roadmap_v2.docx`](docs/Equity_Factor_Book_Roadmap_v2.docx)
(searchable text copy: [`docs/roadmap_v2.md`](docs/roadmap_v2.md)).

**Committed milestone**: Sprints E1 to E10 built, gates RG-Data through
RG-Operate answered, and the live paper book stood up on Render (Sprint E11,
Part B). The book runs indefinitely on `idio_momentum` through the full stack,
paper only. The handoff files live in [`handoff/`](handoff/): the standing
rules, the current task, the reviewer's log and the implementer report.

## Status

- [x] Repo skeleton and engineering standards (Roadmap Appendix B)
- [x] E1  Universe, returns, Hygiene Ledger, perf library (Sep 1 to 6), gate RG-Data
  - F1.3 passes (0.9564); F1.1, F1.2, F1.4, F1.5 fail with stored numbers;
    survivorship bias 365.10 bp per year recorded. See
    docs/research/E1_data_note.md and sprints/E1/RESULTS.json.
- [x] E2  Time-series factor models, volatility, TS-v1 (Sep 7 to 13)
  - F2.0a, F2.0b, F2.0c, F2.1, F2.2, F2.4 and F2.5 pass; F2.3 and F2.6 fail
    with stored numbers, so EWMA stays the production default. TS-v1 is
    registered as diagnostic only and is ineligible for champion under the
    pre-registered rule. See docs/research/E2_exposure_study.md and
    sprints/E2/RESULTS.json.
- [x] E3  Cross-sectional model, Fama-MacBeth, XS-v1 (Sep 14 to 20), gate G1
- [x] E4  Covariance, PCA-v1 and PCA-v1c
- [x] E5  Risk evaluation and the champion: XS-v1 is the provisional champion,
  stress haircut 1.8471. See docs/research/E5_risk_model_diagnostic.md.
- [x] E6  Hedging toolkit over the seed books
- [x] E7  Alpha lab; RG-Signal returned all six signals NULL. See
  docs/research/E7_signal_idio_momentum.md.
- [x] E8  Construction on synthetic alpha
- [x] E9  Cost model and the capacity curve
- [x] E10  Risk allocation and loss management; RG-Operate not cleared (item 5,
  the ongoing constituent source is stood up but not yet applied). See
  docs/research/RG_OPERATE.md.
- [x] E11  The live paper book (paper only, loop runs indefinitely)
- [ ] E12 to E13  Attribution and the credit port

## The live book

The book is a **documented null book**: `idio_momentum` through the full stack,
Procedure 6.3 plus the exact FMP hedge, paper only. Its factor-neutral IC is
-0.0031 (t -0.51) at horizon 21, null rather than negative, against a raw IC of
0.0121 (t 5.04) at horizon 1, read from data/alpha/summary.parquet. The loop
runs indefinitely (run_condition open_ended, day 1 2026-09-22) with a
30-trading-day reporting window. Render runs two services, `efb-live-dashboard`
(web) and `efb-live-daily` (the daily cron that extends, proposes, executes and
reconciles); the blueprint is `render.yaml` and the deployed URL is assigned by
Render at deploy time. The live series lives in Supabase; research artifacts
stay in git and the evidence snapshot.

## Corporate actions

The pipeline only appends, so a split never rewrites a stored row. What the
append path uses is the vendor's own split factor, which sits on the price row of
the session it takes effect on: the appended session's return is
`close * factor / previous close - 1`, computed from raw closes rather than from a
back-adjusted history, and the event is recorded on the run and named in the
evening message ("split: APH 2:1 applied"). Because a raw halving is a 50% move
and the E1 outlier flag is 50%, the move would otherwise sit right under the flag
that is supposed to catch it. Every appended session whose move is large is also
cross-checked against a refetch of the last stored session's adjusted close, and a
restated session that no split record explains stops the run before anything is
priced.

Three consequences, and they are the whole reason for the rule. Consumers of
returns compare two prices inside one basis, so they need no factor. Consumers of
price levels cross the seam and do: market cap is a close times a share count, and
at a split those move opposite ways, so the two factors cancel only when both come
from the same date's snapshot. And a held position keeps its notional, because the
broker doubles the shares and halves the price, so an unchanged target trades
nothing.

## Workflow

Sprints run sequentially. Do not open Sprint N+1 until Sprint N's exit criteria
are met, its walkthrough is rendered, and its research deliverable is written.

Each sprint follows three commands, or the equivalent `prd` / `dev` /
`walkthrough` skills:

| Command or skill | What it produces |
| --- | --- |
| `/quant-prd` | `sprints/E<n>/PRD.md`, `TASKS.md`, `PROBES.md` |
| `/quant-dev` | One task at a time, tests first, F criteria stored in `sprints/E<n>/RESULTS.json` |
| `/quant-walkthrough` | `notebooks/E<n>_walkthrough.ipynb`, rendered to HTML |

The command definitions live in `.claude/commands/`. Falsification criteria are
copied verbatim from the roadmap into each PRD and are not reworded after the
number is seen.

## Repository layout

See [`docs/engineering_standards.md`](docs/engineering_standards.md) for the
full tree and the engineering discipline. Quick map:

- `efb/` - the Python package, one module per sprint
- `data/` - parquet artifacts (raw, processed, model outputs); `VERSION.json`
  carries the content hash of every artifact
- `dashboard/` - one Streamlit app, one tab per sprint (D0 to D11)
- `sprints/` - one folder per sprint: PRD, TASKS, RESULTS, PROBES
- `docs/` - ledgers, research deliverables, standards
- `notebooks/` - hand-derived walkthroughs
- `live/` - the paper-trading loop and the Render dashboard (E11)
- `render.yaml` - the Render blueprint (dashboard web service plus daily cron)
- `scripts/` - the daily cron entrypoint and the Supabase provisioning script
- `.streamlit/` - the Streamlit server configuration
- `handoff/` - the standing rules, the current task, the reviewer's log, the
  report

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
make test
```
