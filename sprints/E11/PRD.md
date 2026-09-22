# Sprint E11 PRD: The Book: Daily Long/Short Paper Trading

Sprint E11, 2026-09-22. Tier 3. The sprint that assembles the full stack
into a daily long/short equity book that runs forward in paper for thirty
trading days, and that starts the clock that E12 waits on.

## Research framing, copied verbatim from the roadmap

- Academic question: What must be true of a research pipeline for it to run in production without look-ahead, and how is the ex-ante forecast reconciled to the ex-post outcome?
- Practitioner question: Can this portfolio actually be operated every day, unattended, with every decision explainable the next morning?
- Research question: Over 30 trading days, does ex-ante risk match ex-post, and does realized cost match the E9 model?

## The book this sprint trades

The book trades `idio_momentum` through the full stack: Procedure 6.3
sizing under the champion XS-v1, the exact in-model FMP hedge, the E8
constraint set, and E9 costs. It is documented as a **null book**. Its
factor-neutral IC is -0.0031 at t -0.51, null rather than negative, which
is why it survives the hedge that would strip `momentum_12_1`.

The expected E12 verdict is **luck**, written down now, before the clock
starts. Thirty days cannot show skill; the loop exists to prove the
machinery, not the signal. If E12 later reads anything other than luck,
that is a bug in the measurement, not a discovery.

## The owner's decisions, settled

- **E11 trades `idio_momentum` through the full stack**, documented as a
  null book. The expected E12 verdict is luck.
- **Paper only.** No real money, no real broker credentials, ever. Alpaca
  paper keys only, and never committed.
- **The universe stays split.** History is frozen on the pinned Wikipedia
  table; the live universe comes from the SPY archive, 2026-09-18 forward.
  The seam between the two sources is documented and never bridged.
- **The v8.x loop is reused for shape, not copied for domain.** Its loop
  shape, Option A governance and fail-safe guards are proven and are
  ported. Its dashboard is not inherited; D10 is built new.

## What is reused from v8.x, and why

Reused because they are operational machinery that does not depend on the
credit-trading domain, ported rather than copied verbatim:

| v8.x piece | what E11 keeps | what changes |
| --- | --- | --- |
| `execution/calendar_utils.py` | trading-day check, idempotency markers (`check_already_ran`, `record_run`) | state store moves to EFB artifacts |
| `execution/alpaca_paper.py` skeleton | `OrderSpec` legs, two named fail-safe guards, submit, poll fills, reconcile fills vs intent | alpha, universe, costs come from EFB E6 to E10 |
| Option A governance | the loop proposes, the rules decide, nothing discretionary; overrides logged and dated | decisions stored in EFB artifacts, not Supabase, unless Supabase is justified |
| Two fail-safe guards | position-size cap (NAV-relative) and traded-notional brake (absolute) | constants restated for the E11 book |

Rebuilt because they are the EFB stack, and this sprint exists to run them
end to end:

| EFB piece | what E11 uses |
| --- | --- |
| E7 `idio_momentum` | the alpha, residualized on the champion design |
| E8 Procedure 6.3 | sizing under the constraint set: net zero, gross at most 1, 5% per-name cap, sector-neutral, beta-neutral to the five non-market styles |
| E6 exact FMP hedge | the hedge that drives the worst exposure toward zero and the idio share toward 1.0 |
| E5 XS-v1 | the champion risk model with its stored stress haircut |
| E9 | the cost model, reused as is |
| E10 | the vol target that scales the book |

## The daily loop

- **Evening job** (`live/evening_job.py`): previous-close data only.
  Compute `idio_momentum` on the SPY-archive universe, Procedure 6.3
  sizing under the champion XS-v1, the exact FMP hedge, E8 constraints,
  E9 costs, E10 vol scale. Store the ex-ante risk decomposition and write
  the proposal to a dated artifact with its input hashes. Nothing executes.
- **Morning job** (`live/morning_job.py`): submit the proposal to Alpaca
  paper under the two fail-safe guards, reconcile fills against targets,
  store both. Option A governance: the loop proposes, the rules decide,
  nothing discretionary.
- **Reconciliation** (`live/`): forecast against outcome every day,
  ex-ante risk vs realized, realized slippage vs the E9 model, exposures
  vs limits, stored append-only.

## Pre-registered falsification criteria

Copied verbatim from `docs/roadmap_v2.md`:

| ID | criterion |
| --- | --- |
| F11.1 | 30 consecutive trading days unattended with zero missed proposals. |
| F11.2 | The ex-ante risk decomposition is stored every day and reconciles to the champion model's numbers on D2. |
| F11.3 | Realized book vol over the window sits inside the champion model's bias band from E5. |

## Deliverables and dashboard increment

- `live/evening_job.py`, `live/morning_job.py`, the reconciliation module
- `live/` state store on EFB artifacts, append-only, idempotent re-runs
- `sprints/E11/RESULTS.json` with F11.1 to F11.3, evaluated with stored
  numbers once the window closes
- `notebooks/E11_walkthrough.ipynb`, rendered and published
- Dashboard tab D10 Book Monitor, built new, not inherited from v8.x
- The 30-day clock recorded with day 1 and its end date

## Dashboard D10, the strategy-review view

Built for someone deciding whether the book is doing what it was built to
do, not for someone auditing a pipeline. It leads with the answer, not the
plumbing. Every number carries its n and its units. One idea per panel.
The null-book framing is impossible to miss. Every panel builder raises on
an empty read, per the D9 convention.
