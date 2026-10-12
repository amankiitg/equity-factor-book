// The run's own state: whether the page is telling the truth, and how loudly.
//
// Two questions that used to be answered in one place. *What* the run did is
// `health`: a stopped, errored, closed or late snapshot is a different statement
// from a clean evening, and the page must never show an old book as though it were
// tonight's. *How* that reads is the tone, and the owner's rule is narrow: red is
// for a run that failed or stopped, amber for what needs attention without a broken
// loop (a snapshot past its deadline, a positions drift, a leg that did not fill),
// and green or slate for a clean evening and a day the exchange was shut. Routine
// amber that never clears is what teaches a reader to ignore red.

import { dateOnly } from "./format";
import type { Snapshot } from "./types";

export type Tone = "good" | "info" | "warn" | "bad";

export interface Health {
  ok: boolean;
  headline: string;
  detail: string;
}

export interface RunState extends Health {
  /** One of the states the strip names: ok, stale_stopped, error, market_closed, catch_up, expired. */
  pill: string;
  tone: Tone;
}

const MINUTE = 60_000;

function minutesBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / MINUTE);
}

/** A human age, so the reader does not have to subtract two timestamps. */
export function ageText(generated: Date, now: Date): string {
  const minutes = minutesBetween(generated, now);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  return `${Math.round(hours / 24)} day${Math.round(hours / 24) === 1 ? "" : "s"} ago`;
}

/** Whether the snapshot has sat past the instant the next run was due. */
export function isLate(snapshot: Snapshot, now: Date): boolean {
  const due = snapshot.expected_next_by ? new Date(snapshot.expected_next_by) : null;
  return Boolean(due && now.getTime() > due.getTime());
}

/** Whether this snapshot is current, and if not, why in one sentence. */
export function health(snapshot: Snapshot, now: Date): Health {
  const status = snapshot.run_status?.status ?? "unknown";
  // A day the exchange was shut is neither clean nor broken: there was no close
  // to price, so no run was due and nothing is late. It must not read as a
  // failure, or the one line that has to mean something stops meaning anything.
  // It is not a licence to stop paying attention either, so the deadline check
  // below still applies: the next session's run is due the evening after it, and
  // a closed day must not sit on the page looking current while that run is
  // missing.
  const closed = status === "market_closed";
  if (!closed && status !== "ok") {
    const failing = (snapshot.run_status?.failing_inputs ?? [])
      .map((item) => `${item.input} ${item.sessions_behind ?? "no date"}`)
      .join("; ");
    const detail =
      snapshot.run_status?.detail ||
      (failing ? `failing inputs: ${failing}` : "no reason recorded");
    return {
      ok: false,
      headline:
        status === "stale_stopped"
          ? "STALE STOP: the run refused to price a book"
          : `the run recorded ${status}`,
      detail,
    };
  }
  if (isLate(snapshot, now)) {
    const due = new Date(snapshot.expected_next_by as string);
    return {
      ok: false,
      headline: closed
        ? `no run for the session after the ${dateOnly(snapshot.target_close) ?? "last"} close`
        : "no run for the session that should have closed",
      detail: `the snapshot for the ${dateOnly(snapshot.target_close) ?? "next"} close was expected by ${snapshot.expected_next_by}, ${Math.abs(
        minutesBetween(now, due),
      )} minute(s) ago`,
    };
  }
  if (closed) {
    return {
      ok: true,
      headline: `market closed on ${dateOnly(snapshot.target_close) ?? "the run's date"}: no run was due`,
      detail:
        snapshot.run_status?.detail ||
        "the exchange was shut, so there was no close to price",
    };
  }
  return {
    ok: true,
    // No detail: the notification status is not the page's to report here. The
    // snapshot is written before the message goes out, so what it carries is
    // `pending` on every evening; the strip states the one case the owner has to
    // see, which is the evening whose message never went out.
    headline: `clean run for the ${dateOnly(snapshot.target_close) ?? "latest"} close`,
    detail: "",
  };
}

/** The state the strip names, which is not quite the run's recorded status. */
export function pillFor(snapshot: Snapshot, now: Date): string {
  const status = snapshot.run_status?.status ?? "unknown";
  if (status === "error" || status === "stale_stopped" || status === "market_closed") {
    return status;
  }
  if (status === "ok") {
    // A snapshot sitting past the next run's deadline is the page's loudest fact,
    // and it outranks the qualifiers below: a catch-up that never arrived is not a
    // catch-up. Catch-up is named when the run is current, which is when it is
    // true of the book in hand rather than of a run nobody made.
    if (isLate(snapshot, now)) return "expired";
    return snapshot.run_status?.catch_up ? "catch_up" : "ok";
  }
  return status;
}

/** Red only for a failed or stopped run: everything else that needs a look is amber. */
export function runTone(pill: string): Tone {
  if (pill === "error" || pill === "stale_stopped") return "bad";
  if (pill === "expired") return "warn";
  if (pill === "market_closed" || pill === "catch_up") return "info";
  if (pill === "ok") return "good";
  return "warn";
}

/** The state the strip renders: what happened, and how loudly it reads. */
export function runState(snapshot: Snapshot, now: Date): RunState {
  const pill = pillFor(snapshot, now);
  return { ...health(snapshot, now), pill, tone: runTone(pill) };
}

/**
 * One reconciliation check, and whether the document lets it be decided at all.
 *
 * `not_run` is a real third state and not a soft failure: the evening reads the
 * account before the orders go out, so "the fills have not been reconciled yet" is
 * the ordinary condition of every evening snapshot, and a page that painted that
 * amber would be amber every night. What it must not do is call it clean.
 */
export type CheckState = "clean" | "explained" | "unresolved" | "not_run";

export interface ReconciliationCheck {
  /** The panel's own name for the check. */
  name: string;
  state: CheckState;
  detail: string;
}

export interface Reconciliation {
  checks: ReconciliationCheck[];
  /** Unresolved checks: what the reader has to act on, and what colours the pill. */
  unresolved: number;
  pass: boolean;
  tone: Tone;
  headline: string;
  detail: string;
}

/**
 * Whether the book the page is showing was reconciled, as distinct from proposed.
 *
 * The two halves of the loop are separate jobs and the page used to answer them in
 * one label: a successful proposal run for the 2026-10-09 close rendered as a green
 * "clean run" while the account-versus-store check failed and a bridge identity did
 * not add up. A proposal that priced a book and a book that reconciles against the
 * account are different claims, and the morning question is the second one.
 *
 * Three checks, each from a key that states it, and none of them inferred:
 *
 * - **account against the store**, `positions.matches`; a mismatch whose every name
 *   is a class the document explains (a deferred reversal, a removal the bridge
 *   itemised) is `explained`, and one unexplained name makes it `unresolved`;
 * - **the bridge's identities**, `bridge.holds`, with the failing identity named
 *   from `bridge.identities`;
 * - **the fills**, `actual_holdings.fills`, unresolved when `fills.n_unfilled` is
 *   non-zero, `not_run` when the snapshot is the evening's own read.
 *
 * `explained` does not fail the pill and `not_run` does not pass it: the reader sees
 * which of the three is which, and green means every check that could be run was
 * clean.
 */
export function reconciliation(
  snapshot: Snapshot,
  expected: number,
  unexpected: number,
): Reconciliation {
  const positions = snapshot.positions ?? null;
  const bridge = snapshot.bridge ?? null;
  const read = snapshot.actual_holdings ?? null;
  const fills = read?.fills ?? null;
  const checks: ReconciliationCheck[] = [];

  if (!positions || positions.matches === null) {
    checks.push({
      name: "account against the store",
      state: "not_run",
      detail: "the account has not been read against the stored positions",
    });
  } else if (positions.matches) {
    checks.push({
      name: "account against the store",
      state: "clean",
      detail: positions.note ?? `${positions.n_store ?? "?"} name(s) on both sides`,
    });
  } else if (unexpected === 0) {
    checks.push({
      name: "account against the store",
      state: "explained",
      // The writer's own sentence is kept rather than paraphrased: the page's job is
      // to classify the names, not to restate what the run said about them.
      detail: `${expected} mismatch(es), every one of them a class the document explains${
        positions.note ? ` — ${positions.note}` : ""
      }`,
    });
  } else {
    checks.push({
      name: "account against the store",
      state: "unresolved",
      detail: `${unexpected} unexplained mismatch(es) and ${expected} explained${
        positions.note ? ` — ${positions.note}` : ""
      }`,
    });
  }

  if (!bridge) {
    checks.push({
      name: "the bridge",
      state: "not_run",
      detail: "no bridge for this close",
    });
  } else {
    // A block with no identities is a block that did not check itself, which is not
    // the same answer as a block whose identities hold: the writer always publishes
    // them, and a page that read their absence as a pass would be reading a truncated
    // document as a clean one.
    const identities = bridge.identities ?? [];
    if (identities.length === 0) {
      checks.push({
        name: "the bridge",
        state: "not_run",
        detail: "the bridge carries no identity to check",
      });
    } else {
      const broken = identities.filter((identity) => !identity.holds);
      checks.push({
        name: "the bridge",
        state: broken.length === 0 ? "clean" : "unresolved",
        detail:
          broken.length === 0
            ? `${identities.length} identit${identities.length === 1 ? "y" : "ies"} hold`
            : broken
                .map(
                  (identity) =>
                    `${identity.name}: ${identity.left} against ${identity.right}`,
                )
                .join("; "),
      });
    }
  }

  if (!read) {
    checks.push({
      name: "the fills",
      state: "not_run",
      detail: "the account has not been read, so no fill was reconciled",
    });
  } else if (!fills) {
    checks.push({
      name: "the fills",
      state: "not_run",
      detail:
        read.read_by === "evening"
          ? "the account was read before the orders went out, so there is nothing to reconcile yet"
          : "the account was read without a fill reconciliation",
    });
  } else if ((fills.n_unfilled ?? 0) > 0) {
    checks.push({
      name: "the fills",
      state: "unresolved",
      detail: `${fills.n_unfilled} order(s) did not fill${
        (fills.not_sent ?? 0) > 0 ? `, and ${fills.not_sent} leg(s) were never sent` : ""
      }`,
    });
  } else {
    checks.push({
      name: "the fills",
      state: "clean",
      detail: `${fills.n_filled ?? 0} of ${fills.n_orders ?? 0} sent order(s) filled${
        (fills.not_sent ?? 0) > 0 ? `, ${fills.not_sent} leg(s) never sent` : ""
      }`,
    });
  }

  const unresolved = checks.filter((check) => check.state === "unresolved").length;
  const explained = checks.filter((check) => check.state === "explained").length;
  const notRun = checks.filter((check) => check.state === "not_run").length;
  const headline =
    unresolved > 0
      ? "reconciliation: unresolved"
      : notRun === checks.length
        ? "reconciliation: not run"
        : explained > 0
          ? "reconciliation: clean, with explained mismatches"
          : "reconciliation: clean";
  return {
    checks,
    unresolved,
    pass: unresolved === 0,
    tone: unresolved > 0 ? "warn" : notRun === checks.length ? "info" : "good",
    headline,
    detail: checks.map((check) => `${check.name}: ${check.detail}`).join("; "),
  };
}

/**
 * The two jobs on one line: proposal generation, and whether the book reconciled.
 *
 * Green only when both are: the run proposing a book says nothing about whether the
 * last one is what the account holds, and the strip's colour is the one thing a
 * reader takes without reading the sentence beside it.
 */
export function overallTone(proposal: Tone, reconciled: Tone): Tone {
  const rank: Record<Tone, number> = { bad: 3, warn: 2, info: 1, good: 0 };
  return rank[proposal] >= rank[reconciled] ? proposal : reconciled;
}
