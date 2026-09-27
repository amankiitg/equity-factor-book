// By sector: one diverging bar per GICS sector, long gross right, short left.
//
// The book is grouped with the bundled map, and a name the map does not carry
// falls into an Unmapped row rather than a guessed sector. The bars share one
// scale, the largest side on the page, so a sector that is twice another's is
// drawn twice as long; a bar per row scaled to its own maximum would make every
// sector look the same size.

import type { SectorBucket } from "./book";
import { dollars, percent, signedDollars } from "./format";

function SectorRow({ bucket, scale }: { bucket: SectorBucket; scale: number }) {
  const longShare = scale > 0 ? bucket.longNotional / scale : 0;
  const shortShare = scale > 0 ? bucket.shortNotional / scale : 0;
  return (
    <div
      className="grid grid-cols-[9rem_1fr] items-center gap-x-3 gap-y-1 border-b border-slate-100 py-1.5 sm:grid-cols-[12rem_1fr_7rem]"
      data-sector={bucket.code === null ? "unmapped" : String(bucket.code)}
    >
      <div className="font-medium">{bucket.label}</div>
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
      {/* Counts and the sector's own net, beside the bar rather than under it:
          on a phone this row wraps, and a label that moves is a label that gets
          misread. */}
      <div className="col-span-2 flex flex-wrap items-baseline gap-x-3 text-xs text-slate-600 sm:col-span-1 sm:block sm:text-right">
        <div data-counts="names">
          {bucket.nLong}L / {bucket.nShort}S
        </div>
        <div data-net="sector" className="font-mono">
          {signedDollars(bucket.netNotional)}
        </div>
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
  const totalLong = sectors.reduce((total, bucket) => total + bucket.longNotional, 0);
  const totalShort = sectors.reduce((total, bucket) => total + bucket.shortNotional, 0);

  return (
    <section data-section="sector">
      <h2 className="text-lg font-semibold">By sector</h2>
      <p className="mt-1 text-sm text-slate-600">
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
      <dl className="mt-2 flex flex-wrap gap-x-6 text-sm text-slate-600">
        <div className="flex gap-2">
          <dt className="font-medium">long gross</dt>
          <dd>{dollars(totalLong)}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="font-medium">short gross</dt>
          <dd>{dollars(totalShort)}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="font-medium">long less short</dt>
          <dd data-net="book">{dollars(totalLong - totalShort)}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="font-medium">short share of gross</dt>
          <dd>{percent(totalShort / (totalLong + totalShort || 1))}</dd>
        </div>
      </dl>
    </section>
  );
}
