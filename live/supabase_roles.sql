-- EFB deploy step 2: the one role, after the schema and the tables exist.
--
-- Run this in the Supabase SQL editor, as the project owner. It creates two
-- role, gives it the least it needs, and touches nothing outside schema `efb`.
-- Replace the placeholder with a long random password before running it, and
-- keep the result out of the repository: the Render dashboard holds the
-- connection string, and it is never committed.
--
-- There is one role because Render runs one service. The read role went with the
-- web service (the live book monitor is a Cloudflare page reading an R2
-- snapshot), which is one fewer credential to hold. `efb_archiver`, which needs
-- `delete` on the `e11_*` tables and nothing else, arrives with retention in item
-- 6.
--
-- Apply this AFTER live/supabase_schema.sql. A grant on a schema that does not
-- exist yet fails, which is the order the earlier steps had wrong.
--
-- The store issues no DDL at runtime, so DML is all either role needs: the
-- write role never has to create the schema, a table, or a sequence, and the
-- schema file defines no sequence (every table is keyed, not serial).

create role efb_writer login password 'REPLACE_WITH_A_LONG_RANDOM_PASSWORD';

-- The cron writes the live series, the appendix and the run status.
--
-- `live/store.py` issues four verbs: INSERT and UPDATE (the ON CONFLICT upsert),
-- SELECT (every read), and DELETE (`replace_by_date`, which erases a date before
-- re-inserting it so a rerun cannot leave the previous run's rows behind). The
-- broad grant below covers three of them on every table, and DELETE is granted
-- narrowly on the two tables `replace_by_date` is called on, because that is the
-- only place a row is ever removed. The grant is traced to its caller and the
-- runtime cannot discover a missing privilege: the DELETE only runs on a rerun.
grant usage on schema efb to efb_writer;
grant select, insert, update on all tables in schema efb to efb_writer;
grant delete on efb.positions, efb.orders to efb_writer;

-- Future tables inherit those grants. Run this as the role that creates the
-- tables, which is `postgres` in the SQL editor, because default privileges
-- attach to the creating role and not to the schema.
alter default privileges in schema efb
  grant select, insert, update on tables to efb_writer;

-- Nothing is granted on `public` or on any other schema, and nothing is
-- granted on the database itself, so the credit-trading-lab objects in the
-- shared project are untouched by the role.

-- Verify the roles and the usernames the pooler expects:
--   select rolname, rolcanlogin from pg_roles where rolname like 'efb_%';
-- A custom role connects through the pooler as `<role>.<project-ref>`, for
-- example `efb_writer.omnsjnosbaiqkrmnknqw`.
