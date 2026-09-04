# Equity Factor Book (EFB)

Learn the theory in Paleologo's *APM* and *EQI*, build the machinery, and develop
the judgment to run a systematic book. This repository implements the 13-sprint
roadmap in
[`docs/Equity_Factor_Book_Roadmap_v2.docx`](docs/Equity_Factor_Book_Roadmap_v2.docx)
(searchable text copy: [`docs/roadmap_v2.md`](docs/roadmap_v2.md)).

**Committed milestone**: Gate G1, Sunday September 20, 2026. Sprints E1 to E3
running end to end. Later dates are indicative and re-planned at each gate.

## Status

- [x] Repo skeleton and engineering standards (Roadmap Appendix B)
- [ ] E1  Universe, returns, Hygiene Ledger, perf library (Sep 1 to 6), gate RG-Data
- [ ] E2  Time-series factor models, volatility, TS-v1 (Sep 7 to 13)
- [ ] E3  Cross-sectional model, Fama-MacBeth, XS-v1 (Sep 14 to 20), gate G1
- [ ] E4 to E13  See the roadmap sprint plan

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
- `live/` - evening and morning paper-trading jobs (E11)

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
make test
```
