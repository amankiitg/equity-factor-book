# 2026-11-23 rebalance readiness

Status: draft. Items 1-3 are open as PRs (#4 sector refresh, #6 corporate-actions
exclusion, #7 rehearsal); the live rehearsal is pending and is run by the owner's
main agent. This is the checklist the owner signs before the 2026-11-23 rebalance.

## What is different at 2026-11-23

- The 21-session cadence (anchored 2026-10-23) lands on a **rebalance day**.
- Item 1 (PR #4): the additive sector refresh runs in the evening for the first
  time at a rebalance, with the `BE`/`ILMN`/`P` hold-list through 2026-11-24.
- Item 2 (PR #6): a name the vendor returns nothing for (or a split factor with
  no record) is dropped for the night through "Excluded tonight" instead of
  stopping the run.
- Item 3 (PR #7): `scripts/rehearse_evening.py` runs the real entry point with a
  clock override and fail-closed writes, so the owner can rehearse it.

## Go / no-go checklist

- [ ] PRs #4, #6, #7 merged (Aman).
- [ ] Item 1 identity proof passed on 2026-11-04 **and** 2026-11-05: list every
      name that gains a row, show only those names enter the book, every other
      weight change explained.
- [ ] Item 3 rehearsal passes for 2026-10-29, 11-02, 11-03, 11-04, 11-05.
- [ ] Full-rebalance rehearsal for 2026-11-23 passes (below).
- [ ] KVUE/KMB handling correct: KVUE reported inactive/acquired, recorded as
      owed, never resent; KMB priced on its own name.
- [ ] No name-level stop: every drop is on the "Excluded tonight" or refused
      line, never a stopped run.
- [ ] Expected cost and turnover inside the book's normal band.
- [ ] Post-hedge exposures inside the 5% drift guard.

## Rehearsal commands (owner runs, keys in the environment)

`rehearse_evening` sets `EFB_DRY_RUN=true`, `EFB_FORCE_HOUR=true`,
`EFB_CADENCE=21`, `EFB_CADENCE_ANCHOR=2026-10-23`, `EFB_DRIFT_GUARD=0.05`,
`EFB_SNAPSHOT=off`, `EFB_SHORTABILITY_PRECHECK=true`. It reads the real store and
broker and **blocks every store write** (fail-closed).

```bash
# 1. The five closes item 3 rehearses:
python scripts/rehearse_evening.py 2026-10-29 2026-11-02 2026-11-03 2026-11-04 2026-11-05

# 2. The full rebalance, as if today were a rebalance day:
python scripts/rehearse_evening.py 2026-11-23
```

## What a passing full-rebalance rehearsal shows

- **legs** - the signed change per name with its position intent; nothing sent
  (dry run), so a leg that would refuse shows as a refusal, not an order.
- **turnover** - traded notional against the book's gross notional.
- **expected cost** - the E9 split (spread, impact, commission, borrow).
- **largest variance share** - the name with the largest share of portfolio
  variance after the hedge.
- **exposures** - post-hedge factor exposures, all inside the drift guard.
- **flips** - long<->short reversals, with the deferred second leg named.
- **exclusions** - `excluded_tonight` plus the standing `excluded`, each with its
  reason and age.
- **KVUE/KMB** - KVUE inactive/acquired, recorded as owed and never resent; KMB
  handled as its own name.
- **errors** - none: every name-level problem is on the exclusion/refused line,
  never a stopped run.

## Live verification pending

This agent does not run the rehearsal against the real store or broker and never
loads keys. The owner's main agent runs the commands above and reports: each
close's exit code, the "Excluded tonight" line, the KVUE/KMB handling, and the
full-rebalance legs/turnover/cost/variance-share/exposures/flips.

- [ ] Attribution bias fix (2026-11-06 failure): run
      `python scripts/repair_risk_lines.py` (dry run) on the real store - see
      `docs/owner_fixes/attribution_too_few_observations.md`.
