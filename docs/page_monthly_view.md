# The page on a monthly cadence: every panel measured from the last rebalance

Written 2026-10-29 before any code. `EFB_CADENCE=21` turned the evening into a hold day
most nights, and every panel on the page still compares tonight with last night: a hold
day reads 0 orders, $0 of sector gaps and 0 hedge legs, which is true and useless. The
page's subject becomes the rebalance, and each panel is measured from the last one.

## The anchor

    ANCHOR = the latest close whose proposal manifest cadence day is "rebalance"

On 2026-10-29 that is **2026-10-23**. Two cases fall back to tonight, so that a daily
book and a rebalance evening render exactly as they do today:

- **no cadence block** (`EFB_CADENCE` unset) - the anchor is tonight, and every panel is
  the panel it already was;
- **tonight is a rebalance** - the anchor is tonight, and the panels are the panels they
  already were, because "since the anchor" is one evening.

The anchor is derived from `efb.proposals.manifest.cadence.day`, never from a hard-coded
date. `EFB_CADENCE_ANCHOR` is 2026-10-23 and `EFB_CADENCE` is 21, so the next rebalance
is derivable too: `cadence.next_rebalance`.

## The panels

### 1. Cadence strip (new panel)

- **Old:** nothing. The strip showed the run state, the mode, the close and the account.
- **New:** hold day N of 21, the last rebalance date, the next rebalance date, and the
  drift guard's reading: the worst absolute exposure against its threshold, and whether
  it fired tonight.
- **Reads:** `cadence.k`, `cadence.offset`, `cadence.sessions_since`,
  `cadence.anchor`, `cadence.next_rebalance`, `drift_guard.worst`, `drift_guard.fired`
  from the run's manifest; all already in the document except the guard reading.

### 2. Rebalance card (the metrics row, re-based)

- **Old:** tonight's orders, tonight's notional and % NAV, tonight's expected and
  realized cost. On a hold day every number was zero.
- **New:** the anchor's orders, the anchor's notional sent and % NAV, the anchor's
  expected cost (from the proposal's `cost_breakdown_bps`) and realized cost (from
  `efb.fills` for the anchor close), and completion: legs complete against legs total,
  and the dollars still owed.
- **Reads:** `efb.orders` for the anchor close, `efb.fills` for the anchor close,
  `efb.proposals.manifest` for the anchor's `cost_breakdown_bps` and `nav`.

### 3. Bridge (re-pointed at the rebalance)

- **Old:** account as the evening read it -> the book -> the orders -> account as the
  morning read it, for one close. On a hold day: one name changed, nothing else.
- **New:** account before the rebalance orders (the account read at the anchor) ->
  opened / exited / resized / **flipped** / under $250 -> account now (the latest account
  read).
- **A flip** is a name whose side before the rebalance differs from its target side. It
  counts **once, as a flip**, carrying both legs' dollars and fill dates, and it is
  complete when the account is on the target side within $250 of the target. It is never
  shown as an exit plus an open, which is what the one-close bridge does with it today
  and why the 2026-10-26 close reads as four opens and four exits.
- **Reads:** `efb.broker_positions` at the anchor and at the latest close (side,
  market_value), the anchor proposal's rows for the target side and weight, `efb.orders`
  and `efb.fills` for the two legs' dollars and dates.

The four names that make this concrete, and the fixture the tests use: at the 2026-10-23
account read CCL is short 23 shares, F is long, GEHC is short and VZ is long; the
2026-10-23 target has CCL long, F short, GEHC long, VZ short. Each was closed on 10-23
(`buy_to_close`/`sell_to_close`) and opened on 10-26 (`buy_to_open`/`sell_to_open`), and
by the 2026-10-27 read each account side matches its target within $250. So: four flips,
each one row, each complete.

### 4. Drift card (new panel)

- **Old:** nothing; the nearest thing was the positions check's `max_abs_drift` between
  the store's book and the account.
- **New:** distance from the rebalance target, `sum|w_now - w_target| / 2` in % NAV and
  in dollars; the estimated cost of a rebalance tonight from the live cost model; and the
  five largest drifts, name by name.
- **Reads:** `efb.broker_positions` weights at the latest close, the anchor proposal's
  target weights, and the cost model's `cost_breakdown_bps.trading` from tonight's
  proposal. The estimate is `sum|w_now - w_target| x NAV x trading bps / 1e4`: the
  dollars that would trade, both sides, at the trading cost per dollar.

### 5. Sectors, hedge footprint, trades by reason, largest positions (re-based)

- **Old:** tonight's book against the account's read; trades are tonight's legs by
  reason.
- **New:** each of these measured against the **rebalance target** rather than the held
  book, so a hold day's drift is visible; and trades since the anchor by reason:
  `rebalance`, `reversal second leg`, `carried leg`, `guard`, `forced exit`.
- **Reads:** the anchor proposal's target rows (ticker, weight, sector through the
  existing `web/src/sector_map.json`), `efb.broker_positions` at the latest close,
  `efb.orders.reason_code` and `efb.orders.trade_date` since the anchor.

### 6. Tonight (new one-line panel)

- **Old:** nothing; tonight's forced legs appeared only in the email.
- **New:** one compact line: tonight's forced legs, count and dollars.
- **Reads:** `manifest.forced` count and dollars for tonight's proposal.

### 7. Time-series charts

- **Old:** a line with no calendar on it.
- **New:** a vertical marker on each rebalance date, from the cadence calendar.
- **Reads:** `efb.proposals.manifest.cadence.day` per close, which the evening can read
  back for the series it publishes.

## New snapshot fields

Every field below is a plain number, a date or a ticker. **No order id, account id or
client order id** is introduced, so `web/worker/sanitize.ts` and its tests are unchanged;
`tests/test_e11_snapshot.py` asserts the document has no identifier-shaped string in the
new blocks.

```
anchor            {close, day: "rebalance"|"hold"|"today", source}
cadence_strip     {k, offset, sessions_since, last_rebalance, next_rebalance,
                   guard: {worst_abs_exposure, threshold, fired}}
rebalance_card    {close, orders, notional, pct_nav, expected_cost_bps,
                   realized_cost_bps, legs_total, legs_complete, legs_incomplete,
                   dollars_owed}
bridge_anchor     {before_dollars, opened, exited, resized, flips, under_minimum,
                   after_dollars, identities, holds,
                   flip_rows: [{ticker, from_side, to_side, close_dollars, open_dollars,
                                close_filled, open_filled, target_dollars, now_dollars,
                                complete}]}
drift             {half_turnover_pct, half_turnover_usd, estimated_cost_usd,
                   largest: [{ticker, weight_now, weight_target, usd}]}
since_anchor      {sectors: [...], hedge: {...}, trades_by_reason: [{reason, legs, usd}],
                   largest: [{ticker, weight_now, weight_target, usd}]}
tonight           {forced_legs, forced_usd}
rebalance_dates   [close, ...]
```

All of them are **absent** on a document written before this change and on a run that
cannot compute them, and the page renders as it does today when they are absent. That is
the same rule the `cadence` block already follows.

## What must not change

- A daily book (`k = 1`) and a rebalance evening render **exactly** as they do today.
  The proof is the existing daily fixtures under `web/fixtures/`, which the vitest suite
  renders unchanged.
- The sanitizer's tests pass unmodified.
- The evening's hot path never fails on this: the block is computed in one function that
  returns `None` on any exception, and a `None` block is simply absent.

## What landed first

The block itself lands before the panels: `live/monthly_view.py` builds it and
`live/snapshot.py` publishes it under a `monthly` key, absent when the run cannot build
it. The page ignores it until the panels land, which is the order this document asks for
and the reason the Worker is deployed last.
