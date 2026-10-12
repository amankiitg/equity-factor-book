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

  it("names the classes it cannot check at all, with the key each one needs", () => {
    const report = classify(doc({}));
    const needs = report.unchecked.map((entry) => entry.needs).join(" ");
    expect(report.unchecked).toHaveLength(3);
    expect(needs).toContain("bridge.under_minimum");
    expect(needs).toContain("efb.e11_corporate_actions");
    // The one the brief expected to be decidable: the list is one session out.
    expect(needs).toContain("previous close's bridge.reversals_pending");
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
