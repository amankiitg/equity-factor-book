// The factor exposures, before and after the hedge, as two bars on one scale.
//
// This is the page's one picture of the hedge doing its job, so its rules are the
// load-bearing part: the scale is the largest exposure on the page, which makes the
// rows comparable with each other rather than each filling its own cell, and the
// after column is expected to be flat. A bar that is not there is a factor the hedge
// has taken out, and a reader who cannot see the flatness cannot see the hedge.

import { dollars, exposure, percent } from "./format";
import type { Snapshot } from "./types";

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
          tone === "before" ? "bg-slate-500" : "bg-emerald-600"
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
}: {
  before: number;
  after: number;
  scale: number;
}) {
  return (
    <div className="flex w-28 flex-col gap-[2px]" data-factor-bars="true">
      <ExposureBar value={before} scale={scale} tone="before" />
      <ExposureBar value={after} scale={scale} tone="after" />
    </div>
  );
}

export function ExposuresSection({ snapshot }: { snapshot: Snapshot }) {
  const before = snapshot.exposures_before_hedge ?? {};
  const after = snapshot.exposures_after_hedge ?? {};
  if (Object.keys(before).length === 0 && Object.keys(after).length === 0) return null;
  const rows = exposureRows(before);
  const scale = Math.max(
    ...[...Object.values(before), ...Object.values(after)].map((value) => Math.abs(value ?? 0)),
    0.0001,
  );

  return (
    <section data-section="exposures" className="rounded border border-slate-200 bg-white p-3">
      <h2 className="text-base font-semibold">Factor exposures, before and after the hedge</h2>
      <div className="overflow-x-auto">
        {/* Every column states its own width. The value columns are only as wide as
            their widest number otherwise, so "after" and "before / after" touch and
            read as one label, and the bars column is the width of the bars it holds. */}
        <table className="mt-2 w-full border-collapse text-sm" aria-label="factor exposures">
          <thead>
            <tr className="border-b border-slate-300 text-left">
              <th className="py-1 pr-2">factor</th>
              <th className="w-16 py-1 pr-2 text-right whitespace-nowrap">before</th>
              <th className="w-16 py-1 pr-2 text-right whitespace-nowrap">after</th>
              <th className="w-28 py-1 pl-1 whitespace-nowrap">before / after</th>
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
                  <td className="py-1 pr-2">{label}</td>
                  <td className="w-16 py-1 pr-2 text-right font-mono tabular-nums">
                    {exposure(before[key])}
                  </td>
                  <td className="w-16 py-1 pr-2 text-right font-mono tabular-nums">
                    {exposure(after[key])}
                  </td>
                  <td className="w-28 py-1 pl-1">
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
      </div>
      <p className="mt-1 text-xs text-slate-500">
        The hedge is exact, so every factor's after value is zero to machine precision. The bars are
        on one scale, the largest exposure on the page: a bar that is not there is a factor the
        hedge has taken out. {REFERENCE_SECTOR} is the reference sector and has no column of its
        own, so the ten sectors above are measured against it.
      </p>
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
      </dl>
      <p className="mt-1 text-xs text-slate-500">
        The construction is {snapshot.construction || "n/a"}, and the book is the traded set after
        the floor, renormalized to gross {percent(snapshot.book?.gross)}.
      </p>
    </section>
  );
}
