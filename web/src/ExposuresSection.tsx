// The factor exposures, before and after the hedge, as two bars on one scale.
//
// This is the page's one picture of the hedge doing its job, so its rules are the
// load-bearing part: the scale is the largest exposure on the page, which makes the
// rows comparable with each other rather than each filling its own cell, and the
// after column is expected to be flat. A bar that is not there is a factor the hedge
// has taken out, and a reader who cannot see the flatness cannot see the hedge.

import { Details } from "./Details";
import { HowToRead } from "./Panel";
import { count, dateOnly, dollars, exposure, percent } from "./format";
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

function ExposureBar({ value, scale, tone }: { value: number; scale: number; tone: string }) {
  const share = Math.max(0, Math.min(1, Math.abs(value) / (scale || 1)));
  const style: Record<string, string> =
    value >= 0
      ? { left: "50%", width: `${share * 50}%` }
      : { right: "50%", width: `${share * 50}%` };
  return (
    <div className="relative h-[6px] w-full rounded-sm bg-slate-100">
      <span className="absolute left-1/2 top-0 h-full w-px bg-slate-300" />
      <span
        data-bar={tone}
        data-sign={value >= 0 ? "positive" : "negative"}
        title={`${tone} ${exposure(value)}`}
        className={`absolute top-0 h-full rounded-sm ${
          tone === "before" ? "bg-slate-500" : tone === "now" ? "bg-amber-600" : "bg-emerald-600"
        }`}
        style={style}
      />
    </div>
  );
}

function ExposureBars({
  before,
  after,
  scale,
  now,
}: {
  before: number;
  after: number;
  scale: number;
  now?: number | null;
}) {
  return (
    <div className="flex w-full flex-col gap-[2px]" data-factor-bars="true">
      <ExposureBar value={before} scale={scale} tone="before" />
      <ExposureBar value={after} scale={scale} tone="after" />
      {now === undefined ? null : <ExposureBar value={now ?? 0} scale={scale} tone="now" />}
    </div>
  );
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
      <h2 className="text-base font-semibold">The hedge</h2>
      <HowToRead>
        each bar is one factor exposure as a share of NAV. Zero means the book has
        no tilt to that factor.
      </HowToRead>
      {anchor ? (
        <>
          <p className="mt-1 text-sm" data-hedge-verdict="true" data-hedge-anchor={anchorClose}>
            worst residual factor exposure after the {anchorClose} hedge:{" "}
            <span className="font-mono tabular-nums">
              {exposure(anchor.after && worstOf(anchor.after))}
            </span>{" "}
            of a unit exposure, and that close hedged, so every factor&apos;s after value{" "}
            <em>there</em> is zero to machine precision. Nothing was hedged tonight, so the
            &quot;now&quot; column is the book as it stands, not a hedge&apos;s output.
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
          worst residual factor exposure after the hedge:{" "}
          <span className="font-mono tabular-nums">
            {exposure(snapshot.hedge?.max_abs_exposure_after_fmp)}
          </span>{" "}
          of a unit exposure, and the hedge is exact, so every factor&apos;s after value is zero to
          machine precision, and the eighteen rows behind the disclosure below are the audit of
          that rather than a reading in themselves.
        </p>
      )}
      <Details
        hook="exposures"
        summary={<>every factor, before and after the hedge, {rows.length} row(s)</>}
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
        >
          <thead>
            <tr className="border-b border-slate-300 text-left">
              <th className={anchor ? "w-[28%] py-1 pr-1" : "w-[36%] py-1 pr-1"}>factor</th>
              <th className="w-[15%] py-1 text-right" data-column="before">
                {anchor ? `before the hedge (${anchorClose})` : "before"}
              </th>
              <th className="w-[15%] py-1 text-right" data-column="after">
                {anchor ? `after the hedge (${anchorClose})` : "after"}
              </th>
              {anchor ? (
                <th className="w-[15%] py-1 text-right" data-column="now">
                  now ({dateOnly(snapshot.target_close) ?? "tonight"})
                </th>
              ) : null}
              <th className={anchor ? "w-[27%] py-1 pl-1" : "w-[34%] py-1 pl-1"}>
                {anchor ? "before / after / now" : "before / after"}
              </th>
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
                  <td className="py-1 text-right font-mono tabular-nums">
                    {exposure(before[key])}
                  </td>
                  <td className="py-1 text-right font-mono tabular-nums">
                    {exposure(after[key])}
                  </td>
                  {anchor ? (
                    <td
                      className="py-1 text-right font-mono tabular-nums"
                      data-now={key}
                    >
                      {exposure(tonightBefore[key])}
                    </td>
                  ) : null}
                  <td className="py-1 pl-1">
                    <ExposureBars
                      before={before[key] ?? 0}
                      after={after[key] ?? 0}
                      scale={scale}
                      now={anchor ? (tonightBefore[key] ?? 0) : undefined}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        The bars are on one scale, the largest exposure on the page: a bar that is not there is a
        factor the hedge has taken out. {REFERENCE_SECTOR} is the reference sector and has no
        column of its own, so the ten sectors above are measured against it.
      </p>
      </Details>
      <dl className="mt-2 flex flex-wrap gap-x-6 text-sm text-slate-600">
        <div className="flex gap-2">
          <dt className="font-medium">the hedge</dt>
          <dd>
            <span className="text-slate-500">idio share after FMP</span>{" "}
            <span className="font-mono tabular-nums">
              {exposure(snapshot.hedge?.idio_share_after_fmp)}
            </span>
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="font-medium">worst residual exposure</dt>
          <dd className="font-mono tabular-nums">
            {exposure(snapshot.hedge?.max_abs_exposure_after_fmp)}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="font-medium">post-hedge idio share</dt>
          <dd className="font-mono tabular-nums">
            {exposure(snapshot.hedge?.post_hedge_idio_share)}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="font-medium">reconciliation intended</dt>
          <dd className="font-mono tabular-nums">
            {dollars(snapshot.reconciliation?.intended_notional as number | null)}
          </dd>
        </div>
        {adjustment ? (
          // The day's P&L is the account's own equity move, and this is the part of
          // it that no order of the loop's explains: a position that left with
          // nothing behind it. It is labelled rather than netted out of the P&L,
          // because a number quietly adjusted is one nobody can check, and the
          // figure is the account's paper keeping rather than a result of the book.
          <div className="flex gap-2" data-figure="unexplained-adjustment">
            <dt className="font-medium">unexplained adjustment</dt>
            <dd className="font-mono tabular-nums">
              {dollars(adjustment)}{" "}
              <span className="text-slate-500">
                (left the account with no order behind it)
              </span>
            </dd>
          </div>
        ) : null}
      </dl>
      <p className="mt-1 text-xs text-slate-500">
        The construction is {snapshot.construction || "n/a"}, and the book is the traded set after
        the floor, renormalized to gross {percent(snapshot.book?.gross)}.
      </p>
    </section>
  );
}
