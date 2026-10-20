# The rebalance calendar: `EFB_CADENCE`, on a branch, not merged

Branch `cadence-flag`. **Nothing here is on `main`, nothing is deployed, and no
Render variable has been set.** `docs/research/ic_decay.md` and
`docs/research/cadence_study.md` recommend rebalancing every 21 sessions; this is
that recommendation as a flag whose default is today's daily loop.

## The flags

| variable | meaning | default |
|---|---|---|
| `EFB_CADENCE` | sessions between rebalances. `1` (or unset, or empty) is the daily loop the book runs today. A whole number below 1, a fraction or a word is refused in the log and treated as unset. | `1` |
| `EFB_CADENCE_ANCHOR` | the session the calendar counts from, `YYYY-MM-DD`. The anchor is session 0 and is therefore itself a rebalance. A date that is not a session snaps back to the last session on or before it. | the close being priced |

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

## Turning it on, if the owner wants it

Nothing is set today. On the Render service `efb-live-daily`, the two variables
are:

```
EFB_CADENCE=21
EFB_CADENCE_ANCHOR=2026-10-01
```

`EFB_CADENCE_ANCHOR` must be a **session** the owner is willing to call the start
of the cycle; 2026-10-01 is the anchor the proofs used. With `EFB_CADENCE` unset
or `1`, both the flag and the calendar are inert and the loop rebalances daily
exactly as it does now.

**The order matters on the first evening.** If the anchor's own rebalance never
ran (a fresh anchor in the middle of a month), the first evening after the anchor
takes that rebalance rather than holding - which is the B3 rule, not a bug. The
2026-10-01 anchor in the shadow run was such a rebalance.

**Not deployed.** `web/src/status.ts` carries the hold-day pill, because a hold day
has to read green rather than as an unexplained quiet evening, but the Worker was
not redeployed for this branch. The page keeps working without it: an older page
shows `ok` and simply does not say "hold day" until the next deploy of the page.
