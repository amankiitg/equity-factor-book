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
import type { Exceptions } from "./exceptions";
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

/** The close the document's book is priced from, as a day. */
const bookClose = (snapshot: Snapshot): string | null => dateOnly(snapshot.book_as_of);

/** The close tonight's run was for, as a day. */
const closeOf = (snapshot: Snapshot): string | null => dateOnly(snapshot.target_close);

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
    const reason =
      snapshot.run_status?.detail ||
      (failing ? `failing inputs: ${failing}` : "no reason recorded");
    // A run that stopped before it sized anything leaves the previous close's book
    // standing in the document, so the page's own book and the close it names do not
    // agree. That is the one case where the top of the page can say the plain thing a
    // reader needs: nothing was priced tonight, and the book below is not tonight's.
    // The run's own words are kept beside it - they are what someone fixing the loop
    // needs - rather than replaced by a sentence that reads better.
    const stale = Boolean(
      bookClose(snapshot) && closeOf(snapshot) && bookClose(snapshot) !== closeOf(snapshot),
    );
    if (status === "error" && stale) {
      return {
        ok: false,
        headline: `no book was priced for the ${closeOf(snapshot)} close`,
        detail: `The run stopped on an error before it sized anything, and the book below is still the ${bookClose(
          snapshot,
        )} close. The run's own words: ${reason}`,
      };
    }
    return {
      ok: false,
      headline:
        status === "stale_stopped"
          ? "STALE STOP: the run refused to price a book"
          : `the run recorded ${status}`,
      detail: reason,
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
    // The proposal run's own answer, and only that: this headline used to read
    // "clean run", which the reader takes as the account being reconciled. A
    // successful proposal and a reconciled book are separate claims, and on
    // 2026-10-12 the first is true while the second is not.
    headline: `proposal run: ok for the ${dateOnly(snapshot.target_close) ?? "latest"} close`,
    detail: "the run priced a book; what the account holds is the reconciliation below",
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
    // A hold day is a normal evening that did not trade. It outranks the catch-up
    // qualifier because the hold is what the run was *for*; it is green, because
    // nothing about it needs attention.
    const cadence = snapshot.run_status?.cadence;
    if (cadence && cadence.day === "hold") {
      // A hold day that re-hedged says so, with the two exposures that made it: a
      // refresh is the loop trading on a day it was told not to, and the pill is
      // where a reader sees that it happened and what it was for. Still green -
      // the guard is doing its job, not reporting a fault.
      const guard = cadence.drift_guard;
      if (guard?.fired) {
        const before = `${(guard.exposure_before * 100).toFixed(1)}%`;
        const after = `${(guard.exposure_after * 100).toFixed(1)}%`;
        return `hold day, guard re-hedged ${before} -> ${after}`;
      }
      return cadence.pending
        ? "hold day (rebalance taken: one was missed)"
        : "hold day";
    }
    if (snapshot.run_status?.catch_up) {
      // A catch-up that priced a book is a proposal run that did its job: what was
      // wrong was the clock, not the book, and the pill says so while naming the
      // sessions it made up. Grey `catch_up` on its own read as a run that had
      // done something to the account, beside a panel saying the book was priced.
      const sessions = (snapshot.run_status.catch_up_sessions ?? []).length;
      if (sessions > 0 && (snapshot.book?.n_kept ?? 0) > 0) {
        return `ok (caught up ${sessions} session${sessions === 1 ? "" : "s"})`;
      }
      return "catch_up";
    }
    return "ok";
  }
  return status;
}

/** Red only for a failed or stopped run: everything else that needs a look is amber. */
export function runTone(pill: string): Tone {
  if (pill === "error" || pill === "stale_stopped") return "bad";
  if (pill === "expired") return "warn";
  if (pill === "market_closed" || pill === "catch_up") return "info";
  // `ok (caught up N sessions)` is the same state as `ok`, told with the reason the
  // run was late: it is green for the same reason and must not fall to amber.
  if (pill === "ok" || pill.startsWith("ok (")) return "good";
  // A hold day is the loop doing exactly what it was asked to do.
  if (pill.startsWith("hold day")) return "good";
  return "warn";
}

/** The state the strip renders: what happened, and how loudly it reads. */
export function runState(snapshot: Snapshot, now: Date): RunState {
  const pill = pillFor(snapshot, now);
  return { ...health(snapshot, now), pill, tone: runTone(pill) };
}

/** Which run wrote the document the page is showing. */
export type Writer = "evening" | "morning" | null;

/**
 * When the page's document was last written, and by which run.
 *
 * The document is written twice on a weekday: the evening writes the book, and the
 * morning writes the account read back into the same file. `generated_at` is only
 * the first of those, so a page that aged the document from it called a file
 * rewritten at 11:31 this morning three days old. The later of the two instants is
 * the document's age, and the run that made it is named beside it - the reader's
 * question is not only "how fresh is this" but "how fresh is the thing I am reading
 * that came from this run".
 */
export interface Freshness {
  /** The latest write of the two. */
  at: Date | null;
  /** The run that made that write. Null when the document does not name one. */
  by: Writer;
  /** The evening's own write, when a later read has been written over it. */
  evening: Date | null;
}

function instant(value: string | null | undefined): Date | null {
  if (!value) return null;
  const at = new Date(value);
  return Number.isNaN(at.getTime()) ? null : at;
}

export function freshness(snapshot: Snapshot): Freshness {
  const written = instant(snapshot.generated_at);
  const read = instant(snapshot.actual_holdings?.as_of);
  if (read && (!written || read.getTime() > written.getTime())) {
    return { at: read, by: snapshot.actual_holdings?.read_by ?? null, evening: written };
  }
  // The evening's own write, and a read that came with the evening's shipment
  // seconds later is still the evening's: there is no second run to name.
  return { at: written, by: written ? "evening" : null, evening: null };
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
 * - **the account against the book**, on the read the snapshot carries. The morning
 *   read holds the account after the fills, so the check is the account against the
 *   *target*: the names held and not wanted, the names wanted and not held - each
 *   classified from the same keys as ever - and the drift on the names both books
 *   carry. The evening read holds the account before the orders, so the check is the
 *   account against the *store*, `positions.matches`, and a mismatch whose every name
 *   is a class the document explains is `explained` while one unexplained name makes
 *   it `unresolved`;
 * - **the bridge's identities**, `bridge.holds`, with the failing identity named
 *   from `bridge.identities`;
 * - **the fills**, `actual_holdings.fills`, unresolved when `fills.n_unfilled` is
 *   non-zero, `not_run` when the snapshot is the evening's own read.
 *
 * `explained` does not fail the pill and `not_run` does not pass it: the reader sees
 * which of the three is which, and green means every check that could be run was
 * clean.
 */
export function reconciliation(snapshot: Snapshot, exceptions: Exceptions): Reconciliation {
  const positions = snapshot.positions ?? null;
  const bridge = snapshot.bridge ?? null;
  const read = snapshot.actual_holdings ?? null;
  const fills = read?.fills ?? null;
  const unexpected = exceptions.unexpected.length;
  const expected = exceptions.expected.length;
  const target = exceptions.compare;
  const checks: ReconciliationCheck[] = [];

  if (target) {
    // The morning read's own check. The account is compared with the book the
    // orders were built from, so the names on one side only are the finding and the
    // drift on the rest is the reading; the store comparison is not consulted here,
    // because a store that agrees with the account says nothing about the target.
    const heldNot = target.heldNotTargeted.length;
    const targetedNot = target.targetedNotHeld.length;
    const missing: string[] = [];
    if (heldNot > 0) {
      missing.push(`${heldNot} name${heldNot === 1 ? "" : "s"} the account holds and the target does not`);
    }
    if (targetedNot > 0) {
      missing.push(`${targetedNot} the target asks for and the account does not hold`);
    }
    const both = target.drifts.length;
    if (!target.read) {
      checks.push({
        name: "account against the target",
        state: "not_run",
        detail:
          "the read names no book to compare with the target, or the target names nothing to compare with the read",
      });
    } else if (missing.length === 0) {
      checks.push({
        name: "account against the target",
        state: "clean",
        detail: `the account holds the target's ${both} name(s) and nothing else`,
      });
    } else if (unexpected === 0) {
      checks.push({
        name: "account against the target",
        state: "explained",
        detail: `${missing.join(", ")}; every one of them a class the document explains`,
      });
    } else {
      checks.push({
        name: "account against the target",
        state: "unresolved",
        detail: `${missing.join(", ")}; ${unexpected} of them nothing on the page explains`,
      });
    }
  } else if (!positions || positions.matches === null) {
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
