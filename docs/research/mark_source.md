# Which prices the evening values the held book at, and what that did to the guard

Status: **read-only study.** Nothing here changes the evening. Every number below was
rebuilt from the store's own rows and one vendor read; `broker_positions`, `nav`,
`proposals.manifest` and the XS-v1 design were read, never written.

## The question the 2026-10-30 hold day raised

The drift guard fired on 2026-10-30: worst factor exposure **6.41%** against a 5.00%
threshold, and it sent 109 legs ($68,858.57) that fill at the 2026-11-02 open. Two days
earlier the same account marked `INTC` at **$71.16** while the vendor's official close was
**$92.07** — a 22.7% gap that looks like an after-hours print. If the guard measures
exposure on after-hours prices, it could fire on a move that the official close does not
confirm.

## 1. The code path: the broker's own `market_value`

```
scripts/run_live_daily.py:2113   positions.check(...)            # the evening's account read
live/positions.py:478            alpaca.position_book(client)
live/alpaca.py:985-988           market_value = pos.market_value
                                 notional[symbol] = sign * abs(market_value)
scripts/run_live_daily.py:200    prior_weights(holdings)
live/positions.py:425-432        weight[ticker] = market_value / account equity
live/evening_job.py:2571         _held_book_weights(previous, names)     # a hold day only
live/evening_job.py:772-780      exposures(weights, design) = X'w
                                 worst = max|X'w|  ->  drift_guard.exposure_before
```

So the held book is **the broker's `market_value` divided by the account's equity**, and
Alpaca's `market_value` is the position valued at its **last trade**, which includes
extended-hours trades. The vendor's close is never consulted for the held book. (It is
consulted for the *target*: `efb.race.next_descriptor_design` and the sizing both read the
artifact panel, which carries vendor closes.)

## 2. How far the two disagree, 2026-10-26 to 2026-10-30

Method: for each close, the held book from `efb.broker_positions` for that date; the
position's mark is `market_value / quantity`; the "session close" is the last 5-minute
vendor bar at or before 16:00 New York. The bar-derived close reproduces the vendor's own
daily close to a median of **1.8 bp** (p95 8.5 bp, max 29 bp) on 2026-10-29, which is the
last session whose daily bar had printed when this ran; 2026-10-30's daily bar had not.

| close | names | NAV | worst \|X'w\|, broker marks | worst \|X'w\|, session closes | median mark gap | largest mark gap |
|---|---|---|---|---|---|---|
| 2026-10-26 | 191 | 980,000.03 | 2.28% (momentum) | 2.29% (momentum) | 0.0 bp | 242 bp, FLEX |
| 2026-10-27 | 195 | 978,548.47 | 1.52% (resid\_vol) | 1.51% (reversal) | 0.0 bp | 862 bp, CSGP |
| 2026-10-28 | 195 | 979,671.55 | 3.07% (reversal) | 3.27% (reversal) | 0.0 bp | 834 bp, MRVL |
| 2026-10-29 | 195 | 974,772.43 | 3.03% (resid\_vol) | 2.86% (momentum) | 0.0 bp | **2,271 bp, INTC** |
| 2026-10-30 | 195 | 975,819.58 | 6.85% (reversal) | 6.86% (reversal) | 4.7 bp | 150 bp, INTC |

Reproducing the guard exactly on 2026-10-30, from the **196 `weight_before` values in the
manifest's own `drift_guard.legs`** (so the name set and the weights are the evening's, not
a reconstruction), with the design the evening used:

```
broker marks      worst |X'w| = 0.064105  on reversal     (the manifest records 0.064105)
session closes    worst |X'w| = 0.064218  on reversal
gross             1.0074 -> 1.0076
```

**Both readings are 6.4%, and both are above 5.00%.** The guard's firing on 2026-10-30 was
real on consistent prices; on the four evenings before it, no reading came within 1.7
points of the threshold, so **the mark source has not changed a guard decision in this
window**.

## 3. What the mark source does change: which names carry the exposure

The median gap is zero on four of the five evenings. `market_value` is the last *regular*
trade for a name that did not trade after hours, so the two valuations are identical for
almost every name; the difference is confined to names that printed in the extended
session. On 2026-10-29 that was `INTC` (−22.7% against its official close), `RDDT` (−18.0%),
`HPQ` (−6.4%), `MDLZ` (+6.1%) and `HPE` (−5.1%).

And the after-hours print was **right**. `INTC` closed at $92.07 on 2026-10-29, the account
marked it at $71.16, and the 2026-10-30 session closed at **$65.88** (−28.4% on the day).
The extended-hours price was the market's estimate of a move the official close had not yet
printed. Valuing at the vendor close on 2026-10-29 would have used a price that was 27%
stale within one session.

## 4. What the recommendation is

**Do not switch the held book to vendor close x quantity.** The reasoning is the case
study above, not a preference: the two agree on 191-195 of 196 names on an ordinary
evening, and where they disagree the broker's mark is the more recent price. A close-valued
book would have been *staler* on the one evening the difference mattered. It would also
introduce a one-session lag on the evening itself, because the vendor's daily bar for the
session has not printed at 22:55 UTC: on 2026-10-30 the daily close for every name came
back `NaN` when this study ran at 00:40 UTC, three hours after the close.

What *is* owed is that the run should not be silent about it:

1. **Record both readings.** `manifest.drift_guard` should carry `exposure_before_close`
   beside `exposure_before` (the same weights, re-priced at the session close, or at the
   vendor's latest close where the session's has not printed), and the email should say
   both when they disagree by more than half a point. That is one number on one line, and
   it turns "the guard fired at 6.41%" into "6.41% on broker marks, 6.42% on closes".
2. **Name the outliers.** The five largest `mark / close - 1` gaps belong in the manifest
   beside the guard's own legs, so a 22.7% extended-hours print is stated rather than
   discovered two days later.
3. **Do not silently clip them.** A band that ignores a mark outside, say, ±20% would have
   ignored the one print that turned out to be right.

The switch itself is built on a branch (`held-marks-close`) behind `EFB_HELD_MARKS=close`,
default unchanged, with the identity proof the owner asked for. It is **not merged**: the
proof holds (target books identical on the four closes tested; only the held weights, the
drift card and the guard reading move), but the evidence above says the close is the worse
of the two prices, so the owner should have the choice rather than the change.

## Caveats

- The 2026-10-30 "session close" is the last 5-minute bar at or before 16:00 ET, not the
  official closing-auction print, because the daily bar had not printed when this ran. The
  method is validated on 2026-10-29 against the daily close (median 1.8 bp).
- One name per day could not be priced from the vendor in the five-day table (191 and 195
  of 196); the exact reproduction uses all 196 and the manifest's own weights, which is why
  it reproduces 0.064105 and the table says 0.0685.
- `BF.B` answers no intraday bars under its own symbol, so it keeps its broker mark in the
  close-valued column.
- Exposure is `X'w` on the XS-v1 design of the *next* session, exactly as the evening
  computes it; this study does not re-derive the design another way.
