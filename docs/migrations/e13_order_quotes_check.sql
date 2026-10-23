-- The check query for `docs/migrations/e13_order_quotes.sql`.
--
-- Read-only: one select over the catalog, no DDL and no writes, so it is safe to run
-- before and after the migration. Before it answers false and names what is missing;
-- after it answers true. The four are listed here rather than read out of the code
-- under test, because a check that reads its own list would pass on an empty one.

with expected(column_name, data_type) as (
  values
    ('submitted_bid', 'double precision'),
    ('submitted_ask', 'double precision'),
    ('submitted_mid', 'double precision'),
    ('quoted_at', 'timestamp with time zone')
),
present as (
  select column_name, data_type
  from information_schema.columns
  where table_schema = 'efb' and table_name = 'orders'
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
