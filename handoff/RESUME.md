# Resume: prelaunch batch 2 (S1 to S8)

Written at the close of batch 2, which is on `prelaunch-batch2` and merged to
`main`. If this file is the first thing you read, the state is:

- **S1** `efb.alpha.alpha_from_contract` is the one alpha contract
  (`IC x sigma x z x kappa`, `sigma = sqrt(specific variance)`), used by the
  evening job, `efb/alpha.py`'s E8 conversion and the construction table.
- **S2** the traded book's risk figures and the full book's are on the
  reconciliation row, the run_status row and the snapshot, under `traded_risk`
  and `full_risk`, and the manifest carries the traded book name by name.
- **S3** NAV is the account's own equity, read in the same request that reads the
  book, and the broker's per-name book is stored in `efb.broker_positions`.
  **The schema file must be re-applied to the project before the flip**: the new
  table only exists in the database once `live/supabase_schema.sql` is run against
  it, and `live/supabase_roles.sql` grants the writer's delete on it.
- **S4** the positions check compares the account against the last stored book
  strictly before the close being priced.
- **S5** a partial short cover rounds down to whole shares; a cover under one
  whole share is a recorded skip.
- **S6** the daily run refuses outside 16:00-20:00 New York unless
  `EFB_FORCE_HOUR=true` (exact string only).
- **S7** a kept name the $250 minimum skips is a recorded leg with
  `reason_code=BELOW_MIN_NOTIONAL` and is named in the email, and it does not make
  the run incomplete.
- **S8** `EFB_SNAPSHOT` and the four R2 variables are checked at the start of the
  run, before the seed download and long before any order.

Left for the first week, unchanged by this batch: the holding versus trading cost
labels, rebasing e12, the static snapshot fields, and the documentation
corrections. One artefact is known-stale: `live/construction_table.parquet` is the
committed decision table built before S1, so its numbers describe the pre-S1 book.
Rebuild it with `python -m live.construction_table` when the owner wants it
current, and check the choice of construction still holds (it does: the share-only
floor is still the row the evening sizes from).

The verification for the batch is in `handoff/REPORT.md`'s batch 2 section: the
commands, the S1 before/after table, and the three-day rehearsal transcript.
