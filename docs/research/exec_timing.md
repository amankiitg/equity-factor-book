# When the book trades: the open, 10:00, and what the fills actually paid

**Research only. Nothing in this note changes a trading rule, and no branch carries it
into the loop.** The question is whether the timing of the order path costs money, and
the answer here is measured on twelve filled days - every day the live book traded more
than ten legs between 2026-10-02 and 2026-10-21.

## What the order path actually does

`submitted_at` on every filled leg says the orders do **not** go out two hours after the
close. They go out at **08:01 UTC (04:01 ET), pre-market**, and the broker holds them
until the opening auction:

| day | legs | first submission (UTC) | last |
|---|---|---|---|
| 2026-10-02 | 207 | 08:01:52 | 13:23:01 |
| 2026-10-05 .. 10-16 | 176-202 | 08:01:18 - 08:01:57 | 08:02:25 |
| 2026-10-19 .. 10-21 | 163-170 | 08:01:12 - 08:01:46 | 13:23:01 |

Five of the twelve days carry legs submitted again at **13:23 UTC (09:23 ET)**, seven
minutes before the open: those are the retries, and they also fill in the opening
window. So the "submission time" has no traded price to compare against - it is
pre-market - and the only two timings this data can price are the **open** and any
intraday moment after it. Part 4 of the 2026-10-23 brief records the pre-market quote
going forward, which is what would make the third column measurable.

## The three timings, measured

Every leg's fill is compared with the session's first 30-minute bar (the open print) and
with the 09:30-10:00 bar's close (the 10:00 ET price), weighted by the leg's dollars and
signed so that **positive is a cost** for both a buy and a sell. Twelve days, 2,203
legs, SIP feed, raw prices.

| close | legs | fill vs open (bp) | open vs 10:00 (bp) | fill vs 10:00 (bp) |
|---|---|---|---|---|
| 2026-10-02 | 207 | -5.7 | +5.8 | -11.5 |
| 2026-10-05 | 197 | -16.4 | -5.8 | -9.7 |
| 2026-10-06 | 190 | +12.4 | +12.6 | +0.3 |
| 2026-10-08 | 202 | -1.1 | -14.7 | +13.4 |
| 2026-10-09 | 171 | +43.0 | -4.3 | +46.9 |
| 2026-10-12 | 188 | +31.5 | +10.3 | +21.4 |
| 2026-10-13 | 191 | +27.8 | -8.9 | +36.8 |
| 2026-10-15 | 176 | +11.2 | -24.9 | +36.7 |
| 2026-10-16 | 181 | +18.0 | -1.7 | +20.2 |
| 2026-10-19 | 163 | +11.6 | -9.7 | +21.2 |
| 2026-10-20 | 167 | +35.6 | +12.3 | +23.0 |
| 2026-10-21 | 170 | +39.1 | +2.7 | +36.1 |
| **mean** | | **+17.2** | **-2.2** | **+19.6** |
| median | | +18.0 | -1.7 | +21.4 |

Read it as: the fills paid 17.2 bp more than the open and 19.6 bp more than the 10:00
price, and the market's own move between the open and 10:00 was -2.2 bp - two-sided and
small. So the cost is not the market walking away in the first half hour; it is the
fill itself, and it is **one-way**: 10 of 12 days are positive.

## Is the drift one-way, and does it follow the trade's direction?

Split by side, on the same weighting:

| side | legs | mean day (bp) | standard error | days positive |
|---|---|---|---|---|
| buy | 1,097 | **+17.5** | 10.9 | 6 of 12 |
| sell | 1,106 | **-0.6** | 13.4 | 8 of 12 |
| all | 2,203 | **+16.9** | 5.4 | 10 of 12 |

The cost is **entirely on the buy side**. Sells fill at the open, within a basis point
of noise; buys pay 17.5 bp. That is the signature of buying into strength - the names
the signal buys are the ones that keep bid in the first minutes - and it is also what
paying the spread and the opening-cross imbalance on the long side looks like. **The
data cannot separate the two**: 12 days, and a buy-side standard error of 11 bp means
the buy-side mean alone is a t of 1.6, short of anything a desk should act on.

## The annual cost, at monthly plus guard turnover

Monthly with the 5% guard trades 13.4x NAV a year (the study's number). At that
turnover:

| timing | cost per dollar traded | annual, bp of NAV |
|---|---|---|
| the open, as executed | +16.9 bp | **227 +/- 73** |
| 10:00 ET, if the book had waited | +16.9 - 19.6 = -2.7 bp | **-36 +/- 73** |
| the pre-market submission | not measurable | - |

The research model in `docs/research/E9_tcost_capacity.md` predicts about 2.5 bp a
day, which at 13.4 turns is **34 bp a year**. The executed book is paying **227 +/- 73
bp a year** against that, and the 10:00 column is the same transaction book valued at a
later print, which is where the sign flips. Both numbers carry the same 73 bp standard
error: **the gap is real, the size of the fix is not measured.**

## Recommendation

1. **Wait until 10:00 ET, or at least the first minutes after the open, before the
   orders are worked.** The measured effect is large enough to justify the experiment
   and not large enough to justify a rule: the right next step is a **staged
   comparison** - one week at the current timing, one week at 10:00 - rather than
   flipping the path on twelve days of evidence.
2. **Record the pre-market quote before deciding.** Part 4 (`order-time-quotes`, held)
   stores the bid, ask and mid with every order, and `filled_at` should join it: with
   those, the split is four ways and the pre-market column stops being blank.
3. **Do not read the 10:00 column as a saving.** It is what the same trades would have
   paid at a later print, and it ignores thirty minutes of adverse selection the book
   would then carry - which is the thing a staged comparison would measure.

## What this sample cannot say

Twelve consecutive sessions of a long/short book in a rising market, one execution
mechanism, one venue, no control. The 10:00 mark is measured *after* seeing which names
traded, so the fill-versus-10:00 gap embeds the selection; the open-versus-10:00 line is
the market's own move and it is two-sided. Nothing here identifies whether the buy-side
cost is momentum, the opening cross, or impact - only that it is on the buy side, and
that it is the largest single term in the live cost record.
