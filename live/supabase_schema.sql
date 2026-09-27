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
  -- The book that trades: `gross`, `net` and `achieved_annual_vol` are the kept
  -- set after the hedge. The 499-name book the model sized before the floor
  -- dropped any is beside them under `full_book_*` names. The three extra
  -- columns are nullable because rows written before the split hold only the
  -- unqualified figures, which is what those columns meant then.
  gross double precision not null,
  net double precision not null,
  full_book_gross double precision,
  full_book_net double precision,
  n_eff_kept double precision not null,
  n_eff_full_book double precision not null,
  target_annual_vol double precision not null,
  achieved_annual_vol double precision not null,
  full_book_achieved_annual_vol double precision,
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
  -- `intention` when no order left the process (every dry-run evening) and
  -- `holding` when they did. A dry-run book is what the loop meant to hold, and
  -- E12's attribution must never count one as a holding.
  kind text,
  primary key (trade_date, ticker)
);

-- What the broker itself reports holding, per name, read in the same request
-- that sized the evening's book. `positions` above is the loop's intention and
-- this is the account's own answer: a run that reads a book back has to be able
-- to tell the two apart, and E12's attribution must never count an intention as
-- a holding. `weight` is the name's share of the account's own equity.
create table if not exists efb.broker_positions (
  trade_date date not null,
  ticker text not null,
  side text not null,
  quantity double precision,
  market_value double precision not null,
  weight double precision,
  primary key (trade_date, ticker)
);

create table if not exists efb.orders (
  trade_date date not null,
  ticker text not null,
  intended_notional double precision not null,
  filled_notional double precision not null,
  status text not null,
  reason text not null,
  -- The stable code for a leg that never became a submitted order: the guard's
  -- status, the broker's classification, or SKIPPED_AFTER_HALT. Alpaca does not
  -- persist a submit-time rejection, so this column is the durable record that
  -- the leg was intended.
  reason_code text,
  -- The id the leg was sent with: deterministic from the close, the ticker and
  -- the side, so a rerun of the same evening is refused by the broker rather
  -- than doubling the book.
  client_order_id text,
  -- The broker's own open-or-close decision on the leg, so a reconciler can tell
  -- a close from a short without re-deriving it from the sign of a notional.
  position_intent text,
  -- The broker's own id for the order, empty for a leg that never became one (a
  -- guard rejection, a skipped minimum) and empty on a dry run. A fill arrives as
  -- an activity against an order id, so this is the key the evening that
  -- reconciles fills has to match on.
  broker_order_id text,
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
  -- The reconciler's own columns, added after the table was created. `filled_qty`
  -- and `filled_avg_price` arrive from the broker, and the share count is what
  -- makes a partial fill visible at all: a filled notional alone cannot say
  -- whether the whole leg traded. `cancel_time` is the instant the broker
  -- cancelled the order, which is what the message quotes beside the status.
  filled_quantity double precision,
  cancel_time timestamptz,
  submitted_at timestamptz,
  updated_at timestamptz,
  -- The close the leg was sized from, and what the fill cost against it. Stored
  -- per leg rather than only summed, so the day's realized cost can be checked
  -- against the legs that produced it instead of taken on trust.
  close_price double precision,
  slippage_bps double precision,
  -- The broker's own open-or-close decision on the leg, as `efb.orders` carries
  -- it: the message's did-not-fill line quotes it, and a reconciler that had to
  -- re-derive it from the sign of a notional would get a reversal wrong.
  position_intent text,
  primary key (trade_date, ticker, order_id)
);

create table if not exists efb.reconciliation (
  trade_date date primary key,
  -- The unqualified risk fields on this row describe the book that trades: the
  -- forecast is the traded book's, and so are gross and net. The 499-name book
  -- is beside them under `full_book_*` names, because a row whose "gross" was
  -- the 499-name book read as the gross of the book the owner holds.
  forecast_annual_vol double precision,
  full_book_forecast_annual_vol double precision,
  realized_annual_vol double precision,
  idio_share_after_fmp double precision,
  -- The hedge's worst residual factor exposure, beside the idio share: the
  -- proposal and the snapshot both carry it, and the reconciled row is the
  -- day's record of the same book.
  max_abs_exposure_after_fmp double precision,
  gross double precision,
  net double precision,
  full_book_gross double precision,
  full_book_net double precision,
  n_eff_kept double precision,
  intended_notional double precision,
  filled_notional double precision,
  expected_cost_bps double precision,
  -- The establishment cost, split the way efb/costs.py computes it. A total
  -- alone is a number nobody can check; these four make it an arithmetic
  -- claim. Borrow is the short leg's annual rate over one 21-session
  -- horizon, not a year.
  expected_spread_bps double precision,
  expected_impact_bps double precision,
  expected_commission_bps double precision,
  expected_borrow_bps double precision,
  dry_run boolean not null,
  realized_pnl double precision,
  -- The part of the day's P&L that no order of the loop's explains: a position
  -- that left the account with nothing behind it. Its own labelled figure rather
  -- than a correction applied to the P&L - a quietly adjusted number is one
  -- nobody can check - and negative for a removal.
  unexplained_adjustment double precision,
  -- The traded book's risk figures and the full book's, each under its own
  -- names, as jsonb. The traded book is what the run holds; the full book is
  -- every name the model sized before the floor dropped any.
  traded_risk jsonb,
  full_risk jsonb
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
  -- Whether this run created the book or rebalanced it. An establishment run
  -- started from an empty account, was allowed to trade up to the full book, and
  -- carries "establishment" as its cost label; from the second trading day the
  -- run is a rebalance and the absolute traded-notional brake applies.
  establishment boolean default false,
  cost_label text,
  -- The broker's position book against the store's, read before the orders were
  -- built: the counts, the names only one side holds, and the largest drift. A
  -- difference here makes every traded leg wrong in the same direction.
  positions_check jsonb,
  -- The traded book's risk figures and the full book's, each under its own
  -- names, as jsonb, copied from the manifest the run was priced from.
  traded_risk jsonb,
  full_risk jsonb,
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
--
-- The same table carries spin-offs, which are the other action that moves one
-- session's return. `explained_by` says which of the two a row is ('split' or
-- 'spinoff'), and for a spin-off `factor` is the child's shares per parent share
-- (`new_rate / source_rate`) with the child named in `new_ticker`. The parent is
-- the row's ticker either way, because the parent is the name whose return the
-- rule replaced. A row written before this column existed has it null, and it is
-- a split: spin-offs are what the column was added for.
create table if not exists efb.e11_corporate_actions (
  trade_date date not null,
  ticker text not null,
  effective_date date not null,
  factor double precision not null,
  source text,
  cross_check_ratio double precision,
  explained_by text,
  new_ticker text,
  source_rate double precision,
  new_rate double precision,
  primary key (trade_date, ticker)
);

-- E12: the holdings-based attribution, one row per attributed session. The three
-- components sum to the total to machine precision by construction, and the
-- residual is stored rather than assumed zero so a later reader can see the
-- identity was checked and not restated. Row level security is disabled
-- deliberately: the loop writes this table as `efb_writer` through
-- `scripts/run_live_daily.py`, which is a direct Postgres connection and not an
-- anonymous API client, so a policy would refuse the writer rather than protect
-- anything. The statement is idempotent, and the grants come from
-- `live/supabase_roles.sql`, which grants on all tables in the schema.
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
  realized_vol double precision,
  vol_ratio double precision,
  bias_statistic double precision,
  expected_cost_bps double precision,
  realized_cost_bps double precision,
  n_target int,
  n_filled int,
  max_fill_gap double precision,
  n_missing_return int,
  missing_return_weight double precision,
  written_at timestamptz not null default now()
);

alter table efb.attribution disable row level security;

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

-- Pre-flip: the establishment cost, split into its four parts. They sum to
-- `expected_cost_bps` by construction (live/evening_job.py adds exactly these
-- four), and stating them turns the total into something the owner can check.
alter table efb.reconciliation
  add column if not exists expected_spread_bps double precision;
alter table efb.reconciliation
  add column if not exists expected_impact_bps double precision;
alter table efb.reconciliation
  add column if not exists expected_commission_bps double precision;
alter table efb.reconciliation
  add column if not exists expected_borrow_bps double precision;

-- Part B: the PSKY removal. A position that left the paper account between two
-- reads with no order, no fill, no cash and no share credit is an adjustment to
-- the day's P&L rather than a result of the strategy, and it is written as its
-- own labelled figure so the P&L itself is never silently edited. See the entry
-- of the same date in docs/hygiene_ledger.md.
alter table efb.reconciliation
  add column if not exists unexplained_adjustment double precision;

-- Pre-flip: the establishment day's flag and its cost label.
alter table efb.run_status
  add column if not exists establishment boolean default false;
alter table efb.run_status
  add column if not exists cost_label text;

-- Pre-flip: the broker's book against the store's, read before sizing.
alter table efb.run_status
  add column if not exists positions_check jsonb;

-- Pre-flip: the refusal code for a leg that was never submitted.
alter table efb.orders
  add column if not exists reason_code text;

-- Spin-offs: `e11_corporate_actions` was created for splits, so a provisioned
-- database needs the four columns the spin-off rows are written into. The writer
-- names every column it inserts, so without these the first morning after a
-- spin-off fails on a column the table does not have.
alter table efb.e11_corporate_actions
  add column if not exists explained_by text;
alter table efb.e11_corporate_actions
  add column if not exists new_ticker text;
alter table efb.e11_corporate_actions
  add column if not exists source_rate double precision;
alter table efb.e11_corporate_actions
  add column if not exists new_rate double precision;
-- Pre-flip: the rerun-proof ticket for each leg.
alter table efb.orders
  add column if not exists client_order_id text;

-- Pre-flip: a position row is an intention until orders have actually gone out.
alter table efb.positions
  add column if not exists kind text;

-- Pre-launch: the traded book's risk figures and the full book's, each under its
-- own names, on the day's reconciliation row and on the run_status row.
alter table efb.reconciliation
  add column if not exists traded_risk jsonb;
alter table efb.reconciliation
  add column if not exists full_risk jsonb;
alter table efb.run_status
  add column if not exists traded_risk jsonb;
alter table efb.run_status
  add column if not exists full_risk jsonb;

-- Pre-launch batch 3: the unqualified risk fields on the day's row and on the
-- proposal row describe the book that trades, and the 499-name book moves to
-- `full_book_*` names of its own.
alter table efb.reconciliation
  add column if not exists full_book_forecast_annual_vol double precision;
alter table efb.reconciliation
  add column if not exists full_book_gross double precision;
alter table efb.reconciliation
  add column if not exists full_book_net double precision;
alter table efb.proposals
  add column if not exists full_book_gross double precision;
alter table efb.proposals
  add column if not exists full_book_net double precision;
alter table efb.proposals
  add column if not exists full_book_achieved_annual_vol double precision;

-- Pre-launch batch 4: the order row carries the intent the leg was sent with and
-- the broker's own id for it, so the evening that reconciles fills can match a
-- fill to the order it belongs to instead of to a derived ticket.
alter table efb.orders
  add column if not exists position_intent text;
alter table efb.orders
  add column if not exists broker_order_id text;

-- Week one: `efb.fills` was created before anything wrote it, and it carried the
-- notional, the average price and the status only. The reconciler records what
-- the broker says about the leg as well, and the two prices the realized cost is
-- the difference of. A create block reaches a fresh database only, so a table
-- that already exists needs the columns added by name as well.
alter table efb.fills
  add column if not exists filled_quantity double precision;
alter table efb.fills
  add column if not exists cancel_time timestamptz;
alter table efb.fills
  add column if not exists submitted_at timestamptz;
alter table efb.fills
  add column if not exists updated_at timestamptz;
alter table efb.fills
  add column if not exists close_price double precision;
alter table efb.fills
  add column if not exists slippage_bps double precision;
-- The intent the broker was given, which the message's did-not-fill line quotes
-- (`DG sell_to_open 41 canceled 12:15 UTC`). The create block above carries it,
-- and a table that already existed needs it by name: without this the writer's
-- INSERT names a column the live table does not have and the first morning fails.
alter table efb.fills
  add column if not exists position_intent text;

-- E12: the attribution table as first provisioned, before the hedge-timing line
-- and the two design vintages existed. A database created from an earlier
-- version of this file holds `efb.attribution` without them, and `live/store.py`
-- writes every column it is handed, so a missing one is a failed evening rather
-- than a nullable field.
alter table efb.attribution
  add column if not exists pnl_timing double precision;
alter table efb.attribution
  add column if not exists pnl_timing_json jsonb;
alter table efb.attribution
  add column if not exists exposure_json jsonb;
alter table efb.attribution
  add column if not exists book_exposure_json jsonb;
-- Row level security, off, last. Supabase enables row level security on the
-- tables its SQL editor is asked to create, and an RLS table with no policy
-- refuses everything: re-applying this file left the writer role unable to write
-- and the appendix unreadable from the dashboard. RLS is not this project's
-- access control. The credentials are server-side only (the web service holds
-- none), the reader and writer roles carry no bypassrls, and every table lives in
-- schema `efb`, away from `public`. The table names are read from the catalog
-- rather than listed, so a table created anywhere above cannot be missed, and
-- this block is the last statement in the file, so applying it always leaves RLS
-- off, including on a database where an earlier apply left it on.
do $$
declare
  target text;
begin
  for target in
    select c.relname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'efb' and c.relkind = 'r' and c.relrowsecurity
    order by c.relname
  loop
    execute format('alter table efb.%I disable row level security', target);
    raise notice 'efb.%: row level security disabled', target;
  end loop;
end
$$;
