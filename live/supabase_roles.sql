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
-- 6; until then nothing deletes a row.
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
-- No `delete`: live/store.py issues exactly two statements, an INSERT ... ON
-- CONFLICT upsert and a SELECT, so no code path in this repository deletes a row
-- from `efb`. A grant nothing uses is a grant that cannot be traced to a caller.
grant usage on schema efb to efb_writer;
grant select, insert, update on all tables in schema efb to efb_writer;

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
