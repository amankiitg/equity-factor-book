// The live book monitor. One screen, from one JSON document, in two tabs.
//
// The page answers two different jobs and used to answer them in one column: whether
// the loop is working (what happened overnight, does the account match the book, must
// I act today) and what the book earned (attribution, cost, risk against forecast).
// The first is a thirty-second read every morning; the second is a few minutes once a
// week. So the strip - both run states, the mode, the close, the account read and the
// exception count - sits above the tabs and is visible from either, and the tabs
// below it hold the two jobs. The book monitor is the default because it is the one
// that is read every day.
//
// Within the book monitor the order is the reading order of the morning question:
// the numbers (metrics), then the arithmetic between the three books (bridge), then
// two columns - where the trading went and what the book looks like - with the
// name-by-name tables behind the drawer at the bottom. Nothing is duplicated between
// the columns: the sector totals live on the metrics row, the long and short dollars
// beside the name counts, and the largest names in their own panel.
//
// Behind the tabs, the rule the redesign added: what is a diagnostic is behind a
// disclosure, and what answers the morning question is not. The full exposure table,
// the construction's telemetry and the derivation prose are behind `Details`; the
// check on the identity, the sector deltas and the exception names are not.

import { useEffect, useState } from "react";

import { Alerts } from "./Alerts";
import { AttributionSection } from "./AttributionSection";
import { Bridge } from "./Bridge";
import { Reasons, TopNames } from "./BookSections";
import { bookFacts } from "./book";
import { DrawerSection } from "./DrawerSection";
import { ExposuresSection } from "./ExposuresSection";
import { Movers, RiskConcentration } from "./FutureSections";
import { HedgePanel } from "./HedgePanel";
import { MetricsRow } from "./MetricsRow";
import { MonthlyPanels } from "./Monthly";
import { Glossary, Panel } from "./Panel";
import { SectorSection } from "./SectorSection";
import { StatusStrip } from "./StatusStrip";
import { classify } from "./exceptions";
import { overallTone, reconciliation, runState } from "./status";
import type { Snapshot } from "./types";

// Re-exported for the page's own tests, which ask what the page says about a
// snapshot without rendering it.
export { health, pillFor, runState, runTone } from "./status";

type View = "book" | "attribution";

export function SnapshotView({ snapshot, now }: { snapshot: Snapshot; now: Date }) {
  const state = runState(snapshot, now);
  const facts = bookFacts(snapshot);
  const exceptions = classify(snapshot);
  const reconciled = reconciliation(snapshot, exceptions);
  const [view, setView] = useState<View>("book");
  const tabClass = (active: boolean): string =>
    `rounded px-3 py-1 text-sm font-semibold ${
      active ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-800 hover:bg-slate-200"
    }`;

  return (
    <main className="mx-auto flex max-w-[88rem] flex-col gap-3 p-3 sm:p-4">
      <h1 className="text-xl font-bold">EFB paper book</h1>
      <StatusStrip
        snapshot={snapshot}
        now={now}
        state={state}
        tone={overallTone(state.tone, reconciled.tone)}
        reconciled={reconciled}
        exceptions={exceptions}
      />
      <Glossary />
      {/* The tabs switch the body, not the strip: the run's state and the exception
          count are what a reader came for, and neither belongs to one job. */}
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="view">
        <button
          type="button"
          role="tab"
          data-view="book"
          aria-selected={view === "book"}
          onClick={() => setView("book")}
          className={tabClass(view === "book")}
        >
          Book monitor
        </button>
        <button
          type="button"
          role="tab"
          data-view="attribution"
          aria-selected={view === "attribution"}
          onClick={() => setView("attribution")}
          className={tabClass(view === "attribution")}
        >
          Attribution
        </button>
      </div>

      {view === "book" ? (
        <>
          <Alerts
            snapshot={snapshot}
            state={state}
            reconciled={reconciled}
            exceptions={exceptions}
          />
          {/* The anchored panels when the document carries them, and the nightly
              ones when it does not. A monthly book's hold day has nothing to say in a
              comparison with last night, and the anchor is what the page is about;
              every document published before the block existed still renders exactly
              as it did, because the block is absent rather than empty. */}
          {snapshot.monthly ? (
            <MonthlyPanels monthly={snapshot.monthly} />
          ) : (
            <>
              <MetricsRow snapshot={snapshot} facts={facts} />
              <Bridge snapshot={snapshot} />
            </>
          )}
          <div data-columns="true" className="grid gap-3 lg:grid-cols-2">
            <div className="flex flex-col gap-3">
              <HedgePanel snapshot={snapshot} facts={facts} />
              <ExposuresSection snapshot={snapshot} />
              {snapshot.monthly ? null : <Reasons facts={facts} snapshot={snapshot} />}
            </div>
            <div className="flex flex-col gap-3">
              <SectorSection snapshot={snapshot} sectors={facts.sectors} />
              <TopNames facts={facts} />
            </div>
          </div>
          <DrawerSection snapshot={snapshot} facts={facts} />
        </>
      ) : (
        <>
          {/* The section hides itself when the document carries no attribution block,
              which is the right rule for a page read top to bottom and the wrong one
              behind a tab the reader has just asked for: a tab that opens a blank
              screen reads as a broken page. So the tab states the absence instead. */}
          {snapshot.attribution ? null : (
            <p
              data-attribution="absent"
              className="rounded border border-slate-200 bg-white p-3 text-sm text-slate-600"
            >
              this snapshot carries no attribution block, so there is nothing to attribute
              here: it was published before the attribution step ran, or the step wrote no
              day for its close. The book monitor is unaffected.
            </p>
          )}
          <AttributionSection attribution={snapshot.attribution} snapshot={snapshot} />
          <div data-columns="true" className="grid gap-3 lg:grid-cols-2">
            <div className="flex flex-col gap-3">
              <RiskConcentration snapshot={snapshot} />
            </div>
            <div className="flex flex-col gap-3">
              <Movers snapshot={snapshot} />
            </div>
          </div>
        </>
      )}
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
        <Panel tone="bad" title="the snapshot could not be read" detail={load.detail} />
      </div>
    );
  }
  return <SnapshotView snapshot={load.snapshot} now={now()} />;
}

export default App;
