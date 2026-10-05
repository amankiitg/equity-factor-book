// The right-hand column's own sections: the top names on each side, and where the
// trades came from.
//
// Everything here is read from the snapshot's rows and the run's own manifest
// figures. Nothing is recomputed from a price series, because the page has none: the
// one derived quantity is the book in dollars, from the traded gross and the traded
// notional the snapshot states.

import type { BookFacts } from "./book";
import { dollars, percent } from "./format";
import type { BookName } from "./types";

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
      <div className="mt-2 grid gap-4 sm:grid-cols-2">
        {panel("Longs", facts.topLongs, "longs")}
        {panel("Shorts", facts.topShorts, "shorts")}
      </div>
    </section>
  );
}

/** Where the trades came from: one row per reason the run recorded. */
export function Reasons({ facts }: { facts: BookFacts }) {
  if (!facts.hasBook) return null;
  return (
    <section data-section="reasons" className="rounded border border-slate-200 bg-white p-3">
      <h2 className="text-base font-semibold">Trades by reason</h2>
      <table className="mt-2 w-full border-collapse text-sm" aria-label="trades by reason">
        <thead>
          <tr className="border-b border-slate-300 text-left">
            <th className="py-1">reason</th>
            <th className="py-1 text-right">names</th>
            <th className="py-1 text-right">dollars</th>
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
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-xs text-slate-500">
        The count and the dollars are the positions carrying each reason. The snapshot records one
        reason per name and no per-trade size, so the dollars are what the run holds under that
        reason, not the notional traded today.
      </p>
    </section>
  );
}
