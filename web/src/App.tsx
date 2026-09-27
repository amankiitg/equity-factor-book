// The live book monitor. One screen, from one JSON document.
//
// The order is deliberate and matches the deliverable: status first, then the
// book, then the hedge. Status first because the one thing a monitor must never
// do is show an old book as though it were current: a run that stopped, errored,
// never happened, or is late is a failure state that takes the top of the screen,
// and the book below it is labelled with its own close when that close is not the
// target.

import { useEffect, useState } from "react";

import type { Snapshot } from "./types";

export interface Health {
  ok: boolean;
  headline: string;
  detail: string;
}

const MINUTE = 60_000;

function minutesBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / MINUTE);
}

/** Whether this snapshot is current, and if not, why in one sentence. */
export function health(snapshot: Snapshot, now: Date): Health {
  const status = snapshot.run_status?.status ?? "unknown";
  // A day the exchange was shut is neither clean nor broken: there was no close
  // to price, so no run was due and nothing is late. It must not read as a
  // failure, or the one line that has to mean something stops meaning anything.
  // It is not a licence to stop paying attention either, so the deadline check
  // below still applies: the next session's run is due the evening after it, and
  // a closed day must not sit on the page looking current while that run is
  // missing.
  const closed = status === "market_closed";
  if (!closed && status !== "ok") {
    const failing = (snapshot.run_status?.failing_inputs ?? [])
      .map((item) => `${item.input} ${item.sessions_behind ?? "no date"}`)
      .join("; ");
    const detail =
      snapshot.run_status?.detail ||
      (failing ? `failing inputs: ${failing}` : "no reason recorded");
    return {
      ok: false,
      headline:
        status === "stale_stopped"
          ? "STALE STOP: the run refused to price a book"
          : `the run recorded ${status}`,
      detail,
    };
  }
  const due = snapshot.expected_next_by ? new Date(snapshot.expected_next_by) : null;
  if (due && now.getTime() > due.getTime()) {
    return {
      ok: false,
      headline: closed
        ? `no run for the session after the ${dateOnly(snapshot.target_close) ?? "last"} close`
        : "no run for the session that should have closed",
      detail: `the snapshot for the ${dateOnly(snapshot.target_close) ?? "next"} close was expected by ${snapshot.expected_next_by}, ${Math.abs(
        minutesBetween(now, due),
      )} minute(s) ago`,
    };
  }
  if (closed) {
    return {
      ok: true,
      headline: `market closed on ${dateOnly(snapshot.target_close) ?? "the run's date"}: no run was due`,
      detail:
        snapshot.run_status?.detail ||
        "the exchange was shut, so there was no close to price",
    };
  }
  return {
    ok: true,
    headline: `clean run for the ${dateOnly(snapshot.target_close) ?? "latest"} close`,
    detail: snapshot.run_status?.notify_status
      ? `the owner was notified (${snapshot.run_status.notify_status})`
      : "",
  };
}

const percent = (value: number | null): string =>
  value === null || value === undefined ? "n/a" : `${(value * 100).toFixed(2)}%`;

const dollars = (value: number | null): string =>
  value === null || value === undefined ? "n/a" : `$${Math.round(value).toLocaleString()}`;

const exposures = (value: number | null): string =>
  value === null || value === undefined ? "n/a" : value.toFixed(4);

/** A date as the day it is, never with a midnight time stapled to it. */
const dateOnly = (value: string | null | undefined): string | null =>
  value === null || value === undefined || value === "" ? null : value.slice(0, 10);

/** One decimal place: an effective breadth of 70.59213 is 70.6 names, not 70.59. */
const oneDecimal = (value: number | null): string =>
  value === null || value === undefined ? "n/a" : value.toFixed(1);

/**
 * A factor exposure to four places, with negative zero shown as zero.
 *
 * The hedge drives every factor to zero to machine precision, so the "after"
 * column holds values like -2.6e-18 whose four-place form is "-0.0000". That is
 * not a negative exposure, it is rounding, and a table of minus-zeroes reads as
 * though the hedge had missed.
 */
const exposure = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const rounded = Number(value.toFixed(4));
  return (Object.is(rounded, -0) ? 0 : rounded).toFixed(4);
};

/** A human age, so the reader does not have to subtract two timestamps. */
function ageText(generated: Date, now: Date): string {
  const minutes = minutesBetween(generated, now);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  return `${Math.round(hours / 24)} day${Math.round(hours / 24) === 1 ? "" : "s"} ago`;
}

// The factor vocabulary, styles first then sectors, in the order the reader
// wants them: what the portfolio is tilted towards, then where it sits. The
// sector labels are GICS names with their codes, because `sector_45` is not a
// thing anyone reads off a screen.
const STYLE_ROWS: Array<[string, string]> = [
  ["beta", "Beta"],
  ["liquidity", "Liquidity"],
  ["market", "Market"],
  ["momentum", "Momentum"],
  ["resid_vol", "Residual vol"],
  ["reversal", "Reversal"],
  ["size", "Size"],
];

const SECTOR_ROWS: Array<[string, string]> = [
  ["sector_10", "10 Energy"],
  ["sector_15", "15 Materials"],
  ["sector_20", "20 Industrials"],
  ["sector_25", "25 Consumer Discretionary"],
  ["sector_30", "30 Consumer Staples"],
  ["sector_35", "35 Health Care"],
  ["sector_40", "40 Financials"],
  ["sector_45", "45 Information Technology"],
  ["sector_50", "50 Communication Services"],
  ["sector_55", "55 Utilities"],
];

// The sector dummy the design leaves out, so its exposure is carried by the
// intercept rather than by a column of its own. Named in the table itself: a
// reader who knows the GICS codes asks where 60 went.
const REFERENCE_SECTOR = "60 Real Estate";

/**
 * The rows of the exposure table: styles, sectors, then anything the design
 * carries that this list does not know about, so a new factor cannot disappear
 * from the page by being unlisted.
 */
function exposureRows(before: Record<string, number | null>): Array<[string, string]> {
  const known = new Set([...STYLE_ROWS, ...SECTOR_ROWS].map(([key]) => key));
  const rest = Object.keys(before)
    .filter((key) => !known.has(key))
    .sort()
    .map((key) => [key, key] as [string, string]);
  return [...STYLE_ROWS, ...SECTOR_ROWS, ...rest];
}

/**
 * One factor's before and after as two zero-centred bars on the same scale.
 *
 * The scale is the largest exposure on the page, so the rows are comparable with
 * each other rather than each filling its own cell, and the "after" bars are
 * visibly absent because the hedge takes every factor to zero.
 */
function ExposureBars({
  before,
  after,
  scale,
}: {
  before: number;
  after: number;
  scale: number;
}) {
  return (
    <div className="flex w-40 flex-col gap-[2px]" data-factor-bars="true">
      <ExposureBar value={before} scale={scale} tone="before" />
      <ExposureBar value={after} scale={scale} tone="after" />
    </div>
  );
}

function ExposureBar({ value, scale, tone }: { value: number; scale: number; tone: string }) {
  const share = Math.max(0, Math.min(1, Math.abs(value) / (scale || 1)));
  const style: Record<string, string> =
    value >= 0 ? { left: "50%", width: `${share * 50}%` } : { right: "50%", width: `${share * 50}%` };
  return (
    <div className="relative h-[6px] w-full rounded-sm bg-slate-100">
      <span className="absolute left-1/2 top-0 h-full w-px bg-slate-300" />
      <span
        data-bar={tone}
        data-sign={value >= 0 ? "positive" : "negative"}
        title={`${tone} ${exposure(value)}`}
        className={`absolute top-0 h-full rounded-sm ${
          tone === "before" ? "bg-slate-500" : "bg-emerald-600"
        }`}
        style={style}
      />
    </div>
  );
}


function Panel({
  tone,
  title,
  detail,
}: {
  tone: "bad" | "good" | "info";
  title: string;
  detail: string;
}) {
  const colour =
    tone === "bad"
      ? "bg-red-100 text-red-900 border-red-400"
      : tone === "good"
        ? "bg-emerald-50 text-emerald-900 border-emerald-300"
        : "bg-slate-100 text-slate-800 border-slate-300";
  return (
    <section className={`border-l-4 px-4 py-3 ${colour}`} role={tone === "bad" ? "alert" : "status"}>
      <p className="font-semibold">{title}</p>
      {detail ? <p className="text-sm">{detail}</p> : null}
    </section>
  );
}

export function SnapshotView({ snapshot, now }: { snapshot: Snapshot; now: Date }) {
  const state = health(snapshot, now);
  const bookAsof = dateOnly(snapshot.book_as_of);
  const targetClose = dateOnly(snapshot.target_close);
  const dated = bookAsof && bookAsof !== targetClose;
  const positions = snapshot.positions;
  const before = snapshot.exposures_before_hedge ?? {};
  const after = snapshot.exposures_after_hedge ?? {};
  const rows = exposureRows(before);
  const scale = Math.max(
    ...[...Object.values(before), ...Object.values(after)].map((value) => Math.abs(value ?? 0)),
    0.0001,
  );

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-4 p-6">
      <h1 className="text-xl font-bold">EFB live book</h1>

      {snapshot.dry_run ? (
        <Panel
          tone="info"
          title="DRY RUN: no orders are sent"
          detail="the run prices the book and records the orders it would place"
        />
      ) : null}

      <Panel tone={state.ok ? "good" : "bad"} title={state.headline} detail={state.detail} />
      <p className="text-sm text-slate-600">
        snapshot generated {dateOnly(snapshot.generated_at) ?? "unknown"} (
        {ageText(new Date(snapshot.generated_at), now)}), target close{" "}
        {dateOnly(snapshot.target_close) ?? "unknown"}
      </p>

      {snapshot.run_status?.catch_up ? (
        <Panel
          tone="info"
          title={`catch-up run: ${snapshot.run_status.catch_up_sessions
            .map((session) => dateOnly(session) ?? session)
            .join(", ")}`}
          detail="the gate evening must be a run whose target close is the only session it appended"
        />
      ) : null}

      {positions ? (
        <Panel
          tone={positions.matches === true ? "good" : positions.matches === null ? "info" : "bad"}
          title="positions against the store"
          detail={positions.note ?? "not read"}
        />
      ) : null}

      <section>
        <h2 className="text-lg font-semibold">
          The book: {snapshot.book.n_names} name(s)
          {dated ? ` (as of ${bookAsof})` : ""}
        </h2>
        {/* One labelled item per number, rather than a pipe-separated run of
            text: a reader looking for the cost should not have to count fields. */}
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-4 text-sm text-slate-600">
          <dt className="font-medium">construction</dt>
          <dd>{snapshot.construction}</dd>
          <dt className="font-medium">gross</dt>
          <dd>
            {percent(snapshot.book.gross)}
            {snapshot.book.gross_notional !== null
              ? ` (${dollars(snapshot.book.gross_notional)})`
              : ""}
          </dd>
          {snapshot.book.full_book_gross !== null ? (
            <>
              <dt className="text-slate-500">full book before the floor</dt>
              <dd className="text-slate-500">{percent(snapshot.book.full_book_gross)}</dd>
            </>
          ) : null}
          <dt className="font-medium">net</dt>
          <dd>{percent(snapshot.book.net)}</dd>
          {snapshot.book.n_kept !== null ? (
            <>
              <dt className="font-medium">n_eff_kept</dt>
              <dd>
                {oneDecimal(snapshot.breadth.n_eff_kept)}
                {snapshot.breadth.kept_label ? ` (${snapshot.breadth.kept_label})` : ""}
              </dd>
            </>
          ) : null}
          <dt className="font-medium">n_eff_full_book</dt>
          <dd>
            {oneDecimal(snapshot.breadth.n_eff_full_book)}
            {snapshot.breadth.full_book_label ? ` (${snapshot.breadth.full_book_label})` : ""}
          </dd>
          <dt className="font-medium">cost</dt>
          <dd>
            {snapshot.book.expected_cost_bps?.toFixed(2) ?? "n/a"} bps
            {snapshot.run_status?.cost_label ? ` (${snapshot.run_status.cost_label})` : ""}
          </dd>
        </dl>
        {snapshot.book.reason ? (
          <p className="text-sm text-amber-800">no book: {snapshot.book.reason}</p>
        ) : null}
        <table aria-label="the book" className="mt-2 w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-300 text-left">
              <th className="py-1">ticker</th>
              <th className="py-1">side</th>
              <th className="py-1">weight</th>
              <th className="py-1">reason</th>
            </tr>
          </thead>
          <tbody>
            {snapshot.book.names.map((name) => (
              <tr key={name.ticker} className="border-b border-slate-100">
                <td className="py-1 font-mono">{name.ticker}</td>
                <td className="py-1">{name.side}</td>
                <td className="py-1">{percent(name.weight)}</td>
                <td className="py-1 text-slate-600">{name.reason ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Factor exposures, before and after the hedge</h2>
        <table className="mt-2 w-full border-collapse text-sm" aria-label="factor exposures">
          <thead>
            <tr className="border-b border-slate-300 text-left">
              <th className="py-1">factor</th>
              <th className="py-1 text-right">before</th>
              <th className="py-1 text-right">after</th>
              <th className="py-1">before / after</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([key, label], index) => {
              const startOfSectors =
                index === 0 ? false : rows[index - 1][0].startsWith("sector_") === false;
              return (
                <tr
                  key={key}
                  data-factor={key}
                  className={`border-b border-slate-100 ${
                    key.startsWith("sector_") ? "bg-slate-50" : ""
                  } ${startOfSectors ? "border-t-2 border-t-slate-300" : ""}`}
                >
                  <td className="py-1">{label}</td>
                  <td className="py-1 text-right font-mono">{exposure(before[key])}</td>
                  <td className="py-1 text-right font-mono">{exposure(after[key])}</td>
                  <td className="py-1">
                    <ExposureBars
                      before={before[key] ?? 0}
                      after={after[key] ?? 0}
                      scale={scale}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="mt-1 text-xs text-slate-500">
          The hedge is exact, so every factor's after value is zero to machine precision. The bars are
          on one scale, the largest exposure on the page: a bar that is not there is a factor the
          hedge has taken out. 60 Real Estate is the reference sector and has no column of its own,
          so the ten sectors above are measured against it.
        </p>
        <dl className="mt-3 text-sm">
          <dt className="font-medium">the hedge</dt>
          <dd>idio share after FMP: {exposures(snapshot.hedge?.idio_share_after_fmp)}</dd>
          <dd>worst residual exposure: {exposures(snapshot.hedge?.max_abs_exposure_after_fmp)}</dd>
          <dd>reconciliation intended: {dollars(snapshot.reconciliation?.intended_notional)}</dd>
        </dl>
      </section>
    </main>
  );
}

type Load =
  | { kind: "loading" }
  | { kind: "loaded"; snapshot: Snapshot }
  | { kind: "missing" }
  | { kind: "error"; detail: string };

export function App({ now = () => new Date() }: { now?: () => Date }) {
  const [load, setLoad] = useState<Load>({ kind: "loading" });

  useEffect(() => {
    let live = true;
    fetch("/api/snapshot")
      .then(async (response) => {
        if (response.status === 404) {
          if (live) setLoad({ kind: "missing" });
          return;
        }
        if (!response.ok) {
          if (live) setLoad({ kind: "error", detail: `the endpoint answered ${response.status}` });
          return;
        }
        const snapshot = (await response.json()) as Snapshot;
        if (live) setLoad({ kind: "loaded", snapshot });
      })
      .catch((error: unknown) => {
        if (live) setLoad({ kind: "error", detail: String(error) });
      });
    return () => {
      live = false;
    };
  }, []);

  if (load.kind === "loading") {
    return <p className="p-6">loading the snapshot...</p>;
  }
  if (load.kind === "missing") {
    return (
      <div className="p-6">
        <Panel
          tone="bad"
          title="no snapshot at all"
          detail="the page cannot show a book: no run has written a snapshot yet"
        />
      </div>
    );
  }
  if (load.kind === "error") {
    return (
      <div className="p-6">
        <Panel
          tone="bad"
          title="the snapshot could not be read"
          detail={`${load.detail}. A missing token or a missing bucket shows here first.`}
        />
      </div>
    );
  }
  return <SnapshotView snapshot={load.snapshot} now={now()} />;
}

export default App;
