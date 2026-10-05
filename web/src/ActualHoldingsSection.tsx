// The account's own book, beside the target book it was sized from.
//
// The book above this section is what the run intended to hold; this is what the
// account actually holds, read from the broker by the evening run before it sized
// and rewritten by the next morning's reconciliation with what the orders did. It
// sits near the top because it is the one section on the page that reports the
// account rather than a proposal, and because a book the loop believes it holds
// and the account does not is the failure that makes every number below it wrong.
//
// The table is the union of the two books, not the held book alone: a target name
// the account does not hold is the drift that matters most, and a held name the
// target has dropped is the leg that did not close. The default order is the
// largest absolute drift first, which puts both kinds at the top; every column
// sorts, on the same pattern as the holdings table below.
//
// A name's held weight is of the account's equity at the read and its target
// weight is of the book's own, which is the same denominator the sizing used, so
// the two are comparable column to column.

import { useMemo, useState } from "react";

import { count, dateOnly, dateTime, dollars, percent, signedPercent } from "./format";
import type { ActualHoldings, BookName } from "./types";

type SortKey = "ticker" | "side" | "held" | "heldDollars" | "target" | "targetDollars" | "drift";
type Direction = "asc" | "desc";

/** The miss lines the section is willing to show before it counts the rest. */
const MISS_LINES = 3;

interface Row {
  ticker: string;
  side: string;
  held: boolean;
  heldWeight: number | null;
  heldDollars: number | null;
  targetWeight: number | null;
  targetDollars: number | null;
  drift: number | null;
}

/** The rows: the held book, plus the target names the account does not hold. */
function rowsOf(actual: ActualHoldings, names: BookName[], nav: number | null): Row[] {
  const target = new Map<string, number | null>();
  for (const name of names) target.set(name.ticker, name.weight ?? null);
  const rows: Row[] = [];
  const seen = new Set<string>();
  for (const entry of actual.names) {
    seen.add(entry.ticker);
    const targetWeight = target.has(entry.ticker) ? target.get(entry.ticker) ?? null : null;
    rows.push({
      ticker: entry.ticker,
      side: entry.side ?? "",
      held: true,
      heldWeight: entry.weight ?? null,
      heldDollars: entry.notional ?? null,
      targetWeight,
      targetDollars: targetWeight === null || nav === null ? null : targetWeight * nav,
      drift: entry.weight === null || entry.weight === undefined ? null : entry.weight - (targetWeight ?? 0),
    });
  }
  for (const name of names) {
    if (seen.has(name.ticker)) continue;
    const targetWeight = name.weight ?? null;
    rows.push({
      ticker: name.ticker,
      side: name.side ?? "",
      held: false,
      heldWeight: null,
      heldDollars: null,
      targetWeight,
      targetDollars: targetWeight === null || nav === null ? null : targetWeight * nav,
      drift: targetWeight === null ? null : -targetWeight,
    });
  }
  return rows;
}

function sortValue(row: Row, key: SortKey): string | number {
  switch (key) {
    case "ticker":
      return row.ticker;
    case "side":
      return row.side;
    case "held":
      return Math.abs(row.heldWeight ?? 0);
    case "heldDollars":
      return Math.abs(row.heldDollars ?? 0);
    case "target":
      return Math.abs(row.targetWeight ?? 0);
    case "targetDollars":
      return Math.abs(row.targetDollars ?? 0);
    case "drift":
      return Math.abs(row.drift ?? 0);
  }
}

/** One line for the fills behind the held book, or why there is none. */
function fillsLine(actual: ActualHoldings): string {
  const fills = actual.fills;
  if (!fills) {
    // The evening's read happens before the orders go out, so no fill exists yet.
    // Saying "0 filled" would read as a day on which nothing traded.
    return actual.read_by === "evening"
      ? "none to reconcile yet, the account was read before the orders went out"
      : "not reconciled";
  }
  const parts = [
    `${count(fills.n_filled)} filled`,
    `${count(fills.n_unfilled)} did not fill`,
    `${count(fills.not_sent)} never sent`,
  ];
  const realized =
    fills.realized_cost_bps === null || fills.realized_cost_bps === undefined
      ? "realized cost not priced"
      : `realized ${fills.realized_cost_bps.toFixed(2)} bps of NAV`;
  const expected =
    fills.expected_cost_bps === null || fills.expected_cost_bps === undefined
      ? ""
      : ` against ${fills.expected_cost_bps.toFixed(2)} expected`;
  return `${parts.join(", ")}, ${realized}${expected}`;
}

export function ActualHoldingsSection({
  actual,
  names,
  nav,
}: {
  actual?: ActualHoldings | null;
  names: BookName[];
  nav: number | null;
}) {
  const [sort, setSort] = useState<{ key: SortKey; direction: Direction }>({
    key: "drift",
    direction: "desc",
  });

  const rows = useMemo(() => (actual ? rowsOf(actual, names, nav) : []), [actual, names, nav]);
  const shown = useMemo(() => {
    const ordered = [...rows].sort((a, b) => {
      const left = sortValue(a, sort.key);
      const right = sortValue(b, sort.key);
      const order =
        typeof left === "number" && typeof right === "number"
          ? left - right
          : String(left).localeCompare(String(right));
      if (order !== 0) return sort.direction === "asc" ? order : -order;
      return a.ticker.localeCompare(b.ticker);
    });
    return ordered;
  }, [rows, sort]);

  // One line, and nothing else, when nobody has read the account: the page must
  // say that rather than draw an empty table, which would read as an account
  // holding nothing.
  if (!actual) {
    return (
      <section data-section="actual-holdings">
        <h2 className="text-lg font-semibold">Actual holdings</h2>
        <p className="text-sm text-slate-600" data-actual="absent">
          the account has not been read, so there is no actual book to show
        </p>
      </section>
    );
  }

  const longDollars = actual.names
    .filter((entry) => (entry.notional ?? 0) > 0)
    .reduce((total, entry) => total + (entry.notional ?? 0), 0);
  const shortDollars = actual.names
    .filter((entry) => (entry.notional ?? 0) < 0)
    .reduce((total, entry) => total - (entry.notional ?? 0), 0);
  // The two gaps, each counted on its own: a target name the account does not hold
  // is a leg that did not fill, and a held name the target has dropped is a leg
  // that has not been closed. Reporting one number for both would be neither.
  const notHeld = rows.filter((row) => !row.held).length;
  const notInTarget = rows.filter((row) => row.held && row.targetWeight === null).length;
  const session =
    actual.close === null || actual.close === undefined
      ? ""
      : `, for the ${dateOnly(actual.close)} close`;
  const when = dateTime(actual.as_of);

  const header = (key: SortKey, label: string, align = "left") => (
    <th
      className={`py-1 ${align === "right" ? "text-right" : "text-left"}`}
      aria-sort={
        sort.key === key ? (sort.direction === "asc" ? "ascending" : "descending") : "none"
      }
    >
      <button
        type="button"
        data-sort={key}
        onClick={() =>
          setSort((current) =>
            current.key === key
              ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
              : {
                  key,
                  direction:
                    key === "ticker" || key === "side" ? "asc" : "desc",
                },
          )
        }
        className="w-full font-semibold underline decoration-dotted underline-offset-2"
      >
        {label}
        {sort.key === key ? (sort.direction === "asc" ? " ↑" : " ↓") : ""}
      </button>
    </th>
  );

  return (
    <section data-section="actual-holdings">
      <h2 className="text-lg font-semibold">
        Actual holdings: {actual.n_names} name{actual.n_names === 1 ? "" : "s"}
      </h2>
      <p className="text-sm text-slate-600">
        {when === null
          ? "read time not recorded"
          : `read at ${when}${actual.read_by ? `, at the ${actual.read_by} run` : ""}`}
        {session}
      </p>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 text-sm text-slate-600">
        <dt className="font-medium">long gross</dt>
        <dd>{dollars(longDollars)}</dd>
        <dt className="font-medium">short gross</dt>
        <dd>{dollars(shortDollars)}</dd>
        <dt className="font-medium">net</dt>
        <dd>{dollars(actual.net_notional)}</dd>
        <dt className="font-medium">fills</dt>
        <dd data-fills="summary">{fillsLine(actual)}</dd>
      </dl>
      {actual.fills?.unfilled?.length ? (
        <ul className="mt-1 text-sm text-amber-800" data-fills="misses">
          {actual.fills.unfilled.slice(0, MISS_LINES).map((line) => (
            <li key={line}>{line}</li>
          ))}
          {actual.fills.unfilled.length > MISS_LINES ? (
            <li>and {actual.fills.unfilled.length - MISS_LINES} more</li>
          ) : null}
        </ul>
      ) : null}
      <p className="mt-1 text-sm text-slate-600" data-actual="unheld">
        {notHeld === 0 && notInTarget === 0
          ? `every one of the target book's ${names.length} name(s) is held`
          : `${notHeld} of the target book's ${names.length} name(s) are not held, and ${notInTarget} held name(s) are not in the target book`}
      </p>
      {/* Collapsed, like the full holdings table below and for the same reason:
          the two books together are hundreds of rows, and this section sits above
          the book it is read against. The default order inside is the largest
          absolute drift first, so the open table answers "what differs" rather
          than listing the book again. */}
      <details data-actual="table" className="mt-2 rounded border border-slate-200 bg-white">
        <summary className="cursor-pointer px-3 py-2 font-semibold">
          The name-by-name detail ({shown.length} row{shown.length === 1 ? "" : "s"}), sortable
        </summary>
        <div className="overflow-x-auto px-3 pb-3">
          <table className="mt-2 w-full min-w-[44rem] border-collapse text-sm" aria-label="actual holdings">
            <thead>
              <tr className="border-b border-slate-300">
                {header("ticker", "ticker")}
                {header("side", "side")}
                {header("held", "held weight", "right")}
                {header("heldDollars", "held $", "right")}
                {header("target", "target weight", "right")}
                {header("targetDollars", "target $", "right")}
                {header("drift", "drift", "right")}
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr
                  key={row.ticker}
                  data-ticker={row.ticker}
                  data-held={row.held ? "true" : "false"}
                  className={`border-b border-slate-100 ${row.held ? "" : "bg-slate-50"}`}
                >
                  <td className="py-1 font-mono">{row.ticker}</td>
                  <td className="py-1">{row.side}</td>
                  <td className="py-1 text-right tabular-nums">
                    {row.held ? percent(row.heldWeight) : "not held"}
                  </td>
                  <td className="py-1 text-right tabular-nums">{dollars(row.heldDollars)}</td>
                  <td className="py-1 text-right tabular-nums">{percent(row.targetWeight)}</td>
                  <td className="py-1 text-right tabular-nums">{dollars(row.targetDollars)}</td>
                  <td className="py-1 text-right tabular-nums">{signedPercent(row.drift)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
