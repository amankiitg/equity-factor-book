// The detail drawer: the two tables, one search box, no rows on the page by default.
//
// The page above it answers "does the book look like the book" in one screen, and
// this holds the name-by-name detail that answering that question does not need: the
// full book, and the account's own book against the target it was sized from. It is
// closed until a tab is asked for, because 190 rows of book and 235 rows of drift
// would push the rest of the page off a laptop screen, and both tables sort as they
// did before.
//
// One search box rather than one per table: a reader looking for a name does not
// care which table it is in, and two boxes a few inches apart is how a page makes
// someone type in the wrong one. The box filters whichever tab is open.
//
// The actual-holdings tab opens on the largest absolute drift, which is what the
// section is for: the held names the target has dropped and the target names the
// account does not hold come to the top together, rather than being buried in a list
// ordered by size.

import { useState } from "react";

import { ActualHoldingsTable } from "./ActualHoldingsTable";
import { dateOnly } from "./format";
import { HoldingsTable } from "./HoldingsSection";
import type { BookFacts } from "./book";
import type { Snapshot } from "./types";

type Tab = "book" | "actual";

export function DrawerSection({
  snapshot,
  facts,
}: {
  snapshot: Snapshot;
  facts: BookFacts;
}) {
  const actual = snapshot.actual_holdings ?? null;
  const hasBook = facts.hasBook;
  const [tab, setTab] = useState<Tab | null>(null);
  const [query, setQuery] = useState("");

  if (!hasBook && !actual) return null;
  const first: Tab = hasBook ? "book" : "actual";
  const open: Tab = tab ?? first;
  const shown = tab === null ? null : tab;

  const bookClose = dateOnly(snapshot.book_as_of);
  const targetClose = dateOnly(snapshot.target_close);
  const dated = Boolean(bookClose && bookClose !== targetClose);
  const tabs: Array<{ key: Tab; label: string; present: boolean }> = [
    {
      key: "book",
      label: `The book: ${snapshot.book?.n_names ?? 0} name(s)${dated ? ` (as of ${bookClose})` : ""}`,
      present: hasBook,
    },
    {
      key: "actual",
      label: `Actual holdings: ${actual?.n_names ?? 0} name(s)`,
      present: actual !== null,
    },
  ];

  return (
    <section
      data-section="drawer"
      data-drawer={shown === null ? "closed" : "open"}
      className="rounded border border-slate-300 bg-white"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-slate-200 px-3 py-2">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="detail">
          {tabs
            .filter((entry) => entry.present)
            .map((entry) => (
              <button
                key={entry.key}
                type="button"
                role="tab"
                data-tab={entry.key}
                aria-selected={shown === entry.key}
                aria-expanded={shown === entry.key}
                onClick={() => setTab((current) => (current === entry.key ? null : entry.key))}
                className={`rounded px-2 py-1 text-sm font-semibold ${
                  shown === entry.key
                    ? "bg-slate-800 text-white"
                    : "bg-slate-100 text-slate-800 hover:bg-slate-200"
                }`}
              >
                {entry.label}
              </button>
            ))}
        </div>
        <label className="ml-auto flex items-center gap-2 text-sm">
          <span className="text-xs uppercase tracking-wide text-slate-500">find a name</span>
          <input
            data-search="ticker"
            aria-label="ticker search"
            type="search"
            value={query}
            placeholder="ticker"
            onChange={(event) => {
              setQuery(event.target.value);
              // Typing while the drawer is shut opens the first table: a search that
              // silently filters something nobody can see is a broken search.
              setTab((current) => current ?? first);
            }}
            className="w-32 rounded border border-slate-300 px-2 py-1 font-mono"
          />
        </label>
      </div>

      {shown === null ? (
        <p className="px-3 py-2 text-sm text-slate-600" data-drawer-hint="true">
          the two tables are closed, open one to read the names
        </p>
      ) : null}

      {shown === "book" ? (
        <div className="px-3 pb-3 pt-2">
          <HoldingsTable names={snapshot.book.names} nav={facts.nav} query={query} />
        </div>
      ) : null}

      {shown === "actual" && actual ? (
        <div className="px-3 pb-3 pt-2" data-section="actual-holdings">
          <ActualHoldingsTable
            actual={actual}
            names={snapshot.book?.names ?? []}
            nav={facts.nav}
            query={query}
          />
        </div>
      ) : null}
    </section>
  );
}
