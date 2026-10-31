# Owner decisions

One entry per decision the owner made, with the evidence it rests on and what it
changes. Newest first. A decision recorded here is closed: reversing one is a new
entry, not an edit.

## 2026-10-31: market-on-open orders are not adopted for 2026-11-23

**Decision: not adopted.** `EFB_ORDER_TIF` stays unset, the loop keeps sending its
orders after the close on the day-tif the code already uses, and the branch
`moo-orders` is archived as tag `archive/moo-orders` and deleted.

The evidence is `docs/research/moo_rebalance_1023.md`: the 2026-10-23 rebalance
realized **11.0 bp** against a **4.8 bp** expectation, and the split shows the cost
sits in the opening auction, which is exactly where a market-on-open order would
trade. Moving the orders into the auction without a measured spread would replace one
unmeasured cost with another: the fills we have are simulated paper fills against the
broker's own opening prints, so the gap between them and a real auction price is not
observable in our data.

Revisit when the order-time quotes give a measured spread - that is, once the loop
records the bid/ask it saw when it sent a leg, so a market-on-open price can be
compared with the quote it replaced. Until then the decision is to leave the order
type alone and keep the 11.0 bp figure as the cost of the current path.

## 2026-10-31: the paper NAV stays at $1M

**Declined: raising the paper NAV to $5M.** The book trades 169-199 names at gross
1.0, and at $1M the smallest whole-share position is already a few dollars: raising
NAV five-fold would shrink that quantisation error, which is the only argument for it.
Against that, every cost figure, every capacity study and the whole stored live history
are denominated at $1M, and the minimum position and $250 send floor are calibrated to
it, so a change would silently re-base the cost per unit of turnover and break
comparability with the 2026-09-30 reporting window that just started. The
quantisation is reported honestly in every proposal manifest
(`quantization.gross_notional_error_usd`), so a reader can see it rather than guess.
Revisit only alongside a deliberate re-basing of the cost model.

## 2026-10-31: `EFB_DESIGN_RETURNS=clean` is not adopted

**Declined.** The flag would build the book on returns with the corporate-action and
reuse breaks removed. The 2026-10-31 audit found the breaks are three names out of 504
(`ticker_identity`: reused symbols with an undeterminable break date, DD among them)
and all three are already excluded from the book before sizing. So the flag would
change no weight today, and it would take the design away from the panel the whole
research record was built on - an identity proof in one direction, and a silent
divergence from every stored study in the other. The named exclusions are the honest
answer instead, and they are now stated in the email and in
`docs/research/excluded_names.md`.

## 2026-10-31: the floor release band is not adopted

**Declined.** The band would let a name sit slightly under the risk floor instead of
being dropped, smoothing the keep/drop line. It was declined because the line is
already handled for the case that matters: `enforce_final_cap` re-caps and re-projects
the vector that trades, so a name the floor pushed over the variance cap is brought
back under it, and the floor search itself is recorded in every manifest
(`floor_search_cycles`, `floor_search_passes`, `n_kept_drop_only`,
`n_kept_one_pass_admission`). A band would add a second, fuzzier rule on top of a
mechanism that is measured and reported; the churn it would hide is better seen than
smoothed.

## Open question 2026-10-31: the 10% volatility target is unreachable at gross 1.0

**Not a decision yet.** The 2026-11-23 rehearsal built the book with the live settings
and read **2.31% predicted annual volatility against a 10.00% target**. That is not a
one-off: across the 24 stored proposals the achieved figure runs 2.22%-2.86% on every
close but one, `gross_cap_bound` is true on 18 of them, and the four closes from
2026-10-27 to 2026-10-30 all sit at 2.8% with gross at 1.0. The one exception is
2026-09-25 at exactly 10.0%, before the book was gross-capped.

### Where the number comes from

`TARGET_ANNUAL_VOL = 0.10` is declared in three modules - `live/evening_job.py` ("the
E10 target"), `efb/allocate.py` and `efb/size.py` - and it is a *research* parameter:
E10 was the vol-targeting study, and E8 sized synthetic books to it. The live loop
inherited it as the scale it aims at.

### What acts on it

`live/evening_job.py::_scale_to_target` scales the sized book so its predicted annual
volatility equals 10%, and then refuses: if that scale would need gross above
`GROSS_CAP = 1.0` it scales to gross 1.0 instead, sets `gross_cap_bound = true` and
stores the achieved vol beside the target. So the target is consulted on every close
and overruled on 18 of 24 - the manifest says both numbers and the page shows neither
prominently.

### Is it a real gap or a stale setting?

**Both, and they are the same fact from two ends.** The book's unlevered predicted vol
is about 2.8%; reaching 10% needs roughly 3.6x gross, which a `GROSS_CAP` of 1.0
forbids by construction. So either

- the *cap* is the binding decision and the target is stale - a number from a research
  design that assumed leverage the live book may not take; or
- the *target* is the decision and the cap is too low - the owner wants a 10%-vol book
  and must allow gross ~3.6, which changes the position sizes, the cost model and the
  capacity numbers along with it.

Nothing else in the loop reads `target_annual_vol`, so this is a reporting and
intent question rather than a sizing bug: no order is wrong today, and the book is
doing exactly what the cap says.

### Recommendation for the owner

1. **Decide which number is the promise.** If gross 1.0 stands, restate the target as
   "10% at gross 3.6, capped at gross 1.0: 2.8% delivered" wherever it is printed, so
   the manifest and the page stop implying a book that is not there. That is a docs
   and page change, and it can be made this week.
2. **Do not raise the gross cap as a side effect.** Leverage is a risk decision with a
   cost and capacity consequence; it needs its own identity proof (expected cost,
   borrow, and the drift guard's readings all move with gross), not a constant edit.
3. If a 10%-vol book is what is wanted, the clean route is an explicit leverage step in
   the allocation layer, sized off the *achieved* vol the manifest already records, so
   the loop keeps building a gross-1 book and the lever is one number with its own
   audit trail.
