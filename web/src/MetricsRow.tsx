// The dense row of numbers the book is read by, one card per figure.
//
// Every value is either stated by the snapshot or derived in `book.ts` from what it
// states, and a value the snapshot does not carry prints "n/a": a zero would claim a
// measurement nobody made, which is the one thing this page cannot afford. The numbers
// are monospaced and tabular so a column of them lines up and a digit that moves is
// visible rather than merely different.
//
// Two things moved out of this row in the redesign. The pre-floor construction
// telemetry - the effective breadth before the floor and the index-sized book's gross -
// answers a question nobody has in the morning ("what did the sizing look like before
// it was finished"), so it sits behind one disclosure at the end of the row. And the
// denominator is now stated on every ratio: the book's gross is 100% of NAV by
// construction, so "gross 100.00%" alone reads as a fact about the book when it is a
// fact about the sizing target, and weights, turnover and costs are all quoted against
// NAV for the same reason.
//
// Turnover is the one card that is a correction rather than a move. The per-name column
// the page used to total counts only the legs of names the book still holds, so on
// 2026-10-09 it summed to $267,018 while the evening sent $379,430 - the difference
// being the 34 legs that closed names leaving the book, which the join drops. The card
// now reads the reconciliation's own `intended_notional`, which is every leg the run
// built, and the disclosure says which legs the per-name column leaves out.

import { Details } from "./Details";
import { EXPECTED_EXPENSE, bpOfNav } from "./labels";
import { count, dollars, oneDecimal, percent } from "./format";
import type { BookFacts } from "./book";
import type { Snapshot } from "./types";

function Card({
  hook,
  label,
  value,
  detail,
}: {
  /** A stable name for the tests and for anything reading the page mechanically. */
  hook: string;
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div data-card={hook} className="rounded border border-slate-200 bg-white px-2 py-1">
      <div className="text-[0.65rem] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="font-mono text-base leading-tight tabular-nums">{value}</div>
      {detail ? <div className="text-xs text-slate-600">{detail}</div> : null}
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

/** The expected cost, split into the trading half and the holding cost. */
export function costDetail(
  label: string | null | undefined,
  split: import("./types").CostSplit | null,
): string | undefined {
  const parts: string[] = [];
  if (split && split.trading !== null && split.trading !== undefined) {
    const names = (["spread", "impact", "commission"] as const)
      .filter((name) => split[name] !== null && split[name] !== undefined)
      .map((name) => `${name} ${(split[name] as number).toFixed(2)}`);
    parts.push(
      `trading ${split.trading.toFixed(2)} bp of NAV${
        names.length ? ` (${names.join(" + ")})` : ""
      }`,
    );
    if (split.borrow !== null && split.borrow !== undefined) {
      parts.push(`borrow ${split.borrow.toFixed(2)} bp of NAV of holding cost`);
    }
  }
  if (label) parts.push(label);
  return parts.length ? parts.join(" · ") : undefined;
}

/**
 * The fills' own cost, against the horizon it can be measured against.
 *
 * The day's realized cost is measured from the previous close to the fill, which is the
 * trade the loop actually made: the leg is sent after one close and fills at the next
 * open, so the overnight gap is inside it. That is a one-session horizon, and the
 * expectation it belongs beside is the day's own trading cost - not the period average
 * of a five-day fill history, and not the total that carries borrow, which is a holding
 * cost over a twenty-one session horizon and no fill price pays it. The panel states
 * both horizons so the two numbers cannot be read as like-for-like when they are not.
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
  const sent = fills?.n_orders ?? null;
  const nav = facts.nav;
  const intended = snapshot.reconciliation?.intended_notional ?? null;
  const sentNotional = snapshot.reconciliation?.sent_notional ?? null;
  const unsentNotional = snapshot.reconciliation?.unsent_notional ?? null;
  // The card stands on the legs the broker was sent, which is what turnover means; the
  // legs the run built are stated beside it when the document carries both, and the
  // built figure alone when it predates the split.
  const turnover = sentNotional ?? intended;

  // The day's legs, against NAV. The reconciliation states the notional of every leg
  // the run built, which is the figure that measured the day's trading; the per-name
  // column the book carries totals less than it, because a name that left the book has
  // no row to attach its closing leg to.
  const perNameTotal = (book?.names ?? []).reduce(
    (total, name) => total + Math.abs(name.traded_notional ?? 0),
    0,
  );

  return (
    <section data-cards="true" className="rounded border border-slate-200 bg-white p-2">
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
        />
        <Card hook="net" label="net" value={percent(book?.net)} detail="of NAV" />
        <Card
          hook="long-names"
          label="long names"
          value={count(facts.hasBook ? facts.nLong : null)}
          detail={facts.hasBook ? `${dollars(facts.longNotional)} of NAV` : undefined}
        />
        <Card
          hook="short-names"
          label="short names"
          value={count(facts.hasBook ? facts.nShort : null)}
          detail={facts.hasBook ? `${dollars(facts.shortNotional)} of NAV` : undefined}
        />
        <Card
          hook="turnover"
          label={sentNotional === null ? "turnover, order-leg notional" : "turnover, legs sent"}
          value={percent(nav === null || turnover === null ? null : turnover / nav)}
          detail={
            turnover === null
              ? "the reconciliation carries no notional for this close"
              : sentNotional === null || intended === null || unsentNotional === null
                ? `${dollars(turnover)} of every leg built, of NAV`
                : `${dollars(sentNotional)} sent of NAV, and ${dollars(intended)} built, of which ${dollars(unsentNotional)} was never sent`
          }
        />
        <Card
          hook="n_eff_kept"
          label="n_eff_kept"
          value={oneDecimal(breadth?.n_eff_kept)}
          detail={
            // What the number means, not its name: an effective breadth of 130 is
            // the book behaving like 130 equally sized positions, which is the only
            // way to read it without knowing the statistics.
            breadth === null || breadth === undefined
              ? "the book&apos;s effective breadth"
              : `spread like about ${Math.round(breadth.n_eff_kept ?? 0)} equal positions (out of ${count(
                  book?.n_names,
                )})`
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
        />
        <Card
          hook="expected-expense"
          label={EXPECTED_EXPENSE}
          value={bps(book?.expected_cost_bps)}
          detail={costDetail(snapshot.run_status?.cost_label, split)}
        />
        <Card
          hook="top10-share"
          label="top 10 share of gross"
          value={percent(facts.top10Share)}
          detail={facts.hasBook ? "the ten largest weights" : undefined}
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
          />
        ) : null}
      </div>

      <Details
        hook="construction"
        summary={
          <>
            construction telemetry — the full book before the floor, {percent(book?.full_book_gross)}{" "}
            of NAV
          </>
        }
      >
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
        <div data-flag="turnover-note" className="mt-2 text-xs text-slate-500">
          Turnover on the card is{" "}
          <code>
            {sentNotional === null
              ? "reconciliation.intended_notional"
              : "reconciliation.sent_notional"}
          </code>
          ,{" "}
          {sentNotional === null
            ? "every leg the evening built for this close, whether or not it was sent — this document predates the sent-only figure, so the card stands on the built one."
            : "the legs the broker was sent for this close; the legs built and never sent are stated beside it."}
          {perNameTotal > 0
            ? ` The book's own per-name rows total ${dollars(
                perNameTotal,
              )} here, and the difference is not an error in either: a name that left the book has no row for its closing leg, so the trades-by-reason table carries that row itself.`
            : ""}{" "}
          The sent-only notional is in the evening&apos;s email and is not published in this
          document.
        </div>
      </Details>
    </section>
  );
}
