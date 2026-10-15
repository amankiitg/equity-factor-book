// The right-hand column's own sections: the top names on each side, and where the
// trades came from.
//
// Everything here is read from the snapshot's rows and the run's own manifest
// figures. Nothing is recomputed from a price series, because the page has none: the
// one derived quantity is the book in dollars, from the traded gross and the traded
// notional the snapshot states.

import { Details } from "./Details";
import type { BookFacts } from "./book";
import { dollars, percent } from "./format";
import type { BookName, Snapshot } from "./types";

function NameRow({ name, nav }: { name: BookName; nav: number | null }) {
  const weight = name.weight ?? 0;
  const amount = nav === null ? null : Math.abs(weight) * nav;
  return (
    <li
      data-ticker={name.ticker}
      className="flex flex-wrap items-baseline gap-x-3 border-b border-slate-100 py-1"
    >
      <span className="font-mono font-semibold">{name.ticker}</span>
      <span className="font-mono tabular-nums">{percent(weight)}</span>
      <span className="font-mono tabular-nums text-slate-600">{dollars(amount)}</span>
      <span className="w-full text-xs text-slate-500 sm:w-auto">{name.reason ?? ""}</span>
    </li>
  );
}

/** The ten largest on each side, side by side on a wide screen and stacked on a phone. */
export function TopNames({ facts }: { facts: BookFacts }) {
  if (!facts.hasBook) return null;
  const panel = (title: string, names: BookName[], hook: string) => (
    <div data-top={hook}>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <ul className="mt-1 text-sm">
        {names.map((name) => (
          <NameRow key={name.ticker} name={name} nav={facts.nav} />
        ))}
        {names.length === 0 ? <li className="py-1 text-sm text-slate-500">none</li> : null}
      </ul>
    </div>
  );
  return (
    <section data-section="top-names" className="rounded border border-slate-200 bg-white p-3">
      <h2 className="text-base font-semibold">The largest longs and shorts</h2>
      <p className="mt-1 text-sm text-slate-600">
        the largest position is {facts.largest?.ticker ?? "n/a"}
        {facts.largest ? ` at ${percent(facts.largest.weight)} of NAV` : ""}; the two lists of ten
        are below.
      </p>
      <Details hook="top-names" summary={<>the ten largest on each side</>}>
        <div className="mt-1 grid gap-4 sm:grid-cols-2">
          {panel("Longs", facts.topLongs, "longs")}
          {panel("Shorts", facts.topShorts, "shorts")}
        </div>
      </Details>
    </section>
  );
}

/**
 * Where the trades came from: one row per reason the run recorded, and it adds up.
 *
 * The per-name rows are the legs of the names the book still holds, and a name that
 * left the book has no row for the closing leg that took it out, so the rows summed
 * to less than the day's turnover and the reader had to notice. The closing legs are
 * one row of their own - the difference between the turnover card and these rows -
 * and every row carries its share of the turnover, so the column totals 100%.
 *
 * The basis is the card's own: the legs the broker was sent when the document
 * carries that figure, and every leg the run built when it does not.
 */
export function Reasons({ facts, snapshot }: { facts: BookFacts; snapshot: Snapshot }) {
  if (!facts.hasBook) return null;
  const reconciliation = snapshot.reconciliation ?? null;
  const turnover = reconciliation?.sent_notional ?? reconciliation?.intended_notional ?? null;
  const perName = facts.reasons.reduce((total, bucket) => total + bucket.traded, 0);
  // The closing legs of the names that left, which no per-name row can carry. Zero
  // rather than a negative when the per-name column already exceeds the card: the
  // difference is the loop's arithmetic, not a row of the table.
  const exited = turnover === null ? null : Math.max(0, turnover - perName);
  const total = turnover === null ? perName : turnover;
  const share = (amount: number): string =>
    total > 0 ? percent(amount / total, 1) : "n/a";
  const sent = reconciliation?.sent_notional ?? null;

  return (
    <section data-section="reasons" className="rounded border border-slate-200 bg-white p-3">
      <h2 className="text-base font-semibold">Trades by reason</h2>
      <table className="mt-2 w-full border-collapse text-sm" aria-label="trades by reason">
        <thead>
          <tr className="border-b border-slate-300 text-left">
            <th className="py-1">reason</th>
            <th className="py-1 text-right">names</th>
            <th className="py-1 text-right">held</th>
            <th className="py-1 text-right">traded</th>
            <th className="py-1 text-right">share</th>
          </tr>
        </thead>
        <tbody>
          {facts.reasons.map((bucket) => (
            <tr
              key={bucket.reason}
              data-reason={bucket.reason}
              className="border-b border-slate-100"
            >
              <td className="py-1">{bucket.reason}</td>
              <td className="py-1 text-right font-mono tabular-nums">{bucket.n}</td>
              <td className="py-1 text-right font-mono tabular-nums">
                {dollars(bucket.notional)}
              </td>
              <td
                className="py-1 text-right font-mono tabular-nums"
                data-traded={bucket.reason}
              >
                {dollars(bucket.traded)}
              </td>
              <td className="py-1 text-right font-mono tabular-nums">{share(bucket.traded)}</td>
            </tr>
          ))}
          {exited !== null ? (
            <tr data-reason="exited" className="border-b border-slate-100">
              <td className="py-1">exited (closing legs of names that left)</td>
              <td className="py-1 text-right font-mono tabular-nums">—</td>
              <td className="py-1 text-right font-mono tabular-nums">—</td>
              <td className="py-1 text-right font-mono tabular-nums" data-traded="exited">
                {dollars(exited)}
              </td>
              <td className="py-1 text-right font-mono tabular-nums">{share(exited)}</td>
            </tr>
          ) : null}
        </tbody>
        <tfoot>
          <tr data-total="true" className="border-t border-slate-300 font-medium">
            <td className="py-1">total</td>
            <td className="py-1" />
            <td className="py-1 text-right font-mono tabular-nums">
              {dollars(facts.reasons.reduce((total_, bucket) => total_ + bucket.notional, 0))}
            </td>
            <td className="py-1 text-right font-mono tabular-nums" data-traded-total="true">
              {turnover === null ? dollars(perName) : dollars(turnover)}
            </td>
            <td className="py-1 text-right font-mono tabular-nums">
              {turnover === null ? "n/a" : percent(1, 0)}
            </td>
          </tr>
        </tfoot>
      </table>
      <p className="mt-1 text-xs text-slate-500">
        Traded is the day&apos;s turnover by reason: the legs the broker was{" "}
        {sent === null ? "built" : "sent"} for the close
        {sent === null ? " (this document predates the sent figure)" : ""}. The names and held
        columns are the positions carrying each reason, not a difference between two books. The
        exited row is computed here as the turnover card less the per-name rows
        {turnover === null || exited === null
          ? ""
          : ` (${dollars(turnover)} − ${dollars(perName)} = ${dollars(exited)})`}
        , because a name that left the book has no row for its closing leg.
      </p>
    </section>
  );
}
