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

// The rows keep the design's order and lose the design's numbers: "45" is the
// GICS code, not part of the sector's name, and a reader scanning a column of
// exposures should not have to parse a code to find Health Care.
const SECTOR_ROWS: Array<[string, string]> = [
  ["sector_10", "Energy"],
  ["sector_15", "Materials"],
  ["sector_20", "Industrials"],
  ["sector_25", "Consumer Discretionary"],
  ["sector_30", "Consumer Staples"],
  ["sector_35", "Health Care"],
  ["sector_40", "Financials"],
  ["sector_45", "Information Technology"],
  ["sector_50", "Communication Services"],
  ["sector_55", "Utilities"],
];

// The sector dummy the design leaves out, so its exposure is carried by the
// intercept rather than by a column of its own. Named in the table itself: a reader
// who knows the GICS codes asks where 60 went.
const REFERENCE_SECTOR = "Real Estate";

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
 * The two hues, one per sign, and the neutral they fade to at zero.
 *
 * One hue cannot carry a sign: a page of slate washes says "some size" and nothing
 * about direction, which is the half of a factor exposure a reader acts on. Blue is a
 * long tilt, rose is a short one, and a cell at zero is left unpainted so it stays
 * near white. The palette is light on purpose: the value is printed in the cell, and a
 * dark block behind dark text is a cell nobody can read.
 */
const POSITIVE: [number, number, number] = [37, 99, 235];
const NEGATIVE: [number, number, number] = [225, 29, 72];

/** Below this a column reads as zero at the page's own precision. */
const FLAT_UNDER = 0.00005;

/** The drift guard's own line: a now cell at or beyond it gets the amber ring. */
const GUARD_BAND = 0.05;

/** The two inks. Which one a cell takes is decided by its own background. */
const DARK_INK = "#191713";
const LIGHT_INK = "#efebe2";

/** One sRGB channel, linearised for a WCAG contrast ratio. */
const linear = (value: number): number => {
  const channel = value / 255;
  return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
};

/** A colour's relative luminance, from its three channels. */
const luminance = ([r, g, b]: [number, number, number]): number =>
  0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);

/** The contrast ratio between two luminances, always at or above 1. */
const ratio = (a: number, b: number): number => {
  const [high, low] = a > b ? [a, b] : [b, a];
  return (high + 0.05) / (low + 0.05);
};

const hexRgb = (hex: string): [number, number, number] => [
  parseInt(hex.slice(1, 3), 16),
  parseInt(hex.slice(3, 5), 16),
  parseInt(hex.slice(5, 7), 16),
];

/**
 * A fill as it lands on the page: the tint composited over the card's white.
 *
 * A cell's background is a translucent wash over white, so the colour the eye sees is
 * the blend, and that blend is what the text has to be readable on.
 */
const landed = (fill: string): [number, number, number] => {
  const match = fill.match(/rgba?\(([^)]+)\)/);
  if (!match) return [255, 255, 255];
  const parts = match[1].split(",").map((part) => Number(part.trim()));
  const [r, g, b] = parts;
  const alpha = parts.length > 3 ? parts[3] : 1;
  return [
    r * alpha + 255 * (1 - alpha),
    g * alpha + 255 * (1 - alpha),
    b * alpha + 255 * (1 - alpha),
  ];
};

/** A colour given either way: a hex literal or an rgba string. */
const inkRgb = (ink: string): [number, number, number] =>
  ink.startsWith("#") ? hexRgb(ink) : landed(ink);

/** The contrast ratio between a cell's background and an ink, as WCAG measures it. */
export const heatContrast = (fill: string, ink: string): number =>
  ratio(luminance(landed(fill)), luminance(inkRgb(ink)));

/**
 * The ink a cell's value takes: dark on a light fill, light on a dark one.
 *
 * One text colour cannot serve both ends of a scale. Today's palette is light enough
 * that every cell takes the dark ink and clears 4.5:1 by a wide margin, but the
 * choice is made per cell from the colour the cell actually has, so a darker palette
 * (or a dark fill in a future column) switches that cell's number to the light ink
 * instead of printing dark text on a dark block.
 */
export const heatInk = (fill: string): string =>
  heatContrast(fill, DARK_INK) >= heatContrast(fill, LIGHT_INK) ? DARK_INK : LIGHT_INK;

/** A cell's value, as the share of the book it is. The table is read in percent. */
const heatText = (value: number | null | undefined): string => percent(value, 2);

/**
 * The sign a cell's colour is built from, exposed so a test can read it.
 *
 * A value that prints as 0.00% is signed zero, not a tiny long: a cell the reader sees
 * as zero and a cell coloured as a bet would be the page contradicting itself.
 */
export const heatSign = (value: number): "positive" | "negative" | "zero" =>
  Math.abs(value) < FLAT_UNDER ? "zero" : value > 0 ? "positive" : "negative";

/**
 * The tint one cell carries, on its own column's scale.
 *
 * The scale is per column because the columns are not the same size: before the 10-23
 * hedge one factor reached 87% of NAV, while now the whole column moves inside 2%, and
 * one shared scale turned the second column into a single pale wash. The largest value
 * in a column is that column's strongest shade; a column that is all zero gets none at
 * all, so the capped column reads as flat rather than as weak data.
 */
export function heatFill(value: number, scale: number): string {
  // A value that prints as 0.00%, or a column whose every value does, gets no tint:
  // a cell the reader sees as zero and the page colours as a bet is the page
  // contradicting itself.
  if (scale < FLAT_UNDER || Math.abs(value) < FLAT_UNDER) return "transparent";
  const share = Math.min(1, Math.abs(value) / scale);
  if (share === 0) return "transparent";
  const [r, g, b] = value >= 0 ? POSITIVE : NEGATIVE;
  // The top of the scale stays light: the value is printed in the cell, so the shade
  // has to leave dark text readable at the largest number as well.
  const alpha = 0.07 + share * 0.26;
  return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`;
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
  // Each column is normalised against its own largest value. A shared scale let the
  // 87% momentum row of the before column decide the shade of the now column, which
  // is a wash of one pale colour; a column normalised against itself shows the moves
  // that are actually in it.
  const beforeScale = worstOf(before);
  const afterScale = worstOf(after);
  const nowScale = worstOf(tonightBefore);
  // Present only when the evening recorded one: the key is absent on a document
  // built without a reconciled row, and a missing figure is not a zero figure.
  const adjustment = (snapshot.reconciliation?.unexplained_adjustment as number | null) ?? null;

  return (
    <section
      data-section="exposures"
      data-window="EFB / the hedge"
      className="efb-window rounded border border-slate-200 bg-white p-3"
    >
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
              <th
                className="w-[22%] py-1 pl-1 text-right leading-tight"
                data-column="before"
                data-column-range={percent(beforeScale, 2)}
                title={`this column's own scale runs to ${percent(beforeScale, 2)}`}
              >
                before the hedge
                {anchor ? (
                  <span className="block text-[0.65rem] font-normal text-slate-500">
                    {" "}
                    {anchorClose}
                  </span>
                ) : null}
              </th>
              <th
                className="w-[22%] py-1 pl-1 text-right leading-tight"
                data-column="after"
                data-column-range={percent(afterScale, 2)}
                title={`this column's own scale runs to ${percent(afterScale, 2)}`}
              >
                after the hedge
                {anchor ? (
                  <span className="block text-[0.65rem] font-normal text-slate-500">
                    {" "}
                    {anchorClose}
                  </span>
                ) : null}
              </th>
              {anchor ? (
                <th
                  className="w-[22%] py-1 pl-1 text-right leading-tight"
                  data-column="now"
                  data-column-range={percent(nowScale, 2)}
                  title={`this column's own scale runs to ${percent(nowScale, 2)}`}
                >
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
              const beforeFill = heatFill(before[key] ?? 0, beforeScale);
              const afterFill = heatFill(after[key] ?? 0, afterScale);
              const nowFill = heatFill(tonightBefore[key] ?? 0, nowScale);
              // The guard is a line, not a colour: a cell that crosses it keeps its
              // own shade and gains a ring, so the size and the warning read together.
              const guarded = Math.abs(tonightBefore[key] ?? 0) >= GUARD_BAND;
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
                    data-heat-sign={heatSign(before[key] ?? 0)}
                    style={{ backgroundColor: beforeFill, color: heatInk(beforeFill) }}
                  >
                    {heatText(before[key])}
                  </td>
                  <td
                    className="py-1 text-right font-mono tabular-nums"
                    data-heat="after"
                    data-heat-sign={heatSign(after[key] ?? 0)}
                    style={{ backgroundColor: afterFill, color: heatInk(afterFill) }}
                  >
                    {heatText(after[key])}
                  </td>
                  {anchor ? (
                    <td
                      className="py-1 text-right font-mono tabular-nums"
                      data-now={key}
                      data-heat="now"
                      data-heat-sign={heatSign(tonightBefore[key] ?? 0)}
                      data-guard={guarded ? "true" : undefined}
                      style={{
                        backgroundColor: nowFill,
                        color: heatInk(nowFill),
                        boxShadow: guarded ? "inset 0 0 0 2px #b45309" : undefined,
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
      <p className="mt-1 text-xs text-slate-500" data-heat-caption="true">
        The shade compares a cell only with the other cells in its own column: blue is a
        positive exposure, rose a negative one, zero is left unpainted, and a now cell at
        the 5% guard carries an amber ring. {REFERENCE_SECTOR} is the reference sector and
        has no column of its own, so the ten sectors above are measured against it.
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
