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
  /** The tickers the $250 floor's count is taken from, so the class is decidable. */
  under_minimum_tickers?: string[] | null;
  reversals_pending: string[];
  /**
   * The *previous* close's deferral list, read from the document that carried it.
   * Null is "not known" - the evening could not read the document that is up - and
   * an empty list is "the previous close deferred nothing"; the page must not read
   * the first as the second. Absent on documents written before the key existed.
   */
  previous_reversals_pending?: string[] | null;
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
  /**
   * The rebalance calendar (`EFB_CADENCE`). Absent on every document written
   * before the flag existed, and on a run that did not ask: an absent block is the
   * daily behaviour and must read as one.
   */
  cadence?: CadenceBlock | null;
}

/** One close on the rebalance calendar, as the evening reports it. */
export interface CadenceBlock {
  /** Sessions between rebalances. 1 is the daily loop. */
  k: number;
  anchor: string;
  /** `rebalance` or `hold`. */
  day: "rebalance" | "hold";
  /** Whether the calendar named today, rather than a missed one promoting it. */
  scheduled: boolean;
  /** Whether today is a rebalance because an earlier scheduled one did not run. */
  pending: boolean;
  /** The scheduled rebalances the completion record does not have. */
  missed: string[];
  /** The next rebalance date. */
  next_rebalance: string | null;
  /** The one sentence the strip shows: "hold day, next rebalance <date>". */
  label: string;
  /**
   * The hold day's hedge refresh (`EFB_DRIFT_GUARD`), when the flag was on: what it
   * measured, what it did, and the legs it moved. Null is a hold day the guard
   * looked at and left alone; absent is a run that never asked for one.
   */
  drift_guard?: DriftGuard | null;
}

/** One hold day's hedge refresh. */
export interface DriftGuard {
  fired: boolean;
  /** The threshold in force, as a fraction of NAV. */
  threshold: number;
  /** Worst absolute factor exposure before and after, as a fraction of NAV. */
  exposure_before: number;
  exposure_after: number;
  /** The correction's gross, as a fraction of NAV. */
  turnover: number;
  legs: DriftGuardLeg[];
}

export interface DriftGuardLeg {
  ticker: string;
  weight_before: number;
  weight_after: number;
  /** The signed change in weight points of NAV. */
  delta_notional_pct: number;
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

/**
 * A dated statement about the series, written by the snapshot builder.
 *
 * Drawn as a marker at its date with its text beside the chart, because a series that
 * changed formula or opened on a book that was not yet the book reads as a change in
 * risk unless the date it changed is on the picture.
 */
export interface AttributionNote {
  date: string | null;
  text: string;
}

export interface Attribution {
  live: AttributionPeriod | null;
  backtest: AttributionPeriod | null;
  /** Dated notes about the series; absent on a document written before they existed. */
  notes?: AttributionNote[];
  note: string;
}

/** One name's share of the book's predicted specific variance, largest first. */
export interface VarianceShare {
  ticker: string;
  variance_share: number | null;
}

/**
 * The traded book's own risk figures, as the evening computed them.
 *
 * Published by the reconciliation because they describe the book that trades: gross,
 * net, the effective breadth, the forecast, and the shares of predicted specific
 * variance that say which names carry the risk the hedge cannot remove. The page
 * shows them rather than recomputing a second set, so the two cannot disagree about
 * the same book. It is not the 499-name book beside it (`full_risk`), which the
 * floor has not finished with.
 */
export interface TradedRisk {
  forecast_annual_vol?: number | null;
  gross?: number | null;
  net?: number | null;
  n_eff?: number | null;
  max_weight?: number | null;
  idio_share?: number | null;
  max_abs_exposure?: number | null;
  top_variance_shares?: VarianceShare[] | null;
}

/** The day's reconciliation row: what the orders intended, and what they did. */
export interface Reconciliation {
  expected_cost_bps?: number | null;
  intended_notional?: number | null;
  /**
   * The legs the broker was actually sent, and the ones it was not, both in dollars.
   * `intended_notional` less these two is the figure the page's turnover card used to
   * stand on alone, and on 2026-10-09 it read $388,402.25 where $379,430.49 was sent.
   * Absent on every document written before the evening published them.
   */
  sent_notional?: number | null;
  unsent_notional?: number | null;
  filled_notional?: number | null;
  realized_annual_vol?: number | null;
  unexplained_adjustment?: number | null;
  traded_risk?: TradedRisk | null;
  full_risk?: TradedRisk | null;
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
    /**
     * The names the risk model had no specific variance for, which never reached the
     * sizing, each with the reason it left. Absent on every document written before
     * the evening published them.
     */
    n_dropped_no_risk?: number | null;
    dropped_no_risk?: { ticker: string; reason: string }[] | null;
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
    full_book_net: number | null;
    full_book_achieved_annual_vol: number | null;
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
  reconciliation: Reconciliation;
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
  /**
   * The anchored panels: every number measured from the last rebalance rather than
   * from last night, which is what a monthly cadence needs a page to do. **Absent**
   * when the run could not build it, and absent on every document written before it
   * existed, so the page renders exactly as it did then.
   */
  monthly?: MonthlyBlock | null;
}

/** One flip: a name whose side before the rebalance differs from its target side. */
export interface FlipRow {
  ticker: string;
  from_side: string;
  to_side: string;
  close_dollars: number | null;
  /** The close the leg was priced from, and the day it actually filled. */
  close_filled: string | null;
  close_filled_at?: string | null;
  open_dollars: number | null;
  open_filled: string | null;
  open_filled_at?: string | null;
  now_dollars: number;
  on_target_side: boolean;
  complete: boolean;
}

/** The pages measured from the anchor, built by `live/monthly_view.py`. */
export interface MonthlyBlock {
  anchor?: { close: string | null; day: "rebalance" | "cadence" | "daily"; account_read: string | null };
  cadence_strip?: {
    k: number | null;
    offset: number | null;
    sessions_since: number | null;
    last_rebalance: string | null;
    next_rebalance: string | null;
    guard: {
      worst_abs_exposure: number | null;
      exposure_after?: number | null;
      threshold: number | null;
      fired: boolean;
      ran: boolean;
    };
  };
  rebalance_card?: {
    close: string | null;
    orders?: number;
    /** Legs meant to be sent, and how many of those filled. */
    sent_legs?: number;
    filled_legs?: number;
    /** Legs under the $250 minimum: built, never sent, and not owed. */
    under_minimum_legs?: number;
    under_minimum_usd?: number;
    skipped_other_legs?: number;
    notional?: number;
    pct_nav?: number | null;
    expected_cost_bps?: number | null;
    expected_cost_usd?: number | null;
    realized_cost_bps?: number | null;
    legs_total?: number;
    legs_complete?: number;
    legs_incomplete?: number;
    dollars_owed?: number;
  };
  bridge_anchor?: {
    before_dollars: number;
    after_dollars: number;
    opened: number;
    exited: number;
    resized: number;
    flipped: number;
    under_minimum: number;
    opened_usd?: number;
    exited_usd?: number;
    resized_usd?: number;
    flipped_usd?: number;
    complete_flips: number;
    flip_rows: FlipRow[];
    identities: BridgeIdentity[];
    holds: boolean;
  };
  drift?: {
    half_turnover_pct: number;
    half_turnover_usd: number | null;
    traded_usd: number | null;
    estimated_cost_usd: number | null;
    largest: Array<{
      ticker: string;
      weight_now: number;
      weight_target: number;
      usd: number | null;
    }>;
  };
  since_anchor?: {
    trades_by_reason: Array<{ reason: string; legs: number; usd: number }>;
  };
  /**
   * The account against the anchor rebalance's target, by sector, in dollars.
   *
   * Absent from every document written before this existed, and absent when the
   * writer could not read the sector map: the page's own sector panel then renders
   * as it always has, which is the right failure for a panel.
   */
  sectors?: {
    anchor: string | null;
    nav: number;
    rows: MonthlySectorRow[];
    /** `both_sides_usd / 2`: the drift card's one-side turnover, sector by sector. */
    one_side_usd: number;
    both_sides_usd: number;
    unmapped_usd: number;
    n_names: number;
    n_mapped: number;
  };
  tonight?: { forced_legs: number; forced_usd: number };
  rebalance_dates?: string[];
}

/** One sector's distance from the rebalance target, net and name by name. */
export interface MonthlySectorRow {
  code: number | null;
  label: string;
  /** The target's and the account's signed net, and the difference, in dollars. */
  target_usd: number;
  account_usd: number;
  delta_usd: number;
  /** Sum of |name gap| in this sector: what closing it would trade, both sides. */
  traded_usd: number;
  n_target: number;
  n_account: number;
  drivers: Array<{
    ticker: string;
    usd: number;
    weight_now: number;
    weight_target: number;
  }>;
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
