-- EFB deploy step 2: the two roles, after the schema and the tables exist.
--
-- Run this in the Supabase SQL editor, as the project owner. It creates two
-- roles, gives each the least it needs, and touches nothing outside schema
-- `efb`. Replace both placeholders with long random passwords before running
-- it, and keep the result out of the repository: the Render dashboard holds the
-- connection strings, and they are never committed.
--
-- Apply this AFTER live/supabase_schema.sql. A grant on a schema that does not
-- exist yet fails, which is the order the earlier steps had wrong.
--
-- The store issues no DDL at runtime, so DML is all either role needs: the
-- write role never has to create the schema, a table, or a sequence, and the
-- schema file defines no sequence (every table is keyed, not serial).

create role efb_writer login password 'REPLACE_WITH_A_LONG_RANDOM_PASSWORD';
create role efb_reader login password 'REPLACE_WITH_A_DIFFERENT_LONG_RANDOM_PASSWORD';

-- The cron writes the live series, the appendix and the run status.
grant usage on schema efb to efb_writer;
grant select, insert, update, delete on all tables in schema efb to efb_writer;

-- The dashboard only reads.
grant usage on schema efb to efb_reader;
grant select on all tables in schema efb to efb_reader;

-- Future tables inherit those grants. Run this as the role that creates the
-- tables, which is `postgres` in the SQL editor, because default privileges
-- attach to the creating role and not to the schema.
alter default privileges in schema efb
  grant select, insert, update, delete on tables to efb_writer;
alter default privileges in schema efb
  grant select on tables to efb_reader;

-- Nothing is granted on `public` or on any other schema, and nothing is
-- granted on the database itself, so the credit-trading-lab objects in the
-- shared project are untouched by both roles.

-- Verify the roles and the usernames the pooler expects:
--   select rolname, rolcanlogin from pg_roles where rolname like 'efb_%';
-- A custom role connects through the pooler as `<role>.<project-ref>`, for
-- example `efb_writer.omnsjnosbaiqkrmnknqw`.
