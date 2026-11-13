// The panels measured from the last rebalance.
//
// With EFB_CADENCE=21 most evenings are hold days, and every panel that compares
// tonight with last night reads zero on one: 0 orders, $0 of sector gaps, 0 hedge
// legs. These panels are measured from the anchor instead, the latest close whose
// cadence day is a rebalance, so a hold day's page is about the rebalance that is
// still settling rather than about a night that did nothing.
//
// The whole section renders nothing when the document carries no `monthly` block.
// That is every document published before the block existed, and the page has to
// look exactly as it did then: the nightly panels still carry those evenings.

import { HowToRead } from "./Panel";
import { dateOnly, dollars, percent, signedDollars } from "./format";
import type { MonthlyBlock } from "./types";

function Card({
  title,
  howToRead,
  children,
}: {
  title: string;
  howToRead: string;
  children: React.ReactNode;
}) {
  return (
    <section
      data-panel="monthly"
      className="min-w-0 rounded border border-slate-200 bg-white px-3 py-2"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title}
        <HowToRead>{howToRead}</HowToRead>
      </p>
      {children}
    </section>
  );
}

function Stat({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="font-mono text-sm font-semibold text-slate-900">{value}</dd>
      {detail ? <dd className="text-xs text-slate-500">{detail}</dd> : null}
    </div>
  );
}

export function CadenceStrip({ monthly }: { monthly: MonthlyBlock }) {
  const strip = monthly.cadence_strip;
  if (!strip) return null;
  const guard = strip.guard;
  const fired = guard.fired ? "fired" : guard.ran ? "held" : "did not run";
  return (
    <Card
      title="cadence"
      howToRead="most closes change nothing: the book is rebuilt every 21 sessions and repaired only when a factor exposure drifts too far. Example: 13 of 21 sessions have passed since 10-23, so the next rebuild is 11-23."
    >
      <dl data-cadence="true" className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
        <Stat
          label="today"
          value={
            strip.day === "rebalance"
              ? "rebalance"
              : strip.k === null || strip.k === undefined || strip.k === 1
                ? "daily"
                : "hold day"
          }
          detail={
            strip.day === "rebalance" || strip.k === null || strip.k === undefined || strip.k === 1
              ? undefined
              : `${strip.sessions_since ?? 0} of ${strip.k}`
          }
        />
        <Stat label="last rebalance" value={dateOnly(strip.last_rebalance) ?? "-"} />
        <Stat label="next rebalance" value={dateOnly(strip.next_rebalance) ?? "-"} />
        <Stat
          label="drift guard"
          value={
            guard.worst_abs_exposure === null ||
            guard.worst_abs_exposure === undefined
              ? "-"
              : `${percent(guard.worst_abs_exposure)} of ${percent(guard.threshold)}`
          }
          detail={
            guard.threshold === null || guard.threshold === undefined
              ? `threshold not set, ${fired}`
              : `${fired}`
          }
        />
      </dl>
    </Card>
  );
}

export function RebalanceCard({ monthly }: { monthly: MonthlyBlock }) {
  const card = monthly.rebalance_card;
  if (!card || card.orders === undefined) return null;
  return (
    <Card
      title={`the rebalance of ${dateOnly(card.close) ?? "the anchor"}`}
      howToRead="one evening turns the old book into the new one, so it is the month's largest trade and almost all of its cost. Example: on 10-23 it sent 208 legs for $544,003, 56% of NAV."
    >
      <dl data-rebalance="true" className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
        <Stat
          label="orders"
          value={String(card.orders)}
          detail={`${dollars(card.notional)} sent, ${percent(card.pct_nav)} of NAV`}
        />
        <Stat
          label="expected cost"
          value={
            card.expected_cost_bps === null || card.expected_cost_bps === undefined
              ? "-"
              : `${card.expected_cost_bps.toFixed(1)} bp`
          }
          detail={dollars(card.expected_cost_usd)}
        />
        <Stat
          label="realized cost"
          value={
            card.realized_cost_bps === null || card.realized_cost_bps === undefined
              ? "-"
              : `${card.realized_cost_bps.toFixed(1)} bp`
          }
          detail="from the fills"
        />
        <Stat
          label="completion"
          value={`${card.filled_legs ?? card.legs_complete ?? 0} of ${
            card.sent_legs ?? card.legs_complete ?? 0
          } sent legs filled`}
          detail={[
            (card.under_minimum_legs ?? 0) > 0
              ? `${card.under_minimum_legs} under $250 not sent (${dollars(
                  card.under_minimum_usd,
                )})`
              : null,
            (card.dollars_owed ?? 0) > 0
              ? `${dollars(card.dollars_owed)} owed on sent legs`
              : "nothing owed",
          ]
            .filter(Boolean)
            .join("; ")}
        />
      </dl>
    </Card>
  );
}

export function FlipBridge({ monthly }: { monthly: MonthlyBlock }) {
  const bridge = monthly.bridge_anchor;
  if (!bridge) return null;
  const flips = bridge.flip_rows ?? [];
  // The date a leg carries is the fill's own when the store has one, and the close
  // it was priced from when it does not. The column says which, because a reader who
  // takes a close date for a fill date reads two days of a flip as one.
  const legsFilled = flips.some(
    (flip) => flip.close_filled_at || flip.open_filled_at,
  );
  const legDate = (filledAt: string | null | undefined, close: string | null): string =>
    dateOnly(filledAt ?? close) ?? "-";
  return (
    <Card
      title="the rebalance, from the account before it to the account now"
      howToRead="a name that changes side cannot do it in one order: the close lands one morning and the open the next. Example: CCL bought back $605 of short on 10-26 and bought $678 of long on 10-27."
    >
      <dl data-flips={bridge.flipped} className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
        <Stat label="before" value={dollars(bridge.before_dollars)} detail="account, anchor close" />
        <Stat
          label="opened / exited"
          value={`${bridge.opened} / ${bridge.exited}`}
          detail={`${bridge.resized} resized`}
        />
        <Stat
          label="flips"
          value={`${bridge.flipped}`}
          detail={`${bridge.complete_flips} complete`}
        />
        <Stat label="now" value={dollars(bridge.after_dollars)} detail="account, latest close" />
      </dl>
      {flips.length ? (
        <>
          <div
            data-flip-header="true"
            className="mt-2 hidden gap-2 border-b border-slate-200 pb-1 text-slate-500 sm:grid sm:grid-cols-3"
          >
            <span>leg 1: closed the old position (trade size)</span>
            <span>leg 2: opened the new side (trade size)</span>
            <span>position now (minus = short, at today&apos;s price)</span>
          </div>
          <ul data-flip-table="true" className="mt-2 flex flex-col gap-2 text-xs">
            {flips.map((flip) => {
              const state = flip.state ?? (flip.complete ? "complete" : "owed");
              const label =
                flip.state_label ?? (flip.complete ? "complete" : "still owed");
              return (
                <li
                  key={flip.ticker}
                  data-flip={flip.ticker}
                  className="border-b border-slate-100 pb-1.5"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-mono text-sm font-semibold">{flip.ticker}</span>
                    <span className="flex-1 truncate text-slate-700">
                      {flip.from_side} to {flip.to_side}
                    </span>
                    <span
                      data-flip-state={state}
                      className="font-sans text-slate-600"
                    >
                      {label}
                    </span>
                  </div>
                  <div className="mt-1 grid gap-1 sm:grid-cols-3">
                    <div data-flip-leg="1" className="font-mono text-slate-600">
                      <span className="block font-sans text-slate-500 sm:hidden">
                        leg 1: closed the old position (trade size)
                      </span>
                      <span className="tabular-nums">{dollars(flip.close_dollars)}</span>
                      <span className="text-slate-500">
                        {" "}
                        {legDate(flip.close_filled_at, flip.close_filled)}
                      </span>
                    </div>
                    <div data-flip-leg="2" className="font-mono text-slate-600">
                      <span className="block font-sans text-slate-500 sm:hidden">
                        leg 2: opened the new side (trade size)
                      </span>
                      <span className="tabular-nums">{dollars(flip.open_dollars)}</span>
                      <span className="text-slate-500">
                        {" "}
                        {legDate(flip.open_filled_at, flip.open_filled)}
                      </span>
                    </div>
                    <div data-flip-leg="now" className="font-mono text-slate-600">
                      <span className="block font-sans text-slate-500 sm:hidden">
                        position now (minus = short, at today&apos;s price)
                      </span>
                      <span className="tabular-nums">{signedDollars(flip.now_dollars)}</span>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
      <p className="mt-1 text-xs text-slate-500" data-flip-why="true">
        why the position now differs from leg 2: prices moved after the trades, so the
        dollar value changed. The side did not.
      </p>
    </Card>
  );
}

export function DriftCard({ monthly }: { monthly: MonthlyBlock }) {
  const drift = monthly.drift;
  if (!drift) return null;
  return (
    <Card
      title="distance from the rebalance target"
      howToRead="prices move the book away from the target every day, and the gap is measured at today's price. Example: on 11-11 the book was 8.74% of NAV from target, $85,486 on one side, and closing it would trade $170,971."
    >
      <dl data-drift="true" className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
        <Stat
          label="drift"
          value={percent(drift.half_turnover_pct)}
          detail={`${dollars(drift.half_turnover_usd)} of NAV, one side`}
        />
        <Stat
          label="to close it"
          value={dollars(drift.traded_usd)}
          detail="both sides would trade"
        />
        <Stat
          label="estimated cost"
          value={dollars(drift.estimated_cost_usd)}
          detail="at the rebalance's trading cost"
        />
      </dl>
      {drift.largest?.length ? (
        // Three columns and no sideways scroll: the name, the two weights it is
        // between, and the dollars that separate them. The gap leads because it is
        // the number the card is about.
        <ul data-drift-table="true" className="mt-2 flex flex-col gap-1 text-xs">
          <li className="flex items-baseline justify-between gap-2 text-slate-500">
            <span>name</span>
            <span className="ml-auto mr-1">now → target</span>
            <span>gap</span>
          </li>
          {drift.largest.map((row) => (
            <li key={row.ticker} data-drift-row={row.ticker} className="flex items-baseline gap-2">
              <span className="w-14 shrink-0 font-mono font-semibold">{row.ticker}</span>
              <span className="flex-1 truncate text-right font-mono tabular-nums text-slate-600">
                {percent(row.weight_now)} → {percent(row.weight_target)}
              </span>
              <span className="w-16 shrink-0 text-right font-mono tabular-nums">
                {signedDollars(row.usd)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

export function TradesSinceAnchor({ monthly }: { monthly: MonthlyBlock }) {
  const trades = monthly.since_anchor?.trades_by_reason ?? [];
  const notSent = monthly.since_anchor?.not_sent;
  if (!trades.length) return null;
  const under = notSent?.under_minimum;
  const refused = notSent?.other ?? [];
  return (
    <Card
      title="every leg since the rebalance, by why it went"
      howToRead="a leg is one order in one direction, and the reason says which event asked for it. The count moves when a rebalance lands, when a flip needs its second day, or when the guard fires. Example: 8 legs on 10-26 re-traded a rebalance that had already filled, so they are their own row, fixed 10-27."
    >
      <div className="overflow-x-auto">
        <table data-trades-reason="true" className="w-full min-w-[16rem] text-left text-xs">
        <tbody className="font-mono">
          {trades.map((row) => {
            const sent = row.sent_legs ?? row.legs;
            return (
              <tr key={row.reason}>
                <td className="font-semibold">{row.reason}</td>
                <td className="text-right">
                  {sent === row.legs
                    ? `${row.legs} legs`
                    : `${sent} sent, ${row.legs - sent} owed`}
                </td>
                <td className="text-right">{dollars(row.usd)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
      {under || refused.length ? (
        <p data-not-sent="true" className="mt-1 text-xs text-slate-500">
          not sent: {under?.legs ?? 0} legs under $250 ({dollars(under?.usd ?? 0)})
          {refused.length
            ? `; ${refused
                .map((row) => `${row.legs} refused (${row.code}, ${dollars(row.usd)})`)
                .join("; ")}`
            : ""}
        </p>
      ) : null}
    </Card>
  );
}

export function TonightLine({ monthly }: { monthly: MonthlyBlock }) {
  const tonight = monthly.tonight;
  if (!tonight) return null;
  const owed = tonight.owed_legs ?? 0;
  const cannotSend = tonight.cannot_send_legs ?? 0;
  const unsendable = (tonight.cannot_send ?? [])
    .map((leg) => (leg.code ? `${leg.ticker}, ${leg.code}` : leg.ticker))
    .join("; ");
  // A leg that will be sent on the next close and a leg that can never be sent are
  // both "forced", and one line said "1 forced leg, $269" for either. The refusal is
  // stated as a refusal: there is no order to place under one share, so it is not a
  // leg in flight and it is not retried forever.
  const parts: string[] = [];
  if (owed > 0) {
    parts.push(
      `${owed} leg${owed === 1 ? "" : "s"} owed, ${dollars(tonight.owed_usd ?? 0)}, to be sent on the next close`,
    );
  }
  if (cannotSend > 0) {
    parts.push(
      `${cannotSend} owed, cannot be sent, ${dollars(tonight.cannot_send_usd ?? 0)}${
        unsendable ? `: ${unsendable}` : ""
      }`,
    );
  }
  return (
    <p data-tonight="true" className="text-xs text-slate-600">
      {parts.length > 0
        ? `tonight: ${parts.join("; ")}`
        : "tonight: nothing owed, nothing to send"}
    </p>
  );
}

/** The fields a panel cannot be drawn without, in the order the page reads them. */
const REQUIRED: Array<[string, (monthly: MonthlyBlock) => boolean]> = [
  ["anchor", (monthly) => Boolean(monthly.anchor?.close)],
  ["cadence_strip", (monthly) => Boolean(monthly.cadence_strip)],
  ["rebalance_card", (monthly) => Boolean(monthly.rebalance_card?.close)],
  [
    "bridge_anchor",
    (monthly) => Boolean(monthly.bridge_anchor?.flip_rows),
  ],
  ["drift", (monthly) => Boolean(monthly.drift?.largest)],
  ["since_anchor", (monthly) => Boolean(monthly.since_anchor?.trades_by_reason)],
];

/**
 * What the block is missing, so a partial one is visible rather than silent.
 *
 * The rule the panels follow is render what is there and say what is not: a document
 * whose block arrived half-built must not look like a complete one, and it must not
 * fall back to the nightly panels either, because the reader asked for the rebalance.
 */
export function incompleteFields(monthly?: MonthlyBlock | null): string[] {
  if (!monthly) return [];
  return REQUIRED.filter(([, present]) => !present(monthly)).map(([name]) => name);
}

/** Every anchored panel, or nothing at all when the document carries no block. */
export function MonthlyPanels({ monthly }: { monthly?: MonthlyBlock | null }) {
  if (!monthly) return null;
  const missing = incompleteFields(monthly);
  return (
    <div data-monthly="true" className="flex min-w-0 flex-col gap-3">
      {missing.length ? (
        <p
          data-monthly-incomplete={missing.join(",")}
          className="rounded border border-amber-400 bg-amber-50 px-3 py-2 text-sm text-amber-900"
        >
          monthly view incomplete: {missing.join(", ")}
        </p>
      ) : null}
      <CadenceStrip monthly={monthly} />
      <RebalanceCard monthly={monthly} />
      <FlipBridge monthly={monthly} />
      <DriftCard monthly={monthly} />
      <div data-columns="true" className="grid min-w-0 gap-3 lg:grid-cols-2">
        <TradesSinceAnchor monthly={monthly} />
        <Card
          title="tonight"
          howToRead="a leg is owed when the close asked for it and the broker did not fill it, so the next close sends it again. Example: on 11-11 nothing was owed, so the line says nothing to send."
        >
          <TonightLine monthly={monthly} />
        </Card>
      </div>
    </div>
  );
}
