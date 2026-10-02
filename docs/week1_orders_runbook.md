# Week one, order path: the merge-day runbook

Three changes are on branch `week1-orders`: the fills reconciliation as the morning
half of the one daily cron, the easy-to-borrow gate that skips rather than fails, and
the reason classifier's two thresholds and two new labels. This file is the order to
put them on `main` in, and how to know each step worked.

The order, in one line: **the SQL (already applied), merge, confirm the new schedule,
the first 15:30 UTC run.**

There is one Render service now. `efb-live-daily` runs both jobs: it starts
`scripts/run_cron.py` at `"30 15,22 * * 1-5"` (15:30 and 22:30 UTC, Monday to
Friday), and the router picks the job by the New York hour -- before noon is the
fills reconciliation, from 16:00 is the evening run, and any other hour does nothing
and exits 0. The separate `efb-fills-reconcile` service is gone, and so is the
`efb-live` environment group: with one service there is no group to create and no
copies to retire, and every key both jobs read is declared on the one service. A
comma list in a cron hour field is standard cron syntax, which is what Render's
cron documentation specifies for `schedule` ("defined as a cron expression"), and
Render guarantees at most one run of a given job at a time, delaying the next
scheduled run while one is active.

Nothing here is safe to do in a different order, for one reason: the deployment runs
the new code as soon as `main` moves, so the schema the new writer names has to be in
place **before** the merge. Step 1 is therefore done already.

## 1. SQL, against the live Supabase project (applied 2026-10-02)

Both steps are idempotent, and both are additive: no table is dropped, no row is
rewritten, and nothing is read before it is written. They are recorded here as the
check to run against the live project, not as work still to do.

1. The `efb.fills` additive block. The live table held seven of the fourteen columns
the writer needs (`trade_date`, `ticker`, `order_id`, `intended_notional`,
`filled_notional`, `fill_price`, `status`, zero rows), so the seven it lacked had to
exist before the first run or its INSERT would fail. The statements are the block in
`live/supabase_schema.sql` headed "Week one: `efb.fills` was created before anything
wrote it" -- copy them from the file rather than from here, so there is one copy of
the SQL and not two:

   ```sql
   alter table efb.fills add column if not exists filled_quantity double precision;
   alter table efb.fills add column if not exists cancel_time timestamptz;
   alter table efb.fills add column if not exists submitted_at timestamptz;
   alter table efb.fills add column if not exists updated_at timestamptz;
   alter table efb.fills add column if not exists close_price double precision;
   alter table efb.fills add column if not exists slippage_bps double precision;
   alter table efb.fills add column if not exists position_intent text;
   ```

   `position_intent` is the seventh and the one that is easy to miss: the writer
   names every column it writes, and without it the first morning fails on a column
   the table does not have. The column-fit test reads these statements out of the
   file for `efb.fills` alone (a search over the whole schema passed on a column
   only `efb.orders` had, which is how this one was found).

   (The file also adds `position_intent` to `efb.orders`, which is batch 4's column
   and already exists on the live table: the writer has been sending position
   intents since the broker-review batch.)

   The schema file carries the create block as well, for a fresh database.
   Re-applying the whole file is the other way to do this and is safe: it is
   idempotent, and it ends by disabling row level security on every `efb` table,
   which is the state this project needs.

2. Grant `delete` on `efb.fills` to the writer role. `replace_by_date` erases the
   date it reconciles before inserting it, so without this the first morning fails
   on privileges rather than on data:

   ```sql
   grant delete on efb.fills to efb_writer;
   ```

   `live/supabase_roles.sql` carries this line; re-applying that file is fine, but
   it must be applied after the schema file (it grants on tables that have to
   exist).

   Verify, from `scripts/verify_store_roundtrip.py` or by hand: the column count is
   fourteen, `delete` is granted on `efb.fills`, and row level security is off
   (`select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'efb' and c.relkind = 'r' and c.relrowsecurity` returns 0).

## 2. Merge

```bash
git checkout main
git merge --no-ff week1-orders
git push origin main
```

Then watch the Blueprint sync in the Render dashboard. The evening job's next run is
unaffected by this merge: `scripts/run_live_daily.py` changed only in the
`skipped_borrow` pass-through and the NAV argument to the reason classifier, and the
one service runs it through `scripts/run_cron.py` with no argument the old start
command did not pass.

## 3. Confirm Render shows the new schedule

One visit to the dashboard, four things to see. Until they are all true the merge is
not finished, even though the code is on `main`.

1. **The schedule.** `efb-live-daily`'s Settings page shows Schedule
   `30 15,22 * * 1-5` and Start Command `python scripts/run_cron.py`.
2. **The second service is gone.** There is no `efb-fills-reconcile` in the
   dashboard. A service dropped from the blueprint is **not** deleted in the
   account, so delete it by hand if it is still there: it would otherwise keep
   waking up on its own old schedule and reconciling nothing.
3. **The keys are on the service.** `efb-live-daily`'s Environment page still lists
   the nineteen keys with their values (Render preserves variables a Blueprint
   omits, and a service-level value always beats a linked group's).
4. **The group is unlinked, then deleted.** If `efb-live` still appears under
   Linked Environment Groups, unlink it, and then delete the group from
   Environment Groups. Nothing breaks while it exists -- a service-level value wins
   over a group's -- but it is a second copy of the same nineteen values, which is
exactly the drift the one-service layout is meant to remove.

## 4. The first 15:30 UTC run

The first weekday after the merge, at 15:30 UTC (11:30 EDT / 10:30 EST), the same
service that ran the evening before wakes again and the router sends it to the fills
reconciliation. This is the run that has to be checked carefully, because it is the
one that reads the account.

1. **The morning job ran.** In the Render dashboard, the service's Runs page shows a
   15:30 UTC run that exited 0, and `select * from efb.run_status where job =
   'fills_reconcile'` has a row for the previous close with status `ok`. The row is
   keyed by the close it reconciled, not by the morning it ran.
2. **The fills are there.** `select count(*), min(trade_date), max(trade_date) from
   efb.fills` shows the previous close's legs, and
   `select ticker, filled_quantity, fill_price, status, cancel_time from efb.fills
   where trade_date = '<the close>' and status <> 'FILLED'` is the same list the
   email carried.
3. **The page gained the section.** Read the published document back:
   `cd web && npx wrangler r2 object get "efb-snapshots/latest.json" --file
   /tmp/latest.json --remote`, then check that `actual_holdings` is present, that
   its `fills.trade_date` is the close being reconciled, and that the target
   `book` is byte-identical to the evening's own publication (`generated_at`
   unchanged is the quickest tell).
4. **The message is right.** If a leg did not fill, the email carries
   `Did not fill: <name> <intent> <size> <status> <time>` and a
   `Realized cost: X bps of NAV against Y bps expected (n of m orders filled)`
   line. If nothing did not fill, there is no email at all, which is the designed
   silence.
5. **It did not trade.** `select * from efb.orders where trade_date = '<the
   close>'` is unchanged since the evening, and no new order appears at the broker.
   The morning path has no submit path, and the run's own test drives it against a
   broker whose `submit_order` raises; this is the check that says so in the
   account.
6. **That evening still ran.** The 22:30 UTC run the same day has its own
   `run_status` row keyed `live_daily` reading `ok`, and its email still names
   `store: postgres/efb`. This is the one thing the merge newly puts in reach: both
   jobs are the same service now, so an evening that did not run could be visible
   only as a morning that did.

If the morning run failed on a missing or wrong value, fix that key on the service
and wait for the next weekday run. If it failed on a date -- no session, no orders to
reconcile -- the log says which, and that is the job working rather than a
misconfiguration.

## What to watch after the first week

- **Both slots, both days.** A missing morning is easy to miss, because nothing
  emails when the job does not run. The Runs page and `run_status` are where a
  skipped 15:30 start shows up, and `job = 'fills_reconcile'` is the row to look
  for.
- The reason mix: if `new name` is a large share of a rebalance every evening, the
  previous book and the target differ structurally and the prior book is worth a
  look (on 2026-10-01 it was 35 of 188).
- `n_unfilled` against the evening's declared `expected_cost_bps`: the realized
  cost line is the first measurement of what the after-hours execution actually
  costs, and it is now recorded beside what was expected.
- The slot itself: 15:30 UTC is 10:30 EST, an hour after the open. A morning when
  the exchange opens late (a closure or a delay) would be read before the open;
  `live/fills.py` counts a working order as not filled, so that morning's email
  would name legs that had not had their chance yet. The fix, if it happens, is to
  have the job check the calendar's own open before it reads.
