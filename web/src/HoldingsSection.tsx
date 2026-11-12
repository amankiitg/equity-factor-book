// The full book's table: one row per kept name, sortable on every column, filtered
// by sector and by the drawer's search box.
//
// It is the drawer's first tab rather than a section of the page, because 188 rows
// of detail on a screen whose job is to answer "does the book still look like the
// book" in one glance is a screen nobody reads. The default order is the snapshot's
// own: absolute weight, largest first. The weight column sorts on the absolute value,
// because a reader sorting "weight" is asking which positions matter, and a 5% short
// matters as much as a 5% long; the signed value is what the column prints.

import { useMemo, useState } from "react";

import { dollars, percent } from "./format";
import { UNMAPPED, sectorNameFor } from "./sectors";
import type { BookName, MonthlyBlock } from "./types";

type SortKey = "ticker" | "side" | "sector" | "weight" | "dollars" | "since";
type Direction = "asc" | "desc";

interface Row {
  name: BookName;
  sector: string;
  absolute: number;
}

export function HoldingsTable({
  names,
  nav,
  query = "",
  monthly = null,
}: {
  names: BookName[];
  nav: number | null;
  query?: string;
  monthly?: MonthlyBlock | null;
}) {
  const [sort, setSort] = useState<{ key: SortKey; direction: Direction }>({
    key: "weight",
    direction: "desc",
  });
  const [sector, setSector] = useState<string>("all");

  const rows = useMemo<Row[]>(
    () =>
      names.map((name) => ({
        name,
        sector: sectorNameFor(name.ticker),
        absolute: Math.abs(name.weight ?? 0),
      })),
    [names],
  );
  const since = useMemo(() => {
    const map = new Map<string, NonNullable<MonthlyBlock["holdings"]>["rows"][number]>();
    for (const row of monthly?.holdings?.rows ?? []) map.set(row.ticker, row);
    return map;
  }, [monthly]);
  const anchored = since.size > 0;

  const sectorsPresent = useMemo(
    () => [...new Set(rows.map((row) => row.sector))].sort(),
    [rows],
  );

  const shown = useMemo(() => {
    const needle = query.trim().toUpperCase();
    const filtered = rows.filter(
      (row) =>
        (sector === "all" || row.sector === sector) &&
        (needle === "" || (row.name.ticker ?? "").toUpperCase().includes(needle)),
    );
    const value = (row: Row): string | number => {
      switch (sort.key) {
        case "ticker":
          return row.name.ticker ?? "";
        case "side":
          return row.name.side ?? "";
        case "sector":
          return row.sector;
        case "since":
          return since.get(row.name.ticker ?? "")?.since ?? row.name.reason ?? "";
        case "weight":
        case "dollars":
          return row.absolute;
      }
    };
    return [...filtered].sort((a, b) => {
      const left = value(a);
      const right = value(b);
      const order =
        typeof left === "number" && typeof right === "number"
          ? left - right
          : String(left).localeCompare(String(right));
      return sort.direction === "asc" ? order : -order;
    });
  }, [rows, sector, query, sort, since]);

  if (names.length === 0) return null;

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
                    key === "ticker" || key === "sector" || key === "since" || key === "side"
                      ? "asc"
                      : "desc",
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
    <div data-section="holdings" data-holdings="true">
      <p className="pb-1 text-xs text-slate-500" data-how-to-read="true">
        how to read this: the since column names the last event that changed the
        name, so an entry at a rebuild and a repair by the guard read differently.
        Example: MRVL says drift guard leg (2026-10-30), so the guard moved it, not
        the rebuild. A hold day never resizes a name: BNY says held, guard leg under
        the minimum (2026-11-04) because the guard wanted a leg it could not size.
      </p>
      <div className="flex flex-wrap items-end gap-3 py-2">
        <label className="text-sm">
          <span className="block text-xs uppercase tracking-wide text-slate-500">sector</span>
          <select
            data-filter="sector"
            aria-label="sector filter"
            value={sector}
            onChange={(event) => setSector(event.target.value)}
            className="mt-1 rounded border border-slate-300 px-2 py-1"
          >
            <option value="all">all sectors</option>
            {sectorsPresent.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <p className="text-sm text-slate-600" data-count="shown">
          showing {shown.length} of {names.length}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] border-collapse text-sm" aria-label="the book">
          <thead>
            <tr className="border-b border-slate-300">
              {header("ticker", "ticker")}
              {header("side", "side")}
              {header("sector", "sector")}
              {header("weight", "weight", "right")}
              {header("dollars", "dollars", "right")}
              {anchored ? header("since", "since the rebalance") : header("since", "reason")}
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr
                key={row.name.ticker}
                data-ticker={row.name.ticker}
                className="border-b border-slate-100"
              >
                <td className="py-1 font-mono">{row.name.ticker}</td>
                <td className="py-1">{row.name.side}</td>
                <td className={`py-1 ${row.sector === UNMAPPED ? "text-slate-400" : ""}`}>
                  {row.sector}
                </td>
                <td className="py-1 text-right font-mono tabular-nums">
                  {percent(row.name.weight)}
                </td>
                <td className="py-1 text-right font-mono tabular-nums">
                  {dollars(nav === null ? null : row.absolute * nav)}
                </td>
                <td className="py-1 text-slate-600">
                  {anchored
                    ? since.get(row.name.ticker ?? "")?.since ?? "held, no trade since"
                    : row.name.reason ?? ""}
                  {anchored && since.get(row.name.ticker ?? "")?.tonight ? (
                    <span className="block text-xs text-slate-400">
                      {since.get(row.name.ticker ?? "")?.tonight}
                    </span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
