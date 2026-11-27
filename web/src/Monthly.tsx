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

import { Fragment } from "react";

import { HowToRead } from "./Panel";
import { dateOnly, dollars, percent, signedDollars } from "./format";
import { legReasonWord } from "./labels";
import type { GuardFiring, MonthlyBlock } from "./types";

/** A date as the page writes dates in a sentence: month and day, no year. */
const dayShort = (value: string | null | undefined): string => (value ? value.slice(5, 10) : "-");

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
      data-window="EFB / since the rebalance"
      className="efb-window min-w-0 rounded border border-slate-200 bg-white px-3 py-2"
    >
      <h3>
        {title}
        <HowToRead>{howToRead}</HowToRead>
      </h3>
      {children}
    </section>
  );
}

function Stat({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="efb-stat-sm text-slate-900">{value}</dd>
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
      howToRead={`most closes change nothing: the book is rebuilt every ${strip.k ?? 21} sessions and repaired only when a factor exposure drifts too far. Example: ${strip.sessions_since ?? 0} of ${strip.k ?? 21} sessions have passed since ${dayShort(strip.last_rebalance)}, so the next rebuild is ${dayShort(strip.next_rebalance)}.`}
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
              : `day ${
                  (strip.day_in_cycle ?? ((strip.offset ?? 0) % (strip.k || 21))) || 1
                } of ${strip.k}`
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
      howToRead={`one evening turns the old book into the new one, so it is the month's largest trade and almost all of its cost. Example: on ${dayShort(card.close)} it sent ${card.sent_legs ?? card.filled_legs ?? 0} legs for ${dollars(card.notional)}, ${percent(card.pct_nav)} of NAV.`}
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
      <p className="mt-1 text-xs text-slate-600" data-cost-why="true">
        {costWhy(card)}
      </p>
    </Card>
  );
}

/**
 * Why the rebalance's realized cost is not the expected cost, in one line.
 *
 * The two are not two estimates of the same thing. The expected figure prices the
 * trade: spread, impact and commission. The realized figure is measured from the
 * previous close to each fill, and the loop sends after one close and fills at the
 * next open, so it carries the overnight move with it. A realized number can even be
 * negative, when the gap moved in the book's favour; that is a gain on the trade and
 * not a cost. On top of that the card counts 224 legs of which 16 were built under
 * the $250 minimum and never sent.
 */
function costWhy(card: NonNullable<MonthlyBlock["rebalance_card"]>): string {
  const realized = card.realized_cost_bps ?? null;
  const expected = card.expected_cost_bps ?? null;
  if (realized === null) {
    return "the day's fills have not been priced yet, so there is no realized figure to compare.";
  }
  if (expected === null) {
    return `realized ${realized.toFixed(1)} bp, measured from the previous close to each fill.`;
  }
  const under = realized <= expected;
  return `${realized.toFixed(1)} bp realized against ${expected.toFixed(
    1,
  )} bp expected: the realized figure is measured from the previous close to each fill, so it carries the overnight move, while the estimate priced the spread and impact of the trade alone${under ? ", and this time the gap moved in the book's favour" : ""}.`;
}

export function FlipBridge({ monthly }: { monthly: MonthlyBlock }) {
  const bridge = monthly.bridge_anchor;
  if (!bridge) return null;
  const flips = bridge.flip_rows ?? [];
  // The guard's own side changes, for the names the rebalance did not flip. They
  // belong in this list: a reader asking "what has changed side since 10-23" wants
  // all of them, not only the ones the rebuild made.
  const guardFlips = monthly.since_anchor?.guard_flips ?? [];
  // The date a leg carries is the fill's own when the store has one, and the close
  // it was priced from when it does not. The column says which, because a reader who
  // takes a close date for a fill date reads two days of a flip as one.
  const legsFilled = flips.some(
    (flip) => flip.close_filled_at || flip.open_filled_at,
  );
  const legDate = (filledAt: string | null | undefined, close: string | null): string =>
    dateOnly(filledAt ?? close) ?? "-";
  const nav = monthly.sectors?.nav ?? null;
  const nowClose = dateOnly(monthly.holdings?.as_of ?? null);
  const apart =
    nav === null ? null : Math.abs(nav - (bridge.after_dollars ?? 0));
  return (
    <Card
      title={`the book, from the ${dayShort(monthly.cadence_strip?.last_rebalance)} close to the account now`}
      howToRead={`the before and now figures are gross position value: every position's dollars added up, longs and shorts both counted positive. That is not NAV, which nets the shorts against the cash and adds it, so the two differ and both are right. Example: today the gross positions are ${dollars(
        bridge.after_dollars,
      )} and NAV is ${dollars(nav)}, ${dollars(apart)} apart.`}
    >
      <dl data-flips={bridge.flipped} className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
        <Stat
          label="before, gross positions"
          value={dollars(bridge.before_dollars)}
          detail={`${dayShort(monthly.cadence_strip?.last_rebalance)} close, longs and shorts added up; not NAV either`}
        />
        <Stat
          label="opened / exited"
          value={`${bridge.opened} / ${bridge.exited}`}
          detail={`${bridge.resized} resized since ${dayShort(monthly.cadence_strip?.last_rebalance)}`}
        />
        <Stat
          label="flips"
          value={`${bridge.flipped}`}
          detail={`${bridge.complete_flips} complete`}
        />
        <Stat
          label="now, gross positions"
          value={dollars(bridge.after_dollars)}
          detail={`${nowClose ?? "latest"} close, longs and shorts added up; NAV nets the shorts and adds cash`}
        />
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
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <span className="font-mono text-sm font-semibold">{flip.ticker}</span>
                    <span className="min-w-0 flex-1 break-words text-slate-700">
                      {flip.from_side} to {flip.to_side}
                    </span>
                    <span
                      data-flip-state={state}
                      className="w-full font-sans text-slate-600 sm:ml-auto sm:w-auto"
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
      {guardFlips.length ? (
        <div data-guard-flips="true" className="mt-2">
          <p className="text-xs font-medium text-slate-600">
            the drift guard flipped these names after the rebalance
          </p>
          <ul className="mt-1 flex flex-col gap-1 text-xs">
            {guardFlips.map((flip) => (
              <li
                key={flip.ticker}
                data-guard-flip={flip.ticker}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-slate-100 pb-1"
              >
                <span className="font-mono text-sm font-semibold">{flip.ticker}</span>
                <span className="min-w-0 break-words text-slate-700">
                  {flip.from_side} to {flip.to_side}
                </span>
                <span className="font-mono tabular-nums text-slate-600">
                  {dollars(flip.usd)}
                </span>
                <span className="text-slate-600">
                  moved by the drift guard on {dateOnly(flip.date) ?? flip.date}
                </span>
              </li>
            ))}
          </ul>
        </div>
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
  const next = monthly.cadence_strip?.next_rebalance ?? null;
  // The rate the rebalance was priced at, in bp of each dollar traded. A hold
  // day's manifest carries only borrow, and reading its residue as a rate is what
  // printed "about $0" for a trade of this size.
  const card = monthly.rebalance_card;
  const navBps =
    monthly.sectors?.nav !== null && monthly.sectors?.nav !== undefined && monthly.sectors.nav > 0
      ? monthly.sectors.nav
      : null;
  const traded = drift.traded_usd;
  const rate =
    card?.expected_cost_usd && card.expected_cost_usd > 0 && card?.notional && card.notional > 0
      ? (card.expected_cost_usd / card.notional) * 1e4
      : card?.expected_cost_bps && card.expected_cost_bps > 0 && card?.pct_nav && card.pct_nav > 0
        ? card.expected_cost_bps / card.pct_nav
        : null;
  // One rate, and the document's own when it carries it. `estimated_cost_bps`
  // is bp of NAV, so the dollars are that rate times NAV: the two figures are
  // the same number and cannot disagree, which is what a card that read the bp
  // from the document and the dollars from the rebalance's rate did. Only a
  // document without that field falls back to the rebalance's rate, and then
  // the bp are derived from those dollars rather than read from a second place.
  const docBps =
    drift.estimated_cost_bps !== null &&
    drift.estimated_cost_bps !== undefined &&
    drift.estimated_cost_bps > 0 &&
    navBps !== null
      ? drift.estimated_cost_bps
      : null;
  const costUsd =
    docBps !== null && navBps !== null
      ? (docBps / 1e4) * navBps
      : rate !== null && traded !== null && traded !== undefined
        ? (traded * rate) / 1e4
        : drift.estimated_cost_usd ?? null;
  const costBps =
    docBps ??
    (costUsd !== null && navBps !== null ? (costUsd / navBps) * 1e4 : null);
  // A nonzero trade is never free: a figure that rounds to $0 is treated as one
  // the block did not carry, rather than printed as a cost of nothing.
  const costKnown =
    costBps !== null && costUsd !== null && !((traded ?? 0) > 0 && Math.round(costUsd) === 0);
  // The rate is the anchor rebalance's own, so the sentence names that close rather
  // than a date typed in when the panel was written.
  const anchorDay = dayShort(monthly.cadence_strip?.last_rebalance);
  const costText = costKnown
    ? `${costBps!.toFixed(1)} bp of NAV (${dollars(costUsd)}) at the ${anchorDay} rebalance\u2019s own trading rate`
    : `at the ${anchorDay} rebalance\u2019s own trading rate, which the block does not carry`;
  return (
    <Card
      title="distance from the rebalance target"
      howToRead={
        drift.largest?.length
          ? `prices move the book away from the target every day, and so do the guard's own repairs: the target stays fixed until the next rebalance. The largest gaps now are ${drift.largest
              .slice(0, 3)
              .map((row) => `${row.ticker} ${signedDollars(row.usd)}`)
              .join(", ")}.`
          : "prices move the book away from the target every day, and so do the guard's own repairs: the target stays fixed until the next rebalance."
      }
    >
      <p className="text-sm text-slate-700" data-drift="true">
        The target stays fixed until the {next ?? "next"} rebalance, so the book is{" "}
        <span className="font-mono tabular-nums">{percent(drift.half_turnover_pct)}</span> of
        NAV away from it ({dollars(drift.half_turnover_usd)} on one side). Closing the gap
        today would trade <span className="font-mono tabular-nums">{dollars(drift.traded_usd)}</span>{" "}
        and cost {costText}. The gap includes every move the guard made on purpose,
        not only price drift.
      </p>
    </Card>
  );
}

/**
 * One card per evening the drift guard fired.
 *
 * The guard is a monthly-cadence repair: on a hold day it moves the book back to
 * factor-neutral when an exposure passes 5% of NAV. The events are in the hold days'
 * own manifests, so each card can state the date, what the guard found and left, the
 * legs it sent and their dollars. The cost is the day's fills when the store carries
 * them; a day it does not carry says so instead of printing zero.
 */
export function GuardCards({ monthly }: { monthly: MonthlyBlock }) {
  const firings = monthly.since_anchor?.guard_history ?? [];
  if (!firings.length) return null;
  // The estimate the cost-by-era row also quotes, at the rebalance's own rate. The
  // measured figure is the day's fills, and it includes the overnight move; the two
  // are stated side by side so neither is read as the other.
  const card = monthly.rebalance_card;
  const rate =
    card?.expected_cost_usd && card?.notional
      ? (card.expected_cost_usd / card.notional) * 1e4
      : card?.expected_cost_bps && card?.pct_nav
        ? card.expected_cost_bps / card.pct_nav
        : null;
  const nav = monthly.sectors?.nav ?? null;
  const estimate = (usd: number | null | undefined): number | null =>
    rate === null || !usd || !nav ? null : -((usd * rate) / 1e4 / nav) * 1e4;
  return (
    <>
      {firings.map((firing) => (
        <Card
          key={firing.date}
          title={`drift guard, ${dateOnly(firing.date) ?? firing.date}`}
          howToRead="on a hold day the guard repairs the book only when a factor exposure passes 5% of NAV. It moves the names the book already holds, so the dollars are the legs it had to re-size, not a new position. Example: the 11-04 firing took the worst exposure from 6.41% to 0.41% with 109 legs."
        >
          <dl
            data-guard-firing={firing.date}
            className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4"
          >
            <Stat
              label="worst exposure"
              value={`${percent(firing.exposure_before)} to ${percent(firing.exposure_after)}`}
              detail={`against the ${percent(firing.threshold)} line`}
            />
            <Stat
              label="legs sent"
              value={String(firing.legs_sent ?? 0)}
              detail={`${firing.legs_not_sent ?? firing.legs_under_minimum ?? 0} not sent, under the $250 floor`}
            />
            <Stat
              label="dollars sent"
              value={dollars(firing.usd)}
              detail={
                firing.not_sent_usd === null || firing.not_sent_usd === undefined
                  ? "the legs it moved"
                  : `${dollars(firing.not_sent_usd)} of legs not sent`
              }
            />
            <Stat
              label="cost, measured from fills"
              value={
                firing.cost_bps === null
                  ? "not measured"
                  : `${(-firing.cost_bps).toFixed(1)} bp`
              }
              detail={
                firing.cost_bps === null
                  ? "the store carries no fills for this day"
                  : estimate(firing.usd) === null
                    ? "the day's fills; no estimate to compare"
                    : `estimated ${estimate(firing.usd)?.toFixed(1)} bp at the rebalance's rate`
              }
            />
          </dl>
          <p className="mt-1 text-xs text-slate-600">
            {firing.flips.length
              ? `it moved ${firing.flips.join(", ")} back to the other side`
              : "no name changed side because of this firing"}
            {Object.entries(firing.reversals ?? {}).map(([ticker, rebalance]) => (
              <span key={ticker} data-guard-reversal={ticker}>
                {"; "}
                {ticker} reverses the {rebalance} flip
              </span>
            ))}
          </p>
        </Card>
      ))}
    </>
  );
}

/** The window's firings: nothing dated before the current rebalance. */
function firingsInWindow(monthly: MonthlyBlock): GuardFiring[] {
  const anchor = monthly.anchor?.close ?? monthly.cadence_strip?.last_rebalance ?? null;
  const rows = monthly.since_anchor?.guard_history ?? [];
  return anchor ? rows.filter((row) => !row.date || row.date >= anchor) : rows;
}

/** The floor legs across the window's firings, the same field the rows print. */
function firingsUnder(monthly: MonthlyBlock): number {
  return firingsInWindow(monthly).reduce(
    (total, firing) => total + (firing.legs_not_sent ?? firing.legs_under_minimum ?? 0),
    0,
  );
}

function firingsUnderUsd(monthly: MonthlyBlock): number {
  return firingsInWindow(monthly).reduce(
    (total, firing) => total + (firing.not_sent_usd ?? 0),
    0,
  );
}

export function TradesSinceAnchor({ monthly }: { monthly: MonthlyBlock }) {
  const trades = monthly.since_anchor?.trades_by_reason ?? [];
  const notSent = monthly.since_anchor?.not_sent;
  if (!trades.length) return null;
  const under = notSent?.under_minimum;
  // The footer counts what the table's own under-$250 rows count: the rebalance's
  // floor legs plus each firing's, from the same fields the rows print. Two
  // numbers that describe one set of legs cannot disagree if one is a sum of the
  // other.
  const underLegs =
    (monthly.rebalance_card?.under_minimum_legs ?? under?.legs ?? 0) +
    firingsUnder(monthly);
  const underUsd =
    (monthly.rebalance_card?.under_minimum_usd ?? under?.usd ?? 0) +
    firingsUnderUsd(monthly);
  // Three shapes, newest first: the refusals counted by name, the tonight line's
  // own list, and the older aggregate by reason code. Each names the position
  // rather than counting the nights it was refused.
  const refusedNames = notSent?.refused_names ?? [];
  const cannot = monthly.tonight?.cannot_send ?? [];
  const refusedCodes = notSent?.other ?? [];
  const refusedCount = refusedNames.length + cannot.length + refusedCodes.length;
  return (
    <Card
      title="every leg since the rebalance, by why it went"
      howToRead="a leg is one order in one direction, and the reason says which event asked for it. The count moves when a rebalance lands, when a flip needs its second day, or when the guard fires. Example: 8 legs on 10-26 re-traded a rebalance that had already filled, so they are their own row, fixed 10-27."
    >
      <div className="overflow-x-auto">
        <table data-trades-reason="true" className="efb-legs w-full text-left text-xs">
          <thead>
            <tr>
              <th className="pb-1 pr-2">reason</th>
              <th className="efb-num pb-1 pr-2">legs</th>
              <th className="efb-num pb-1">dollars</th>
            </tr>
          </thead>
          <tbody>
          {trades.map((row) => {
            const sent = row.sent_legs ?? row.legs;
            const firings = row.reason === "guard" ? firingsInWindow(monthly) : [];
            return (
              <Fragment key={row.reason}>
                <tr data-reason={row.reason}>
                  <td className="py-0.5 pr-2 font-medium">{row.reason}</td>
                  <td className="py-0.5 pr-2 text-right font-mono tabular-nums">
                    {row.reason === "rebalance" && sent < row.legs
                      ? (() => {
                          // One definition: a leg sized with a nonzero change that
                          // was not sent because it was under the $250 floor. A
                          // refusal is a different line, so it is named as one
                          // instead of folded into the floor count.
                          const under =
                            monthly.rebalance_card?.under_minimum_legs ??
                            row.legs - sent;
                          const refused = row.legs - sent - under;
                          // On a phone the three facts get a line each instead of one
                          // wrapped cell; the string a reader or a test sees is the
                          // same with the commas in place.
                          return (
                            <>
                              <span className="efb-split">{`${sent} sent, `}</span>
                              <span className="efb-split">{`${under} not sent (under $250)`}</span>
                              {refused > 0 ? (
                                <span className="efb-split">{`, ${refused} refused`}</span>
                              ) : null}
                            </>
                          );
                        })()
                      : row.reason === "carried leg"
                        ? `${row.legs} leg, impossible (under one share)`
                        : sent === row.legs
                          ? `${row.legs} legs`
                          : `${sent} sent, ${row.legs - sent} not sent`}
                  </td>
                  <td className="py-0.5 text-right font-mono tabular-nums">
                    {dollars(row.usd)}
                  </td>
                </tr>
                {firings.map((firing) => (
                  <tr
                    key={`${row.reason}-${firing.date}`}
                    data-guard-date={firing.date}
                    className="text-slate-500"
                  >
                    <td className="py-0.5 pl-3 font-normal">
                      of which guard, {dateOnly(firing.date) ?? firing.date}
                    </td>
                    <td className="py-0.5 text-right font-mono tabular-nums">
                      {firing.legs_sent ?? 0} legs
                    </td>
                    <td className="py-0.5 text-right font-mono tabular-nums">
                      {dollars(firing.usd)}
                    </td>
                  </tr>
                ))}
                {/* The same pair the guard card prints, from the same fields: the
                    card and the table say one number, not two. */}
                {firings.map((firing) => (
                  <tr
                    key={`${row.reason}-${firing.date}-under`}
                    data-guard-under={firing.date}
                    className="text-slate-500"
                  >
                    <td className="pb-0.5 pl-6 text-xs font-normal">
                      under $250, not sent
                    </td>
                    <td className="pb-0.5 text-right font-mono tabular-nums text-xs">
                      {firing.legs_not_sent ?? firing.legs_under_minimum ?? 0} legs
                    </td>
                    <td className="pb-0.5 text-right font-mono tabular-nums text-xs">
                      {firing.not_sent_usd === null || firing.not_sent_usd === undefined
                        ? "-"
                        : dollars(firing.not_sent_usd)}
                    </td>
                  </tr>
                ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      </div>
      {under || refusedCount ? (
        <div data-not-sent="true" className="mt-1 text-xs text-slate-500">
          <p>
            not sent: {notSent?.legs ?? 0} legs ({dollars(notSent?.usd ?? 0)}). {underLegs}{" "}
            under $250 ({dollars(underUsd)})
            {refusedCount ? ", and " : ""}
            {refusedNames.length
              ? refusedNames.map((row, index) => (
                  <span key={row.ticker} data-refused-name={row.ticker}>
                    {index > 0 ? "; " : ""}
                    {row.ticker} {dollars(row.usd)} ({legReasonWord(row.status)}, refused on{" "}
                    {row.legs} nights from {dateOnly(row.first_close)} to{" "}
                    {dateOnly(row.last_close)})
                  </span>
                ))
              : (
                  <>
                    {cannot.map((leg, index) => (
                      <span key={leg.ticker} data-refused-name={leg.ticker}>
                        {index > 0 ? "; " : ""}
                        {leg.ticker} {dollars(leg.usd)} ({legReasonWord(leg.code)}; one name,
                        refused on every night, and the leg total above counts it once per
                        night)
                      </span>
                    ))}
                    {/* The codes are the older shape and are only drawn when the
                        document names no position: once the name is known, counting
                        the same holding per code is the double count this line fixes. */}
                    {cannot.length === 0
                      ? refusedCodes.map((row, index) => (
                          <span key={row.code} data-refused-code={row.code}>
                            {index > 0 ? "; " : ""}
                            {row.legs} {row.legs === 1 ? "leg" : "legs"} ({legReasonWord(row.code)},{" "}
                            {dollars(row.usd)})
                          </span>
                        ))
                      : null}
                  </>
                )}
            .
          </p>
          {under?.by_day && under.by_day.length > 0 ? (
            <p data-not-sent-parts="true">
              the {under.legs} under $250 were asked for on these closes:{" "}
              {under.by_day
                .map((day) => `${day.legs} on ${dateOnly(day.close) ?? day.close}`)
                .join(", ")}
              .
            </p>
          ) : null}
          {notSent?.usd_by_name !== undefined ? (
            <p data-not-sent-by-name="true">
              by name the positions that never traded are worth {dollars(notSent.usd_by_name)}:
              the same holding was refused on several nights, and the leg total above
              counts it once per night.
            </p>
          ) : null}
        </div>
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
    .map((leg) => {
      const reason = legReasonWord(leg.code);
      return reason ? `${leg.ticker}, ${reason}` : leg.ticker;
    })
    .join("; ");
  // A leg that will be sent on the next close and a leg that can never be sent are
  // both "forced", and one line said "1 forced leg, $269" for either. The refusal is
  // stated as a refusal: there is no order to place under one share, so it is not a
  // leg in flight and it is not retried forever.
  const parts: string[] = [];
  if (owed > 0) {
    // Plain words, and no dollars when there are none: "4 legs owed, $0" is a
    // sentence about a rounding error, not about a position.
    const usd = tonight.owed_usd ?? 0;
    parts.push(
      `${owed} leg${owed === 1 ? "" : "s"} to send on the next close${usd >= 1 ? ` (${dollars(usd)})` : ""}`,
    );
  }
  if (cannotSend > 0) {
    parts.push(
      `${cannotSend} leg${cannotSend === 1 ? "" : "s"} that cannot be sent, ${dollars(
        tonight.cannot_send_usd ?? 0,
      )}${unsendable ? `: ${unsendable}` : ""}`,
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
      <GuardCards monthly={monthly} />
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
