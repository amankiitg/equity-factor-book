# The owner's fixes: five notes, nothing applied

Everything here was prepared on 2026-10-20, read-only, except the fill-gap and
HON notes of 2026-10-27 and the HON repair plan of 2026-10-28. **No row was written, no
object was uploaded, no order was sent, and no run was triggered.** Each script is a
dry run until you pass `--apply`.

| file | what it is | action needed |
|---|---|---|
| [`skyd_return.md`](./skyd_return.md) | where the 2026-10-14 SKYD return lives, and why nothing needs fixing | **none** - verify with the two queries after tonight's run |
| [`attribution_recompute.md`](./attribution_recompute.md) | every stored attribution row's `pre_hedge_vol` is overstated (B4 landed after they were written) | run `scripts/recompute_attribution.py`, check the dry run, then `--apply` |
| [`reconciliation_backfill.md`](./reconciliation_backfill.md) | 14 reconciliation rows carry the evening's `filled_notional = 0` / empty `realized_annual_vol` | run `scripts/backfill_reconciliation.py`, then `--apply` (after 2026-10-19's morning) |
| [`key_rotation.md`](./key_rotation.md) | every credential, where it is configured, and the order to rotate it | when you choose to rotate |
| [`attribution_fill_gap.md`](./attribution_fill_gap.md) | every stored `max_fill_gap` is the largest leg of the day, not the largest amount still owed; 14 of 21 rows move | needs an `--only-max-fill-gap` mode in `scripts/recompute_attribution.py`, then the dry run, then `--apply` |
| [`hon_repair_plan.md`](./hon_repair_plan.md) | the repair the owner asked for: where the value lives, which writer would fix each part, and why it was not applied (the live path is already clean, and no writer recomputes a variance range) | add `--variance-from` to `scripts/repair_session.py`, then run the plan |
| [`hon_spinoff_return.md`](./hon_spinoff_return.md) | HON's 2026-06-29 return is stored as +45.51% against a session that paid -6.46%, because the action row's ratio says 47% of the parent was distributed and the vendor's own factor says 4.65% | the guard that nulls the next one is on the held `hon-spinoff-return` branch; the stored cell and the fitted model artifact still carry the bad print |

## The commands, in the order to run them

```bash
# once, in the repo root
set -a; source .env; set +a

# 1. read-only: confirm the attribution dry run matches the table in its note
python scripts/recompute_attribution.py --root <live data tree>

# 2. write the attribution fix
python scripts/recompute_attribution.py --root <live data tree> --apply

# 3. read-only: confirm the reconciliation dry run (after 2026-10-19's morning)
python scripts/backfill_reconciliation.py

# 4. write the reconciliation back-fill
python scripts/backfill_reconciliation.py --apply

# 5. verify both, read-only
psql "$EFB_SUPABASE_DB_URL" -c "SELECT trade_date, pre_hedge_vol, hedged_vol,
  pnl_total - (pnl_factor + pnl_idio + pnl_cost) AS residual
  FROM efb.attribution ORDER BY trade_date;"
psql "$EFB_SUPABASE_DB_URL" -c "SELECT trade_date, filled_notional, realized_annual_vol
  FROM efb.reconciliation ORDER BY trade_date;"
```

`--root` is the data tree the evening reads. On Render it is the run tree; locally it
is the seed-plus-appendix tree (the 2026-10-19 cut tree was used for the dry runs in
these notes).

## What is deliberately not here

- No SQL that deletes or updates anything: the two scripts are the only writers and
  they both default to a dry run.
- No command that sends email or places an order.
- No credential values, in any file, in any diff.
