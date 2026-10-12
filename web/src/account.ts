// The account against the target, name by name.
//
// The page carries two comparisons and only one of them can be current. The
// evening's is the account against the *store*: the positions the loop last wrote
// down, read before it sent anything, which is a statement about the loop's own
// bookkeeping. The morning's is the account against the *target*: by then the fills
// exist, so the question is whether what the account holds is what the evening asked
// for, and the answer is three lists - the names held and not wanted, the names
// wanted and not held, and the drift on the names both books carry. A page that
// answered the morning question with the evening's comparison was answering it about
// the wrong two books.
//
// The target's weights are turned into dollars with the book's own per-unit NAV, and
// the account's side is the broker's own notionals, which are dollars already. That is
// the one place the two are comparable, and it is the same arithmetic the sector panel
// draws its signed deltas from: a per-name difference that did not add up to the
// sector's would be two numbers pretending to be one.

import { navOf } from "./book";
import type { Snapshot } from "./types";

/** Which side of the target comparison a name is on. */
export type NameKind = "both" | "held" | "targeted";

/** One name, as each side of the comparison has it. */
export interface NameCompare {
  ticker: string;
  /** The account's own dollars, or null when the account does not hold the name. */
  held: number | null;
  /** The target's dollars at the book's own NAV, or null when it does not ask for it. */
  target: number | null;
  /** Held less target, a missing side read as zero: signed, in dollars. */
  delta: number;
  /** `held` is held and not targeted, `targeted` is targeted and not held. */
  kind: NameKind;
}

export interface AccountCompare {
  /** Whether there are two books to compare at all: one side naming nothing is not one. */
  read: boolean;
  readBy: "evening" | "morning" | null;
  /** The per-unit NAV the target's weights are turned into dollars with. */
  nav: number | null;
  /** Every name either side carries, largest absolute difference first. */
  names: NameCompare[];
  /** The account holds it and the target does not. */
  heldNotTargeted: NameCompare[];
  /** The target asks for it and the account does not hold it. */
  targetedNotHeld: NameCompare[];
  /** Both books carry it and they disagree: the drift, largest first. */
  drifts: NameCompare[];
}

const priced = (value: number | null | undefined): value is number =>
  value !== null && value !== undefined && Number.isFinite(value);

/**
 * The account's book against the target's, for whichever read the snapshot carries.
 *
 * Read-agnostic on purpose: the sector panel differences the same two books on an
 * evening read, and only the reconciliation check cares which read it is looking at.
 * A name the read did not price is skipped rather than read as zero - a position with
 * no notional is not a flat position - and a name the target carries at no weight is
 * skipped for the same reason on the other side.
 */
export function compareAccount(snapshot: Snapshot): AccountCompare {
  const nav = navOf(snapshot);

  const held = new Map<string, number>();
  for (const name of snapshot.actual_holdings?.names ?? []) {
    if (!priced(name.notional)) continue;
    held.set(name.ticker, (held.get(name.ticker) ?? 0) + name.notional);
  }

  const target = new Map<string, number>();
  for (const name of snapshot.book?.names ?? []) {
    if (!priced(name.weight) || nav === null) continue;
    target.set(name.ticker, (target.get(name.ticker) ?? 0) + name.weight * nav);
  }

  const names: NameCompare[] = [...new Set([...held.keys(), ...target.keys()])].map((ticker) => {
    const mine = held.has(ticker) ? (held.get(ticker) as number) : null;
    const theirs = target.has(ticker) ? (target.get(ticker) as number) : null;
    return {
      ticker,
      held: mine,
      target: theirs,
      delta: (mine ?? 0) - (theirs ?? 0),
      kind: mine === null ? "targeted" : theirs === null ? "held" : "both",
    };
  });
  names.sort(
    (a, b) => Math.abs(b.delta) - Math.abs(a.delta) || a.ticker.localeCompare(b.ticker),
  );

  return {
    read: held.size > 0 && target.size > 0,
    readBy: snapshot.actual_holdings?.read_by ?? null,
    nav,
    names,
    heldNotTargeted: names.filter((row) => row.kind === "held"),
    targetedNotHeld: names.filter((row) => row.kind === "targeted"),
    drifts: names.filter((row) => row.kind === "both" && row.delta !== 0),
  };
}

/**
 * How a one-sided name is named on the page, or "" for one both books carry.
 *
 * The words are the reader's, not the code's: "held, not targeted" says which book
 * has it and which does not, where "missing" would leave the reader to guess which
 * side the page had found empty.
 */
export function nameKindText(kind: NameKind): string {
  if (kind === "held") return "held, not targeted";
  if (kind === "targeted") return "targeted, not held";
  return "";
}
