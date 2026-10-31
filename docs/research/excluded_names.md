# Names the book cannot size, and why (2026-10-31)

The evening drops a name when it has no risk estimate for it. This note states the
rule, names every name the 2026-10-30 run dropped, and records one experiment that
looked like the fix and was not: adding the missing GICS rows moves six names from
"no GICS row" to "no specific variance" and changes the whole book with it.

## The rule

> A name enters the book only if the model published a finite, positive specific
> variance for it on the close.

That is the whole test. `n_specific_var_missing` in the proposal manifest counts the
universe members that failed it, and the evening email states the rule in the
"no risk estimate" line rather than only listing the names.

There are two distinct reasons a name fails it, and they have different fixes:

| Reason | Meaning | Fix |
| --- | --- | --- |
| Not in the fitted set | the name is in the universe and priced, but the model has no fitted variance for it on the close | coverage work on the model's descriptor and history inputs |
| Not in the universe | no GICS row, or a symbol the identity rule drops, or a line that is not common stock | data repair, or accept the exclusion |

## The 2026-10-30 exclusions

`build_proposal(store=False, as_of=2026-10-30)` on the 2026-10-30 tree, default hedge
mode: `n_kept 169`, `n_excluded 8`, two more dropped for no risk estimate after
sizing.

| Ticker | Label the run gives it | What the data says | Bucket | What would fix it |
| --- | --- | --- | --- | --- |
| BE | no GICS row | 4,222 return sessions to 2026-10-30; members all through; descriptors stop 2026-08-31; no variance after that | not in the fitted set | find why the descriptor panel stops for it on 2026-09-01 |
| ILMN | no GICS row | 4,233 return sessions to 2026-10-30; descriptors stop 2026-08-31 | not in the fitted set | same |
| P | no GICS row | 4,222 return sessions to 2026-10-30; descriptors stop 2026-08-31 | not in the fitted set | same |
| DD | in the sectors file but absent from the processed returns panel | `ticker_identity` marks the symbol reused, `rename_suspect: true`, break date undeterminable, `action: drop` | not in the universe | a determined break date for the reuse |
| SKYD | no GICS row | 19 return sessions, 2026-10-06..10-30 | not in the fitted set | history: under the model's minimum |
| TWLO | no GICS row | 19 return sessions, 2026-10-06..10-30 | not in the fitted set | history |
| VYLR | no GICS row | 22 return sessions, 2026-10-01..10-30 | not in the fitted set | history |
| 2602335D | no GICS row | a Hologic CVR/contra line (`436CVR021`, "CONTRA HOLOGIC INCORPO"), not common stock | not in the universe | nothing: it should not be sized |
| FDXF | no specific variance | 4,233 return sessions, descriptors present on 2026-10-30, never a fitted variance | not in the fitted set | coverage |
| HONA | no specific variance | as FDXF | not in the fitted set | coverage |

SKYD, TWLO and VYLR are recent listings of the current symbol line, so the minimum
history rule is doing its job and states itself in the email. BE, ILMN and P are not:
they are old, priced and still index members, and the model simply stopped fitting
them.

The specific-variance panel for 2026-10-30 covers **500 of 503** names, and none of
the nine above is among the 500: the fit is the gate, not the sector label.

## The experiment that was reverted

`scripts/refresh_sectors.py` (union-only, `--apply --backup`) adds the six tickers the
newest `wikipedia_constituents` snapshot carries but `efb.e11_sectors` does not: BE,
ILMN, P, SKYD, TWLO and VYLR.

Applied to a copy of the tree, and compared against the same copy with only
`processed/sectors.parquet` swapped (no other file differs; the 503 shared tickers
have identical sector labels, so the delta is exactly the six rows):

| | sectors 503 (today) | sectors 509 (six rows added) |
| --- | --- | --- |
| `n_kept` | 169 | 163 |
| names entering / leaving the book | 23 leave, 17 enter | |
| max abs weight change on the 146 common names | 0.61% | |
| the eight | excluded: 2602335D, BE, DD, ILMN, P, SKYD, TWLO, VYLR | excluded: 2602335D, DD; dropped for no risk: BE, ILMN, P, SKYD, TWLO, VYLR |

The six are unmeasurable either way, so nothing is gained, and the sector labels feed
the descriptor cross-section and the variance shrinkage's bucket means, so the floor
search lands on a different book. The identity proof the change needs - only the named
tickers move - does not hold, so it is not merged. The store was reverted to its 503
rows (the six rows deleted, read back to confirm), and `web/src/sector_map.json` is
untouched.

The lesson is in the buckets above: the six failed for two different reasons and the
sector row was neither. Fixing them means fixing the fitted-set coverage, which is its
own piece of work with its own identity proof.

## Recommendation

1. Treat "no specific variance" as the rule and keep the email line that says so.
2. Investigate the descriptor cutoff for BE, ILMN and P before touching sectors: prices,
   returns, membership and the raw descriptor panel are all complete for them through
   2026-10-30, so the loss is inside the model's own per-name coverage.
3. Leave SKYD, TWLO and VYLR to history; they become measurable by accumulating
   sessions, not by a data repair.
4. Do not size 2602335D at all, and fix its label so the exclusion says "not common
   stock" rather than "no GICS row".
