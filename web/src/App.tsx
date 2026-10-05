// The live book monitor. One screen, from one JSON document.
//
// The order is the reading order of a question: what happened (the strip), what
// needs a look (the alerts), the numbers (the metrics), then the detail, with the
// name-by-name tables behind a drawer at the bottom. Status first because the one
// thing a monitor must never do is show an old book as though it were current: a run
// that stopped, errored, never happened or is late takes the colour of the strip, and
// a book that is not tonight's says so in words underneath it.
//
// Two columns on a laptop and one on a phone. The left column is the hedge, which is
// the thing the page exists to show is still exact; the right is the book's shape,
// its largest names and where the trades came from. Nothing here is duplicated
// between the two: the sector totals live on the metrics row, the long and short
// dollars beside the name counts, and the largest names in their own panel rather
// than in a second list.

import { useEffect, useState } from "react";

import { Alerts } from "./Alerts";
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
import type { Snapshot } from "./types";

// Re-exported for the page's own tests, which ask what the page says about a
// snapshot without rendering it.
export { health, pillFor, runState, runTone } from "./status";

export function SnapshotView({ snapshot, now }: { snapshot: Snapshot; now: Date }) {
  const state = runState(snapshot, now);
  const facts = bookFacts(snapshot);

  return (
    <main className="mx-auto flex max-w-[88rem] flex-col gap-3 p-3 sm:p-4">
      <h1 className="text-xl font-bold">EFB live book</h1>
      <StatusStrip snapshot={snapshot} now={now} state={state} />
      <Alerts snapshot={snapshot} state={state} />
      <MetricsRow snapshot={snapshot} facts={facts} />
      <div className="grid gap-3 lg:grid-cols-2">
        <ExposuresSection snapshot={snapshot} />
        <div className="flex flex-col gap-3">
          <SectorSection sectors={facts.sectors} />
          <TopNames facts={facts} />
          <Reasons facts={facts} />
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
