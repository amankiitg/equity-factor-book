-- The check query for docs/migrations/e12_attribution_bias_n_obs.sql.
--
-- Read-only: one select over the catalog, no DDL and no writes, so it is safe to run
-- before and after the migration. Before it answers false and names the missing
-- column; after it answers true. The columns are listed here rather than read out of
-- the code under test, because a check that reads its own list would pass on an
-- empty one.
--
-- It also pins `bias_statistic` to `double precision`: the migration adds a column
-- and must not re-type the one the running code already reads as a number.

with expected(column_name, data_type) as (
  values
    ('bias_n_obs', 'integer'),
    ('bias_statistic', 'double precision')
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
