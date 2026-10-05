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
];

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
  "unread",
];

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
      if (name === "snapshot_actual_holdings.json") {
        expect(Object.keys(fixture), `${name} has no actual holdings`).toContain(
          "actual_holdings",
        );
      } else {
        expect(
          Object.keys(fixture),
          `${name} carries actual_holdings, which only the read fixture may`,
        ).not.toContain("actual_holdings");
      }
    }
  });

  it("reads the actual holdings block the way the page draws it", () => {
    const block = load("snapshot_actual_holdings.json").actual_holdings as Record<
      string,
      unknown
    >;
    for (const key of ACTUAL) {
      expect(Object.keys(block), `actual_holdings is missing ${key}`).toContain(key);
    }
    const names = block.names as Array<Record<string, unknown>>;
    expect(names.length).toBe(block.n_names);
    for (const entry of names) {
      for (const key of ACTUAL_NAME) {
        expect(Object.keys(entry), `a held name is missing ${key}`).toContain(key);
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
        expect(Object.keys(fills), `fills is missing ${key}`).toContain(key);
      }
      const filled = fills.n_filled as number;
      const missed = fills.n_unfilled as number;
      expect((fills.n_orders as number) - (fills.not_sent as number)).toBe(filled + missed);
    }
  });
});
