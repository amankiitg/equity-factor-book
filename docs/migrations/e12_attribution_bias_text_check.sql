-- The check query for docs/migrations/e12_attribution_bias_text.sql.
--
-- Read-only: one select over the catalog, no DDL and no writes, so it is safe to run
-- before and after the migration. Before it answers false and names the old type; after
-- it answers true. The column and its expected type are listed here rather than read
-- out of the code under test, because a check that reads its own list would pass on an
-- empty one.

with expected(column_name, data_type) as (
  values
    ('bias_statistic', 'text')
),
present as (
  select column_name, data_type
  from information_schema.columns
  where table_schema = 'efb' and table_name = 'attribution'
)
select
  (select count(*) from expected) as expected_columns,
  (select count(*) from expected e join present p using (column_name)) as present_columns,
  (select count(*) from expected e join present p using (column_name, data_type))
    = (select count(*) from expected) as ready,
  coalesce(
    (select string_agg(e.column_name || ' (' || e.data_type || ')', ', ' order by e.column_name)
     from expected e
     left join present p
       on p.column_name = e.column_name and p.data_type = e.data_type
     where p.column_name is null),
    ''
  ) as missing;
