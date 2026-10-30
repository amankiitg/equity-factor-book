# The 2026-10-23 rebalance: where the 11 bp went, and what it says about market-on-open

Status: **read-only research.** Nothing here changes what the loop sends. The
`moo-orders` branch is untouched, `EFB_ORDER_TIF` stays unset, and no store row was
written. The measurement is `/tmp/moo_legs_1023.parquet`, rebuilt from `efb.fills` and
one vendor read of the 2026-10-26 opens.

## The question

The 2026-10-23 rebalance realized **11.0 bp of NAV** against **4.8 bp expected** (the
stored `expected_cost_bps` is 4.7619). The flag on the `moo-orders` branch would send the
legs as `time_in_force=opg`, eligible only in the opening auction. Does the overrun sit
in a part of the cost an opening auction would remove?

## What was measured

The 208 filled legs of that rebalance, `efb.fills` where `trade_date = 2026-10-23` and
`status = FILLED`: 99 buys ($273,188) and 109 sells ($270,816), **$544,003** traded.
`fill_price` is the broker's own `filled_avg_price`; the reference prices are the
2026-10-23 close (`efb.fills.close_price`) and the 2026-10-26 official open (vendor,
`efb.prices.download_prices`, all 208 names answered). Each term is signed so that
positive is a cost, and weighted by `|intended_notional|`:

```
overnight   prior close -> open      0.82 bp   buys +25.32   sells +23.89
execution   open -> fill            19.35 bp   buys +30.35   sells  +8.25
total       prior close -> fill     20.14 bp   buys +55.62   sells -15.65
```

- 20.14 bp of notional × $544,003 = **$1,096 = 11.24 bp of NAV**, which is the reported
  11.0 bp to within its own rounding. The split reconciles.
- **Execution is 96% of it.** The overnight gap is 0.82 bp in aggregate, and it is two
  large, opposite numbers: the market gapped *in the direction of the trade* on both
  sides, +25.3 bp on what we were buying and +23.9 bp on what we were selling, so
  $692 of it was paid by the buys and $647 of it was *received* by the sells.
- In dollars: buys paid **$829** of execution and $692 of overnight; sells paid **$223**
  of execution and received $647 of overnight.
- The asymmetry is a property of the distribution, not of one name: median execution is
  **+36.19 bp on buys** and **+6.03 bp on sells**, and 145 of the 208 legs were adverse.
- It is not an outlier effect either: dropping the five largest execution gaps moves the
  execution average from 19.35 to **19.04 bp** (those five legs are 2.1% of the dollars).
  The five, for the record: DECK −336.5 (fill 78.97 against an open of 81.72, a *gain*),
  STLD +198.4, EBAY +173.8, DOW +172.5, SW +160.7, WAB +158.7.

That shape - buys paying materially more than sells - is the signature of **crossing the
spread on the first post-open quote**, which is the same reading the earlier note on the
`moo-orders` branch took from a 2026-10-16 sample (buys +17.5 bp, sells −0.6 bp, 16.6 bp
overall). Two rebalances, two weeks apart, the same asymmetry and a different magnitude.

## What a market-on-open order would change

An `opg` order is eligible only in the opening auction and fills at its single clearing
price. Two consequences:

1. **The `open -> fill` term stops being a first-minutes drift** and becomes the
   auction's own impact. That is the 19.35 bp term above.
2. **The `close -> open` term is untouched.** No order type reaches back to the close the
   book was sized from. On this rebalance it was 0.82 bp in aggregate by luck - it is a
   risk that cancelled between the two sides, not a cost that was avoided.

So the flag addresses, at most, **19.35 of the 20.14 bp**.

## The caveat that decides it

**The fills are paper.** `fill_price` is the paper broker's `filled_avg_price`, produced
by Alpaca's simulation from the quote it sees when it processes an order released into
the 13:30 UTC session. On a real account a `day` market order released before the open
normally participates in the opening auction too, and the cost that shows up here as
19 bp of first-minutes drift would mostly not be paid. Two facts say the measured number
is at least partly the simulator's model rather than ours:

- the asymmetry is exactly what crossing a spread looks like, and a real pre-open market
  order would not cross a spread at all - there is no spread in a single-price auction;
- the magnitude moved 16.6 to 19.4 bp in two weeks while the shape held, which is a
  model-and-noise regime rather than a stable cost.

The honest summary: **this measurement cannot tell us what an auction would save on a
real account, because the fills it is computed from are not auction fills.**

## Recommendation

**Do not switch `EFB_ORDER_TIF` on for the 2026-11-23 rebalance on this evidence.**

- The saving the flag could capture is inside the simulator's fill model, and the flag
  changes what a real account sends in a way that cannot be undone once sent: `opg` is
  auction-only, with no fallback, and the branch's own rule downgrades to `day` only
  before 09:28 ET.
- The cost question is worth settling, but with a measurement that does not depend on
  the simulator. Since the order-time-quotes migration the store records
  `submitted_bid`, `submitted_ask`, `submitted_mid` and `quoted_at` on every leg; the
  spread we would be crossing is now measurable directly, on our own quotes, without
  changing what is sent.
- Concretely: keep the flag off, and read the next two rebalances' quotes against their
  fills. If the measured crossing there is still of this size, that is a spread we are
  paying by choice; if it is not, the 19 bp was the paper engine.

Revisit after 2026-11-23 with these numbers beside that rebalance's.

## Caveats, stated plainly

- **Paper fills.** The central caveat above: `filled_avg_price` is simulated.
- **One vendor open.** The 2026-10-26 open is the vendor's official print; a name whose
  open is a reopening print rather than the auction's would carry its own error. All 208
  legs answered, none was priced at zero.
- **No corporate action moves these prices.** The vendor's `split_factor` is 0 and
  `dividend` 0 for the 2026-10-26 session on these names, and `adj_close == close`.
- **Overnight is a risk, not a cost.** Its aggregate is small only because buys and sells
  were both gapped against us in nearly equal dollars. A rebalance that is one-sided
  would pay it in full.
- **Weights.** Everything above is weighted by `|intended_notional|`; an equal-weighted
  average would let the five large-gap legs count as much as the $8,700 legs beside them.
