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
// one line under the count. Each name that stays carries a plain label and what
// happens next, so a reader does not have to work out whether a name means action:
// "in transit", "stuck", "too small" or "look at this". Only the last is drawn
// amber, and the panel says how many kinds of gap it could not check at all behind a
// toggle, because a page that found nothing and a page that could not look are
// different answers - and because the reader who wants the key names is the one who
// knows to open a toggle.
//
// The legs the broker did not fill keep their own panel, one line each, and so does a
// position that left the account with nothing behind it: that last one is the line no
// other number on the page implies, which is what happened to PSKY on 2026-10-06.

import { Details } from "./Details";
import { NEXT_STEP, exceptionText, type Exceptions, type Mismatch } from "./exceptions";
import { dollars, percent, shares, signedDollars } from "./format";
import { Panel } from "./Panel";
import type { Reconciliation, RunState } from "./status";
import type { ExitsBlock, Snapshot } from "./types";

/** How many miss lines the strip lists before it counts the rest. */
const MISS_LINES = 6;

/** How many drifts, and how many one-sided names, before the counts take over. */
const DRIFT_LINES = 3;
const MISMATCH_LINES = 8;

function checkClass(state: Reconciliation["checks"][number]["state"]): string {
  return state === "unresolved" ? "font-semibold text-amber-900" : "text-slate-700";
}

/**
 * The evening's own comparison, kept where it cannot be read as today's.
 *
 * The evening reads the account before it sends anything, so what it compared was
 * the account against the positions the loop had written down - neither the target
 * nor the fills. It is not dropped on a morning read: a name the store holds and the
 * account does not is a fact about the loop's own record.
 *
 * The morning replaced it, so the line says that first and answers the only question
 * left about it: are its names still open? A name the document explains - the
 * previous close's deferred reversals, a leg the broker would not take - is done
 * with, and the line says so rather than making the reader count. A name nothing
 * explains is named on the line, because that is the morning this panel exists for.
 */
function EveningCompare({
  snapshot,
  evening,
  resolved,
}: {
  snapshot: Snapshot;
  evening: Mismatch[];
  resolved: number;
}) {
  const positions = snapshot.positions ?? null;
  if (!positions || evening.length === 0) return null;
  const open = evening.filter((entry) => entry.key === "");
  const names = evening.map((entry) => entry.ticker).sort();
  const verdict =
    open.length === 0
      ? `${evening.length} name${evening.length === 1 ? "" : "s"}, ${evening.length === 1 ? "it is" : "both"} settled since`
      : `${open.length} still open: ${open.map((entry) => entry.ticker).join(", ")}`;
  return (
    <Details
      hook="evening-compare"
      summary={
        <>
          last night&apos;s check, before the orders ({names.join(", ")}) — {verdict}
        </>
      }
    >
      <p className="text-xs text-slate-600">
        The evening read the account before it sent anything, so this compares it with the
        positions the loop had written down — not with the target, and not after the fills. The
        morning&apos;s read above replaced it{resolved > 0 ? `; ${resolved} name(s) here are ones it has already settled` : ""}.
      </p>
      <ul className="mt-1 text-sm">
        {evening.map((entry) => (
          <li key={`${entry.side}-${entry.ticker}`} data-evening-mismatch={entry.side}>
            <span className="font-mono">{entry.ticker}</span> —{" "}
            {entry.side === "at_broker"
              ? "the loop&apos;s own record has it and the account does not"
              : "the account has it and the loop&apos;s own record does not"}
            {entry.key === "" ? ", and nothing here explains it" : ` — ${entry.why}`}
            {entry.key === "" ? "" : `; ${NEXT_STEP[entry.label]}`}
          </li>
        ))}
      </ul>
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
  const drifts = exceptions.compare?.drifts ?? [];
  const overnight = exceptions.evening ?? [];
  // One label per class, and the class's own words once: a list of four names all
  // "in transit" does not need the sentence four times.
  const left = exceptions.unexpected;
  const settled = exceptions.expected;
  const settledLabels = [...new Set(settled.map((entry) => `${entry.label}: ${NEXT_STEP[entry.label]}`))];
  const settledEvening = overnight.filter((entry) => entry.key !== "").length;
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
              <span className="font-mono tabular-nums">{signedDollars(row.delta)}</span>
              {row.target === null || row.target === 0
                ? ""
                : ` (${percent(row.delta / Math.abs(row.target), 1)} of the position)`}
              : the account holds {dollars(row.held)} against the target&apos;s{" "}
              {dollars(row.target)} — price moved since the close
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

      {left.length > 0 ? (
        <div data-alert="mismatches" data-tone="warn" className="mt-2">
          <p className="font-semibold">
            {left.length} name{left.length === 1 ? "" : "s"} to look at
          </p>
          <ul className="text-sm">
            {left.slice(0, MISMATCH_LINES).map((entry) => (
              <li key={`${entry.side}-${entry.ticker}`} data-label={entry.label}>
                <span className="font-mono font-semibold">{entry.ticker}</span>{" "}
                <span className="rounded bg-amber-100 px-1 text-xs font-semibold uppercase tracking-wide text-amber-900">
                  {entry.label}
                </span>{" "}
                — {entry.why}; {NEXT_STEP[entry.label]}.
              </li>
            ))}
            {left.length > MISMATCH_LINES ? <li>and {left.length - MISMATCH_LINES} more</li> : null}
          </ul>
        </div>
      ) : null}

      {settled.length > 0 ? (
        <ul data-expected="true" className="mt-2 text-sm text-slate-600">
          <li>
            {settled.length} name{settled.length === 1 ? "" : "s"} already settled, nothing to do:{" "}
            {settled.map((entry) => entry.ticker).sort().join(", ")}
          </li>
          {settledLabels.length > 0 ? <li className="text-xs">{settledLabels.join("; ")}</li> : null}
        </ul>
      ) : null}

      {exceptions.unchecked.length > 0 ? (
        <Details
          hook="unchecked"
          summary={
            <>
              {exceptions.unchecked.length} kind{exceptions.unchecked.length === 1 ? "" : "s"} of
              gap this page cannot check yet
            </>
          }
        >
          <ul data-unchecked="true" className="text-xs text-slate-600">
            {exceptions.unchecked.map((entry) => (
              <li key={entry.what}>
                {entry.what}: the page would need {entry.needs}.
              </li>
            ))}
          </ul>
        </Details>
      ) : null}

      <EveningCompare snapshot={snapshot} evening={overnight} resolved={settledEvening} />
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
