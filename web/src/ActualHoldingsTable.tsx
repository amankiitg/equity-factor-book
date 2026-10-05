// The account's own book, name by name, against the target it was sized from.
//
// The rows are the union of the two books, not the held book alone: a target name
// the account does not hold is the drift that matters most, and a held name the
// target has dropped is a leg that has not been closed. The default order is the
// largest absolute drift first, which puts both kinds at the top; every column
// sorts. A name's held weight is of the account's equity at the read and its target
// weight is of the book's own, which is the same denominator the sizing used, so the
// two are comparable column to column.

import { useMemo, useState } from "react";

import { dateOnly, dateTime, dollars, percent, signedPercent } from "./format";
import type { ActualHoldings, BookName } from "./types";

type SortKey = "ticker" | "side" | "held" | "heldDollars" | "target" | "targetDollars" | "drift";
type Direction = "asc" | "desc";

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
      drift:
        entry.weight === null || entry.weight === undefined
          ? null
          : entry.weight - (targetWeight ?? 0),
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

export function ActualHoldingsTable({
  actual,
  names,
  nav,
  query = "",
}: {
  actual: ActualHoldings;
  names: BookName[];
  nav: number | null;
  query?: string;
}) {
  const [sort, setSort] = useState<{ key: SortKey; direction: Direction }>({
    key: "drift",
    direction: "desc",
  });

  const rows = useMemo(() => rowsOf(actual, names, nav), [actual, names, nav]);
  const shown = useMemo(() => {
    const needle = query.trim().toUpperCase();
    const filtered = rows.filter(
      (row) => needle === "" || row.ticker.toUpperCase().includes(needle),
    );
    return [...filtered].sort((a, b) => {
      const left = sortValue(a, sort.key);
      const right = sortValue(b, sort.key);
      const order =
        typeof left === "number" && typeof right === "number"
          ? left - right
          : String(left).localeCompare(String(right));
      if (order !== 0) return sort.direction === "asc" ? order : -order;
      return a.ticker.localeCompare(b.ticker);
    });
  }, [rows, query, sort]);

  // The two gaps, each counted on its own: a target name the account does not hold
  // is a leg that did not fill, and a held name the target has dropped is a leg that
  // has not been closed. One number for both would be neither.
  const notHeld = rows.filter((row) => !row.held).length;
  const notInTarget = rows.filter((row) => row.held && row.targetWeight === null).length;
  const session = actual.close ? ` for the ${dateOnly(actual.close)} close` : "";
  const when = dateTime(actual.as_of);

  const header = (key: SortKey, label: string) => (
    <th
      className="py-1 text-right"
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
              : { key, direction: key === "side" ? "asc" : "desc" },
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
    <div>
      <p className="text-sm text-slate-600" data-actual="read">
        {/* The read time as a date and a time: the evening's read and the
            morning's are hours apart, and which one this is decides whether the
            fills beside it can exist at all. */}
        {when === null
          ? "read time not recorded"
          : `read at ${when}${actual.read_by ? `, at the ${actual.read_by} run` : ""}`}
        {session}.
      </p>
      <p className="text-sm text-slate-600" data-actual="unheld">
        {notHeld === 0 && notInTarget === 0
          ? `every one of the target book's ${names.length} name(s) is held`
          : `${notHeld} of the target book's ${names.length} name(s) are not held, and ${notInTarget} held name(s) are not in the target book`}
      </p>
      <p className="text-xs text-slate-500" data-count="shown">
        showing {shown.length} of {rows.length}
      </p>
      <div className="overflow-x-auto">
        <table
          className="w-full min-w-[44rem] border-collapse text-sm"
          aria-label="actual holdings"
        >
          <thead>
            <tr className="border-b border-slate-300">
              <th className="py-1 text-left">
                <button
                  type="button"
                  data-sort="ticker"
                  onClick={() =>
                    setSort((current) =>
                      current.key === "ticker"
                        ? {
                            key: "ticker",
                            direction: current.direction === "asc" ? "desc" : "asc",
                          }
                        : { key: "ticker", direction: "asc" },
                    )
                  }
                  className="w-full text-left font-semibold underline decoration-dotted underline-offset-2"
                >
                  ticker
                  {sort.key === "ticker" ? (sort.direction === "asc" ? " ↑" : " ↓") : ""}
                </button>
              </th>
              {header("side", "side")}
              {header("held", "held weight")}
              {header("heldDollars", "held $")}
              {header("target", "target weight")}
              {header("targetDollars", "target $")}
              {header("drift", "drift")}
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
                <td className="py-1 text-right">{row.side}</td>
                <td className="py-1 text-right font-mono tabular-nums">
                  {row.held ? percent(row.heldWeight) : "not held"}
                </td>
                <td className="py-1 text-right font-mono tabular-nums">
                  {dollars(row.heldDollars)}
                </td>
                <td className="py-1 text-right font-mono tabular-nums">
                  {percent(row.targetWeight)}
                </td>
                <td className="py-1 text-right font-mono tabular-nums">
                  {dollars(row.targetDollars)}
                </td>
                <td className="py-1 text-right font-mono tabular-nums">
                  {signedPercent(row.drift)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
