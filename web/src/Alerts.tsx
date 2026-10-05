// What needs a look, in the order the reader asks it.
//
// The run's own state first: that is the one that must never be missed, and it is
// the only thing on this page allowed to be red. Then the account against the
// store, which is the failure that makes every number below it wrong, and which is
// amber: a drift is a fact to read, not a broken loop. Then the legs the broker did
// not fill, one line each, because the count alone leaves the reader to open the
// store to find out which name did not happen.
//
// Deferred legs are amber by the same rule. The snapshot carries no deferral list
// (`run_status` has status, failures, splits, flags and the cost label, and the
// evening's own message is where the deferrals are named), so this page has none to
// show and says nothing rather than inferring one from a missing leg.

import { Panel } from "./Panel";
import type { RunState } from "./status";
import type { Snapshot } from "./types";

/** How many miss lines the strip lists before it counts the rest. */
const MISS_LINES = 6;

export function Alerts({ snapshot, state }: { snapshot: Snapshot; state: RunState }) {
  const positions = snapshot.positions;
  const misses = snapshot.actual_holdings?.fills?.unfilled ?? [];

  return (
    <div data-alerts="true" className="flex flex-col gap-2">
      <Panel
        hook="run"
        tone={state.tone}
        title={state.headline}
        detail={state.detail}
      />

      {positions ? (
        <Panel
          hook="positions"
          tone={
            positions.matches === true ? "good" : positions.matches === null ? "info" : "warn"
          }
          title="positions against the store"
          detail={positions.note ?? "not read"}
        />
      ) : null}

      {misses.length > 0 ? (
        <section
          data-alert="misses"
          data-tone="warn"
          data-fills="misses"
          role="status"
          className="border-l-4 border-amber-400 bg-amber-50 px-3 py-2 text-amber-900"
        >
          <p className="font-semibold">
            {misses.length} order{misses.length === 1 ? "" : "s"} did not fill
          </p>
          <ul className="text-sm">
            {misses.slice(0, MISS_LINES).map((line) => (
              <li key={line}>{line}</li>
            ))}
            {misses.length > MISS_LINES ? (
              <li>and {misses.length - MISS_LINES} more</li>
            ) : null}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
