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

import { useState } from "react";

import { Details } from "./Details";
import { count, dateOnly, percent } from "./format";
import type {
  Attribution,
  AttributionDay,
  AttributionNote,
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
  { key: "idio", word: "idio", color: COLORS.idio, dash: "1 3" },
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
    long: "unexplained (the stored artifacts do not reproduce the panel's own return)",
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
        aria-label="cumulative P&L: total, factor, idio and cost"
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
            <th className="py-1 pr-2">idio</th>
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
function RiskSplit({ risk, notes }: { risk: AttributionRisk; notes: AttributionNote[] }) {
  const before = risk.pre_hedge_vol;
  const after = risk.hedged_vol;
  const removed = before === null || after === null ? null : before - after;
  const share = removed === null || !before ? null : removed / before;
  // The envelope, not a chart: it holds the two pictures, each of which carries its
  // own axis, caption and legend. Giving the envelope a legend of its own would name
  // series it does not draw.
  return (
    <div className="mt-3" data-chart="risk">
      <p className="text-xs text-slate-500">
        predicted variance, as of {dateOnly(risk.as_of) ?? "n/a"}, % of the book&apos;s predicted
        variance
      </p>
      <p className="mt-1 text-sm tabular-nums">
        <span data-var-share="factor">{percent(risk.factor_share, 1)}</span> from factors,{" "}
        <span data-var-share="idio">{percent(risk.idio_share, 1)}</span> idiosyncratic.
      </p>
      {risk.path.length >= 2 ? <RiskPath path={risk.path} notes={notes} /> : null}
      <p className="mt-1 text-xs text-slate-500">
        The traded book is hedged to be factor-neutral, so the factor share sits near zero - under
        6% across the live period - and almost all of the predicted risk is idiosyncratic. That is
        the hedge's residue and not its size: what it removed is the gap between the two books
        below.
      </p>
      <p className="mt-2 text-sm tabular-nums" data-vol="line">
        predicted annual volatility {volPct(after)} after the hedge, from {volPct(before)} before it
        {removed === null || share === null
          ? ""
          : ` - the hedge removed ${(removed * 100).toFixed(1)} points, ${(share * 100).toFixed(
              0,
            )}% of the sized book's risk`}
        .
      </p>
      {risk.path.length >= 2 && before !== null && after !== null ? (
        <HedgeVol path={risk.path} notes={notes} />
      ) : null}
      <Notes notes={notes} />
    </div>
  );
}

/**
 * The dates a note falls on, numbered as the list below the charts numbers them.
 *
 * A note whose date is not in the path is still in the list: it is a statement about
 * the series, and a chart that dropped it because the window had scrolled past it
 * would lose the record of a correction exactly when the correction is old.
 */
function noteMarkers(
  path: AttributionRiskPath[],
  notes: AttributionNote[],
): Array<{ index: number; number: number; note: AttributionNote }> {
  const dates = path.map((point) => dateOnly(point.trade_date) ?? "");
  const markers: Array<{ index: number; number: number; note: AttributionNote }> = [];
  notes.forEach((note, position) => {
    const index = dates.indexOf(dateOnly(note.date) ?? "");
    if (index >= 0) markers.push({ index, number: position + 1, note });
  });
  return markers;
}

/** A numbered marker on a chart, carrying its note's text as the accessible title. */
function Marker({
  cx,
  top,
  height,
  number,
  note,
}: {
  cx: number;
  top: number;
  height: number;
  number: number;
  note: AttributionNote;
}) {
  return (
    <g data-note-marker={number}>
      <title>{`${dateOnly(note.date) ?? "undated"}: ${note.text}`}</title>
      <line
        x1={cx}
        y1={top}
        x2={cx}
        y2={top + height}
        stroke="#475569"
        strokeWidth="0.8"
        strokeDasharray="2 2"
      />
      <circle cx={cx} cy={top + 4} r="6" fill="#475569" />
      <text x={cx} y={top + 6.5} textAnchor="middle" fontSize="7" fill="#ffffff">
        {number}
      </text>
    </g>
  );
}

/** The dated notes, numbered to match the markers on the charts. */
function Notes({ notes }: { notes: AttributionNote[] }) {
  if (notes.length === 0) return null;
  return (
    <ol className="mt-2 space-y-1 text-xs text-slate-600" data-notes="true" aria-label="notes on these charts">
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
            <span className="font-medium">{dateOnly(note.date) ?? "undated"}</span> - {note.text}
          </span>
        </li>
      ))}
    </ol>
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
function HedgeVol({ path, notes }: { path: AttributionRiskPath[]; notes: AttributionNote[] }) {
  const W = 320;
  const H = 110;
  const L = 30;
  const R = 8;
  const T = 8;
  const B = 18;
  const pw = W - L - R;
  const ph = H - T - B;
  const before = path.map((point) => point.pre_hedge_vol ?? 0);
  const after = path.map((point) => point.hedged_vol ?? 0);
  const top = Math.max(...before, 0.005) * 1.08;
  const x = (index: number): number =>
    path.length <= 1 ? L + pw / 2 : L + (index / (path.length - 1)) * pw;
  const y = (value: number): number => T + (1 - Math.min(value / top, 1)) * ph;
  const line = (values: number[]): string =>
    values.map((value, index) => `${x(index)},${y(value)}`).join(" ");
  const band = [
    ...before.map((value, index) => `${x(index)},${y(value)}`),
    ...after.map((value, index) => `${x(index)},${y(value)}`).reverse(),
  ].join(" ");

  return (
    <figure className="mt-2" data-chart="hedge-vol">
      <figcaption className="text-xs text-slate-500">
        predicted annual volatility, % annualized, by session
      </figcaption>
      <svg
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
      {noteMarkers(path, notes).map((marker) => (
        <Marker
          key={marker.number}
          cx={x(marker.index)}
          top={T}
          height={ph}
          number={marker.number}
          note={marker.note}
        />
      ))}
      <text x={L} y={H - 5} textAnchor="start" fontSize="8" fill="#64748b">
        {dateOnly(path[0]?.trade_date) ?? ""}
      </text>
      <text x={W - R} y={H - 5} textAnchor="end" fontSize="8" fill="#64748b">
        {dateOnly(path[path.length - 1]?.trade_date) ?? ""}
      </text>
      </svg>
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
    </figure>
  );
}

function RiskPath({ path, notes }: { path: AttributionRiskPath[]; notes: AttributionNote[] }) {
  const W = 320;
  const H = 110;
  const L = 30;
  const R = 8;
  const T = 8;
  const B = 18;
  const pw = W - L - R;
  const ph = H - T - B;
  const x = (index: number): number =>
    path.length <= 1 ? L + pw / 2 : L + (index / (path.length - 1)) * pw;
  const y = (value: number): number => T + (1 - value) * ph;
  const bands = path.map((point) => {
    const factor = Math.max(0, Math.min(1, point.factor_share ?? 0));
    const idio = Math.max(0, Math.min(1, point.idio_share ?? 0));
    return { factor, top: Math.min(1, factor + idio) };
  });
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
      {noteMarkers(path, notes).map((marker) => (
        <Marker
          key={marker.number}
          cx={x(marker.index)}
          top={T}
          height={ph}
          number={marker.number}
          note={marker.note}
        />
      ))}
      <text x={L} y={H - 5} textAnchor="start" fontSize="8" fill="#64748b">
        {dateOnly(path[0]?.trade_date) ?? ""}
      </text>
      <text x={W - R} y={H - 5} textAnchor="end" fontSize="8" fill="#64748b">
        {dateOnly(path[path.length - 1]?.trade_date) ?? ""}
      </text>
      </svg>
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
          : `Measured over ${count(period.cost.n_realized)} of ${count(period.n_days_carried)} days: ${costBps(realized)} on average.`}{" "}
        It is measured from the previous close to the fill, so it carries the overnight move with
        it and can be positive — a fill that beat the close is a gain, not a cost.
      </p>
    </div>
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
  const total = entries.reduce((sum, entry) => sum + entry.value, 0);
  const widest = Math.max(...entries.map((entry) => Math.abs(entry.value)), 1e-12);

  return (
    <div data-panel="by-factor" className="mt-3">
      <h3 className="text-sm font-semibold">By factor</h3>
      <p className="mt-1 text-xs text-slate-600">
        Cumulative contribution of each modelled factor over {count(period.n_days)} session(s), in
        bp of NAV, largest first. These sum to the factor card above.
      </p>
      <table aria-label="by factor" className="mt-1 w-full text-xs">
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.factor} data-factor={entry.factor} className="border-b border-slate-100">
              <td className="py-0.5 pr-2 font-mono">{entry.factor}</td>
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
          <tr data-factor="total" className="text-slate-700">
            <td className="py-1 pr-2 font-semibold">total</td>
            <td className="py-1 pr-2" />
            <td className="py-1 text-right font-semibold tabular-nums">{bps(total)}</td>
          </tr>
        </tbody>
      </table>
      <p className="mt-1 text-xs text-slate-500">
        The hedge&apos;s own timing residue over the period — the P&amp;L the gap between the two
        design vintages produced — is {bps(timing)}.
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
        <h3 className="text-sm font-semibold">Realized against forecast volatility</h3>
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
  const x = (index: number): number =>
    pairs.length <= 1 ? L + pw / 2 : L + (index / (pairs.length - 1)) * pw;
  const y = (value: number): number => T + (1 - Math.min(value / top, 1)) * ph;
  const line = (pick: (day: AttributionDay) => number): string =>
    pairs.map((day, index) => `${x(index)},${y(pick(day))}`).join(" ");
  const last = pairs[pairs.length - 1];

  return (
    <figure data-chart="volatility" data-panel="volatility" className="mt-3">
      <figcaption className="text-sm font-semibold">Realized against forecast volatility</figcaption>
      <p className="mt-1 text-xs text-slate-600">
        Annualized, per session, from <code>attribution.live.daily</code>. {count(pairs.length)} of{" "}
        {count(period.n_days)} session(s) carry both; the realized line is the book&apos;s own
        P&amp;L over a rolling quarter and the forecast is the model&apos;s.
      </p>
      <svg
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
        <text x={L} y={H - 5} textAnchor="start" fontSize="8" fill="#64748b">
          {dateOnly(pairs[0]?.trade_date) ?? ""}
        </text>
        <text x={W - R} y={H - 5} textAnchor="end" fontSize="8" fill="#64748b">
          {dateOnly(last?.trade_date) ?? ""}
        </text>
      </svg>
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
      <p className="mt-1 text-sm tabular-nums" data-vol="last">
        the last session with both, {dateOnly(last?.trade_date) ?? "n/a"}: realized{" "}
        {volPct(last?.realized_vol)} against {volPct(last?.forecast_vol)} forecast
        {biasSentence(pairs)}
      </p>
      <p className="mt-1 text-xs text-slate-500">
        {count(pairs.length)} session(s) is not enough to judge the model: E11&apos;s risk test
        wants thirty live days before a bias band means anything, and a page that drew a verdict
        on seven would be inventing one.
      </p>
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

function PeriodView({
  period,
  chart,
  snapshot,
  live = false,
  notes = [],
}: {
  period: AttributionPeriod;
  chart: "daily" | "monthly";
  snapshot?: Snapshot;
  live?: boolean;
  /** Dated notes about the series, drawn as markers on the risk pictures. */
  notes?: AttributionNote[];
}) {
  const cumulative = period.cumulative;
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
        {from && to ? `, ${from} to ${to}` : ""}.{" "}
        {live
          ? "Every row is stored by the evening run: factor P&L is the book's exposure times the factor returns, idio P&L is its positions times the specific returns, and the four terms below are the day's total."
          : `This is a backtest of the seed book, not the live book: nobody traded it, so its cost is exactly zero, and its fourth term, ${bps(
              cumulative.pnl_unexplained,
            )}, is a research-vintage mismatch - the descriptors on file differ from the fit's design - rather than a loss anyone took.`}
      </p>
      {live ? null : period.note ? (
        <p className="mt-1 text-xs text-slate-500" data-backtest-note="true">
          {period.note}
        </p>
      ) : null}

      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3 lg:grid-cols-5">
        <div data-card="pnl-total" className="rounded border border-slate-100 bg-slate-50 px-2 py-1">
          <dt className="break-words text-xs uppercase tracking-wide text-slate-500">total</dt>
          <dd className="tabular-nums">{bps(cumulative.pnl_total)}</dd>
        </div>
        <div data-card="pnl-factor" className="rounded border border-slate-100 bg-slate-50 px-2 py-1">
          <dt className="break-words text-xs uppercase tracking-wide text-slate-500">factor</dt>
          <dd className="tabular-nums">{bps(cumulative.pnl_factor)}</dd>
        </div>
        <div data-card="pnl-idio" className="rounded border border-slate-100 bg-slate-50 px-2 py-1">
          <dt className="break-words text-xs uppercase tracking-wide text-slate-500">idio</dt>
          <dd className="tabular-nums">{bps(cumulative.pnl_idio)}</dd>
        </div>
        <div data-card="pnl-cost" className="rounded border border-slate-100 bg-slate-50 px-2 py-1">
          <dt className="break-words text-xs uppercase tracking-wide text-slate-500">
            cost contribution to P&amp;L
          </dt>
          <dd className="tabular-nums">{bps(cumulative.pnl_cost)}</dd>
        </div>
        <div
          data-card="pnl-unexplained"
          className="rounded border border-slate-100 bg-slate-50 px-2 py-1"
        >
          <dt className="break-words text-xs uppercase tracking-wide text-slate-500">
            {UNEXPLAINED_LABEL[live ? "live" : "backtest"].long}
          </dt>
          <dd className="tabular-nums">{bps(cumulative.pnl_unexplained)}</dd>
        </div>
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
      {live ? <VolatilityPanel period={period} /> : null}
      {live && period.risk ? <RiskSplit risk={period.risk} notes={notes} /> : null}
      <FactorTable period={period} />

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
      <h2 className="text-lg font-semibold">Attribution</h2>
      <p className="mt-1 text-sm text-slate-600">
        What the book earned, split into the four terms that add to its total: the hedge&apos;s
        factor P&amp;L, the names&apos; idiosyncratic P&amp;L, the cost contribution to P&amp;L,
        and the unexplained remainder. Every figure is in bp of NAV.
      </p>
      <Details
        hook="attribution-method"
        summary={<>how these four terms are computed, and what they are not</>}
      >
        <p className="text-xs text-slate-500">
          Every row is stored by the evening run: factor P&amp;L is the book&apos;s exposure times
          the factor returns, idio P&amp;L is its positions times the specific returns, and the
          four terms sum to the day&apos;s total by construction - a row that does not add up is a
          stored day that does not decompose, which is what the check column in the table is for.
          The fourth term is not a fourth estimate: it is the stored artifacts disagreeing with the
          panel&apos;s own return, and on the live book it is a few hundredths of a bp. On the
          research panel it is the descriptors&apos; vintage and it accumulates to hundreds of bp
          over a decade, which is why the two views label it differently.
        </p>
        {attribution.note ? (
          <p className="mt-1 text-xs text-slate-500">{attribution.note}</p>
        ) : null}
      </Details>

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
        <PeriodView period={backtest} chart="monthly" />
      ) : emptyLive ? (
        <p className="mt-2 text-sm text-slate-600" data-empty="live">
          {live?.note || attribution.note || "no live day is attributed yet"}
        </p>
      ) : live ? (
        <PeriodView period={live} chart="daily" snapshot={snapshot} live notes={attribution.notes ?? []} />
      ) : null}
    </section>
  );
}
