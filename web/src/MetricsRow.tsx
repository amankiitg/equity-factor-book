// The dense row of numbers the book is read by, one card per figure.
//
// Every value is either stated by the snapshot or derived in `book.ts` from what it
// states, and a value the snapshot does not carry prints "n/a": a zero would claim a
// measurement nobody made, which is the one thing this page cannot afford. The numbers
// are monospaced and tabular so a column of them lines up and a digit that moves is
// visible rather than merely different.
//
// Every card title carries its own (i). The label on a card is a word, not a
// sentence: "turnover" says nothing to a reader who has not met it, and the
// explanation used to be a paragraph over the whole row that no reader takes in
// twice. One tap opens the meaning, why the number moves, and one real example.
//
// Two cards changed with the reader they are written for. Turnover reads as the
// night's own sentence, "Tonight: 109 orders sent, $68,859", and names the legs the
// broker refused with the reason it gave; the "$X sent of NAV, and $Y built, of which
// $Z was never sent" arithmetic is in the construction disclosure on the Operations
// tab, which is where a reader checking the loop goes. And the expected cost states
// the period it covers: the trade half is paid once on tonight's legs and the borrow
// half is charged over the sessions the book is held, so the two are added into a
// total over that hold and the card says which hold it is.

import { Details } from "./Details";
import { HowToRead } from "./Panel";
import { EXPECTED_EXPENSE } from "./labels";
import { count, dollars, oneDecimal, percent } from "./format";
import type { BookFacts } from "./book";
import type { Snapshot } from "./types";

/** How many dropped-for-no-risk names the coverage line lists before counting the rest. */
const DROPPED_LINES = 6;

/** How many blocked legs the turnover card names before it just counts them. */
const BLOCKED_NAMES = 3;

function Card({
  hook,
  label,
  value,
  detail,
  info,
  children,
}: {
  /** A stable name for the tests and for anything reading the page mechanically. */
  hook: string;
  label: string;
  value?: React.ReactNode;
  detail?: React.ReactNode;
  /** The (i) beside the title: what the number is, why it moves, one example. */
  info: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div data-card={hook} className="rounded border border-slate-200 bg-white px-2 py-1">
      <div className="text-[0.65rem] uppercase tracking-wide text-slate-500">
        {label}
        <HowToRead>{info}</HowToRead>
      </div>
      {value === undefined ? null : (
        <div className="font-mono text-base leading-tight tabular-nums">{value}</div>
      )}
      {detail === undefined ? null : (
        <div className="text-xs text-slate-600">{detail}</div>
      )}
      {children}
    </div>
  );
}

/**
 * A cost in basis points of NAV, or "n/a" when the run did not price one.
 *
 * The unit is on the face of every figure rather than in the caption: a cost is quoted
 * against the book it was charged to, and a page that prints "14.20" beside a dollar
 * column and lets the reader guess has two readings of one number.
 */
export function bps(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : `${value.toFixed(2)} bp of NAV`;
}

/** One leg the evening could not send, read off the line the run wrote. */
export interface BlockedLeg {
  ticker: string;
  notional: number | null;
  reason: string;
}

/**
 * The legs the broker refused, with their dollars and the reason it gave.
 *
 * `not_sent_lines` are the legs the evening built and could not send at all, and the
 * writer fixes their shape at the source: ticker, intent, dollars, "never sent", and
 * the reason in brackets. A line that does not parse is skipped rather than guessed
 * at. Only the legs no broker could trade under any spelling reach this list, which is
 * why the card can say they no longer trade rather than reporting a decision the run
 * made on purpose.
 */
export function blockedLegs(snapshot: Snapshot): BlockedLeg[] {
  const legs = sentBlockedLegs(snapshot);
  if (legs.length) return legs;
  // On a hold night nothing is sent, so the document carries no never-sent line at
  // all: the leg it wanted and could not place is the retired name's own gap, which
  // the anchored block states name by name. Same claim, same words, no order needed.
  return (snapshot.monthly?.holdings?.rows ?? [])
    .filter((row) => row.retired && Math.abs(row.gap_usd ?? 0) >= 1)
    .map((row) => ({
      ticker: row.ticker,
      notional: Math.abs(row.gap_usd ?? 0),
      reason: "SYMBOL_NOT_FOUND",
    }));
}

/** The legs the evening built and the broker refused, from its own lines. */
function sentBlockedLegs(snapshot: Snapshot): BlockedLeg[] {
  const legs: BlockedLeg[] = [];
  for (const line of snapshot.actual_holdings?.fills?.not_sent_lines ?? []) {
    const match = /^(\S+)\s+(.*?)\s+never sent\s*\((.*)\)$/.exec(line.trim());
    if (!match) continue;
    const amount = /\$([\d,]+(?:\.\d+)?)/.exec(match[2]);
    legs.push({
      ticker: match[1],
      notional: amount ? Number(amount[1].replace(/,/g, "")) : null,
      reason: match[3],
    });
  }
  return legs;
}

/** The reason a broker refused a leg, in words a reader who is not a broker knows. */
function blockedReason(code: string): string {
  const clean = code.trim();
  if (clean.toUpperCase() === "SYMBOL_NOT_FOUND") return "no longer trades";
  return clean.toLowerCase().replace(/_/g, " ");
}

/**
 * The blocked legs as one clause: named while there are three or fewer, counted
 * once there are more, because four tickers and three dollar figures in a small card
 * is a list nobody finishes.
 */
export function blockedText(legs: BlockedLeg[]): string {
  if (legs.length > BLOCKED_NAMES) {
    const total = legs.reduce((sum, leg) => sum + Math.abs(leg.notional ?? 0), 0);
    return `${count(legs.length)} names, ${dollars(total)} (no longer trade)`;
  }
  return legs
    .map((leg) => `${leg.ticker} ${dollars(leg.notional)} (${blockedReason(leg.reason)})`)
    .join("; ");
}

/**
 * The expected cost, split into the trading half and the holding half.
 *
 * The two halves are different things and are named that way: the trades are paid
 * once, tonight, on the legs the book actually sends; the borrow is charged on the
 * short leg for as long as the book is held. The total the card leads with is their
 * sum over that hold, which is why the card's own title states the hold.
 */
export function costDetail(
  horizon: number | null,
  split: import("./types").CostSplit | null,
): string | undefined {
  if (!split) return undefined;
  // A cost that rounds to zero is not a zero: a hold night trades a few hundred
  // dollars and prints "0.00 bp" at two places, which reads as a missing figure.
  const amount = (value: number): string =>
    value > 0 && value < 0.005 ? "<0.01" : value.toFixed(2);
  const parts: string[] = [];
  if (split.borrow !== null && split.borrow !== undefined) {
    parts.push(`borrow ${amount(split.borrow)} bp`);
  }
  if (split.trading !== null && split.trading !== undefined) {
    parts.push(`tonight's trades ${amount(split.trading)} bp`);
  }
  if (!parts.length) return undefined;
  return `${parts.join(", ")} over ${horizon === null ? "the hold" : `${horizon} sessions`}`;
}

/**
 * The fills' own cost, against the horizon it can be measured against.
 *
 * The day's realized cost is measured from the previous close to the fill, which is the
 * trade the loop actually made: the leg is sent after one close and fills at the next
 * open, so the overnight gap is inside it. That is a one-session horizon, and the
 * expectation it belongs beside is the day's own trading cost, not the period total
 * that carries borrow, which is a holding cost over twenty-one sessions and no fill
 * price pays it. The card states both horizons so the two numbers cannot be read as
 * like-for-like when they are not.
 */
export function realizedLine(
  fills: NonNullable<Snapshot["actual_holdings"]>["fills"],
  split: import("./types").CostSplit | null,
  fallbackExpected: number | null | undefined,
): string {
  if (!fills) return "realized cost not priced";
  if (fills.realized_cost_bps === null || fills.realized_cost_bps === undefined) {
    return "realized cost not priced";
  }
  const against =
    split && split.trading !== null && split.trading !== undefined
      ? ` against ${split.trading.toFixed(2)} bp of NAV of trading cost expected for the same one session`
      : ` against ${bps(fills.expected_cost_bps ?? fallbackExpected)} expected for the same one session`;
  const day = `realized ${fills.realized_cost_bps.toFixed(2)} bp of NAV over one session, from the previous close to the fill${against}`;
  const avg = fills.realized_cost_avg_bps;
  const days = fills.realized_cost_days;
  if (avg === null || avg === undefined || !days) return day;
  // The average is over several sessions and is a different statistic about a
  // different window: it is stated as its own number with its own day count rather
  // than set beside the one-session expectation as though the two were comparable.
  return `${day}. Separately, the fill history averages ${avg.toFixed(2)} bp of NAV across ${days} session(s)`;
}

/**
 * The full book before the floor, on the Operations tab.
 *
 * This is a diagnostic: it says what the sizing looked like before the floor was
 * applied and how much of the idea the floor costs. It is readable, and it is not
 * one of the numbers the morning reader acts on, so it sits with the run's own
 * detail rather than in the row of cards above the tables.
 */
export function ConstructionTelemetry({ snapshot }: { snapshot: Snapshot }) {
  const book = snapshot.book;
  const breadth = snapshot.breadth;
  // The names the risk model could not measure, published under the breadth block.
  // Absent on a document written before the evening published them, and an empty list
  // on a night that dropped none: both mean nothing to report, so both draw nothing.
  const droppedNoRisk = breadth?.dropped_no_risk ?? [];
  return (
    <Details
      hook="construction"
      summary={
        <>
          construction telemetry: the full book before the floor, {percent(book?.full_book_gross)}{" "}
          of NAV
        </>
      }
    >
      {droppedNoRisk.length > 0 ? (
        <p data-flag="dropped-no-risk" className="mt-2 text-xs text-slate-600">
          {count(breadth?.n_dropped_no_risk ?? droppedNoRisk.length)} name(s) never reached the
          book at all: the risk model has no specific risk for them, and a position is not sized
          on a median that is not its own.{" "}
          <span className="font-mono">
            {droppedNoRisk
              .slice(0, DROPPED_LINES)
              .map((entry) => (entry.reason ? `${entry.ticker} (${entry.reason})` : entry.ticker))
              .join(", ")}
            {droppedNoRisk.length > DROPPED_LINES
              ? ` and ${droppedNoRisk.length - DROPPED_LINES} more`
              : ""}
          </span>
          .
        </p>
      ) : null}
      <ul className="text-xs text-slate-600" data-telemetry="true">
        <li>
          The sizing starts wider than it trades: before dropping positions too small to trade,
          the ideal book was spread like about {Math.round(breadth?.n_eff_full_book ?? 0)} equal
          names at {percent(book?.full_book_achieved_annual_vol, 1)} predicted volatility.
        </li>
        <li>
          The floor keeps {count(book?.n_names)} names, which spread like about{" "}
          {Math.round(breadth?.n_eff_kept ?? 0)} equal names.
        </li>
        <li>
          Nothing in the morning route reads this: it says how much of the idea the floor
          costs.
        </li>
      </ul>
      <dl className="mt-1 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <div data-card="n_eff_full_book">
          <dt className="text-[0.65rem] uppercase tracking-wide text-slate-500">
            n_eff full book
          </dt>
          <dd className="font-mono tabular-nums">{oneDecimal(breadth?.n_eff_full_book)}</dd>
        </div>
        <div data-card="full-book-gross">
          <dt className="text-[0.65rem] uppercase tracking-wide text-slate-500">
            full book gross
          </dt>
          <dd className="font-mono tabular-nums">{percent(book?.full_book_gross)}</dd>
        </div>
        <div data-card="full-book-net">
          <dt className="text-[0.65rem] uppercase tracking-wide text-slate-500">
            full book net
          </dt>
          <dd className="font-mono tabular-nums">{percent(book?.full_book_net)}</dd>
        </div>
        <div data-card="full-book-vol">
          <dt className="text-[0.65rem] uppercase tracking-wide text-slate-500">
            full book forecast vol
          </dt>
          <dd className="font-mono tabular-nums">
            {percent(book?.full_book_achieved_annual_vol, 1)}
          </dd>
        </div>
      </dl>
    </Details>
  );
}

export function MetricsRow({
  snapshot,
  facts,
}: {
  snapshot: Snapshot;
  facts: BookFacts;
}) {
  const book = snapshot.book;
  const breadth = snapshot.breadth;
  const fills = snapshot.actual_holdings?.fills ?? null;
  const split = book?.expected_cost_split ?? null;
  const sent = fills?.n_orders ?? snapshot.bridge?.orders_sent ?? null;
  const nav = facts.nav;
  const intended = snapshot.reconciliation?.intended_notional ?? null;
  const sentNotional = snapshot.reconciliation?.sent_notional ?? null;
  // The card stands on the legs the broker was sent, which is what turnover means; the
  // legs the run built are stated in the construction disclosure when the document
  // carries both, and the built figure alone when it predates the split.
  const turnover = sentNotional ?? intended;
  const blocked = blockedLegs(snapshot);
  // The horizon the cost is quoted over: the sessions the book is held between
  // rebalances. `EFB_CADENCE` is absent on a daily loop, which is one session and is
  // the same 21 the E6/E9 convention used before the flag existed.
  const horizon = snapshot.run_status?.cadence?.k ?? 21;
  const held = horizon === 1 ? "1 session" : `${horizon} sessions`;
  // The names the risk model could not measure, for the book line below the cards.
  const droppedNoRisk = breadth?.dropped_no_risk ?? [];
  const droppedCount = breadth?.n_dropped_no_risk ?? droppedNoRisk.length;

  return (
    <section data-cards="true" className="rounded border border-slate-200 bg-white p-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        the book
        <HowToRead>
          every ratio here is quoted against NAV, so today&apos;s book compares with last
          month&apos;s even after the equity moves. Example: gross is{" "}
          {percent(book?.gross)} of NAV right now, {dollars(book?.gross_notional)} in all.
        </HowToRead>
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Card
          hook="gross"
          label="gross"
          value={percent(book?.gross)}
          detail={
            book?.gross_notional === null || book?.gross_notional === undefined
              ? "of NAV"
              : `${dollars(book.gross_notional)} of NAV`
          }
          info={
            <>
              The long and short sides added together, as a share of NAV, with the dollars
              beside it. It is held near 100% by construction, so it moves when the book is
              resized rather than when the market moves. Example: today&apos;s gross is{" "}
              {percent(book?.gross)} of NAV, {dollars(book?.gross_notional)}.
            </>
          }
        />
        <Card
          hook="net"
          label="net"
          value={percent(book?.net)}
          detail="of NAV"
          info={
            <>
              Long dollars less short dollars, as a share of NAV. Near zero means the book
              is not betting on the market&apos;s direction, only on one stock against
              another. Example: net is {percent(book?.net)} of NAV, {dollars(facts.netNotional)}
              {" "}in dollars.
            </>
          }
        />
        <Card
          hook="long-names"
          label="long names"
          value={count(facts.hasBook ? facts.nLong : null)}
          detail={facts.hasBook ? `${dollars(facts.longNotional)} of NAV` : undefined}
          info={
            <>
              How many stocks the book holds long, and the dollars behind them, as a share
              of NAV. It moves when the rebalance changes the book and when the guard
              repairs it. Example: {count(facts.hasBook ? facts.nLong : null)} longs carry{" "}
              {dollars(facts.longNotional)}.
            </>
          }
        />
        <Card
          hook="short-names"
          label="short names"
          value={count(facts.hasBook ? facts.nShort : null)}
          detail={facts.hasBook ? `${dollars(facts.shortNotional)} of NAV` : undefined}
          info={
            <>
              How many stocks the book is short, and the dollars behind them, as a share of
              NAV. The two sides are deliberately close to the same size. Example:{" "}
              {count(facts.hasBook ? facts.nShort : null)} shorts carry{" "}
              {dollars(facts.shortNotional)}.
            </>
          }
        />
        <Card
          hook="turnover"
          label="turnover"
          info={
            <>
              Every leg sent to the broker, in dollars, for the close this page was written
              for. A rebalance night trades the whole book; a hold night trades only what the
              drift guard repairs, so the number moves by an order of magnitude between the
              two. Example: {count(sent)} orders sent, {dollars(turnover)} of trading.
            </>
          }
        >
          <div className="font-mono text-sm leading-tight tabular-nums">
            {sentNotional !== null
              ? `Tonight: ${count(sent)} orders sent, ${dollars(sentNotional)}`
              : intended !== null
                ? `Tonight: the run built ${dollars(intended)} of legs`
                : `Tonight: ${count(sent)} orders sent, ${dollars(null)}`}
          </div>
          {turnover === null ? (
            <div className="text-xs text-slate-600">
              the reconciliation carries no notional for this close
            </div>
          ) : null}
          {blocked.length > 0 ? (
            <div data-blocked="true" className="text-xs text-slate-600">
              Blocked: {blockedText(blocked)}
            </div>
          ) : null}
        </Card>
        <Card
          hook="n_eff_kept"
          label="n_eff_kept"
          value={oneDecimal(breadth?.n_eff_kept)}
          detail={
            breadth === null || breadth === undefined
              ? "the book's effective breadth"
              : `spread like about ${Math.round(breadth.n_eff_kept ?? 0)} equal positions (out of ${count(
                  book?.n_names,
                )})`
          }
          info={
            <>
              Risk is spread as if the book held {Math.round(breadth?.n_eff_kept ?? 0)} equal
              positions. Example: two positions at 50/50 count as 2, at 90/10 about 1.2.
            </>
          }
        />
        <Card
          hook="largest-position"
          label="largest position"
          value={facts.largest?.ticker ?? "n/a"}
          detail={
            facts.largest
              ? `${percent(facts.largest.weight)} of NAV (${dollars(facts.largestNotional)})`
              : undefined
          }
          info={
            <>
              The biggest single weight in the book. A cap keeps any one name from carrying
              too much of the book&apos;s risk, so this is a position size, not a bet size.
              Example: {facts.largest?.ticker ?? "no name"} is{" "}
              {percent(facts.largest?.weight)} of NAV.
            </>
          }
        />
        <Card
          hook="expected-expense"
          label={horizon ? `expected cost, ${horizon}-session hold` : EXPECTED_EXPENSE}
          value={bps(book?.expected_cost_bps)}
          detail={costDetail(horizon, split)}
          info={
            <>
              What the book is expected to cost, in basis points of NAV, over the {held} it
              is held: the spread, impact and commission on the legs it sends are paid once,
              and the borrow is charged on the short leg for the whole hold. The two are
              added into the one total. Example: {costDetail(horizon, split) ?? "no split is published for this close"}.
            </>
          }
        />
        <Card
          hook="top10-share"
          label="top 10 share of gross"
          value={percent(facts.top10Share)}
          detail={facts.hasBook ? "the ten largest weights" : undefined}
          info={
            <>
              The ten largest weights as a share of the book&apos;s gross. It says how much
              of the book sits in its biggest ideas; the effective breadth beside it says how
              evenly the rest is spread. Example: the top ten carry{" "}
              {percent(facts.top10Share)} of gross.
            </>
          }
        />
        {snapshot.actual_holdings ? (
          <Card
            hook="fills"
            label="fills"
            value={
              fills === null
                ? snapshot.actual_holdings.read_by === "evening"
                  ? "none to reconcile yet"
                  : "not reconciled"
                : `${count(fills.n_filled)} of ${count(sent)} filled`
            }
            detail={
              fills === null
                ? snapshot.actual_holdings.read_by === "evening"
                  ? "the account was read before the orders went out"
                  : "the account was read without a reconciliation"
                : [
                    `${count(fills.not_sent)} never sent, ${count(fills.n_unfilled)} did not fill`,
                    realizedLine(fills, split, book?.expected_cost_bps ?? null),
                  ].join(" · ")
            }
            info={
              <>
                What the broker did with the legs it was sent, read back the next morning.
                A leg that did not fill leaves the book away from its target until the next
                send. Example: {count(fills?.n_filled)} of {count(sent)} filled,{" "}
                {count(fills?.n_unfilled)} did not.
              </>
            }
          />
        ) : null}
      </div>

      {book?.n_names ? (
        <p data-flag="book-line" className="mt-2 text-xs text-slate-600">
          {[
            `Tonight's book: ${count(book.n_names)} names.`,
            droppedCount > 0 ? `${count(droppedCount)} left out (no risk estimate yet);` : null,
            "positions too small to trade removed;",
            // The rule is a renormalization to gross 1.0 and the round shares land
            // where they land, so the achieved gross is stated beside the target
            // whenever the two differ by more than a rounding error.
            `the rest scaled to 100% of NAV${
              book.gross !== null && Math.abs(book.gross - 1) >= 0.005
                ? ` (${percent(book.gross)} after the round shares)`
                : ""
            }.`,
          ]
            .filter(Boolean)
            .join(" ")}
        </p>
      ) : null}
    </section>
  );
}
