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
  // The dollars the evening traded in this name, as the absolute notional of the
  // leg it built for it, or 0 when it built none. `weight` is a holding and this
  // is a movement: the trades-by-reason table needs both to say where the
  // turnover came from. Absent on a frame that carried no orders, which is what a
  // stopped run's book is, and read as "not recorded" rather than as zero.
  traded_notional?: number | null;
}

/** One identity the bridge claims, with both sides and whether it holds. */
export interface BridgeIdentity {
  name: string;
  left: number | null;
  right: number | null;
  holds: boolean;
}

/** A name in the book that left the account with no order behind it. */
export interface BridgeRemoval {
  ticker: string;
  quantity: number | null;
  notional: number | null;
}

/**
 * The arithmetic between the three sets the page draws.
 *
 * `held_before` is the account as the evening read it, `book` is what it published,
 * `orders_sent` is what it sent, and `held_after` is the account as the morning read
 * it: the numbers the page shows as three separate panels, connected by `in_both`,
 * `opened`, `exited` and the two halves of the continuing names. The evening
 * publishes the first half and the morning completes it, so `filled`,
 * `did_not_fill` and `held_after` are null until the 15:30 UTC reconciliation has
 * run. `identities` carries the block's own checks, each with both sides, and
 * `holds` is their verdict: a false here is a bridge that does not add up, which
 * the page shows in amber rather than smoothing over.
 */
export interface BridgeBlock {
  close: string | null;
  seen_by: "evening" | "morning" | null;
  book: number | null;
  held_before: number | null;
  in_both: number | null;
  opened: number | null;
  exited: number | null;
  changed: number | null;
  under_minimum: number | null;
  orders_sent: number | null;
  filled: number | null;
  did_not_fill: number | null;
  held_after: number | null;
  under_minimum_usd: number | null;
  reversals_pending: string[];
  removed_without_order: BridgeRemoval[];
  unexplained: string[];
  identities: BridgeIdentity[];
  holds: boolean;
}

/** The day's expected cost, split into the parts the proposal computed. */
export interface CostSplit {
  spread?: number | null;
  impact?: number | null;
  commission?: number | null;
  borrow?: number | null;
  /** spread + impact + commission: the half a fill price can be measured against. */
  trading?: number | null;
  total?: number | null;
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
  // The same figure over every day the loop has reconciled, and how many days are
  // behind it. One day is mostly the overnight move between the close the leg was
  // sized from and the open it filled at, so the average is the number that can be
  // read as execution quality; the count is shown with it, because an average of
  // two days is not an average of twenty. Null before any day has been priced.
  realized_cost_avg_bps: number | null;
  realized_cost_days: number | null;
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

/**
 * The attribution the evening step writes: what the book earned, split into the
 * four terms that add to its total. Fractions of the book's gross, which is 1.0 of
 * NAV, so 1e-4 is one basis point.
 *
 * `live` is the book that traded and `backtest` is the seed's own research panel,
 * which nobody traded; the second is null on a host that has no artifact. The two
 * are different objects and are never summed: the page keeps them behind a switch.
 */
export interface AttributionDay {
  trade_date: string | null;
  pnl_total: number | null;
  pnl_factor: number | null;
  pnl_idio: number | null;
  pnl_cost: number | null;
  pnl_unexplained: number | null;
  pnl_timing: number | null;
  book_beta: number | null;
  market_return: number | null;
  pnl_beta: number | null;
  realized_vol: number | null;
  forecast_vol: number | null;
  /** Predicted annual vol of the sized book, and of the book the hedge left. */
  pre_hedge_vol: number | null;
  hedged_vol: number | null;
  factor_var_share: number | null;
  idio_var_share: number | null;
}

export interface AttributionMonth {
  month: string | null;
  pnl_total: number | null;
  pnl_factor: number | null;
  pnl_idio: number | null;
  pnl_cost: number | null;
  n_sessions: number | null;
}

export interface AttributionRiskPath {
  trade_date: string | null;
  factor_share: number | null;
  idio_share: number | null;
  /** Annualized predicted volatility of the sized book the hedge acted on. */
  pre_hedge_vol: number | null;
  /** The same forecast at the book that was held: the hedge's own effect. */
  hedged_vol: number | null;
}

export interface AttributionRisk {
  as_of: string | null;
  factor_share: number | null;
  idio_share: number | null;
  pre_hedge_vol: number | null;
  hedged_vol: number | null;
  path: AttributionRiskPath[];
}

export interface AttributionPeriod {
  label: string;
  first_day: string | null;
  last_day: string | null;
  /** Every session the period holds, whether or not it is in `daily`. */
  n_days: number;
  /** How many of them are in `daily`. */
  n_days_carried: number;
  cumulative: {
    pnl_total: number | null;
    pnl_factor: number | null;
    pnl_idio: number | null;
    pnl_cost: number | null;
    pnl_unexplained: number | null;
    max_identity_residual: number | null;
    n_computed_specific: number;
  };
  by_factor: Record<string, number | null>;
  daily: AttributionDay[];
  /** Backtest only: the whole run, one row a month, oldest first. */
  monthly: AttributionMonth[];
  cost: {
    expected_bps: number | null;
    /**
     * The expected cost's trading half (spread + impact + commission). This is the
     * only half a realized fill cost can be measured against: a fill price pays
     * spread, impact and commission, and it pays no borrow.
     */
    expected_trading_bps: number | null;
    /** The short leg's holding cost over the horizon, shown beside the trading half. */
    expected_borrow_bps: number | null;
    realized_bps: number | null;
    n_realized: number;
  };
  risk: AttributionRisk | null;
  note: string;
}

export interface Attribution {
  live: AttributionPeriod | null;
  backtest: AttributionPeriod | null;
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
    // The same cost split the way the proposal computes it, in bps of NAV: the
    // trading half (spread + impact + commission, summed as `trading`) and borrow,
    // the cost of holding the short leg over the horizon. The page compares the
    // fills against the trading half only - a fill price cannot be measured against
    // a holding cost - and the split is what makes that comparison readable.
    // Absent on a manifest that predates the breakdown.
    expected_cost_split?: CostSplit | null;
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
  // The arithmetic between the three sets above, written by the evening and
  // completed by the morning. Absent (not null) when no run built one - a stopped
  // evening - because a bridge of zeroes would read as an evening that moved
  // nothing.
  bridge?: BridgeBlock | null;
  // Both blocks are absent until the cron writes them, and the page hides the
  // section that needs one rather than drawing an empty one: a snapshot carrying
  // neither is the state every run is in today (see docs/snapshot.schema.json for
  // the shape each section expects, and the page's own notes for why).
  risk?: RiskConcentration | null;
  movers?: SessionMovers | null;
  // What the book earned, split into the four terms that add to its total, written
  // by the evening's attribution step. Absent (not null) on a document written
  // before that step existed, which is every document already in the bucket: the
  // section hides itself for one rather than reading a block that is not there. A
  // present block always carries a `live` period, which may itself be empty; the
  // `backtest` period is null on a host that has no research artifact.
  attribution?: Attribution | null;
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
