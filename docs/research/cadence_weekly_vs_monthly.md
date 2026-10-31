# Weekly (k=5) against monthly (k=21), with the 5% drift guard (P4a)

Read-only, built on the 2026-10-30 tree with the live hedge mode
(`EFB_HEDGE_MODE=cap_then_rehedge`) and NAV $1M. The book is the same book either way:
the cadence decides *when it trades*, not what it holds.

## The cost of one rebalance at each cadence

Same target book, same trades, one difference in the cost model - the borrow horizon:

| | k=5 (weekly) | k=21 (monthly) |
| --- | --- | --- |
| spread | 4.851 bp | 4.851 bp |
| impact | 0.400 bp | 0.400 bp |
| commission | 1.000 bp | 1.000 bp |
| **borrow** | **0.347 bp** | **1.458 bp** |
| total | **6.60 bp** | **7.71 bp** |

Borrow is linear in the holding period by construction
(`costs.BORROW_RATE * short_gross * k / 252`), so the monthly book pays 4.2x the weekly
book's borrow on every rebalance. Everything else is identical.

## What the live history says the cadences actually cost

From the 24 stored proposals (`efb.proposals`, expected cost per close):

| period | cadence | cost per close |
| --- | --- | --- |
| 2026-09-29 .. 2026-10-22 (18 closes) | daily, k=1 | **14.1-14.5 bp** |
| 2026-10-23 (the anchor) | monthly, rebalance | **4.76 bp** |
| 2026-10-26 .. 2026-10-30 (5 closes) | monthly, hold days | **1.47-1.93 bp** |

So the cadence change on 2026-10-23 took the per-close cost down by a factor of about
seven on the days it holds. That is the whole case for holding: a hold day trades
nothing and pays only the borrow accrual.

## The guard is what decides whether "monthly" means monthly

The 5% guard on 2026-10-30 read **6.4105%** and fired, sending 109 legs. That close was
**day 5 of 21**: the book had drifted 6.4% in five sessions, which is faster than the
guard allows. The monthly cadence therefore did not hold for a month - the guard forced a
full rebalance at the first week.

That is the finding that matters for the 2026-11-23 decision:

| | trading cost per year | borrow per year | total |
| --- | --- | --- | --- |
| weekly, k=5, 50 rebalances | 50 x 6.25 bp = 313 bp | 50 x 0.35 bp = 17 bp | **330 bp** |
| monthly, k=21, 12 rebalances | 12 x 6.25 bp = 75 bp | 12 x 1.46 bp = 18 bp | **93 bp** |
| monthly, k=21, guard firing every 5 sessions (~50 rebalances) | 50 x 6.25 bp = 313 bp | 50 x 1.46 bp = 73 bp | **386 bp** |

The third row is what the loop is actually running: the borrow accrual of a monthly book
with the trading frequency of a weekly one, and it is the most expensive of the three.

## Recommendation

Either cadence is defensible; the combination as it stands is not.

1. **If the 5% guard is the right tolerance**, run **k=5**. A book that trips a 5% drift
   line within five sessions is a book whose risk is being refreshed weekly by the guard
   anyway, and k=5 makes the borrow accrual match the holding period that actually
   happens.
2. **If monthly holding is the point**, widen the guard - or make it a function of
   sessions since the anchor - so that a 6% drift on day 5 is a *reading* rather than a
   trigger. The 2026-10-30 firing was real, not an artifact
   (`docs/research/mark_source.md`), so this is a tolerance decision, not a data fix.
3. Do not leave k=21 with a 5% guard and expect monthly costs.

## Caveats

- One drift observation (2026-10-30) drives the "fires in five sessions" claim. The guard
  has existed for one read; a second month of readings would make it a distribution.
- The spread schedule is an assumption from the cost model, not a measured spread; the
  6.25 bp trading leg moves with it and the comparison between cadences does not.
- The fills behind these numbers are paper fills. The realized 2026-10-23 rebalance cost
  11.0 bp against the 4.8 bp expected (`docs/research/moo_rebalance_1023.md`), so treat
  the absolute level as a floor.
