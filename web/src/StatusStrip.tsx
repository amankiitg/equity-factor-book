// The top strip: the two things the run did, and what they read.
//
// A successful proposal and a reconciled book are two claims, and the page used to
// make one of them: a green "clean run" for the 2026-10-09 close sat above an
// account-versus-store mismatch and a bridge identity that did not add up. So the
// strip carries two pills, "proposal run" and "reconciliation", and green is the
// answer to both. The strip's colour is the one thing a reader takes without
// reading the sentence beside it, which is why it is the colour of the worse of the
// two rather than of the run that happens to have written the document.
//
// The rest of the line answers "what am I looking at" without scrolling: that this
// is the PAPER account (nothing here is real capital, which the word "live" quietly
// claims), the close the book is priced from, which account read is on the page and
// when it was taken, how old the document is on a clock a person keeps, and how many
// mismatches there are with the split between the explained ones and the rest.
//
// The age is the age of the document's latest write, which on a weekday morning is
// the account read rather than the book: the file is written by the evening and
// rewritten by the morning, and a page that aged it from `generated_at` alone called
// a file updated at 11:31 that morning three days old. So the strip names the run
// that made the latest write and puts the evening's own time beside it, and the age
// counts from the same instant the name does.
//
// The account read is a line of its own because it is the difference between "the
// intended book" and "the book the account holds": the evening reads the account
// before it sends anything, so an evening snapshot cannot certify the fills, and a
// morning snapshot can. A reader who mistakes the first for the second reads a
// plan as a position.

import { dateOnly, etDateTime, utcInstant } from "./format";
import { exceptionText, type Exceptions } from "./exceptions";
import { pillClass } from "./Panel";
import { ageText, freshness, type Reconciliation, type RunState, type Tone } from "./status";
import type { Snapshot } from "./types";

/** How the run that last wrote the document is named on the strip. */
const WRITER: Record<"evening" | "morning", string> = {
  evening: "the evening run",
  morning: "the morning run",
};

/**
 * The strip's own accent, one left edge for the two claims together.
 *
 * The pills say what each job did and are coloured one at a time; this says what
 * the pair of them amounts to, and it is the element a reader takes without
 * reading, so it takes the worse of the two. A strip that painted the proposal
 * pill with the reconciliation's colour would report a failed check as a failed
 * run, which is a different and more alarming claim.
 */
const ACCENT: Record<Tone, string> = {
  bad: "border-l-red-500",
  warn: "border-l-amber-400",
  info: "border-l-slate-400",
  good: "border-l-emerald-400",
};

/** How the account read is described: which run took it and what it can certify. */
function readLabel(snapshot: Snapshot): { text: string; note: string } | null {
  const read = snapshot.actual_holdings;
  if (!read) return null;
  const at = etDateTime(read.as_of) ?? "at an unrecorded time";
  if (read.read_by === "morning") {
    return {
      text: `account read ${at} (morning, after the fills)`,
      note: `the fills exist, so this compares what the account holds with the target${
        read.close ? ` for the ${dateOnly(read.close)} close` : ""
      }`,
    };
  }
  if (read.read_by === "evening") {
    return {
      text: `account read ${at} (evening, before the orders)`,
      note: "taken before the orders went out, so it cannot certify the fills",
    };
  }
  return { text: `account read ${at}`, note: "no run recorded against this read" };
}

export function StatusStrip({
  snapshot,
  now,
  state,
  tone,
  reconciled,
  exceptions,
}: {
  snapshot: Snapshot;
  now: Date;
  state: RunState;
  /** The worse of the two claims, and the only thing the strip's own colour says. */
  tone: Tone;
  reconciled: Reconciliation;
  exceptions: Exceptions;
}) {
  const written = freshness(snapshot);
  const close = dateOnly(snapshot.target_close);
  const bookClose = dateOnly(snapshot.book_as_of);
  const staleBook = Boolean(bookClose && close && bookClose !== close);
  const reason = snapshot.book?.reason;
  const read = readLabel(snapshot);
  // The evening writes its snapshot before it sends its message, so the document
  // itself says `pending` on an evening whose email went out; the morning reads the
  // evening's own row and rewrites this field with what actually happened. Only a
  // failure is worth a line: `pending` is the writer's ordering and `sent` is the
  // ordinary case, and a strip that reports either on every clean evening is a strip
  // nobody reads.
  const notifyFailed = snapshot.run_status?.notify_status === "failed";

  return (
    <header
      data-strip="status"
      data-tone={tone}
      className={`rounded border border-slate-300 border-l-4 bg-white px-3 py-2 ${ACCENT[tone]}`}
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span
          data-pill="status"
          data-tone={state.tone}
          className={`rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${pillClass(
            state.tone,
          )}`}
        >
          proposal run: {state.pill}
        </span>
        <span
          data-pill="reconciliation"
          data-tone={reconciled.tone}
          data-reconciliation={reconciled.pass ? "pass" : "fail"}
          className={`rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${pillClass(
            reconciled.tone,
          )}`}
        >
          reconciliation:{" "}
          {reconciled.unresolved > 0
            ? `${reconciled.unresolved} unresolved`
            : reconciled.tone === "info"
              ? "not run"
              : "clean"}
        </span>
        <span data-flag="mode" className="font-medium">
          {snapshot.dry_run
            ? "DRY RUN: no orders are sent"
            : "PAPER: orders go to the paper account"}
        </span>
        <span data-flag="close" className="text-slate-600">
          close {close ?? "unknown"}
        </span>
        <span data-flag="exceptions" className="text-slate-600">
          {exceptionText(exceptions)}
        </span>
        <span data-flag="snapshot" className="text-slate-600">
          {written.at === null ? (
            "no write recorded on this document"
          ) : (
            <>
              updated by{" "}
              {written.by === null ? "a run that did not name itself" : WRITER[written.by]}{" "}
              {etDateTime(written.at) ?? close ?? "unknown"} ({ageText(written.at, now)})
              {written.by === "evening" || written.evening === null
                ? ""
                : `; the evening run wrote ${etDateTime(written.evening)}`}
            </>
          )}
        </span>
        <span data-flag="snapshot-utc" className="text-xs text-slate-500">
          {utcInstant(written.at) ?? "no write recorded"} UTC
          {written.by === "evening" || written.evening === null
            ? ""
            : ` (the evening's own ${utcInstant(written.evening)})`}
        </span>
      </div>
      {read ? (
        <p data-flag="account-read" className="mt-1 text-xs text-slate-600">
          {read.text} — {read.note}
        </p>
      ) : null}
      {notifyFailed ? (
        <p data-note="notify-failed" className="mt-1 text-sm font-medium text-amber-800">
          the owner was never told: the message for the {close ?? "last"} close failed to send
        </p>
      ) : null}
      {staleBook ? (
        <p data-note="older-book" className="mt-1 text-sm font-medium text-amber-800">
          the book is the {bookClose} close, not tonight&apos;s {close}: the run did not price
          tonight
        </p>
      ) : null}
      {snapshot.run_status?.catch_up ? (
        <p data-note="catch-up" className="mt-1 text-sm text-slate-600">
          catch-up run:{" "}
          {(snapshot.run_status.catch_up_sessions ?? [])
            .map((session) => dateOnly(session) ?? session)
            .join(", ")}
        </p>
      ) : null}
      {reason ? (
        <p data-note="no-book" className="mt-1 text-sm text-amber-800">
          no book: {reason}
        </p>
      ) : null}
      {snapshot.actual_holdings ? null : (
        // Said here rather than inside the drawer, because the drawer is shut by
        // default and a reader who cannot find the table has to be able to read
        // why: an empty table would say the account holds nothing.
        <p data-note="account" className="mt-1 text-sm text-slate-600">
          the account has not been read, so there is no actual holdings table
        </p>
      )}
    </header>
  );
}
