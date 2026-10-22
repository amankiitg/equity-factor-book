# The rebalance calendar: `EFB_CADENCE`, the drift guard, and the deferred reversal

Branch `cadence-flag`, merged to `main` on 2026-10-22 with **every flag off**: the
default is the daily loop, byte for byte, and the identity proof below is the gate
that merge passed. No Render variable has been set; `docs/turn_on_monthly.md` is
the switch, and the owner sets it.

`docs/research/ic_decay.md` and `docs/research/cadence_study.md` recommend
rebalancing every 21 sessions; `docs/research/daily_design_study.md` adds what a
monthly book costs in exposure and what a drift guard costs to fix. This branch is
all three as flags whose defaults are today's behaviour.

## The flags

| variable | meaning | default |
|---|---|---|
| `EFB_CADENCE` | sessions between rebalances. `1` (or unset, or empty) is the daily loop the book runs today. A whole number below 1, a fraction or a word is refused in the log and treated as unset. | `1` |
| `EFB_CADENCE_ANCHOR` | the session the calendar counts from, `YYYY-MM-DD`. The anchor is session 0 and is therefore itself a rebalance. A date that is not a session snaps back to the last session on or before it. | the close being priced |
| `EFB_DRIFT_GUARD` | a fraction of NAV. On a hold day, if the held book's worst absolute factor exposure is past it, the book takes the minimum-norm correction that makes it neutral, under the active hedge mode, and every name it moves is forced. The exposure it reports is the one **after the $250 order minimum**, not the projection's. `off`, `none`, `0` and `false` are all "no guard"; anything else that is not a fraction in (0, 1) is refused in the log and treated as unset. | unset (no guard) |

`EFB_FLOOR_RELEASE` keeps its own meaning and is unchanged; the band is simply
fixed (see B6 below) so that it can be turned on at all.

A close is a **rebalance day** when `(sessions since the anchor) % k == 0`. Every
other close is a **hold day**. At `k = 1` every close is a rebalance, which is
why the default is byte-identical to today: the whole calendar is one line of
arithmetic that says "yes" for every session.

## What a hold day does

Everything the evening does, except trade:

- **data**: `extend_archives`, `extend_prices`, `extend_shares`, `extend_returns`
  and `extend_model` run exactly as they do today. The book is priced on the same
  artifacts.
- **the book**: the proposal is **the held book** - the previous proposal's
  weights, unchanged, on the names tonight's universe and model still carry. It is
  not renormalized: a name that left drops out and gross falls with it, which is
  the truth about the book. Nothing is sized, hedged or floor-enforced, because
  none of it is being traded.
- **marks, reconciliation, attribution, snapshot, page**: unchanged. The manifest
  and the snapshot say it was a hold (`run_status.cadence.day == "hold"`), and the
  page's pill reads **`hold day`**, green, with `hold day, next rebalance <date>`
  in the headline. A hold is a normal, green state: it is the loop doing what it
  was asked to do.
- **orders**: only the forced reasons. The order path takes an allow-list
  (`morning_job.target_orders(..., forced=...)`) and, on a hold day, emits a leg
  only for a name in it - plus every close, which is always allowed because a
  position the book no longer carries is a state it cannot keep, and every sign
  flip, which is a position the account and the book disagree about.

### Every forced reason wired in

| reason | where it comes from | what it does |
|---|---|---|
| **left universe** | `manifest["left_universe"]`: held names tonight's universe or model no longer carries | a close, `-held` |
| **corporate action** | the run's own `splits` and `spinoffs` for the close | the leg the action needs |
| **not shortable** | `manifest["dropped_no_short"]`, the broker's lending feed | the name leaves the book |
| **no risk estimate** | `manifest["dropped_no_risk"]`, the model cannot measure it | the name leaves the book |
| **no usable close** | `manifest["dropped_no_price"]`, no price to quantize on | the name leaves the book |
| **reversal** | a held position whose sign the target book does not have | the close, then the other side tomorrow |

The first five are named on the manifest and in the run's record
(`hold_forced_names`); the reversal needs no name because the filter lets a sign
flip through by construction. On the shadow window below, the only hold day that
traded is 2026-10-05, and its three legs are the first reason: CTVA, PSKY and WBD
left the 2026-10-05 universe.

### A missed rebalance

A scheduled rebalance with no completed run makes the next successful evening a
rebalance. The completion record is the one the loop already writes - this job's
own `efb.run_status` row for the close, with status `ok` or `incomplete` - so
**nothing new is stored**: the gap is the missing row, and `live/cadence.py` reads
it. If the record cannot be read at all (a tree with no store, a store that is
down), no gap is inferred and the calendar says so in a warning: promoting every
hold day to a rebalance on a store failure would quietly undo the calendar.

## B5: the cost horizon

**What it was.** `live/evening_job.py` charged the borrow on the short leg over a
fixed `HORIZON = 21` sessions, whatever the cadence:

```python
borrow_bps = costs_mod.BORROW_RATE * short_gross * (HORIZON / TRADING_DAYS) * 1e4
```

That is the only term in the construction that amortizes anything over a holding
period. Spread, commission and impact are the cost of a **trade** and are charged
per trade; the borrow is the cost of **holding** the short leg for a horizon.

**What it becomes.** With `EFB_CADENCE=k > 1` the horizon is `k`, so the borrow is
charged over the time the book is actually held - `k / 252` instead of `21 / 252`.
At `k = 1` and at the default the argument is `None` and the expression is the
one above, unchanged. The manifest records the choice as
`expected_establishment_cost_bps` (which now includes the longer borrow) and the
code path says which horizon it used in `_cost_decomposition`'s docstring.

## B6: the floor band could not run

Found by the churn study and fixed here. `floor_book_violations` ended with
`below_floor(shares, prices, dollar_floor, share_floor)` against the **full**
floor, and `build_proposal` raises when that list is non-empty. But
`EFB_FLOOR_RELEASE` exists precisely to keep a held name that has fallen **below**
its floor and is still above `release x floor`, so the check contradicted the flag
by construction: the first rebalance where the band bound raised "the enforced
floor book fails its checks and must not trade" and the evening produced no book.

The check is the band's own now: the same `_releasable` mask the floor search uses,
given `sticky` and `release`, so the search and the check cannot disagree about
which kept names are inside the band. At `release = 1.0` - the default, and every
caller that does not pass it - `_releasable` returns the mask untouched, so the
check is exactly what it was.

## The proofs

### B7: identity with every flag unset

`build_proposal(store=False)` for each close, on two code trees with the same cut
`data/` (the R2 seed plus the store appendix truncated to the close), the
`previous` book from `efb.positions` and the `nav` from `efb.nav` - the same
apparatus the nov11 merge used (`/tmp/nov11merge/a2_identity.py`):

| close | names main / branch | max abs weight difference | kept_gross | n_kept | excluded identical |
|---|---|---|---|---|---|
| 2026-10-14 | 176 / 176 | **0.0** | 0.9999999999999999 | 176 | yes |
| 2026-10-15 | 169 / 169 | **0.0** | 1.0 | 169 | yes |
| 2026-10-16 | 170 / 170 | **0.0** | 1.0 | 170 | yes |
| 2026-10-19 | 169 / 169 | **0.0** | 0.9999999999999999 | 169 | yes |

**Max abs weight difference over all four closes: 0.0**, name for name, with the
same `dropped_no_price` and the same `excluded` list on every close.
(`examples: 2026-10-19 traded $412,452 on both trees, identical.)`

### B8: the shadow run, `EFB_CADENCE=21` from the 2026-10-01 anchor

`scripts/cadence_shadow.py`, `store=False`, no broker, one cut tree (2026-10-19),
the book carried forward exactly as the loop carries it. Orders are what
`morning_job.target_orders` builds against the *dollars* held.

| close | day | held book | orders | traded | next rebalance |
|---|---|---|---|---|---|
| 2026-10-01 | **rebalance** | no | 186 | $985,941 | 2026-10-30 |
| 2026-10-02 | hold | yes | 0 | $0 | 2026-10-30 |
| 2026-10-05 | hold | yes | **3** | $9,815 | 2026-10-30 |
| 2026-10-06 | hold | yes | 0 | $0 | 2026-10-30 |
| 2026-10-07 | hold | yes | 0 | $0 | 2026-10-30 |
| 2026-10-08 | hold | yes | 0 | $0 | 2026-10-30 |
| 2026-10-09 | hold | yes | 0 | $0 | 2026-10-30 |
| 2026-10-12 | hold | yes | 0 | $0 | 2026-10-30 |
| 2026-10-13 | hold | yes | 0 | $0 | 2026-10-30 |
| 2026-10-14 | hold | yes | 0 | $0 | 2026-10-30 |
| 2026-10-15 | hold | yes | 0 | $0 | 2026-10-30 |
| 2026-10-16 | hold | yes | 0 | $0 | 2026-10-30 |
| 2026-10-19 | hold | yes | 0 | $0 | 2026-10-30 |

- **One rebalance, twelve holds**, and the next rebalance is 2026-10-30 (the 21st
  session after the anchor).
- **The only hold-day orders are the three forced closes on 2026-10-05** - CTVA,
  PSKY and WBD, the names that left the universe that day - and that is exactly
  the forced set the manifest names (`left_universe`). Every other hold day sends
  nothing.
- **What the calendar saved, over these 13 closes**: $985,941 traded on the
  monthly path against **$6,092,348** on the daily path, which is 84% less.
  (Orders: 189 against 2,387.) The window holds one rebalance, so this is the
  cost of the 12 closes that were not rebalanced, not a full year's turnover.

### The tests

- `tests/test_cadence.py`: 20 fast tests (the flag, the calendar, the anchor, the
  missed rebalance, the unreadable record, the held book, the forced list, the
  order filter, the daily path unchanged, the reversal) and 2 slow ones that
  build **whole proposals** on the real tree: one with `EFB_CADENCE=21` **and**
  `EFB_FLOOR_RELEASE=0.5` together (the B6 defect's own case), and one rebalance
  build with the band on.
- The gate (`pytest tests/ -q -m "not slow and not requires_live_tree and not
  merge_guard"`) on this branch: **14 failed, 1598 passed** - the same fourteen
  ids `docs/known_test_failures.md` lists, no new ones.
- `make lint` clean; `npx tsc -b` clean; `npx vitest run`: **233 passed**, including
  three new cases that pin the hold-day pill (`hold day` green, the missed-rebalance
  wording, and a document without the block reading exactly as before).
- `make lint` needed one pre-existing fix: `tests/test_live_panel_parity.py` fails
  `black --check` on `origin/main` too (two asserts Black would restate). The branch
  carries the format-only change so the lint gate means something.

### B7 (re-run 2026-10-22, after the guard, the reversal fix and the manifest gating)

Every flag unset, `main` at `606ba5d` against this branch, one cut tree
(`/tmp/nov11merge/cut-2026-10-20/data`), the last four closes the tree prices.

**Weights**, `build_proposal(store=False)`:

| close | n_kept main / branch | kept_gross main / branch | same names | **max abs weight difference** |
|---|---|---|---|---|
| 2026-10-15 | 159 / 159 | 1.0 / 1.0 | yes | **0.0** |
| 2026-10-16 | 173 / 173 | 1.0 / 1.0 | yes | **0.0** |
| 2026-10-19 | 169 / 169 | 1.0 / 1.0 | yes | **0.0** |
| 2026-10-20 | 153 / 153 | 1.0 / 1.0 | yes | **0.0** |

**The manifest, key for key** - the owner's rule that a flag-less run writes the
manifest it always wrote. Both trees dumped the **whole** manifest for those four
closes and they were diffed, key by key:

```
main vs branch, all four closes: 8 differences
  ~2026-10-15.code_commit: 606ba5d7... -> 37d010e1...     (the two trees are different commits)
  ~2026-10-15.floor_search_seconds: 0.0657 -> 0.0678      (wall clock)
  ... the same two keys on the other three closes ...
```

The same tree run twice differs on `floor_search_seconds` alone, which is what makes
those two keys the answer rather than an excuse: **every other key of the manifest is
identical**, including the seven the branch used to add - `cadence`, `drift_guard`,
`held_book`, `left_universe`, `reversal_targets`, `target_book_held_back` and
`unfilled_remainder`. They are emitted only when `EFB_CADENCE > 1`
(`tests/test_cadence_manifest_identity.py` pins that, and that a calendar run emits
all seven).

### B8 (re-run 2026-10-22, with the guard on and the post-filter check in)

`scripts/cadence_shadow.py --as-of 2026-10-20 --guard 0.05 --hedge cap_then_rehedge
--seed-reversal ADM`, `store=False`, no broker, the cut tree above. Thirteen closes:
**1 rebalance, 12 hold**. The tree ends at the 2026-10-20 close, so 2026-10-21 is not
in it - one session short of the brief's window, because that session exists only in
the evening's run tree.

| close | day | orders | traded | guard | before | projection | tradeable | **after** | legs sent / dropped / rounds |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-01 | **rebalance** | 183 | $985,941 | - | - | - | - | - | - |
| 2026-10-02 | hold | **1** | $7,167 | - | - | - | - | - | - (the seeded reversal's second leg) |
| 2026-10-05 | hold | 3 | $9,865 | - | - | - | - | - | - |
| 2026-10-06 | hold | 0 | $0 | - | - | - | - | - | - |
| 2026-10-07 | hold | 0 | $0 | - | - | - | - | - | - |
| 2026-10-08 | hold | 0 | $0 | - | - | - | - | - | - |
| 2026-10-09 | hold | 0 | $0 | - | - | - | - | - | - |
| 2026-10-12 | hold | 0 | $0 | - | - | - | - | - | - |
| 2026-10-13 | hold | 117 | $69,174 | **fired** | 5.31% | 0.00% | 0.42% | **0.42%** | 117 / 63 / 1 |
| 2026-10-14 | hold | 98 | $56,030 | **fired** | 6.58% | 0.00% | 0.39% | **0.39%** | 99 / 81 / 1 |
| 2026-10-15 | hold | 0 | $0 | - | - | - | - | - | - |
| 2026-10-16 | hold | 116 | $65,975 | **fired** | 7.32% | 0.00% | 0.38% | **0.38%** | 116 / 62 / 1 |
| 2026-10-19 | hold | 1 | $0 | - | - | - | - | - | - |

Monthly traded **$1,185,849** against the daily loop's **$5,984,875** (519 orders
against 2,400); 336 of the monthly legs are hold-day legs, 331 of those the guard's.

**What the post-filter check changed.** Before it, the guard reported the projection's
`0.00%` on the three fires while sending 56-88 of the 493 legs it computed, and the
book it left carried an exposure it never stated. Now the number on the manifest is
the one those legs deliver: `0.42%`, `0.39%`, `0.38%` - each measured on the book the
sent legs leave, and each well under the 2.5% floor that would trigger the re-solve.
The re-solve path itself is exercised by
`tests/test_cadence_guard.py::test_the_guard_resolves_over_the_names_that_clear_the_minimum`,
and the "it cannot deliver, so it does not trade" path by the test above it.

**One leg's difference between `orders` and `legs sent`** (10-14: 98 orders against 99
legs) is whole-share quantization: a leg that clears $250 before the book is quantized
can fall under it after, and the morning is the thing that decides.

## Turning it on, if the owner wants it

Nothing is set today. The four variables, on the Render service `efb-live-daily`:

```
EFB_CADENCE=21
EFB_CADENCE_ANCHOR=<the first evening you want a rebalance on>
EFB_DRIFT_GUARD=0.05
EFB_HEDGE_MODE=cap_then_rehedge
```

The step-by-step, with the read-only query that confirms it the next morning and the
way back to daily, is `docs/turn_on_monthly.md`. `EFB_CADENCE_ANCHOR` must be a
**session** the owner is willing to call the start of the cycle; the anchor's own
close is a rebalance, and if it never ran the first evening after it takes that
rebalance rather than holding - which is the B3 rule, not a bug.

With `EFB_CADENCE` unset or `1`, all four are inert and the loop is the daily loop it
is today, manifest included. `EFB_HEDGE_MODE=cap_then_rehedge` is the one that can be
turned on by itself: it does not need a hold day.

**Deployed.** `web/src/status.ts` carries the hold-day pill and the guard's version of
it, and the Worker was redeployed with them on 2026-10-22
(`dd3110ad-7ae6-4715-9540-4288cd3f1f74`, replacing
`a4082203-e469-48b1-8001-641f6b63ddc0`). An older page shows `ok` and simply does not
say "hold day"; a newer page whose document carries no `cadence` block reads exactly
as it did before this branch.

## `EFB_DRIFT_GUARD`: the hold day's hedge refresh

A hold day publishes the book it holds, so its factor exposure drifts as the loadings
are republished every evening. `docs/research/daily_design_study.md` measured that
drift on a panel that refreshes nightly: a monthly book's worst exposure runs to
22.7% at the 95th percentile and 33.3% at its worst, against 4.0% median for a book
rebalanced every session. The guard is the cheapest thing that fixes it.

On a hold day, after the reversal legs are placed and before the floor:

1. **measure**: `design.T @ weights`, the worst absolute value, as a fraction of NAV,
   against the design the book will be held with - the same measurement the study
   makes, and the same design `efb.eval_risk` hedges against;
2. **decide**: past `EFB_DRIFT_GUARD`, take the minimum-norm correction that zeroes
   every exposure (`weights - design @ lstsq(design, weights)`), which spreads the
   correction over the book in proportion to loading instead of dumping it on the
   largest position;
3. **apply the hedge mode**: with `EFB_HEDGE_MODE=cap_then_rehedge` the cap rounds run
   and the neutrality is restored after them, which is variant **G5H** in the study;
4. **measure what will actually trade**: the projection is exact, but the morning only
   sends legs at or above the $250 order minimum, and the projection moves every name
   the book holds a little. So the exposure that matters is measured *after* the
   minimum filter. If that is above 2.5% of NAV the correction is re-solved over the
   names whose legs do clear the minimum (the same restricted projection, round after
   round, until the tradeable set stops changing), and **if the best it can deliver is
   worse than the book it found, the guard trades nothing** - a half-sent correction
   can leave the book further from neutral than it started;
5. **force the legs**: every name the correction moved joins the hold day's forced
   list, and the manifest records
   `drift_guard: {fired, threshold, exposure_before, exposure_projection,
   exposure_projection_tradeable, exposure_after, turnover, legs_under_minimum, rounds,
   legs[]}`.

The correction is solved **over the names the book holds**, not over the universe: the
minimum-norm solution over the whole cross-section is smaller in norm but it opens
positions the book does not have, which is a rebalance on a day the calendar did not
ask for.

A hold day the guard looked at and left alone records `drift_guard: null`; a run that
never asked for a guard records no `drift_guard` key at all, so a flag-less document
is the document the loop has always written.

The page shows it in the pill: `hold day, guard re-hedged 6.7% -> 0.0%`, still green
- a re-hedge is the loop doing its job, not a fault.

## The deferred reversal, which a hold day used to strand

A reversal that crosses zero cannot be one order. The morning closes the held side
and defers the other (`OrderSpec.deferred_target_notional`), and the *next* evening's
delta opens it. On the daily loop that is automatic: the next evening rebuilds the
target and the morning trades the difference.

On a hold day it was not. The published book is the held book, and the held book is
read from the **account** - which is flat on the name, because the first leg closed
it. So the published book carried the name at zero, the morning's delta had nothing
to send, and the second leg waited for the next rebalance: up to twenty sessions
with the book claiming a position the account did not have.

The fix is the deferred target, taken from the book the loop last recorded and
written back into the held book on a hold day, plus the name in the forced list:

- `live.evening_job._with_deferred_targets` writes the deferred weights back;
- `manifest["reversal_targets"]` records them, and `forced_names_for_hold` adds every
  one of them to the allow-list;
- `scripts/run_live_daily.py::reversal_weights` reads the previous close's deferral
  list (`previous_close_reversals`) and the weight from the last recorded book, and
  logs any name it cannot reconstruct rather than trading blind.

Both changes are inert with the flags off: the overlay only runs on a hold day, and a
hold day only exists when `EFB_CADENCE > 1`.

### The reversal in the shadow run

The shadow's own window has one rebalance and no sign flip in it, so the run seeds
one: the account starts holding `ADM` long, in the size the 2026-10-01 rebalance
targets short. What follows is the addendum's proof - the close on the rebalance day,
and the short leg landing on the next morning, which is a **hold** day.

| close | day | what the morning did |
|---|---|---|
| 2026-10-01 | rebalance | ADM: long closed, **`deferred = -0.006986`** recorded |
| 2026-10-02 | **hold** | `reversal_targets = {ADM: -0.006986}`, ADM forced, **1 order, $7,167 short** |

And on a day with nothing pending, `reversal_targets` is empty and the hold day sends
nothing but its forced legs.

## The last rebalance's unfinished legs

The same defect, one step wider. A rebalance is a set of legs and the book only holds
what filled; on the daily loop the next evening rebuilds the target and the delta
finishes the job, but on a hold day nothing would, so a partially filled name would
sit short of its target for up to twenty sessions.

`evening_job.unfilled_remainder` reads `efb.proposals` for the newest close before
tonight whose own manifest says `cadence.day == "rebalance"`, then `efb.orders` for
that close, and keeps every name whose `intended_notional - filled_notional` is at or
above the $250 order minimum - whatever the reason: a partial fill, a rejection, a
name that never filled. The weight it carries is the **target** weight from the book
that close published, not the leg's size, because completing a leg means reaching the
target. On a hold day those names are written back into the held book and forced,
exactly like a deferred reversal; on a rebalance day the key is not even computed into
the manifest, because the rebuild trades the whole difference by itself.

It is idempotent for the same reason the reversal is: the remainder is recomputed from
the store every evening, so once the following morning has filled it the name drops out.

| test | what it pins |
|---|---|
| `test_a_partly_filled_rebalance_is_carried_into_the_next_hold_day` | a leg filled 40% of its size is owed the other 60%, and the next morning sends exactly that |
| `test_a_fully_filled_rebalance_forces_nothing` | nothing is carried, nothing is forced |
| `test_a_leg_under_the_order_minimum_is_not_carried` | a $100 leftover is not a leg |
| `test_the_daily_loop_carries_nothing_into_a_rebalance` | the computation is the evening's; the daily build never writes it |
