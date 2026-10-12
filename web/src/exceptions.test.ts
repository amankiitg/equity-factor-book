// The classification rule, pinned on the real numbers.
//
// The rule has one direction that matters and it is the hard one: a name this
// document does not explain is an exception, even when the loop's own record
// elsewhere explains it. The names in the cases below are the ones the published
// documents actually carry, because the interesting case is exactly the one a
// plausible-looking shortcut gets wrong.

import { describe, expect, it } from "vitest";

import { classify, exceptionText, hasUnexpected } from "./exceptions";
import type { Snapshot } from "./types";
import broken from "../fixtures/snapshot_bridge_broken.json";

const BROKEN = broken as unknown as Snapshot;

/** A document carrying only the blocks this module reads. */
function doc(parts: {
  atBroker?: string[];
  inStore?: string[];
  reversals?: string[];
  removed?: string[];
  underMinimum?: string[];
  matches?: boolean | null;
}): Snapshot {
  return {
    positions: {
      matches: parts.matches === undefined ? false : parts.matches,
      missing_at_broker: parts.atBroker ?? [],
      missing_in_store: parts.inStore ?? [],
    },
    bridge: {
      reversals_pending: parts.reversals ?? [],
      removed_without_order: (parts.removed ?? []).map((ticker) => ({ ticker })),
      under_minimum_tickers: parts.underMinimum ?? [],
    },
  } as unknown as Snapshot;
}

/**
 * The published 2026-10-12 document, at a size a test can read.
 *
 * A morning read: the account after the fills, one name the target has dropped (WBD),
 * one the target asks for that the account does not hold (INVH, which this document's
 * own bridge lists as the deferred reversal), and two names both books carry at a
 * different size. Beside it, the evening's account-versus-store comparison still fails
 * on the same two books, which is the comparison the morning read replaced.
 */
const MORNING: Snapshot = {
  generated_at: "2026-10-09T22:50:01Z",
  book: {
    gross: 1,
    gross_notional: 1_000_000,
    names: [
      { ticker: "KO", weight: 0.2, side: "long" },
      { ticker: "SMCI", weight: 0.15, side: "long" },
      { ticker: "INVH", weight: -0.02, side: "short" },
    ],
  },
  actual_holdings: {
    as_of: "2026-10-12T15:31:15+00:00",
    close: "2026-10-09",
    read_by: "morning",
    names: [
      { ticker: "KO", notional: 180_000 },
      { ticker: "SMCI", notional: 120_000 },
      { ticker: "WBD", notional: -70_000 },
    ],
  },
  positions: {
    matches: false,
    missing_at_broker: ["BEN"],
    missing_in_store: ["WBD"],
  },
  bridge: { reversals_pending: ["INVH"], removed_without_order: [] },
} as unknown as Snapshot;

/**
 * A morning read in miniature: a target book, the account, and the bridge keys.
 *
 * `target` names are in the book and not in the account, `held` the other way round,
 * and the bridge carries the two ticker lists the classifier reads.
 */
function targetRead(parts: {
  target?: string[];
  held?: string[];
  underMinimum?: string[];
  reversals?: string[];
}): Snapshot {
  return {
    book: {
      gross: 1,
      gross_notional: 1_000_000,
      names: (parts.target ?? []).map((ticker) => ({ ticker, weight: 0.01, side: "long" })),
    },
    actual_holdings: {
      read_by: "morning",
      names: (parts.held ?? []).map((ticker) => ({ ticker, notional: 10_000 })),
    },
    positions: { matches: false, missing_at_broker: [], missing_in_store: [] },
    bridge: {
      reversals_pending: parts.reversals ?? [],
      removed_without_order: [],
      under_minimum_tickers: parts.underMinimum ?? [],
    },
  } as unknown as Snapshot;
}

describe("the classification", () => {
  it("files a name the document's own reversal list names as expected", () => {
    // 2026-10-08's bridge names exactly these four, which is also that morning's
    // four missing-at-broker names: the loop closed them, so the account not
    // holding them is the intended state and the document says so itself.
    const report = classify(
      doc({ atBroker: ["BEN", "F", "VZ", "ZTS"], reversals: ["BEN", "F", "VZ", "ZTS"] }),
    );
    expect(report.expected.map((entry) => entry.ticker)).toEqual(["BEN", "F", "VZ", "ZTS"]);
    expect(report.unexpected).toEqual([]);
    for (const entry of report.expected) {
      expect(entry.key).toBe("bridge.reversals_pending");
      expect(entry.side).toBe("at_broker");
    }
  });

  it("files a name the bridge itemised as a removal as expected, and says which key", () => {
    const report = classify(doc({ inStore: ["PSKY"], removed: ["PSKY"] }));
    expect(report.expected).toHaveLength(1);
    expect(report.expected[0].key).toBe("bridge.removed_without_order");
    expect(report.expected[0].side).toBe("in_store");
  });

  it("keeps a name this document does not explain as an exception", () => {
    // The live pairing of 2026-10-09: the four names the account does not hold are
    // the *previous* close's deferred reversals, and this document's own list -
    // INVH - is one session ahead of them, naming the gap tomorrow's read will
    // show. Nothing here names BEN, F, VZ or ZTS, so the page must not decide they
    // are routine on the strength of the four looking familiar.
    const report = classify(doc({ atBroker: ["BEN", "F", "VZ", "ZTS"], reversals: ["INVH"] }));
    expect(report.expected).toEqual([]);
    expect(report.unexpected.map((entry) => entry.ticker)).toEqual(["BEN", "F", "VZ", "ZTS"]);
    for (const entry of report.unexpected) {
      expect(entry.key).toBe("");
      expect(entry.why).toContain("nothing in this document explains it");
    }
    expect(hasUnexpected(report)).toBe(true);
  });

  it("tells the two directions apart, and only the store-holds direction is over the key", () => {
    const report = classify(doc({ atBroker: ["WBD"], inStore: ["WBD"] }));
    const [atBroker] = report.unexpected.filter((entry) => entry.side === "at_broker");
    const [inStore] = report.unexpected.filter((entry) => entry.side === "in_store");
    expect(atBroker.ticker).toBe("WBD");
    expect(inStore.ticker).toBe("WBD");
    expect(atBroker.why).not.toBe(inStore.why);
    expect(atBroker.why).toContain("the store holds it");
    expect(inStore.why).toContain("the account holds it");
  });

  it("does not call a read that named no names a pass", () => {
    // `matches === null` is the read that did not happen; empty lists beside a false
    // `matches` are a comparison that found nothing, which is a different sentence.
    expect(classify(doc({ matches: null })).read).toBe(false);
    expect(classify(doc({ matches: true })).read).toBe(true);
    expect(classify({} as unknown as Snapshot).read).toBe(false);
  });

  it("reads the reversal list the document carries, name by name", () => {
    // Driven by the fixture's own lists rather than by names typed here, so
    // regenerating the fixture cannot leave the test passing against a stale one.
    const names = (BROKEN.bridge?.reversals_pending ?? []).map((ticker) => String(ticker));
    const removed = (BROKEN.bridge?.removed_without_order ?? []).map((entry) => entry.ticker);
    expect(names.length).toBeGreaterThan(1);
    expect(removed.length).toBeGreaterThan(0);
    const report = classify(
      {
        positions: {
          matches: false,
          missing_at_broker: [...names, ...removed, "NOTLISTED"],
          missing_in_store: [],
        },
        bridge: BROKEN.bridge,
      } as unknown as Snapshot,
    );
    expect(report.unexpected.map((entry) => entry.ticker)).toEqual(["NOTLISTED"]);
    expect(report.expected.map((entry) => entry.ticker).sort()).toEqual(
      [...names, ...removed].sort(),
    );
    expect(report.expected.every((entry) => entry.key !== "")).toBe(true);
  });

  it("files a leg the floor left untraded as expected, by ticker", () => {
    // The count alone said 21 legs of 2026-10-09 went untraded and not which, so the
    // class was listed as one the page could not check. The tickers are published
    // beside the count now, and the target asking for a position whose leg the floor
    // skipped is the loop's own decision: on a morning read it is the target that
    // asks and the account that does not hold it.
    const report = classify(targetRead({ target: ["PSKY", "SLB"], underMinimum: ["PSKY"] }));
    expect(report.source).toBe("target");
    expect(report.expected.map((entry) => entry.ticker)).toEqual(["PSKY"]);
    expect(report.expected[0].key).toBe("bridge.under_minimum_tickers");
    expect(report.expected[0].side).toBe("targeted_not_held");
    expect(report.expected[0].why).toContain("the $250 floor left its leg untraded");
    // A name the floor did not skip is still the reader's to explain.
    expect(report.unexpected.map((entry) => entry.ticker)).toEqual(["SLB"]);
  });

  it("does not let a skipped leg explain a position the account holds", () => {
    // The hard direction: a name the account holds and the target does not is the
    // break the panel exists to show, and "its leg was under the minimum" is not an
    // explanation for a position being there.
    const report = classify(
      targetRead({ target: [], held: ["SLB"], underMinimum: ["SLB"] }),
    );
    expect(report.expected).toEqual([]);
    expect(report.unexpected.map((entry) => entry.ticker)).toEqual(["SLB"]);
    expect(report.unexpected[0].side).toBe("held_not_targeted");
  });

  it("names the classes it cannot check at all, with the key each one needs", () => {
    const report = classify(doc({}));
    const needs = report.unchecked.map((entry) => entry.needs).join(" ");
    expect(report.unchecked).toHaveLength(2);
    expect(needs).not.toContain("bridge.under_minimum,");
    expect(needs).toContain("efb.e11_corporate_actions");
    // The one the brief expected to be decidable: the list is one session out.
    expect(needs).toContain("previous close's bridge.reversals_pending");
  });
});

describe("the classification follows the read", () => {
  it("compares the morning read with the target, not with the store", () => {
    const report = classify(MORNING);
    expect(report.source).toBe("target");
    expect(report.read).toBe(true);
    // WBD is held and not wanted, and nothing in the document names it.
    expect(report.unexpected.map((entry) => entry.ticker)).toEqual(["WBD"]);
    expect(report.unexpected[0].side).toBe("held_not_targeted");
    expect(report.unexpected[0].why).toContain("the account holds it and the target does not");
    // INVH is wanted and not held, and the document's own list explains it.
    expect(report.expected.map((entry) => entry.ticker)).toEqual(["INVH"]);
    expect(report.expected[0].key).toBe("bridge.reversals_pending");
    expect(report.expected[0].side).toBe("targeted_not_held");
    expect(exceptionText(report)).toBe("1 unexpected, 1 expected");
    // The drift is on the names both books carry, largest first.
    expect(report.compare?.drifts.map((row) => row.ticker)).toEqual(["SMCI", "KO"]);
  });

  it("keeps the evening's account-versus-store comparison beside it, never as the current one", () => {
    const report = classify(MORNING);
    expect(report.evening?.map((entry) => entry.ticker).sort()).toEqual(["BEN", "WBD"]);
    expect(report.evening?.map((entry) => entry.side).sort()).toEqual(["at_broker", "in_store"]);
    // Neither name is in the current comparison's lists, so a reader cannot read the
    // evening's findings as this morning's answer.
    const current = [...report.expected, ...report.unexpected].map((entry) => entry.ticker);
    expect(current.sort()).toEqual(["INVH", "WBD"]);
  });

  it("compares an evening read with the store, as it always did", () => {
    const evening = {
      ...MORNING,
      actual_holdings: { ...MORNING.actual_holdings, read_by: "evening" },
    } as Snapshot;
    const report = classify(evening);
    expect(report.source).toBe("store");
    expect(report.compare).toBeNull();
    expect(report.evening).toBeNull();
    expect(report.unexpected.map((entry) => entry.ticker).sort()).toEqual(["BEN", "WBD"]);
    expect(exceptionText(report)).toBe("2 unexpected mismatches");
  });

  it("says which comparison did not run when the morning read carries no book", () => {
    const report = classify({
      actual_holdings: { read_by: "morning", names: [] },
    } as unknown as Snapshot);
    expect(report.source).toBe("target");
    expect(report.read).toBe(false);
    expect(exceptionText(report)).toBe("the account has not been compared with the target");
  });
});

describe("the one line the count is read from", () => {
  it("states the unexplained count and the explained count as two numbers", () => {
    const report = classify(
      doc({ atBroker: ["BEN", "WBD"], inStore: ["ZTS"], reversals: ["ZTS"] }),
    );
    expect(exceptionText(report)).toBe("2 unexpected, 1 expected");
  });

  it("says so when nothing was compared, rather than counting zero", () => {
    expect(exceptionText(classify(doc({ matches: null })))).toBe(
      "account not compared with the store",
    );
  });

  it("reads a single name in the singular", () => {
    expect(exceptionText(classify(doc({ atBroker: ["WBD"] })))).toBe("1 unexpected mismatch");
    expect(exceptionText(classify(doc({ matches: true })))).toBe("no mismatch");
  });
});
