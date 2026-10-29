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

import { dateOnly, dollars, exposure, percent, signedDollars } from "./format";
import type { MonthlyBlock } from "./types";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      data-panel="monthly"
      className="rounded border border-slate-200 bg-white px-3 py-2"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title}
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
    <Card title="cadence">
      <dl data-cadence="true" className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
        <Stat
          label="hold day"
          value={
            strip.k === null || strip.k === undefined
              ? "daily"
              : strip.k === 1
                ? "daily"
                : `${strip.sessions_since ?? 0} of ${strip.k}`
          }
        />
        <Stat label="last rebalance" value={dateOnly(strip.last_rebalance) ?? "-"} />
        <Stat label="next rebalance" value={dateOnly(strip.next_rebalance) ?? "-"} />
        <Stat
          label="drift guard"
          value={`${exposure(guard.worst_abs_exposure)} worst`}
          detail={
            guard.threshold === null || guard.threshold === undefined
              ? `threshold not recorded, ${fired}`
              : `threshold ${exposure(guard.threshold)}, ${fired}`
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
    <Card title={`the rebalance of ${dateOnly(card.close) ?? "the anchor"}`}>
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
          value={`${card.legs_complete ?? 0} of ${card.legs_total ?? 0} legs`}
          detail={`${dollars(card.dollars_owed)} still owed`}
        />
      </dl>
    </Card>
  );
}

export function FlipBridge({ monthly }: { monthly: MonthlyBlock }) {
  const bridge = monthly.bridge_anchor;
  if (!bridge) return null;
  const flips = bridge.flip_rows ?? [];
  return (
    <Card title="the rebalance, from the account before it to the account now">
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
        <table data-flip-table="true" className="mt-2 w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="font-medium">name</th>
              <th className="font-medium">side</th>
              <th className="font-medium text-right">closed</th>
              <th className="font-medium text-right">opened</th>
              <th className="font-medium text-right">now</th>
              <th className="font-medium">state</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {flips.map((flip) => (
              <tr key={flip.ticker} data-flip={flip.ticker}>
                <td className="font-semibold">{flip.ticker}</td>
                <td>
                  {flip.from_side} to {flip.to_side}
                </td>
                <td className="text-right">
                  {dollars(flip.close_dollars)}
                  <span className="text-slate-500"> {dateOnly(flip.close_filled)}</span>
                </td>
                <td className="text-right">
                  {dollars(flip.open_dollars)}
                  <span className="text-slate-500"> {dateOnly(flip.open_filled)}</span>
                </td>
                <td className="text-right">{signedDollars(flip.now_dollars)}</td>
                <td>{flip.complete ? "complete" : "still owed"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <p className="mt-1 text-xs text-slate-500">
        a flip counts once, with both legs, and is complete when the account is on the
        target side within the order minimum. It is never an exit plus an open.
      </p>
    </Card>
  );
}

export function DriftCard({ monthly }: { monthly: MonthlyBlock }) {
  const drift = monthly.drift;
  if (!drift) return null;
  return (
    <Card title="distance from the rebalance target">
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
        <table data-drift-table="true" className="mt-2 w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="font-medium">name</th>
              <th className="font-medium text-right">now</th>
              <th className="font-medium text-right">target</th>
              <th className="font-medium text-right">gap</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {drift.largest.map((row) => (
              <tr key={row.ticker}>
                <td className="font-semibold">{row.ticker}</td>
                <td className="text-right">{percent(row.weight_now)}</td>
                <td className="text-right">{percent(row.weight_target)}</td>
                <td className="text-right">{signedDollars(row.usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </Card>
  );
}

export function TradesSinceAnchor({ monthly }: { monthly: MonthlyBlock }) {
  const trades = monthly.since_anchor?.trades_by_reason ?? [];
  if (!trades.length) return null;
  return (
    <Card title="every leg since the rebalance, by why it went">
      <table data-trades-reason="true" className="w-full text-left text-xs">
        <tbody className="font-mono">
          {trades.map((row) => (
            <tr key={row.reason}>
              <td className="font-semibold">{row.reason}</td>
              <td className="text-right">{row.legs} legs</td>
              <td className="text-right">{dollars(row.usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

export function TonightLine({ monthly }: { monthly: MonthlyBlock }) {
  const tonight = monthly.tonight;
  if (!tonight) return null;
  return (
    <p data-tonight="true" className="text-xs text-slate-600">
      tonight: {tonight.forced_legs} forced leg{tonight.forced_legs === 1 ? "" : "s"},{" "}
      {dollars(tonight.forced_usd)}
    </p>
  );
}

/** Every anchored panel, or nothing at all when the document carries no block. */
export function MonthlyPanels({ monthly }: { monthly?: MonthlyBlock | null }) {
  if (!monthly) return null;
  return (
    <div data-monthly="true" className="flex flex-col gap-3">
      <CadenceStrip monthly={monthly} />
      <RebalanceCard monthly={monthly} />
      <FlipBridge monthly={monthly} />
      <DriftCard monthly={monthly} />
      <div data-columns="true" className="grid gap-3 lg:grid-cols-2">
        <TradesSinceAnchor monthly={monthly} />
        <Card title="tonight">
          <TonightLine monthly={monthly} />
        </Card>
      </div>
    </div>
  );
}
