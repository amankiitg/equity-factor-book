# Owner fix: recompute the stored attribution rows after the B4 variance fix

**Not applied. Run it yourself; it is a dry run until you pass `--apply`.**

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
