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

import { HowToRead } from "./Panel";

import {
  dateOnly,
  dateTime,
  dollars,
  percent,
  shortSince,
  signedDollars,
  signedPercent,
} from "./format";
import type { ActualHoldings, BookName, MonthlyBlock, MonthlyHoldingRow } from "./types";

type SortKey =
  | "ticker"
  | "side"
  | "held"
  | "heldDollars"
  | "target"
  | "targetDollars"
  | "drift"
  | "gapDollars"
  | "since";
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
  gapDollars: number | null;
  since: string | null;
  sinceKind: string | null;
  sinceDate: string | null;
  sinceLabel: string | null;
  tonight: string | null;
  retired: boolean;
  /** The target book's own reason for the name, when it is in the target. */
  reason: string | null;
  /** The account read carried the name twice and the rows were merged into one. */
  flipped: boolean;
}

/** More means the account holds more than the target asked for, the sector panel's blue. */
function gapTone(gap: number | null): string {
  if (gap === null || Math.abs(gap) < 1e-9) return "";
  return gap > 0 ? "efb-gap-more" : "efb-gap-less";
}

function sideTone(side: string): string {
  if (side === "long") return "efb-side-long";
  if (side === "short") return "efb-side-short";
  return "efb-side-none";
}

/** The rows: the held book, plus the target names the account does not hold. */
function rowsOf(
  actual: ActualHoldings,
  names: BookName[],
  nav: number | null,
  monthlyRows: MonthlyHoldingRow[],
): Row[] {
  const target = new Map<string, number | null>();
  const reasons = new Map<string, string | null>();
  for (const name of names) {
    target.set(name.ticker, name.weight ?? null);
    reasons.set(name.ticker, name.reason ?? null);
  }
  const anchored = new Map<string, MonthlyHoldingRow>();
  for (const row of monthlyRows) anchored.set(row.ticker, row);
  // The broker can report one name as two rows: a closed short that has not left
  // the account yet and the new long that replaced it. The table is one row per
  // name, so the two are merged here and the merge is what the reason pill says.
  interface ReadRow {
    ticker: string;
    side: string;
    notional: number | null;
    weight: number | null;
    flipped: boolean;
  }
  const held = new Map<string, ReadRow>();
  for (const entry of actual.names) {
    const prior = held.get(entry.ticker);
    if (!prior) {
      held.set(entry.ticker, {
        ticker: entry.ticker,
        side: entry.side ?? "",
        notional: entry.notional ?? null,
        weight: entry.weight ?? null,
        flipped: false,
      });
      continue;
    }
    const flipped =
      prior.side !== "" && entry.side !== null && prior.side !== entry.side;
    prior.notional = (prior.notional ?? 0) + (entry.notional ?? 0);
    prior.weight = (prior.weight ?? 0) + (entry.weight ?? 0);
    prior.side = (prior.notional ?? 0) >= 0 ? "long" : "short";
    prior.flipped = prior.flipped || flipped;
  }
  const rows: Row[] = [];
  const seen = new Set<string>();
  for (const entry of held.values()) {
    seen.add(entry.ticker);
    const targetWeight = target.has(entry.ticker) ? target.get(entry.ticker) ?? null : null;
    const anchor = anchored.get(entry.ticker);
    const drift =
      entry.weight === null || entry.weight === undefined
        ? null
        : entry.weight - (targetWeight ?? 0);
    rows.push({
      ticker: entry.ticker,
      side: entry.side ?? "",
      held: true,
      heldWeight: entry.weight ?? null,
      heldDollars: entry.notional ?? null,
      targetWeight,
      targetDollars: targetWeight === null || nav === null ? null : targetWeight * nav,
      drift: anchor?.gap_weight ?? drift,
      gapDollars:
        anchor?.gap_usd ?? (drift === null || nav === null ? null : drift * nav),
      since:
        anchor?.since ??
        (entry.flipped ? "one row: a closed short and the new long" : null),
      sinceKind: anchor?.since_kind ?? (entry.flipped ? "flipped" : null),
      sinceDate: anchor?.since_date ?? null,
      sinceLabel: anchor?.since_label ?? (entry.flipped ? "Flipped" : null),
      tonight: anchor?.tonight ?? null,
      retired: anchor?.retired ?? false,
      reason: reasons.get(entry.ticker) ?? null,
      flipped: entry.flipped,
    });
  }
  for (const name of names) {
    if (seen.has(name.ticker)) continue;
    // One row per name: the target books both name this one, and the monthly row
    // comes from the anchor, so the name is marked here and its row is not drawn
    // twice. MKC is the live case: short in the 10-23 target, long in tonight's.
    seen.add(name.ticker);
    const targetWeight = name.weight ?? null;
    const anchor = anchored.get(name.ticker);
    // The anchor's target was the other side, so the name has flipped since it.
    const flippedTarget =
      anchor !== undefined &&
      anchor.weight_target !== 0 &&
      (name.weight ?? 0) !== 0 &&
      Math.sign(anchor.weight_target) !== Math.sign(name.weight ?? 0);
    rows.push({
      ticker: name.ticker,
      side: name.side ?? "",
      held: false,
      heldWeight: null,
      heldDollars: null,
      targetWeight,
      targetDollars: targetWeight === null || nav === null ? null : targetWeight * nav,
      drift: flippedTarget
        ? targetWeight === null
          ? null
          : -targetWeight
        : anchor?.gap_weight ?? (targetWeight === null ? null : -targetWeight),
      gapDollars: flippedTarget
        ? targetWeight === null || nav === null
          ? null
          : -targetWeight * nav
        : anchor?.gap_usd ??
          (targetWeight === null || nav === null ? null : -targetWeight * nav),
      since: flippedTarget
        ? `flipped since the rebalance: the target was ${(anchor?.weight_target ?? 0) < 0 ? "short" : "long"}`
        : anchor?.since ?? null,
      sinceKind: flippedTarget ? "flipped" : anchor?.since_kind ?? null,
      sinceDate: anchor?.since_date ?? null,
      sinceLabel: flippedTarget ? "Flipped" : anchor?.since_label ?? null,
      tonight: anchor?.tonight ?? null,
      retired: anchor?.retired ?? false,
      reason: name.reason ?? null,
      flipped: flippedTarget,
    });
  }
  for (const row of monthlyRows) {
    if (seen.has(row.ticker)) continue;
    rows.push({
      ticker: row.ticker,
      side: row.weight_now < 0 ? "short" : row.weight_now > 0 ? "long" : "",
      held: Math.abs(row.weight_now) > 0,
      heldWeight: row.weight_now,
      heldDollars: nav === null ? null : row.weight_now * nav,
      targetWeight: row.weight_target,
      targetDollars: nav === null ? null : row.weight_target * nav,
      drift: row.gap_weight,
      gapDollars: row.gap_usd,
      since: row.since,
      sinceKind: row.since_kind,
      sinceDate: row.since_date,
      sinceLabel: row.since_label ?? null,
      tonight: row.tonight,
      retired: row.retired,
      reason: row.note ?? reasons.get(row.ticker) ?? null,
      flipped: false,
    });
  }
  return rows;
}

/**
 * What the table's header counts: the names the account holds, and the names it held
 * at the rebalance and has since exited.
 *
 * The header used to print the account read's own row count, which is not the row
 * count of the table under it: the table is the held book plus the names the target
 * wants and the account does not hold, and a header that counts one of those is a
 * claim the rows beside it contradict.
 */
export function actualCounts(
  actual: ActualHoldings,
  names: BookName[],
  monthlyRows: MonthlyHoldingRow[],
): { held: number; exited: number } {
  const rows = rowsOf(actual, names, null, monthlyRows);
  return {
    held: rows.filter((row) => row.held).length,
    exited: rows.filter((row) => !row.held && row.sinceKind === "exited").length,
  };
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
    case "gapDollars":
      return Math.abs(row.gapDollars ?? 0);
    case "since":
      return row.since ?? "";
  }
}

export function ActualHoldingsTable({
  actual,
  names,
  nav,
  query = "",
  monthly = null,
}: {
  actual: ActualHoldings;
  names: BookName[];
  nav: number | null;
  query?: string;
  monthly?: MonthlyBlock | null;
}) {
  const [sort, setSort] = useState<{ key: SortKey; direction: Direction }>({
    key: "drift",
    direction: "desc",
  });
  // A phone shows the four columns that answer the question and keeps the rest
  // one tap away. On a wide screen every column is shown and the toggle is hidden.
  const [allColumns, setAllColumns] = useState(false);

  const rows = useMemo(
    () => rowsOf(actual, names, nav, monthly?.holdings?.rows ?? []),
    [actual, names, nav, monthly],
  );
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

  const optional = allColumns ? "" : "hidden sm:table-cell";
  const header = (key: SortKey, label: string, extra = "", width = "") => (
    <th
      className={`py-1 text-right ${extra}`}
      style={width ? { width } : undefined}
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
      <HowToRead>
        a minus gap means the account holds less of that name than the target asked
        for, at today&apos;s price, and the size of the gap is what the next rebuild
        would trade. Example: on 11-11 NVDA sat $3,919 away from its target, the
        largest single gap in the book.
      </HowToRead>
      <p className="text-sm text-slate-600" data-actual="read">
        {/* The read time as a date and a time: the evening's read and the
            morning's are hours apart, and which one this is decides whether the
            fills beside it can exist at all. */}
        {when === null
          ? "read time not recorded"
          : `read at ${when}${actual.read_by ? `, at the ${actual.read_by} run` : ""}`}
        {session}.
      </p>
      <div className="text-sm text-slate-600" data-actual="unheld">
        {notHeld === 0 && notInTarget === 0 ? (
          `every one of the target book's ${names.length} name(s) is held`
        ) : notHeld === 0 ? (
          `every one of the target book's ${names.length} name(s) is held, and ${notInTarget} held name(s) are not in the target book`
        ) : (
          <details data-unheld-list="true">
            <summary className="cursor-pointer underline decoration-dotted underline-offset-2">
              {notHeld} of the target book&apos;s {names.length} name(s) are not held
            </summary>
            <ul className="mt-1 flex flex-col gap-0.5 text-xs">
              {rows
                .filter((row) => !row.held)
                .map((row) => (
                  <li key={row.ticker} data-unheld={row.ticker}>
                    <span className="font-mono font-semibold">{row.ticker}</span>{" "}
                    {row.reason ?? row.since ?? row.tonight ?? "no reason recorded"}
                  </li>
                ))}
            </ul>
            {notInTarget > 0 ? (
              <p className="mt-1 text-xs text-slate-500">
                {notInTarget} held name(s) are not in the target book either.
              </p>
            ) : null}
          </details>
        )}
      </div>
      <p className="text-xs text-slate-500" data-count="shown">
        showing {shown.length} of {rows.length}
      </p>
      <div className="flex items-center justify-between gap-2 pb-1 sm:hidden">
        <p className="text-xs text-slate-500">ticker, side, gap and reason; tap for the rest</p>
        <button
          type="button"
          data-columns-toggle="true"
          aria-expanded={allColumns}
          onClick={() => setAllColumns((open) => !open)}
          className="shrink-0 rounded border border-slate-300 px-2 py-1 text-xs text-slate-700"
        >
          {allColumns ? "fewer columns" : "all columns"}
        </button>
      </div>
      <div className="efb-table-scroll">
        <table className="efb-table w-full text-sm sm:min-w-[56rem]" aria-label="actual holdings">
          <thead>
            <tr className="border-b border-slate-300">
              <th className="py-1 text-left" style={{ width: "5.5rem" }}>
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
              {header("side", "side", "", "3.5rem")}
              {header("held", "held weight", optional, "6rem")}
              {header("heldDollars", "held $", optional, "6.5rem")}
              {header("target", "target weight", optional, "6.5rem")}
              {header("targetDollars", "target $", optional, "6.5rem")}
              {header("drift", "gap %", optional, "5.5rem")}
              {header("gapDollars", "gap $", "", "6.5rem")}
              {header("since", "since the rebalance", "efb-since", "11rem")}
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => {
              const label = shortSince(row.sinceKind, row.sinceDate, row.sinceLabel) || row.since || "";
              const compact = label !== "" && label !== row.since;
              const tone = gapTone(row.drift);
              return (
                <tr
                  key={row.ticker}
                  data-ticker={row.ticker}
                  data-held={row.held ? "true" : "false"}
                  data-retired={row.retired ? "true" : "false"}
                  className={`border-b border-slate-100 ${row.held ? "" : "bg-slate-50"}`}
                >
                  <td className="py-1 font-mono font-semibold">{row.ticker}</td>
                  <td className="py-1 text-right">
                    {row.side ? (
                      <span
                        className={`efb-side ${sideTone(row.side)}`}
                        data-side-badge={row.side}
                      >
                        {row.side}
                      </span>
                    ) : null}
                  </td>
                  <td className={`py-1 text-right font-mono tabular-nums ${optional}`}>
                    {row.held ? percent(row.heldWeight) : "not held"}
                  </td>
                  <td className={`py-1 text-right font-mono tabular-nums ${optional}`}>
                    {dollars(row.heldDollars)}
                  </td>
                  <td className={`py-1 text-right font-mono tabular-nums ${optional}`}>
                    {percent(row.targetWeight)}
                  </td>
                  <td className={`py-1 text-right font-mono tabular-nums ${optional}`}>
                    {dollars(row.targetDollars)}
                  </td>
                  <td className={`py-1 text-right font-mono tabular-nums ${tone} ${optional}`}>
                    {signedPercent(row.drift)}
                  </td>
                  <td className={`py-1 text-right font-mono tabular-nums ${tone}`}>
                    {signedDollars(row.gapDollars)}
                    {/* The phone keeps one gap column; the percentage rides under the dollars. */}
                    <span className="mt-0.5 block text-xs sm:hidden">{signedPercent(row.drift)}</span>
                  </td>
                  <td className="efb-since py-1 text-slate-600">
                    {compact ? <span className="sr-only">{row.since}</span> : null}
                    {label ? (
                      <span
                        className="efb-pill"
                        aria-hidden={compact || undefined}
                        title={row.since ?? undefined}
                      >
                        {label}
                      </span>
                    ) : null}
                    {row.tonight ? (
                      <span className="mt-0.5 block text-xs text-slate-400">{row.tonight}</span>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
