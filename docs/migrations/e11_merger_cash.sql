-- The cash leg of a cash-and-stock merger, as a migration the owner applies by hand.
--
-- live/supabase_schema.sql declares the same column, so a database provisioned from
-- that file after this migration is identical to one migrated by hand. It is additive
-- and idempotent: one nullable column, no rewrite, no backfill, and every existing row
-- keeps its values.
--
-- Why. A spin-off carries a share ratio and no cash; a cash-and-stock merger carries
-- both. The KVUE -> KMB merger (2026-11-02) pays 0.14625 KMB shares plus $3.50 cash per
-- KVUE share, so the appendix row that records it needs a place for the $3.50. The
-- reader defaults a null to $0.00, so older split and spin-off rows are unaffected.
--
-- Row level security needs nothing here: the schema file's catalog block covers every
-- table in efb, and a hand-applied migration changes no table's policy.

begin;

alter table efb.e11_corporate_actions
  add column if not exists cash_per_share double precision;

commit;

-- The grants come from live/supabase_roles.sql, which grants on every table in the
-- schema: efb_reader already reads this table and efb_writer already writes it, and an
-- added column is covered by the table's grant.
--
-- Verify with docs/migrations/e11_merger_cash_check.sql, which is read-only and
-- answers false before this file and true after it.
