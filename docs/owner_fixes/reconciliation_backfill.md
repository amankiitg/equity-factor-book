# Owner fix: back-fill `efb.reconciliation`'s two morning-owned columns

**Not applied. Run it yourself; it is a dry run until you pass `--apply`.**

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
