// What needs a look, in the order the reader asks it.
//
// The run's own state first: that is the one that must never be missed, and it is
// the only thing on this page allowed to be red. Then the account against the
// store, which is the failure that makes every number below it wrong, and which is
// amber: a drift is a fact to read, not a broken loop. Then the legs the broker did
// not fill, one line each, because the count alone leaves the reader to open the
// store to find out which name did not happen.
//
// A position that left the account with nothing behind it is amber for the same
// reason, and it is the one line here that no other number on the page implies:
// the book, the orders and the fill count can all be right while a name has walked
// out of the account, which is what happened to PSKY on 2026-10-06. It is drawn
// with its own dollars, so the reader has the size of the adjustment in front of
// them rather than having to difference two books to find it.
//
// Deferred legs are amber by the same rule. The snapshot carries no deferral list
// (`run_status` has status, failures, splits, flags and the cost label, and the
// evening's own message is where the deferrals are named), so this page has none to
// show and says nothing rather than inferring one from a missing leg.

import { Panel } from "./Panel";
import { dollars, shares } from "./format";
import type { RunState } from "./status";
import type { ExitsBlock, Snapshot } from "./types";

/** How many miss lines the strip lists before it counts the rest. */
const MISS_LINES = 6;

export function Alerts({ snapshot, state }: { snapshot: Snapshot; state: RunState }) {
  const positions = snapshot.positions;
  const misses = snapshot.actual_holdings?.fills?.unfilled ?? [];
  const notSent = snapshot.actual_holdings?.fills?.not_sent_lines ?? [];
  const exits = snapshot.actual_holdings?.exits ?? null;
  const gone = exits?.names ?? [];

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

      {gone.length > 0 ? (
        <section
          data-alert="exits"
          data-tone="warn"
          data-feed={exits?.feed ?? "unknown"}
          role="status"
          className="border-l-4 border-amber-400 bg-amber-50 px-3 py-2 text-amber-900"
        >
          <p className="font-semibold">
            {gone.length} position{gone.length === 1 ? "" : "s"} left the account with no
            order behind {gone.length === 1 ? "it" : "them"}
          </p>
          <ul className="text-sm">
            {gone.map((name) => (
              <li key={name.ticker}>
                <span className="font-mono">{name.ticker}</span>{" "}
                {shares(name.quantity)} shares ({dollars(name.notional)}) — no closing order
                filled{exits?.feed === "read" ? " and no activity of the broker's" : ""}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs">
            {exits?.feed === "read"
              ? "The broker's activity feed was read for the window and names none of these."
              : "The broker's activity feed could not be read, so one explanation was not checked."}
            {exits?.previous_read
              ? ` Compared with the account as it was on ${exits.previous_read.slice(0, 10)}.`
              : ""}
          </p>
        </section>
      ) : null}

      {misses.length > 0 || notSent.length > 0 ? (
        <section
          data-alert="misses"
          data-tone="warn"
          data-fills="misses"
          role="status"
          className="border-l-4 border-amber-400 bg-amber-50 px-3 py-2 text-amber-900"
        >
          <p className="font-semibold">
            {misses.length} order{misses.length === 1 ? "" : "s"} did not fill
            {notSent.length > 0
              ? `, and ${notSent.length} leg${notSent.length === 1 ? "" : "s"} could not be sent`
              : ""}
          </p>
          <ul className="text-sm">
            {misses.slice(0, MISS_LINES).map((line) => (
              <li key={line}>{line}</li>
            ))}
            {misses.length > MISS_LINES ? (
              <li>and {misses.length - MISS_LINES} more</li>
            ) : null}
            {notSent.map((line) => (
              <li key={line} data-not-sent="true">
                {line}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
