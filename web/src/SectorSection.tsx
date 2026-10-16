// By sector: what the account holds against what the target asks for.
//
// The old panel led with long gross to the right and short gross to the left, which is
// a true picture of a book that is neutral by construction and therefore says almost
// nothing: every sector's two bars sit within a fraction of a percent of each other
// because that is the design, so the chart is eleven rows of the same shape. The
// question a reader actually has is *where is the account away from its target*, and
// that is a signed dollar difference per sector.
//
// So the delta leads: account net minus target net, in dollars, sorted by absolute
// size, with the sign kept and the sector's own long/short gross behind a disclosure
// where it is still available to anyone checking the shape. The account side is the
// read the strip names, and on an evening snapshot that read is taken before the orders
// go out - so the deltas describe the book the account held going into the session, not
// the outcome of the orders the page is showing. On a morning read they are the outcome:
// the fills exist, so the difference is what they left behind.
//
// A sector's dollar difference names its own drivers, because a total the reader cannot
// decompose is a number they have to take on trust: eleven sectors of a few hundred
// dollars and one of -$7,598 is a different morning depending on whether that one is
// 900 names slightly out or one name that should not be held at all. The driver line
// says which, in the dollars and with the class the account-versus-target comparison
// put on it.
//
// A sector the bundled map does not carry is its own row rather than a guessed one, and
// the panel says how many names it could not place: an unmapped name is still a
// position, and a delta computed without it would be a delta of the book the page can
// see rather than of the book.

import { compareAccount, nameKindText, type NameCompare } from "./account";
import { Details } from "./Details";
import { count, dollars, percent, signedDollars } from "./format";
import { UNMAPPED, sectorCodeFor, sectorLabel } from "./sectors";
import type { BookFacts, SectorBucket } from "./book";
import type { Snapshot } from "./types";

/** How many driver names a sector row prints before the rest are left to the drawer. */
const DRIVERS = 3;

/** A driver below a dollar is rounding, not a contribution. */
const DRIVER_FLOOR = 1;

/** One sector's account-against-target difference, in dollars and names. */
interface SectorDelta {
  code: number | null;
  label: string;
  /** Account net minus target net, signed: what the account has that the target does not. */
  delta: number;
  targetNet: number;
  accountNet: number;
  /** Names held, wanted, and the two sets' difference in count. */
  accountNames: number;
  targetNames: number;
  /** The names contributing most to the delta, largest absolute first. */
  drivers: NameCompare[];
  /** The sector's gross on each side, from the target, for the detail disclosure. */
  bucket: SectorBucket;
}

/**
 * The sectors' account-to-target differences.
 *
 * The target side is turned into dollars with the book's own per-unit NAV, and the
 * account side is the broker's own notionals, which are dollars already. That is the
 * one place the two are comparable: the target's weights are fractions of the NAV the
 * evening sized from, and the account's weights are fractions of its own equity, which
 * is the same number to within the day's P&L.
 */
export function sectorDeltas(snapshot: Snapshot, sectors: SectorBucket[]): SectorDelta[] {
  const target = new Map<string, SectorBucket>();
  for (const bucket of sectors) {
    target.set(bucket.code === null ? UNMAPPED : String(bucket.code), bucket);
  }

  const account = new Map<string, { net: number; names: number }>();
  for (const name of snapshot.actual_holdings?.names ?? []) {
    if (name.notional === null || name.notional === undefined) continue;
    const code = sectorCodeFor(name.ticker);
    const key = code === null ? UNMAPPED : String(code);
    const entry = account.get(key) ?? { net: 0, names: 0 };
    // A row the read did not price is skipped rather than read as zero: a position
    // with no notional is not a flat position.
    entry.net += name.notional;
    entry.names += 1;
    account.set(key, entry);
  }

  // The per-name differences the sector totals are the sum of, so a driver line
  // cannot disagree with the delta above it: the comparison is the same one the
  // reconciliation and the drift list are made from.
  const byName = compareAccount(snapshot);
  const drivers = new Map<string, NameCompare[]>();
  for (const row of byName.names) {
    if (Math.abs(row.delta) < DRIVER_FLOOR) continue;
    const code = sectorCodeFor(row.ticker);
    const key = code === null ? UNMAPPED : String(code);
    const list = drivers.get(key) ?? [];
    if (list.length < DRIVERS) list.push(row);
    drivers.set(key, list);
  }

  const keys = new Set([...target.keys(), ...account.keys()]);
  const out: SectorDelta[] = [];
  for (const key of keys) {
    const bucket = target.get(key) ?? null;
    const held = account.get(key) ?? { net: 0, names: 0 };
    // A sector the account holds and the target does not is still a sector with a
    // name and a code: reading the key as an unmapped name would file nine hundred
    // shares of a real sector under "Unmapped" and leave the largest difference on
    // the page labelled "50".
    const code = bucket?.code ?? (key === UNMAPPED ? null : Number(key));
    const label = bucket?.label ?? sectorLabel(code);
    out.push({
      code,
      label,
      delta: held.net - (bucket?.netNotional ?? 0),
      targetNet: bucket?.netNotional ?? 0,
      accountNet: held.net,
      accountNames: held.names,
      targetNames: bucket === null ? 0 : bucket.nLong + bucket.nShort,
      drivers: drivers.get(key) ?? [],
      bucket:
        bucket ??
        ({
          code,
          label,
          longNotional: 0,
          shortNotional: 0,
          netNotional: 0,
          nLong: 0,
          nShort: 0,
        } satisfies SectorBucket),
    });
  }
  return out.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
}

/** One driver name's contribution, in the dollars and the class the comparison put on it. */
function driverText(row: NameCompare): string {
  const kind = nameKindText(row.kind);
  return `${row.ticker} ${signedDollars(row.delta)}${kind === "" ? "" : ` (${kind})`}`;
}

function DeltaRow({ row, scale }: { row: SectorDelta; scale: number }) {
  const share = scale > 0 ? Math.min(1, Math.abs(row.delta) / scale) : 0;
  const over = row.delta >= 0;
  return (
    <div
      data-sector={row.code === null ? "unmapped" : String(row.code)}
      data-delta={row.delta.toFixed(2)}
      className="border-b border-slate-100"
    >
      <div className="grid grid-cols-[7rem_1fr_6rem] items-center gap-x-2 py-1">
        <div className="truncate text-sm font-medium" title={row.label}>
          {row.label}
        </div>
        <div className="relative h-3 w-full rounded-sm bg-slate-100">
          <span className="absolute left-1/2 top-0 h-full w-px bg-slate-300" />
          <span
            data-side={over ? "over" : "under"}
            title={`account ${signedDollars(row.accountNet)} against target ${signedDollars(
              row.targetNet,
            )}`}
            className={`absolute top-0 h-full rounded-sm ${over ? "bg-sky-600" : "bg-violet-500"}`}
            style={
              over
                ? { left: "50%", width: `${share * 50}%` }
                : { right: "50%", width: `${share * 50}%` }
            }
          />
        </div>
        <div className="text-right font-mono text-xs tabular-nums">{signedDollars(row.delta)}</div>
      </div>
      {row.drivers.length > 0 ? (
        <p
          data-drivers={row.code === null ? "unmapped" : String(row.code)}
          className="pb-1 text-xs text-slate-500"
        >
          of which {row.drivers.map(driverText).join(", ")}
        </p>
      ) : null}
    </div>
  );
}

export function SectorSection({
  snapshot,
  sectors,
  facts: _facts,
}: {
  snapshot: Snapshot;
  sectors: SectorBucket[];
  facts?: BookFacts;
}) {
  const read = snapshot.actual_holdings ?? null;
  if (sectors.length === 0) return null;
  if (!read) {
    // With no account read there is no difference to draw, and drawing the target
    // against nothing would render every sector as a full-size short. The target's own
    // signed net is still a reading - it says where the book is tilted before the
    // hedge is applied to the book as a whole - so the panel falls back to it and says
    // which of the two views it is showing. That is a narrower view than the delta, and
    // a reader can see it is narrower rather than wondering where the account went.
    const scale = Math.max(...sectors.map((bucket) => Math.abs(bucket.netNotional)), 1);
    return (
      <section data-section="sector" className="rounded border border-slate-200 bg-white p-3">
        <h2 className="text-base font-semibold">By sector</h2>
        <p data-sector-deltas="no-account" className="mt-1 text-xs text-slate-600">
          the account has not been read for this close, so there is no account-against-target
          difference. The target&apos;s own signed net is shown instead: it is a narrower
          reading, and not the one the panel exists for.
        </p>
        <div className="mt-2" data-sector-net="true">
          {[...sectors]
            .sort((a, b) => Math.abs(b.netNotional) - Math.abs(a.netNotional))
            .map((bucket) => (
              <div
                key={bucket.code === null ? "unmapped" : String(bucket.code)}
                data-sector={bucket.code === null ? "unmapped" : String(bucket.code)}
                className="grid grid-cols-[7rem_1fr_6rem] items-center gap-x-2 border-b border-slate-100 py-1"
              >
                <div className="truncate text-sm font-medium" title={bucket.label}>
                  {bucket.label}
                </div>
                <div className="relative h-3 w-full rounded-sm bg-slate-100">
                  <span className="absolute left-1/2 top-0 h-full w-px bg-slate-300" />
                  <span
                    data-side={bucket.netNotional >= 0 ? "over" : "under"}
                    className={`absolute top-0 h-full rounded-sm ${
                      bucket.netNotional >= 0 ? "bg-sky-600" : "bg-violet-500"
                    }`}
                    style={
                      bucket.netNotional >= 0
                        ? {
                            left: "50%",
                            width: `${(Math.abs(bucket.netNotional) / scale) * 50}%`,
                          }
                        : {
                            right: "50%",
                            width: `${(Math.abs(bucket.netNotional) / scale) * 50}%`,
                          }
                    }
                  />
                </div>
                <div className="text-right font-mono text-xs tabular-nums">
                  {signedDollars(bucket.netNotional)}
                </div>
              </div>
            ))}
        </div>
      </section>
    );
  }

  const rows = sectorDeltas(snapshot, sectors);
  const scale = Math.max(...rows.map((row) => Math.abs(row.delta)), 1);
  const worst = rows[0];
  const unmapped = rows.filter((row) => row.code === null);
  const nav = snapshot.book?.gross_notional ?? null;
  const morning = read.read_by === "morning";
  // Which name carries the largest sector: the answer to "is this spread across the
  // book or is it one position", which the total on its own cannot give.
  const worstDriver = worst?.drivers[0] ?? null;

  return (
    <section data-section="sector" className="rounded border border-slate-200 bg-white p-3">
      <h2 className="text-base font-semibold">By sector: account against target</h2>
      <p className="mt-1 text-xs text-slate-600">
        Signed dollars, sorted by size: blue where the account holds more net than the target
        asks for, violet where it holds less. The two books are turned into dollars with the
        same NAV
        {nav === null ? "" : ` (${dollars(nav)})`}, and the account side is the read the strip
        names
        {morning
          ? " — this morning's, after the fills, so the difference is what the orders left behind."
          : ", which the evening took before the orders went out."}
      </p>
      {worst ? (
        <p data-sector-largest="true" className="mt-1 text-sm">
          largest difference: <span className="font-medium">{worst.label}</span>{" "}
          <span className="font-mono tabular-nums">{signedDollars(worst.delta)}</span>
          {worstDriver ? <>, of which {driverText(worstDriver)}</> : null}
          {nav === null ? "" : ` (${percent(worst.delta / nav)} of NAV)`}
        </p>
      ) : null}
      <div className="mt-2" data-sector-deltas="true">
        {rows.map((row) => (
          <DeltaRow
            key={row.code === null ? "unmapped" : String(row.code)}
            row={row}
            scale={scale}
          />
        ))}
      </div>

      <Details
        hook="sector-gross"
        summary={<>the target&apos;s long and short gross by sector — {count(rows.length)} sector(s)</>}
      >
        <p className="text-xs text-slate-500">
          The book is neutral by construction, so each sector&apos;s long and short gross sit
          within a fraction of a percent of each other and the bars are all the same shape. It
          is here for the reader checking the shape, not as the decision view.
        </p>
        {/* Six columns on a phone, so the layout is fixed and the labels are short:
            the units are in the heading above rather than in every header, and the
            table is exactly the width of its box rather than wider than it. */}
        <table
          aria-label="sector gross"
          className="mt-1 w-full table-fixed border-collapse text-[0.65rem]"
        >
          <thead>
            <tr className="text-left text-slate-500">
              <th className="w-[26%] py-1 pr-1">sector</th>
              <th className="w-[15%] py-1 pr-1 text-right">long</th>
              <th className="w-[15%] py-1 pr-1 text-right">short</th>
              <th className="w-[15%] py-1 pr-1 text-right">target</th>
              <th className="w-[15%] py-1 pr-1 text-right">account</th>
              <th className="w-[14%] py-1 text-right">names</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`gross-${row.code ?? "unmapped"}`}>
                <td className="break-words py-1 pr-1">{row.label}</td>
                <td className="py-1 pr-1 text-right tabular-nums">
                  {dollars(row.bucket.longNotional)}
                </td>
                <td className="py-1 pr-1 text-right tabular-nums">
                  {dollars(row.bucket.shortNotional)}
                </td>
                <td className="py-1 pr-1 text-right tabular-nums">
                  {signedDollars(row.targetNet)}
                </td>
                <td className="py-1 pr-1 text-right tabular-nums">
                  {signedDollars(row.accountNet)}
                </td>
                <td className="py-1 text-right tabular-nums">
                  {row.targetNames} / {row.accountNames}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Details>

      {unmapped.length > 0 ? (
        <p className="mt-1 text-xs text-slate-500">
          {unmapped.reduce(
            (total, row) => total + row.accountNames + row.targetNames,
            0,
          )}{" "}
          name(s) in {unmapped.length} row(s) the bundled map does not carry: they are drawn
          rather than dropped, because an unmapped name is still a position.
        </p>
      ) : null}
    </section>
  );
}
