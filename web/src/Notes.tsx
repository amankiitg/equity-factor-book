// The page's notes, kept in one drawer on the Operations tab.
//
// Three kinds of writing used to sit in the middle of the reading sections: how the
// attribution terms are built, the dated corrections that moved a series, and the
// reminder that a short live window cannot judge the risk model. None of them is a
// number the morning reader acts on, and each of them pushed the numbers down the
// page. They live here now, behind one disclosure, where the reader who wants the
// derivation or the change log can find all of it in one place.

import { Details } from "./Details";
import { count, dateOnly } from "./format";
import type { Snapshot } from "./types";

function Section({
  hook,
  title,
  children,
}: {
  hook: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section data-note-section={hook}>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <div className="mt-1 flex flex-col gap-1">{children}</div>
    </section>
  );
}

/** The method, the corrections and the caveats, in one drawer. */
export function Notes({ snapshot }: { snapshot: Snapshot }) {
  const attribution = snapshot.attribution;
  const live = attribution?.live;
  const notes = attribution?.notes ?? [];
  const backtestNote = attribution?.backtest?.note ?? null;
  const pairs = (live?.daily ?? []).filter(
    (day) => day.realized_vol !== null && day.realized_vol !== undefined
      && day.forecast_vol !== null && day.forecast_vol !== undefined,
  );
  return (
    <div data-notes-panel="true" className="flex flex-col gap-3 text-xs text-slate-600">
      <Section hook="method" title="how the four terms are computed">
        <p>
          Every row is stored by the evening run: factor P&amp;L is the book&apos;s exposure times
          the factor returns, idio P&amp;L is its positions times the specific returns, and the
          four terms sum to the day&apos;s total by construction. A row that does not add up is a
          stored day that does not decompose, which is what the check column in the table is for.
          The fourth term is not a fourth estimate: it is the stored artifacts disagreeing with the
          panel&apos;s own return, and on the live book it is a few hundredths of a bp.
        </p>
        {attribution?.note ? <p>{attribution.note}</p> : null}
        <p>
          <span className="font-medium">the research panel:</span> this is a backtest of the seed
          book, not the live book. Nobody traded it, so its cost is exactly zero, and its fourth
          term is a research-vintage mismatch rather than a loss anyone took.
        </p>
        {backtestNote ? (
          <p>
            <span className="font-medium">the research panel:</span> {backtestNote}
          </p>
        ) : null}
      </Section>

      <Section hook="corrections" title="corrections to the series">
        {notes.length === 0 ? (
          <p>no correction has been recorded for this document.</p>
        ) : (
          <ol data-notes="true" className="space-y-1" aria-label="notes on these charts">
            {notes.map((note, index) => (
              <li
                key={`${note.date ?? "undated"}-${index}`}
                data-note={dateOnly(note.date) ?? ""}
                className="flex gap-1"
              >
                <span className="mt-px inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-slate-600 text-[10px] text-white">
                  {index + 1}
                </span>
                <span>
                  <span className="font-medium">{dateOnly(note.date) ?? "undated"}</span>{" "}
                  {note.text}
                </span>
              </li>
            ))}
          </ol>
        )}
      </Section>

      <Section hook="sample-size" title="sample size">
        <p>
          {count(pairs.length)} session(s) is not enough to judge the model: E11&apos;s risk test
          wants thirty live days before a bias band means anything, and a page that drew a verdict
          on seven would be inventing one.
        </p>
      </Section>
    </div>
  );
}

/** The drawer the Operations tab opens: a summary that says what is inside it. */
export function NotesDrawer({ snapshot }: { snapshot: Snapshot }) {
  return (
    <Details hook="notes" summary="Notes: method, corrections and sample size">
      <Notes snapshot={snapshot} />
    </Details>
  );
}
