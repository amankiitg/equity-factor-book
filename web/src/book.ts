// Every number the page shows that the snapshot does not state outright.
//
// The snapshot is the run's own document: it carries the book's rows, its gross,
// the traded notional and the breadth. Everything else the page needs is derived
// here, in one pure module, so a section cannot quietly invent its own arithmetic
// and so the derivation can be tested without rendering anything.

import { sectorCodeFor, sectorLabel } from "./sectors";
import type { BookName, Snapshot } from "./types";

export interface SectorBucket {
  /** The GICS code, or null for a name the bundled map does not carry. */
  code: number | null;
  label: string;
  /** Sum of the long weights in dollars, positive. */
  longNotional: number;
  /** Sum of the short weights in dollars, positive. The bar draws it to the left. */
  shortNotional: number;
  /** long less short, signed: the sector's own net exposure. */
  netNotional: number;
  nLong: number;
  nShort: number;
}

export interface ReasonBucket {
  reason: string;
  n: number;
  /** The dollars held in that bucket, signed as the book holds them. */
  notional: number;
  /**
   * The dollars the evening traded in that bucket, absolute and summed.
   *
   * A movement, not a holding: this is what the names under this reason cost the
   * turnover, which is the one thing the held dollars above cannot say. Absolute
   * because it is turnover - a bucket holding a long the run trimmed and a short
   * it opened would otherwise net the two and report less trading than happened.
   * Zero for a bucket the run built no leg for, which is the hedge's own case.
   */
  traded: number;
}

export interface BookFacts {
  /** The book in dollars per unit of weight, or null when the snapshot lacks it. */
  nav: number | null;
  hasBook: boolean;
  nLong: number;
  nShort: number;
  longNotional: number;
  shortNotional: number;
  netNotional: number;
  largest: BookName | null;
  largestNotional: number | null;
  /** The ten largest |weights| as a share of the book's total absolute weight. */
  top10Share: number | null;
  sectors: SectorBucket[];
  reasons: ReasonBucket[];
  topLongs: BookName[];
  topShorts: BookName[];
}

/**
 * The book in dollars per unit of weight.
 *
 * The snapshot states the traded book's gross and the same book's notional, so
 * the per-unit figure is the notional over the gross. It is derived rather than
 * assumed: one run's NAV is not the next run's, and a page that hard-coded the
 * paper account's opening balance would go on being wrong quietly.
 */
export function navOf(snapshot: Snapshot): number | null {
  const gross = snapshot.book?.gross;
  const notional = snapshot.book?.gross_notional;
  if (gross === null || gross === undefined || notional === null || notional === undefined) {
    return null;
  }
  if (!Number.isFinite(gross) || !Number.isFinite(notional) || gross === 0) return null;
  return notional / gross;
}

/** Which side a row is on: the run's own column, or the sign of its weight. */
function sideOf(name: BookName): "long" | "short" {
  if (name.side === "long" || name.side === "short") return name.side;
  return (name.weight ?? 0) < 0 ? "short" : "long";
}

const weightOf = (name: BookName): number => Math.abs(name.weight ?? 0);

export function bookFacts(snapshot: Snapshot): BookFacts {
  const names = snapshot.book?.names ?? [];
  const nav = navOf(snapshot);
  const inDollars = (weight: number): number => (nav === null ? 0 : weight * nav);

  const longs = names.filter((name) => sideOf(name) === "long");
  const shorts = names.filter((name) => sideOf(name) === "short");
  const longGross = longs.reduce((total, name) => total + weightOf(name), 0);
  const shortGross = shorts.reduce((total, name) => total + weightOf(name), 0);
  const grossOfRows = longGross + shortGross;

  const buckets = new Map<string, SectorBucket>();
  for (const name of names) {
    const code = sectorCodeFor(name.ticker);
    const key = code === null ? "unmapped" : String(code);
    const bucket =
      buckets.get(key) ??
      ({
        code,
        label: sectorLabel(code),
        longNotional: 0,
        shortNotional: 0,
        netNotional: 0,
        nLong: 0,
        nShort: 0,
      } satisfies SectorBucket);
    // The bar is drawn from the absolute weights on each side, which is what
    // "long gross to the right, short gross to the left" means: a sector with
    // $400k long and $500k short is not a small sector.
    const dollars = inDollars(weightOf(name));
    if (sideOf(name) === "long") {
      bucket.longNotional += dollars;
      bucket.nLong += 1;
    } else {
      bucket.shortNotional += dollars;
      bucket.nShort += 1;
    }
    bucket.netNotional = bucket.longNotional - bucket.shortNotional;
    buckets.set(key, bucket);
  }
  const sectors = [...buckets.values()].sort((a, b) => {
    if (a.code === null) return 1;
    if (b.code === null) return -1;
    return a.code - b.code;
  });

  const reasonBuckets = new Map<string, ReasonBucket>();
  for (const name of names) {
    const reason = (name.reason ?? "").trim() || "no reason recorded";
    const bucket = reasonBuckets.get(reason) ?? { reason, n: 0, notional: 0, traded: 0 };
    bucket.n += 1;
    bucket.notional += inDollars(weightOf(name));
    // The leg's own notional, already absolute in the snapshot: this is turnover,
    // so the sign of the book's weight is not what it is measured by. A name with
    // no leg is a zero, and a book published without any is a zero for every
    // bucket rather than a missing column, because the section reads one number
    // per reason and both columns are always shown.
    bucket.traded += Math.abs(name.traded_notional ?? 0);
    reasonBuckets.set(reason, bucket);
  }
  const reasons = [...reasonBuckets.values()].sort((a, b) => b.notional - a.notional);

  const largest = names.length
    ? names.reduce((best, name) => (weightOf(name) > weightOf(best) ? name : best), names[0])
    : null;
  const byWeight = [...names].sort((a, b) => weightOf(b) - weightOf(a));
  const top10Weight = byWeight.slice(0, 10).reduce((total, name) => total + weightOf(name), 0);

  return {
    nav,
    hasBook: names.length > 0,
    nLong: longs.length,
    nShort: shorts.length,
    longNotional: inDollars(longGross),
    shortNotional: inDollars(shortGross),
    netNotional: inDollars(longGross - shortGross),
    largest,
    largestNotional: largest === null ? null : inDollars(weightOf(largest)),
    top10Share: grossOfRows > 0 ? top10Weight / grossOfRows : null,
    sectors,
    reasons,
    topLongs: byWeight.filter((name) => sideOf(name) === "long").slice(0, 10),
    topShorts: byWeight.filter((name) => sideOf(name) === "short").slice(0, 10),
  };
}
