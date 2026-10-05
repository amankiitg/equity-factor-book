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
    headline: `clean run for the ${dateOnly(snapshot.target_close) ?? "latest"} close`,
    detail: snapshot.run_status?.notify_status
      ? `the owner was notified (${snapshot.run_status.notify_status})`
      : "",
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
