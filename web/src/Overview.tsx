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

import { useState } from "react";

import type { Exceptions } from "./exceptions";
import { dollars, percent, signedDollars } from "./format";
import type { Reconciliation, RunState, Tone } from "./status";
import { freshness, ageText } from "./status";
import { etDateTime } from "./format";
import type { AttributionDay, MonthlyBlock, Snapshot } from "./types";

/** A short explanation behind the (i) beside a title. */
export function Info({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block align-middle">
      <button
        type="button"
        aria-label={`about ${title}`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-300 bg-white text-[0.65rem] font-semibold leading-none text-slate-500 hover:bg-slate-100"
      >
        i
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
    <p className="flex items-baseline gap-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
      {title}
      <Info title={title}>{info}</Info>
    </p>
  );
}

/** A KPI card: one number, its unit, and the sentence that makes it readable. */
function Kpi({
  title,
  value,
  detail,
  info,
  children,
  hook,
}: {
  title: string;
  value?: React.ReactNode;
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
        <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-slate-900">
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

const SERIES = [
  { key: "total", word: "total", color: COLORS.total, dash: "" },
  { key: "factor", word: "factor", color: COLORS.factor, dash: "5 2" },
  { key: "idio", word: "stock-specific", color: COLORS.idio, dash: "1 3" },
  { key: "cost", word: "cost", color: COLORS.cost, dash: "7 2 1 2" },
] as const;

function CumulativeChart({ snapshot }: { snapshot: Snapshot }) {
  const points = cumulativePoints(snapshot);
  if (points.length === 0) {
    return (
      <p data-overview-cumulative="absent" className="text-xs text-slate-500">
        no attributed session yet, so there is no P&L line to draw.
      </p>
    );
  }
  const width = 720;
  const height = 240;
  const pad = { left: 48, right: 14, top: 12, bottom: 26 };
  const values = points.flatMap((point) => [
    point.total,
    point.factor,
    point.idio,
    point.cost,
  ]);
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const span = high - low || 1;
  const x = (index: number): number =>
    pad.left +
    (points.length === 1 ? 0 : (index / (points.length - 1)) * (width - pad.left - pad.right));
  const y = (value: number): number =>
    pad.top + ((high - value) / span) * (height - pad.top - pad.bottom);
  const path = (key: keyof Omit<CumulativePoint, "date">): string =>
    points
      .map((point, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(1)},${y(point[key]).toFixed(1)}`)
      .join(" ");
  const dates = new Set(points.map((point) => point.date));
  const markers = [
    ...(snapshot.monthly?.rebalance_dates ?? []),
    ...(snapshot.monthly?.cadence_strip?.last_rebalance
      ? [snapshot.monthly.cadence_strip.last_rebalance]
      : []),
  ].filter((date, index, all) => dates.has(date) && all.indexOf(date) === index);

  return (
    <>
      <svg
        role="img"
        aria-label="cumulative P&L in basis points"
        viewBox={`0 0 ${width} ${height}`}
        className="mt-1 h-48 w-full"
        data-overview-cumulative="true"
      >
        <line
          x1={pad.left}
          x2={width - pad.right}
          y1={y(0)}
          y2={y(0)}
          stroke="#cbd5e1"
          strokeWidth="1"
        />
        <text x={4} y={y(high) + 4} className="fill-slate-500" fontSize="10">
          {high.toFixed(0)} bp
        </text>
        <text x={4} y={y(low) + 4} className="fill-slate-500" fontSize="10">
          {low.toFixed(0)} bp
        </text>
        {markers.map((date) => {
          const index = points.findIndex((point) => point.date === date);
          return (
            <g key={date} data-overview-rebalance={date}>
              <line
                x1={x(index)}
                x2={x(index)}
                y1={pad.top}
                y2={height - pad.bottom}
                stroke="#94a3b8"
                strokeDasharray="2 3"
              />
              <text x={x(index) + 3} y={pad.top + 9} className="fill-slate-500" fontSize="9">
                {dayShort(date)}
              </text>
            </g>
          );
        })}
        {SERIES.map((series) => (
          <path
            key={series.key}
            d={path(series.key)}
            fill="none"
            stroke={series.color}
            strokeWidth={series.key === "total" ? "2" : "1.5"}
            strokeDasharray={series.dash || undefined}
            data-series={series.key}
          />
        ))}
      </svg>
      <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-600">
        {SERIES.map((series) => (
          <li key={series.key} data-legend={series.key} className="flex items-center gap-1">
            <span
              aria-hidden="true"
              className="inline-block h-0.5 w-4"
              style={{ background: series.color }}
            />
            {series.word}
          </li>
        ))}
      </ul>
    </>
  );
}

function DailyBars({ snapshot }: { snapshot: Snapshot }) {
  const rows = [...(snapshot.attribution?.live?.daily ?? [])].sort((a, b) =>
    String(a.trade_date ?? "").localeCompare(String(b.trade_date ?? "")),
  );
  if (rows.length === 0) {
    return (
      <p data-overview-daily="absent" className="text-xs text-slate-500">
        no attributed session yet, so there are no daily bars to draw.
      </p>
    );
  }
  const width = 720;
  const height = 180;
  const pad = { left: 48, right: 14, top: 12, bottom: 24 };
  const values = rows.map((row) => (row.pnl_total ?? 0) * 1e4);
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const span = high - low || 1;
  const y = (value: number): number =>
    pad.top + ((high - value) / span) * (height - pad.top - pad.bottom);
  const slot = (width - pad.left - pad.right) / Math.max(rows.length, 1);
  const barWidth = Math.max(2, slot * 0.65);
  return (
    <svg
      role="img"
      aria-label="daily P&L in basis points"
      viewBox={`0 0 ${width} ${height}`}
      className="mt-1 h-40 w-full"
      data-overview-daily="true"
    >
      <line x1={pad.left} x2={width - pad.right} y1={y(0)} y2={y(0)} stroke="#cbd5e1" />
      <text x={4} y={y(high) + 4} className="fill-slate-500" fontSize="10">
        {high.toFixed(0)} bp
      </text>
      <text x={4} y={y(low) + 4} className="fill-slate-500" fontSize="10">
        {low.toFixed(0)} bp
      </text>
      {rows.map((row, index) => {
        const value = (row.pnl_total ?? 0) * 1e4;
        const top = Math.min(y(0), y(value));
        const heightOfBar = Math.max(1, Math.abs(y(0) - y(value)));
        return (
          <rect
            key={row.trade_date ?? index}
            data-daily-bar={row.trade_date ?? index}
            x={pad.left + index * slot + (slot - barWidth) / 2}
            y={top}
            width={barWidth}
            height={heightOfBar}
            fill={value >= 0 ? "#059669" : "#e11d48"}
          >
            <title>{`${dayShort(row.trade_date)}: ${bps(value / 1e4)}`}</title>
          </rect>
        );
      })}
    </svg>
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
  if (key.startsWith("sector_")) return `Sector ${key.slice(7)}`;
  return key.replace(/_/g, " ");
};

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
  const rows = exposureRows(snapshot);
  if (rows.length === 0) {
    return (
      <p data-overview-exposures="absent" className="text-xs text-slate-500">
        this document carries no rebalance hedge footprint, so there is nothing to compare.
      </p>
    );
  }
  const labelWidth = 108;
  const width = 720;
  const rowHeight = 21;
  const height = rows.length * rowHeight + 28;
  const center = labelWidth + (width - labelWidth - 16) / 2;
  const half = (width - labelWidth - 16) / 2;
  const worst = Math.max(
    0.05,
    ...rows.flatMap((row) => [Math.abs(row.afterHedge), Math.abs(row.now ?? 0)]),
  );
  const scale = worst * 1.05;
  const at = (value: number): number => center + (value / scale) * half;
  const threshold = 0.05;
  return (
    <svg
      role="img"
      aria-label="factor exposures after the rebalance hedge and now"
      viewBox={`0 0 ${width} ${height}`}
      className="mt-1 w-full"
      data-overview-exposures="true"
    >
      <line x1={center} x2={center} y1={6} y2={height - 10} stroke="#94a3b8" />
      {[threshold, -threshold].map((value) => (
        <g key={value}>
          <line
            x1={at(value)}
            x2={at(value)}
            y1={6}
            y2={height - 10}
            stroke="#f59e0b"
            strokeDasharray="3 3"
            data-threshold="5"
          />
          <text
            x={at(value) + (value > 0 ? 2 : -20)}
            y={12}
            className="fill-amber-700"
            fontSize="9"
          >
            5%
          </text>
        </g>
      ))}
      {rows.map((row, index) => {
        const top = 20 + index * rowHeight;
        return (
          <g key={row.factor} data-exposure-factor={row.factor}>
            <text x={0} y={top + 10} className="fill-slate-600" fontSize="10">
              {factorLabel(row.factor)}
            </text>
            <rect
              x={Math.min(center, at(row.afterHedge))}
              y={top + 2}
              width={Math.abs(at(row.afterHedge) - center)}
              height={5}
              fill="#94a3b8"
              data-exposure-series="after-hedge"
            />
            {row.now === null ? null : (
              <rect
                x={Math.min(center, at(row.now))}
                y={top + 9}
                width={Math.abs(at(row.now) - center)}
                height={5}
                fill="#0284c7"
                data-exposure-series="now"
              />
            )}
            <text x={width - 48} y={top + 10} className="fill-slate-500" fontSize="9">
              {row.now === null ? "n/a" : percent(row.now)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** One line per thing a person has to look at, and nothing when there is none. */
export interface OverviewException {
  key: string;
  text: string;
}

export function overviewExceptions(
  snapshot: Snapshot,
  state: RunState,
  reconciled: Reconciliation,
  exceptions: Exceptions,
): OverviewException[] {
  const lines: OverviewException[] = [];
  const seen = new Set<string>();
  const add = (key: string, text: string): void => {
    if (seen.has(key)) return;
    seen.add(key);
    lines.push({ key, text });
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
      const words = acquired
        ? `${acquired.startsWith("acquired") ? acquired : `acquired by ${acquired}`}, held, cannot be traded`
        : note.replace(/^retired, /, "");
      const dollarsSuffix =
        row.gap_usd === null || row.gap_usd === undefined
          ? ""
          : `, ${dollars(Math.abs(row.gap_usd))}`;
      add(row.ticker, `${row.ticker}: ${words}${dollarsSuffix}`);
    } else if (row.owed) {
      const dollarsSuffix =
        row.gap_usd === null || row.gap_usd === undefined
          ? ""
          : `, ${dollars(Math.abs(row.gap_usd))}`;
      add(row.ticker, `${row.ticker}: owed and cannot be traded${dollarsSuffix}`);
    }
  }
  for (const leg of snapshot.monthly?.tonight?.cannot_send ?? []) {
    add(
      `cannot-send-${leg.ticker}`,
      `${leg.ticker}: ${dollars(leg.usd)} owed, cannot be sent (${leg.code})`,
    );
  }
  for (const name of snapshot.actual_holdings?.exits?.names ?? []) {
    add(
      `exit-${name.ticker}`,
      `${name.ticker}: left the account with no order behind it, ${dollars(name.notional)}`,
    );
  }
  for (const entry of exceptions.unexpected) {
    add(entry.ticker, `${entry.ticker}: ${entry.why}`);
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
        {lines.length === 0
          ? "All clear"
          : lines.length === 1
            ? "1 thing needs a person"
            : `${lines.length} things need a person`}
      </p>
      {lines.length === 0 ? (
        <p className="text-xs">nothing on the account or the run needs attention today.</p>
      ) : (
        <ul className="mt-1 flex flex-col gap-0.5 text-sm">
          {shown.map((line) => (
            <li key={line.key} data-exception={line.key}>
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
          detail={[
            lastDate ? `the ${lastDate} close` : "no attributed session",
            todayValue === null || nav === null
              ? null
              : `${signedDollars(todayValue * nav)} in dollars`,
          ]
            .filter(Boolean)
            .join(", ")}
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
          <dl data-since-split="true" className="mt-1 grid gap-0.5 text-xs">
            {[
              { label: "factor", value: cumulative?.pnl_factor ?? null },
              { label: "stock-specific", value: cumulative?.pnl_idio ?? null },
              { label: "cost", value: cumulative?.pnl_cost ?? null },
            ].map((row) => (
              <div key={row.label} className="flex items-baseline justify-between gap-2">
                <dt className="text-slate-500">{row.label}</dt>
                <dd className="font-mono tabular-nums text-slate-800">
                  {bps(row.value)}
                  <span className="ml-1 text-slate-500">
                    {row.value === null || nav === null
                      ? ""
                      : signedDollars(row.value * nav)}
                  </span>
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
              stock-specific and cost; vertical marks are rebalance closes. Example: cost
              is {bps(cumulative?.pnl_cost)} since go-live, and the last session moved it{" "}
              {bps(latest?.pnl_cost)}.
            </>
          }
        />
        <CumulativeChart snapshot={snapshot} />
      </section>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="min-w-0 rounded border border-slate-200 bg-white px-3 py-2">
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
        <section className="min-w-0 rounded border border-slate-200 bg-white px-3 py-2">
          <Title
            title="factor exposures"
            info={
              <>
                Each factor’s exposure as a share of NAV: grey is where the rebalance’s
                hedge left it, blue is where the book carries it now, and the dashed line
                is the 5% guard. It moves when prices move the book or a rebalance changes
                its shape. Example: the worst factor now is {percent(worstNow)}, against{" "}
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
