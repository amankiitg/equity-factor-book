// The dense row of numbers the book is read by, one card per figure.
//
// Every value is either stated by the snapshot or derived in `book.ts` from what it
// states, and a value the snapshot does not carry prints "n/a": a zero would claim a
// measurement nobody made, which is the one thing this page cannot afford. The
// numbers are monospaced and tabular so a column of them lines up and a digit that
// moves is visible rather than merely different.
//
// The gross, the net and the breadth are the traded book's own. The full book's
// gross and breadth travel beside them under their own names, because one number
// labelled "gross" that changes meaning between evenings is worse than two numbers.

import type { BookFacts } from "./book";
import { count, dollars, oneDecimal, percent } from "./format";
import type { CostSplit, Snapshot } from "./types";

export function Card({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div
      data-card={label}
      className="rounded border border-slate-200 bg-white px-2.5 py-1.5"
    >
      <div className="text-[0.65rem] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="font-mono text-base leading-tight tabular-nums">{value}</div>
      {detail ? <div className="text-xs text-slate-600">{detail}</div> : null}
    </div>
  );
}

/** A cost in basis points, or "n/a" when the run did not price one. */
export function bps(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : `${value.toFixed(2)} bps`;
}

/** The expected cost, split into the trading half and the holding cost.
 *
 * A total alone leaves the reader unable to tell which half a number belongs to,
 * and the fills can only be measured against one of them: spread, impact and
 * commission are what a fill price pays, and borrow is the short leg's cost over
 * the horizon, which no fill price can be compared to. Absent on a manifest that
 * predates the breakdown, in which case the card shows the total and its label and
 * says nothing about a split it does not have.
 */
export function costDetail(
  label: string | null | undefined,
  split: CostSplit | null,
): string | undefined {
  const parts: string[] = [];
  if (split && split.trading !== null && split.trading !== undefined) {
    const names = (["spread", "impact", "commission"] as const)
      .filter((name) => split[name] !== null && split[name] !== undefined)
      .map((name) => `${name} ${(split[name] as number).toFixed(2)}`);
    parts.push(
      `trading ${split.trading.toFixed(2)} bps${names.length ? ` (${names.join(" + ")})` : ""}`,
    );
    if (split.borrow !== null && split.borrow !== undefined) {
      parts.push(`borrow ${split.borrow.toFixed(2)} bps of holding cost`);
    }
  }
  if (label) parts.push(label);
  return parts.length ? parts.join(" · ") : undefined;
}

/**
 * The fills' own cost, against the half of the expectation it can be measured by.
 *
 * Two figures, and both are on purpose. The day's realized cost is measured from
 * the previous close to the fill, which is the trade the loop actually made: the
 * leg is sent after one close and fills at the next open, so the overnight gap is
 * inside it. The average over every reconciled day is the one that can be read as
 * execution quality, and it is stated with its day count.
 */
export function realizedLine(
  fills: NonNullable<Snapshot["actual_holdings"]>["fills"],
  split: CostSplit | null,
  fallbackExpected: number | null | undefined,
): string {
  if (!fills) return "realized cost not priced";
  if (fills.realized_cost_bps === null || fills.realized_cost_bps === undefined) {
    return "realized cost not priced";
  }
  // The trading half when the split is published, because that is the only half a
  // fill price can be measured against: borrow is a holding cost over the horizon
  // and no fill price pays it. Without a split the total is all there is, and it is
  // stated as what it is rather than compared against as though it were trading.
  const against =
    split && split.trading !== null && split.trading !== undefined
      ? ` against ${split.trading.toFixed(2)} bps of trading cost expected`
      : ` against ${bps(fills.expected_cost_bps ?? fallbackExpected)} expected`;
  const day = `realized ${fills.realized_cost_bps.toFixed(2)} bps from the previous close to the fill${against}`;
  const avg = fills.realized_cost_avg_bps;
  const days = fills.realized_cost_days;
  if (avg === null || avg === undefined || !days) return day;
  return `${day} · ${avg.toFixed(2)} bps average over ${days} reconciled day${
    days === 1 ? "" : "s"
  }`;
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
  // "filled of sent": the denominator is the legs the evening **sent**, because a
  // leg it never sent is not an order the broker could have filled. Sent is
  // `n_orders` itself, not `n_orders - not_sent`: the writer counts the submitted
  // legs only, so subtracting the never-sent legs a second time reported "197 of
  // 165 filled" for a morning that reconciled 197 of 199. The never-sent and the
  // did-not-fill legs are stated beside it as their own counts.
  const sent = fills?.n_orders ?? null;

  return (
    <div data-cards="true" className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      <Card
        label="gross"
        value={percent(book?.gross)}
        detail={
          book?.gross_notional === null || book?.gross_notional === undefined
            ? undefined
            : dollars(book.gross_notional)
        }
      />
      <Card label="net" value={percent(book?.net)} />
      <Card
        label="long names"
        value={count(facts.hasBook ? facts.nLong : null)}
        detail={facts.hasBook ? dollars(facts.longNotional) : undefined}
      />
      <Card
        label="short names"
        value={count(facts.hasBook ? facts.nShort : null)}
        detail={facts.hasBook ? dollars(facts.shortNotional) : undefined}
      />
      <Card
        label="n_eff_kept"
        value={oneDecimal(breadth?.n_eff_kept)}
        detail={breadth?.kept_label || undefined}
      />
      <Card
        label="n_eff_full_book"
        value={oneDecimal(breadth?.n_eff_full_book)}
        detail={breadth?.full_book_label || undefined}
      />
      <Card
        label="largest position"
        value={facts.largest?.ticker ?? "n/a"}
        detail={
          facts.largest
            ? `${percent(facts.largest.weight)} (${dollars(facts.largestNotional)})`
            : undefined
        }
      />
      <Card
        label="expected cost"
        value={bps(book?.expected_cost_bps)}
        detail={costDetail(snapshot.run_status?.cost_label, split)}
      />
      <Card
        label="top 10 share of gross"
        value={percent(facts.top10Share)}
        detail={facts.hasBook ? "the ten largest weights" : undefined}
      />
      <Card
        label="full book before the floor"
        value={percent(book?.full_book_gross)}
        detail="the index-sized book, before the floor"
      />
      {snapshot.actual_holdings ? (
        <Card
          label="fills"
          value={
            fills === null
              ? // Neither a zero nor a blank: the evening reads the account before
                // it sends anything, so there is nothing to reconcile yet, and
                // "0 filled" would report the evening as a day on which nothing
                // traded.
                snapshot.actual_holdings.read_by === "evening"
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
                  `${count(fills.not_sent)} never sent, ${count(
                    fills.n_unfilled,
                  )} did not fill`,
                  realizedLine(
                    fills,
                    split,
                    book?.expected_cost_bps ?? null,
                  ),
                ].join(" · ")
          }
        />
      ) : null}
    </div>
  );
}
