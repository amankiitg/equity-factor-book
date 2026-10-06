// The fixtures against the schema, and the schema against the page.
//
// `docs/snapshot.schema.json` is the contract: the Python writer is tested
// against it, and the TypeScript types in `types.ts` are hand-written mirrors of
// it. This test is what keeps the mirrors honest, by checking every committed
// fixture for the keys `types.ts` declares and the page reads. It fails when the
// writer starts emitting a field the page does not know, or when the page starts
// reading a field the fixtures do not carry.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURES = join(HERE, "..", "fixtures");

const NAMES = [
  "snapshot_ok.json",
  "snapshot_expired.json",
  "snapshot_stale_stopped.json",
  "snapshot_error.json",
  "snapshot_catch_up.json",
  "snapshot_market_closed.json",
  "snapshot_establishment.json",
  "snapshot_no_book.json",
  "snapshot_actual_holdings.json",
  "snapshot_fills_rejected.json",
  "snapshot_position_removed.json",
];

// The fixtures that carry an `actual_holdings` block, which is every document a
// run has read the account for: the two the morning republished, and the evening
// whose read found a position gone. Exactly these, so a fourth one cannot appear
// without this list moving with it.
const ACCOUNT_FIXTURES = [
  "snapshot_actual_holdings.json",
  "snapshot_fills_rejected.json",
  "snapshot_position_removed.json",
];

// The fixture that carries the departure block: the PSKY removal, where a name
// left the account between two reads with no closing leg filled and no activity
// of the broker's naming it.
const REMOVED_FIXTURE = "snapshot_position_removed.json";

// The account's own book. Not in TOP_LEVEL on purpose: the key is absent until a
// run has read the account, so requiring it everywhere would demand a key none of
// the other fixtures may carry.
const ACTUAL = [
  "as_of",
  "close",
  "read_by",
  "n_names",
  "gross_notional",
  "net_notional",
  "names",
  "fills",
];

const ACTUAL_NAME = ["ticker", "side", "notional", "weight"];

const ACTUAL_FILLS = [
  "trade_date",
  "n_orders",
  "n_filled",
  "n_unfilled",
  "not_sent",
  "realized_cost_bps",
  "expected_cost_bps",
  "unfilled",
  "not_sent_lines",
  "unread",
];

// The departure block: the names that left the account with nothing of the
// evening's explaining them, which is the one fact on the page no other number
// implies.
const EXITS = ["previous_read", "feed", "window", "names"];

const EXIT_NAME = ["ticker", "quantity", "notional"];

const TOP_LEVEL = [
  "schema_version",
  "generated_at",
  "target_close",
  "book_as_of",
  "expected_next_by",
  "dry_run",
  "store",
  "run_status",
  "construction",
  "positions",
  "breadth",
  "book",
  "exposures_before_hedge",
  "exposures_after_hedge",
  "hedge",
  "exposures",
  "reconciliation",
];

const RUN_STATUS = [
  "status",
  "detail",
  "failing_inputs",
  "catch_up",
  "catch_up_sessions",
  "splits",
  "flags",
  "notify_status",
  "snapshot",
  "establishment",
  "cost_label",
];

const POSITIONS = [
  "matches",
  "n_broker",
  "n_store",
  "source",
  "note",
  "missing_at_broker",
  "missing_in_store",
  "max_abs_drift",
];

const BOOK = ["n_names", "reason", "names"];

const load = (name: string): Record<string, Record<string, unknown>> =>
  JSON.parse(readFileSync(join(FIXTURES, name), "utf8"));

describe("the fixtures and the page's types", () => {
  it.each(NAMES)("%s carries every key the page reads", (name) => {
    const fixture = load(name);
    expect(fixture.schema_version).toBe(1);
    for (const key of TOP_LEVEL) {
      expect(Object.keys(fixture), `${name} is missing ${key}`).toContain(key);
    }
    for (const key of RUN_STATUS) {
      expect(Object.keys(fixture.run_status), `${name}.run_status is missing ${key}`).toContain(
        key,
      );
    }
    for (const key of POSITIONS) {
      expect(Object.keys(fixture.positions), `${name}.positions is missing ${key}`).toContain(key);
    }
    for (const key of BOOK) {
      expect(Object.keys(fixture.book), `${name}.book is missing ${key}`).toContain(key);
    }
  });

  it.each(NAMES)("%s has no NaN and no Infinity", (name) => {
    const text = readFileSync(join(FIXTURES, name), "utf8");
    expect(text).not.toMatch(/\bNaN\b/);
    expect(text).not.toMatch(/Infinity/);
  });

  it("lists the book largest absolute weight first, in every state", () => {
    for (const name of NAMES) {
      const names = load(name).book.names as Array<{ weight: number | null }>;
      const weights = names.map((entry) => Math.abs(entry.weight ?? 0));
      expect(weights, `${name} is not sorted`).toEqual([...weights].sort((a, b) => b - a));
    }
  });

  it("states a reason whenever the book is empty", () => {
    for (const name of NAMES) {
      const book = load(name).book as { n_names: number; reason: string | null };
      if (book.n_names === 0) {
        expect(book.reason, `${name} has an empty book and no reason`).toBeTruthy();
      }
    }
  });

  it("carries the account's own book in exactly the fixtures that read it", () => {
    // Absent, never null: a null key would read as an account holding nothing,
    // which is a different statement from an account nobody read.
    for (const name of NAMES) {
      const fixture = load(name) as Record<string, unknown>;
      if (ACCOUNT_FIXTURES.includes(name)) {
        expect(Object.keys(fixture), `${name} has no actual holdings`).toContain(
          "actual_holdings",
        );
      } else {
        expect(
          Object.keys(fixture),
          `${name} carries actual_holdings, which only a morning fixture may`,
        ).not.toContain("actual_holdings");
      }
    }
  });


  it("carries the departure block in the fixture built for it, and nowhere else", () => {
    for (const name of NAMES) {
      const fixture = load(name) as Record<string, unknown>;
      const actual = fixture.actual_holdings as Record<string, unknown> | undefined;
      if (name === REMOVED_FIXTURE) {
        const exits = actual?.exits as Record<string, unknown>;
        for (const key of EXITS) {
          expect(Object.keys(exits), `${name}: exits is missing ${key}`).toContain(key);
        }
        // The real case: PSKY left the account between the 10-05 read and the
        // 10-06 one, and neither a filled close nor an activity of the broker's
        // names the ticker.
        const names = exits.names as Array<Record<string, number>>;
        expect(names.map((entry) => entry.ticker)).toEqual(["PSKY"]);
        expect(names[0].quantity).toBeCloseTo(326.072572039, 6);
        expect(names[0].notional).toBeCloseTo(3211.81, 2);
        expect(exits.feed).toBe("read");
        // The dollars are on the day's row as their own labelled figure, which is
        // what stops them from being read as a result of the strategy.
        const reconciliation = fixture.reconciliation as Record<string, number>;
        expect(reconciliation.unexplained_adjustment).toBeCloseTo(-3211.81, 2);
      } else {
        expect(
          Object.keys(actual ?? {}),
          `${name} carries a departure block, which only the removal fixture may`,
        ).not.toContain("exits");
      }
    }
  });

  it.each(ACCOUNT_FIXTURES)(
    "reads the actual holdings block of %s the way the page draws it",
    (name) => {
      const block = load(name).actual_holdings as Record<string, unknown>;
      for (const key of ACTUAL) {
        expect(Object.keys(block), `${name}: actual_holdings is missing ${key}`).toContain(key);
      }
      const names = block.names as Array<Record<string, unknown>>;
      expect(names.length).toBe(block.n_names);
      for (const entry of names) {
        for (const key of ACTUAL_NAME) {
          expect(Object.keys(entry), `${name}: a held name is missing ${key}`).toContain(key);
        }
      }
      // Largest absolute position first, the order the section prints and the same
      // order the target book above it uses.
      const notionals = names.map((entry) => Math.abs(entry.notional as number));
      expect(notionals).toEqual([...notionals].sort((a, b) => b - a));
      // Which run read it, and the fields that follow from that: the morning's read
      // is the one with fills, the evening's is the one with no close.
      expect(["evening", "morning"]).toContain(block.read_by);
      if (block.read_by === "morning") {
        expect(block.close).toBeTruthy();
        expect(block.fills).toBeTruthy();
        const fills = block.fills as Record<string, unknown>;
        for (const key of ACTUAL_FILLS) {
          expect(Object.keys(fills), `${name}: fills is missing ${key}`).toContain(key);
        }
        const filled = fills.n_filled as number;
        const missed = fills.n_unfilled as number;
        const unread = (fills.unread as unknown[]).length;
        // `n_orders` counts the legs the evening sent, and `not_sent` counts the
        // legs it did not; the two are disjoint sets, so subtracting `not_sent`
        // from `n_orders` double-counts the exclusion the writer already made.
        expect(fills.n_orders).toBe(filled + missed + unread);
      }
    },
  );
});
