# Rehearsal: the 2026-11-23 rebalance, built read-only on the 2026-10-30 close (P1e)

Run 2026-10-31 against the 2026-10-30 tree, `store=False`, with the live settings:
`EFB_HEDGE_MODE=cap_then_rehedge`, `EFB_DRIFT_GUARD=0.05`, `cadence_mode=1` so the
close is treated as a rebalance day, NAV $1,000,000. Nothing was written: no store, no
R2, no broker.

The held book is the reconstruction of the 2026-10-23 rebalance built the same way,
because this shell has no account read. Legs, turnover and cost are therefore
*indicative*: they measure the distance between two reconstructions, not between the
account and a target.

## The books

| | 2026-10-23 (the held book) | 2026-10-30 (the rehearsal) |
| --- | --- | --- |
| names kept | 199 | 178 |
| gross | 1.000000 | 1.000000 |
| net | 0 | -6.9e-18 |
| largest variance share | 9.961% | 9.961% (cap not binding) |
| achieved annual vol | 2.31% | 2.31% |
| target annual vol | 10.00% | 10.00% |
| gross cap bound | yes | yes |

## The trade

| | |
| --- | --- |
| legs | 234 (119 buys, 115 sells) |
| one-side turnover | 31.09% of NAV |
| traded notional | $621,727 |
| expected cost | **5.46 bp** ($546) |
| split | spread 3.17 bp, commission 0.62 bp, impact 0.21 bp, borrow 1.46 bp |
| flips | 9: APA, BAX, BKR, CCL, CMCSA, F, FAST, IR, SWK |
| largest trades | FERG 1.38%, TRGP 1.08%, NTAP 1.03%, NOW 1.00%, INTC 0.96% |
| excluded | 2602335D, BE, DD, ILMN, P, SKYD, TWLO, VYLR |
| dropped for no risk estimate | FDXF, HONA |
| factor exposures after the hedge | every one below 1e-16 |

## What looks right

- The cap holds on the vector that trades: 9.961% against the 10% rule, and the
  manifest says it does not bind. The renormalization cannot push it back over any
  more (`live/sizing.py::enforce_final_cap`, 2026-10-31).
- Factor neutrality survives the whole path: the largest post-hedge exposure is 1.7e-17.
- The expected cost is where the model says it should be: 5.46 bp for a 31% one-side
  turnover is in the same range as the 4.8 bp the 2026-10-23 rebalance expected (and
  the 11.0 bp it realized, which is what `docs/research/moo_rebalance_1023.md` is
  about).
- Nothing errored: no `KeyError`, no missing input, no store or network dependency
  outside the tree.

## What to know before the 2026-11-23

1. **The vol target is not reachable at gross 1.0.** The book runs 2.31% annualised
   against a 10% target and `gross_cap_bound` is true: the E8 gross cap binds long
   before the E10 vol target, exactly as `_scale_to_target` documents. If the owner
   expects a 10%-vol book, that expectation is being met by leverage elsewhere or not
   at all; this rehearsal cannot tell which, and it is not a defect introduced here.
2. **`EFB_HEDGE_MODE=cap_then_rehedge` is not inert.** On the same close it keeps 178
   names where the default keeps 169, because it caps and re-projects at every pass
   rather than once at the end. The manifest records `hedge_mode`, so a book can
   always be traced to the mode that built it, but the two modes are not the same book
   and the gate's fixtures run the default.
3. **Nine flips** in one 5-session move (APA, BAX, BKR, CCL, CMCSA, F, FAST, IR, SWK):
   names whose score crosses zero between rebalances. At the monthly cadence these are
   the legs that pay spread on a round trip; nothing in the rehearsal suggests the
   classifier is confused, and each one is a small weight.
4. **The two unmeasurable spin children (FDXF, HONA) and the six short-history names**
   stay out, so the book is built on 178 of 504. That is the coverage item in
   `docs/research/excluded_names.md`, not something the rehearsal can fix.
