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
import type { Snapshot } from "./types";

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
  // "filled of sent": a leg the evening never sent is not an order the broker could
  // have filled, so it is out of the denominator rather than counted as a miss.
  const sent =
    fills === null || fills.n_orders === null || fills.n_orders === undefined
      ? null
      : fills.n_orders - (fills.not_sent ?? 0);

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
        detail={snapshot.run_status?.cost_label ?? undefined}
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
              : fills.realized_cost_bps === null || fills.realized_cost_bps === undefined
                ? "realized cost not priced"
                : `realized ${fills.realized_cost_bps.toFixed(2)} against ${bps(
                    fills.expected_cost_bps ?? book?.expected_cost_bps,
                  )} expected`
          }
        />
      ) : null}
    </div>
  );
}
