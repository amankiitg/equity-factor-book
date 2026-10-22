# Turning on the monthly cadence

The calendar, the drift guard and the cap-then-rehedge hedge are on `main` as of
2026-10-22 with **every flag off**, which is today's daily loop. This is the switch:
four Render environment variables, and the checks that say the switch worked.

The evidence behind the settings is in `docs/research/daily_design_study.md` on
`research-daily-design` (what a monthly book's exposure costs and what the guard costs
to fix) and `docs/cadence_flag.md` on `main` (how the flag works, and the identity and
shadow proofs it merged on).

## The four variables

| variable | value | what it does |
|---|---|---|
| `EFB_CADENCE` | `21` | sessions between rebalances. `1` or unset is the daily loop. |
| `EFB_CADENCE_ANCHOR` | `<the first evening you set them>` — **`2026-10-22` if you set them before Thursday 2026-10-22 22:25 UTC** | the session the calendar counts from. The anchor is itself a rebalance, so the first evening after you set it is a full rebalance and the next one is 21 sessions later. |
| `EFB_DRIFT_GUARD` | `0.05` | a fraction of NAV. On a hold day, if the book's worst factor exposure is past 5%, it re-hedges to neutral - and the exposure it reports is the one **after the $250 order minimum**, which is the exposure the book actually keeps. |
| `EFB_HEDGE_MODE` | `cap_then_rehedge` | the hedge the book is built with. Default `exact`. |

Set the anchor to **the session of the first evening you want a rebalance on**, not to
a date in the past. An anchor in the past is legitimate - the calendar counts sessions
from it - but it makes the first evening's day type depend on arithmetic you then have
to check, and the anchor is meant to be the day the new policy starts.

## Where, and when

**One service: `efb-live-daily`**, the cron in `render.yaml` that runs both slots
(15:30 UTC is `scripts/reconcile_fills.py`, 22:30 UTC is `scripts/run_live_daily.py`,
routed by `scripts/run_cron.py`). It is the only service that reads these variables:

- the calendar (`live/cadence.py`) is read by the evening build only;
- the guard and the hedge mode are read by `live/evening_job.py`'s construction, which
  only the evening calls;
- the morning's reconciliation imports neither, and it reads no flag: the attribution
  re-price runs in the evening, not the morning, because the morning's service holds
  no artifacts to rebuild a row from.

If a second service is ever pointed at `scripts/run_live_daily.py`, it needs the same
four values. `render.yaml` does **not** declare them, deliberately: adding them to the
blueprint would put them under the *next* deploy's control and a blueprint sync would
then set them for you. Add them in the dashboard (Environment → Add Environment
Variable) on the existing service.

**When:** outside the run windows - not between 15:25-15:45 UTC and not between
22:25-23:00 UTC, which are the two slots the cron occupies. Setting them in the middle
of a running evening changes nothing for that run (the process read its environment at
start) and makes the next one start on a calendar it did not expect to.

## What the first evening does

1. **The anchor evening is a full rebalance.** The calendar says `rebalance`, the book
   is built from scratch exactly as it is today, and the orders are the whole
   difference between the account and the target - a normal rebalance evening.
2. **The next 20 sessions are holds.** The evening still runs everything: data,
   marks, reconciliation, attribution, snapshot, page. The proposal is the held book.
   The only legs are the forced ones - a name that left the universe, a corporate
   action, a short the broker will not lend, a name the model cannot price, a reversal
   whose second leg is due, **the unfinished remainder of the last rebalance's own
   legs** (a partial fill, a rejection, a name that never filled - anything left owing
   from the rebalance), and the drift guard's own re-hedge when it fires.
3. **A missed rebalance is taken.** If a scheduled rebalance evening fails or is
   skipped, the completion record (`efb.run_status`) shows the gap and the next
   successful evening rebalances, so the book cannot quietly drift for months.
4. **The page says which day it is**: `hold day, next rebalance <date>`, green, and
   `hold day, guard re-hedged 6.7% -> 0.0%` when the guard fired.

The first evening also writes the calendar into the manifest, so the run's own record
says what it did rather than leaving the page to infer it.

## What changed under this switch since it was written

Three things moved on 2026-10-22, none of them a flag and none of them the book:

- **The evening's cost estimate now prices the trade.** Spread, commission and impact are
  charged on the traded notional (target minus held) and only the borrow on the book, so
  the `expected_cost_bps` you see from Friday onwards moves with turnover instead of
  sitting at a flat ~14.3 bp. Friday's number is not comparable with last week's.
- **A close's attribution is re-priced once its fills exist**, in the evening, and the
  realized-volatility line is restated from the whole P&L history rather than from the
  sessions that run happened to attribute. The page's "realized against forecast" chart
  is the one that changed most: it used to show a tenfold cliff on 2026-10-15 that was an
  artefact of a two-session window.
- **The borrow rate is still 2%/yr and still unsourced**; `docs/borrow_rate.md` collects
  the public evidence (general collateral at 10-35 bp, Alpaca free on easy-to-borrow) and
  recommends 0.35% with a 0.10%-1.00% range. It is not changed in code; that is yours.

None of the three changes what the four variables below do.

## Confirming it the next morning (read-only)

The manifest is stored per close in `efb.proposals.manifest`. This is the query:

```sql
SELECT trade_date,
       manifest -> 'cadence' ->> 'k'                       AS cadence_k,
       manifest -> 'cadence' ->> 'day'                     AS day,
       manifest -> 'cadence' ->> 'label'                   AS label,
       manifest ->> 'hedge_mode'                           AS hedge_mode,
       manifest ->> 'held_book'                            AS held_book,
       manifest -> 'cadence' -> 'drift_guard' ->> 'fired'  AS guard_fired,
       (manifest -> 'cadence' -> 'drift_guard' ->> 'legs_under_minimum')::int AS guard_small_legs,
       (manifest -> 'cadence' -> 'drift_guard' ->> 'exposure_before')::float8 AS guard_before,
       (manifest -> 'cadence' -> 'drift_guard' ->> 'exposure_after')::float8  AS guard_after
FROM efb.proposals
WHERE trade_date >= '2026-10-22'
ORDER BY trade_date;
```

What it must say on the first evening:

- `cadence_k = 21`, `day = rebalance`, `hedge_mode = cap_then_rehedge`,
  `held_book = false`, `guard_fired = NULL` (the guard only acts on a hold day);
- the evening 21 sessions later: `day = rebalance` again;
- the evenings between: `day = hold`, `held_book = true`, and `guard_fired` either
  `NULL` (the guard looked and left the book alone: it only writes a block when it
  fires) or `true` with `guard_before` above `0.05`, `guard_after` at 0, and
  `legs_under_minimum` counting the legs too small to send.

And the run's own row, which is what the page reads:

```sql
SELECT target_close, job, status, n_orders, cost_label, gross_notional
FROM efb.run_status
WHERE job = 'live_daily' AND target_close >= '2026-10-22'
ORDER BY target_close DESC;
```

A hold day is `status = 'ok'` with `n_orders` equal to the forced legs only - often 0.

On a hold day the manifest also carries `unfilled_remainder` (the last rebalance's legs
still owed, as target weights) and `reversal_targets` (a sign flip whose second leg is
due). Both are forced, so a rebalance finishes before the book is allowed to sit still:

```sql
SELECT trade_date,
       manifest -> 'unfilled_remainder' AS owed_from_the_rebalance,
       manifest -> 'reversal_targets'   AS reversals_due
FROM efb.proposals
WHERE trade_date >= '2026-10-22' AND manifest -> 'cadence' ->> 'day' = 'hold'
ORDER BY trade_date DESC;
```

An evening with an empty `unfilled_remainder` is a rebalance that finished.

## Turning it off

Delete the four variables (or set `EFB_CADENCE=1`). The next evening is a rebalance on
the daily loop: `EFB_CADENCE=1` makes every close a rebalance, the guard has no hold
day to act on, and `EFB_HEDGE_MODE` returns to `exact`. Nothing is left behind - the
book in hand is a book like any other, and the next evening trades it to the target.

If you want the hedge to stay capped after the calendar goes back, keep
`EFB_HEDGE_MODE=cap_then_rehedge`; it is independent of the other three.
