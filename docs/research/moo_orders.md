# Market-on-open orders: what Alpaca does, what the paper account does, and what the flag would send

Status: **research plus a held code change.** The code is on branch `moo-orders`
behind `EFB_ORDER_TIF`; it is not merged, because switching it on changes what the
morning sends. The owner's decision point is the next rebalance, about 2026-11-23.

## The question

The book's orders are created by the evening run at 22:30-22:56 UTC (18:30-18:56
ET) as `day` market orders. The broker releases them into the next session's
pre-market, and they fill at 13:30-13:34 UTC (09:30-09:34 ET). Measured against
the session's opening price, execution costs 16.6 bp per dollar traded: buys come
in **+17.5 bp** above the open (standard error 10.9) and sells **−0.6 bp** (se
13.4). A symmetric cost would show the same sign on both sides; a spread paid by
the buyer and received by the seller shows exactly this asymmetry. That is the
signature of crossing the spread in the first post-open quote, not of paying an
auction price.

So: would a genuine market-on-open order — `time_in_force=opg`, eligible only in
the opening auction and filled at its single clearing price — remove that
asymmetry, and can this account send one?

## What the Alpaca documentation says

Read on 2026-10-24:

* **Placing Orders**, https://docs.alpaca.markets/docs/orders-at-alpaca#time-in-force
  and the section *Opening and Closing Auction Orders*: "Market on open and limit
  on open orders are only eligible to execute in the opening auction."
* **Create an Order** (OpenAPI schema), https://docs.alpaca.markets/reference/postorder
  — the `time_in_force` enum and the descriptions it carries:
  * "Equity trading: day, gtc, opg, cls, ioc, fok."
  * "`opg`: Use this TIF with a market/limit order type to submit "market on open"
    (MOO) and "limit on open" (LOO) orders. This order is eligible to execute only
    in the market opening auction. Any unfilled orders after the open will be
    cancelled. **OPG orders submitted after 9:28am but before 7:00pm ET will be
    rejected.** OPG orders submitted after 7:00pm will be queued and routed to the
    following day's open."
  * `notional`: "dollar amount to trade. Cannot work with `qty`. **Can only work
    for market order types and day for time in force.**"
* **Paper Trading**, https://docs.alpaca.markets/us/docs/paper-trading — "the
  system simulates the order filling based on the real-time quotes"; "all orders
  submitted in paper trading will be matched against the best available current
  market price (NBBO)"; "Your order quantity is not checked against the NBBO
  quantities ... When orders are eligible to be filled, they will receive partial
  fills for a random size 10% of the time"; paper does not model market impact,
  information leakage, latency slippage, queue position, price improvement,
  regulatory fees or dividends; and the paper-vs-live table marks **borrow fees as
  not simulated**.
* **Historical auctions**, https://docs.alpaca.markets/us/reference/stockauctions-1
  — auction prices per symbol per session, which is the official open an `opg` fill
  would have to be compared against.

Three consequences follow directly, and none of them is a judgement call:

1. **`opg` is a supported equity TIF on this account's API surface.** The paper
   documentation says "the API spec is the same between the paper trading and the
   live accounts", and where the paper environment does *not* support something the
   docs say so explicitly — the locate endpoints are each marked "This endpoint is
   not available in paper trading". No such exclusion is written for `opg`. That is
   strong evidence and not proof: only a test order proves it, and a test order is
   a broker write that the freeze forbids.
2. **The 09:28 ET cutoff is comfortably clear in the normal case and tight in the
   worst one.** The evening's submissions are created at 22:52-22:56 UTC and
   released by the broker at 08:01 UTC (04:01 ET). One leg in the measured sample
   was released much later: RDDT, created 2026-10-21 22:56 UTC, released
   2026-10-22 13:23:01 UTC (**09:23 ET**), filled 13:30:01 UTC. That is five minutes
   inside the cutoff. A release after 09:28 ET would be rejected outright, so the
   flag cannot be a bare TIF swap — see the fallback below.
3. **A notional order cannot carry `opg` at all.** Today the open-long legs are
   notional (`notional` set, `qty` null: CMG on 2026-10-23 is a measured example)
   and the close and short legs are quantities. Under the flag, the open legs are
   sized in whole shares at the run's own reference price, rounded **down**, so the
   flag can only ever buy less than the notional the run sized.

## What is not established

* **How paper fills an `opg` order.** The docs describe the simulator as matching
  against the NBBO, and say nothing about auctions. An `opg` order in paper may
  fill at the auction's clearing price, or the engine may simply match it against
  the first quote after the bell as it does today — in which case the flag changes
  nothing and the asymmetry survives. This is the one question that decides whether
  the flag is worth switching on, and it can only be answered by measuring one
  session with the flag on.
* **Partial fills in the auction.** The exchange can fill an auction order
  partially; the simulator's rule (a random 10% partial) is its own, so a paper
  partial fill says nothing about the auction. `opg` cancels whatever is unfilled
  after the open either way.
* **Fractional shares in the auction.** Not documented. The flag avoids the
  question by sending whole shares.

## The measurement that settles it

One session with `EFB_ORDER_TIF=opg`, then, for every filled leg, compare the fill
price with that symbol's opening auction price from the Historical auctions
endpoint for the same session, and with the same leg's fill price from the prior
`day` sessions. Two outcomes:

* fills land on the auction price and the buy/sell asymmetry collapses toward
  zero → keep the flag on, and the cost model's 16.6 bp becomes a spread the book
  no longer pays;
* fills still sit at the first post-open quote → the asymmetry is the simulator's,
  not the book's, and neither TIF is a real cost. The 16.6 bp figure would then
  have to be read as a paper artefact and the live cost model re-derived before any
  capacity decision rests on it.

Either way the answer arrives within one rebalance, which is why the flag is built
now and switched later.

## What the flag sends

`EFB_ORDER_TIF` (in `live/alpaca.py`):

| value | what the morning sends |
| --- | --- |
| unset, or empty | exactly today's orders: `day`, notional for the open longs, quantities for everything else, the same `client_order_id`s |
| `opg` | every leg market with `time_in_force=opg`; the open longs become whole-share quantities sized down at the reference price |
| anything else | `ValueError` before the first leg is sent |

The cutoff guard is per leg, not per run: past 09:28 ET an `opg` leg is sent `day`
instead, and the leg's record carries `sent day: opg is rejected after 09:28 ET`
in its detail, so the email and the stored row both say which TIF was actually
used. A leg the broker already holds is resolved by its `client_order_id` and
never re-sent, so a rerun cannot change or duplicate an accepted order.

## How it was proved

`tests/test_moo_orders.py` (9 tests, no network, no broker):

* unset and empty are `day`; `OPG` is accepted case-insensitively; `moo` raises
  before anything is sent;
* unset sends the four legs with `day`, the notional open, the quantity closes and
  the four pinned `client_order_id`s — the "byte-identical" proof;
* `opg` sends all four legs with `opg`, the open as `qty=500` and not notional;
* an open that rounds below one whole share is skipped, not quietly sent notional;
* past 09:28 ET the legs fall back to `day` and every record says why;
* the cutoff is on the New York clock: 13:35 UTC is past it in summer (09:35 ET)
  and inside it in winter (08:35 ET);
* a rerun whose tickets the broker holds submits nothing and resolves all four.

The rest of the gate is unchanged by the flag: `tests/test_e11_order_timing.py`,
`tests/test_e11_order_guardrails.py` and `tests/test_e11_broker_models.py` pass
with the flag unset, which is the state the book trades in until the owner decides.
