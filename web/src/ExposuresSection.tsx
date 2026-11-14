// The factor exposures, before and after the hedge, as a heat table.
//
// This is the page's one picture of the hedge doing its job. It used to be bars on
// one scale, and one row broke the picture: momentum is about 87% of NAV before the
// 10-23 rebalance, so every other bar was a sliver against it and the after column
// read as empty space rather than as a measurement. A heat table keeps the three
// numbers in their cells and lets the colour carry the size: the darkest cell is the
// largest exposure, and a pale cell is a small one rather than a missing one.

import { Details } from "./Details";
import { anchoredHedge } from "./HedgePanel";
import { HowToRead } from "./Panel";
import { count, dateOnly, dollars, percent } from "./format";
import type { MonthlyBlock, Snapshot } from "./types";

// The factor vocabulary, styles first then sectors, in the order the reader wants
// them: what the portfolio is tilted towards, then where it sits. The sector labels
// are GICS names with their codes, because `sector_45` is not a thing anyone reads
// off a screen.
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
// intercept rather than by a column of its own. Named in the table itself: a reader
// who knows the GICS codes asks where 60 went.
const REFERENCE_SECTOR = "60 Real Estate";

/**
 * The anchor close's own before/after pair, when tonight is a hold day.
 *
 * A hold day builds no hedge: the evening sizes nothing, the guard may trade the
 * held book, and the document's own `exposures_before_hedge` and
 * `exposures_after_hedge` are the same vector twice. So the pair that means anything
 * is the rebalance's, and this is where the page gets it. `null` on a rebalance day,
 * on the daily loop and on any document written before the field existed, all of
 * which render exactly as they did.
 */
export function anchoredExposures(
  monthly?: MonthlyBlock | null,
): NonNullable<MonthlyBlock["anchor_exposures"]> | null {
  if (monthly?.anchor?.day !== "cadence") return null;
  const block = monthly?.anchor_exposures;
  if (!block) return null;
  const before = block.before ?? {};
  const after = block.after ?? {};
  if (Object.keys(before).length === 0 || Object.keys(after).length === 0) return null;
  return block;
}

/** The largest absolute value in a factor vector. */
function worstOf(vector: Record<string, number | null>): number {
  return Object.values(vector).reduce<number>(
    (worst, value) => Math.max(worst, Math.abs(value ?? 0)),
    0,
  );
}

/**
 * The rows of the exposure table: styles, sectors, then anything the design carries
 * that this list does not know about, so a new factor cannot disappear from the page
 * by being unlisted.
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
 * The light tint one exposure cell carries: none at zero, the faintest wash at a
 * sliver, the strongest at the largest number on the page. The palette is light on
 * purpose: the value is printed in the cell, and a dark block behind dark text is a
 * cell nobody can read.
 */
const HEAT: Record<string, [number, number, number]> = {
  before: [100, 116, 139],
  after: [5, 150, 105],
  now: [217, 119, 6],
};

/** A cell's value, as the share of the book it is. The table is read in percent. */
const heatText = (value: number | null | undefined): string => percent(value, 2);

export function heatFill(tone: string, value: number, scale: number): string {
  const share = scale > 0 ? Math.min(1, Math.abs(value) / scale) : 0;
  const [r, g, b] = HEAT[tone] ?? HEAT.before;
  // The top of the scale stays light: the value is printed in the cell, so the
  // shade has to leave dark text readable at the largest number as well.
  const alpha = share === 0 ? 0 : 0.06 + share * 0.3;
  return alpha === 0 ? "transparent" : `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`;
}

/**
 * Tonight's wanted orders, in one plain line.
 *
 * Two numbers were on the page and neither said what happened to the money: the
 * dollars the evening wanted to trade, and the dollars it sent. The line names the
 * ones that could not go and why, because "blocked" on its own sends a reader
 * looking for a failure the page then does not explain. KVUE is the live example:
 * KMB bought the company, so the symbol is inactive and no order can close it.
 */
export function wantedOrders(snapshot: Snapshot): { text: string } {
  const sent = snapshot.reconciliation?.sent_notional ?? null;
  const intended = snapshot.reconciliation?.intended_notional ?? null;
  const blocked = snapshot.monthly?.tonight?.cannot_send ?? [];
  // The names tonight's run traded, from the holding rows it marked. The document
  // stores the sent dollars as a total, not per leg, so a name is printed only when
  // exactly one name was traded: that is the one case where the total is its dollars.
  const tradedTonight = (snapshot.monthly?.holdings?.rows ?? []).filter(
    (row) => !row.retired && (row.tonight ?? "").startsWith("traded tonight"),
  );
  if ((sent === null || sent === 0) && blocked.length === 0) {
    if (intended === null || intended === 0) {
      return { text: "nothing wanted tonight." };
    }
    return { text: `${dollars(intended)}, none of it sent.` };
  }
  const parts: string[] = [];
  if (blocked.length > 0) {
    parts.push(
      blocked
        .map(
          (leg) =>
            `${leg.ticker} ${dollars(leg.usd)} blocked${
              leg.code === "ASSET_INACTIVE" ? " because the company was acquired" : ""
            }`,
        )
        .join(", "),
    );
  }
  if (sent !== null && sent > 0) {
    parts.push(
      tradedTonight.length === 1
        ? `${tradedTonight[0].ticker} ${dollars(sent)} sent`
        : `${dollars(sent)} sent`,
    );
  }
  if (parts.length === 0) {
    return { text: "nothing wanted tonight." };
  }
  return { text: `${parts.join(", ")}.` };
}

export function ExposuresSection({ snapshot }: { snapshot: Snapshot }) {
  const tonightBefore = snapshot.exposures_before_hedge ?? {};
  const tonightAfter = snapshot.exposures_after_hedge ?? {};
  if (Object.keys(tonightBefore).length === 0 && Object.keys(tonightAfter).length === 0) {
    return null;
  }
  // A hold day anchors the pair on the close that hedged; every other document uses
  // its own, which is tonight's own.
  const anchor = anchoredExposures(snapshot.monthly);
  const before = anchor ? anchor.before : tonightBefore;
  const after = anchor ? anchor.after : tonightAfter;
  const anchorClose = anchor ? (anchor.anchor ?? "") : "";
  const guard = snapshot.monthly?.cadence_strip?.guard;
  const hedgeBlock = anchoredHedge(snapshot.monthly);
  const guardFired = Boolean(anchor && guard?.fired);
  const rows = exposureRows({ ...tonightBefore, ...before });
  const scale = Math.max(
    ...[
      ...Object.values(before),
      ...Object.values(after),
      ...(anchor ? Object.values(tonightBefore) : []),
    ].map((value) => Math.abs(value ?? 0)),
    0.0001,
  );
  // Present only when the evening recorded one: the key is absent on a document
  // built without a reconciled row, and a missing figure is not a zero figure.
  const adjustment = (snapshot.reconciliation?.unexplained_adjustment as number | null) ?? null;

  return (
    <section data-section="exposures" className="rounded border border-slate-200 bg-white p-3">
      <h2 className="text-base font-semibold">The hedge <HowToRead>
        a factor exposure away from zero is a bet the book did not mean to take, and the
        drift guard acts when one passes 5% of NAV. Example: before the 10-23 rebalance
        the book leaned 87.2% of NAV on momentum, and the hedge took that to zero.
      </HowToRead></h2>
      {anchor ? (
        <>
          <p className="mt-1 text-sm" data-hedge-verdict="true" data-hedge-anchor={anchorClose}>
            the {anchorClose} rebalance cut the book&apos;s worst factor exposure from{" "}
            <span className="font-mono tabular-nums">
              {heatText(worstOf(before))}
            </span>{" "}
            to{" "}
            <span className="font-mono tabular-nums">
              {heatText(worstOf(anchor.after))}
            </span>
            . Nothing was hedged tonight, so the &quot;now&quot; column is the book as it
            stands, not a hedge&apos;s output.
          </p>
          {guardFired ? (
            <p className="mt-1 text-sm text-amber-800" data-hedge-guard="true">
              drift guard tonight: worst{" "}
              <span className="font-mono tabular-nums">
                {percent(guard?.worst_abs_exposure)}
              </span>{" "}
              →{" "}
              <span className="font-mono tabular-nums">{percent(guard?.exposure_after)}</span>{" "}
              against{" "}
              <span className="font-mono tabular-nums">{percent(guard?.threshold)}</span>,{" "}
              {count(guard?.legs ?? null)} sent leg(s); the after value assumes they fill.
            </p>
          ) : null}
        </>
      ) : (
        <p className="mt-1 text-sm" data-hedge-verdict="true">
          after the hedge the book&apos;s worst factor exposure is{" "}
          <span className="font-mono tabular-nums">
            {heatText(worstOf(after))}
          </span>{" "}
          and the book as it stands is{" "}
          <span className="font-mono tabular-nums">
            {heatText(snapshot.hedge?.max_abs_exposure_after_fmp)}
          </span>
          . Every factor row below is close to zero because the hedge removed the bet, and
          the rows are the receipt.
        </p>
      )}
      <Details
        hook="exposures"
        open
        summary={
          <>
            every factor as a heat table: before, after and now, {rows.length} row(s)
          </>
        }
      >
      <div className="overflow-x-auto">
        {/* Every column states its own width. The value columns are only as wide as
            their widest number otherwise, so "after" and "before / after" touch and
            read as one label, and the bars column is the width of the bars it holds. */}
        {/* Fixed layout with percentage columns, so the table is exactly as wide as
            the box it sits in at any width: a phone must not scroll sideways to read
            a table, and a factor name that needs two lines is the cheap half of that
            trade. */}
        <table
          className="mt-2 w-full table-fixed border-collapse text-xs"
          aria-label="factor exposures"
          data-heat-table="true"
        >
          <thead>
            <tr className="border-b border-slate-300 align-top text-left">
              <th className="w-[34%] py-1 pr-1">factor</th>
              <th className="w-[22%] py-1 pl-1 text-right leading-tight" data-column="before">
                before the hedge
                {anchor ? (
                  <span className="block text-[0.65rem] font-normal text-slate-500">
                    {" "}
                    {anchorClose}
                  </span>
                ) : null}
              </th>
              <th className="w-[22%] py-1 pl-1 text-right leading-tight" data-column="after">
                after the hedge
                {anchor ? (
                  <span className="block text-[0.65rem] font-normal text-slate-500">
                    {" "}
                    {anchorClose}
                  </span>
                ) : null}
              </th>
              {anchor ? (
                <th className="w-[22%] py-1 pl-1 text-right leading-tight" data-column="now">
                  now
                  <span className="block text-[0.65rem] font-normal text-slate-500">
                    {" "}
                    {dateOnly(snapshot.target_close) ?? "tonight"}
                  </span>
                </th>
              ) : null}
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
                  <td className="break-words py-1 pr-1">{label}</td>
                  <td
                    className="py-1 text-right font-mono tabular-nums"
                    data-heat="before"
                    style={{ backgroundColor: heatFill("before", before[key] ?? 0, scale) }}
                  >
                    {heatText(before[key])}
                  </td>
                  <td
                    className="py-1 text-right font-mono tabular-nums"
                    data-heat="after"
                    style={{ backgroundColor: heatFill("after", after[key] ?? 0, scale) }}
                  >
                    {heatText(after[key])}
                  </td>
                  {anchor ? (
                    <td
                      className="py-1 text-right font-mono tabular-nums"
                      data-now={key}
                      data-heat="now"
                      style={{
                        backgroundColor: heatFill("now", tonightBefore[key] ?? 0, scale),
                      }}
                    >
                      {heatText(tonightBefore[key])}
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        The shade is one scale, the largest exposure on the page: the darkest cell is the
        biggest bet, and a pale cell is a small number rather than a missing one.{" "}
        {REFERENCE_SECTOR} is the reference sector and has no column of its own, so the ten
        sectors above are measured against it.
      </p>
      </Details>
      <dl className="mt-2 grid gap-1 text-sm text-slate-700" data-hedge-lines="true">
        <div className="flex flex-wrap gap-x-2" data-hedge-line="after">
          <dt className="font-medium">after the rebalance hedge:</dt>
          <dd>
            worst factor exposure{" "}
            <span className="font-mono tabular-nums">{heatText(after && worstOf(after))}</span>
            {anchor ? `, on the ${anchorClose} close` : ""}.
            {hedgeBlock
              ? ` The hedge moved ${count(hedgeBlock.moved_names)} of ${count(
                  hedgeBlock.book_names,
                )} names.`
              : ""}
          </dd>
        </div>
        <div className="flex flex-wrap gap-x-2" data-hedge-line="now">
          <dt className="font-medium">now:</dt>
          <dd>
            worst factor exposure{" "}
            <span className="font-mono tabular-nums">
              {heatText(snapshot.hedge?.max_abs_exposure_after_fmp)}
            </span>
            {guard?.threshold === null || guard?.threshold === undefined
              ? ""
              : `, against the ${percent(guard.threshold)} guard line`}
            .{" "}
            <span className="font-mono tabular-nums">
              {percent(snapshot.hedge?.idio_share_after_fmp, 1)}
            </span>{" "}
            of the book&apos;s predicted risk sits in the stocks themselves, not the factors.
          </dd>
        </div>
        <div className="flex flex-wrap gap-x-2" data-hedge-line="orders">
          <dt className="font-medium">Tonight&apos;s wanted orders:</dt>
          <dd data-wanted-orders="true">
            {wantedOrders(snapshot).text}
          </dd>
        </div>
        {adjustment ? (
          // The day's P&L is the account's own equity move, and this is the part of
          // it that no order of the loop's explains: a position that left with
          // nothing behind it. It is labelled rather than netted out of the P&L,
          // because a number quietly adjusted is one nobody can check, and the
          // figure is the account's paper keeping rather than a result of the book.
          <div className="flex flex-wrap gap-x-2" data-figure="unexplained-adjustment">
            <dt className="font-medium">money that moved with no order behind it:</dt>
            <dd className="font-mono tabular-nums">{dollars(adjustment)}</dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}
