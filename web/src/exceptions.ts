// Every mismatch the page can see, sorted into the ones the loop already knows
// about and the ones it does not.
//
// The morning question is "must I act today", and a list of six names where four
// are the loop's own deferred reversals answers it badly: the reader learns to
// skim the list, which is how a page teaches someone to miss the one that mattered.
// So each mismatch is classified, and only the unexplained ones are drawn as
// exceptions.
//
// Every class here is a *fact stated in the document*, named with the key that
// states it, and nothing is inferred from a name merely looking familiar. Where the
// document does not carry the fact - and for two of the three classes the brief
// asks for, it does not - the class is listed as unverifiable with the key that
// would carry it, rather than guessed at. A page that classified a name as
// "expected" on a hunch would be worse than one that shows it amber and says why.

import type { Snapshot } from "./types";

/** Which side of the account-versus-store comparison a name is on. */
export type MismatchSide = "at_broker" | "in_store";

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
  /** Whether the comparison ran at all: a read that named no names is not a pass. */
  read: boolean;
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
          : "the account holds it and the store does not, and nothing in the document explains it",
      key: "",
    };
  };

  const all = [
    ...(positions?.missing_at_broker ?? []).map((t) => classifyOne(t, "at_broker")),
    ...(positions?.missing_in_store ?? []).map((t) => classifyOne(t, "in_store")),
  ];

  return {
    expected: all.filter((entry) => entry.key !== ""),
    unexpected: all.filter((entry) => entry.key === ""),
    unchecked: UNCHECKED,
    // A read that answered with no names at all is a read that found nothing, which
    // is not the same as a comparison nobody ran: `matches === null` is the latter.
    read: positions !== undefined && positions !== null && positions.matches !== null,
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
  if (!report.read) return "account not compared with the store";
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
