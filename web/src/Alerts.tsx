// What needs a look, in the order the reader asks it.
//
// The two jobs first, as two panels: the proposal run's own state (the one thing on
// the page allowed to be red) and then whether the book reconciled - the checks the
// strip's second pill summarises. The account-versus-store comparison is one of
// those checks rather than a panel of its own, because a mismatch is a fact about
// reconciliation and reading it beside the two other checks is what stops it being
// taken for the whole answer.
//
// The mismatches are then split. A name the document explains - a deferred reversal,
// a removal the bridge itemised - is not an exception, and listing four of them
// beside a real break is how a page teaches its reader to skim the list. They go in
// one line under the count. Only the unexplained ones are drawn in amber, and the
// panel says which of the brief's classes it could not check at all, because a page
// that found nothing and a page that could not look are different answers.
//
// The legs the broker did not fill keep their own panel, one line each, and so does a
// position that left the account with nothing behind it: that last one is the line no
// other number on the page implies, which is what happened to PSKY on 2026-10-06.

import { exceptionText, type Exceptions, type Mismatch } from "./exceptions";
import { dollars, shares } from "./format";
import { Panel } from "./Panel";
import type { Reconciliation, RunState } from "./status";
import type { ExitsBlock, Snapshot } from "./types";

/** How many miss lines the strip lists before it counts the rest. */
const MISS_LINES = 6;

/** The expected names, grouped by the class that explains them, in one line each. */
function expectedLines(mismatches: Mismatch[]): string[] {
  const groups = new Map<string, string[]>();
  for (const entry of mismatches) {
    const list = groups.get(entry.why) ?? [];
    list.push(entry.ticker);
    groups.set(entry.why, list);
  }
  return [...groups.entries()].map(
    ([why, tickers]) => `${tickers.length} expected: ${why} — ${[...tickers].sort().join(", ")}`,
  );
}

function checkClass(state: Reconciliation["checks"][number]["state"]): string {
  return state === "unresolved" ? "font-semibold text-amber-900" : "text-slate-700";
}

function ReconciliationPanel({
  reconciled,
  exceptions,
}: {
  reconciled: Reconciliation;
  exceptions: Exceptions;
}) {
  const expected = expectedLines(exceptions.expected);
  return (
    <section
      data-alert="reconciliation"
      data-tone={reconciled.tone}
      role="status"
      className={`border-l-4 px-3 py-2 ${
        reconciled.unresolved > 0
          ? "border-amber-400 bg-amber-50 text-amber-900"
          : "border-slate-300 bg-slate-50 text-slate-800"
      }`}
    >
      <p className="font-semibold">{reconciled.headline}</p>
      <ul className="mt-1 text-sm">
        {reconciled.checks.map((check) => (
          <li key={check.name} data-check={check.state} className={checkClass(check.state)}>
            <span className="font-medium">{check.name}</span>
            {check.state === "not_run" ? " (not run)" : ""}
            {check.state === "unresolved" ? " (unresolved)" : ""}
            {check.state === "explained" ? " (explained)" : ""}: {check.detail}
          </li>
        ))}
      </ul>

      {exceptions.unexpected.length > 0 ? (
        <div data-alert="positions" data-tone="warn" className="mt-2">
          <p className="font-semibold">
            {exceptions.unexpected.length} mismatch
            {exceptions.unexpected.length === 1 ? "" : "es"} nothing on the page explains
          </p>
          <ul className="text-sm">
            {exceptions.unexpected.map((entry) => (
              <li key={`${entry.side}-${entry.ticker}`}>
                <span className="font-mono">{entry.ticker}</span> — {entry.why}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {expected.length > 0 ? (
        <ul data-expected="true" className="mt-2 text-sm text-slate-600">
          {expected.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}

      {exceptions.unchecked.length > 0 ? (
        <ul data-unchecked="true" className="mt-1 text-xs text-slate-500">
          {exceptions.unchecked.map((entry) => (
            <li key={entry.what}>
              not checked here: {entry.what} — this snapshot does not carry it, so the page
              cannot classify it. It needs {entry.needs}.
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function Alerts({
  snapshot,
  state,
  reconciled,
  exceptions,
}: {
  snapshot: Snapshot;
  state: RunState;
  reconciled: Reconciliation;
  exceptions: Exceptions;
}) {
  const misses = snapshot.actual_holdings?.fills?.unfilled ?? [];
  const notSent = snapshot.actual_holdings?.fills?.not_sent_lines ?? [];
  const exits: ExitsBlock | null = snapshot.actual_holdings?.exits ?? null;
  const gone = exits?.names ?? [];

  return (
    <div data-alerts="true" className="flex flex-col gap-2">
      <Panel hook="run" tone={state.tone} title={state.headline} detail={state.detail} />

      <ReconciliationPanel reconciled={reconciled} exceptions={exceptions} />

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
                <span className="font-mono">{name.ticker}</span> {shares(name.quantity)} shares
                ({dollars(name.notional)}) — no closing order filled
                {exits?.feed === "read" ? " and no activity of the broker's" : ""}
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
