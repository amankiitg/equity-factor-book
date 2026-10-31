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
