# Owner fix: back-fill `efb.reconciliation`'s two morning-owned columns

**Applied 2026-10-20 23:51 UTC.** 14 rows back-filled; see
["Applied 2026-10-20"](#applied-2026-10-20) at the end for the before/after table and the
rollback command. The numbers in the 2026-10-20 dry run below are one session stale:
the count is 14, not 13.

## What is wrong

The evening writes the day's reconciliation row **before its orders settle**, so it
can only leave `filled_notional = 0.0` and `realized_annual_vol` empty. The morning
is what knows both, and before nov11's B1/B2 it never wrote them back. The zeros
therefore read as measurements - a stored zero is the one thing a placeholder must
never look like - and the page's reconciliation block shows a day that filled
nothing.

Measured now, read-only:

| | rows |
|---|---|
| `filled_notional = 0.0` | **14** |
| `realized_annual_vol IS NULL` | **7** |
| one or both missing | **14** (the union; 7 overlap) |
| of those, written before 2026-10-16 | 11 |

The brief named **nine**; the table says **fourteen** rows carry at least one
placeholder and **eleven** predate the nov11 merge. The script targets every row that
is actually missing a value, so the count in your run is the measured one rather than
a typed list - check the dry-run output below against what you expect.

## The command

```bash
cd <repo>
set -a; source .env; set +a

python scripts/backfill_reconciliation.py                         # dry run
python scripts/backfill_reconciliation.py --apply
```

What each column becomes:

- **`filled_notional`** = `sum(abs(filled_notional))` over `efb.fills` for the close,
  the same expression `live/reconcile.py::_execution_row` uses.
- **`realized_annual_vol`** = `live.reconcile.realized_annual_vol_for(close,
  attribution)` - the standard deviation of the book's daily P&L over the stored
  attribution rows up to the close, annualized (a fraction, so `0.03` is 3%).

**A close with no fills rows at all is reported and left alone** unless you pass
`--include-empty-fills`: an empty fills table can mean a day that genuinely traded
nothing (the 2026-09-25 dry run, the 2026-09-29/30 rows) or a morning that has not
run yet (always the newest close). The script cannot tell those apart, so it does not
guess.

## The dry-run output (2026-10-20, before any write)

```
close         filled before   filled after  realized before  realized after   note
2026-09-25             0.00           0.00                -               -   no fills rows: verify the morning ran; realized needs two attributed sessions
2026-09-29             0.00           0.00                -            0.05   no fills rows: verify the morning ran
2026-09-30             0.00           0.00                -            0.03   no fills rows: verify the morning ran
2026-10-01             0.00         517.42                -            0.03
2026-10-02             0.00     411,229.54                -            0.03
2026-10-05             0.00     425,739.98                -            0.03
2026-10-06             0.00     342,598.25                -            0.03
2026-10-08             0.00     494,417.34                -            0.02
2026-10-09             0.00     376,262.54                -            0.03
2026-10-12             0.00     409,357.31                -            0.02
2026-10-13             0.00     437,952.78                -            0.03
2026-10-15             0.00     429,573.30                -            0.03
2026-10-16             0.00     480,740.60                -            0.03
2026-10-19             0.00           0.00                -            0.02   no fills rows: verify the morning ran

newest close considered: 2026-10-19

DRY RUN: 13 row(s) would be updated. Nothing was written.
```

Readings:

- The filled notionals match the trade sizes in `efb.fills` (2026-10-02: 207 legs,
  $411,229.54; 2026-10-05: 199 legs, $425,739.98 - the churn study's own numbers).
- **2026-10-19 must not be back-filled yet**: its morning (2026-10-20 15:30 UTC) has
  not run, so the fills table is empty for it and `0.00` would be a fresh placeholder
  written as a measurement. Re-run the script after the morning and it will fill it.
- 2026-09-25 has no attribution rows before it, so `realized_annual_vol` cannot be
  computed and stays null - which is the honest value, not a zero.
- 2026-09-29 and 2026-09-30 keep `filled_notional = 0.00`: they were dry-run days
  with no fills rows, and the script reports them rather than deciding. If you know
  they traded nothing, `--include-empty-fills` writes the zero explicitly.

## How to verify afterwards

```sql
SELECT trade_date, filled_notional, realized_annual_vol
FROM efb.reconciliation ORDER BY trade_date;
```

Every row up to 2026-10-16 must carry a non-zero `filled_notional` where
`efb.fills` has rows for that close, and a `realized_annual_vol` where two
attribution sessions precede it. `intended_notional`, `forecast_annual_vol`, the
cost split and the risk blocks must be **byte-identical** to before: the script
rewrites the whole row from the row it read and changes only those two columns.

Re-running the dry run after `--apply` prints "before" equal to "after" and `0 row(s)
would be updated`.

## Applied 2026-10-20

Ran at 23:51 UTC on `owner-fixes`. The 2026-10-19 evening's morning (2026-10-20
15:30 UTC) had run, so **2026-10-19 was updatable** and the count moved from 13 to
**14** - 13 as before, plus 10-19, plus 10-20 which now has the two attributed
sessions its `realized_annual_vol` needs. 2026-10-20 becomes the new "no fills rows"
close, exactly as 10-19 was before it.

```
close         filled before   filled after  realized before  realized after   note
2026-09-25             0.00           0.00                -               -   no fills rows: verify the morning ran; realized needs two attributed sessions
2026-09-29             0.00           0.00                -            0.05   no fills rows: verify the morning ran
2026-09-30             0.00           0.00                -            0.03   no fills rows: verify the morning ran
2026-10-01             0.00         517.42                -            0.03
2026-10-02             0.00     411,229.54                -            0.03
2026-10-05             0.00     425,739.98                -            0.03
2026-10-06             0.00     342,598.25                -            0.03
2026-10-08             0.00     494,417.34                -            0.02
2026-10-09             0.00     376,262.54                -            0.03
2026-10-12             0.00     409,357.31                -            0.02
2026-10-13             0.00     437,952.78                -            0.03
2026-10-15             0.00     429,573.30                -            0.03
2026-10-16             0.00     480,740.60                -            0.03
2026-10-19             0.00     394,934.52                -            0.02
2026-10-20             0.00           0.00                -            0.02   no fills rows: verify the morning ran

newest close considered: 2026-10-20

APPLIED: 14 row(s) upserted into efb.reconciliation
```

2026-09-25 and the 09-29 / 09-30 / 10-20 `filled_notional` zeros are left alone: no
fills rows means the script will not claim a day filled nothing.

### Two fixes the apply forced

1. **jsonb columns cannot be written back as objects.** `select` returns
   `full_risk`, `traded_risk`, `exposure_json` and friends as dicts, and
   `store.upsert` binds values straight to the placeholder, so the first `--apply`
   died with `psycopg.ProgrammingError: cannot adapt type 'dict' using placeholder
   '%s'`. It wrote nothing (verified: the table still matched the backup afterwards).
   Rows read from the table and written back are now re-encoded with
   `store.json_text`, which is what the evening's own writer passes. The restore
   scripts use the same encoding.
2. **`Decimal` never equals the float that produced it.** The stored money and
   volatility columns are Postgres `numeric`, so the change test reported all 14 rows
   as "would be updated" on every re-run. It now compares at
   `1e-9 * max(1, |new|)`. Without this the verification step below could never pass.

### Verification

Every `filled_notional` was re-derived independently from `efb.fills`
(`sum(abs(filled_notional))` per close) and every `realized_annual_vol` from
`live.reconcile.realized_annual_vol_for` - the same function `live/reconcile.py::
backfill` calls for a new morning:

| close | legs in `efb.fills` | `sum abs(filled)` = stored |
|---|---|---|
| 2026-10-02 | 207 | 411,229.54 |
| 2026-10-16 | 181 | 480,740.60 |
| 2026-10-19 | 163 | 394,934.52 |

Re-running the dry run after the apply:

```
newest close considered: 2026-10-20

DRY RUN: 0 row(s) would be updated. Nothing was written.
```

and the restore dry run shows both back-filled columns as the only difference from
the backup with `other cols = 0` on all 14 rows - `intended_notional`,
`forecast_annual_vol`, the cost split and the risk blocks are unchanged:

```
close         filled now    filled backup   realized now  realized backup  other cols
2026-09-29          0.00             0.00          4.64%                -           0
2026-10-01        517.42             0.00          2.83%                -           0
2026-10-02    411,229.54             0.00          2.81%                -           0
2026-10-19    394,934.52             0.00          2.46%                -           0
2026-10-20          0.00             0.00          2.40%                -           0
```

(14 rows in total; four shown.)

### Backup and rollback

- `docs/owner_fixes/backups/reconciliation_before.json` - the 14 rows, every column.
- `docs/owner_fixes/backups/reconciliation_context_before.json` - the whole table
  (15 rows) before the write.
- Restore, dry run by default:

```bash
python scripts/restore_reconciliation.py            # shows the difference
python scripts/restore_reconciliation.py --apply    # puts every backup row back
```

Before the apply the restore dry run reported **0 row(s) differ from the backup**;
after it, the 14 rows with `filled_notional` and `realized_annual_vol` as the only
data difference. The table still holds 15 rows on the same 15 dates.
