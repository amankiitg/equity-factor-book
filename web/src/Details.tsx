// The disclosure every "read this by choice" block now sits behind.
//
// The morning route is three questions in under thirty seconds, and a page that
// answers them answers them at scroll zero: everything that is a *diagnostic* - the
// derivation of a number, the full exposure table, the construction's own telemetry,
// the name-by-name tables - costs a reader scroll and attention without answering any
// of the three. It is not hidden: a `<details>` element is keyboard-reachable, opens
// without JavaScript state, prints open, and is findable by the browser's own
// in-page search when the reader knows what they are looking for.
//
// The summary always states what is inside and, where the number is what matters,
// carries it: "the full 499-name book before the floor — 100.0%" tells the reader the
// thing the collapsed row would have told them, so collapsing cannot hide a figure
// that would have changed their morning.

import type { ReactNode } from "react";

export function Details({
  hook,
  summary,
  children,
}: {
  /** A stable name for the tests and for anything reading the page mechanically. */
  hook: string;
  summary: ReactNode;
  children: ReactNode;
}) {
  return (
    <details data-details={hook} className="mt-2 rounded border border-slate-200 bg-slate-50">
      <summary className="cursor-pointer px-2 py-1 text-xs font-medium text-slate-700">
        {summary}
      </summary>
      <div className="px-2 pb-2">{children}</div>
    </details>
  );
}
