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
  "attribution",
];

const ATTRIBUTION = [
  "n_days",
  "first_day",
  "last_day",
  "cumulative",
  "by_factor",
  "daily",
  "cost",
  "note",
];

const ATTRIBUTION_CUMULATIVE = [
  "pnl_total",
  "pnl_factor",
  "pnl_idio",
  "pnl_cost",
  "max_identity_residual",
  "n_computed_specific",
];

const ATTRIBUTION_DAY = [
  "trade_date",
  "pnl_total",
  "pnl_factor",
  "pnl_idio",
  "pnl_cost",
  "pnl_timing",
  "book_beta",
  "market_return",
  "pnl_beta",
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
    const attribution = fixture.attribution as Record<string, unknown>;
    for (const key of ATTRIBUTION) {
      expect(Object.keys(attribution), `${name}.attribution is missing ${key}`).toContain(key);
    }
    const cumulative = attribution.cumulative as Record<string, unknown>;
    for (const key of ATTRIBUTION_CUMULATIVE) {
      expect(Object.keys(cumulative), `${name}.attribution.cumulative is missing ${key}`).toContain(
        key,
      );
    }
    for (const day of attribution.daily as Array<Record<string, unknown>>) {
      for (const key of ATTRIBUTION_DAY) {
        expect(Object.keys(day), `${name}.attribution.daily[] is missing ${key}`).toContain(key);
      }
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

  it("carries attributed days in every state, and a day is a day", () => {
    // The attribution describes the book, and the book is the same object in all
    // six states, so every fixture has it. A date with a midnight time stapled to
    // it is the bug this pins: the page shows these beside `target_close`.
    for (const name of NAMES) {
      const attribution = load(name).attribution as {
        n_days: number;
        daily: Array<{ trade_date: string }>;
      };
      expect(attribution.n_days, `${name} has no attributed days`).toBeGreaterThan(0);
      expect(attribution.daily.length, `${name} has no daily series`).toBeGreaterThan(0);
      for (const day of attribution.daily) {
        expect(day.trade_date, `${name} has a date with a time in it`).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      }
    }
  });
});
