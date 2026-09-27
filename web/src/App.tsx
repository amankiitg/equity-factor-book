// The live book monitor. One screen, from one JSON document.
//
// The order is the reading order of a question: what happened (the strip), what
// needs a look (the alerts), the numbers (the metrics), then the detail, with the
// name-by-name tables behind a drawer at the bottom. Status first because the one
// thing a monitor must never do is show an old book as though it were current: a run
// that stopped, errored, never happened or is late takes the colour of the strip, and
// a book that is not tonight's says so in words underneath it.
//
// Two columns on a laptop and one on a phone. The left column is the hedge and where
// the trades came from, the right is the book's shape and its largest names, which puts
// two long panels against two long panels and keeps the columns close in height. On a
// phone the single column reads in the same order: the hedge, the trades, then the
// book's shape, with the tables behind the drawer at the bottom. Nothing here is
// duplicated between the two: the sector totals live on the metrics row, the long and
// short dollars beside the name counts, and the largest names in their own panel rather
// than in a second list.

import { useEffect, useState } from "react";

import { Alerts } from "./Alerts";
import { Bridge } from "./Bridge";
import { Reasons, TopNames } from "./BookSections";
import { bookFacts } from "./book";
import { DrawerSection } from "./DrawerSection";
import { ExposuresSection } from "./ExposuresSection";
import { Movers, RiskConcentration } from "./FutureSections";
import { MetricsRow } from "./MetricsRow";
import { Panel } from "./Panel";
import { SectorSection } from "./SectorSection";
import { StatusStrip } from "./StatusStrip";
import { runState } from "./status";
import type { Attribution, Snapshot } from "./types";

// Re-exported for the page's own tests, which ask what the page says about a
// snapshot without rendering it.
export { health, pillFor, runState, runTone } from "./status";

/**
 * A P&L in basis points of the book, signed to one place.
 *
 * The attribution's P&L is in weight units: the book is gross 1.0, so a weight of
 * 0.0012 is 12 basis points of the book. Basis points are the unit a reader can
 * hold in their head, and the sign is the point of the section, so it is always
 * printed.
 */
const bookBps = (value: number | null | undefined): string =>
  value === null || value === undefined ? "n/a" : `${value >= 0 ? "+" : ""}${(value * 1e4).toFixed(1)} bp`;

/** A cost in basis points, or n/a: costs are already quoted in bp and unsigned. */
const costBps = (value: number | null | undefined): string =>
  value === null || value === undefined ? "n/a" : `${value.toFixed(2)} bp`;

/**
 * The attribution section: what the book earned, split three ways.
 *
 * The three components are the total, and the page says so with the worst day's
 * residual rather than by asserting it. The hedge's own factor P&L is beside them
 * because on a book whose hedge did its job it is the part that should have been
 * zero; the raw-beta line is there because it explains part of the idio number
 * and is not one of the three, which is the mistake the section exists to make
 * impossible.
 */
function AttributionSection({ attribution }: { attribution: Attribution }) {
  const cumulative = attribution.cumulative;
  if (!attribution.n_days) {
    return (
      <section>
        <h2 className="text-lg font-semibold">Attribution</h2>
        <p className="mt-1 text-sm text-slate-600">
          {attribution.note || "no attributed day is stored yet"}
        </p>
      </section>
    );
  }
  const days = [...attribution.daily].reverse();
  return (
    <section>
      <h2 className="text-lg font-semibold">Attribution</h2>
      <p className="mt-1 text-xs text-slate-500">
        {attribution.n_days} attributed day{attribution.n_days === 1 ? "" : "s"}, {
          attribution.first_day
        } to {attribution.last_day}. Every row is stored, by the evening run: factor P&L is the
        book's exposure times the factor returns, idio P&L is its positions times the specific
        returns, and the two plus the cost are the day's total.
      </p>
      <dl className="mt-3 text-sm">
        <dt className="font-medium">cumulative, the three components</dt>
        <dd>total: {bookBps(cumulative.pnl_total)}</dd>
        <dd>factor: {bookBps(cumulative.pnl_factor)}</dd>
        <dd>idio: {bookBps(cumulative.pnl_idio)}</dd>
        <dd>cost: {bookBps(cumulative.pnl_cost)}</dd>
        <dd>
          worst day's identity residual: {bookBps(cumulative.max_identity_residual)} over {
            cumulative.n_computed_specific
          } name-day(s) whose residual was computed rather than stored
        </dd>
        <dd className="mt-1">
          cost: expected {costBps(attribution.cost.expected_bps)}, realized{" "}
          {attribution.cost.realized_bps === null
            ? `n/a on ${attribution.n_days - attribution.cost.n_realized} of ${attribution.n_days} day(s)`
            : costBps(attribution.cost.realized_bps)}
        </dd>
      </dl>
      <table aria-label="attribution by day" className="mt-3 w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-300 text-left">
            <th className="py-1">close</th>
            <th className="py-1">total</th>
            <th className="py-1">factor</th>
            <th className="py-1">idio</th>
            <th className="py-1">cost</th>
            <th className="py-1">hedge factor P&L</th>
            <th className="py-1">raw beta</th>
            <th className="py-1">beta line</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day.trade_date} className="border-b border-slate-100">
              <td className="py-1 font-mono">{day.trade_date}</td>
              <td className="py-1">{bookBps(day.pnl_total)}</td>
              <td className="py-1">{bookBps(day.pnl_factor)}</td>
              <td className="py-1">{bookBps(day.pnl_idio)}</td>
              <td className="py-1">{bookBps(day.pnl_cost)}</td>
              <td className="py-1">{bookBps(day.pnl_timing)}</td>
              <td className="py-1">{oneDecimal(day.book_beta)}</td>
              <td className="py-1">{bookBps(day.pnl_beta)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-xs text-slate-500">
        The hedge factor P&L is the part of the factor number the exposure gap between the two design
        vintages produced: on a book whose hedge did its job it is the part that should have been
        zero. The beta line is the book's raw beta times the market's return. It explains part of the
        idio number and is never added to the three components.
      </p>
    </section>
  );
}

export function SnapshotView({ snapshot, now }: { snapshot: Snapshot; now: Date }) {
  const state = runState(snapshot, now);
  const facts = bookFacts(snapshot);

  return (
    <main className="mx-auto flex max-w-[88rem] flex-col gap-3 p-3 sm:p-4">
      <h1 className="text-xl font-bold">EFB live book</h1>
      <StatusStrip snapshot={snapshot} now={now} state={state} />
      <Alerts snapshot={snapshot} state={state} />
      <MetricsRow snapshot={snapshot} facts={facts} />
      <Bridge snapshot={snapshot} />
      <div data-columns="true" className="grid gap-3 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <AttributionSection attribution={snapshot.attribution} />

          <ExposuresSection snapshot={snapshot} />
          <Reasons facts={facts} />
        </div>
        <div className="flex flex-col gap-3">
          <SectorSection sectors={facts.sectors} />
          <TopNames facts={facts} />
          <RiskConcentration snapshot={snapshot} />
          <Movers snapshot={snapshot} />
        </div>
      </div>
      <DrawerSection snapshot={snapshot} facts={facts} />
    </main>
  );
}

type Load =
  | { kind: "loading" }
  | { kind: "loaded"; snapshot: Snapshot }
  | { kind: "missing" }
  | { kind: "error"; detail: string };

export function App({ now = () => new Date() }: { now?: () => Date }) {
  const [load, setLoad] = useState<Load>({ kind: "loading" });

  useEffect(() => {
    let live = true;
    fetch("/api/snapshot")
      .then(async (response) => {
        if (response.status === 404) {
          if (live) setLoad({ kind: "missing" });
          return;
        }
        if (!response.ok) {
          if (live) setLoad({ kind: "error", detail: `the endpoint answered ${response.status}` });
          return;
        }
        const snapshot = (await response.json()) as Snapshot;
        if (live) setLoad({ kind: "loaded", snapshot });
      })
      .catch((error: unknown) => {
        if (live) setLoad({ kind: "error", detail: String(error) });
      });
    return () => {
      live = false;
    };
  }, []);

  if (load.kind === "loading") {
    return <p className="p-6">loading the snapshot...</p>;
  }
  if (load.kind === "missing") {
    return (
      <div className="p-6">
        <Panel
          tone="bad"
          title="no snapshot at all"
          detail="the page cannot show a book: no run has written a snapshot yet"
        />
      </div>
    );
  }
  if (load.kind === "error") {
    return (
      <div className="p-6">
        <Panel
          tone="bad"
          title="the snapshot could not be read"
          detail={`${load.detail}. A missing token or a missing bucket shows here first.`}
        />
      </div>
    );
  }
  return <SnapshotView snapshot={load.snapshot} now={now()} />;
}

export default App;
