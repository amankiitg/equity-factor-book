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
  if (status !== "ok") {
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
      headline: "no run for the session that should have closed",
      detail: `the snapshot for the ${snapshot.target_close ?? "next"} close was expected by ${snapshot.expected_next_by}, ${Math.abs(
        minutesBetween(now, due),
      )} minute(s) ago`,
    };
  }
  return {
    ok: true,
    headline: `clean run for the ${snapshot.target_close ?? "latest"} close`,
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
  const age = minutesBetween(new Date(snapshot.generated_at), now);
  const bookAsof = snapshot.book_as_of;
  const dated = bookAsof && bookAsof !== snapshot.target_close;
  const positions = snapshot.positions;

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
        snapshot generated {snapshot.generated_at} ({age} minute(s) ago), target close{" "}
        {snapshot.target_close ?? "unknown"}
      </p>

      {snapshot.run_status?.catch_up ? (
        <Panel
          tone="info"
          title={`catch-up run: ${snapshot.run_status.catch_up_sessions.join(", ")}`}
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
        <p className="text-sm text-slate-600">
          {snapshot.construction} | gross {percent(snapshot.book.gross)} | net{" "}
          {percent(snapshot.book.net)} | n_eff_kept{" "}
          {snapshot.book.n_kept !== null ? snapshot.breadth.n_eff_kept : "n/a"} (
          {snapshot.breadth.kept_label}) | n_eff_full_book {snapshot.breadth.n_eff_full_book} (
          {snapshot.breadth.full_book_label}) | cost{" "}
          {snapshot.book.expected_cost_bps?.toFixed(2) ?? "n/a"} bps
          {snapshot.run_status?.cost_label ? ` (${snapshot.run_status.cost_label})` : ""}
        </p>
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
        <div className="flex gap-8">
          <table className="text-sm">
            <caption className="text-left font-medium">before the hedge</caption>
            <tbody>
              {Object.entries(snapshot.exposures_before_hedge ?? {}).map(([key, value]) => (
                <tr key={key}>
                  <td className="pr-4 font-mono">{key}</td>
                  <td>{exposures(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <table className="text-sm">
            <caption className="text-left font-medium">after the hedge</caption>
            <tbody>
              {Object.entries(snapshot.exposures_after_hedge ?? {}).map(([key, value]) => (
                <tr key={key}>
                  <td className="pr-4 font-mono">{key}</td>
                  <td>{exposures(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <dl className="text-sm">
            <dt className="font-medium">the hedge</dt>
            <dd>idio share after FMP: {exposures(snapshot.hedge?.idio_share_after_fmp)}</dd>
            <dd>
              worst residual exposure: {exposures(snapshot.hedge?.max_abs_exposure_after_fmp)}
            </dd>
            <dd>reconciliation intended: {dollars(snapshot.reconciliation?.intended_notional)}</dd>
          </dl>
        </div>
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
