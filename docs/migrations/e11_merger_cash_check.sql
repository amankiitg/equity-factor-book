-- The check query for docs/migrations/e11_merger_cash.sql.
--
-- Read-only: one select over the catalog, no DDL and no writes, so it is safe to run
-- before and after the migration. Before it answers false and names what is missing;
-- after it answers true. The column is listed here rather than read out of the code
-- under test, because a check that reads its own list would pass on an empty one.

with expected(column_name, data_type) as (
  values
    ('cash_per_share', 'double precision')
),
present as (
  select column_name, data_type
  from information_schema.columns
  where table_schema = 'efb' and table_name = 'e11_corporate_actions'
)
select
  (select count(*) from expected) as expected_columns,
  (select count(*) from expected e join present p using (column_name)) as present_columns,
  (select count(*) from expected e join present p using (column_name))
    = (select count(*) from expected) as ready,
  coalesce(
    (select string_agg(e.column_name, ', ' order by e.column_name)
     from expected e left join present p using (column_name)
     where p.column_name is null),
    ''
  ) as missing;
