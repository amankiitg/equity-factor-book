# Every check that can act on one name, and what it does now

Read on 2026-11-04. The point of the list is the class: seven failures since launch were
one name's data stopping the whole evening, and each was answered where it was found. This
is the inventory, the behaviour each check has today, and the one mechanism the answers now
route through (`live/exclusions.py`).

## The mechanism

A name whose data cannot support an order leaves the book for the night, carries a reason
and the reader that decided it, and the evening's message says them in one sentence:
`Excluded tonight: KVUE (no usable close at the close), FDXF (no risk estimate).` The
manifest publishes the same list as `excluded_tonight`. A held position is not quietly
dropped: the broker's refusals that cannot change are in `UNREACHABLE_REFUSALS`, so the
name is reported as owed and never carried to the next evening.

The stop is one number: `exclusions.MAX_EXCLUSIONS = 10`, the line the no-price and
no-risk drops already drew. More names out than that is an input that failed for the
panel, not a market with holes in it.

## Name-level checks: exclude for the night

| check | file:line | behaviour today |
| --- | --- | --- |
| no usable close at the close | `live/evening_job.py:1330` `priced_names_or_stop` | the name is dropped and named; more than `MAX_PRICE_DROPS` (10) stops the run |
| no specific variance | `live/evening_job.py:1394` `risk_names_or_stop` | dropped and named; more than `MAX_RISK_DROPS` (10) stops |
| a held name with no close, hold day | `live/evening_job.py:2990` `drop_unpriced_held` | zeroed out of the published book, named, gross falls with it |
| a kept name with no price at quantization | `live/evening_job.py:1450` `usable_prices` | raises; unreachable on the rebalance path because `start=priced` filters first, and the hold path drops it above. Kept as an invariant |
| the broker will not lend a short | `live/evening_job.py:2790` `drop_not_shortable` | dropped before sizing, named |
| the asset is retired at the broker | `live/alpaca.py:560` `SymbolResolver._resolve_stale` | `ASSET_INACTIVE` with the broker's reason, recorded as owed, never carried |
| the broker carries no asset under any spelling | `live/alpaca.py:1360` `SYMBOL_NOT_FOUND` | skipped and named; no order sent |
| the broker will not let the account trade it | `live/alpaca.py:380` `short_refusal` | `ASSET_NOT_TRADABLE` / `ASSET_NOT_SHORTABLE`, recorded as owed |
| a vendor restatement nothing explains | `live/corporate_actions.py:1200` `apply_to_append` | the name is `Suspended` for the session; its return is nulled, not guessed |
| a spin-off ratio its own factor contradicts | `live/corporate_actions.py:634` | the return is nulled and the flag says which ratio and which factor disagreed |
| a spin-off child close that did not come back | `live/corporate_actions.py:855` | the parent's cell is nulled, the child is named |
| a name outside the fitted universe | `live/evening_job.py:2520` `load_spy_universe` | in the manifest's `excluded`, with its cause and age; a standing list, not tonight's |

## Systemic failures: still a stop

| check | file:line | why it stays |
| --- | --- | --- |
| more than 10 names out, any mix of the reasons above | `live/exclusions.py:86` `guard` | the input, not the names |
| fewer than `MIN_NAMES` (50) left in the sizing universe | `live/evening_job.py:2561`, `:2715` | a book of thirty names is another book |
| a duplicated universe row | `live/evening_job.py:2490` | warned and kept once; never seen |
| any input stale for live names | `live/staleness.py:521` `check` | the close being priced is not the close the input describes |
| the enforced book failing its own floor checks | `live/evening_job.py:2883` | the book that trades must be the book that was checked |
| a transport-class submit failure | `live/alpaca.py:328` `classify_submit_failure` | the order may have arrived |
| NAV unreadable or non-positive | `live/evening_job.py:2470` | nothing can be sized |
| the calendar, the signal row, the risk pieces missing | `live/evening_job.py:2596`, `:2607`; `live/cadence.py:144` | the panel, not a name |

## What was routed through the mechanism on 2026-11-04

`live/exclusions.py` is new; `build_proposal` publishes `excluded_tonight` from the price,
risk and broker drops and guards it; `scripts/run_live_daily.py` adds the corporate-actions
suspensions, which had no consumer before (the CTVA shape stopped at `Outcome.suspended`
and reached neither the manifest nor the mail); `live/notify.py` prints the one sentence and
keeps the universe's own standing list on its own line, because the two are different facts.
