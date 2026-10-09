-- E12's migration, exactly as it would be applied to the live project.
--
-- NOT RUN BY THE BUILD. This file is the statement set for the owner to read and to
-- apply by hand, through the Supabase SQL editor or `scripts/provision_supabase.py`.
--
-- Two groups of statements, in this order, all additive and all idempotent:
--   1. the create, which reaches a fresh database only;
--   2. the additive columns, which reach a database already provisioned from an
--      earlier version of `live/supabase_schema.sql` -- where
--      `create table if not exists` says nothing about a table that exists.
-- They are cut from `live/supabase_schema.sql` itself, so applying this file by hand
-- leaves the live database identical to one provisioned from that file, and
-- `docs/migrations/e12_attribution_check.sql` proves it afterwards.
--
-- Row level security is left off by the schema file's own catalog block, which runs
-- last and covers every table in `efb`; on a hand-applied migration the statement
-- below is the same one that block would issue for this one table.

begin;

create table if not exists efb.attribution (
  trade_date date primary key,
  n_names int,
  gross double precision,
  net double precision,
  pnl_total double precision,
  pnl_factor double precision,
  pnl_idio double precision,
  pnl_cost double precision,
  identity_residual double precision,
  pnl_factor_json jsonb,
  pnl_timing double precision,
  pnl_timing_json jsonb,
  exposure_json jsonb,
  book_exposure_json jsonb,
  n_computed_specific int,
  book_beta double precision,
  market_return double precision,
  pnl_beta double precision,
  forecast_vol double precision,
  pre_hedge_vol double precision,
  hedged_vol double precision,
  realized_vol double precision,
  vol_ratio double precision,
  bias_statistic double precision,
  factor_var_share double precision,
  idio_var_share double precision,
  n_missing_specific_var int,
  expected_cost_bps double precision,
  expected_trading_bps double precision,
  expected_borrow_bps double precision,
  realized_cost_bps double precision,
  n_target int,
  n_filled int,
  max_fill_gap double precision,
  n_missing_return int,
  missing_return_weight double precision,
  written_at timestamptz not null default now()
);

alter table efb.attribution
  add column if not exists pnl_timing double precision;
alter table efb.attribution
  add column if not exists pnl_timing_json jsonb;
alter table efb.attribution
  add column if not exists exposure_json jsonb;
alter table efb.attribution
  add column if not exists book_exposure_json jsonb;
alter table efb.attribution
  add column if not exists factor_var_share double precision;
alter table efb.attribution
  add column if not exists idio_var_share double precision;
alter table efb.attribution
  add column if not exists n_missing_specific_var int;
alter table efb.attribution
  add column if not exists pre_hedge_vol double precision;
alter table efb.attribution
  add column if not exists hedged_vol double precision;
alter table efb.attribution
  add column if not exists expected_trading_bps double precision;
alter table efb.attribution
  add column if not exists expected_borrow_bps double precision;

alter table efb.attribution disable row level security;

commit;

-- The grants come from `live/supabase_roles.sql`, which grants on every table in the
-- schema and needs nothing here: `efb_reader` already reads this schema and
-- `efb_writer` already writes it.
