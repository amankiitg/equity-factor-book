-- EFB live series schema. Run once in the Supabase SQL editor, or via
-- scripts/provision_supabase.py. Every table is keyed by date (and
-- ticker where a day has many rows), so the store upserts instead of
-- appending duplicates. The efb_ prefix keeps EFB's tables disjoint from
-- credit-trading-lab's in the shared project.

create table if not exists public.efb_proposals (
  trade_date date primary key,
  signal text not null,
  as_of date not null,
  n_names int not null,
  n_excluded int not null,
  gross double precision not null,
  net double precision not null,
  n_eff double precision not null,
  target_annual_vol double precision not null,
  achieved_annual_vol double precision not null,
  idio_share_after_fmp double precision not null,
  max_abs_exposure_after_fmp double precision not null,
  gross_cap_bound boolean not null,
  nav double precision not null,
  expected_establishment_cost_bps double precision not null,
  cost_breakdown_bps jsonb not null,
  notional double precision not null,
  avg_trade_size double precision not null,
  input_as_of jsonb not null,
  max_input_staleness_days int not null,
  universe_source text not null,
  universe_as_of date not null,
  manifest jsonb not null
);

create table if not exists public.efb_positions (
  trade_date date not null,
  ticker text not null,
  weight double precision not null,
  signed_notional double precision not null,
  side text not null,
  z double precision not null,
  alpha double precision not null,
  rank int not null,
  idio_vol double precision not null,
  previous_weight double precision not null,
  trade double precision not null,
  reason text not null,
  primary key (trade_date, ticker)
);

create table if not exists public.efb_orders (
  trade_date date not null,
  ticker text not null,
  intended_notional double precision not null,
  filled_notional double precision not null,
  status text not null,
  reason text not null,
  primary key (trade_date, ticker)
);

create table if not exists public.efb_fills (
  trade_date date not null,
  ticker text not null,
  order_id text not null,
  intended_notional double precision not null,
  filled_notional double precision not null,
  fill_price double precision not null,
  status text not null,
  primary key (trade_date, ticker, order_id)
);

create table if not exists public.efb_reconciliation (
  trade_date date primary key,
  forecast_annual_vol double precision,
  realized_annual_vol double precision,
  idio_share_after_fmp double precision,
  gross double precision,
  net double precision,
  n_eff double precision,
  intended_notional double precision,
  filled_notional double precision,
  expected_cost_bps double precision,
  dry_run boolean not null,
  realized_pnl double precision
);

create table if not exists public.efb_nav (
  trade_date date primary key,
  nav double precision not null,
  realized_pnl double precision not null,
  gross_pnl double precision,
  cash double precision
);

create table if not exists public.efb_decisions (
  trade_date date primary key,
  decision text not null,
  reason text not null,
  created_at timestamptz not null
);

create table if not exists public.efb_cron_runs (
  run_date date not null,
  job text not null,
  status text not null,
  detail text,
  started_at timestamptz not null,
  finished_at timestamptz,
  primary key (run_date, job)
);
