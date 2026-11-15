// The attribution section: what the book earned, in the four terms that add to its
// total, and the two pictures the numbers need to be read.
//
// The section exists to make one misreading impossible: a return is not one
// number. Every session's P&L is a sum of four terms - the hedge's factor P&L, the
// names' idiosyncratic P&L, what the fills cost, and the unexplained remainder -
// and the page prints all four, the total, and the worst day's identity residual
// beside them, so a split nobody checked shows up as one that does not add up.
//
// Two periods live here and only one of them is the book. The live book runs from
// the session the first leg filled; the research panel is the seed's own backtest,
// which nobody traded. They are different objects, so the second sits behind a
// switch and carries its own note: its cost is zero because no leg was traded, and
// its fourth term is the stored descriptors' vintage disagreement rather than a
// loss anyone took. Reading the two as one panel is the mistake the switch exists
// to prevent.
//
// Both charts are drawn by hand in SVG. No chart library is in the page's
// dependencies and two small plots do not justify one; the colours carry a meaning
// (factor, idio, cost, unexplained) that is repeated in words in each legend,
// because colour alone is not readable to everyone.

import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

import { HowToRead } from "./Panel";
import { count, dateOnly, dollars, percent, pnlClass } from "./format";
import { factorWord } from "./labels";
import type {
  Attribution,
  AttributionDay,
  AttributionPeriod,
  AttributionRisk,
  AttributionRiskPath,
  Snapshot,
} from "./types";

/** A P&L in basis points of NAV, signed to one place. */
const bps = (value: number | null | undefined): string =>
  value === null || value === undefined
    ? "n/a"
    : `${value >= 0 ? "+" : ""}${(value * 1e4).toFixed(1)} bp of NAV`;

/**
 * A figure in basis points, bare, for a table whose header carries the unit.
 *
 * "bp of NAV" in every cell is the same three words eleven times; in the header it is
 * said once and the column reads as numbers. The sign is kept: a favourable cost is a
 * negative number in the same column as an expensive one.
 */
const bare = (value: number | null | undefined): string =>
  value === null || value === undefined
    ? "n/a"
    : `${value >= 0 ? "+" : ""}${(value * 1e4).toFixed(1)}`;

/** A cost already quoted in basis points of NAV; a favourable fill is negative. */
const costBps = (value: number | null | undefined): string =>
  value === null || value === undefined ? "n/a" : `${value.toFixed(2)} bp of NAV`;

/** An annualized volatility, which is a fraction, as a percentage to one place. */
const volPct = (value: number | null | undefined): string =>
  value === null || value === undefined ? "n/a" : `${(value * 100).toFixed(1)}%`;

/**
 * The raw book beta to three places.
 *
 * One decimal printed a real beta of 0.0228 as "0.0" while the beta line beside it
 * was non-zero, which reads as a section disagreeing with itself. Three places is
 * the smallest that never turns a live beta into zero.
 */
const beta3 = (value: number | null | undefined): string =>
  value === null || value === undefined ? "n/a" : value.toFixed(3);

/** A term a day does not carry closes that day exactly, so it prints as zero. */
const closingBps = (value: number | null | undefined): string => bps(value ?? 0);

const COLORS = {
  total: "#0f172a",
  factor: "#0284c7",
  idio: "#059669",
  cost: "#e11d48",
  unexplained: "#d97706",
} as const;

const SERIES = [
  { key: "total", word: "total", color: COLORS.total, dash: "" },
  { key: "factor", word: "factor", color: COLORS.factor, dash: "5 2" },
  { key: "idio", word: "stock-specific", color: COLORS.idio, dash: "1 3" },
  { key: "cost", word: "cost", color: COLORS.cost, dash: "7 2 1 2" },
] as const;

const COMPONENTS = [
  { key: "factor", field: "pnl_factor", color: COLORS.factor },
  { key: "idio", field: "pnl_idio", color: COLORS.idio },
  { key: "cost", field: "pnl_cost", color: COLORS.cost },
  { key: "unexplained", field: "pnl_unexplained", color: COLORS.unexplained },
] as const;

/**
 * One legend entry.
 *
 * `shape` says how the series is drawn, because a legend that showed every series as a
 * line would mislabel the two charts whose series are filled areas: a reader looking
 * for "where is that line" in a stacked band is looking for something the chart does
 * not have.
 */
type LegendEntry = {
  key: string;
  word: string;
  color: string;
  dash: string;
  shape?: "line" | "patch";
};

/**
 * What the fourth term is called in each view.
 *
 * The live book's fourth term is a stored artifact not reproducing the panel's own
 * return, and it is a few hundredths of a basis point. On a backtest of the seed it
 * is the descriptors' vintage: the ones on file are not the design the 2012-2026 fit
 * was estimated on, so a decade of the same gap accumulates to hundreds of bp.
 * Labelling that "unexplained" invites it to be read as P&L nobody can account for,
 * which is the one thing it is not: it is a known data gap, and it is named as one.
 */
const UNEXPLAINED_LABEL = {
  live: {
    long: "unexplained remainder (rounding and data gaps)",
    short: "unexplained",
  },
  backtest: {
    long: "research-vintage mismatch (descriptors on file differ from the fit's design)",
    short: "research-vintage mismatch",
  },
} as const;

function Legend({ entries }: { entries: LegendEntry[] }) {
  return (
    <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-600">
      {entries.map((entry) => (
        <li key={entry.key} data-series={entry.key} className="flex items-center gap-1">
          <svg width="18" height="8" aria-hidden="true">
            {entry.shape === "patch" ? (
              <rect x="0" y="0" width="18" height="8" fill={entry.color} fillOpacity="0.55" />
            ) : (
              <line
                x1="0"
                y1="4"
                x2="18"
                y2="4"
                stroke={entry.color}
                strokeWidth="2"
                strokeDasharray={entry.dash === "" ? undefined : entry.dash}
              />
            )}
          </svg>
          <span>{entry.word}</span>
        </li>
      ))}
    </ul>
  );
}

type CumulativePoint = { label: string; total: number; factor: number; idio: number; cost: number };

const runningTotals = (
  rows: Array<{
    label: string;
    total: number | null;
    factor: number | null;
    idio: number | null;
    cost: number | null;
  }>,
): CumulativePoint[] => {
  let total = 0;
  let factor = 0;
  let idio = 0;
  let cost = 0;
  return rows.map((row) => {
    total += row.total ?? 0;
    factor += row.factor ?? 0;
    idio += row.idio ?? 0;
    cost += row.cost ?? 0;
    return { label: row.label, total, factor, idio, cost };
  });
};

/**
 * The cumulative lines: total, factor, idio and cost across the whole period.
 *
 * Four lines on one axis, because the question is how the total's shape splits, not
 * four separate histories. The scale is shared and the viewBox scales with its
 * container, so the same drawing is readable on a phone and on a laptop; the first
 * and last dates are labelled rather than every tick.
 */
function CumulativeChart({
  points,
  rebalances = [],
}: {
  points: CumulativePoint[];
  /** The rebalance closes, drawn as vertical markers. Empty leaves the chart as it was. */
  rebalances?: string[];
}) {
  const W = 320;
  const H = 150;
  const L = 42;
  const R = 8;
  const T = 10;
  const B = 22;
  const pw = W - L - R;
  const ph = H - T - B;
  const values = points.flatMap((point) => [point.total, point.factor, point.idio, point.cost]);
  const max = Math.max(0, ...values);
  const min = Math.min(0, ...values);
  const span = max - min || 1;
  const x = (index: number): number =>
    points.length <= 1 ? L + pw / 2 : L + (index / (points.length - 1)) * pw;
  const y = (value: number): number => T + (1 - (value - min) / span) * ph;
  const ticks = [max, (max + min) / 2, min];
  const first = points[0];
  const last = points[points.length - 1];

  return (
    <figure className="mt-3" data-chart="cumulative">
      <figcaption className="text-xs text-slate-500">cumulative, bp of NAV</figcaption>
      <svg
        className="h-auto"
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label="cumulative P&L: total, factor, stock-specific and cost"
      >
        {ticks.map((tick, index) => (
          <g key={index}>
            <line x1={L} y1={y(tick)} x2={W - R} y2={y(tick)} stroke="#e2e8f0" strokeWidth="1" />
            <text x={L - 4} y={y(tick) + 3} textAnchor="end" fontSize="8" fill="#64748b">
              {(tick * 1e4).toFixed(0)}
            </text>
          </g>
        ))}
        <line
          x1={L}
          y1={y(0)}
          x2={W - R}
          y2={y(0)}
          stroke="#94a3b8"
          strokeWidth="1"
          strokeDasharray="2 2"
        />
        {SERIES.map((series) => (
          <polyline
            key={series.key}
            data-series={series.key}
            fill="none"
            stroke={series.color}
            strokeWidth="1.5"
            strokeDasharray={series.dash === "" ? undefined : series.dash}
            points={points
              .map((point, index) => `${x(index)},${y(point[series.key])}`)
              .join(" ")}
          />
        ))}
        {/* One marker per rebalance close that this series holds. A monthly book's
            chart is a line with no calendar on it until these are drawn: the steps in
            it are the rebalances, and the reader cannot see which days they were. */}
        {rebalances.map((close) => {
          const index = points.findIndex((point) => point.label === close);
          if (index < 0) return null;
          return (
            <g key={close} data-rebalance-marker={close}>
              <line
                x1={x(index)}
                y1={T}
                x2={x(index)}
                y2={T + ph}
                stroke="#94a3b8"
                strokeWidth="1"
                strokeDasharray="3 2"
              />
            </g>
          );
        })}
        <text x={L} y={H - 6} textAnchor="start" fontSize="8" fill="#64748b">
          {first.label}
        </text>
        <text x={W - R} y={H - 6} textAnchor="end" fontSize="8" fill="#64748b">
          {last.label}
        </text>
        {/* The pointer's own reading: a band per session with the date and the four
            running totals, so the shape is not the only thing the chart says. */}
        {points.map((point, index) => {
          const hit = pw / Math.max(points.length, 1);
          return (
            <rect
              key={`hover-${point.label}`}
              data-hover-point={point.label}
              x={x(index) - hit / 2}
              y={T}
              width={hit}
              height={ph}
              fill="transparent"
              pointerEvents="all"
            >
              <title>
                {`${point.label}: total ${(point.total * 1e4).toFixed(1)} bp, factor ${(
                  point.factor * 1e4
                ).toFixed(1)} bp, stock-specific ${(point.idio * 1e4).toFixed(1)} bp, cost ${(
                  point.cost * 1e4
                ).toFixed(1)} bp`}
              </title>
            </rect>
          );
        })}
      </svg>
      <Legend entries={SERIES.map((series) => ({ ...series }))} />
    </figure>
  );
}

/**
 * One bar per live day, the four terms stacked, and the day's total on a marker.
 *
 * The stack diverges: a positive term rises from the zero line and a negative one
 * falls below it, because idio P&L is negative on many days of a hedged book and a
 * chart that dropped the sign would draw a loss as a gain. The total marker is
 * what makes a day that does not add up visible: if the four segments do not reach
 * the marker, one of the terms is not the term it claims to be.
 */
function DailyBars({ days }: { days: AttributionDay[] }) {
  const W = 320;
  const H = 150;
  const L = 6;
  const R = 6;
  const T = 12;
  const B = 20;
  const pw = W - L - R;
  const ph = H - T - B;
  const stats = days.map((day) => {
    let up = 0;
    let down = 0;
    for (const component of COMPONENTS) {
      const value = day[component.field] ?? 0;
      if (value > 0) up += value;
      else down += value;
    }
    return { day, up, down };
  });
  const top = Math.max(0, ...stats.map((stat) => stat.up));
  const bottom = Math.min(0, ...stats.map((stat) => stat.down));
  const span = top - bottom || 1;
  const y = (value: number): number => T + (1 - (value - bottom) / span) * ph;
  const slot = pw / Math.max(1, stats.length);
  const barWidth = Math.max(3, Math.min(18, slot * 0.55));
  const first = days[0];
  const last = days[days.length - 1];

  return (
    <figure className="mt-3" data-chart="daily">
      <figcaption className="text-xs text-slate-500">
        each bar is one live day, its four terms stacked, bp of NAV
      </figcaption>
      <svg
        className="h-auto"
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label="daily P&L, the four terms stacked against the day's total"
      >
        <line x1={L} y1={y(0)} x2={W - R} y2={y(0)} stroke="#94a3b8" strokeWidth="1" />
        {stats.map((stat, index) => {
          const cx = L + (index + 0.5) * slot;
          const date = dateOnly(stat.day.trade_date) ?? "";
          let up = 0;
          let down = 0;
          return (
            <g key={stat.day.trade_date ?? index} data-day={date}>
              {COMPONENTS.map((component) => {
                const value = stat.day[component.field] ?? 0;
                if (value === 0) return null;
                const from = value > 0 ? up : down;
                const to = value > 0 ? up + value : down + value;
                const y0 = y(from);
                const y1 = y(to);
                if (value > 0) up += value;
                else down += value;
                return (
                  <rect
                    key={component.key}
                    data-series={component.key}
                    x={cx - barWidth / 2}
                    y={Math.min(y0, y1)}
                    // A term worth a few hundredths of a bp is a hairline at this
                    // scale; the minimum keeps a real term visible rather than
                    // dropping it, and the marker still fixes where the total is.
                    height={Math.max(Math.abs(y1 - y0), 0.8)}
                    width={barWidth}
                    fill={component.color}
                  />
                );
              })}
              <line
                data-series="total"
                x1={cx - barWidth / 2 - 2}
                y1={y(stat.day.pnl_total ?? 0)}
                x2={cx + barWidth / 2 + 2}
                y2={y(stat.day.pnl_total ?? 0)}
                stroke={COLORS.total}
                strokeWidth="1.6"
              />
              <rect
                data-hover-day={date}
                x={cx - slot / 2}
                y={T}
                width={slot}
                height={ph}
                fill="transparent"
                pointerEvents="all"
              >
                <title>
                  {`${date}: total ${bare(stat.day.pnl_total)} bp, factor ${bare(
                    stat.day.pnl_factor,
                  )} bp, stock-specific ${bare(stat.day.pnl_idio)} bp, cost ${bare(
                    stat.day.pnl_cost,
                  )} bp, unexplained ${bare(stat.day.pnl_unexplained)} bp`}
                </title>
              </rect>
            </g>
          );
        })}
        <text x={L} y={H - 6} textAnchor="start" fontSize="8" fill="#64748b">
          {dateOnly(first?.trade_date) ?? ""}
        </text>
        <text x={W - R} y={H - 6} textAnchor="end" fontSize="8" fill="#64748b">
          {dateOnly(last?.trade_date) ?? ""}
        </text>
      </svg>
      <Legend
        entries={[
          ...COMPONENTS.map((component) => ({
            key: component.key,
            word: component.key,
            color: component.color,
            dash: "",
          })),
          { key: "total", word: "total", color: COLORS.total, dash: "" },
        ]}
      />
      <p className="mt-1 text-xs text-slate-500">
        The short dark line on each bar is that day's total, not a fifth term: the four segments
        stack to it, so a bar that does not reach its marker is a day that does not add up.
      </p>
    </figure>
  );
}

/**
 * Whether a day's cost is a measured number or the evening's estimate.
 *
 * `live/attribution_job.py` puts the fill-measured cost in a day's row when the store
 * has one and the evening's expectation in when it does not, so the same column holds
 * two kinds of number. What the document publishes is the count of measured days
 * (`cost.n_realized`) and, for the close it reconciled, the measured figure itself
 * (`actual_holdings.fills.realized_cost_bps`). A day whose cost is that figure is
 * measured; a day whose cost is the period's expectation is the estimate. A day that
 * matches neither gets no tag rather than a guess.
 */
function costBasis(
  day: AttributionDay,
  period: AttributionPeriod | undefined,
  snapshot: Snapshot | undefined,
): "m" | "est" | null {
  const cost = day.pnl_cost;
  if (cost === null || cost === undefined) return null;
  const fills = snapshot?.actual_holdings?.fills ?? null;
  const close = dateOnly(day.trade_date);
  if (fills && close !== null && dateOnly(fills.trade_date) === close) {
    const measured = fills.realized_cost_bps;
    if (measured !== null && measured !== undefined && Math.abs(-cost * 1e4 - measured) < 0.05) {
      return "m";
    }
  }
  const expected = period?.cost.expected_bps ?? null;
  if (expected !== null && Math.abs(-cost * 1e4 - expected) < 0.05) return "est";
  return null;
}

/** One day's row, with the row's own sum checked against its total rather than asserted. */
function DayRow({
  day,
  period,
  snapshot,
}: {
  day: AttributionDay;
  period?: AttributionPeriod;
  snapshot?: Snapshot;
}) {
  const date = dateOnly(day.trade_date);
  const basis = costBasis(day, period, snapshot);
  const sum =
    (day.pnl_factor ?? 0) + (day.pnl_idio ?? 0) + (day.pnl_cost ?? 0) + (day.pnl_unexplained ?? 0);
  const total = day.pnl_total ?? 0;
  // The four terms are the total to machine precision; anything larger is a stored
  // day that does not decompose, which is the one thing this table is for.
  const ok = Math.abs(sum - total) < 1e-12;
  return (
    <tr data-day={date ?? ""} className="border-b border-slate-100">
      <td className="py-1 font-mono whitespace-nowrap">{date ?? "n/a"}</td>
      <td className="py-1 tabular-nums">{bare(day.pnl_total)}</td>
      <td className="py-1 tabular-nums">{bare(day.pnl_factor)}</td>
      <td className="py-1 tabular-nums">{bare(day.pnl_idio)}</td>
      <td className="py-1 tabular-nums">
        {bare(day.pnl_cost)}
        {basis === null ? null : (
          <span
            data-cost-basis={basis}
            className="ml-1 rounded bg-slate-200 px-1 text-[0.6rem] uppercase text-slate-600"
          >
            {basis}
          </span>
        )}
      </td>
      <td className="py-1 tabular-nums">{closingBps(day.pnl_unexplained)}</td>
      <td className="py-1" data-check={ok ? "ok" : "off"}>
        {ok ? "✓ ok" : `✗ ${bps(sum - total)}`}
      </td>
    </tr>
  );
}

/**
 * The day-by-day table, newest first, ten rows until asked for the rest.
 *
 * Ten is a screen; the toggle is for the whole period so the last month of a long
 * run stays reachable without pushing the rest of the page away. The check column
 * carries a tick rather than a fifth number: the residual is either zero or the
 * row is broken, and a column of "+0.0 bp" beside four numbers invites being read
 * as one of the terms.
 */
function DayTable({
  days,
  label,
  period,
  snapshot,
  live = true,
}: {
  days: AttributionDay[];
  label: string;
  period?: AttributionPeriod;
  snapshot?: Snapshot;
  live?: boolean;
}) {
  const [showAll, setShowAll] = useState(false);
  const newest = [...days].reverse();
  const shown = showAll ? newest : newest.slice(0, 10);
  if (newest.length === 0) return null;
  return (
    <div className="mt-3 overflow-x-auto">
      <table aria-label={label} className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-slate-300 text-left">
            <th className="py-1 pr-2">close</th>
            <th className="py-1 pr-2">total, bp of NAV</th>
            <th className="py-1 pr-2">factor</th>
            <th className="py-1 pr-2">stock-specific</th>
            <th className="py-1 pr-2">cost</th>
            <th className="py-1 pr-2">{UNEXPLAINED_LABEL[live ? "live" : "backtest"].short}</th>
            <th className="py-1">check</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((day, index) => (
            <DayRow
              key={`${day.trade_date ?? "day"}-${index}`}
              day={day}
              period={period}
              snapshot={snapshot}
            />
          ))}
        </tbody>
      </table>
      {newest.length > 10 ? (
        <button
          type="button"
          data-toggle="days"
          onClick={() => setShowAll((current) => !current)}
          className="mt-1 rounded bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-800 hover:bg-slate-200"
        >
          {showAll ? "show the last 10 days" : `show all ${newest.length} days`}
        </button>
      ) : null}
      <p className="mt-1 text-xs text-slate-500" data-cost-legend="true">
        Every figure is bp of NAV. <span className="rounded bg-slate-200 px-1">est</span> is a day
        whose cost is the evening&apos;s estimate; an untagged day&apos;s cost is measured from the
        fills
        {period
          ? `, and ${count(period.cost.n_realized)} of ${count(period.n_days_carried)} days here have one`
          : ""}
        .
      </p>
    </div>
  );
}

/**
 * Today's predicted-risk split and its path since the period opened, and the
 * hedge's own effect beside it.
 *
 * The hedge drives the traded book's factor exposure to zero, so the factor share
 * of predicted variance is a rounding-error-sized slice and the idio share is
 * nearly all of it; the chart is stacked from the factor share up to the idio
 * share so the two always read as the whole. The prose states what the near-zero
 * factor share means, because a 0.0% on its own reads like a missing number.
 *
 * That split is flat by design, which is the point and also its limitation: a
 * section that only showed it would say nothing about what the hedge bought. The
 * same forecast is therefore stated and drawn at both books - the sized book the
 * hedge acted on and the book that was held - so the hedge reads as the difference
 * it is rather than as a line pinned at 100%.
 */
/**
 * What the hedge removed, as a waterfall: the book before it, the points it took
 * out, and the book after.
 *
 * The brief's three numbers, in order: the sized book at 8.6% annual volatility, the
 * 5.9 points the hedge removed, and the 2.7% the book carries. The middle bar is the
 * one no other panel drew: the difference is a quantity in the same units as the two
 * ends, so drawing it beside them is the whole point. On the live 11-11 close the
 * same three read 8.9%, 6.2 points and 2.7%.
 */
export function HedgeWaterfall({ before, after }: { before: number; after: number }) {
  const removed = before - after;
  const scale = Math.max(before, after, 0.0001);
  const at = (value: number): number =>
    Math.min(100, Math.max(0, (Math.max(0, value) / scale) * 100));
  const end = (value: number): { left: string } => ({ left: `${at(value)}%` });
  const step = (key: string, word: string, value: string, bar: ReactNode, endValue: number) => (
    <div className="flex items-center gap-2" data-waterfall-step={key}>
      <span className="w-32 shrink-0 text-slate-600">{word}</span>
      {/* One scale for all three rows. The label sits at the bar's own end, so the
          reader sees after plus removed meet the end of before without arithmetic. */}
      <span className="relative mr-12 h-3 flex-1 rounded-sm bg-slate-100" data-waterfall-track={key}>
        {bar}
        <span
          data-waterfall-value={key}
          style={end(endValue)}
          className="absolute top-1/2 -translate-y-1/2 whitespace-nowrap pl-1 font-mono text-[10px] tabular-nums text-slate-700"
        >
          {value}
        </span>
      </span>
    </div>
  );
  return (
    <div className="mt-2 flex flex-col gap-1 text-xs" data-waterfall="true">
      {step(
        "before",
        "before the hedge",
        volPct(before),
        <span
          data-waterfall-bar="before"
          className="absolute left-0 top-0 h-full rounded-sm bg-slate-500"
          style={{ width: `${at(before)}%` }}
        />,
        before,
      )}
      {step(
        "removed",
        "removed by the hedge",
        `${removed >= 0 ? "-" : "+"}${(Math.abs(removed) * 100).toFixed(1)} pts`,
        <span
          data-waterfall-bar="removed"
          className="absolute top-0 h-full rounded-sm bg-rose-300"
          style={{ left: `${at(after)}%`, width: `${at(before) - at(after)}%` }}
        />,
        before,
      )}
      {step(
        "after",
        "after the hedge",
        volPct(after),
        <span
          data-waterfall-bar="after"
          className="absolute left-0 top-0 h-full rounded-sm bg-emerald-500"
          style={{ width: `${at(after)}%` }}
        />,
        after,
      )}
    </div>
  );
}

/**
 * The corrections to these series, in the words the reader is owed.
 *
 * Three moments changed what the charts below mean: the two opening sessions were
 * built before the hedge was complete, the 10-20 fix moved every earlier point, and
 * the 10-21 refill re-priced eight days of cost. A reader comparing a session with
 * the one before it needs each of those at the date it happened, so the numbers are
 * drawn on the charts and the same three statements are listed under the panel. The
 * list order is the marker number, which is what keeps the two together.
 *
 * The words live here rather than in the payload because they are page copy: the
 * evening's stored notes are the record other readers use, and these are the
 * sentences the owner asked this panel to carry.
 */
type Correction = { number: number; dates: string[]; text: string };

const CORRECTIONS: Correction[] = [
  {
    number: 1,
    dates: ["2026-09-28", "2026-09-29"],
    text:
      "The first two days (09-28 and 09-29) the book was still being built and not " +
      "fully hedged, so their predicted volatility can't be compared with later days.",
  },
  {
    number: 2,
    dates: ["2026-10-20"],
    text:
      "On 10-20 a formula error in the before-hedge volatility was fixed and every " +
      "earlier day recomputed. The line before 10-20 is lower than it was first drawn.",
  },
  {
    number: 3,
    dates: ["2026-10-21"],
    text:
      "On 10-21, trading costs for 10-09 to 10-20 were recomputed from the actual " +
      "fills (they had been estimated before the fills arrived). Those days' cost, " +
      "P&L and realized volatility changed slightly.",
  },
  {
    number: 4,
    dates: ["2026-10-27"],
    text:
      "Hold days since 10-27 show about 1.4 bp of cost each; borrow is over-charged " +
      "on those days. The fix and restatement come after the 11-23 rebalance.",
  },
];

/**
 * The dates a chart draws: its own sessions, plus the days a correction names.
 *
 * A correction about a day before the first plotted session still has to be findable
 * at its date, so the axis carries that date as an empty slot and the marker sits on
 * it. Nothing is invented: a slot with no value draws no point.
 */
const chartDates = (dates: string[]): string[] => {
  const all = new Set(dates.filter((date) => date !== ""));
  for (const correction of CORRECTIONS) {
    for (const date of correction.dates) all.add(date);
  }
  return [...all].sort();
};

/**
 * The marker's own size, and the stagger that keeps two notes apart.
 *
 * A 14px circle is small enough to sit on a chart without hiding a line and large
 * enough to be tapped. Notes 2 and 3 are one session apart (10-20 and 10-21), so
 * their circles would overlap on the same row: note 3 is drawn one marker lower.
 * Note 1 covers two sessions and carries ONE marker, drawn across both.
 */
const MARKER_RADIUS = 7;
const MARKER_OFFSET: Record<number, number> = { 1: 0, 2: 0, 3: 16 };

/**
 * How many viewBox units make one screen pixel in a chart that scales to its box.
 *
 * The charts are drawn in a 320 unit viewBox and stretched to the column, so a
 * radius written in viewBox units grows on a wide screen. A 14px footnote marker
 * has to stay 14px, so the marker's geometry is divided by the rendered scale.
 * jsdom has no layout and no ResizeObserver, where the scale stays 1.
 */
function useChartScale(): [RefObject<SVGSVGElement | null>, number] {
  const ref = useRef<SVGSVGElement | null>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const measure = (): void => {
      const width = node.getBoundingClientRect().width;
      if (width > 0) setScale(Math.min(4, Math.max(0.1, 320 / width)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, scale];
}

/** A numbered correction marker, at the dates it is about, opened by a click. */
function Marker({
  xs,
  dates,
  top,
  height,
  number,
  scale,
  open,
  onOpen,
}: {
  /** The x position of every date the note covers, in axis order. */
  xs: number[];
  dates: string[];
  top: number;
  height: number;
  number: number;
  /** viewBox units per screen pixel, so the marker keeps its 14px size. */
  scale: number;
  open: boolean;
  onOpen: () => void;
}) {
  const left = Math.min(...xs);
  const right = Math.max(...xs);
  const cx = (left + right) / 2;
  const offset = MARKER_OFFSET[number] ?? 0;
  const radius = MARKER_RADIUS * scale;
  // The stagger is a screen size too: 16px apart keeps the 14px circles clear.
  const cy = top + radius + offset * scale;
  const span = dates.length > 1 ? `${dates[0]} to ${dates[dates.length - 1]}` : dates[0];
  return (
    <g
      data-note-marker={number}
      data-note-marker-date={dates[0]}
      data-note-marker-dates={dates.join(",")}
      data-marker-offset={offset}
      data-marker-scale={scale}
      data-marker-diameter={MARKER_RADIUS * 2}
      role="button"
      tabIndex={0}
      aria-label={`correction ${number} on ${span}`}
      aria-expanded={open}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
      className="cursor-pointer"
    >
      <title>{`correction ${number}, ${span}`}</title>
      {xs.map((x) => (
        <line
          key={x}
          x1={x}
          y1={top}
          x2={x}
          y2={top + height}
          stroke="#475569"
          strokeWidth="0.8"
          strokeDasharray="2 2"
        />
      ))}
      {dates.length > 1 ? (
        <line
          x1={left}
          y1={cy}
          x2={right}
          y2={cy}
          stroke="#475569"
          strokeWidth="1.2"
          strokeLinecap="round"
        />
      ) : null}
      <circle cx={cx} cy={cy} r={radius} fill={open ? "#0f172a" : "#475569"} />
      <text x={cx} y={cy + 3 * scale} textAnchor="middle" fontSize={8 * scale} fill="#ffffff">
        {number}
      </text>
    </g>
  );
}

/** Every correction marker whose date falls on a chart's axis. */
function ChartMarkers({
  dates,
  x,
  top,
  height,
  scale,
  open,
  setOpen,
}: {
  dates: string[];
  x: (index: number) => number;
  top: number;
  height: number;
  scale: number;
  open: number | null;
  setOpen: (number: number | null) => void;
}) {
  return (
    <>
      {CORRECTIONS.map((correction) => {
        const present = correction.dates.filter((date) => dates.includes(date));
        if (present.length === 0) return null;
        return (
          <Marker
            key={correction.number}
            xs={present.map((date) => x(dates.indexOf(date)))}
            dates={present}
            top={top}
            height={height}
            number={correction.number}
            scale={scale}
            open={open === correction.number}
            onOpen={() => setOpen(open === correction.number ? null : correction.number)}
          />
        );
      })}
    </>
  );
}

/** A correction's text, opened at the marker that carries its number. */
function CorrectionPopover({ correction, left }: { correction: Correction; left: number }) {
  return (
    <div
      role="dialog"
      aria-label={`correction ${correction.number}`}
      data-correction-text={correction.number}
      style={{ left: `${Math.min(90, Math.max(10, left))}%`, top: "2rem" }}
      className="absolute z-20 w-64 -translate-x-1/2 rounded border border-slate-300 bg-white p-2 text-xs leading-snug text-slate-700 shadow-lg"
    >
      {correction.text}
    </div>
  );
}

/** Where a correction's popover should sit on a 320 wide chart. */
const popoverLeft = (
  dates: string[],
  number: number | null,
  x: (index: number) => number,
): number => {
  const correction = CORRECTIONS.find((entry) => entry.number === number);
  const present = (correction?.dates ?? []).filter((entry) => dates.includes(entry));
  // A note that covers a run of sessions opens over the middle of the run, not
  // over its first date: the marker is drawn there, and the text should follow it.
  const centres = present.map((entry) => x(dates.indexOf(entry)));
  const centre = centres.length > 0 ? centres.reduce((a, b) => a + b, 0) / centres.length : 0;
  return (centre / 320) * 100;
};

/** The same three corrections as words, under the panel whose charts they qualify. */
function Corrections() {
  return (
    <div data-corrections="true" className="mt-2 text-xs text-slate-600">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Corrections
      </h3>
      <ol data-notes="true" aria-label="corrections to these charts" className="mt-1 space-y-1">
        {CORRECTIONS.map((correction) => (
          <li
            key={correction.number}
            data-note={correction.dates[0]}
            data-note-dates={correction.dates.join(",")}
            className="flex gap-1"
          >
            <span className="mt-px inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-slate-600 text-[9px] text-white">
              {correction.number}
            </span>
            <span>{correction.text}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function RiskSplit({ risk }: { risk: AttributionRisk }) {
  const before = risk.pre_hedge_vol;
  const after = risk.hedged_vol;
  const removed = before === null || after === null ? null : before - after;
  const share = removed === null || !before ? null : removed / before;
  // The envelope, not a chart: it holds the two pictures, each of which carries its
  // own axis, caption and legend. Giving the envelope a legend of its own would name
  // series it does not draw.
  return (
    <div className="mt-3" data-chart="risk">
      <p className="text-sm text-slate-700" data-vol="line">
        Before the hedge, the sized book&apos;s predicted annual volatility was{" "}
        <span className="font-mono tabular-nums">{volPct(before)}</span>. It carried{" "}
        <span className="font-mono tabular-nums">{volPct(after)}</span>.
      </p>
      {before !== null && after !== null ? (
        <HedgeWaterfall before={before} after={after} />
      ) : null}
      <p className="mt-1 text-sm text-slate-700" data-var-share="line">
        <span data-var-share="factor">{percent(risk.factor_share, 1)}</span> of the risk that
        remains comes from factors and{" "}
        <span data-var-share="idio">{percent(risk.idio_share, 1)}</span> from the stocks
        themselves.
        <HowToRead>
          the two shares add up to the whole of the book&apos;s predicted risk, after the
          hedge. The traded book is hedged to be factor-neutral, so the factor share is
          near zero: that is the hedge&apos;s residue, not its size. What it removed is the
          waterfall above. Example: on {dateOnly(risk.as_of) ?? "the last close"} factors
          were {percent(risk.factor_share, 1)} and the stocks{" "}
          {percent(risk.idio_share, 1)}.
        </HowToRead>
      </p>
      {risk.path.length >= 2 ? <HedgeVol path={risk.path} /> : null}
      {risk.factor_share !== null &&
      risk.factor_share !== undefined &&
      risk.factor_share > 0.05 &&
      risk.path.length >= 2 ? (
        <RiskPath path={risk.path} />
      ) : null}
    </div>
  );
}

/**
 * The two forecasts the hedge stands between, over the period.
 *
 * The upper line is the annualized volatility of the sized book the hedge acted on,
 * the lower one is the book that was held, and the shaded band between them is the
 * risk the hedge removed. Both are read off one covariance and one design, which is
 * what makes the band a measurement rather than a comparison of two vintages.
 */
function HedgeVol({ path }: { path: AttributionRiskPath[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const [svgRef, scale] = useChartScale();
  const W = 320;
  const H = 110;
  const L = 30;
  const R = 8;
  const T = 8;
  const B = 18;
  const pw = W - L - R;
  const ph = H - T - B;
  const byDate = new Map(path.map((point) => [dateOnly(point.trade_date) ?? "", point]));
  const dates = chartDates(path.map((point) => dateOnly(point.trade_date) ?? ""));
  const before = dates.map((date) => byDate.get(date)?.pre_hedge_vol ?? null);
  const after = dates.map((date) => byDate.get(date)?.hedged_vol ?? null);
  const measured = before.filter((value): value is number => value !== null);
  const top = Math.max(...measured, 0.005) * 1.08;
  const x = (index: number): number =>
    dates.length <= 1 ? L + pw / 2 : L + (index / (dates.length - 1)) * pw;
  const y = (value: number): number => T + (1 - Math.min(value / top, 1)) * ph;
  const line = (values: Array<number | null>): string =>
    values
      .map((value, index) => (value === null ? null : `${x(index)},${y(value)}`))
      .filter((point): point is string => point !== null)
      .join(" ");
  // The band is shaded only where both lines have a value: a session with no forecast
  // has no removed risk to shade, and shading it to zero would draw one.
  const paired = dates
    .map((_, index) => index)
    .filter((index) => before[index] !== null && after[index] !== null);
  const band = [
    ...paired.map((index) => `${x(index)},${y(before[index] as number)}`),
    ...[...paired].reverse().map((index) => `${x(index)},${y(after[index] as number)}`),
  ].join(" ");
  const correction = CORRECTIONS.find((entry) => entry.number === open) ?? null;

  return (
    <figure className="relative mt-2" data-chart="hedge-vol">
      <figcaption className="text-xs text-slate-500">
        predicted annual volatility, % annualized, by session
      </figcaption>
      <svg
        ref={svgRef}
        className="mt-1 h-auto"
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label="predicted annual volatility before and after the hedge"
      >
      {[0, 0.5, 1].map((tick, index) => (
        <g key={index}>
          <line x1={L} y1={y(tick * top)} x2={W - R} y2={y(tick * top)} stroke="#e2e8f0" strokeWidth="1" />
          <text x={L - 4} y={y(tick * top) + 3} textAnchor="end" fontSize="8" fill="#64748b">
            {`${(tick * top * 100).toFixed(1)}%`}
          </text>
        </g>
      ))}
      <polygon data-series="removed" points={band} fill="#94a3b8" fillOpacity="0.25" />
      <polyline
        data-series="pre-hedge"
        points={line(before)}
        fill="none"
        stroke={COLORS.factor}
        strokeWidth="1.4"
      />
      <polyline
        data-series="hedged"
        points={line(after)}
        fill="none"
        stroke={COLORS.idio}
        strokeWidth="1.4"
      />
      <ChartMarkers dates={dates} x={x} top={T} height={ph} open={open} setOpen={setOpen} scale={scale} />
      <text x={L} y={H - 5} textAnchor="start" fontSize="8" fill="#64748b">
        {dates[0] ?? ""}
      </text>
      <text x={W - R} y={H - 5} textAnchor="end" fontSize="8" fill="#64748b">
        {dates[dates.length - 1] ?? ""}
      </text>
      </svg>
      {correction ? (
        <CorrectionPopover correction={correction} left={popoverLeft(dates, open, x)} />
      ) : null}
      <Legend
        entries={[
          {
            key: "pre-hedge",
            word: "sized book, before the hedge",
            color: COLORS.factor,
            dash: "",
          },
          { key: "hedged", word: "book held, after the hedge", color: COLORS.idio, dash: "" },
          { key: "removed", word: "removed by the hedge", color: "#94a3b8", dash: "", shape: "patch" },
        ]}
      />
      <p className="mt-1 text-xs text-slate-500">
        the two opening sessions carry one marker and no line: this period&apos;s own
        record starts on 10-01, and note 1 says why those two days cannot be compared with
        it.
      </p>
    </figure>
  );
}

function RiskPath({ path }: { path: AttributionRiskPath[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const [svgRef, scale] = useChartScale();
  const W = 320;
  const H = 110;
  const L = 30;
  const R = 8;
  const T = 8;
  const B = 18;
  const pw = W - L - R;
  const ph = H - T - B;
  const byDate = new Map(path.map((point) => [dateOnly(point.trade_date) ?? "", point]));
  const dates = chartDates(path.map((point) => dateOnly(point.trade_date) ?? ""));
  const x = (index: number): number =>
    dates.length <= 1 ? L + pw / 2 : L + (index / (dates.length - 1)) * pw;
  const y = (value: number): number => T + (1 - value) * ph;
  const bands = dates.map((date) => {
    const point = byDate.get(date);
    const factor = Math.max(0, Math.min(1, point?.factor_share ?? 0));
    const idio = Math.max(0, Math.min(1, point?.idio_share ?? 0));
    return { factor, top: Math.min(1, factor + idio) };
  });
  const correction = CORRECTIONS.find((entry) => entry.number === open) ?? null;
  const line = (values: number[]): string =>
    values.map((value, index) => `${x(index)},${y(value)}`).join(" ");
  const polygon = (upper: number[], lower: number[]): string =>
    [
      ...upper.map((value, index) => `${x(index)},${y(value)}`),
      ...lower.map((value, index) => `${x(index)},${y(value)}`).reverse(),
    ].join(" ");

  return (
    <figure className="mt-2" data-chart="risk-path">
      <figcaption className="text-xs text-slate-500">
        share of predicted variance, % of the book&apos;s predicted variance, by session
      </figcaption>
      <svg
        ref={svgRef}
        className="mt-1 h-auto"
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label="share of predicted variance, factors and idiosyncratic"
      >
      {[0, 0.5, 1].map((tick, index) => (
        <g key={index}>
          <line x1={L} y1={y(tick)} x2={W - R} y2={y(tick)} stroke="#e2e8f0" strokeWidth="1" />
          <text x={L - 4} y={y(tick) + 3} textAnchor="end" fontSize="8" fill="#64748b">
            {`${(tick * 100).toFixed(0)}%`}
          </text>
        </g>
      ))}
      <polygon
        data-series="idio"
        points={polygon(
          bands.map((band) => band.top),
          bands.map((band) => band.factor),
        )}
        fill={COLORS.idio}
        fillOpacity="0.35"
        stroke={COLORS.idio}
        strokeWidth="1"
      />
      <polygon
        data-series="factor"
        points={polygon(
          bands.map((band) => band.factor),
          bands.map(() => 0),
        )}
        fill={COLORS.factor}
        fillOpacity="0.6"
        stroke={COLORS.factor}
        strokeWidth="1"
      />
      <ChartMarkers dates={dates} x={x} top={T} height={ph} open={open} setOpen={setOpen} scale={scale} />
      <text x={L} y={H - 5} textAnchor="start" fontSize="8" fill="#64748b">
        {dates[0] ?? ""}
      </text>
      <text x={W - R} y={H - 5} textAnchor="end" fontSize="8" fill="#64748b">
        {dates[dates.length - 1] ?? ""}
      </text>
      </svg>
      {correction ? (
        <CorrectionPopover correction={correction} left={popoverLeft(dates, open, x)} />
      ) : null}
      <Legend
        entries={[
          { key: "factor", word: "from factors", color: COLORS.factor, dash: "", shape: "patch" },
          { key: "idio", word: "idiosyncratic", color: COLORS.idio, dash: "", shape: "patch" },
        ]}
      />
    </figure>
  );
}

/**
 * How the cost term is built, which is not the same number every day.
 *
 * The realized cost is measured from the previous close to the fill, which is the
 * trade the loop actually made - the leg is sent after one close and fills at the
 * next open - so most of it *is* the overnight gap rather than the spread. The one
 * number it can be compared against is the expectation's trading half, because
 * that is the half of the cost a fill price pays: spread, impact and commission.
 * Borrow is the short leg's holding cost over the horizon, no execution price pays
 * a calendar, so it is reported beside the comparison rather than inside it.
 */
function CostLine({ period, snapshot }: { period: AttributionPeriod; snapshot?: Snapshot }) {
  const realized = period.cost.realized_bps;
  const trading = period.cost.expected_trading_bps;
  const borrow = period.cost.expected_borrow_bps;
  const expected = period.cost.expected_bps;
  const fills = snapshot?.actual_holdings?.fills ?? null;
  const session = fills?.realized_cost_bps ?? null;
  return (
    <div className="mt-2 text-xs text-slate-600" data-cost="line">
      <p>
        The evening expected to pay{" "}
        <span className="font-medium">{costBps(expected)}</span>
        {trading === null ? "" : `: ${trading.toFixed(1)} bp of trading`}
        {borrow === null ? "" : ` and ${borrow.toFixed(1)} bp of borrow`}
        {trading === null || borrow === null ? "" : " to hold the shorts"}.
        {session === null
          ? ""
          : ` The fills cost ${session.toFixed(1)} bp against the ${trading === null ? "expected trading" : `${trading.toFixed(1)} bp of trading`} that was expected for them.`}
      </p>
      <p className="mt-1">
        {realized === null
          ? "No measured fill cost is on file for this period."
          : `Average cost per day with fills: ${costBps(
              realized,
            )}, measured over ${count(period.cost.n_realized)} of ${count(
              period.n_days_carried,
            )} days.`}{" "}
        It is measured from the previous close to the fill, so it carries the overnight move with
        it and can be positive. A fill that beat the close is a gain, not a cost.
      </p>
    </div>
  );
}

/** The close that began the monthly cadence, and the boundary between cost eras. */
const CADENCE_SWITCH = "2026-10-23";

/**
 * The cost, split by the cadence it was paid under.
 *
 * The live cost card sums every session since go-live, and the book traded daily
 * until 2026-10-23. A reader who takes that total for the price of the monthly
 * cadence is reading a daily era's bill as the guard's. Three figures fix that: the
 * daily era up to the switch, the monthly era from it, and the drift guard's own
 * cost inside the second. The guard's figure is an estimate at the book's own
 * trading rate, because the store prices the guard's legs but does not post a cost
 * for them; it is stated as an estimate rather than given a precision it lacks.
 */
function CostEras({ period, snapshot }: { period: AttributionPeriod; snapshot?: Snapshot }) {
  const nav =
    snapshot?.book?.gross && snapshot?.book?.gross_notional
      ? snapshot.book.gross_notional / snapshot.book.gross
      : null;
  const rows = period.daily ?? [];
  const sum = (predicate: (day: AttributionDay) => boolean): number =>
    rows.reduce((total, day) => total + (predicate(day) ? day.pnl_cost ?? 0 : 0), 0);
  const dailyEra = sum((day) => (dateOnly(day.trade_date) ?? "") < CADENCE_SWITCH);
  const monthlyEra = sum((day) => (dateOnly(day.trade_date) ?? "") >= CADENCE_SWITCH);
  const guard = (snapshot?.monthly?.since_anchor?.trades_by_reason ?? []).find(
    (row) => row.reason === "guard",
  );
  const split = snapshot?.book?.expected_cost_split ?? null;
  const turnover =
    snapshot?.reconciliation?.sent_notional ?? snapshot?.reconciliation?.intended_notional ?? null;
  const rebalance = snapshot?.monthly?.rebalance_card ?? null;
  // A cost rate is bp of NAV per dollar traded. The day's own trading half and the
  // dollars it was quoted on give that rate; the guard's dollars then convert at it.
  // A hold day prices only borrow, so a zero trading half is not a rate: the anchor
  // rebalance's expected cost stands in then, and the figure is labelled an estimate.
  const guardBp = !guard
    ? null
    : split?.trading && turnover
      ? (guard.usd * split.trading) / turnover
      : rebalance?.expected_cost_bps && rebalance.pct_nav && nav
        ? (guard.usd * rebalance.expected_cost_bps) / (rebalance.pct_nav * nav)
        : null;
  const guardUsd = guard ? Math.abs(guard.usd) : null;
  // The same legs, measured from the fills: four guard days' cost added up is what
  // the guard actually cost, while `guardBp` is what the trading rate predicts. The
  // page used to print the estimate alone, positive, a few lines under cards whose
  // measured costs add to 6.3 bp.
  const guardMeasured = (snapshot?.monthly?.since_anchor?.guard_history ?? []).reduce(
    (total, firing) => total + (firing.cost_bps ?? 0),
    0,
  );
  const guardMeasuredKnown = (snapshot?.monthly?.since_anchor?.guard_history ?? []).some(
    (firing) => firing.cost_bps !== null,
  );
  const figure = (value: number | null): string =>
    value === null ? "n/a" : `${value >= 0 ? "+" : ""}${(value * 1e4).toFixed(1)} bp`;
  const amount = (value: number | null): string =>
    value === null || nav === null ? "" : dollars(value * nav);
  return (
    <section data-cost="eras" className="mt-2 rounded border border-slate-200 bg-white px-2 py-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        cost by era
        <HowToRead>
          The book traded every day until 10-23 and every 21 sessions after it, so the cost
          column is two different regimes and one average would hide the change. The guard
          row is the share of the monthly era that the drift repairs spent. Example: the
          daily era took {figure(dailyEra)} and the monthly one {figure(monthlyEra)}.
        </HowToRead>
      </h3>
      <dl className="mt-1 grid grid-cols-3 gap-2 text-xs">
        <div data-cost-era="daily">
          <dt className="text-slate-500">daily trading, to 10-23</dt>
          <dd className="font-mono text-sm font-semibold tabular-nums">{figure(dailyEra)}</dd>
          <dd className="font-mono tabular-nums text-slate-600">{amount(dailyEra)}</dd>
        </div>
        <div data-cost-era="monthly">
          <dt className="text-slate-500">monthly cadence, since 10-23</dt>
          <dd className="font-mono text-sm font-semibold tabular-nums">{figure(monthlyEra)}</dd>
          <dd className="font-mono tabular-nums text-slate-600">{amount(monthlyEra)}</dd>
        </div>
        <div data-cost-era="guard">
          <dt className="text-slate-500">drift guard, since 10-23</dt>
          <dd className="font-mono text-sm font-semibold tabular-nums">
            {guardBp === null ? "n/a" : `${guardBp <= 0 ? "" : "-"}${Math.abs(guardBp).toFixed(2)} bp`}{" "}
            estimated
          </dd>
          <dd className="font-mono tabular-nums text-slate-600">
            {guardMeasuredKnown ? `-${guardMeasured.toFixed(1)} bp measured from fills` : "not measured"}
            {guardBp === null || nav === null
              ? ""
              : `; ${dollars((Math.abs(guardBp) / 1e4) * nav)} est., ${dollars(guardUsd)} of legs`}
          </dd>
        </div>
      </dl>
      <p className="mt-1 text-xs text-slate-500">
        The 10-23 close is the first monthly one, so it is counted there. The guard&apos;s row
        sits inside the monthly era, not beside it: the measured figure is part of the monthly
        total, and the estimate describes the same legs at the book&apos;s trading rate. They are
        two readings of one cost and are not added together.
      </p>
    </section>
  );
}

/**
 * What each factor contributed, over the period.
 *
 * The four cards say how much of the total came from the modelled factors; this says
 * which of them, which is the question that follows immediately and that the page
 * could not answer before even though the document has carried `by_factor` all along.
 * On the live book the hedge drives the traded exposures to zero, so these are the
 * hedge's own residue rather than a set of bets - small, and it is the *size* that is
 * the reading, not the sign.
 *
 * Sorted by absolute contribution, because a table in factor-name order puts the
 * largest move wherever the alphabet decides, and the sum is printed at the foot:
 * these are components of the factor P&L card above, so a reader must be able to add
 * them up and get it.
 */
function FactorTable({ period }: { period: AttributionPeriod }) {
  const entries = Object.entries(period.by_factor ?? {})
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([factor, value]) => ({ factor, value: value as number }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  const timing = period.daily.reduce((total, day) => total + (day.pnl_timing ?? 0), 0);
  if (entries.length === 0) return null;
  const added = entries.reduce((sum, entry) => sum + entry.value, 0);
  // The per-factor rows are the stored terms and they do not always add to the factor
  // card above, because the card is the stored total. The gap is a few hundredths of
  // a basis point, and printing a total the rows do not reach was the thing a reader
  // could not check. The gap gets its own row and the total is the card's own number.
  const stated = period.cumulative?.pnl_factor ?? null;
  const remainder = stated === null ? null : stated - added;
  // The rows print to a tenth of a basis point, so a remainder under half of that
  // would print as 0.0 and add a row that says nothing.
  const showRemainder = remainder !== null && Math.abs(remainder) >= 5e-6;
  const total = stated ?? added;
  const widest = Math.max(
    ...entries.map((entry) => Math.abs(entry.value)),
    ...(showRemainder ? [Math.abs(remainder as number)] : []),
    1e-12,
  );

  return (
    <div data-panel="by-factor" className="mt-3">
      <h3 className="text-sm font-semibold">
        By factor
        <HowToRead>
          Each factor&apos;s cumulative contribution over {count(period.n_days)} session(s), in
          basis points of NAV, largest first, and they sum to the factor card above. The
          small remainder that the stored per-factor terms do not explain has its own row
          rather than being folded into the total. Example: {factorWord(entries[0].factor)}{" "}
          contributed {bps(entries[0].value)}.
        </HowToRead>
      </h3>
      <table aria-label="by factor" className="mt-1 w-full text-xs">
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.factor} data-factor={entry.factor} className="border-b border-slate-100">
              <td className="py-0.5 pr-2">{factorWord(entry.factor)}</td>
              <td className="py-0.5 pr-2">
                <span
                  data-factor-bar="true"
                  className={`inline-block h-2 rounded-sm ${
                    entry.value >= 0 ? "bg-emerald-600" : "bg-rose-500"
                  }`}
                  style={{
                    width: `${Math.max(2, (Math.abs(entry.value) / widest) * 90)}px`,
                  }}
                />
              </td>
              <td className="py-0.5 text-right tabular-nums">{bps(entry.value)}</td>
            </tr>
          ))}
          {showRemainder ? (
            <tr data-factor="remainder" className="border-b border-slate-100 text-slate-600">
              <td className="py-0.5 pr-2">not attributed to a factor</td>
              <td className="py-0.5 pr-2">
                <span
                  data-factor-bar="true"
                  className={`inline-block h-2 rounded-sm ${
                    (remainder as number) >= 0 ? "bg-emerald-600" : "bg-rose-500"
                  }`}
                  style={{
                    width: `${Math.max(
                      2,
                      (Math.abs(remainder as number) / widest) * 90,
                    )}px`,
                  }}
                />
              </td>
              <td className="py-0.5 text-right tabular-nums">{bps(remainder)}</td>
            </tr>
          ) : null}
          <tr data-factor="total" className="text-slate-700">
            <td className="py-1 pr-2 font-semibold">total</td>
            <td className="py-1 pr-2" />
            <td className="py-1 text-right font-semibold tabular-nums">{bps(total)}</td>
          </tr>
        </tbody>
      </table>
      <p className="mt-1 text-xs text-slate-500">
        The hedge trades against the design the book was built with, and the risk model was
        revised during this period. The gap between the two designs accounts for {bps(timing)} in
        the period&apos;s P&amp;L.
      </p>
    </div>
  );
}

/**
 * Realized against forecast volatility, session by session.
 *
 * The one question about risk the page could not answer from its charts: the predicted
 * split and the pre/post-hedge forecast are both *model* output, so a reader could see
 * what the model believed and never whether the book did what the model said. The
 * evidence is per session and the document already carries it - `realized_vol` is the
 * book's own P&L over a rolling quarter, `forecast_vol` the model's, both annualized.
 *
 * Two things are stated rather than implied. The session count, because a volatility
 * comparison on seven sessions is an anecdote and the reader has to be able to see
 * that; and the gap's own sign, because "realized below forecast" is the reassuring
 * direction and a reader should not have to work out which is which from the lines.
 * A session with no forecast is drawn as a gap rather than as zero, because an
 * unmeasured session is not a quiet one.
 */
function VolatilityPanel({ period }: { period: AttributionPeriod }) {
  const [open, setOpen] = useState<number | null>(null);
  const [svgRef, scale] = useChartScale();
  const rows = period.daily;
  const pairs = rows.filter(
    (day) =>
      day.realized_vol !== null &&
      day.realized_vol !== undefined &&
      day.forecast_vol !== null &&
      day.forecast_vol !== undefined,
  );
  const withRealized = rows.filter(
    (day) => day.realized_vol !== null && day.realized_vol !== undefined,
  );
  if (withRealized.length === 0) {
    return (
      <div data-panel="volatility" className="mt-3">
        <h3 className="text-sm font-semibold">
          Realized against forecast volatility
          <HowToRead>
            The model&apos;s forecast against what the book actually did, session by session,
            both annualized. A realized line below the forecast means the model was cautious,
            above it means the book took more risk than it was sized for. Example: this
            period has no realized session yet, so nothing is drawn rather than drawn as zero.
          </HowToRead>
        </h3>
        <p className="mt-1 text-xs text-slate-600" data-vol="absent">
          no session of this period carries a realized volatility yet: the measure needs a
          quarter of the book&apos;s own daily P&amp;L, so it is absent on a book that has not
          been running that long rather than zero.
        </p>
      </div>
    );
  }

  const W = 320;
  const H = 120;
  const L = 34;
  const R = 8;
  const T = 8;
  const B = 18;
  const pw = W - L - R;
  const ph = H - T - B;
  const values = pairs.flatMap((day) => [day.realized_vol as number, day.forecast_vol as number]);
  const top = Math.max(...values, 0.01) * 1.1;
  const byDate = new Map(pairs.map((day) => [dateOnly(day.trade_date) ?? "", day]));
  const dates = chartDates(pairs.map((day) => dateOnly(day.trade_date) ?? ""));
  const x = (index: number): number =>
    dates.length <= 1 ? L + pw / 2 : L + (index / (dates.length - 1)) * pw;
  const y = (value: number): number => T + (1 - Math.min(value / top, 1)) * ph;
  const line = (pick: (day: AttributionDay) => number): string =>
    dates
      .map((date, index) => {
        const day = byDate.get(date);
        return day ? `${x(index)},${y(pick(day))}` : null;
      })
      .filter((point): point is string => point !== null)
      .join(" ");
  const last = pairs[pairs.length - 1];
  const correction = CORRECTIONS.find((entry) => entry.number === open) ?? null;

  return (
    <figure data-chart="volatility" data-panel="volatility" className="relative mt-3">
      <figcaption className="text-sm font-semibold">
        Realized against forecast volatility
        <HowToRead>
          The model&apos;s forecast against what the book actually did, session by session,
          both annualized. A realized line below the forecast means the model was cautious,
          above it means the book took more risk than it was sized for. Example: the last
          session realized {percent(last.realized_vol)} against a forecast of{" "}
          {percent(last.forecast_vol)}.
        </HowToRead>
      </figcaption>
      <p className="mt-1 text-xs text-slate-600">
        Annualized, per session, from the live book&apos;s own daily record.{" "}
        {count(pairs.length)} of {count(period.n_days)} session(s) carry both; the realized
        line is the book&apos;s own P&amp;L over a rolling quarter and the forecast is the
        model&apos;s.
      </p>
      <svg
        ref={svgRef}
        className="mt-1 h-auto"
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label="realized and forecast annualized volatility by session"
      >
        {[0, 0.5, 1].map((tick, index) => (
          <g key={index}>
            <line
              x1={L}
              y1={y(tick * top)}
              x2={W - R}
              y2={y(tick * top)}
              stroke="#e2e8f0"
              strokeWidth="1"
            />
            <text x={L - 4} y={y(tick * top) + 3} textAnchor="end" fontSize="8" fill="#64748b">
              {`${(tick * top * 100).toFixed(1)}%`}
            </text>
          </g>
        ))}
        <polyline
          data-series="forecast"
          points={line((day) => day.forecast_vol as number)}
          fill="none"
          stroke={COLORS.factor}
          strokeWidth="1.4"
        />
        <polyline
          data-series="realized"
          points={line((day) => day.realized_vol as number)}
          fill="none"
          stroke={COLORS.idio}
          strokeWidth="1.4"
        />
        <ChartMarkers dates={dates} x={x} top={T} height={ph} open={open} setOpen={setOpen} scale={scale} />
        <text x={L} y={H - 5} textAnchor="start" fontSize="8" fill="#64748b">
          {dates[0] ?? ""}
        </text>
        <text x={W - R} y={H - 5} textAnchor="end" fontSize="8" fill="#64748b">
          {dates[dates.length - 1] ?? ""}
        </text>
      </svg>
      {correction ? (
        <CorrectionPopover correction={correction} left={popoverLeft(dates, open, x)} />
      ) : null}
      <Legend
        entries={[
          {
            key: "realized",
            word: "realized volatility, % annualized (the book's own P&L over a rolling quarter)",
            color: COLORS.idio,
            dash: "",
          },
          {
            key: "forecast",
            word: "forecast volatility, % annualized (the model's, for the same session)",
            color: COLORS.factor,
            dash: "",
          },
        ]}
      />
      <div className="mt-1 flex flex-wrap items-baseline gap-x-3">
        <p className="text-sm tabular-nums" data-vol="last">
          the last session with both, {dateOnly(last?.trade_date) ?? "n/a"}: realized{" "}
          {volPct(last?.realized_vol)} against {volPct(last?.forecast_vol)} forecast
          {biasSentence(pairs)}
        </p>
        <p className="text-xs text-slate-600" data-vol="sample">
          Not enough live days yet to judge the model ({count(pairs.length)} of 30)
          <HowToRead>
            thirty live days is the sample the risk test needs before a bias means
            anything: below it the line above is a direction, not a verdict. Example:
            this period has {count(pairs.length)} session(s) with both a forecast and a
            realized number, so the comparison has {count(pairs.length)} points in it.
          </HowToRead>
        </p>
      </div>
    </figure>
  );
}

/** How the realized line has sat against the forecast, stated rather than left to the eye. */
function biasSentence(pairs: AttributionDay[]): string {
  const ratios = pairs.map((day) => (day.realized_vol as number) / (day.forecast_vol as number));
  const mean = ratios.reduce((total, value) => total + value, 0) / ratios.length;
  if (!Number.isFinite(mean)) return "";
  if (mean > 1.05) return `; realized has run ${((mean - 1) * 100).toFixed(0)}% above forecast on average`;
  if (mean < 0.95) return `; realized has run ${((1 - mean) * 100).toFixed(0)}% below forecast on average`;
  return "; the two have tracked each other on average";
}

/**
 * The volatility breakdown: what the book carried, what the hedge took out, and how
 * the model's forecast compared with what the book did.
 *
 * It sits between what the book earned and which factors earned it, which is the
 * order the questions are asked in: what came in, how much risk produced it, and only
 * then which of the modelled factors was behind the factor half. The corrections list
 * closes the panel because a reader who has just compared two sessions needs the days
 * that made two of them not comparable.
 */
function VolatilityGroup({ period }: { period: AttributionPeriod }) {
  const risk = period.risk ?? null;
  return (
    <section data-group="volatility" className="mt-4">
      <h3 className="text-sm font-semibold">
        Risk and volatility
        <HowToRead>
          the book&apos;s predicted risk before the hedge, the points the hedge took out,
          and the model&apos;s forecast against what the book actually did. Every figure
          is annualized, so one session compares with the next.
          {risk
            ? ` Example: the last session was sized for ${volPct(risk.pre_hedge_vol)} and held ${volPct(risk.hedged_vol)}.`
            : ""}
        </HowToRead>
      </h3>
      {risk ? <RiskSplit risk={risk} /> : null}
      <VolatilityPanel period={period} />
      <Corrections />
    </section>
  );
}

function PeriodView({
  period,
  chart,
  snapshot,
  live = false,
}: {
  period: AttributionPeriod;
  chart: "daily" | "monthly";
  snapshot?: Snapshot;
  live?: boolean;
}) {
  const cumulative = period.cumulative;
  const nav =
    snapshot?.book?.gross && snapshot.book.gross_notional
      ? snapshot.book.gross_notional / snapshot.book.gross
      : null;
  const carried = period.daily;
  const newest = [...carried].reverse();
  const lastDay = newest[0] ?? null;
  const rows =
    chart === "monthly"
      ? period.monthly.map((month) => ({
          label: dateOnly(month.month) ?? "",
          total: month.pnl_total,
          factor: month.pnl_factor,
          idio: month.pnl_idio,
          cost: month.pnl_cost,
        }))
      : carried.map((day) => ({
          label: dateOnly(day.trade_date) ?? "",
          total: day.pnl_total,
          factor: day.pnl_factor,
          idio: day.pnl_idio,
          cost: day.pnl_cost,
        }));
  const points = runningTotals(rows);
  const from = dateOnly(period.first_day);
  const to = dateOnly(period.last_day);

  return (
    <>
      <p className="mt-2 text-sm text-slate-600">
        {period.label}. {count(period.n_days_carried)} of {count(period.n_days)} session(s)
        {from && to ? `, ${from} to ${to}` : ""}.
      </p>

      {/* The flow, in the order a reader asks the questions: what the book earned,
          how much risk produced it, and only then which factors were behind it. */}
      <h3 className="mt-4 text-sm font-semibold">
        What the book earned
        <HowToRead>
          four terms that add to the total: the hedge&apos;s factor P&amp;L, the names&apos;
          own P&amp;L, what the fills cost, and the part no term explains. Every figure is
          in basis points of NAV, so a session&apos;s move is the same size whether the book
          was large or small. Example: the live book is {bps(cumulative.pnl_total)} since it
          opened. The evening run stores every row: factor P&amp;L is the book&apos;s
          exposure times the factor returns, stock-specific P&amp;L is its positions times the
          specific returns, and the four terms add to the day&apos;s total by construction.
          A row that does not add up is a stored day that does not decompose, which is what
          the check column in the table is for. The fourth term is not a fourth estimate:
          it is rounding and gaps in the stored data, and on the live book it is a few
          hundredths of a bp.
        </HowToRead>
      </h3>
      <dl className="mt-1 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3 lg:grid-cols-5">
        {[
          { hook: "total", label: "total", value: cumulative.pnl_total },
          { hook: "factor", label: "factor", value: cumulative.pnl_factor },
          { hook: "idio", label: "stock-specific", value: cumulative.pnl_idio },
          { hook: "cost", label: "cost contribution to P&L", value: cumulative.pnl_cost },
          {
            hook: "unexplained",
            label: UNEXPLAINED_LABEL[live ? "live" : "backtest"].long,
            value: cumulative.pnl_unexplained,
          },
        ].map((card) => (
          <div
            key={card.hook}
            data-card={`pnl-${card.hook}`}
            className="rounded border border-slate-100 bg-slate-50 px-2 py-1"
          >
            <dt className="break-words text-xs uppercase tracking-wide text-slate-500">
              {card.label}
            </dt>
            <dd className={`font-mono tabular-nums ${pnlClass(card.value)}`}>{bps(card.value)}</dd>
            <dd className="font-mono text-xs tabular-nums text-slate-500">
              {card.value === null || nav === null ? "" : dollars(card.value * nav)}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-1 text-xs text-slate-500">
        worst single day's identity residual: {bps(cumulative.max_identity_residual)}, over{" "}
        {count(cumulative.n_computed_specific)} name-day(s) whose residual was computed rather than
        stored.
      </p>

      {points.length >= 1 ? (
        <CumulativeChart
          points={points}
          rebalances={snapshot?.monthly?.rebalance_dates ?? []}
        />
      ) : null}
      {live ? <DailyBars days={carried} /> : null}
      <CostLine period={period} snapshot={snapshot} />
      {live ? <CostEras period={period} snapshot={snapshot} /> : null}

      <DayTable
        days={carried}
        label="attribution by day"
        period={period}
        snapshot={snapshot}
        live={live}
      />
      {lastDay ? (
        <p className="mt-1 text-xs text-slate-500" data-beta="book">
          On {dateOnly(lastDay.trade_date) ?? "the last day"} the book barely moved with the
          market: a {bps(lastDay.market_return)} market day moved it{" "}
          {bps(lastDay.pnl_beta)} (beta {beta3(lastDay.book_beta)}).
        </p>
      ) : null}

      {live ? <VolatilityGroup period={period} /> : null}
      <FactorTable period={period} />
    </>
  );
}

export function AttributionSection({
  attribution,
  snapshot,
}: {
  attribution?: Attribution | null;
  /** The document the fills come from, so a day's cost can be called measured. */
  snapshot?: Snapshot;
}) {
  // The view is a decision about which object to read, so it is the one piece of
  // state here; it defaults to the live book, which is the only one that is the book.
  const [view, setView] = useState<"live" | "backtest">("live");
  // A document written before the attribution step carries no block at all, and
  // one is in the bucket right now: the section hides itself rather than drawing an
  // empty one, the rule every other section here follows.
  if (!attribution) return null;

  const live = attribution.live;
  const backtest = attribution.backtest;
  const emptyLive = !live || live.n_days === 0;
  const tabClass = (active: boolean): string =>
    `rounded px-2 py-1 text-sm font-semibold ${
      active ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-800 hover:bg-slate-200"
    }`;

  return (
    <section
      data-section="attribution"
      data-view={view}
      className="rounded border border-slate-200 bg-white p-3"
    >
      <h2 className="text-lg font-semibold">Attribution <HowToRead>
        basis points of NAV, so a figure is one hundredth of a percent of the book
        and two sessions compare even as it grows. Example: realized cost ran 7.31
        bp a session over the live track against 8.51 bp expected.
      </HowToRead></h2>
      <p className="mt-1 text-sm text-slate-600">
        What the book earned, split into the four terms that add to its total: the hedge&apos;s
        factor P&amp;L, the names&apos; idiosyncratic P&amp;L, the cost contribution to P&amp;L,
        and the unexplained remainder. Every figure is in bp of NAV.
      </p>
      {/* The switch only exists when there are two objects to switch between: a
          second tab that opens nothing is worse than no tab. */}
      {backtest ? (
        <div className="mt-2 flex flex-wrap gap-1" role="tablist" aria-label="attribution view">
          <button
            type="button"
            role="tab"
            data-tab="live"
            aria-selected={view === "live"}
            onClick={() => setView("live")}
            className={tabClass(view === "live")}
          >
            the live book
          </button>
          <button
            type="button"
            role="tab"
            data-tab="backtest"
            aria-selected={view === "backtest"}
            onClick={() => setView("backtest")}
            className={tabClass(view === "backtest")}
          >
            the research panel (backtest)
          </button>
        </div>
      ) : null}

      {view === "backtest" && backtest ? (
        <>
          {/* The paragraph that used to sit in the Operations notes now explains this
              panel where the panel is: it is about the object the reader is looking at,
              not about the book. */}
          <h3 className="mt-3 text-sm font-semibold" data-panel="backtest">
            the research panel (backtest)
            <HowToRead>
              this is a backtest of the seed book, not the live book. Nobody traded it, so
              its cost is exactly zero, and its fourth term is a research-vintage mismatch
              rather than a loss anyone took.
            </HowToRead>
          </h3>
          <PeriodView period={backtest} chart="monthly" />
        </>
      ) : emptyLive ? (
        <p className="mt-2 text-sm text-slate-600" data-empty="live">
          {live?.note || attribution.note || "no live day is attributed yet"}
        </p>
      ) : live ? (
        <PeriodView period={live} chart="daily" snapshot={snapshot} live />
      ) : null}
    </section>
  );
}
