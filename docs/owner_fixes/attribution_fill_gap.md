# Owner fix: the attribution rows' `max_fill_gap`, computed from the fills

**Not applied. This note is the dry run and the plan; nothing was written.**

## What is wrong

`efb.attribution.max_fill_gap` is meant to be the largest amount a close still owed
after its fills, and every stored row was written by a reader of
`efb.orders.filled_notional`:

```python
intended = pd.to_numeric(group["intended_notional"], errors="coerce")
filled = pd.to_numeric(group["filled_notional"], errors="coerce")
gap = (intended - filled).abs().max()
```

That column is written at submission, before the open, and never updated afterwards.
It is 0 in all 3,850 rows `efb.orders` has ever held, so `filled` was 0 for every leg
and the number is the largest *leg* of the day rather than the largest amount still
owed. On the 2026-10-23 close it reads $20,696.16; the close filled 208 of 208 legs
and the largest remainder was $352.07.

The writer now reads `efb.fills` through `live.fills.filled_dollars`, which signs each
fill by the direction of the leg it belongs to and sums per ticker, and answers `None`
for a close the fills table holds no row for. A close with no fills row reports null,
which is "not known" rather than "nothing filled".

## The dry run (2026-10-27, read-only)

`live.attribution_job.session_inputs` run against the live store's own frames, no
write and no upsert:

| close | legs | filled | stored gap | recomputed | delta |
|---|---|---|---|---|---|
| 2026-09-28 | 0 | 0 | null | null | - |
| 2026-09-29 | 177 | 0 | 20,852.32 | null | - |
| 2026-09-30 | 178 | 0 | 20,963.61 | null | - |
| 2026-10-01 | 212 | 1 | 17,358.77 | 17,358.77 | +0.00 |
| 2026-10-02 | 230 | 207 | 14,103.52 | 857.53 | -13,245.99 |
| 2026-10-05 | 233 | 197 | 13,130.34 | 1,520.89 | -11,609.46 |
| 2026-10-06 | 220 | 190 | 13,136.16 | 7,063.49 | -6,072.67 |
| 2026-10-07 | 0 | 0 | null | null | - |
| 2026-10-08 | 227 | 202 | 12,501.57 | 7,056.60 | -5,444.97 |
| 2026-10-09 | 193 | 171 | 12,172.89 | 7,056.60 | -5,116.29 |
| 2026-10-12 | 205 | 188 | 12,105.30 | 7,056.60 | -5,048.70 |
| 2026-10-13 | 216 | 191 | 12,147.63 | 573.08 | -11,574.55 |
| 2026-10-14 | 0 | 0 | null | null | - |
| 2026-10-15 | 199 | 176 | 17,506.93 | 222.89 | -17,284.04 |
| 2026-10-16 | 202 | 181 | 18,888.54 | 249.50 | -18,639.04 |
| 2026-10-19 | 197 | 163 | 19,131.53 | 261.09 | -18,870.44 |
| 2026-10-20 | 190 | 167 | 10,617.70 | 248.88 | -10,368.83 |
| 2026-10-21 | 203 | 170 | 12,599.29 | 543.22 | -12,056.07 |
| 2026-10-22 | 214 | 197 | 13,751.20 | 340.55 | -13,410.66 |
| 2026-10-23 | 224 | 208 | 20,696.16 | 352.07 | -20,344.10 |
| 2026-10-26 | 180 | 0 | 2,434.05 | null | - |

**14 of 21 rows would change.** Four kinds:

- **11 rows fall** by $5,049 to $20,344. These are the closes whose fills are in the
  store and whose stored number was the largest leg.
- **2026-10-01 is unchanged** at 17,358.77, which is the control that the new reader
  reproduces the old one where the old one was right: one leg of 212 filled that day,
  and that leg was also the largest.
- **2026-09-29 and 2026-09-30 become null.** `efb.fills` holds no row before
  2026-10-01, so those two closes have no recorded fill and their remainder is not
  known. They are the two closes before the fills table's first row.
- **2026-10-26 becomes null.** Its legs filled at the 2026-10-27 open; the morning of
  2026-10-27 writes the fills, and the evening's re-price restates the row then.

Three rows already hold null (2026-09-28, 2026-10-07, 2026-10-14), so a null in this
column is a state the reader and the page already handle.

## Backup and restore

The pattern is the one `docs/owner_fixes/attribution_recompute.md` used: a backup of
every affected row with every column, taken before the write, and a restore script
that is a dry run until `--apply` and whose restore is proved exact - zero rows
differing - before the repair is applied.

```bash
cd <repo>
set -a; source .env; set +a

# 1. the backup, every column, the rows the dry run says move
python scripts/backup_attribution_rows.py --out docs/owner_fixes/backups/attribution_fill_gap_before.json \
       --since 2026-09-29

# 2. the repair, as a dry run: prints stored beside recomputed, writes nothing
python scripts/recompute_attribution.py --root <live data tree> --only-max-fill-gap --since 2026-09-29

# 3. the write, when the dry run matches the table above
python scripts/recompute_attribution.py --root <live data tree> --only-max-fill-gap --since 2026-09-29 --apply

# 4. the restore, dry run first, then applied - only if the write has to come back out
python scripts/restore_attribution.py --backup docs/owner_fixes/backups/attribution_fill_gap_before.json
python scripts/restore_attribution.py --backup docs/owner_fixes/backups/attribution_fill_gap_before.json --apply
```

**Applied on 2026-10-28.** `--only-max-fill-gap` now exists, with the same shape as
`--only-pre-hedge-vol`, because a whole-row upsert would re-derive columns from today's
store and must not (see `attribution_recompute.md`, "Why the full-row upsert was
rejected"). It reads `efb.orders` and `efb.fills` and no data tree. Measured against the
live store: 16 of the 21 stored rows moved, two already held the recomputed value
(2026-10-01 and 2026-10-26) and three have no orders row at all (2026-09-28, 2026-10-07,
2026-10-14). The rows dated 2026-09-29 and 2026-09-30 became null, because the store
holds no fills for either close.

The write touched `max_fill_gap` and `written_at` and no other column, checked by
re-reading every row and comparing against the backup with the JSON and float columns
normalized: zero columns moved besides those two. Re-running the dry run afterwards
prints "every day already holds the recomputed max_fill_gap". The backup is
`~/efb-backups/2026-10-28/attribution_before_max_fill_gap.json` and its restore is

```
python scripts/restore_attribution.py --backup ~/efb-backups/2026-10-28/attribution_before_max_fill_gap.json
```

which reported 16 rows differing from the backup, dry run, nothing written. The forward
fix was already in place: every row the evening writes from 2026-10-27 onward carries the
number this note recomputes.

## What this note does not do

- It writes nothing: no row, no artifact, no object.
- It does not change `n_target` or `n_filled`. `n_filled` is already read from
  `efb.fills` and was right; the 2026-10-26 row's `n_filled = 0` is correct, because
  its legs had not filled when the row was written.
- It does not touch `scripts/review_week.py`, which prints this number: it reads
  `record["max_fill_gap"] or 0.0` and so prints "worst difference $0" for a null, which
  is a wording change for a later day rather than a defect in this one.
