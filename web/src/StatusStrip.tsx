// The top strip: one line that answers "what am I looking at" without scrolling.
//
// It carries the run's own state (the pill), whether anything is trading, when the
// snapshot was written and how old that is, the close the book is priced from, and
// whether the owner was told. The one line under it is the honest version of the
// most dangerous state the page has: a book that is not tonight's. A reader who
// misses that reads a stale book as a current one, so it is stated in words rather
// than left to a date they have to compare.

import { dateOnly, dateTime } from "./format";
import { ageText, type RunState } from "./status";
import { pillClass } from "./Panel";
import type { Snapshot } from "./types";

export function StatusStrip({
  snapshot,
  now,
  state,
}: {
  snapshot: Snapshot;
  now: Date;
  state: RunState;
}) {
  const generated = new Date(snapshot.generated_at);
  const close = dateOnly(snapshot.target_close);
  const bookClose = dateOnly(snapshot.book_as_of);
  const staleBook = Boolean(bookClose && close && bookClose !== close);
  const reason = snapshot.book?.reason;

  return (
    <header data-strip="status" className="rounded border border-slate-300 bg-white px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span
          data-pill="status"
          data-tone={state.tone}
          className={`rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${pillClass(
            state.tone,
          )}`}
        >
          {state.pill}
        </span>
        <span data-flag="mode" className="font-medium">
          {snapshot.dry_run ? "DRY RUN: no orders are sent" : "live"}
        </span>
        <span data-flag="snapshot" className="text-slate-600">
          snapshot generated{" "}
          {dateTime(snapshot.generated_at) ?? dateOnly(snapshot.generated_at) ?? "unknown"}
          {Number.isNaN(generated.getTime()) ? "" : ` (${ageText(generated, now)})`}
        </span>
        <span data-flag="close" className="text-slate-600">
          target close {close ?? "unknown"}
        </span>
        <span data-flag="notify" className="text-slate-600">
          notify {snapshot.run_status?.notify_status ?? "n/a"}
        </span>
      </div>
      {staleBook ? (
        <p data-note="older-book" className="mt-1 text-sm font-medium text-amber-800">
          the book is the {bookClose} close, not tonight's {close}: the run did not price
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
