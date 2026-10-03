# Resume

## 2026-10-03 (continued): items 0 and 1 done on `backport`, items 2 to 6 not started

Stopped at an item boundary. Nothing is part-committed.

**Item 0 (rebase) done.** `backport` was rebased onto `origin/main` (`db4d39c`)
and force-pushed with `--force-with-lease`. One conflict, in
`tests/test_e4_results.py` (main's H4 test fixes against backport's fuller H4
set); resolved to backport's version, which is a superset. main's README
structure, the "What E11 taught us" sections and the test fixes are all present.
Head after the rebase: `adc09fb`.

**Item 1 (n_eff_kept) done in `3a5c2b1`.** The culprit was not a research
finding. `efb.registry.write_registry` did `models[version] = entry`, so the E3
rebuild replaced the whole XS-v1 registry entry and dropped the `live` block (the
owner's 2026-09-24 share-only choice). `live_construction` then defaulted
`share_floor` to 0, both floors were zero, `below_floor` returned all-False, and
the drop-then-admit search kept every name: the "kept" book silently became the
full model book. Measured with `live.evening_job.build_proposal`, `n_eff_kept` /
`n_kept`, floor off against floor on: corrected panel (2026-10-02) **282.2521 /
502** to **143.2554 / 188**; pre-back-port panel (2026-09-21) **275.7918 / 499**
to **128.6541 / 173**. So the unexplained +142.5 is the disabled floor. Fix:
`write_registry` upserts only the fields a rebuild owns and carries the rest
over; the `live` block is restored on XS-v1.
`tests/test_registry.py::test_write_registry_keeps_the_live_construction` fails
on the version before the commit (`assert 0 == 20`) and passes after;
`tests/test_e11_evening.py` was failing on the branch before the fix and is 37
passed after. **This would have changed the live book at the merge**: the
regenerated seed would have carried no floor and the evening would have sized all
502 names. Ledger: `docs/hygiene_ledger.md`, 2026-10-03.

**Working tree state.** The gitignored `data/**/*.parquet` artifacts were
restored to this branch's own frozen-panel build (`/tmp/efb-neff/data`, panel
ends **2026-10-02**), excluding every path `git ls-files data` reports, so the
tracked `data/VERSION.json` and `data/models/registry.json` are untouched and
`git status` is clean. A copy with the `live` block re-injected is at
`/tmp/efb-neff/withfloor`, and the pre-back-port tree with it at
`/tmp/efb-neff/base-withfloor`.

**Items 2 to 6, not started. Next steps, in order:**

2. **E8 and E10 traded-book figures.** The scratch measurement is
   `/tmp/efb-backport/item56_quantize.py` (`quantize` + `net_returns`, read-only).
   It reads `data/portfolios/persistent_proportional.parquet` (the E10 design
   book, rho=0.02, phi=0.95, seed=1) and quantizes to the E11 construction:
   whole shares, 20-share floor, $1mn NAV, gross cap 1.0. Store `kept_*` and
   `full_book_*` beside the existing numbers (additive; do not replace) and
   confirm or correct the Phase 1 figures (Sharpe 0.98 to 0.73, about half the
   names dropped). A measurement taken after the numbers exist is not a
   criterion (STANDARDS 2b): record it as a stored block, not a new F ID, and
   put the narrative in the ledger and the memo.
3. **E9 costs.** Charge borrow on the short leg at E11's rate, split reversals
   into two cost events, apply the $250 floor at the tested AUM, record that
   borrow availability has no history to replay. Scratch: `/tmp/efb-backport/item7_constraints.py`.
   Rebuild E9 and re-score.
4. **Frozen-panel propagation, once, at `END=2026-10-02`.** Rebuild E1 to E10 in
   order (`make rebuild END=2026-10-02`); fix the stored-hash inconsistencies
   (`data/VERSION.json` against the registry for E2 to E4, and E5's stale
   `data_hash`, which is now also moved by item 1's registry edit); re-execute
   and render every E1-E10 walkthrough; update each "What E11 taught us" section
   from "measured on backport" to "applied" with the stored numbers, and add the
   item 2 figures; update the memos, `make evidence`, the status report and the
   README numbers. Note that E2, E3, E4 and E5 walkthroughs cannot re-execute on
   `main` today (E2 asserts `VERSION.json`'s hash equals the registry's TS-v1
   hash and the two differ in the tree); this item is where that is fixed.
5. Full suite once. Expected red: the two `requires_live_tree` hedge-vintage
   tests and the `merge_guard` parity test (both need a live-shaped tree, item
   6). List any other failure with its cause.
6. **Merge-day dry run, prepare only.** Regenerate the live seed into a
   temporary directory (do not upload), materialise a run root, run the
   hedge-vintage tests and the parity guard with `live/extend.py` switched to
   `returns_clean`, build the evening book at the current account NAV and
   compare it against tonight's live book, then finish `docs/backport_runbook.md`
   as the ordered 2026-11-11 checklist.

## Parked: branch `backport` (do not merge, rebase or delete)

`backport` (head `8b1bbe9`) holds the E11-to-research back-ports: the recorded
vendor spinoffs, the E3 stale-cell contract, the panel pin (`END=2026-10-02`),
E6's F6.1 re-scored on the next session's row, and the E1 reused-ticker
extension. It is parked because the remaining work is mostly record-keeping
while the merge carries live risk, and it has an unexplained `n_eff_kept` jump
(131.9 to 281.4) to resolve before any merge. Do not merge, rebase or delete it.

# Resume: pre-launch batches 2 and 3

## Alpha refresh: branch `alpha-refresh`, off `main`, NOT merged

`main` is still `d3ba599` and is frozen until the flip. Part A of the owner's
instruction is on `alpha-refresh`: refresh what the alpha formula fix affected,
prove where it did not reach, and do not merge.

- **E7** F7.4's stored conversion was rebuilt through
  `efb.alpha.alpha_from_contract` by `alpha.rebuild_conversion`, which rewrites
  one artifact per signal and nothing else. `sprints/E7/RESULTS.json` records the
  revision with both data hashes, the old values beside the new ones, and
  `n_changed` 1; the E7 walkthrough was rebuilt, executed and rendered. Every IC,
  audit, neutral-IC, quantile, regime and ledger artifact is byte-identical, and
  the RG-Signal answers did not move.
- **E8, E9 and E10** never used the variance spelling. Their results and
  walkthroughs are unchanged, and the evidence is in `handoff/REPORT.md`.
- **E11** `live/construction_table.parquet` and
  `live/construction_weights.parquet` are rebuilt under the corrected alpha.
  Share-only 20 shares is still the row the evening sizes from and the
  pre-registered re-decide trigger has not fired; nothing about the live
  construction was changed. The E11 walkthrough came from `e12` and was
  rewritten onto the contract, executed and rendered.
- **The status report**'s MRNA passages now say the cause was the alpha formula
  and that the variance cap no longer binds on the traded book, with the number
  of clamped names stated rather than the claim alone.

Part B waits on the owner: rebase and merge `page`, `e13`, `e12`, then
`alpha-refresh`, regenerate conflicting fixtures, run the full suite once, hand
over the E12 SQL and the row-level-security block, then delete the merged
branches leaving `main`.

Written at the close of batch 3, which is on `prelaunch-batch3` and merged to
`main`. If this file is the first thing you read, the state is:

- **S1** `efb.alpha.alpha_from_contract` is the one alpha contract
  (`IC x sigma x z x kappa`, `sigma = sqrt(specific variance)`), used by the
  evening job, `efb/alpha.py`'s E8 conversion and the construction table.
- **S2** the traded book's risk figures and the full book's are on the
  reconciliation row, the run_status row and the snapshot, under `traded_risk`
  and `full_risk`, and the manifest carries the traded book name by name. Since
  batch 3, the **unqualified** `gross`, `net` and forecast volatility in all three
  places are the traded book's, and the 499-name figures are the `full_book_*`
  ones.
- **S3** NAV is the account's own equity, read in the same request that reads the
  book, and the broker's per-name book is stored in `efb.broker_positions`. An
  equity of zero or below raises (it is an answer, not a failed read), and the nav
  row's `realized_pnl` is the change in equity since the previous stored NAV row.
  **The schema must be re-applied to the project before the flip**, twice over:
  the new table from batch 2 and the six `full_book_*` columns from batch 3 only
  exist in the database once `live/supabase_schema.sql` is run against it, and
  `live/supabase_roles.sql` grants the writer's delete on the new table.
- **S4** the positions check compares the account against the last stored book
  strictly before the close being priced.
- **S5** a partial short cover rounds down to whole shares; a cover under one
  whole share is a recorded skip (`COVER_UNDER_ONE_SHARE`) that does not make the
  run incomplete.
- **S6** the daily run refuses outside 16:00-20:00 New York unless
  `EFB_FORCE_HOUR=true` (exact string only), and a refusal sends a one-line email
  saying it was refused and why.
- **S7** a kept name the $250 minimum skips is a recorded leg with
  `reason_code=BELOW_MIN_NOTIONAL` and is named in the email, and it does not make
  the run incomplete.
- **S8** `EFB_SNAPSHOT` and the four R2 variables are checked at the start of the
  run, before the seed download and long before any order.

Left for the first week, unchanged by these batches: the holding versus trading
cost labels, rebasing e12, the static snapshot fields, and the documentation
corrections.

- Spinoff detection: check whether Alpaca's corporate-action announcements cover
  spinoffs like CTVA/Vylor 2026-10-01; if so, cross-check large moves against them
  before they reach the fit.

- `pd.DataFrame` is `Any` to mypy here, so a function declared to return one can
  return nothing with `make lint` green: `pandas` ships no `py.typed` in this
  environment and sits in the `ignore_missing_imports` override (a probe declared
  `-> int` is flagged, the same probe declared `-> pd.DataFrame` is not). The
  snapshot published an empty per-name book on that silence on every evening the
  loop priced its own proposal.

One artefact is known-stale: `live/construction_table.parquet` is the
committed decision table built before S1, so its numbers describe the pre-S1 book.
Rebuild it with `python -m live.construction_table` when the owner wants it
current, and check the choice of construction still holds (it does: the share-only
floor is still the row the evening sizes from).

The verification for both batches is in `handoff/REPORT.md`: the batch 2 section
carries the S1 before/after table and the three-day rehearsal transcript, and the
batch 3 section carries what the unqualified-field change did, with the numbers
read from the committed fixtures.
