# Owner fix: recompute the stored attribution rows after the B4 variance fix

**Applied 2026-10-20 23:42 UTC, narrow mode only.** The full-row upsert described
below turned out to re-derive columns it must not touch; see
["Applied 2026-10-20"](#applied-2026-10-20-narrow-mode) at the end for what was
actually written, what was backed up and how to roll it back. Read that section
before running anything: the command to use is now `--only-pre-hedge-vol`.

## What is wrong

`nov11-b4-attribution-variance` (on `main` since 2026-10-19, merge `425fcc1`) fixed
`efb/attribution.py::_pre_hedge_vector`: it now squares the stored `idio_vol` before
rebuilding the pre-hedge book. The store's `positions.idio_vol` is a standard
deviation, and `pre_hedge_weights` sizes on `alpha / sigma^2`, so handing it sigma
made the reconstruction overweight the most volatile names and **overstate the
volatility the hedge removed**.

Every `efb.attribution` row was written before that fix, so every row's
`pre_hedge_vol` (and the hedge effect the page reports as the difference from
`hedged_vol`) is too high. The fitted P&L terms - `pnl_factor`, `pnl_idio`,
`pnl_cost`, `pnl_total` - are **not** affected: the fix is upstream of the book that
traded.

## The command

```bash
cd <repo>
set -a; source .env; set +a          # or run it on Render, where the vars are set

python scripts/recompute_attribution.py --root <live data tree>            # dry run
python scripts/recompute_attribution.py --root <live data tree> --apply
```

`--root` is the tree the evening reads (seed + appendix). On Render that is the run
tree; on this machine the 2026-10-19 cut tree was used. Optional `--since` /
`--through` limit the closes.

The script empties `attributed_days()` so the stored days are recomputed rather than
skipped, captures `store.upsert` instead of calling it, and prints the stored value
beside the recomputed one. **Only `--apply` writes**, and it only upserts days that
already have a row.

## The dry-run output (2026-10-20, before any write)

```
recompute: {'n_stored': 16, 'n_done': 0, 'sessions': ['2026-09-28', ..., '2026-10-19']}

close         pre-hedge before   pre-hedge after  hedged before  hedged after  identity after
2026-09-28              18.69%            15.61%         16.47%        16.47%       -3.11e-17
2026-09-29              18.69%            15.61%         16.47%        16.47%        6.08e-05
2026-09-30              11.98%             9.36%          2.87%         2.87%        2.43e-17
2026-10-01              11.75%             8.93%          2.76%         2.76%        3.24e-19
2026-10-02              11.55%             9.01%          2.68%         2.68%        3.44e-18
2026-10-05              10.77%             8.46%          2.48%         2.48%        1.43e-16
2026-10-06              10.26%             7.85%          2.55%         2.55%        1.54e-06
2026-10-07               9.87%             7.62%          2.51%         2.51%        1.17e-16
2026-10-08               9.87%             7.62%          2.51%         2.51%       -1.10e-16
2026-10-09               9.77%             7.48%          2.66%         2.66%       -5.27e-17
2026-10-12               9.34%             7.30%          2.77%         2.77%        4.94e-17
2026-10-13              10.53%             8.04%          2.64%         2.64%       -9.44e-17
2026-10-14               9.46%             7.43%          2.76%         2.76%        6.42e-17
2026-10-15               9.46%             7.43%          2.76%         2.76%       -3.20e-17
2026-10-16              10.14%             7.86%          2.75%         2.75%       -1.08e-16
2026-10-19              10.80%             8.13%          3.01%         3.01%       -2.86e-16

DRY RUN: 16 row(s) would be upserted. Nothing was written.
```

Readings:

- **Every day's pre-hedge vol falls**, by 1.9 to 3.1 points. `hedged_vol` does not
  move on any day, which is the point: the fix is upstream of the book that traded.
- **The four-term identity still closes** on every row:
  `pnl_total − (pnl_factor + pnl_idio + pnl_cost)` is ≤ 1.1e-16 on 14 of the 16.
  The two exceptions are the ones the rows already record rather than new breakage:
  2026-09-29 at **6.08e-05** (`n_computed_specific` = 2, `n_missing_return` = 1) and
  2026-10-06 at **1.54e-06** (`n_computed_specific` = 4). Neither residual changes
  with the fix; both are unchanged from the stored value.
- 2026-09-28 and 2026-09-29 carry the same numbers because they were attributed from
  the same stored book; the 2026-09-28 row has no position rows of its own, and the
  recompute rebuilds it from the 09-29 book. If you prefer to leave that day exactly
  as it is, run with `--since 2026-09-30`.

## How to verify afterwards

```sql
SELECT trade_date, pre_hedge_vol, hedged_vol,
       pnl_total - (pnl_factor + pnl_idio + pnl_cost) AS residual
FROM efb.attribution ORDER BY trade_date;
```

`pre_hedge_vol` must equal the "after" column above for each close, the residual
must be the same two exceptions and no others, and `hedged_vol` must be unchanged
from before the run. Re-running the script after `--apply` prints "before" equal to
"after" on every day and reports 0 rows to update.

## Applied 2026-10-20, narrow mode

### Why the full-row upsert was rejected

The script above upserts the *whole* recomputed row. That row is rebuilt by
`live.attribution_job.run` against **today's** store, and three of its columns are
written from the fills and the price tree of the evening that produced it. Re-deriving
them now does not reproduce the stored value, so a full-row write would have rewritten
already-published P&L:

```
close         pre-hedge before   pre-hedge after  hedged before  hedged after  identity after  other cols
2026-09-29              18.69%            15.61%         16.47%        16.47%        6.08e-05           0
2026-09-30              11.98%             9.36%          2.87%         2.87%        2.43e-17           0
2026-10-01              11.75%             8.93%          2.76%         2.76%        3.24e-19           0
2026-10-02              11.55%             9.01%          2.68%         2.68%        3.44e-18           0
2026-10-05              10.77%             8.46%          2.48%         2.48%        1.43e-16           0
2026-10-06              10.26%             7.85%          2.55%         2.55%        1.54e-06           0
2026-10-07               9.87%             7.62%          2.51%         2.51%        1.17e-16           0
2026-10-08               9.87%             7.62%          2.51%         2.51%       -1.10e-16           0
2026-10-09               9.77%             7.48%          2.66%         2.66%       -5.27e-17   6 (pnl_total, pnl_cost, realized_vol…)
2026-10-12               9.34%             7.30%          2.77%         2.77%        4.94e-17   6 (pnl_total, pnl_cost, realized_vol…)
2026-10-13              10.53%             8.04%          2.64%         2.64%       -9.44e-17   6 (pnl_total, pnl_cost, realized_vol…)
2026-10-14               9.46%             7.43%          2.76%         2.76%        6.42e-17   1 (realized_vol)
2026-10-15               9.46%             7.43%          2.76%         2.76%       -3.20e-17   6 (pnl_total, pnl_cost, realized_vol…)
2026-10-16              10.14%             7.86%          2.75%         2.75%       -1.08e-16   6 (pnl_total, pnl_cost, realized_vol…)
2026-10-19              10.80%             8.13%          3.01%         3.01%       -2.86e-16   6 (pnl_total, pnl_cost, realized_vol…)
2026-10-20               7.69%             7.69%          2.96%         2.96%        1.24e-16   2 (realized_vol, vol_ratio)
```

`other cols` counts the columns other than `pre_hedge_vol` / `hedged_vol` that the
write would change. The cause is visible in `n_filled`:

```
close       pnl_total old     pnl_total new    delta   pnl_cost old    pnl_cost new  n_filled old/new
2026-10-09     -0.0043212215     -0.0041165415  2.05e-04    -0.00141982     -0.00121514       0.0 / 171
2026-10-13      0.0013485556      0.0003346462 -1.01e-03    -0.00142579     -0.00243970       0.0 / 191
2026-10-15      0.0001925681      0.0005924712  4.00e-04    -0.00142888     -0.00102898       0.0 / 176
```

Those rows were written before the morning had recorded the day's fills
(`n_filled = 0`), so their `pnl_cost` is an estimate. The fills exist now, so the
recompute charges the actual execution cost and the day's P&L moves - by 1.01e-03 on
2026-10-13, which flips a +13 bp day to +3 bp. That is a P&L rewrite, not a
volatility fix. `realized_vol` moves for the same reason (it is the dispersion of
`pnl_total`).

### What was run instead

`--only-pre-hedge-vol` updates that one column and nothing else:

```bash
cd /Users/amankesarwani/PycharmProjects/efb-owner-fixes
set -a; source ../equity-factor-book/.env; set +a

python scripts/recompute_attribution.py \
  --root /tmp/nov11merge/cut-2026-10-20/data \
  --since 2026-09-29 --only-pre-hedge-vol            # dry run
```

```
UPDATE "efb"."attribution" SET "pre_hedge_vol" = %s, "written_at" = now() WHERE "trade_date" = %s

DRY RUN (--only-pre-hedge-vol): 15 row(s) would have pre_hedge_vol updated and no other column touched. Nothing was written.
```

**`--since 2026-09-29`** because `--since` is inclusive (`d >= Timestamp(args.since)`)
and 2026-09-28 has no positions of its own - it is rebuilt from the 09-29 book, so
recomputing it would change a day whose inputs did not change, for no reason.
2026-10-20 is selected but does not move (2.8e-17), which is the control: that row was
already written by the fixed code, so the script reproduces the live path exactly.

Applied: **15 rows**, `pre_hedge_vol` and `written_at` only.

| close | pre-hedge before | pre-hedge after | change (pts) |
|---|---|---|---|
| 2026-09-28 | 18.6918% | 18.6918% | 0.000 (not selected) |
| 2026-09-29 | 18.6918% | 15.6087% | -3.083 |
| 2026-09-30 | 11.9783% | 9.3603% | -2.618 |
| 2026-10-01 | 11.7508% | 8.9281% | -2.823 |
| 2026-10-02 | 11.5482% | 9.0140% | -2.534 |
| 2026-10-05 | 10.7682% | 8.4590% | -2.309 |
| 2026-10-06 | 10.2577% | 7.8472% | -2.410 |
| 2026-10-07 | 9.8679% | 7.6226% | -2.245 |
| 2026-10-08 | 9.8679% | 7.6226% | -2.245 |
| 2026-10-09 | 9.7682% | 7.4761% | -2.292 |
| 2026-10-12 | 9.3394% | 7.2984% | -2.041 |
| 2026-10-13 | 10.5279% | 8.0421% | -2.486 |
| 2026-10-14 | 9.4650% | 7.4319% | -2.033 |
| 2026-10-15 | 9.4650% | 7.4319% | -2.033 |
| 2026-10-16 | 10.1428% | 7.8592% | -2.284 |
| 2026-10-19 | 10.8048% | 8.1306% | -2.674 |
| 2026-10-20 | 7.6891% | 7.6891% | 0.000 (already correct) |

Every fall is inside the 1.9-3.1 point band the fix predicts.

### Applied 2026-10-21/22: 2026-09-28, and the eight estimated-cost days

Two more writes, both with the same script and the same narrow/normal modes:

1. **2026-09-28**, `--since 2026-09-28 --through 2026-09-28 --only-pre-hedge-vol`.
   The chart still opened on 18.69% because that row was written before the B4 fix
   and was never in the 09-29..10-19 range. It has no positions of its own and is
   rebuilt from the 09-29 book, so the narrow mode is the right one: **18.6918% ->
   15.6087%**, `hedged_vol` unchanged at 16.4721%, identity -3.11e-17, no other
   column touched. Backup `backups/attribution_0928_before.json` (1 row).
2. **2026-10-09..2026-10-20**, full row, `--since 2026-10-09`. These are the days
   whose rows were written before their own fills existed (`n_filled = 0`), and whose
   fills are now in `efb.fills`. Eight rows; `pnl_cost`, `pnl_total`,
   `realized_cost_bps`, `realized_vol`, `vol_ratio` and `n_filled` moved, and nothing
   else did. `pre_hedge_vol` was restated identically on every one. Backup
   `backups/attribution_fills_before.json` (8 rows).

| close | pnl_total before -> after | pnl_cost before -> after | n_filled |
|---|---|---|---|
| 2026-10-09 | -0.00432122 -> -0.00411654 | -0.00141982 -> -0.00121514 | 0 -> 171 |
| 2026-10-12 | -0.00139560 -> -0.00129091 | -0.00141867 -> -0.00131398 | 0 -> 188 |
| 2026-10-13 | +0.00134856 -> +0.00033465 | -0.00142579 -> -0.00243970 | 0 -> 191 |
| 2026-10-14 | +0.00039369 (unchanged) | 0.00 (unchanged) | - -> - |
| 2026-10-15 | +0.00019257 -> +0.00059247 | -0.00142888 -> -0.00102898 | 0 -> 176 |
| 2026-10-16 | -0.00121018 -> -0.00127656 | -0.00143490 -> -0.00150128 | 0 -> 181 |
| 2026-10-19 | -0.00053191 -> -0.00049661 | -0.00142822 -> -0.00139292 | 0 -> 163 |
| 2026-10-20 | -0.00026332 -> +0.00049675 | -0.00142773 -> -0.00066765 | 0 -> 167 |

2026-10-14 moved only `realized_vol` (empty -> 0.02453864), which is the trailing
window finally having the corrected days behind it.

Verified after both writes with a NaN-aware, tolerance-aware diff of every stored
column against the backups: the columns above and `written_at`, and nothing else.
Re-running either dry run reports `other cols = 0` on every row.

Rollback, dry run first:

```bash
python scripts/restore_attribution.py --backup docs/owner_fixes/backups/attribution_0928_before.json
python scripts/restore_attribution.py --backup docs/owner_fixes/backups/attribution_fills_before.json --apply
```

Both backups were taken with `scripts/backup_attribution_rows.py` (new), and both
restores were proven exact - 0 rows differing - before the writes.

The forward fix, so this cannot recur, is `live.attribution_job.refinalize`: the
morning re-attributes the close it just reconciled against the fills it just
recorded. See the commit and `tests/test_attribution_refinalize.py`.

## Backup and rollback

- Backup of the 14 + 2 rows written, every column:
  `docs/owner_fixes/backups/attribution_before.json` (16 rows, `since` 09-29).
- Whole table before the write, for the "nothing else changed" check:
  `docs/owner_fixes/backups/attribution_context_before.json` (17 rows).
- Restore, dry run by default:

```bash
python scripts/restore_attribution.py            # shows the difference, writes nothing
python scripts/restore_attribution.py --apply    # puts every backup row back
```

Before the apply the restore dry run reported **0 row(s) differ from the backup**
(the backup was taken from the live table and reproduced it exactly after a JSON
round trip). After the apply it reports the 15 rows with `pre_hedge_vol` as the only
data difference plus `written_at` - which is what a correct restore would undo.

### Verification after the apply

- `efb.attribution` still holds **17 rows**, same 17 dates: nothing created, nothing
  deleted.
- Per-row diff against `attribution_context_before.json`: **2026-09-28 changed in no
  column at all**; the 15 applied rows changed in `pre_hedge_vol` and `written_at`;
  **2026-10-20 changed in no column**.
- Re-running the dry run reports `every day already holds the recomputed pre-hedge
  vol: nothing to write` - the write is idempotent.
- `hedged_vol`, `realized_vol`, `pnl_*`, `n_filled`, `vol_ratio` and the identity
  residual are byte-identical to the backup on every row.
