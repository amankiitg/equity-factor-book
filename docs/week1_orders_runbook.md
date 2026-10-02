# Week one, order path: the merge-day runbook

Three changes are on branch `week1-orders`: the fills reconciliation as its own
15:00 UTC cron, the easy-to-borrow gate that skips rather than fails, and the
reason classifier's two thresholds and two new labels. This file is the order to
put them on `main` in, and how to know each step worked.

Nothing here is safe to do in a different order. The two SQL steps come before the
merge, because the deployment runs the new code as soon as `main` moves. The
environment group is created before the merge, because the blueprint references it
by name and a sync that names a group the workspace does not have fails. And the
evening service's own copies of the shared keys are deleted **after** the first
fills run, not before: while those copies exist they win over the group, so the
fills run is the only thing that proves the group carries the right values.

The order, in one line: **SQL, create the group, merge, the first 15:00 UTC run as
proof, delete the evening service's copies, the evening run.**

## 1. SQL, against the live Supabase project

Both steps are idempotent, and both are additive: no table is dropped, no row is
rewritten, and nothing is read before it is written.

1. Apply the `efb.fills` additive block. The live table holds seven of the fourteen
   columns the writer needs today (`trade_date`, `ticker`, `order_id`,
   `intended_notional`, `filled_notional`, `fill_price`, `status`, zero rows), so
   the seven it lacks must exist before the first run or its INSERT fails. The
   statements are the block in `live/supabase_schema.sql` headed "Week one:
   `efb.fills` was created before anything wrote it" -- copy them from the file
   rather than from here, so there is one copy of the SQL and not two:

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

## 2. Render: the shared environment group

The group exists once and both crons take it. The blueprint cannot carry the
group's secrets (`sync: false` is ignored inside an environment group, so a group
declared in `render.yaml` would come out empty and every key would be missing), so
the group is created by hand and referenced by name from both services.

**The order below is the correction that matters.** A service-level value always
beats a linked group's value, and Render keeps environment variables that the
blueprint omits. So while the evening service still holds its own copies of these
keys, nothing about that service proves the group holds the right values: the
copies are what it reads. The proof is the **first fills run**, which has no
service-level copies at all and therefore reads the group and only the group.

1. In the Render Dashboard, click **Environment Groups** in the left pane, then
   **+ New Environment Group**. Name it exactly `efb-live`.
2. Add these thirteen keys, with the values the evening service already uses
   (Environment page of `efb-live-daily`; Render shows each value to the owner):

   | key | what it is |
   | --- | --- |
   | `EFB_SUPABASE_DB_URL` | the write role's connection string |
   | `EFB_DB_SCHEMA` | `efb` |
   | `EFB_ALPACA_PAPER_API_KEY` | the paper key |
   | `EFB_ALPACA_PAPER_SECRET_KEY` | the paper secret |
   | `EFB_ALPACA_ACCOUNT_ID` | `PA3A50WIU0O0`, checked on every run |
   | `EFB_RESEND_API_KEY` | the sending key |
   | `EFB_NOTIFY_EMAIL_FROM` | the sender |
   | `EFB_NOTIFY_EMAIL_TO` | the owner |
   | `EFB_SNAPSHOT` | `on` |
   | `EFB_R2_ACCOUNT_ID` | the Cloudflare account |
   | `EFB_R2_BUCKET` | `efb-snapshots` |
   | `EFB_R2_ACCESS_KEY_ID` | the bucket-scoped token |
   | `EFB_R2_SECRET_ACCESS_KEY` | the same token's secret |

   Do not add `EFB_DRY_RUN`, `EFB_INIT_STORE`, `EFB_SEED_R2_*` or `EFB_STORE`:
   those stay on the evening service, so the fills job cannot inherit the switch
   that trades, the seed request or the history bucket.
3. Click **Create Environment Group**. Do not link it by hand: the blueprint's
   `fromGroup: efb-live` on each service is what links it, at the sync after the
   merge. Linking it by hand before that would prove nothing, for the reason
   above, and would redeploy the evening service for no reason.

## 3. Merge

```bash
git checkout main
git merge --no-ff week1-orders
git push origin main
```

Then watch the Blueprint sync in the Render dashboard. The evening job's next run
is unaffected by this merge: `scripts/run_live_daily.py` changed only in the
`skipped_borrow` pass-through and the NAV argument to the reason classifier.

## 4. The first 15:00 UTC run: the proof that the group carries the values

The first weekday after the merge, at 15:00 UTC (11:00 EDT / 10:00 EST). This run
is also the only thing that proves the group holds the right values: it is a new
service with no environment variables of its own, so every key it reads comes from
`efb-live`. If it succeeds, the group is right; if it fails on a credential, that
credential in the group is wrong.

1. **The job ran.** In the Render dashboard, `efb-fills-reconcile` shows a
   successful run, and `select * from efb.run_status where job = 'fills_reconcile'`
   has a row for the previous close with status `ok`. The row is keyed by the close
   it reconciled, not by the morning it ran.
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
   close>'` is unchanged since the evening, and no new order appears at the broker
   for either account. The job has no submit path, and this is the check that says
   so in the account rather than in the code.

If it failed on a missing or wrong value: fix that key in the group and wait for the
next weekday run. Nothing else is affected, because the evening service is still
reading its own copies of the same keys, which win.

## 5. After that run succeeds: retire the evening service's copies

Do this only once step 4 has passed, because it is the point at which the group
becomes the single source for the evening job too.

1. On `efb-live-daily`, click **Environment** and delete the thirteen keys listed
   in step 2 above from its own **Environment Variables** list. (They are still
   supplied by the linked group; deleting the copies is what stops them overriding
   it.) Keep `EFB_INIT_STORE`, `EFB_DRY_RUN` and the four `EFB_SEED_R2_*` entries.
2. Confirm the next evening run: its `run_status` row keyed `live_daily` reads
   `ok`, the email's first line still names `store: postgres/efb`, and its reason
   column now mixes labels (`new name`, `no trade`, `the hedge moved`,
   `alpha moved`, and `risk moved` where the specific volatility moved by more than
   1%) instead of one label on every row.
3. If that evening run fails on a missing variable, the group is short a key: add
   it and re-run. That failure is the check working, not a surprise.

## What to watch after the first week

- The reason mix: if `new name` is a large share of a rebalance every evening, the
  previous book and the target differ structurally and the prior book is worth a
  look (on 2026-10-01 it was 35 of 188).
- `n_unfilled` against the evening's declared `expected_cost_bps`: the realized
  cost line is the first measurement of what the after-hours execution actually
  costs, and it is now recorded beside what was expected.
- The slot itself: 15:00 UTC is 10:00 EST, half an hour after the open. A morning
  when the exchange opens late (a closure or a delay) would be read before the
  open; `live/fills.py` counts a working order as not filled, so that morning's
  email would name legs that had not had their chance yet. The fix, if it happens,
  is to have the job check the calendar's own open before it reads.
