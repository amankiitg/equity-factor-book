-- Change efb.attribution.bias_statistic from a number to text, so a session with
-- fewer than thirty observations can carry the sentence instead of failing the run.
--
-- live/supabase_schema.sql declares the same column as text, so a database provisioned
-- from that file after this migration is identical to one migrated by hand. The change
-- is a widening, not a rewrite: a double precision value casts to text losslessly, and
-- an existing row keeps its stored number as its text form.
--
-- Why. bias_statistic is the bias engine's dispersion of the book's z-scores, and the
-- engine needs thirty finite observations. Before 2026-11-06 the evening stored null
-- until the book had thirty, but the 2026-11-06 evening reached thirty raw sessions
-- while three carried no forecast, so the guard passed and the engine raised, failing
-- the whole attribution step. The column now carries "not enough data yet (N of 30)"
-- below thirty, so a short history can never raise the step.
--
-- Row level security needs nothing here: the column's type changes, the table's
-- policies are unchanged.

begin;

alter table efb.attribution
  alter column bias_statistic type text;

commit;

-- The grants come from live/supabase_roles.sql, which grants on every table in the
-- schema: efb_reader already reads this table and efb_writer already writes it, and a
-- re-typed column is covered by the table's grant.
--
-- Verify with docs/migrations/e12_attribution_bias_text_check.sql, which is read-only
-- and answers false before this file and true after it.
