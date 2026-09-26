-- EFB live series schema, direct Postgres. Run once in the Supabase SQL
-- editor, or via scripts/provision_supabase.py. Every table is keyed by date
-- (and ticker where a day has many rows), so the store upserts instead of
-- appending duplicates. Everything lives in schema `efb`; nothing targets
-- `public` or an unqualified name, so EFB's tables are disjoint from
-- credit-trading-lab's in the shared project.

create schema if not exists efb;

create table if not exists efb.proposals (
  trade_date date primary key,
  signal text not null,
  as_of date not null,
  n_names int not null,
  n_excluded int not null,
  gross double precision not null,
  net double precision not null,
  n_eff_kept double precision not null,
  n_eff_full_book double precision not null,
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

create table if not exists efb.positions (
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

create table if not exists efb.orders (
  trade_date date not null,
  ticker text not null,
  intended_notional double precision not null,
  filled_notional double precision not null,
  status text not null,
  reason text not null,
  primary key (trade_date, ticker)
);

create table if not exists efb.fills (
  trade_date date not null,
  ticker text not null,
  order_id text not null,
  intended_notional double precision not null,
  filled_notional double precision not null,
  fill_price double precision not null,
  status text not null,
  primary key (trade_date, ticker, order_id)
);

create table if not exists efb.reconciliation (
  trade_date date primary key,
  forecast_annual_vol double precision,
  realized_annual_vol double precision,
  idio_share_after_fmp double precision,
  -- The hedge's worst residual factor exposure, beside the idio share: the
  -- proposal and the snapshot both carry it, and the reconciled row is the
  -- day's record of the same book.
  max_abs_exposure_after_fmp double precision,
  gross double precision,
  net double precision,
  n_eff_kept double precision,
  intended_notional double precision,
  filled_notional double precision,
  expected_cost_bps double precision,
  dry_run boolean not null,
  realized_pnl double precision
);

create table if not exists efb.nav (
  trade_date date primary key,
  nav double precision not null,
  realized_pnl double precision not null,
  gross_pnl double precision,
  cash double precision
);

create table if not exists efb.decisions (
  trade_date date primary key,
  decision text not null,
  reason text not null,
  created_at timestamptz not null
);

create table if not exists efb.cron_runs (
  run_date date not null,
  job text not null,
  status text not null,
  detail text,
  started_at timestamptz not null,
  finished_at timestamptz,
  primary key (run_date, job)
);

-- E11-F15: the model-input appendix. The git artifacts are the seed through
-- 2026-09-03; these tables hold the sessions after that cutoff, one row per
-- key, so a re-run of a session upserts instead of duplicating. A run hydrates
-- the artifacts as seed plus appendix, extends by the new session and writes
-- only that session back. Nothing here is research history: the pre-2026-09-04
-- rows stay in git, byte-identical.

create table if not exists efb.e11_prices (
  trade_date date not null,
  ticker text not null,
  open double precision, high double precision, low double precision,
  close double precision, adj_close double precision, volume double precision,
  dividend double precision, split_factor double precision,
  primary key (trade_date, ticker)
);

create table if not exists efb.e11_descriptors (
  trade_date date not null,
  ticker text not null,
  descriptor text not null,
  value_raw double precision, value_winsor double precision,
  value_z double precision, value_z_orth double precision,
  n_obs double precision, look_ahead boolean,
  primary key (trade_date, ticker, descriptor)
);

create table if not exists efb.e11_factor_returns (
  trade_date date not null,
  factor text not null,
  f double precision, f_pre_identification double precision,
  estimation text, is_sector boolean, is_reference_sector boolean,
  n_names double precision,
  primary key (trade_date, factor)
);

create table if not exists efb.e11_specific_returns (
  trade_date date not null,
  ticker text not null,
  specific_return double precision,
  primary key (trade_date, ticker)
);

create table if not exists efb.e11_specific_var (
  trade_date date not null,
  ticker text not null,
  specific_var_raw double precision, specific_var double precision,
  bucket text, bucket_mean double precision, n_obs double precision,
  primary key (trade_date, ticker)
);

create table if not exists efb.e11_factor_cov (
  trade_date date not null,
  factor text not null,
  with_factor text not null,
  covariance double precision,
  primary key (trade_date, factor, with_factor)
);

create table if not exists efb.e11_shares (
  trade_date date not null,
  ticker text not null,
  shares double precision, source text, fetched_at text, status text,
  primary key (trade_date, ticker)
);

create table if not exists efb.e11_sectors (
  trade_date date not null,
  ticker text not null,
  gics_sector text, gics_sub_industry text, source text,
  primary key (trade_date, ticker)
);

create table if not exists efb.e11_universe (
  trade_date date not null,
  ticker text not null,
  name text, identifier text, sedol text, weight double precision,
  sector text, shares_held double precision, local_currency text,
  primary key (trade_date, ticker)
);

-- Part 3: one row per run, keyed by the target close it was priced for, not
-- by the day the job fired. The dashboard reads the latest row and judges it
-- against the session that should have closed, so a run that stopped on
-- staleness, errored, or never happened shows as a failure instead of leaving
-- an old book looking current. Every input's content date, and the fetch date
-- for the two gated on it, is in `inputs`; the failing inputs and their
-- distance in sessions are in `failures`.

create table if not exists efb.run_status (
  run_date date not null,
  job text not null,
  target_close date not null,
  status text not null,
  checked_at text,
  max_input_staleness_days int,
  worst_input text,
  worst_sessions_behind int,
  n_inputs int,
  inputs jsonb,
  failures jsonb,
  detail text,
  notify_status text,
  notify_failed boolean default false,
  n_orders int,
  gross_notional double precision,
  dry_run boolean,
  -- Whether this run seeded the store. True exactly once, on the explicit first
  -- run; the marker in efb.store_seed is what "seeded" means.
  init boolean default false,
  catch_up boolean default false,
  catch_up_sessions jsonb,
  splits jsonb,
  flags jsonb,
  -- What the Cloudflare page has of this run: "snapshot: on (latest.json,
  -- snapshots/<close>.json)" or "snapshot: off (dry run)".
  snapshot text,
  -- When the run began, UTC. A gate close is a run that started on its target
  -- close's own evening, so the instant has to be recorded rather than assumed.
  started_at timestamptz,
  -- "cross-check capped: N unchecked (...)" when the corporate-actions
  -- cross-check hit its request cap. Null when it did not.
  cross_checks_capped text,
  primary key (target_close, job)
);

-- The explicit first-run marker. Its presence is what "seeded" means: a store
-- that holds rows is not evidence of a seed, because scripts/verify_store_roundtrip.py
-- records a run_status row of its own (job = store_roundtrip) on a store that was
-- never seeded. One row, written by the run that seeds the appendix. It is never
-- written automatically again: a marker with an empty appendix is an error, and a
-- flag left set on a seeded store is an error, so nothing re-seeds by accident.
create table if not exists efb.store_seed (
  marker text primary key,
  seeded_from date not null,
  data_hash text,
  written_at timestamptz not null
);

-- Item 4b: the corporate-actions rule. One row per split applied to a session,
-- written by the run that appended it. The rule computes that session's return
-- from raw closes and the factor (`close_t * factor / close_{t-1} - 1`) instead
-- of from the vendor's back-adjusted history, so no stored price row is ever
-- restated, and the cross-check ratio is kept beside the factor so a later
-- reader can see the two agreed.
create table if not exists efb.e11_corporate_actions (
  trade_date date not null,
  ticker text not null,
  effective_date date not null,
  factor double precision not null,
  source text,
  cross_check_ratio double precision,
  primary key (trade_date, ticker)
);

-- Additive changes, for a database that was already provisioned from an
-- earlier version of this file. `create table if not exists` says nothing
-- about a table that already exists, so a column added to a table above reaches
-- a fresh database only. These statements are idempotent and safe to re-run,
-- and they are what the shared project - and a developer's local `efb` - needs
-- after pulling this file. Fresh databases get the same column from the
-- `create table` above.

-- E11: the reconciled row carries the hedge's worst residual exposure beside
-- the idio share. The first version of this table omitted it while
-- `live/reconcile.py` wrote it every evening, which failed the first real run
-- against a database at `store_reconciliation` with `column
-- "max_abs_exposure_after_fmp" of relation "reconciliation" does not exist`.
alter table efb.reconciliation
  add column if not exists max_abs_exposure_after_fmp double precision;
