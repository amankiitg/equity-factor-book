// The snapshot document, as `docs/snapshot.schema.json` declares it.
//
// Hand-written rather than generated, and pinned by `fixtures.test.ts`, which
// validates every committed fixture against the keys the page reads. A generated
// file would need a build step and a codegen dependency for sixteen fields; the
// test is what keeps the two in step either way.

export interface BookName {
  ticker: string;
  weight: number | null;
  side: "long" | "short" | "";
  reason: string | null;
  z: number | null;
  alpha: number | null;
}

export interface RunStatus {
  status: string | null;
  detail: string;
  failing_inputs: Array<{ input?: string; sessions_behind?: number | null }>;
  worst_input: string | null;
  worst_sessions_behind: number | null;
  catch_up: boolean;
  catch_up_sessions: string[];
  splits: string[];
  flags: Array<Record<string, unknown>>;
  notify_status: string | null;
  snapshot: string | null;
  establishment: boolean;
  cost_label: string | null;
}

export interface PositionsCheck {
  matches: boolean | null;
  n_broker: number | null;
  n_store: number | null;
  source: string | null;
  note: string | null;
  missing_at_broker: string[];
  missing_in_store: string[];
  max_abs_drift: number | null;
}

export interface AttributionDay {
  trade_date: string | null;
  pnl_total: number | null;
  pnl_factor: number | null;
  pnl_idio: number | null;
  pnl_cost: number | null;
  pnl_timing: number | null;
  book_beta: number | null;
  market_return: number | null;
  pnl_beta: number | null;
  realized_vol: number | null;
  forecast_vol: number | null;
}

export interface Attribution {
  n_days: number;
  first_day: string | null;
  last_day: string | null;
  cumulative: {
    pnl_total: number | null;
    pnl_factor: number | null;
    pnl_idio: number | null;
    pnl_cost: number | null;
    max_identity_residual: number | null;
    n_computed_specific: number;
  };
  by_factor: Record<string, number | null>;
  daily: AttributionDay[];
  cost: {
    expected_bps: number | null;
    realized_bps: number | null;
    n_realized: number;
  };
  note: string;
}

export interface Snapshot {
  schema_version: number;
  generated_at: string;
  target_close: string | null;
  book_as_of: string | null;
  expected_next_by: string | null;
  dry_run: boolean;
  store: string | null;
  run_status: RunStatus;
  construction: string;
  positions: PositionsCheck;
  breadth: {
    n_eff_kept: number | null;
    n_eff_full_book: number | null;
    kept_label: string;
    full_book_label: string;
  };
  book: {
    n_names: number;
    reason: string | null;
    n_kept: number | null;
    n_long: number | null;
    n_short: number | null;
    gross: number | null;
    gross_notional: number | null;
    full_book_gross: number | null;
    net: number | null;
    max_kept_weight: number | null;
    achieved_annual_vol: number | null;
    expected_cost_bps: number | null;
    names: BookName[];
  };
  exposures_before_hedge: Record<string, number | null>;
  exposures_after_hedge: Record<string, number | null>;
  hedge: {
    idio_share_after_fmp: number | null;
    max_abs_exposure_after_fmp: number | null;
    post_hedge_idio_share: number | null;
    post_hedge_max_abs_exposure: number | null;
  };
  exposures: Record<string, number | null>;
  reconciliation: Record<string, number | null>;
  attribution: Attribution;
}
