-- Add `efb.attribution.bias_n_obs`: the finite observation count behind the
-- bias statistic, so a session with fewer than thirty observations can say how close
-- it is instead of just carrying a null.
--
-- Additive and idempotent: this reaches a database that already holds
-- `efb.attribution` from an earlier version of `live/supabase_schema.sql` (where
-- `create table if not exists` says nothing about a table that already exists).
-- `bias_statistic` keeps its type - it is still `double precision`, and stays null
-- below thirty finite observations - so the code already running against this table
-- keeps reading a number where it expects one. The new column is null until the code
-- that writes it is running, and a column the running code has never seen cannot
-- change a row it does not write.
--
-- Row level security needs nothing here: the column is added to a table whose
-- policies are unchanged.

begin;

alter table efb.attribution
  add column if not exists bias_n_obs int;

commit;

-- The grants come from live/supabase_roles.sql, which grants on every table in the
-- schema: efb_reader already reads this table and efb_writer already writes it, and an
-- added column is covered by the table's grant.
--
-- Verify with docs/migrations/e12_attribution_bias_n_obs_check.sql, which is read-only
-- and answers false before this file and true after it.
