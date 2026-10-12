// What needs a look, in the order the reader asks it.
//
// The two jobs first, as two panels: the proposal run's own state (the one thing on
// the page allowed to be red) and then whether the book reconciled - the checks the
// strip's second pill summarises. Which comparison the reconciliation is made of
// follows the read: the morning's account read holds the account after the fills, so
// the check is the account against the target, and the evening's account-versus-store
// comparison is kept beside it under a label that says when it was taken, because a
// comparison the reader might mistake for today's answer is worse than one they have
// to open.
//
// Under the account-against-target check are the largest drifts, name by name: the
// check says how many names are on one side only, and the drift is what the rest of
// the book is doing, which is the number that says whether a mismatch is one break
// or a book that was never filled.
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

import { Details } from "./Details";
import { exceptionText, type Exceptions, type Mismatch } from "./exceptions";
import { dollars, shares, signedDollars } from "./format";
import { Panel } from "./Panel";
import type { Reconciliation, RunState } from "./status";
import type { ExitsBlock, Snapshot } from "./types";

/** How many miss lines the strip lists before it counts the rest. */
const MISS_LINES = 6;

/** How many drifts, and how many one-sided names, before the counts take over. */
const DRIFT_LINES = 3;
const MISMATCH_LINES = 8;

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

/**
 * The evening's own comparison, kept where it cannot be read as today's.
 *
 * The evening reads the account before it sends anything, so what it compared was
 * the account against the positions the loop had written down - neither the target
 * nor the fills. It is not dropped on a morning read: a name the store holds and the
 * account does not is a fact about the loop's own record. It is collapsed under a
 * label that says which comparison it is and when it was taken, so a reader scanning
 * for the morning answer does not find the evening's.
 */
function EveningCompare({ snapshot, evening }: { snapshot: Snapshot; evening: Mismatch[] }) {
  const positions = snapshot.positions ?? null;
  if (!positions || evening.length === 0) return null;
  return (
    <Details
      hook="evening-compare"
      summary={<>evening, before the orders — the account against the store: {evening.length} name(s)</>}
    >
      <p className="text-xs text-slate-600">
        Read before the orders went out, so this compares the account with the positions the loop
        had written down, not with the target and not after the fills. It is how the stored book
        and the account differed going into the session.
        {positions.note ? ` The run's own note: ${positions.note}.` : ""}
      </p>
      <ul className="mt-1 text-sm">
        {evening.map((entry) => (
          <li key={`${entry.side}-${entry.ticker}`} data-evening-mismatch={entry.side}>
            <span className="font-mono">{entry.ticker}</span> —{" "}
            {entry.side === "at_broker"
              ? "the store holds it and the account does not"
              : "the account holds it and the store does not"}
            {entry.key === "" ? " — nothing on the page explains it" : ` — ${entry.why}`}
          </li>
        ))}
      </ul>
      {positions.source ? (
        <p className="mt-1 text-xs text-slate-500">read against {positions.source}</p>
      ) : null}
    </Details>
  );
}

function ReconciliationPanel({
  snapshot,
  reconciled,
  exceptions,
}: {
  snapshot: Snapshot;
  reconciled: Reconciliation;
  exceptions: Exceptions;
}) {
  const expected = expectedLines(exceptions.expected);
  const drifts = exceptions.compare?.drifts ?? [];
  const overnight = exceptions.evening ?? [];
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

      {drifts.length > 0 ? (
        <ul data-drifts="true" className="mt-1 text-xs text-slate-600">
          {drifts.slice(0, DRIFT_LINES).map((row) => (
            <li key={row.ticker}>
              drift{" "}
              <span className="font-mono font-medium">{row.ticker}</span>{" "}
              <span className="font-mono tabular-nums">{signedDollars(row.delta)}</span>: the
              account holds {dollars(row.held)} against the target&apos;s {dollars(row.target)}
            </li>
          ))}
          {drifts.length > DRIFT_LINES ? (
            <li>
              and {drifts.length - DRIFT_LINES} other name(s) both books carry, none of them by
              more than {dollars(Math.abs(drifts[DRIFT_LINES].delta))}
            </li>
          ) : null}
        </ul>
      ) : null}

      {exceptions.unexpected.length > 0 ? (
        <div data-alert="mismatches" data-tone="warn" className="mt-2">
          <p className="font-semibold">
            {exceptions.unexpected.length} mismatch
            {exceptions.unexpected.length === 1 ? "" : "es"} nothing on the page explains
          </p>
          <ul className="text-sm">
            {exceptions.unexpected.slice(0, MISMATCH_LINES).map((entry) => (
              <li key={`${entry.side}-${entry.ticker}`}>
                <span className="font-mono">{entry.ticker}</span> — {entry.why}
              </li>
            ))}
            {exceptions.unexpected.length > MISMATCH_LINES ? (
              <li>and {exceptions.unexpected.length - MISMATCH_LINES} more</li>
            ) : null}
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

      <EveningCompare snapshot={snapshot} evening={overnight} />
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

      <ReconciliationPanel snapshot={snapshot} reconciled={reconciled} exceptions={exceptions} />

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
