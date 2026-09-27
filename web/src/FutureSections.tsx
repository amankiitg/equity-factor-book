// The two sections the snapshot cannot feed yet, and the rule they follow.
//
// Each one renders only when the run has written the data it needs, and hides
// itself otherwise. An empty section is worse than a missing one: it says the
// answer is nothing rather than that the question was not asked. The page never
// fills the gap with a zero, and the shape each one waits for is in
// `docs/snapshot.schema.json` so the cron's writer has a contract rather than a
// guess.

import { signedDollars, dateOnly, percent } from "./format";
import { sectorNameFor } from "./sectors";
import type { SessionMovers, Snapshot } from "./types";

/** The names carrying the most of the book's predicted specific variance. */
export function RiskConcentration({ snapshot }: { snapshot: Snapshot }) {
  const shares = snapshot.risk?.concentration ?? [];
  if (shares.length === 0) return null;
  const cap = snapshot.risk?.variance_share_cap ?? null;
  const largest = Math.max(...shares.map((entry) => entry.share), cap ?? 0, 0.0001);
  const scale = largest * 1.05;

  return (
    <section data-section="risk" className="rounded border border-slate-200 bg-white p-3">
      <h2 className="text-lg font-semibold">Risk concentration</h2>
      <p className="mt-1 text-sm text-slate-600">
        Each name's share of the book's predicted specific variance, largest first
        {cap === null ? "" : `, against the ${percent(cap, 0)} cap`}.
      </p>
      <div className="mt-2">
        {shares.map((entry) => (
          <div
            key={entry.ticker}
            data-concentration={entry.ticker}
            className="grid grid-cols-[5rem_1fr_4rem] items-center gap-x-3 border-b border-slate-100 py-1.5"
          >
            <span className="font-mono">{entry.ticker}</span>
            <span className="relative h-3 w-full rounded-sm bg-slate-100">
              <span
                data-share="name"
                className={`absolute left-0 top-0 h-full rounded-sm ${
                  cap !== null && entry.share > cap ? "bg-amber-500" : "bg-sky-600"
                }`}
                style={{ width: `${Math.min(100, (entry.share / scale) * 100)}%` }}
              />
              {cap === null ? null : (
                <span
                  data-cap-line="true"
                  title={`the cap, ${percent(cap, 0)}`}
                  className="absolute top-[-2px] h-[16px] border-l-2 border-dashed border-rose-600"
                  style={{ left: `${Math.min(100, (cap / scale) * 100)}%` }}
                />
              )}
            </span>
            <span className="text-right text-sm tabular-nums">{percent(entry.share)}</span>
          </div>
        ))}
      </div>
      {cap === null ? null : (
        <p className="mt-1 text-xs text-slate-500">
          The dashed line is the cap the sizing applies. A name at or over it was cut back to it,
          which moves the rest of its risk into the other names rather than removing it.
        </p>
      )}
    </section>
  );
}

function Group({ title, rows }: { title: string; rows: Array<{ label: string; value: number }> }) {
  return (
    <div data-movers={title}>
      <h3 className="text-base font-semibold">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-500">none</p>
      ) : (
        <ul className="mt-1 text-sm">
          {rows.map((row) => (
            <li
              key={row.label}
              data-contributor={row.label}
              className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1"
            >
              <span className="font-mono">{row.label}</span>
              <span
                className={`tabular-nums ${
                  row.value >= 0 ? "text-emerald-700" : "text-rose-700"
                }`}
              >
                {signedDollars(row.value)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Sector contributions summed from the names, for a run that sends only names.
 *
 * The page already carries the ticker-to-GICS map, so the sector view of a
 * session's P&L is a sum rather than a second thing for the cron to write. A run
 * that sends its own `by_sector` (the model's own sector labels) keeps it.
 */
function deriveSectors(
  rows: Array<{ ticker: string; contribution: number }>,
): Array<{ sector: string; contribution: number }> {
  const totals = new Map<string, number>();
  for (const row of rows) {
    const key = sectorNameFor(row.ticker);
    totals.set(key, (totals.get(key) ?? 0) + row.contribution);
  }
  return [...totals.entries()].map(([sector, contribution]) => ({ sector, contribution }));
}

/** What moved the book in the latest session, by name and by sector. */
export function Movers({ snapshot }: { snapshot: Snapshot }) {
  const movers: SessionMovers | null | undefined = snapshot.movers;
  const byName = movers?.by_name ?? [];
  const sent = movers?.by_sector ?? [];
  const bySector = sent.length > 0 ? sent : deriveSectors(byName);
  if (byName.length === 0 && bySector.length === 0) return null;
type Contribution = { ticker?: string | null; sector?: string | null; contribution: number };

/** The five best and the five worst, without a row appearing in both lists. */
const split = (rows: Contribution[]): { up: Contribution[]; down: Contribution[] } => {
  const ranked = [...rows].sort((a, b) => b.contribution - a.contribution);
  const up = ranked.slice(0, 5);
  return { up, down: ranked.slice(up.length).slice(-5).reverse() };
};

const label = (row: Contribution): string => row.ticker ?? row.sector ?? "?";

  return (
    <section data-section="movers" className="rounded border border-slate-200 bg-white p-3">
      <h2 className="text-lg font-semibold">
        Movers{movers?.session ? `, ${dateOnly(movers.session)}` : ""}
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        Contribution to the session's P&L, in dollars. Shown only when the run has written its
        per-name attribution.
      </p>
      <div className="mt-2 grid gap-4 lg:grid-cols-2">
        <div className="grid gap-4 sm:grid-cols-2">
          <Group
            title="names, top five"
            rows={split(byName).up.map((row) => ({ label: label(row), value: row.contribution }))}
          />
          <Group
            title="names, bottom five"
            rows={split(byName).down.map((row) => ({ label: label(row), value: row.contribution }))}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Group
            title="sectors, top five"
            rows={split(bySector).up.map((row) => ({ label: label(row), value: row.contribution }))}
          />
          <Group
            title="sectors, bottom five"
            rows={split(bySector).down.map((row) => ({ label: label(row), value: row.contribution }))}
          />
        </div>
      </div>
    </section>
  );
}
