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
  // Both blocks are absent until the cron writes them, and the page hides the
  // section that needs one rather than drawing an empty one: a snapshot carrying
  // neither is the state every run is in today (see docs/snapshot.schema.json for
  // the shape each section expects, and the page's own notes for why).
  risk?: RiskConcentration | null;
  movers?: SessionMovers | null;
}

export interface RiskConcentration {
  /** The share of predicted specific variance one name is capped at, as a fraction. */
  variance_share_cap?: number | null;
  /** Per-name share of the book's predicted specific variance, largest first. */
  concentration?: Array<{ ticker: string; share: number }> | null;
}

export interface SessionMovers {
  /** The session the contributions belong to. */
  session?: string | null;
  by_name?: Array<{ ticker: string; contribution: number }> | null;
  by_sector?: Array<{ sector?: string | null; contribution: number }> | null;
}
