task_id: e11-setup
status: in_progress
base_commit: c26302151fdffce5c14965b9c70f36314e749992

## Goal

Stand up Sprint E11's daily paper-trading loop so the thirty-trading-day clock
can start, and clear the two small items the owner settled on 2026-09-22. The
clock is the critical path: every day of setup is a day E12 waits, so prefer a
loop that runs today over a loop that is complete.

## The owner's decisions, settled. Build on these, do not revisit.

- **E11 trades `idio_momentum` through the full stack**: Procedure 6.3 sizing
  plus the exact in-model FMP hedge, documented as a **null book**. Its
  factor-neutral IC is -0.0031 at t -0.51, null rather than negative, which is
  why it survives the hedge that would strip `momentum_12_1`. The expected E12
  verdict is luck, written down before the clock starts.
- **Paper only.** No real money, no real broker credentials, ever. Alpaca paper
  keys only, and never committed.
- **The universe stays split.** History is frozen on the pinned Wikipedia table;
  the live universe comes from the SPY archive, 2026-09-18 forward. Do not
  re-run the universe reconstruction. The seam between the two sources is
  documented and never silently bridged.
- **The v8.x loop is at `/Users/amankesarwani/PycharmProjects/credit-trading-lab`.**
  Read it before planning: `execution/`, `dashboard/`, `scripts/`,
  `render.yaml`, `.streamlit/`, `sprints/v8.1`, `sprints/v8.6`.

**Guidance, not a template.** Reuse its loop shape, its Option A governance and
its fail-safe guards, because those are proven. **Do not inherit its dashboard.**
The owner wants the strategy-review dashboard materially nicer and more
intuitive than the v8.x one: built for someone deciding whether the book is
doing what it was built to do, not for someone auditing a pipeline. Lead with
the answer, not the plumbing. State every number with its n and its units, keep
one idea per panel, and make the null-book framing impossible to miss. Treat the
old dashboard as a list of things that must be available somewhere, not as a
layout to copy.

## Steps

**S1. F10.1b, per the owner's approval.** Re-register F10.1b against F10.1's
original threshold, "within 10% at the median", verdict **fail** at the
horizon-matched gap. Old criterion, threshold, verdict and stored numbers go
into the `revisions` block with the new ones beside them. The mechanism to
record: the horizon fix cuts the gap from 296% to about 26% and does not close
it, and part of what is left is that Magdon-Ismail gives an expected maximum
drawdown while the simulation reports a median, which accounts for roughly 4
points of the remainder. Update the E10 memo and walkthrough from the artifacts.

**S2. Archive the Wikipedia side.** `constituent_crosscheck` compares SPY
against the **live** Wikipedia page, which is kept nowhere, so today's record
cannot be rebuilt tomorrow. Snapshot the fetched constituents table one dated
file per fetch, same shape as the SPY archive, into `data/VERSION.json` and the
evidence snapshot. Report the size cost.

**S3. Read the v8.x loop and write `sprints/E11/PRD.md` and `TASKS.md`.** Copy
F11.x verbatim from `docs/roadmap_v2.md`; check the strings against the roadmap
yourself. In the PRD, state plainly what is reused from v8.x, what is rebuilt,
and why. Include the null-book label and the pre-written E12 verdict.

**S4. The evening proposal.** `live/evening_job.py`. Build tomorrow's target
book: `idio_momentum` as alpha, Procedure 6.3 sizing under the champion XS-v1,
the exact FMP hedge, the E8 constraint set, E9 costs. Universe from the SPY
archive, never the frozen history. Write the proposal to a dated artifact with
its inputs' hashes. **Nothing executes here.**

**S5. The morning execution.** `live/morning_job.py`. Submit the proposal to
Alpaca paper, reconcile fills against targets, store both. Option A governance
from v8.x: the loop proposes, the rules decide, nothing discretionary. Two
fail-safe guards, ported and named, each with the condition that trips it and
the action it takes. A guard that cannot fire is not a guard; prove each one
fires with a test.

**S6. Daily reconciliation and state.** Forecast against outcome, every day,
stored. Use the project's own artifacts for state unless you have a reason to
add Supabase; if you do add it, say why and keep credentials out of the repo.

**S7. Dashboard D10, the strategy-review view.** See the guidance above. This is
the one the owner will actually read. Every panel builder raises on an empty
read, per the D9 convention.

**S8. Start the clock.** Once S4 to S6 run end to end on one paper day, record
day 1 with its date and the thirty-day end date, and say so plainly at the top
of the report. Then `make test`, `make lint`, `make verify-evidence`.

## Acceptance

1. `make test` passes with at least 595 tests, `make lint` clean,
   `make verify-evidence` exits 0.
2. F10.1b reads `fail` against the verbatim F10.1 threshold, with the old values
   in `revisions` and the mean-versus-median note stored. No other E10 criterion
   moves. No F1.x to F9.x verdict moves.
3. The Wikipedia snapshot is dated, hashed in `data/VERSION.json`, present in
   `evidence/MANIFEST.json`, and `make verify-evidence` still exits 0.
4. F11.x in `sprints/E11/RESULTS.json` are byte-identical to the roadmap.
5. The evening job produces a proposal from `idio_momentum` with the FMP hedge,
   and the proposal's idio share after the hedge is stored. The universe used is
   the SPY archive; assert it, do not assume it.
6. Both fail-safe guards have a test that makes each one fire.
7. No credential, key or token appears in any committed file. State how you
   checked.
8. The 30-day clock has a recorded day 1 and end date, or the report says
   plainly why it could not start and what is missing.
9. No em dashes in any file touched.

## Stop only if

- Any F1.x to F10.x criterion other than F10.1b changes verdict.
- Alpaca paper cannot be reached, or would need anything other than paper keys.
- A step would need the universe reconstruction, or real money.
- Setup cannot start the clock within this task. Then stop, commit what runs,
  and report exactly what blocks day 1. Do not half-start the loop.

Everything else you decide and record: the state store, the proposal artifact
schema, which v8.x pieces are reused against rebuilt, and the D10 layout.

## Report back

`handoff/REPORT.md`, every number read from an artifact.

**Table 1, the clock.** Day 1 date, end date, trading days elapsed, or what
blocks it.

**Table 2, F10.1b.** Old and new criterion, threshold, verdict and stored
numbers, and the revisions entry.

**Table 3, the proposal.** Date, names, gross, net, idio share after the hedge,
predicted vol, expected cost, and the universe source with its as-of date.

**Table 4, the guards.** Per guard: name, condition, action, and the test that
fires it.

**Table 5, reuse.** Per v8.x component: reused, adapted or rebuilt, and why.

**Table 6, no-change.** Per sprint E1 to E10: criteria, verdicts changed.

**Include the Verification section per STANDARDS.** Rules 19 and 20: pasted
command output for the three gates, every headline number with its file and key,
`git diff --stat` from `base_commit`, the seven yes-or-no questions each with an
evidence line, and anything you decided that I might disagree with.
