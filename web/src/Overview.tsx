// The PM-first overview: the answer to "how is the book doing" in one screen.
//
// The page used to open on the book monitor, which is the right page for someone
// checking the loop and the wrong one for someone checking the book. This tab is
// the second reader: the strategy in one sentence, the four numbers that say how
// it is going, a banner that only appears when something needs a person, and three
// pictures that show the shape of the P&L and the risk. Everything diagnostic stays
// behind the other tabs.
//
// The charts are drawn by hand in SVG. The page has no chart library, and three
// small plots do not justify one. Colour always carries a second cue: a legend
// entry, a sign, or a written label, so the picture is not the only place a number
// is stated.

import { useLayoutEffect, useRef, useState } from "react";

import type { Exceptions } from "./exceptions";
import { dollars, percent, pnlClass, signedDollars } from "./format";
import { InfoIcon } from "./Panel";
import { sectorLabel } from "./sectors";
import type { Reconciliation, RunState, Tone } from "./status";
import { freshness, ageText } from "./status";
import { etDateTime } from "./format";
import type { AttributionDay, MonthlyBlock, Snapshot } from "./types";

/** A short explanation behind the (i) beside a title. */
export function Info({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block align-middle" data-how-to-read="true">
      <button
        type="button"
        aria-label={`about ${title}`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="ml-1.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
      >
        <InfoIcon />
      </button>
      {open ? (
        <span
          role="dialog"
          aria-label={`about ${title}`}
          data-info={title}
          className="absolute left-0 top-5 z-20 w-72 rounded border border-slate-300 bg-white p-2 text-xs font-normal normal-case tracking-normal leading-snug text-slate-700 shadow-lg"
        >
          {children}
        </span>
      ) : null}
    </span>
  );
}

function Title({ title, info }: { title: string; info: React.ReactNode }) {
  return (
    <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
      {title}
      <Info title={title}>{info}</Info>
    </p>
  );
}

/** A KPI card: one number, its unit, and the sentence that makes it readable. */
function Kpi({
  title,
  value,
  valueClass,
  detail,
  info,
  children,
  hook,
}: {
  title: string;
  value?: React.ReactNode;
  valueClass?: string;
  detail?: React.ReactNode;
  info: React.ReactNode;
  children?: React.ReactNode;
  hook: string;
}) {
  return (
    <section
      data-kpi={hook}
      className="min-w-0 rounded border border-slate-200 bg-white px-3 py-2"
    >
      <Title title={title} info={info} />
      {value === undefined ? null : (
        <p className={`mt-1 font-mono text-lg font-semibold tabular-nums ${valueClass ?? "text-slate-900"}`}>
          {value}
        </p>
      )}
      {detail === undefined ? null : (
        <p className="text-xs text-slate-500">{detail}</p>
      )}
      {children}
    </section>
  );
}

const bps = (value: number | null | undefined, places = 1): string => {
  if (value === null || value === undefined) return "n/a";
  const shown = (value * 1e4).toFixed(places);
  return `${Number(shown) >= 0 ? "+" : ""}${shown} bp`;
};

const dayShort = (value: string | null | undefined): string => {
  if (!value) return "-";
  return value.slice(5, 10);
};

/** The last attributed session, by its own date rather than by array order. */
export function lastDay(snapshot: Snapshot): AttributionDay | null {
  const rows = snapshot.attribution?.live?.daily ?? [];
  if (!rows.length) return null;
  return [...rows].sort((a, b) =>
    String(a.trade_date ?? "").localeCompare(String(b.trade_date ?? "")),
  )[rows.length - 1];
}

interface CumulativePoint {
  date: string;
  total: number;
  factor: number;
  idio: number;
  cost: number;
}

/** Cumulative P&L in bp, built from the daily rows the attribution wrote. */
export function cumulativePoints(snapshot: Snapshot): CumulativePoint[] {
  const rows = [...(snapshot.attribution?.live?.daily ?? [])].sort((a, b) =>
    String(a.trade_date ?? "").localeCompare(String(b.trade_date ?? "")),
  );
  let total = 0;
  let factor = 0;
  let idio = 0;
  let cost = 0;
  return rows.map((row) => {
    total += (row.pnl_total ?? 0) * 1e4;
    factor += (row.pnl_factor ?? 0) * 1e4;
    idio += (row.pnl_idio ?? 0) * 1e4;
    cost += (row.pnl_cost ?? 0) * 1e4;
    return {
      date: String(row.trade_date ?? "").slice(0, 10),
      total,
      factor,
      idio,
      cost,
    };
  });
}

const COLORS = {
  total: "#0f172a",
  factor: "#0284c7",
  idio: "#059669",
  cost: "#e11d48",
} as const;

interface SeriesLine {
  key: "total" | "factor" | "idio" | "cost";
  word: string;
  color: string;
  width: number;
}

const SERIES: SeriesLine[] = [
  { key: "total", word: "total", color: COLORS.total, width: 2.5 },
  { key: "factor", word: "factor", color: COLORS.factor, width: 2 },
  { key: "idio", word: "stock-specific", color: COLORS.idio, width: 2 },
  { key: "cost", word: "cost", color: COLORS.cost, width: 2 },
];

const DAY_MS = 86_400_000;

/** A date as UTC midnight, so the axis is the same on every machine. */
function utcMidnight(date: string): number {
  const [year, month, day] = date.split("-").map(Number);
  return Date.UTC(year || 1970, (month || 1) - 1, day || 1);
}

/**
 * The charts are drawn in the card's own pixels rather than in a scaled viewBox.
 * A 2px line stays 2px and a 10px bar stays 10px at any window size, and the
 * drawing always fills the card: the width is measured on mount and again
 * whenever the card changes size.
 */
function useChartWidth(fallback: number): {
  ref: React.RefObject<HTMLDivElement | null>;
  width: number;
} {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    const measure = (): void => {
      const next = Math.round(node.getBoundingClientRect().width);
      if (next > 0) setWidth(next);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}

/** Four or five round numbers across the range, each with a light rule. */
function axisTicks(low: number, high: number): number[] {
  const span = high - low;
  const even = (): number[] => [0, 1, 2, 3, 4].map((index) => low + (span * index) / 4);
  if (!Number.isFinite(span) || span <= 0) return even();
  const rough = span / 4;
  const magnitude = Math.pow(10, Math.floor(Math.log10(rough)));
  const norm = rough / magnitude;
  const step =
    (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * magnitude;
  const ticks: number[] = [];
  for (let value = Math.ceil(low / step) * step; value <= high + step * 1e-6; value += step) {
    ticks.push(Math.round(value * 1e6) / 1e6);
  }
  return ticks.length >= 4 && ticks.length <= 5 ? ticks : even();
}

/** The sessions the axis spans, plus the next rebalance when it is still ahead. */
function plotDates(dates: Array<string | null | undefined>, next?: string | null): string[] {
  const sorted = [...new Set(dates.filter((date): date is string => Boolean(date)))].sort();
  if (!sorted.length) return sorted;
  if (next && next > sorted[sorted.length - 1]) sorted.push(next);
  return sorted;
}

/** One date label a week, read off the calendar rather than every nth point. */
function weeklyTicks(dates: string[]): string[] {
  const ticks: string[] = [];
  let previous = Number.NEGATIVE_INFINITY;
  for (const date of dates) {
    const value = utcMidnight(date);
    if (previous === Number.NEGATIVE_INFINITY || value - previous >= 6 * DAY_MS) {
      ticks.push(date);
      previous = value;
    }
  }
  return ticks;
}

interface PlotFrame {
  left: number;
  right: number;
  top: number;
  bottom: number;
  x: (date: string) => number;
}

function plotFrame(
  dates: string[],
  width: number,
  height: number,
  pad: { left: number; right: number; top: number; bottom: number },
): PlotFrame {
  const first = utcMidnight(dates[0]);
  const last = utcMidnight(dates[dates.length - 1]);
  const span = last - first;
  const left = pad.left;
  const right = Math.max(left + 24, width - pad.right);
  return {
    left,
    right,
    top: pad.top,
    bottom: height - pad.bottom,
    x: (date: string) =>
      span === 0 ? (left + right) / 2 : left + ((utcMidnight(date) - first) / span) * (right - left),
  };
}

interface RebalanceMark {
  date: string;
  future: boolean;
}

/** The rebalances the axis can carry: the closes behind it and the next one ahead. */
function rebalanceMarks(snapshot: Snapshot, known: Set<string>): RebalanceMark[] {
  const strip = snapshot.monthly?.cadence_strip;
  const past = [
    ...new Set([
      ...(snapshot.monthly?.rebalance_dates ?? []),
      ...(strip?.last_rebalance ? [strip.last_rebalance] : []),
    ]),
  ]
    .filter((date) => known.has(date))
    .sort();
  const marks: RebalanceMark[] = past.map((date) => ({ date, future: false }));
  const next = strip?.next_rebalance ?? null;
  if (next && !known.has(next)) marks.push({ date: next, future: true });
  return marks;
}

/** The hover title every chart carries: the day and all four parts, in bp. */
function pointTitle(
  date: string,
  total: number,
  factor: number,
  idio: number,
  cost: number,
): string {
  return `${date}: total ${total.toFixed(1)} bp, factor ${factor.toFixed(1)} bp, stock-specific ${idio.toFixed(1)} bp, cost ${cost.toFixed(1)} bp`;
}

function CumulativeChart({ snapshot }: { snapshot: Snapshot }) {
  const points = cumulativePoints(snapshot);
  const { ref, width } = useChartWidth(680);
  if (points.length === 0) {
    return (
      <div ref={ref} className="mt-1 w-full">
        <p data-overview-cumulative="absent" className="text-xs text-slate-500">
          no attributed session yet, so there is no P&L line to draw.
        </p>
      </div>
    );
  }
  const height = 300;
  const pad = { left: 46, right: 64, top: 24, bottom: 26 };
  const dates = plotDates(
    points.map((point) => point.date),
    snapshot.monthly?.cadence_strip?.next_rebalance,
  );
  const frame = plotFrame(dates, width, height, pad);
  const values = points.flatMap((point) => [point.total, point.factor, point.idio, point.cost]);
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const span = high - low || 1;
  const y = (value: number): number =>
    frame.top + ((high - value) / span) * (frame.bottom - frame.top);
  const known = new Set(points.map((point) => point.date));
  const marks = rebalanceMarks(snapshot, known);
  const last = points[points.length - 1];
  const endLabels = SERIES.map((series) => ({
    series,
    value: last[series.key],
    at: y(last[series.key]),
  })).sort((a, b) => a.at - b.at);
  for (let index = 1; index < endLabels.length; index += 1) {
    if (endLabels[index].at - endLabels[index - 1].at < 11) {
      endLabels[index].at = endLabels[index - 1].at + 11;
    }
  }
  const band = (index: number): { x: number; width: number } => {
    const here = frame.x(points[index].date);
    const before = index === 0 ? frame.left : (here + frame.x(points[index - 1].date)) / 2;
    const after =
      index === points.length - 1
        ? here + Math.max(2, here - before)
        : (here + frame.x(points[index + 1].date)) / 2;
    return { x: before, width: Math.max(2, after - before) };
  };

  return (
    <div ref={ref} className="mt-1 w-full">
      <ul className="mb-1 flex flex-wrap gap-x-3 gap-y-1 text-[0.7rem] text-slate-600">
        {SERIES.map((series) => (
          <li key={series.key} data-legend={series.key} className="flex items-center gap-1">
            <span
              aria-hidden="true"
              className="inline-block w-4"
              style={{ background: series.color, height: series.width }}
            />
            {series.word}
          </li>
        ))}
      </ul>
      <svg
        role="img"
        aria-label="cumulative P&L in basis points"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="block w-full"
        data-overview-cumulative="true"
      >
        <rect
          x={frame.x(last.date)}
          y={frame.top}
          width={Math.max(0, frame.right - frame.x(last.date))}
          height={frame.bottom - frame.top}
          fill="#0f172a"
          fillOpacity="0.03"
          data-future-band="true"
        />
        {axisTicks(low, high).map((tick) => (
          <g key={`grid-${tick}`} data-gridline={tick}>
            <line
              x1={frame.left}
              x2={frame.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="#e2e8f0"
              strokeWidth="1"
            />
            <text
              x={frame.left - 5}
              y={y(tick) + 3}
              textAnchor="end"
              fontSize="9"
              className="fill-slate-500"
            >
              {tick.toFixed(0)}
            </text>
          </g>
        ))}
        <line
          x1={frame.left}
          x2={frame.right}
          y1={y(0)}
          y2={y(0)}
          stroke="#475569"
          strokeWidth="1.6"
          data-zero-line="true"
        />
        <text
          x={frame.left - 5}
          y={y(0) + 3}
          textAnchor="end"
          fontSize="9"
          className="fill-slate-700"
        >
          0
        </text>
        <text x={4} y={frame.top - 10} fontSize="9" className="fill-slate-500">
          bp
        </text>
        {weeklyTicks(dates).map((date) => (
          <g key={`week-${date}`} data-x-tick={date}>
            <line
              x1={frame.x(date)}
              x2={frame.x(date)}
              y1={frame.bottom}
              y2={frame.bottom + 4}
              stroke="#cbd5e1"
            />
            <text
              x={frame.x(date)}
              y={height - 6}
              textAnchor="middle"
              fontSize="9"
              className="fill-slate-500"
            >
              {dayShort(date)}
            </text>
          </g>
        ))}
        {marks.map((mark) => (
          <g
            key={mark.date}
            data-overview-rebalance={mark.date}
            data-rebalance-future={mark.future ? "true" : "false"}
          >
            <line
              x1={frame.x(mark.date)}
              x2={frame.x(mark.date)}
              y1={frame.top}
              y2={frame.bottom}
              stroke={mark.future ? "#cbd5e1" : "#94a3b8"}
              strokeWidth="1"
              strokeDasharray="3 3"
            />
            <text
              x={frame.x(mark.date) + (frame.x(mark.date) > frame.right - 90 ? -3 : 3)}
              y={frame.top - 10}
              textAnchor={frame.x(mark.date) > frame.right - 90 ? "end" : "start"}
              fontSize="9"
              className="fill-slate-500"
            >
              {mark.future
                ? `next rebalance ${dayShort(mark.date)}`
                : `rebalance ${dayShort(mark.date)}`}
            </text>
          </g>
        ))}
        {SERIES.map((series) => (
          <path
            key={series.key}
            d={points
              .map(
                (point, index) =>
                  `${index === 0 ? "M" : "L"}${frame.x(point.date).toFixed(1)},${y(
                    point[series.key],
                  ).toFixed(1)}`,
              )
              .join(" ")}
            fill="none"
            stroke={series.color}
            strokeWidth={series.width}
            strokeLinecap="round"
            strokeLinejoin="round"
            data-series={series.key}
          />
        ))}
        {endLabels.map((label) => (
          <text
            key={`label-${label.series.key}`}
            x={frame.x(last.date) + 6}
            y={label.at + 3}
            fontSize="10"
            fontWeight="600"
            fill={label.series.color}
            data-line-label={label.series.key}
          >
            {`${label.value >= 0 ? "+" : ""}${label.value.toFixed(0)}`}
          </text>
        ))}
        {points.map((point, index) => {
          const hit = band(index);
          return (
            <rect
              key={`hit-${point.date}`}
              data-hover-point={point.date}
              x={hit.x}
              y={frame.top}
              width={hit.width}
              height={frame.bottom - frame.top}
              fill="transparent"
              pointerEvents="all"
            >
              <title>{pointTitle(point.date, point.total, point.factor, point.idio, point.cost)}</title>
            </rect>
          );
        })}
      </svg>
    </div>
  );
}

function DailyBars({ snapshot }: { snapshot: Snapshot }) {
  const rows = [...(snapshot.attribution?.live?.daily ?? [])].sort((a, b) =>
    String(a.trade_date ?? "").localeCompare(String(b.trade_date ?? "")),
  );
  const { ref, width } = useChartWidth(680);
  if (rows.length === 0) {
    return (
      <div ref={ref} className="mt-1 w-full">
        <p data-overview-daily="absent" className="text-xs text-slate-500">
          no attributed session yet, so there are no daily bars to draw.
        </p>
      </div>
    );
  }
  const height = 240;
  const pad = { left: 46, right: 24, top: 22, bottom: 26 };
  const dates = plotDates(
    rows.map((row) => String(row.trade_date ?? "").slice(0, 10)),
    snapshot.monthly?.cadence_strip?.next_rebalance,
  );
  const frame = plotFrame(dates, width, height, pad);
  const values = rows.map((row) => (row.pnl_total ?? 0) * 1e4);
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const span = high - low || 1;
  const y = (value: number): number =>
    frame.top + ((high - value) / span) * (frame.bottom - frame.top);
  const days = Math.max(
    1,
    (utcMidnight(dates[dates.length - 1]) - utcMidnight(dates[0])) / DAY_MS,
  );
  const pixelsPerDay = (frame.right - frame.left) / days;
  const gaps = dates
    .slice(1)
    .map((date, index) => (utcMidnight(date) - utcMidnight(dates[index])) / DAY_MS)
    .filter((gap) => gap > 0);
  const gapDays = gaps.length ? Math.min(...gaps) : 1;
  const barWidth = Math.max(3, Math.min(18, pixelsPerDay * gapDays * 0.62));
  const known = new Set(rows.map((row) => String(row.trade_date ?? "").slice(0, 10)));
  const marks = rebalanceMarks(snapshot, known);

  return (
    <div ref={ref} className="mt-1 w-full">
      <svg
        role="img"
        aria-label="daily P&L in basis points"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="block w-full"
        data-overview-daily="true"
      >
        <rect
          x={frame.x(dates[dates.length - 1])}
          y={frame.top}
          width={Math.max(0, frame.right - frame.x(dates[dates.length - 1]))}
          height={frame.bottom - frame.top}
          fill="#0f172a"
          fillOpacity="0.03"
          data-future-band="true"
        />
        {axisTicks(low, high).map((tick) => (
          <g key={`grid-${tick}`} data-gridline={tick}>
            <line
              x1={frame.left}
              x2={frame.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="#e2e8f0"
              strokeWidth="1"
            />
            <text
              x={frame.left - 5}
              y={y(tick) + 3}
              textAnchor="end"
              fontSize="9"
              className="fill-slate-500"
            >
              {tick.toFixed(0)}
            </text>
          </g>
        ))}
        <line
          x1={frame.left}
          x2={frame.right}
          y1={y(0)}
          y2={y(0)}
          stroke="#475569"
          strokeWidth="1.6"
          data-zero-line="true"
        />
        <text
          x={frame.left - 5}
          y={y(0) + 3}
          textAnchor="end"
          fontSize="9"
          className="fill-slate-700"
        >
          0
        </text>
        <text x={4} y={frame.top - 8} fontSize="9" className="fill-slate-500">
          bp
        </text>
        {weeklyTicks(dates).map((date) => (
          <g key={`week-${date}`} data-x-tick={date}>
            <line
              x1={frame.x(date)}
              x2={frame.x(date)}
              y1={frame.bottom}
              y2={frame.bottom + 4}
              stroke="#cbd5e1"
            />
            <text
              x={frame.x(date)}
              y={height - 6}
              textAnchor="middle"
              fontSize="9"
              className="fill-slate-500"
            >
              {dayShort(date)}
            </text>
          </g>
        ))}
        {marks.map((mark) => (
          <g
            key={mark.date}
            data-daily-rebalance={mark.date}
            data-rebalance-future={mark.future ? "true" : "false"}
          >
            <line
              x1={frame.x(mark.date)}
              x2={frame.x(mark.date)}
              y1={frame.top}
              y2={frame.bottom}
              stroke={mark.future ? "#cbd5e1" : "#94a3b8"}
              strokeWidth="1"
              strokeDasharray="3 3"
            />
            {mark.future ? (
              <text
                x={frame.right - 2}
                y={frame.top - 8}
                textAnchor="end"
                fontSize="9"
                className="fill-slate-500"
              >
                {"next rebalance "}
                {dayShort(mark.date)}
              </text>
            ) : null}
          </g>
        ))}
        {rows.map((row, index) => {
          const date = String(row.trade_date ?? "").slice(0, 10);
          const value = (row.pnl_total ?? 0) * 1e4;
          const top = Math.min(y(0), y(value));
          const heightOfBar = Math.max(1, Math.abs(y(0) - y(value)));
          return (
            <rect
              key={row.trade_date ?? index}
              data-daily-bar={row.trade_date ?? index}
              x={frame.x(date) - barWidth / 2}
              y={top}
              width={barWidth}
              height={heightOfBar}
              fill={value >= 0 ? "var(--efb-up-fill)" : "var(--efb-down-fill)"}
            >
              <title>
                {pointTitle(
                  date,
                  value,
                  (row.pnl_factor ?? 0) * 1e4,
                  (row.pnl_idio ?? 0) * 1e4,
                  (row.pnl_cost ?? 0) * 1e4,
                )}
              </title>
            </rect>
          );
        })}
      </svg>
    </div>
  );
}

interface ExposureRow {
  factor: string;
  afterHedge: number;
  now: number | null;
}

const factorLabel = (key: string): string => {
  const known: Record<string, string> = {
    beta: "Beta",
    liquidity: "Liquidity",
    market: "Market",
    momentum: "Momentum",
    resid_vol: "Residual vol",
    reversal: "Reversal",
    size: "Size",
  };
  if (known[key]) return known[key];
  if (key.startsWith("sector_")) return sectorLabel(Number(key.slice(7)));
  return key.replace(/_/g, " ");
};

/**
 * The factor name on the chart's x axis, short enough to stand on its head.
 *
 * The full names are right on a tooltip and too long under a 36-pixel column:
 * "Consumer Discretionary" written sideways runs past its neighbour. The short
 * form is the same sector, abbreviated the way a table would abbreviate it.
 */
const AXIS_SHORT: Record<string, string> = {
  "Consumer Discretionary": "Cons. disc.",
  "Consumer Staples": "Cons. stpls.",
  "Information Technology": "Info tech",
  "Communication Services": "Comm. svcs",
  "Health Care": "Health care",
  "Real Estate": "Real estate",
};

const axisLabel = (key: string): string => AXIS_SHORT[factorLabel(key)] ?? factorLabel(key);

/** The rebalance's after-hedge exposures beside the book's latest ones. */
export function exposureRows(snapshot: Snapshot): ExposureRow[] {
  const anchor = snapshot.monthly?.anchor_exposures?.after ?? null;
  if (!anchor) return [];
  const nowVector =
    snapshot.exposures_after_hedge && Object.keys(snapshot.exposures_after_hedge).length
      ? snapshot.exposures_after_hedge
      : {};
  return Object.keys(anchor)
    .filter((key) => !key.startsWith("realized") && !key.startsWith("residual_exposure"))
    .map((factor) => {
      const afterHedge = anchor[factor];
      const now = nowVector[factor];
      return {
        factor,
        afterHedge: typeof afterHedge === "number" && Number.isFinite(afterHedge) ? afterHedge : 0,
        now: typeof now === "number" && Number.isFinite(now) ? now : null,
      };
    });
}

function ExposureBars({ snapshot }: { snapshot: Snapshot }) {
  const all = exposureRows(snapshot);
  const { ref, width } = useChartWidth(680);
  if (all.length === 0) {
    return (
      <div ref={ref} className="mt-1 w-full">
        <p data-overview-exposures="absent" className="text-xs text-slate-500">
          this document carries no rebalance hedge footprint, so there is nothing to compare.
        </p>
      </div>
    );
  }
  // The biggest exposures come first: the reader is looking for what is large,
  // not for the risk model's own key order.
  const rows = [...all].sort((a, b) => sizeOf(b) - sizeOf(a));
  const worst = Math.max(...rows.map(sizeOf));
  // One column per factor, read left to right on the x axis, growing up for a
  // long exposure and down for a short one. The frame is the daily chart's: the
  // same 240 pixels of height and the same measured width, so the pair reads as
  // one picture and a column can be compared with a day's bar.
  const height = 240;
  const pad = { left: 46, right: 24, top: 22, bottom: 64 };
  const plotLeft = pad.left;
  const plotRight = Math.max(plotLeft + 40, width - pad.right);
  const top = pad.top;
  const bottom = height - pad.bottom;
  const threshold = 0.05;
  // Symmetric about zero, so the middle of the frame is flat exposure and a long
  // and a short of the same size stand the same height on opposite sides.
  const scale = Math.max(threshold, worst) * 1.12;
  const y = (value: number): number => top + ((scale - value) / (2 * scale)) * (bottom - top);
  const zero = y(0);
  const groupWidth = (plotRight - plotLeft) / rows.length;
  const barWidth = Math.max(3, Math.min(12, groupWidth * 0.3));
  const reach = (value: number): number => Math.max(1, Math.abs(y(value) - zero));
  const centreOf = (index: number): number => plotLeft + (index + 0.5) * groupWidth;

  return (
    <div ref={ref} className="mt-1 w-full">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-[0.7rem] text-slate-600">
        <p data-exposure-header="true">
          worst exposure {percent(worst)} of the {percent(threshold, 0)} limit
        </p>
        <p className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span aria-hidden="true" className="inline-block h-2.5 w-2.5" style={{ background: "#94a3b8" }} />
            after the hedge
          </span>
          <span className="flex items-center gap-1">
            <span aria-hidden="true" className="inline-block h-2.5 w-2.5" style={{ background: "#0284c7" }} />
            now
          </span>
        </p>
      </div>
      <svg
        role="img"
        aria-label="factor exposures after the rebalance hedge and now"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="block w-full"
        data-overview-exposures="true"
      >
        {/* Past the 5% guard, tinted above and below, so a column that reaches the
            tint is at the limit and one near the middle is close to flat. */}
        <rect
          x={plotLeft}
          y={top}
          width={Math.max(0, plotRight - plotLeft)}
          height={Math.max(0, y(threshold) - top)}
          fill="#f59e0b"
          fillOpacity="0.08"
          data-limit-band="right"
        />
        <rect
          x={plotLeft}
          y={y(-threshold)}
          width={Math.max(0, plotRight - plotLeft)}
          height={Math.max(0, bottom - y(-threshold))}
          fill="#f59e0b"
          fillOpacity="0.08"
          data-limit-band="left"
        />
        {axisTicks(-scale, scale).map((tick) => (
          <g key={`exposure-grid-${tick}`} data-gridline={tick}>
            <line
              x1={plotLeft}
              x2={plotRight}
              y1={y(tick)}
              y2={y(tick)}
              stroke="#e2e8f0"
              strokeWidth="1"
            />
            <text
              x={plotLeft - 5}
              y={y(tick) + 3}
              textAnchor="end"
              fontSize="9"
              className="fill-slate-500"
            >
              {percent(tick, 0)}
            </text>
          </g>
        ))}
        <line
          x1={plotLeft}
          x2={plotRight}
          y1={zero}
          y2={zero}
          stroke="#475569"
          strokeWidth="1.6"
          data-zero-line="true"
        />
        <text x={4} y={top - 8} fontSize="9" className="fill-slate-500">
          % of NAV
        </text>
        {[threshold, -threshold].map((value) => (
          <g key={value}>
            <line
              x1={plotLeft}
              x2={plotRight}
              y1={y(value)}
              y2={y(value)}
              stroke="#f59e0b"
              strokeDasharray="3 3"
              data-threshold="5"
            />
            <text
              x={plotRight + 3}
              y={y(value) + 3}
              fontSize="9"
              className="fill-amber-700"
            >
              {value > 0 ? "+5%" : "-5%"}
            </text>
          </g>
        ))}
        {rows.map((row, index) => {
          const centre = centreOf(index);
          return (
            <g key={row.factor} data-exposure-factor={row.factor}>
              {/* Grey is where the rebalance's hedge left it; blue is where the
                  book carries it now. Two columns per factor, side by side. */}
              <rect
                x={centre - barWidth - 1}
                y={row.afterHedge >= 0 ? y(row.afterHedge) : zero}
                width={barWidth}
                height={reach(row.afterHedge)}
                fill="#94a3b8"
                data-exposure-series="after-hedge"
              >
                <title>
                  {`${factorLabel(row.factor)}, after the hedge ${percent(row.afterHedge)}`}
                </title>
              </rect>
              {row.now === null ? null : (
                <rect
                  x={centre + 1}
                  y={row.now >= 0 ? y(row.now) : zero}
                  width={barWidth}
                  height={reach(row.now)}
                  fill="#0284c7"
                  data-exposure-series="now"
                >
                  <title>
                    {`${factorLabel(row.factor)}, now ${percent(row.now)}`}
                  </title>
                </rect>
              )}
              <text
                x={centre}
                y={bottom + 6}
                textAnchor="end"
                fontSize="8"
                transform={`rotate(-90 ${centre} ${bottom + 6})`}
                className="fill-slate-600"
              >
                {axisLabel(row.factor)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/** The size a row is sorted and headed by: the larger of its two readings. */
function sizeOf(row: ExposureRow): number {
  return Math.max(Math.abs(row.afterHedge), Math.abs(row.now ?? 0));
}

/** One line per thing a person has to look at, and nothing when there is none. */
export interface OverviewException {
  key: string;
  text: string;
  /** The name a line is about, when it is about one, so two sources cannot double it. */
  ticker?: string;
}

export function overviewExceptions(
  snapshot: Snapshot,
  state: RunState,
  reconciled: Reconciliation,
  exceptions: Exceptions,
): OverviewException[] {
  const lines: OverviewException[] = [];
  const seen = new Map<string, OverviewException>();
  const add = (key: string, text: string, ticker?: string): void => {
    // The same name can arrive from the holdings table, tonight's unsendable legs
    // and the account's departures. One card per fact is the rule: the first source
    // that knows what happened to it wins, and a reader never counts KVUE twice.
    const dedupe = ticker ?? key;
    if (seen.has(dedupe)) return;
    const row = { key, text, ticker };
    seen.set(dedupe, row);
    lines.push(row);
  };
  const heldDollars = (ticker: string): number | null => {
    const name = (snapshot.actual_holdings?.names ?? []).find((entry) => entry.ticker === ticker);
    const value = name?.notional;
    return typeof value === "number" && Number.isFinite(value) ? Math.abs(value) : null;
  };
  if (!state.ok) add("run", `${state.headline}. ${state.detail}`);
  if (reconciled.unresolved > 0) {
    add(
      "reconciliation",
      `${reconciled.unresolved} reconciliation check(s) unresolved, see Operations`,
    );
  }
  for (const row of snapshot.monthly?.holdings?.rows ?? []) {
    if (row.retired) {
      const note = row.note ?? "retired, owed, cannot be traded";
      const acquired = /retired \(([^)]+)\)/.exec(note)?.[1];
      const by = acquired ? acquired.replace(/^acquired by /i, "") : null;
      const value = heldDollars(row.ticker) ?? row.gap_usd ?? null;
      const held = value === null ? "held" : `held ${dollars(value)}`;
      add(
        row.ticker,
        `${row.ticker}: ${by ? `acquired by ${by}` : "retired"}, symbol inactive, ${held}, cannot be traded`,
        row.ticker,
      );
    } else if (row.owed) {
      const dollarsSuffix =
        row.gap_usd === null || row.gap_usd === undefined
          ? ""
          : `, ${dollars(Math.abs(row.gap_usd))}`;
      add(row.ticker, `${row.ticker}: owed and cannot be traded${dollarsSuffix}`, row.ticker);
    }
  }
  for (const leg of snapshot.monthly?.tonight?.cannot_send ?? []) {
    add(
      `cannot-send-${leg.ticker}`,
      `${leg.ticker}: ${dollars(leg.usd)} owed, cannot be sent (${leg.code})`,
      leg.ticker,
    );
  }
  for (const name of snapshot.actual_holdings?.exits?.names ?? []) {
    add(
      `exit-${name.ticker}`,
      `${name.ticker}: left the account with no order behind it, ${dollars(name.notional)}`,
      name.ticker,
    );
  }
  for (const entry of exceptions.unexpected) {
    add(entry.ticker, `${entry.ticker}: ${entry.why}`, entry.ticker);
  }
  return lines;
}

const TONE_BANNER: Record<Tone, string> = {
  bad: "border-red-500 bg-red-50 text-red-900",
  warn: "border-amber-400 bg-amber-50 text-amber-900",
  info: "border-slate-300 bg-slate-50 text-slate-700",
  good: "border-emerald-300 bg-emerald-50 text-emerald-900",
};

function ExceptionBanner({
  state,
  lines,
}: {
  state: RunState;
  lines: OverviewException[];
}) {
  const tone: Tone = lines.length === 0 ? "good" : state.tone === "bad" ? "bad" : "warn";
  const role = tone === "bad" ? "alert" : "status";
  const shown = lines.slice(0, 8);
  return (
    <section
      data-exception-banner={lines.length === 0 ? "clear" : "attention"}
      data-tone={tone}
      role={role}
      className={`rounded border-l-4 px-3 py-2 ${TONE_BANNER[tone]}`}
    >
      <p className="text-sm font-semibold">
        {lines.length === 0 ? "All clear" : "Needs attention"}
      </p>
      {lines.length === 0 ? (
        <p className="text-xs">nothing on the account or the run needs attention today.</p>
      ) : (
        <ul className="mt-1 flex flex-col gap-1 text-sm">
          {shown.map((line) => (
            <li
              key={line.key}
              data-exception={line.key}
              className="rounded border border-slate-300/70 bg-white/70 px-2 py-1"
            >
              {line.text}
            </li>
          ))}
          {lines.length > shown.length ? (
            <li data-exception-more="true">
              and {lines.length - shown.length} more, see Operations
            </li>
          ) : null}
        </ul>
      )}
    </section>
  );
}

function CadencePill({ monthly }: { monthly?: MonthlyBlock | null }) {
  const strip = monthly?.cadence_strip;
  if (!strip) {
    return (
      <p data-cadence-pill="absent" className="text-sm text-slate-600">
        no cadence calendar on this document
      </p>
    );
  }
  const next = dayShort(strip.next_rebalance);
  if (strip.day === "rebalance") {
    return (
      <p
        data-cadence-pill="rebalance"
        className="inline-block rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1 text-sm font-semibold text-emerald-900"
      >
        rebalance day, next {next}
      </p>
    );
  }
  if (strip.k === null || strip.k === undefined || strip.k === 1) {
    return (
      <p
        data-cadence-pill="daily"
        className="inline-block rounded-full border border-slate-300 bg-slate-50 px-3 py-1 text-sm font-semibold text-slate-800"
      >
        daily cadence, next {next}
      </p>
    );
  }
  const day = strip.sessions_since ?? 1;
  return (
    <p
      data-cadence-pill="hold"
      className="inline-block rounded-full border border-slate-300 bg-slate-50 px-3 py-1 text-sm font-semibold text-slate-800"
    >
      hold day {day} of {strip.k}, next rebalance {next}
    </p>
  );
}

function DriftGuard({ monthly }: { monthly?: MonthlyBlock | null }) {
  const guard = monthly?.cadence_strip?.guard;
  const worst = guard?.worst_abs_exposure ?? null;
  const threshold = guard?.threshold ?? null;
  const limit = threshold ?? 0.05;
  if (worst === null) {
    return <p className="text-sm text-slate-500">no drift reading on this document</p>;
  }
  const ratio = limit > 0 ? Math.min(1, Math.max(0, worst / limit)) : 0;
  const over = limit > 0 && worst > limit;
  return (
    <div data-drift-guard="true" className="mt-1">
      <p className="font-mono text-sm font-semibold tabular-nums text-slate-900">
        {percent(worst)} of {percent(limit, 0)}
      </p>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(ratio * 100)}
        className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-200"
      >
        <div
          className={`h-full rounded-full ${over ? "bg-amber-500" : "bg-emerald-600"}`}
          style={{ width: `${(ratio * 100).toFixed(1)}%` }}
        />
      </div>
    </div>
  );
}

function LastRun({ snapshot, state, now }: { snapshot: Snapshot; state: RunState; now: Date }) {
  const written = freshness(snapshot);
  return (
    <div data-last-run="true" className="mt-1">
      <p className="text-sm font-semibold text-slate-900">{state.pill}</p>
      <p className="text-xs text-slate-500">
        {written.at === null
          ? "no write recorded"
          : `${etDateTime(written.at) ?? "unknown"}(${ageText(written.at, now)})`}
      </p>
    </div>
  );
}

export function Overview({
  snapshot,
  state,
  reconciled,
  exceptions,
  now,
}: {
  snapshot: Snapshot;
  state: RunState;
  reconciled: Reconciliation;
  exceptions: Exceptions;
  now: Date;
}) {
  const nav = snapshot.book?.gross_notional && snapshot.book?.gross
    ? snapshot.book.gross_notional / snapshot.book.gross
    : null;
  const latest = lastDay(snapshot);
  const todayValue = latest?.pnl_total ?? null;
  const cumulative = snapshot.attribution?.live?.cumulative;
  const lines = overviewExceptions(snapshot, state, reconciled, exceptions);
  const monthly = snapshot.monthly;
  const totalSince = cumulative?.pnl_total ?? null;
  const lastDate = latest?.trade_date ? dayShort(latest.trade_date) : null;
  const written = freshness(snapshot);
  const exposureNow = exposureRows(snapshot);
  const worstNow = exposureNow.length
    ? Math.max(...exposureNow.map((row) => Math.abs(row.now ?? 0)))
    : null;

  return (
    <div data-overview="true" className="flex flex-col gap-3">
      <p data-strategy="true" className="max-w-4xl text-sm text-slate-700">
        This is a market-neutral equity book: long and short US stocks, rebuilt every
        21 sessions, with the market and sector factors hedged out so the P&amp;L comes
        from stock selection rather than from a market bet.
      </p>

      <ExceptionBanner state={state} lines={lines} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          hook="nav"
          title="NAV"
          value={dollars(nav)}
          detail="the dollars the book is sized in"
          info={
            <>
              The account’s own equity at the latest read, in dollars. It moves when the
              book earns or loses and when cash moves, so every weight and cost is quoted
              against it. Example: the book that trades is 100% of NAV, which is why
              gross is the book and net is its long/short tilt.
            </>
          }
        />
        <Kpi
          hook="today"
          title="today"
          value={bps(todayValue)}
          valueClass={pnlClass(todayValue)}
          detail={
            <>
              {lastDate ? `the ${lastDate} close` : "no attributed session"}
              {todayValue === null || nav === null ? null : (
                <>
                  {", "}
                  <span className={pnlClass(todayValue * nav)}>
                    {signedDollars(todayValue * nav)}
                  </span>
                  {" in dollars"}
                </>
              )}
            </>
          }
          info={
            <>
              The last attributed session’s total, in basis points of NAV, with the same
              number in dollars. It moves with the book’s return, so a quiet hold day is
              often a few bp and a rebalance day also carries its trading cost. Example:{" "}
              {latest?.pnl_total !== null && latest?.pnl_total !== undefined
                ? `on ${lastDate} the book made ${bps(latest.pnl_total)}, of which stock-specific was ${bps(
                    latest.pnl_idio,
                  )}.`
                : "no day is attributed yet."}
            </>
          }
        />
        <Kpi
          hook="since"
          title="P&L since go-live"
          value={bps(totalSince)}
          valueClass={pnlClass(totalSince)}
          detail={
            totalSince === null || nav === null
              ? "no cumulative figure"
              : `${signedDollars(totalSince * nav)} in dollars`
          }
          info={
            <>
              Everything the live book has earned since its first filled leg, split into
              the three parts below. It moves every session; the split says whether the
              month came from the hedge, from stock picking, or went to trading cost.
              Example: the split is the sum of the daily rows, so the three parts plus the
              small unexplained residual equal the total.
            </>
          }
        >
          <div className="mt-1 grid grid-cols-[auto_1fr_1fr] gap-x-2 text-[0.65rem] uppercase tracking-wide text-slate-400">
            <span>part</span>
            <span className="text-right">bp</span>
            <span className="text-right">dollars</span>
          </div>
          <dl data-since-split="true" className="grid grid-cols-[auto_1fr_1fr] gap-x-2 gap-y-0.5 text-xs">
            {[
              { label: "factor", value: cumulative?.pnl_factor ?? null },
              { label: "stock-specific", value: cumulative?.pnl_idio ?? null },
              { label: "cost", value: cumulative?.pnl_cost ?? null },
            ].map((row) => (
              <div key={row.label} className="contents">
                <dt className="text-slate-500">{row.label}</dt>
                <dd className={`text-right font-mono tabular-nums ${pnlClass(row.value)}`}>
                  {bps(row.value)}
                </dd>
                <dd className={`text-right font-mono tabular-nums ${pnlClass(row.value)}`}>
                  {row.value === null || nav === null ? "n/a" : signedDollars(row.value * nav)}
                </dd>
              </div>
            ))}
          </dl>
        </Kpi>
        <Kpi
          hook="drift"
          title="drift guard"
          info={
            <>
              The worst absolute factor exposure the book carries, as a share of NAV,
              against the guard’s 5% limit. It moves as prices and fills change the book’s
              shape; past the limit the next hold day re-hedges. Example:{" "}
              {monthly?.cadence_strip?.guard?.fired
                ? `on the last guard day the worst exposure went from ${percent(
                    monthly.cadence_strip.guard.worst_abs_exposure,
                  )} to ${percent(monthly.cadence_strip.guard.exposure_after)}.`
                : "a quiet hold day leaves it where the last rebalance put it."}
            </>
          }
        >
          <DriftGuard monthly={monthly} />
        </Kpi>
        <Kpi
          hook="cadence"
          title="cadence"
          info={
            <>
              The book is rebuilt every 21 sessions and left alone on the days between,
              unless the drift guard fires. The pill says which day this is and when the
              next rebuild lands. Example: this document is on {monthly?.cadence_strip?.day === "hold" || monthly?.cadence_strip?.day === "rebalance"
                ? `${monthly.cadence_strip.day === "hold" ? `hold day ${monthly.cadence_strip.sessions_since ?? 1} of ${monthly.cadence_strip.k ?? 21}` : "a rebalance day"}, with the next rebuild on ${dayShort(monthly.cadence_strip.next_rebalance)}`
                : "a daily cadence, so every close can resize the book"}.
            </>
          }
        >
          <div className="mt-1">
            <CadencePill monthly={monthly} />
          </div>
        </Kpi>
        <Kpi
          hook="run"
          title="last run"
          info={
            <>
              The state of the evening that wrote this document and when it wrote it, in
              New York time. It moves once a session; a stopped run leaves the previous
              close’s book on the page and the pill says so. Example: this document says{" "}
              {state.pill} and was written {written.at === null ? "at an unrecorded time" : etDateTime(written.at)}.
            </>
          }
        >
          <LastRun snapshot={snapshot} state={state} now={now} />
        </Kpi>
      </div>

      <section className="rounded border border-slate-200 bg-white px-3 py-2">
        <Title
          title="cumulative P&L"
          info={
            <>
              Each line is the running total of one part of the P&L, in basis points of
              NAV, from the first live session. The total is the sum of factor,
              stock-specific and cost. The dashed vertical marks are rebalance closes, and
              the one on the right is the next rebuild. Each line carries its latest value
              at its right end. Example: cost is {bps(cumulative?.pnl_cost)} since go-live,
              and the last session moved it {bps(latest?.pnl_cost)}.
            </>
          }
        />
        <CumulativeChart snapshot={snapshot} />
      </section>

      <div className="grid items-start gap-3 lg:grid-cols-2">
        <section className="min-w-0 self-start rounded border border-slate-200 bg-white px-3 py-2">
          <Title
            title="daily P&L"
            info={
              <>
                One bar per attributed session, in basis points of NAV. Green is a
                positive day and rose a negative one; the bar’s height is the total, not a
                component. Example: the last session, {lastDate ?? "no day"}, was{" "}
                {bps(latest?.pnl_total)}.
              </>
            }
          />
          <DailyBars snapshot={snapshot} />
        </section>
        <section className="min-w-0 self-start rounded border border-slate-200 bg-white px-3 py-2">
          <Title
            title="factor exposures"
            info={
              <>
                One column per factor, largest first, growing up when the book is long the
                factor and down when it is short it. Grey is where the rebalance’s hedge
                left the exposure and blue is where the book carries it now. The two faint
                dashed lines are the 5% guard, so a column that reaches one is at the limit
                and a column near the middle is close to flat. The header names the worst
                exposure as a share of that limit. Example: the worst factor now is{" "}
                {percent(worstNow)}, against{" "}
                {percent(Math.max(0, ...exposureNow.map((row) => Math.abs(row.afterHedge))))}{" "}
                after the rebalance hedge.
              </>
            }
          />
          <ExposureBars snapshot={snapshot} />
        </section>
      </div>
    </div>
  );
}
