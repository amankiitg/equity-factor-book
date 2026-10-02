// The book's own sections: the summary cards, the ten largest longs and shorts,
// and where the trades came from.
//
// Everything here is read from the snapshot's rows and the run's own manifest
// figures. Nothing is recomputed from a price series, because the page has none:
// the one derived quantity is the book in dollars, from the traded gross and the
// traded notional the snapshot states.

import type { BookFacts } from "./book";
import { count, dollars, oneDecimal, percent, signedDollars } from "./format";
import type { BookName, Snapshot } from "./types";

function Card({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded border border-slate-200 bg-white px-3 py-2" data-card={label}>
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      {detail ? <div className="text-xs text-slate-600">{detail}</div> : null}
    </div>
  );
}

/** The nine headline numbers, on one grid that falls from five columns to two. */
export function SummaryCards({ snapshot, facts }: { snapshot: Snapshot; facts: BookFacts }) {
  const kept = snapshot.breadth?.n_eff_kept ?? null;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5" data-cards="true">
      <Card label="long names" value={count(facts.nLong)} />
      <Card label="short names" value={count(facts.nShort)} />
      <Card label="long dollars" value={dollars(facts.longNotional)} />
      <Card label="short dollars" value={dollars(facts.shortNotional)} />
      <Card label="net dollars" value={signedDollars(facts.netNotional)} />
      <Card label="n_eff kept" value={oneDecimal(kept)} detail="effective breadth" />
      <Card
        label="largest position"
        value={facts.largest ? (facts.largest.ticker ?? "n/a") : "n/a"}
        detail={
          facts.largest
            ? `${percent(facts.largest.weight)} (${dollars(facts.largestNotional)})`
            : undefined
        }
      />
      <Card
        label="top 10 share of gross"
        value={percent(facts.top10Share)}
        detail="the ten largest weights"
      />
      <Card
        label="expected cost"
        value={
          snapshot.book?.expected_cost_bps === null ||
          snapshot.book?.expected_cost_bps === undefined
            ? "n/a"
            : `${snapshot.book.expected_cost_bps.toFixed(2)} bps`
        }
        detail={snapshot.run_status?.cost_label ?? undefined}
      />
    </div>
  );
}

function NameRow({ name, nav }: { name: BookName; nav: number | null }) {
  const weight = name.weight ?? 0;
  const amount = nav === null ? null : Math.abs(weight) * nav;
  return (
    <li
      data-ticker={name.ticker}
      className="flex flex-wrap items-baseline gap-x-3 border-b border-slate-100 py-1.5"
    >
      <span className="font-mono font-semibold">{name.ticker}</span>
      <span className="tabular-nums">{percent(weight)}</span>
      <span className="tabular-nums text-slate-600">{dollars(amount)}</span>
      <span className="w-full text-xs text-slate-500 sm:w-auto">{name.reason ?? ""}</span>
    </li>
  );
}

/** The ten largest on each side, side by side on a laptop and stacked on a phone. */
export function TopNames({ facts }: { facts: BookFacts }) {
  if (!facts.hasBook) return null;
  const panel = (title: string, names: BookName[], hook: string) => (
    <div data-top={hook}>
      <h3 className="text-base font-semibold">{title}</h3>
      <ul className="mt-1 text-sm">
        {names.map((name) => (
          <NameRow key={name.ticker} name={name} nav={facts.nav} />
        ))}
        {names.length === 0 ? <li className="py-1.5 text-sm text-slate-500">none</li> : null}
      </ul>
    </div>
  );
  return (
    <section data-section="top-names">
      <h2 className="text-lg font-semibold">The ten largest longs and shorts</h2>
      <div className="mt-2 grid gap-4 lg:grid-cols-2">
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
    <section data-section="reasons">
      <h2 className="text-lg font-semibold">Trades by reason</h2>
      <div className="mt-2 grid gap-4 lg:grid-cols-2">
        <div>
          <table className="w-full border-collapse text-sm" aria-label="trades by reason">
            <thead>
              <tr className="border-b border-slate-300 text-left">
                <th className="py-1">reason</th>
                <th className="py-1 text-right">names</th>
                <th className="py-1 text-right">dollars</th>
              </tr>
            </thead>
            <tbody>
              {facts.reasons.map((bucket) => (
                <tr key={bucket.reason} data-reason={bucket.reason} className="border-b border-slate-100">
                  <td className="py-1">{bucket.reason}</td>
                  <td className="py-1 text-right tabular-nums">{bucket.n}</td>
                  <td className="py-1 text-right tabular-nums">{dollars(bucket.notional)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-slate-500">
            The count and the dollars are the positions carrying each reason. The snapshot records
            one reason per name and no per-trade size, so the dollars are what the run holds under
            that reason, not the notional traded today.
          </p>
        </div>
        <div data-largest="names">
          <h3 className="text-base font-semibold">The ten largest names</h3>
          <ul className="mt-1 text-sm">
            {facts.largestNames.map((name) => (
              <NameRow key={name.ticker} name={name} nav={facts.nav} />
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
