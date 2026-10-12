// Every mismatch the page can see, sorted into the ones the loop already knows
// about and the ones it does not.
//
// The morning question is "must I act today", and a list of six names where four
// are the loop's own deferred reversals answers it badly: the reader learns to
// skim the list, which is how a page teaches someone to miss the one that mattered.
// So each mismatch is classified, and only the unexplained ones are drawn as
// exceptions.
//
// The mismatches themselves follow the read. An evening snapshot holds the account
// as it was *before* the orders went out, so the only comparison it supports is the
// account against the positions the loop had written down. A morning snapshot holds
// the account *after* the fills, so it supports the one that matters then: the
// account against the target the orders were built from. The store comparison is not
// deleted on a morning read - it is a fact about the loop's own record - but it is
// kept as the evening's, never as the current answer.
//
// Every class here is a *fact stated in the document*, named with the key that
// states it, and nothing is inferred from a name merely looking familiar. Where the
// document does not carry the fact - and for two of the three classes the brief
// asks for, it does not - the class is listed as unverifiable with the key that
// would carry it, rather than guessed at. A page that classified a name as
// "expected" on a hunch would be worse than one that shows it amber and says why.

import { compareAccount, type AccountCompare } from "./account";
import type { Snapshot } from "./types";

/** Which comparison a mismatch came out of, and on which side. */
export type MismatchSide =
  | "at_broker"
  | "in_store"
  | "held_not_targeted"
  | "targeted_not_held";

export interface Mismatch {
  ticker: string;
  side: MismatchSide;
  /** The class it was put in, in words the panel prints. */
  why: string;
  /** The snapshot key that decided it. Empty when nothing did. */
  key: string;
}

export interface Unchecked {
  /** The class the brief asks about, in words. */
  what: string;
  /** What the document would have to carry for the page to check it. */
  needs: string;
}

export interface Exceptions {
  expected: Mismatch[];
  unexpected: Mismatch[];
  unchecked: Unchecked[];
  /** Whether the current comparison ran at all: a read that named no names is not a pass. */
  read: boolean;
  /**
   * Which comparison the two lists above came out of.
   *
   * `target` is the morning read's own comparison - the account against the book the
   * orders were built from - `store` is the evening's account against the stored
   * positions, and `none` is a document with neither.
   */
  source: "target" | "store" | "none";
  /** The account-against-target comparison itself, when that is the current one. */
  compare: AccountCompare | null;
  /** The evening's account-against-store mismatches, kept but never shown as current. */
  evening: Mismatch[] | null;
}

/**
 * The classes the document cannot decide, in the words the panel uses for them.
 *
 * Each one names the key that would settle it, so the reader can tell a page that
 * found nothing from a page that could not look. `bridge.under_minimum` is a count
 * of the legs the $250 floor left untraded and `bridge.under_minimum_usd` is the
 * floor itself; neither carries a ticker. The corporate-action class has no key at
 * all: whether an asset is inactive is the broker's own answer, and the loop keeps
 * its own record of the events in `efb.e11_corporate_actions`, which is not
 * published in this document.
 */
const UNCHECKED: Unchecked[] = [
  {
    what: "legs under the $250 minimum",
    needs:
      "a ticker list beside bridge.under_minimum, which carries the count (and " +
      "bridge.under_minimum_usd, the floor) but no names",
  },
  {
    // The class the brief expected to be decidable, and the reason it is not: the
    // lists are one session apart. `bridge.reversals_pending` names what *this*
    // morning closed, which is absent from *tomorrow's* read; the names missing from
    // the account tonight were closed by the previous close's morning, whose list
    // travelled in that close's own document. On 2026-10-09, four names are in this
    // position - BEN, F, VZ, ZTS, all four exactly the deferred reversals of the
    // previous close - and no key in the 2026-10-09 document names them.
    what: "a name the account does not hold because a previous close's morning closed it as a deferred reversal",
    needs:
      "the previous close's bridge.reversals_pending, beside this one: this " +
      "document's list names the deferrals made today, which are the gap in " +
      "tomorrow's read, and the page fetches latest.json only",
  },
  {
    what: "an asset that went inactive or was taken out by a corporate action",
    needs:
      "an asset-status or corporate-action field; the loop records the events in " +
      "efb.e11_corporate_actions, which the snapshot does not publish",
  },
];

/**
 * The mismatches, split into the explained and the unexplained.
 *
 * The two classes that can be decided page-only, and the one key each rests on:
 *
 * - **deferred reversals**, `bridge.reversals_pending`: the names the evening closed
 *   tonight so the other side can open tomorrow. On 2026-10-08 that list is exactly
 *   BEN, F, VZ and ZTS, which is also that morning's four missing-at-broker names -
 *   the loop closed them, so the account not holding them is the intended state;
 * - **a position removed with no order**, `bridge.removed_without_order`: a name
 *   that left the account and which the bridge has already itemised as explained by
 *   the record it keeps.
 *
 * Everything else is unexplained until someone looks. That is deliberately the
 * hard direction: a page that filed a real break under "expected" is a page that
 * hid the thing it exists to show.
 *
 * Which names are compared at all is the read's business, and the classes above are
 * the same either way: the document states them, not the direction of the
 * comparison. On 2026-10-12 the morning read holds WBD short and the target does not
 * ask for it - a name nothing in the document explains - and the target asks for INVH
 * while the account does not hold it, which is that document's own
 * `bridge.reversals_pending`.
 */
export function classify(snapshot: Snapshot): Exceptions {
  const positions = snapshot.positions;
  const bridge = snapshot.bridge;
  const reversals = new Set(bridge?.reversals_pending ?? []);
  const removals = new Set(
    (bridge?.removed_without_order ?? []).map((entry) => entry.ticker),
  );

  const classifyOne = (ticker: string, side: MismatchSide): Mismatch => {
    if (reversals.has(ticker)) {
      return {
        ticker,
        side,
        why: "deferred reversal: closed tonight, reopening tomorrow",
        key: "bridge.reversals_pending",
      };
    }
    if (removals.has(ticker)) {
      return {
        ticker,
        side,
        why: "left the account with no order, already itemised by the bridge",
        key: "bridge.removed_without_order",
      };
    }
    return {
      ticker,
      side,
      why:
        side === "at_broker"
          ? "the store holds it and the account does not, and nothing in this document explains it"
          : side === "in_store"
            ? "the account holds it and the store does not, and nothing in the document explains it"
            : side === "held_not_targeted"
              ? "the account holds it and the target does not, and nothing in this document explains it"
              : "the target asks for it and the account does not hold it, and nothing in this document explains it",
      key: "",
    };
  };

  // The evening's own comparison, always built when the document carries one: on a
  // morning read it is the collapsed line beside the current check, and on an
  // evening read it is the current check itself.
  const store = [
    ...(positions?.missing_at_broker ?? []).map((t) => classifyOne(t, "at_broker")),
    ...(positions?.missing_in_store ?? []).map((t) => classifyOne(t, "in_store")),
  ];
  const storeRead = positions !== undefined && positions !== null && positions.matches !== null;

  const compare = compareAccount(snapshot);
  const targetRead = snapshot.actual_holdings?.read_by === "morning";
  const target = targetRead
    ? [
        ...compare.heldNotTargeted.map((row) => classifyOne(row.ticker, "held_not_targeted")),
        ...compare.targetedNotHeld.map((row) => classifyOne(row.ticker, "targeted_not_held")),
      ]
    : [];

  const current = targetRead ? target : store;
  return {
    expected: current.filter((entry) => entry.key !== ""),
    unexpected: current.filter((entry) => entry.key === ""),
    unchecked: UNCHECKED,
    read: targetRead ? compare.read : storeRead,
    source: targetRead ? "target" : storeRead ? "store" : "none",
    compare: targetRead ? compare : null,
    evening: targetRead ? store : null,
  };
}

/**
 * The one line an exception count is read from, on both tabs.
 *
 * "4 expected" and "2 unexpected" are two different sentences, so the count is
 * stated as both rather than summed: a total that moved because four benign names
 * appeared would tell the reader nothing about whether anything is wrong.
 */
export function exceptionText(report: Exceptions): string {
  if (!report.read) {
    // Which comparison did not run is worth the words: on a morning read the store
    // is the evening's comparison and its silence is not the day's answer.
    return report.source === "target"
      ? "the account has not been compared with the target"
      : "account not compared with the store";
  }
  const unexpected = report.unexpected.length;
  const expected = report.expected.length;
  // Two counts, two statements, and no trailing noun when both are present: "2
  // unexpected, 1 expected" is a sentence, and "2 unexpected, 1 expected
  // mismatches" is not - the noun would have to agree with two numbers at once.
  if (unexpected > 0 && expected > 0) return `${unexpected} unexpected, ${expected} expected`;
  if (unexpected > 0) return `${unexpected} unexpected mismatch${unexpected === 1 ? "" : "es"}`;
  if (expected > 0) return `${expected} expected mismatch${expected === 1 ? "" : "es"}`;
  return "no mismatch";
}

/** Whether anything on the page needs a person today. */
export function hasUnexpected(report: Exceptions): boolean {
  return report.unexpected.length > 0;
}
