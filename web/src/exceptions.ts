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

/**
 * The four plain labels a mismatched name can wear on the page.
 *
 * The reader's question is "must I do something", and the answer is one of four:
 * it is still settling (`in transit`), nothing can be done about it (`stuck`), the
 * run itself decided it (`too small`), or nobody knows (`look`). The words are the
 * same for every name in the class, so a reader learns them once.
 */
export type Label = "in transit" | "stuck" | "too small" | "look at this";

/** What happens next, in one short sentence, per label. */
export const NEXT_STEP: Record<Label, string> = {
  "in transit": "it reopens on the next night, nothing to do",
  stuck: "the broker settles it, nothing to do",
  "too small": "the leg was under the floor, so it opens on a later night",
  "look at this": "look at this one today",
};

export interface Mismatch {
  ticker: string;
  side: MismatchSide;
  /** The class it was put in, in words the panel prints. */
  why: string;
  /** The snapshot key that decided it. Empty when nothing did. */
  key: string;
  /** The plain label, and what happens next. */
  label: Label;
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
 * found nothing from a page that could not look. The corporate-action class has no
 * key at all: whether an asset is inactive is the broker's own answer, and the loop
 * keeps its own record of the events in `efb.e11_corporate_actions`, which is not
 * published in this document.
 */
const UNCHECKED: Unchecked[] = [
  {
    what: "a leg too small to trade",
    needs: "a ticker list beside bridge.under_minimum",
  },
  {
    what: "an asset the broker says is inactive",
    needs: "an asset-status or corporate-action field",
  },
];

/**
 * The one class whose key can be present and still undecided.
 *
 * `bridge.previous_reversals_pending` is this page's own fix for the class that
 * used to sit in `UNCHECKED`: the names missing from tonight's account are the ones
 * the previous close's evening closed, and the previous close's document - not
 * tonight's - is where that list lives. A null is the evening having been unable to
 * read that document, which is a page that could not look and has to say so; an
 * empty list is the previous close having deferred nothing, which decides the class.
 */
const PREVIOUS_REVERSALS: Unchecked = {
  what: "a name the previous close closed and has not reopened",
  needs: "the previous close's deferred-reversal list from the run that read it",
};

/**
 * The mismatches, split into the explained and the unexplained.
 *
 * The classes that can be decided page-only, and the one key each rests on:
 *
 * - **deferred reversals**, `bridge.reversals_pending`: the names the evening closed
 *   tonight so the other side can open tomorrow. On 2026-10-08 that list is exactly
 *   BEN, F, VZ and ZTS, which is also that morning's four missing-at-broker names -
 *   the loop closed them, so the account not holding them is the intended state;
 * - **the previous close's deferrals**, `bridge.previous_reversals_pending`: the same
 *   names one session later, read out of the previous close's document and
 *   republished beside this close's own list, which is the key that decides the class
 *   that used to be listed as one the page could not check. Null there is a page that
 *   could not look, and the class goes back on the list;
 * - **a leg the $250 floor left untraded**, `bridge.under_minimum_tickers`: the names
 *   the floor's count (`bridge.under_minimum`) is taken from. The count alone left the
 *   class undecidable - a reader could see that 25 legs went untraded and not which -
 *   and a name the floor skipped is the loop's own decision, not a break. It explains
 *   one side only: the target asking for a position the run chose not to open. A name
 *   the *account* holds and the store does not is the break this panel exists to
 *   show, and a leg that was never sent does not explain a position being there;
 * - **a position removed with no order**, `bridge.removed_without_order`: a name
 *   that left the account and which the bridge has already itemised as explained by
 *   the record it keeps;
 * - **a leg the broker refused**, `actual_holdings.fills.not_sent_lines`: the evening
 *   wrote the order and the broker would not take it, which is what a delisted or
 *   merged asset looks like from here. The line carries the ticker and the broker's
 *   own reason, so the page can say what happened without checking anything.
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
  const underMinimum = new Set(bridge?.under_minimum_tickers ?? []);
  const previousReversals = bridge?.previous_reversals_pending ?? null;
  const deferred = new Set(previousReversals ?? []);
  const refused = refusedTickers(snapshot);
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
        label: "in transit",
      };
    }
    if (deferred.has(ticker)) {
      return {
        ticker,
        side,
        why: "deferred reversal of the previous close: closed then, reopening now",
        key: "bridge.previous_reversals_pending",
        label: "in transit",
      };
    }
    // A flip is the same fact as a deferral seen from the other side: the evening
    // closed the leg it held and opened the other one, and tonight's read has the
    // first half only.
    if (flipping(snapshot, ticker)) {
      return {
        ticker,
        side,
        why: "flipping sides: the closing leg went out tonight, the other one opens next",
        key: "book.names",
        label: "in transit",
      };
    }
    if (underMinimum.has(ticker) && side === "targeted_not_held") {
      return {
        ticker,
        side,
        why: "the $250 floor left its leg untraded, so the book is short a position it chose not to open",
        key: "bridge.under_minimum_tickers",
        label: "too small",
      };
    }
    if (refused.has(ticker)) {
      return {
        ticker,
        side,
        why: refused.get(ticker) as string,
        key: "actual_holdings.fills.not_sent_lines",
        label: "stuck",
      };
    }
    if (removals.has(ticker)) {
      return {
        ticker,
        side,
        why: "left the account with no order, already itemised by the bridge",
        key: "bridge.removed_without_order",
        label: "in transit",
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
      label: "look at this",
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
  // The classes the page could not check: the previous close's list drops off once
  // the document carries the key at all - a null is the evening saying it could not
  // read that document, and the floor's class drops off once the count has tickers
  // beside it.
  const unchecked = [
    ...(previousReversals === null ? [PREVIOUS_REVERSALS] : []),
    ...UNCHECKED.filter(
      (entry) =>
        !(entry.what === "a leg too small to trade" && underMinimum.size > 0) &&
        !(entry.what.startsWith("an asset the broker says") && refused.size > 0),
    ),
  ];
  return {
    expected: current.filter((entry) => entry.key !== ""),
    unexpected: current.filter((entry) => entry.key === ""),
    unchecked,
    read: targetRead ? compare.read : storeRead,
    source: targetRead ? "target" : storeRead ? "store" : "none",
    compare: targetRead ? compare : null,
    evening: targetRead ? store : null,
  };
}

/**
 * The tickers the broker would not take an order for, with the line the run wrote.
 *
 * `not_sent_lines` are the legs the evening built and could not send - the broker
 * never saw the order, so the reason on the line (`SYMBOL_NOT_FOUND`) is the asset
 * feed's answer rather than a rejection. The first word of the line is the ticker and
 * the reason sits in brackets at the end, which is the shape the writer fixes at the
 * source; a line that does not parse is skipped rather than guessed at.
 */
function refusedTickers(snapshot: Snapshot): Map<string, string> {
  const refused = new Map<string, string>();
  for (const line of snapshot.actual_holdings?.fills?.not_sent_lines ?? []) {
    const match = /^(\S+)\s+(.*?)\s+never sent\s*\((.*)\)$/.exec(line.trim());
    if (!match) continue;
    refused.set(
      match[1],
      `${match[3]}: the broker would not take the order to close it, so the position sits until the broker settles it`,
    );
  }
  return refused;
}

/** Whether the target has this name on the other side from the account. */
function flipping(snapshot: Snapshot, ticker: string): boolean {
  const held = (snapshot.actual_holdings?.names ?? []).find((name) => name.ticker === ticker);
  const wanted = (snapshot.book?.names ?? []).find((name) => name.ticker === ticker);
  if (!held || !wanted) return false;
  if (!held.side || !wanted.side) return false;
  return held.side !== wanted.side;
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
