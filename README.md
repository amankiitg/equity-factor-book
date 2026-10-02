# Equity Factor Book (EFB)

Learn the theory in Paleologo's *APM* and *EQI*, build the machinery, and develop
the judgment to run a systematic book: this repository is a systematic equity
risk and portfolio management stack, written from scratch on free data, one
module per sprint. It is not a search for an edge, since no signal here is
claimed to have one, and a documented negative result counts as a finished piece
of work if it prevents a bad decision later. The 13-sprint roadmap it implements
is in
[`docs/Equity_Factor_Book_Roadmap_v2.docx`](docs/Equity_Factor_Book_Roadmap_v2.docx)
(searchable text copy: [`docs/roadmap_v2.md`](docs/roadmap_v2.md)), and the prose
overview written for a reader who has not seen the project is
[`docs/research/STATUS_REPORT.md`](docs/research/STATUS_REPORT.md).

**Committed milestone**: Sprints E1 to E13 built to their current state, gates
RG-Data through RG-Operate answered, and the live paper book standing on Render
(Sprint E11). E12's attribution engine is built on branch `e12` and its criteria
wait on the live window; E13's credit port design note is written and complete.
The handoff files live in [`handoff/`](handoff/): the standing rules, the current
task, the reviewer's log and the implementer report.

## Branch state

`main` carries the live book. Render runs one service from it, the daily cron
`efb-live-daily` (the blueprint declares no other), and deploys on push, so a
merge to `main` is a deployment rather than a checkpoint. That one service starts
`scripts/run_cron.py` twice a weekday, at 15:30 and 22:30 UTC, and the hour in New
York decides which job runs: before noon the morning's fills reconciliation, from
16:00 the evening run. The live page is not on
Render: it is a Cloudflare Worker reading the run snapshot from a private R2
bucket, and the Streamlit app is a research view that runs locally.

One branch sits unmerged by design, and it merges after the flip.

- `e12` carries the attribution engine, `efb/attribution.py` and
  `live/attribution_job.py`: the evening attributes every stored day it has not
  attributed, the page shows the attribution, the skill test is written down, and
  the weekly review and the attribution build read the result. Its criteria are
  windowed on the live book, so they cannot be evaluated honestly until the window
  has thirty trading days behind it. It also carries the E11 and E12 walkthroughs,
  and the fix to a store guard test that fails on `main`.

`page`, `e13` and `alpha-refresh` are folded into `week1-orders` rather than merged
one at a time: the live page's sections, the credit port note and launch note with
their traceability tests, and the rebuilt alpha conversion with the E7 and E11
walkthroughs. The credit note describes the repository with E12 in it, because four
of the modules it maps are E12's, which is why that branch lands with E12 rather
than before it.

Until then `main` is what the cron runs, and the branch above does not change that.

## Live book

**https://efb-live-book.nutritrack.workers.dev**: the evening's book, one screen.
It sits behind Cloudflare Access, and signing in is an email one-time PIN to the
owner's address: without it, the page and its API answer a redirect to the login
rather than any content. It updates after each weekday evening run (the cron
fires at 22:30 UTC, inside the after-hours window) and shows the run's status and
target close, the book and the orders it produced, the factor exposures before
and after the hedge, and the run status line. It is served by a Worker that reads
the snapshot from a private R2 bucket. The book is paper only, and while `dry_run`
is true the page is showing the rehearsal rather than the live clock. See
[`web/README.md`](web/README.md) for the page's own setup and commands.

## Status

- [x] Repo skeleton and engineering standards (Roadmap Appendix B)
- [x] E1  Universe, returns, performance library, Hygiene Ledger, gate RG-Data
  (four of five criteria fail with stored numbers; F1.3 passes at 0.9564 and the
  survivorship bias is 365.10 bp per year). See
  [`docs/research/E1_data_note.md`](docs/research/E1_data_note.md)
  and [`sprints/E1/RESULTS.json`](sprints/E1/RESULTS.json).
- [x] E2  Time-series models, volatility, TS-v1 (registered diagnostic only, not
  champion-eligible). See
  [`docs/research/E2_exposure_study.md`](docs/research/E2_exposure_study.md).
- [x] E3  Cross-sectional model XS-v1, Fama-MacBeth premia, gate G1
- [x] E4  Covariance race, PCA-v1 and PCA-v1c, residual-factor audit
- [x] E5  Risk model evaluation; XS-v1 is the provisional champion, stress haircut
  1.8471. See
  [`docs/research/E5_risk_model_diagnostic.md`](docs/research/E5_risk_model_diagnostic.md).
- [x] E6  Hedging toolkit; the exact factor-mimicking-portfolio hedge is the policy
- [x] E7  Alpha lab; RG-Signal returned all six signals NULL. See
  [`docs/research/E7_signal_idio_momentum.md`](docs/research/E7_signal_idio_momentum.md).
- [x] E8  Construction on synthetic alpha; the proportional rule is the champion
- [x] E9  Transaction costs and the capacity curve
- [x] E10  Risk allocation and loss management; RG-Operate not cleared (item 5, the
  ongoing constituent source is stood up but not yet applied). See
  [`docs/research/RG_OPERATE.md`](docs/research/RG_OPERATE.md).
- [x] E11  The daily paper book (paper only, `dry_run` until the flip), gate G3
- [x] E12  Ex-post performance attribution; built on branch `e12`, criteria pending
  the live window
- [x] E13  Credit port design note; complete, document only. See
  [`docs/credit_port_design.md`](docs/credit_port_design.md).

## The live book

The book is a **documented null book**: `idio_momentum` through the full stack,
sized by the construction row the owner chose (the share-only floor at 20 shares,
which keeps 158 names) and hedged with the exact factor-mimicking-portfolio
hedge, paper only. Its factor-neutral IC is
-0.0031 (t -0.51) at horizon 21, null rather than negative, against a raw IC of
0.0121 (t 5.04) at horizon 1, read from data/alpha/summary.parquet. The loop
runs indefinitely (run_condition open_ended) with a 30-trading-day reporting
window that starts on day 1, the first session whose orders filled after the flip;
the clock is not started, `live/clock.json` records the voided earlier start, and
`sprints/E11/register_results.py` refuses to register a day the stored first live
run and first proposal do not agree on. Every evening reads the account before it
sizes anything and refuses unless the number Alpaca reports is the one
`EFB_ALPACA_ACCOUNT_ID` names, because EFB's paper keys and the credit lab's sit
under one login; an establishment evening additionally refuses if the account holds
anything or has an order working. Render runs the daily cron, `efb-live-daily`, which extends,
proposes, executes and reconciles; the blueprint is `render.yaml`. The live series
lives in Supabase; research artifacts stay in git and the evidence snapshot. The
store never falls back on its own: a local run (the research dashboard, a dry run,
the test suite) sets `EFB_STORE=local` to use the parquet files under
`live/state/`, and the cron does not, so a missing connection string there is an
error rather than a quiet write to a disk the next container never sees.

## Running things by hand

Four commands are run by hand rather than by the cron.

- **The local research console**: `make dashboard`. It first copies the linked
  sprint documents into the dashboard's static folder (the `publish` target) and
  then serves the Streamlit app headlessly. This is the research view, one tab per
  sprint; the live page is the separate Cloudflare Worker linked above.
- **The order-timing smoke test**: `python scripts/smoke_order_timing.py --symbol
  SPY --yes`, run between 16:00 and 20:00 New York time. The evening cron fires at
  22:30 UTC, which is 18:30 New York in summer and 17:30 in winter, inside the
  after-hours window. The script submits one share with the loop's own
  time-in-force, confirms the broker accepted it, and cancels it. It refuses to run
  without `--yes`, refuses outside that window, because an order accepted at 10:00
  proves nothing about the cron's own hour, and refuses a symbol that is not
  tradable. `--force-hour` exists for a deliberate out-of-hours probe and says in
  its output that it was used.
- **The weekly review**: `PYTHONPATH=. .venv/bin/python scripts/review_week.py`,
  with `--days 5` for the last five attributed days or `--artifact` for the seed
  book's own stored attribution. It prints one row per day: the P&L split into
  factor, idiosyncratic and cost against the total, realized factor P&L against the
  near zero the hedge promises, and cost realized against expected with turnover.
  It is built to be read on a Sunday.
- **The attribution build**, for after the live window:
  `PYTHONPATH=. .venv/bin/python scripts/build_attribution.py`. It writes
  `data/attribution/daily.parquet`, `monthly.parquet` and `timeseries.parquet` from
  a stored book and prints the three measurements the E12 memo quotes: the
  reconciliation residual per session, the hedge timing gap, and whether the
  session-dated design is computable a close earlier.

The last two are on branch `e12`, with the engine they read; the first two are on
`main`.

## Where the main documents are

- **The status report**, [`docs/research/STATUS_REPORT.md`](docs/research/STATUS_REPORT.md):
  the whole project in prose, written for a reader with a quantitative background
  and no knowledge of it. Start here.
- **The E11 launch note**, [`docs/research/E11_live_launch.md`](docs/research/E11_live_launch.md):
  the story of taking the book live, written for a listener who has never seen the
  project, from the order that would have gone the wrong way to the pre-launch
  reviews that caught it. Every figure in it is checked back to a stored file by
  `tests/test_e11_live_launch_traceability.py`.
- **The sprint walkthroughs**, `notebooks/E1_walkthrough.ipynb` and so on: one per
  sprint, each reproducing its sprint's numbers and asserting every printed value
  against the stored artifact it came from. The notebooks are the tracked form,
  E1 to E10 on `main` and E11 and E12 with the `e12` branch; the `.html` beside
  each one is rendered locally with `jupyter nbconvert` and is deliberately not
  committed.
- **The research deliverables**, under [`docs/research/`](docs/research/): one memo
  per sprint, the gate documents (`docs/research/RG_OPERATE.md`,
  `sprints/E7/RG_SIGNAL.json`), and the E12 attribution report,
  `docs/research/E12_attribution_report.md`, which is on the `e12` branch.
- **The sprint records**, under `sprints/E<n>/`: the PRD, the task list, the probe
  log and the criteria verdicts, each stored number in `RESULTS.json`.
- **The credit port design note**, [`docs/credit_port_design.md`](docs/credit_port_design.md):
  what transfers to corporate credit unchanged, what has to be re-specified, and
  the three places where unchanged is the wrong answer.
- **The handoff folder**, [`handoff/`](handoff/): the standing rules, the current
  task, the reviewer's log and the implementer's report. This is where work in
  progress is written down, and it is the first thing to read after the status
  report.

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
- `live/` - the paper-trading loop and its dashboard app, run locally (E11)
- `render.yaml` - the Render blueprint: one service, the daily cron
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
