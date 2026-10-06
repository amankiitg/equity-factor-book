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

/** One name the account holds, in dollars and as a share of its own equity. */
export interface ActualHoldingName {
  ticker: string;
  side: "long" | "short" | null;
  notional: number | null;
  weight: number | null;
}

/** What the evening's orders did, as the broker answered a read by id. */
export interface FillsSummary {
  trade_date: string | null;
  n_orders: number | null;
  n_filled: number | null;
  n_unfilled: number | null;
  not_sent: number | null;
  realized_cost_bps: number | null;
  expected_cost_bps: number | null;
  unfilled: string[];
  // The legs the evening could not send at all, with the reason derived by the
  // writer because the broker never saw the order: a ticker the asset feed
  // carries under no symbol says `SYMBOL_NOT_FOUND`. They are not broker misses,
  // so they are not in `n_unfilled`; they are the rest of what did not happen.
  not_sent_lines?: string[];
  unread: Array<Record<string, unknown>>;
}

/** One name that left the account with nothing of the loop's to explain it. */
export interface ExitName {
  ticker: string;
  // The shares the previous read held, and the dollars that went with them at
  // that read's own market value.
  quantity: number | null;
  notional: number | null;
}

/**
 * The names the account held when it was last read and does not hold now, with no
 * closing leg filled and no activity of the broker's naming the ticker.
 *
 * Absent (not empty) when the question was not asked, which is what lets the page
 * say "not read" rather than "none": the two are different statements about the
 * same book. `feed` says whether the broker's activity feed answered, because a
 * departure the feed could not be asked about is a weaker finding, not an absence
 * of one.
 */
export interface ExitsBlock {
  previous_read: string | null;
  feed: "read" | "not read" | "no previous read" | null;
  window: string | null;
  names: ExitName[];
}

/**
 * The account's own book beside the target book it was sized from.
 *
 * `read_by` says which run read it: `evening` is the read the book was sized from,
 * taken before the orders went out, and `morning` is the reconciliation, when the
 * fills exist. The evening's block carries no `close` and no `fills`, for that
 * reason, and the page states it rather than reading an absent fills block as a
 * day on which nothing filled.
 */
export interface ActualHoldings {
  as_of: string | null;
  close: string | null;
  read_by: "evening" | "morning" | null;
  n_names: number;
  gross_notional: number | null;
  net_notional: number | null;
  names: ActualHoldingName[];
  fills: FillsSummary | null;
  exits?: ExitsBlock | null;
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
  // The account's own book, published by the evening run from its own account
  // read and rewritten by the morning reconciliation. Absent (not null) when
  // nobody read the account, which is why the section says so in one line rather
  // than drawing an empty table.
  actual_holdings?: ActualHoldings | null;
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
