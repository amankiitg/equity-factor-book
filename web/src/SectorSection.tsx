// By sector: one diverging bar per GICS sector, long gross right, short left.
//
// The book is grouped with the bundled map, and a name the map does not carry falls
// into an Unmapped row rather than a guessed sector. The bars share one scale, the
// largest side on the page, so a sector that is twice another's is drawn twice as
// long; a bar per row scaled to its own maximum would make every sector look the
// same size.
//
// The long and short gross totals used to sit under the last row. They are on the
// metrics row now, once, with the same two numbers: the footer repeated the row above
// it, and a summary repeated in two places is a summary nobody knows which of the two
// to believe.

import type { SectorBucket } from "./book";
import { dollars, signedDollars } from "./format";

function SectorRow({ bucket, scale }: { bucket: SectorBucket; scale: number }) {
  const longShare = scale > 0 ? bucket.longNotional / scale : 0;
  const shortShare = scale > 0 ? bucket.shortNotional / scale : 0;
  return (
    <div
      className="grid grid-cols-[8rem_1fr] items-center gap-x-3 gap-y-1 border-b border-slate-100 py-1"
      data-sector={bucket.code === null ? "unmapped" : String(bucket.code)}
    >
      <div className="truncate text-sm font-medium" title={bucket.label}>
        {bucket.label}
      </div>
      <div className="relative h-3 w-full rounded-sm bg-slate-100">
        {/* The zero line, at the middle, so a negative bar is visibly negative. */}
        <span className="absolute left-1/2 top-0 h-full w-px bg-slate-300" />
        <span
          data-side="short"
          title={`short gross ${dollars(bucket.shortNotional)}`}
          className="absolute top-0 h-full rounded-sm bg-rose-500"
          style={{ right: "50%", width: `${Math.min(50, shortShare * 50)}%` }}
        />
        <span
          data-side="long"
          title={`long gross ${dollars(bucket.longNotional)}`}
          className="absolute top-0 h-full rounded-sm bg-emerald-600"
          style={{ left: "50%", width: `${Math.min(50, longShare * 50)}%` }}
        />
      </div>
      <div className="col-span-2 flex flex-wrap items-baseline gap-x-3 text-xs text-slate-600">
        <span data-counts="names">
          {bucket.nLong}L / {bucket.nShort}S
        </span>
        <span data-net="sector" className="font-mono tabular-nums">
          {signedDollars(bucket.netNotional)}
        </span>
      </div>
    </div>
  );
}

export function SectorSection({ sectors }: { sectors: SectorBucket[] }) {
  if (sectors.length === 0) return null;
  const scale = Math.max(
    ...sectors.map((bucket) => Math.max(bucket.longNotional, bucket.shortNotional)),
    1,
  );

  return (
    <section data-section="sector" className="rounded border border-slate-200 bg-white p-3">
      <h2 className="text-base font-semibold">By sector</h2>
      <p className="mt-1 text-xs text-slate-600">
        Long gross to the right, short gross to the left, one scale across the rows. Net is the
        sector's own. Name counts are the long and short counts in that sector.
      </p>
      <div className="mt-2" data-sector-bars="true">
        {sectors.map((bucket) => (
          <SectorRow
            key={bucket.code === null ? "unmapped" : bucket.code}
            bucket={bucket}
            scale={scale}
          />
        ))}
      </div>
      <p className="mt-1 text-xs text-slate-500">
        The sector with no code is the one the bundled map does not carry, and it is drawn rather
        than dropped: an unmapped name is still a position.
      </p>
    </section>
  );
}
