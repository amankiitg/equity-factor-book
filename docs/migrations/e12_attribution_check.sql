-- The check query for `docs/migrations/e12_attribution.sql`.
--
-- Read-only: two selects over the catalog, no DDL and no writes, so it is safe
-- before and after the migration. Before it answers false and names what is missing;
-- after it answers true.
--
-- The expected columns are `efb/attribution.py`'s `TABLE_COLUMNS` plus the one the
-- database owns, `written_at` (`not null default now()`), in the order
-- `live/supabase_schema.sql` declares them. They are listed here rather than read out
-- of the code under test, because a check that reads its own list would pass on an
-- empty list.

with expected(column_name, data_type) as (
  values
    ('trade_date', 'date'),
    ('n_names', 'integer'),
    ('gross', 'double precision'),
    ('net', 'double precision'),
    ('pnl_total', 'double precision'),
    ('pnl_factor', 'double precision'),
    ('pnl_idio', 'double precision'),
    ('pnl_cost', 'double precision'),
    ('identity_residual', 'double precision'),
    ('pnl_factor_json', 'jsonb'),
    ('pnl_timing', 'double precision'),
    ('pnl_timing_json', 'jsonb'),
    ('exposure_json', 'jsonb'),
    ('book_exposure_json', 'jsonb'),
    ('n_computed_specific', 'integer'),
    ('book_beta', 'double precision'),
    ('market_return', 'double precision'),
    ('pnl_beta', 'double precision'),
    ('forecast_vol', 'double precision'),
    ('pre_hedge_vol', 'double precision'),
    ('hedged_vol', 'double precision'),
    ('realized_vol', 'double precision'),
    ('vol_ratio', 'double precision'),
    ('bias_statistic', 'double precision'),
    ('factor_var_share', 'double precision'),
    ('idio_var_share', 'double precision'),
    ('n_missing_specific_var', 'integer'),
    ('expected_cost_bps', 'double precision'),
    ('expected_trading_bps', 'double precision'),
    ('expected_borrow_bps', 'double precision'),
    ('realized_cost_bps', 'double precision'),
    ('n_target', 'integer'),
    ('n_filled', 'integer'),
    ('max_fill_gap', 'double precision'),
    ('n_missing_return', 'integer'),
    ('missing_return_weight', 'double precision'),
    ('written_at', 'timestamp with time zone')
),
present as (
  select column_name, data_type
  from information_schema.columns
  where table_schema = 'efb' and table_name = 'attribution'
),
report as (
  select
    (select count(*) from present) as present_columns,
    coalesce(
      (select array_agg(e.column_name order by e.column_name)
       from expected e
       left join present p using (column_name)
       where p.column_name is null),
      '{}'
    ) as missing_columns,
    coalesce(
      (select array_agg(e.column_name order by e.column_name)
       from expected e
       join present p using (column_name)
       where p.data_type <> e.data_type),
      '{}'
    ) as mistyped_columns,
    exists (
      select 1 from information_schema.tables
      where table_schema = 'efb' and table_name = 'attribution'
    ) as table_exists,
    -- The one confusion that would store an unusable row rather than a wrong number:
    -- jsonb that arrived as text.
    (select count(*) from present where data_type = 'text') as text_columns
)
select
  table_exists
  and cardinality(missing_columns) = 0
  and cardinality(mistyped_columns) = 0
  and text_columns = 0
  and present_columns = 37
  as ready,

--
-- Everything below is the evidence, so a false says which part of it is false and
-- which columns to look at. Delete it and the first column alone is the answer.
--
  table_exists as table_exists,
  present_columns,
  cardinality(missing_columns) as n_missing,
  missing_columns,
  cardinality(mistyped_columns) as n_mistyped,
  mistyped_columns,
  text_columns
from report;
