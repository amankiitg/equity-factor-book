# Borrow, charged per name from the broker's own status (P4b)

Read-only, 2026-10-31. The question: what would borrowing cost if it were charged per
name from the broker's own borrow status, instead of the flat 0.35% constant?

## The constant

`efb/costs.py` charges `BORROW_RATE = 0.0035` on short notional. `docs/borrow_rate.md`
has the provenance: general collateral runs 10-35 bp/yr, the industry anchor is 30 bp,
D'Avolio's value-weighted mean is 17 bp, 9% of lent names cost more than 1% and carry 40%
of the borrow bill on 2% of the dollars. 35 bp is the benchmark plus a margin. At the
monthly horizon that is **1.458 bp per rebalance** on the 2026-10-30 book, and 0.347 bp
at k=5.

## What the broker says about this book's own shorts

Every short in the 2026-10-30 book was checked against the broker's asset record
(`GET /v1/assets/{symbol}`, read-only), all **104** of them:

| tradable | shortable | easy_to_borrow | count |
| --- | --- | --- | --- |
| true | true | **true** | **104** |
| any other combination | | | **0** |

Alpaca's published schedule charges **$0 locate and borrow fees** on its
easy-to-borrow securities (docs/borrow_rate.md, row 5), and every name the book shorts
is one of them. The hard-to-borrow path - an approved locate, round lots of 100, a
per-account annualised rate that is not published - is not entered by any leg.

## Per-name against the constant

| basis | charge on this book |
| --- | --- |
| broker's own status, per name | **0.00 bp** (all 104 easy to borrow, no fee published) |
| the 0.35% constant | 1.458 bp per rebalance at k=21; ~17.5 bp/yr of NAV at half gross |
| one name going hard to borrow at 4.3%/yr (D'Avolio's >1% bucket mean) at a 1% weight | 4.3 bp/yr of NAV, **for that one name** |

The second row is a deliberate over-charge against the broker's published schedule, and
the third row is why: a single name moving into the hard-to-borrow tail costs more than
the entire book's borrow allowance at the constant. The constant is not a measurement of
what is paid today; it is a reserve against what could be paid tomorrow.

## Recommendation

1. **Keep the constant.** Charging per name from the broker's status would set the book's
   borrow to zero today, which is true on paper and misleading in a cost model whose job
   is to decide between trading more and trading less.
2. **Keep the shortability precheck on** (`EFB_SHORTABILITY_PRECHECK`). It is the
   mechanism that keeps the 104 easy names easy: a leg the broker reports
   `easy_to_borrow=false` is dropped before sizing rather than borrowed at a rate we do
   not know.
3. **Record the flags with the run.** The check is a live call; storing
   `easy_to_borrow: true/false` per short in the manifest would let a later audit price
   the borrow against the state that was seen, instead of re-reading today's flags and
   assuming they were the same.
4. Do **not** model a locate fee. The two currencies are different - a per-share locate
   charge and an annualised fee - and conflating them is how a 4 bp book gets a 40 bp
   cost model.

## Caveats

- Paper accounts do not publish whether borrow fees accrue at all
  (`docs/borrow_rate.md`, row 9), so "0.00 bp" is the broker's *schedule*, not an observed
  charge on this account.
- The flags are a snapshot of 2026-10-31, not of 2026-10-30 when the book was built.
  Borrow status moves with the market; the recommendation to record it with the run is
  the fix for that.
