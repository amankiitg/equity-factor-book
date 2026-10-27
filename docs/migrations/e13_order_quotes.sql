-- The order-time quote, as a migration the owner applies by hand.
--
-- Applied to the live database by 2026-10-27: the check file answers 4|4|t. It is
-- not run by the build, so a database provisioned from `live/supabase_schema.sql`
-- already has the columns and a database restored from an older backup has them
-- again once this is re-run. This file is the statement set for the owner to read and
-- to apply through the Supabase SQL editor or `scripts/provision_supabase.py`. It is
-- additive and idempotent: four nullable columns, no rewrite, no backfill, and every
-- existing row keeps its values.
--
-- Why. `realized_cost_bps` measures a fill against the close the book was *sized*
-- from, and the loop sizes after one close and submits about two hours later, so the
-- number carries the market's move between the two. Splitting at the open (measured
-- on 2026-10-22) leaves 16.6 bp per dollar traded of "execution", which is not an
-- execution cost either: the open is not the price the order saw. These columns record
-- what it did see - the bid, the ask and their mid, and when they were read - so the
-- measured cost can be split into the overnight move, the drift from the open to
-- submission, and the execution from submission to fill.
--
-- `live/supabase_schema.sql` declares the same four columns, so a database provisioned
-- from that file after this migration is identical to one migrated by hand.
--
-- Row level security needs nothing here: the schema file's catalog block covers every
-- table in `efb`, and a hand-applied migration changes no table's policy.

begin;

alter table efb.orders
  add column if not exists submitted_bid double precision;
alter table efb.orders
  add column if not exists submitted_ask double precision;
alter table efb.orders
  add column if not exists submitted_mid double precision;
alter table efb.orders
  add column if not exists quoted_at timestamptz;

commit;

-- The grants come from `live/supabase_roles.sql`, which grants on every table in the
-- schema: `efb_reader` already reads this table and `efb_writer` already writes it, and
-- an added column is covered by the table's grant.
--
-- Verify with `docs/migrations/e13_order_quotes_check.sql`, which is read-only and
-- answers false before this file and true after it.
