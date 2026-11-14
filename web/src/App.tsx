// The live book monitor. One document, five tabs, and a first screen for the
// person who wants to know how the book is doing rather than whether the loop
// ran.
//
// The status strip stays above the tabs: the run's state, the close and the
// exception count are what a reader came for, and none of them belongs to one
// tab. The tabs below hold the jobs: the overview (the strategy, the four
// numbers, the exceptions and three pictures), positions (the tables and the
// risk panels), attribution (what the book earned and why), since the rebalance
// (the anchored panels a monthly cadence needs) and operations (the
// reconciliation, the bridge, the run's own detail, staleness and exclusions).
// The diagnostic tabs are the second and third read; the overview is the first.
//
// Every panel is mounted and the inactive ones carry `hidden`. That keeps the
// page's in-document search working across tabs and keeps a tab switch cheap,
// while the accessibility tree still exposes only the selected one.

import { useEffect, useState } from "react";

import { Alerts } from "./Alerts";
import { AttributionSection } from "./AttributionSection";
import { Bridge } from "./Bridge";
import { Reasons, TopNames } from "./BookSections";
import { bookFacts } from "./book";
import { Details } from "./Details";
import { DrawerSection } from "./DrawerSection";
import { ExposuresSection } from "./ExposuresSection";
import { Movers, RiskConcentration } from "./FutureSections";
import { HedgePanel } from "./HedgePanel";
import { ConstructionTelemetry, MetricsRow } from "./MetricsRow";
import { MonthlyPanels } from "./Monthly";
import { NotesDrawer } from "./Notes";
import { Overview } from "./Overview";
import { Glossary, Panel } from "./Panel";
import { SectorSection } from "./SectorSection";
import { StatusStrip } from "./StatusStrip";
import { classify } from "./exceptions";
import { dateOnly } from "./format";
import { overallTone, reconciliation, runState } from "./status";
import type { Snapshot } from "./types";

// Re-exported for the page's own tests, which ask what the page says about a
// snapshot without rendering it.
export { health, pillFor, runState, runTone } from "./status";

type View = "overview" | "book" | "attribution" | "rebalance" | "operations";

const TABS: Array<{ key: View; label: string }> = [
  { key: "overview", label: "Overview" },
  { key: "book", label: "Positions" },
  { key: "attribution", label: "Attribution" },
  { key: "rebalance", label: "Since the rebalance" },
  { key: "operations", label: "Operations" },
];

export function SnapshotView({ snapshot, now }: { snapshot: Snapshot; now: Date }) {
  const state = runState(snapshot, now);
  const facts = bookFacts(snapshot);
  const exceptions = classify(snapshot);
  const reconciled = reconciliation(snapshot, exceptions);
  const [view, setView] = useState<View>("overview");
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
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="view">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            data-view={tab.key}
            aria-selected={view === tab.key}
            aria-controls={`panel-${tab.key}`}
            onClick={() => setView(tab.key)}
            className={tabClass(view === tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id="panel-overview" hidden={view !== "overview"}>
        <Overview
          snapshot={snapshot}
          state={state}
          reconciled={reconciled}
          exceptions={exceptions}
          now={now}
        />
      </div>

      {/* The attribution panel sits before positions in the document so the
          positions drawer stays the last reading section, which is the order a
          reader moves in when the tab is open. The tab buttons keep their own
          order above. */}
      <div role="tabpanel" id="panel-attribution" hidden={view !== "attribution"}>
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
        <div data-columns="attribution" className="grid gap-3 lg:grid-cols-2">
          <div className="flex flex-col gap-3">
            <RiskConcentration snapshot={snapshot} />
          </div>
          <div className="flex flex-col gap-3">
            <Movers snapshot={snapshot} />
          </div>
        </div>
      </div>

      <div role="tabpanel" id="panel-rebalance" hidden={view !== "rebalance"}>
        {snapshot.monthly ? (
          <MonthlyPanels monthly={snapshot.monthly} />
        ) : (
          <p
            data-rebalance-absent="true"
            className="rounded border border-slate-200 bg-white p-3 text-sm text-slate-600"
          >
            this snapshot carries no anchored block, so there is no rebalance close to
            measure from. Positions and Attribution still render.
          </p>
        )}
      </div>

      <div role="tabpanel" id="panel-operations" hidden={view !== "operations"}>
        <div className="flex flex-col gap-2">
          <Details hook="run-detail" summary="run detail, reconciliation and exceptions">
            <Alerts
              snapshot={snapshot}
              state={state}
              reconciled={reconciled}
              exceptions={exceptions}
            />
          </Details>
          <Details hook="bridge" summary="bridge: the account before the rebalance and after it">
            <Bridge snapshot={snapshot} />
          </Details>
          <ConstructionTelemetry snapshot={snapshot} />
          <Details hook="staleness" summary="staleness and freshness">
            <dl className="grid gap-1 text-xs sm:grid-cols-2">
              <div>
                <dt className="text-slate-500">book close</dt>
                <dd className="font-mono">{dateOnly(snapshot.book_as_of) ?? "n/a"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">target close</dt>
                <dd className="font-mono">{dateOnly(snapshot.target_close) ?? "n/a"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">next run expected by</dt>
                <dd className="font-mono">{snapshot.expected_next_by ?? "n/a"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">generated at</dt>
                <dd className="font-mono">{snapshot.generated_at ?? "n/a"}</dd>
              </div>
            </dl>
          </Details>
          <NotesDrawer snapshot={snapshot} />
          <Details hook="glossary" summary="what the words mean">
            <Glossary />
          </Details>
        </div>
      </div>

      <div role="tabpanel" id="panel-book" hidden={view !== "book"}>
        <div className="flex flex-col gap-3">
          <MetricsRow snapshot={snapshot} facts={facts} />
          <div data-columns="true" className="grid gap-3 lg:grid-cols-2">
            <div className="flex flex-col gap-3">
              <HedgePanel snapshot={snapshot} facts={facts} monthly={snapshot.monthly} />
              <ExposuresSection snapshot={snapshot} />
              {snapshot.monthly ? null : <Reasons facts={facts} snapshot={snapshot} />}
            </div>
            <div className="flex flex-col gap-3">
              <SectorSection
                snapshot={snapshot}
                sectors={facts.sectors}
                monthly={snapshot.monthly}
              />
              <TopNames facts={facts} monthly={snapshot.monthly} />
            </div>
          </div>
          <DrawerSection snapshot={snapshot} facts={facts} />
        </div>
      </div>
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
