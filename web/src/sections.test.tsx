// The sections the brief asked for, driven by the fixtures.
//
// Each assertion recomputes its expectation from the fixture and the bundled
// sector map rather than typing a number, so regenerating the fixtures cannot
// make a test pass against the wrong book.
//
// Two of the eight sections the page draws are hidden until the snapshot carries
// their data: risk concentration needs a per-name share of predicted specific
// variance, and movers need a per-name contribution for the session. Those are
// tested twice, once without the data (the section must be absent, not empty) and
// once with it (the section must draw it). The empty-book fixture covers the
// third case, a snapshot with no book at all, where every book section goes.

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SnapshotView } from "./App";
import { bookFacts } from "./book";
import { sectorDeltas } from "./SectorSection";
import { dateOnly, dollars, percent, signedDollars, signedPercent } from "./format";
import { sectorCodeFor, sectorLabel, UNMAPPED } from "./sectors";
import type { AttributionPeriod, Snapshot } from "./types";
import noBook from "../fixtures/snapshot_no_book.json";
import ok from "../fixtures/snapshot_ok.json";
import rejected from "../fixtures/snapshot_fills_rejected.json";
import withActual from "../fixtures/snapshot_actual_holdings.json";

const OK = ok as unknown as Snapshot;
const NONE = noBook as unknown as Snapshot;
const ACTUAL = withActual as unknown as Snapshot;
const REJECTED = rejected as unknown as Snapshot;
const NOW = new Date("2026-09-21T23:00:00Z");

/**
 * A morning read whose account is away from its target in the three ways that matter.
 *
 * Small enough that every number in it can be read at a glance: the target asks for
 * KO, SMCI and INVH at $200,000, $150,000 and -$20,000, and the account holds KO and
 * SMCI at $180,000 and $120,000, plus a short in WBD the target has dropped and no
 * INVH at all. The five sectors it touches are the ones the map carries, so a driver
 * line can be read against a sector the test names.
 */
const MORNING: Snapshot = {
  generated_at: "2026-10-09T22:50:01Z",
  book_as_of: "2026-10-09T00:00:00",
  target_close: "2026-10-09T00:00:00",
  expected_next_by: "2026-10-12T22:30:00Z",
  dry_run: false,
  book: {
    gross: 1,
    gross_notional: 1_000_000,
    net: 0,
    n_names: 3,
    n_long: 2,
    n_short: 1,
    names: [
      { ticker: "KO", weight: 0.2, side: "long", reason: "no trade", z: 1, alpha: 0 },
      { ticker: "SMCI", weight: 0.15, side: "long", reason: "risk moved", z: 1, alpha: 0 },
      { ticker: "INVH", weight: -0.02, side: "short", reason: "alpha moved", z: -1, alpha: 0 },
    ],
  },
  actual_holdings: {
    as_of: "2026-10-12T15:31:15+00:00",
    close: "2026-10-09",
    read_by: "morning",
    n_names: 3,
    gross_notional: 1_000_000,
    net_notional: 0,
    names: [
      { ticker: "KO", side: "long", notional: 180_000, weight: 0.18 },
      { ticker: "SMCI", side: "long", notional: 120_000, weight: 0.12 },
      { ticker: "WBD", side: "short", notional: -70_000, weight: -0.07 },
    ],
    fills: null,
  },
} as unknown as Snapshot;

/** The risk and mover panels are the weekly read, so they are on their own tab. */
function openAttributionTab(): void {
  fireEvent.click(document.querySelector("[data-view='attribution']") as HTMLElement);
}

/** The drawer is shut until a tab is asked for, which is half of what it is for. */
function openDrawer(tab: "book" | "actual"): HTMLElement {
  fireEvent.click(document.querySelector(`[data-tab='${tab}']`) as HTMLElement);
  return document.querySelector(
    tab === "book" ? "[data-section='holdings']" : "[data-section='actual-holdings']",
  ) as HTMLElement;
}

describe("the metrics row", () => {
  it("states the counts, the dollars, the breadth, the largest name and the cost", () => {
    const facts = bookFacts(OK);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const cards = document.querySelector("[data-cards='true']") as HTMLElement;
    expect(cards).toBeTruthy();
    const card = (label: string): HTMLElement =>
      cards.querySelector(`[data-card="${label}"]`) as HTMLElement;

    // Gross and net are the traded book's own, with the dollars beside the
    // fraction so the two are one statement.
    expect(card("gross").textContent).toContain(percent(OK.book.gross));
    expect(card("gross").textContent).toContain(dollars(OK.book.gross_notional));
    expect(card("net").textContent).toContain(percent(OK.book.net));
    // The name counts carry each side's dollars, which is where the long and
    // short gross live now that the sector footer is gone.
    expect(card("long-names").textContent).toContain(String(facts.nLong));
    expect(card("long-names").textContent).toContain(dollars(facts.longNotional));
    expect(card("short-names").textContent).toContain(String(facts.nShort));
    expect(card("short-names").textContent).toContain(dollars(facts.shortNotional));
    expect(card("n_eff_kept").textContent).toContain(
      (OK.breadth.n_eff_kept as number).toFixed(1),
    );
    expect(card("n_eff_kept").textContent).toContain(OK.breadth.kept_label);
    // The pre-floor telemetry is behind the construction disclosure now: still
    // addressable, and no longer on the row a reader scans in the morning.
    const construction = document.querySelector("[data-details='construction']") as HTMLElement;
    expect(construction).toBeTruthy();
    expect(card("n_eff_full_book").textContent).toContain(
      (OK.breadth.n_eff_full_book as number).toFixed(1),
    );
    expect(construction.textContent).toContain(
      (OK.breadth.n_eff_full_book as number).toFixed(1),
    );
    expect(card("largest-position").textContent).toContain(facts.largest?.ticker as string);
    // The ten largest weights as a share of the book's absolute weight.
    expect(card("top10-share").textContent).toContain(percent(facts.top10Share));
    expect(card("full-book-gross").textContent).toContain(
      percent(OK.book.full_book_gross),
    );
    const cost = card("expected-expense").textContent ?? "";
    expect(cost).toContain((OK.book.expected_cost_bps as number).toFixed(2));
    // And the split: the trading half summed from its own three parts, and the
    // borrow that no fill price can be measured against. A total alone leaves the
    // reader unable to say which half a miss belongs to.
    const split = OK.book.expected_cost_split as NonNullable<
      typeof OK.book.expected_cost_split
    >;
    expect(cost).toContain(`trading ${(split.trading as number).toFixed(2)} bp of NAV`);
    expect(cost).toContain(`spread ${(split.spread as number).toFixed(2)}`);
    expect(cost).toContain(`borrow ${(split.borrow as number).toFixed(2)} bp of NAV of holding cost`);
    // The fills card is the account's own, and this fixture has no account read.
    expect(OK.actual_holdings).toBeUndefined();
    expect(cards.querySelector("[data-card='fills']")).toBeNull();
  });

  it("states the fills the reconciler read, filled of sent and realized against expected", () => {
    const block = ACTUAL.actual_holdings;
    expect(block?.fills).toBeTruthy();
    if (!block?.fills) return;
    const fills = block.fills;
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    const card = document.querySelector("[data-card='fills']") as HTMLElement;
    expect(card).toBeTruthy();
    // "filled of sent": the denominator is the legs the evening sent, which the
    // writer's `n_orders` already counts. The never-sent legs are their own count
    // beside it, never subtracted from the denominator a second time.
    expect(fills.n_orders).toBeGreaterThanOrEqual(fills.n_filled as number);
    expect(card.textContent).toContain(`${fills.n_filled} of ${fills.n_orders} filled`);
    expect(card.textContent).toContain(
      `${fills.not_sent} never sent, ${fills.n_unfilled} did not fill`,
    );
    const realized = card.textContent ?? "";
    expect(realized).toContain((fills.realized_cost_bps as number).toFixed(2));
    // Measured from the previous close to the fill, and against the trading half of
    // the expectation: borrow is a holding cost and no fill price pays it.
    expect(realized).toContain("from the previous close to the fill");
    const split = ACTUAL.book.expected_cost_split as NonNullable<
      typeof ACTUAL.book.expected_cost_split
    >;
    expect(realized).toContain(
      `against ${(split.trading as number).toFixed(2)} bp of NAV of trading cost expected`,
    );
  });

  it("shows the realized cost averaged over every reconciled day", () => {
    // A single day is dominated by the overnight move: the leg is sized after one
    // close and fills at the next open, so the average is the number that can be
    // read as execution quality. The day count travels with it, because an average
    // of two days is not an average of twenty.
    const block = ACTUAL.actual_holdings;
    if (!block?.fills) return;
    const averaged: Snapshot = {
      ...ACTUAL,
      actual_holdings: {
        ...block,
        fills: { ...block.fills, realized_cost_avg_bps: 4.31, realized_cost_days: 7 },
      },
    };
    render(<SnapshotView snapshot={averaged} now={NOW} />);
    const card = document.querySelector("[data-card='fills']") as HTMLElement;
    expect(card.textContent).toContain("averages 4.31 bp of NAV across 7 session(s)");
  });

  it("says one day in the singular", () => {
    const block = ACTUAL.actual_holdings;
    if (!block?.fills) return;
    const one: Snapshot = {
      ...ACTUAL,
      actual_holdings: {
        ...block,
        fills: { ...block.fills, realized_cost_avg_bps: 6.42, realized_cost_days: 1 },
      },
    };
    render(<SnapshotView snapshot={one} now={NOW} />);
    expect(
      (document.querySelector("[data-card='fills']") as HTMLElement).textContent,
    ).toContain("averages 6.42 bp of NAV across 1 session(s)");
  });

  it("says the day's own number and no average when no day has been priced", () => {
    const block = ACTUAL.actual_holdings;
    if (!block?.fills) return;
    const none: Snapshot = {
      ...ACTUAL,
      actual_holdings: {
        ...block,
        fills: { ...block.fills, realized_cost_avg_bps: null, realized_cost_days: 0 },
      },
    };
    render(<SnapshotView snapshot={none} now={NOW} />);
    const text =
      (document.querySelector("[data-card='fills']") as HTMLElement).textContent ?? "";
    expect(text).not.toContain("averages");
    expect(text).toContain("from the previous close to the fill");
  });

  it("falls back to the whole expected cost when the document carries no split", () => {
    // A manifest that predates the cost breakdown has a total and no parts, and the
    // page states the total as what it is rather than comparing a fill against a
    // half it was never given.
    const block = ACTUAL.actual_holdings;
    if (!block?.fills) return;
    const { expected_cost_split: _drop, ...book } = ACTUAL.book;
    const older: Snapshot = {
      ...ACTUAL,
      book: { ...book, expected_cost_bps: 14.54 },
      actual_holdings: {
        ...block,
        fills: { ...block.fills, expected_cost_bps: 14.54 },
      },
    };
    render(<SnapshotView snapshot={older} now={NOW} />);
    const cost = (document.querySelector("[data-card='expected-expense']") as HTMLElement)
      .textContent ?? "";
    expect(cost).toContain("14.54");
    expect(cost).not.toContain("trading");
    const fills = (document.querySelector("[data-card='fills']") as HTMLElement).textContent ?? "";
    expect(fills).toContain("against 14.54 bp of NAV expected for the same one session");
    expect(fills).not.toContain("trading cost expected");
  });

  it("reports the 2026-10-05 morning's exact counts, and never a double-subtracted 165", () => {
    // The incident's own numbers, from the fixture the writer built for it: the
    // morning reconciled 197 of the 199 orders the evening sent, with 2 rejected
    // and the 34 under-$250 names never sent. The page read `n_orders - not_sent`
    // as the denominator and printed "197 of 165 filled", subtracting the
    // never-sent legs a second time. The numbers are asserted literally because
    // the point is the arithmetic, not the fixture.
    const fills = REJECTED.actual_holdings?.fills;
    expect(fills).toBeTruthy();
    if (!fills) return;
    expect([fills.n_orders, fills.n_filled, fills.n_unfilled, fills.not_sent]).toEqual([
      199, 197, 2, 34,
    ]);
    render(<SnapshotView snapshot={REJECTED} now={NOW} />);
    const card = document.querySelector("[data-card='fills']") as HTMLElement;
    expect(card.textContent).toContain("197 of 199 filled");
    expect(card.textContent).toContain("34 never sent, 2 did not fill");
    expect(card.textContent).not.toContain("165");
    // The misses are on the page too, each with the broker's own status word.
    const misses = document.querySelector("[data-fills='misses']") as HTMLElement;
    expect(misses.textContent).toContain("2 orders did not fill");
    for (const line of fills.unfilled) {
      expect(misses.textContent).toContain(line);
    }
  });

  it("derives the book in dollars from the snapshot's own gross and notional", () => {
    // The page must not carry the paper account's opening balance: one run's NAV
    // is not the next run's, and a hard-coded one is wrong quietly.
    const facts = bookFacts(OK);
    const implied = (OK.book.gross_notional as number) / (OK.book.gross as number);
    expect(facts.nav).toBeCloseTo(implied, 6);
    // The book is gross 1.0, so its own dollars and the snapshot's notional agree.
    expect(facts.longNotional + facts.shortNotional).toBeCloseTo(implied, 3);
    expect(facts.netNotional).toBeCloseTo(
      facts.longNotional - facts.shortNotional,
      6,
    );
  });
});

describe("by sector", () => {
  it("leads with the account-against-target difference, one row per sector", () => {
    // The account's own read is what the section differences against the target, so
    // this is the fixture that carries one. The old long/short bars are still on the
    // page, in the disclosure, because a neutral book's two sides are the same shape
    // and the decision view is the difference.
    const facts = bookFacts(ACTUAL);
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    const section = document.querySelector("[data-section='sector']") as HTMLElement;
    expect(section).toBeTruthy();
    const deltas = sectorDeltas(ACTUAL, facts.sectors);
    expect(deltas.length).toBeGreaterThan(1);
    for (const row of deltas) {
      const key = row.code === null ? "unmapped" : String(row.code);
      const node = section.querySelector(`[data-sector="${key}"]`) as HTMLElement;
      expect(node, `no row for ${row.label}`).toBeTruthy();
      expect(node.getAttribute("data-delta")).toBe(row.delta.toFixed(2));
      // The sign is drawn, not only labelled: over the target is one side of the
      // zero line and under it is the other.
      expect(node.querySelector(`[data-side="${row.delta >= 0 ? "over" : "under"}"]`)).toBeTruthy();
      expect(node.textContent).toContain(signedDollars(row.delta));
    }
    // Sorted by absolute size, largest first: the reader's first question is which
    // sector is furthest from its target.
    const sizes = deltas.map((row) => Math.abs(row.delta));
    expect(sizes).toEqual([...sizes].sort((a, b) => b - a));
    // And the target's gross is still there for anyone checking the shape.
    const gross = document.querySelector("[data-details='sector-gross']") as HTMLElement;
    expect(gross).toBeTruthy();
    expect(gross.textContent).toContain(dollars(facts.sectors[0].longNotional));
  });

  it("says which comparison it cannot make when the account has not been read", () => {
    // No account read means no difference to draw; the panel falls back to the
    // target's own net and says so rather than drawing the target against nothing,
    // which would render every sector as a full-size short.
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const section = document.querySelector("[data-section='sector']") as HTMLElement;
    expect(section).toBeTruthy();
    const note = section.querySelector("[data-sector-deltas='no-account']") as HTMLElement;
    expect(note).toBeTruthy();
    expect(note.textContent).toContain("account has not been read");
    expect(section.querySelector("[data-sector-net='true']")).toBeTruthy();
    expect(section.querySelector("[data-delta]")).toBeNull();
  });

  it("renders Unmapped for a name the bundled map does not carry", () => {
    // A new listing has no sector row until the vendor's table catches up, and
    // the page says so rather than guessing from the ticker's neighbours. The
    // fixture's own book is entirely mapped, so this state needs a name that is
    // not: ZZZZ is in no sector file and in no holdings archive.
    const snapshot: Snapshot = {
      ...OK,
      book: {
        ...OK.book,
        n_names: 3,
        names: [
          { ticker: "ZZZZ", weight: 0.05, side: "long", reason: "new position", z: 1, alpha: 0.1 },
          { ticker: "MU", weight: -0.04, side: "short", reason: "alpha moved", z: -1, alpha: -0.1 },
          { ticker: "MRNA", weight: 0.01, side: "long", reason: "alpha moved", z: 0.5, alpha: 0.01 },
        ],
      },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const row = document.querySelector("[data-sector='unmapped']") as HTMLElement;
    expect(row).toBeTruthy();
    expect(row.textContent).toContain(UNMAPPED);
    const holdings = openDrawer("book");
    const cells = Array.from(
      holdings.querySelector("[data-ticker='ZZZZ']")?.querySelectorAll("td") ?? [],
    ).map((cell) => cell.textContent);
    expect(cells[2]).toBe(UNMAPPED);
    // The mapped names beside it still read their own sector.
    const mapped = Array.from(
      holdings.querySelector("[data-ticker='MU']")?.querySelectorAll("td") ?? [],
    ).map((cell) => cell.textContent);
    expect(mapped[2]).toBe(sectorLabel(sectorCodeFor("MU")));
  });

  it("puts the largest difference on the page at half the track, so the rows share one scale", () => {
    // The committed fixtures cannot exercise this: their account block is a mock
    // built from the target, so it is sector-neutral to the last bit and every delta
    // is float noise. The real 2026-10-09 account is not neutral by a long way
    // (Communication Services -$8,149 against a target of exactly zero), so the
    // snapshot here is built with the account the section exists to difference.
    const snapshot: Snapshot = {
      ...OK,
      actual_holdings: {
        as_of: "2026-10-09T22:47:37+00:00",
        close: null,
        read_by: "evening",
        n_names: 3,
        gross_notional: 90_000,
        net_notional: 0,
        names: [
          { ticker: "GOOGL", side: "short", notional: -60_000, weight: -0.6 },
          { ticker: "KO", side: "long", notional: 18_000, weight: 0.18 },
          { ticker: "AAPL", side: "long", notional: 12_000, weight: 0.12 },
        ],
        fills: null,
      },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const section = document.querySelector("[data-sector-deltas='true']") as HTMLElement;
    const bars = Array.from(section.querySelectorAll("[data-side]")) as HTMLElement[];
    expect(bars.length).toBeGreaterThan(0);
    const widths = bars.map((bar) => parseFloat(bar.style.width));
    const deltas = sectorDeltas(snapshot, bookFacts(snapshot).sectors).map((row) =>
      Math.abs(row.delta),
    );
    const largest = Math.max(...deltas, 1);
    const smallest = Math.min(...deltas.filter((value) => value > 0));
    // Half the track is the largest, and every other row is drawn against it.
    expect(Math.max(...widths)).toBeCloseTo(50, 5);
    expect(Math.min(...widths)).toBeCloseTo((smallest / largest) * 50, 5);
  });

  it("reads the difference as the account's own drift, because the target is exactly neutral", () => {
    // The point of the panel: sector neutrality is a property of the *target*, so a
    // difference against it is the account's own per-sector net. Saying that on the
    // page is what stops the reader looking for a tilt in the target that is not
    // there.
    const facts = bookFacts(ACTUAL);
    const target = facts.sectors.map((bucket) => Math.abs(bucket.netNotional));
    expect(Math.max(...target)).toBeLessThan(1e-6);
  });

  it("names each sector's drivers, in the dollars the delta is made of", () => {
    // A sector total the reader cannot decompose is a number they have to take on
    // trust: -$70,000 in Communication Services is a different morning depending on
    // whether it is nine hundred names a few dollars out or one name that should not
    // be held at all. So the row names its own drivers.
    const facts = bookFacts(MORNING);
    render(<SnapshotView snapshot={MORNING} now={NOW} />);
    const rows = sectorDeltas(MORNING, facts.sectors);
    const worst = rows[0];
    expect(worst.label).toBe("Communication Services");

    const drivers = document.querySelector(
      `[data-drivers="${worst.code}"]`,
    ) as HTMLElement;
    expect(drivers).toBeTruthy();
    expect(drivers.textContent).toContain("of which WBD -$70,000 (held, not targeted)");

    // The other direction is named as the other direction: a name the target asks for
    // and the account does not hold is not the same finding as one held and dropped.
    const held = document.querySelector("[data-drivers='60']") as HTMLElement;
    expect(held.textContent).toContain("INVH +$20,000 (targeted, not held)");
    // A name both books carry is a drift, and is not given a one-sided class.
    const drift = document.querySelector("[data-drivers='45']") as HTMLElement;
    expect(drift.textContent).toContain("SMCI -$30,000");
    expect(drift.textContent).not.toContain("(");

    // The line is the row's own total decomposed, not a second opinion about it.
    for (const row of rows) {
      const line = document.querySelector(`[data-drivers="${row.code}"]`) as HTMLElement | null;
      if (!line) continue;
      const shown = row.drivers.reduce((total, driver) => total + driver.delta, 0);
      expect(shown, row.label).toBeCloseTo(row.delta, 6);
    }
  });

  it("puts the largest sector's own driver on the largest-difference line", () => {
    // The one line a reader takes without reading the panel: "Communication Services
    // -$7,598" says nothing about whether to act; "of which WBD -$7,057 (held, not
    // targeted)" says it.
    render(<SnapshotView snapshot={MORNING} now={NOW} />);
    const line = document.querySelector("[data-sector-largest='true']") as HTMLElement;
    expect(line.textContent).toContain(
      "largest difference: Communication Services -$70,000, of which WBD -$70,000 (held, not targeted)",
    );
    expect(line.textContent).toContain("of NAV");
  });

  it("says which read the difference is against", () => {
    render(<SnapshotView snapshot={MORNING} now={NOW} />);
    const section = document.querySelector("[data-section='sector']") as HTMLElement;
    expect(section.textContent).toContain("after the fills");
    document.body.innerHTML = "";
    const evening = {
      ...MORNING,
      actual_holdings: { ...MORNING.actual_holdings, read_by: "evening" },
    } as Snapshot;
    render(<SnapshotView snapshot={evening} now={NOW} />);
    const other = document.querySelector("[data-section='sector']") as HTMLElement;
    expect(other.textContent).toContain("before the orders went out");
  });

  it("renders Unmapped exactly for the names the bundled map does not carry", () => {
    const facts = bookFacts(OK);
    const unmapped = OK.book.names.filter((name) => sectorCodeFor(name.ticker) === null);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const row = document.querySelector("[data-sector='unmapped']");
    expect(row === null).toBe(unmapped.length === 0);
    if (unmapped.length > 0) {
      expect(row?.textContent).toContain(UNMAPPED);
      const bucket = facts.sectors.find((entry) => entry.code === null);
      expect(bucket?.nLong).toBe(unmapped.filter((name) => name.side === "long").length);
    }
  });
});

describe("the ten largest longs and shorts", () => {
  it("lists each side with its weight, its dollars and its reason", () => {
    const facts = bookFacts(OK);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    for (const [hook, names] of [
      ["longs", facts.topLongs],
      ["shorts", facts.topShorts],
    ] as const) {
      const panel = document.querySelector(`[data-top='${hook}']`) as HTMLElement;
      expect(panel).toBeTruthy();
      const rows = Array.from(panel.querySelectorAll("[data-ticker]")) as HTMLElement[];
      expect(rows.length).toBe(Math.min(10, names.length));
      rows.forEach((row, index) => {
        const name = names[index];
        expect(row.textContent).toContain(name.ticker);
        expect(row.textContent).toContain(percent(name.weight));
        expect(row.textContent).toContain(
          dollars(facts.nav === null ? null : Math.abs(name.weight ?? 0) * facts.nav),
        );
        expect(row.textContent).toContain(name.reason ?? "");
      });
    }
    // The sides do not overlap: a name appears on one list.
    const longs = facts.topLongs.map((name) => name.ticker);
    const shorts = facts.topShorts.map((name) => name.ticker);
    expect(longs.filter((ticker) => shorts.includes(ticker))).toEqual([]);
  });
});

describe("trades by reason", () => {
  it("counts the names and dollars the run recorded under each reason", () => {
    const facts = bookFacts(OK);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const table = screen.getByRole("table", { name: "trades by reason" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.length).toBe(facts.reasons.length);
    rows.forEach((row, index) => {
      const bucket = facts.reasons[index];
      expect(row.textContent).toContain(bucket.reason);
      expect(row.textContent).toContain(String(bucket.n));
      expect(row.textContent).toContain(dollars(bucket.notional));
    });
    const total = facts.reasons.reduce((sum, bucket) => sum + bucket.n, 0);
    expect(total).toBe(OK.book.names.length);
  });

  it("shows the dollars traded beside the dollars held, under each reason", () => {
    // The held column says what the run keeps under a reason and the traded column
    // says what it did about those names: without the second, the section cannot
    // answer the question it exists for, which is where the turnover came from.
    const facts = bookFacts(OK);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const table = screen.getByRole("table", { name: "trades by reason" });
    const headers = within(table).getAllByRole("columnheader").map((cell) => cell.textContent);
    expect(headers).toEqual(["reason", "names", "held", "traded"]);

    for (const bucket of facts.reasons) {
      const cell = document.querySelector(
        `[data-traded="${bucket.reason}"]`,
      ) as HTMLElement;
      expect(cell).toBeTruthy();
      expect(cell.textContent).toBe(dollars(bucket.traded));
    }
    // The traded column is the movement and the held column is the holding: on this
    // book the two differ, which is the point of printing both.
    const traded = facts.reasons.reduce((sum, bucket) => sum + bucket.traded, 0);
    const held = facts.reasons.reduce((sum, bucket) => sum + Math.abs(bucket.notional), 0);
    expect(traded).toBeGreaterThan(0);
    expect(traded).not.toBeCloseTo(held, 0);
  });

  it("keeps the traded column a movement, not a second holding", () => {
    // A name the run built no leg for is a zero in the traded column rather than a
    // copy of its weight: the bucket's traded dollars are the legs, absolute, so a
    // reason whose names were not traded reads as nothing traded there.
    const quiet: Snapshot = {
      ...OK,
      book: {
        ...OK.book,
        names: OK.book.names.map((name) => ({ ...name, traded_notional: 0 })),
      },
    };
    const facts = bookFacts(quiet);
    expect(facts.reasons.every((bucket) => bucket.traded === 0)).toBe(true);
    render(<SnapshotView snapshot={quiet} now={NOW} />);
    const table = screen.getByRole("table", { name: "trades by reason" });
    for (const bucket of facts.reasons) {
      const cell = document.querySelector(
        `[data-traded="${bucket.reason}"]`,
      ) as HTMLElement;
      expect(cell.textContent).toBe(dollars(0));
    }
    expect(within(table).getAllByRole("row").length).toBe(facts.reasons.length + 1);
  });

  it("reads a book published without the traded column as nothing traded", () => {
    // A document written before the column existed carries no traded dollars, and
    // the page must not invent them from the weights it does have.
    const older: Snapshot = {
      ...OK,
      book: {
        ...OK.book,
        names: OK.book.names.map(({ traded_notional: _drop, ...name }) => name),
      },
    };
    expect(bookFacts(older).reasons.every((bucket) => bucket.traded === 0)).toBe(true);
  });

  it("names the largest position on the metrics row", () => {
    // The list of ten largest names that used to sit beside this table is gone:
    // it repeated the top-names panels and the drawer's own sort. The largest
    // position is named once, on the metrics row, and the panels below carry the
    // names themselves.
    const facts = bookFacts(OK);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const card = document.querySelector("[data-card='largest-position']") as HTMLElement;
    expect(card.textContent).toContain(facts.largest?.ticker as string);
    expect(card.textContent).toContain(percent(facts.largest?.weight));
    expect(document.querySelector("[data-largest='names']")).toBeNull();
  });
});

describe("risk concentration", () => {
  it("is absent when the snapshot carries no per-name variance", () => {
    // Every fixture today. An empty section would say the risk is nowhere, which
    // is not the same statement as "the run has not written this yet".
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(document.querySelector("[data-section='risk']")).toBeNull();
  });

  it("draws each name's share with the cap as a line", () => {
    const snapshot: Snapshot = {
      ...OK,
      risk: {
        variance_share_cap: 0.1,
        concentration: [
          { ticker: "MRNA", share: 0.084 },
          { ticker: "LITE", share: 0.061 },
          { ticker: "MU", share: 0.042 },
        ],
      },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    openAttributionTab();
    const section = document.querySelector("[data-section='risk']") as HTMLElement;
    expect(section).toBeTruthy();
    expect(section.querySelectorAll("[data-concentration]").length).toBe(3);
    const line = section.querySelector("[data-cap-line='true']") as HTMLElement;
    expect(line).toBeTruthy();
    // The line sits at the cap on the same scale as the bars, so a bar past it
    // is a name the sizing cut back.
    const scale = 0.1 * 1.05;
    expect(parseFloat(line.style.left)).toBeCloseTo((0.1 / scale) * 100, 5);
    const bar = section.querySelector("[data-concentration='MRNA'] [data-share='name']") as HTMLElement;
    expect(parseFloat(bar.style.width)).toBeCloseTo((0.084 / scale) * 100, 5);
  });
});

describe("movers", () => {
  it("is absent when the snapshot carries no contributions", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(document.querySelector("[data-section='movers']")).toBeNull();
  });

  it("splits the session's contributions into five up and five down", () => {
    const byName = Array.from({ length: 14 }, (_, index) => ({
      ticker: `T${String(index).padStart(2, "0")}`,
      contribution: (index - 7) * 1000,
    }));
    const snapshot: Snapshot = {
      ...OK,
      movers: {
        session: "2026-09-21T00:00:00",
        by_name: byName,
        by_sector: [
          { sector: "Utilities", contribution: 4200 },
          { sector: "Energy", contribution: -3100 },
        ],
      },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    openAttributionTab();
    const section = document.querySelector("[data-section='movers']") as HTMLElement;
    expect(section).toBeTruthy();
    // The best five and the worst five of fourteen, and no name in both.
    const up = document.querySelector("[data-movers='names, top five']") as HTMLElement;
    const down = document.querySelector("[data-movers='names, bottom five']") as HTMLElement;
    expect(up.querySelectorAll("[data-contributor]").length).toBe(5);
    expect(down.querySelectorAll("[data-contributor]").length).toBe(5);
    expect(up.textContent).toContain("T13");
    expect(down.textContent).toContain("T00");
    const names = [...up.querySelectorAll("[data-contributor]")].map((row) => row.getAttribute("data-contributor"));
    const others = [...down.querySelectorAll("[data-contributor]")].map((row) => row.getAttribute("data-contributor"));
    expect(names.filter((name) => others.includes(name))).toEqual([]);
    // Contributions are dollars and keep their sign.
    expect(up.textContent).toContain(signedDollars(6000));
    expect(section.textContent).toContain("Energy");
  });
});

describe("the detail drawer", () => {
  it("is shut by default, and names both tables and their row counts", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const drawer = document.querySelector("[data-section='drawer']") as HTMLElement;
    expect(drawer).toBeTruthy();
    expect(drawer.getAttribute("data-drawer")).toBe("closed");
    // Neither table is in the document until it is asked for: 188 rows of book
    // above the fold is a screen nobody reads.
    expect(document.querySelector("[data-section='holdings']")).toBeNull();
    expect(
      drawer.querySelector("[data-tab='book']")?.textContent,
    ).toContain(`${OK.book.names.length} name`);
    // This fixture has no account block, so there is no second tab to open.
    expect(drawer.querySelector("[data-tab='actual']")).toBeNull();
  });

  it("opens a table when its tab is asked for, and shuts again", () => {
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    const drawer = document.querySelector("[data-section='drawer']") as HTMLElement;
    expect(drawer.querySelectorAll("[data-tab]").length).toBe(2);
    const book = openDrawer("book");
    expect(book).toBeTruthy();
    expect(drawer.getAttribute("data-drawer")).toBe("open");
    expect(document.querySelector("[data-section='actual-holdings']")).toBeNull();
    // One tab at a time: asking for the other one closes this one.
    fireEvent.click(drawer.querySelector("[data-tab='actual']") as HTMLElement);
    expect(document.querySelector("[data-section='holdings']")).toBeNull();
    expect(document.querySelector("[data-section='actual-holdings']")).toBeTruthy();
    // And asking for the open one again closes the drawer.
    fireEvent.click(drawer.querySelector("[data-tab='actual']") as HTMLElement);
    expect(drawer.getAttribute("data-drawer")).toBe("closed");
  });

  it("starts the book in the snapshot's own order, then sorts on any column", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const book = openDrawer("book");
    const first = (): string | null =>
      book.querySelector("tbody [data-ticker]")?.getAttribute("data-ticker") ?? null;
    expect(first()).toBe(OK.book.names[0].ticker);
    const ascending = [...OK.book.names]
      .map((name) => name.ticker)
      .sort((a, b) => a.localeCompare(b))[0];
    fireEvent.click(book.querySelector("[data-sort='ticker']") as HTMLElement);
    expect(first()).toBe(ascending);
    // The weight column sorts on the absolute value, and a first click on a
    // numeric column sorts descending: the heaviest position comes first.
    const heaviest = [...OK.book.names].sort(
      (a, b) => Math.abs(b.weight ?? 0) - Math.abs(a.weight ?? 0),
    )[0].ticker;
    fireEvent.click(book.querySelector("[data-sort='weight']") as HTMLElement);
    expect(first()).toBe(heaviest);
  });

  it("filters by sector and searches the drawer's one box, and counts what it shows", () => {
    const facts = bookFacts(OK);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const book = openDrawer("book");
    const count = (): string => book.querySelector("[data-count='shown']")?.textContent ?? "";
    expect(count()).toContain(`of ${OK.book.names.length}`);

    const bucket = facts.sectors.find((entry) => (entry.nLong + entry.nShort) > 2) as {
      label: string;
      nLong: number;
      nShort: number;
    };
    fireEvent.change(within(book).getByLabelText("sector filter"), {
      target: { value: bucket.label },
    });
    expect(count()).toContain(`showing ${bucket.nLong + bucket.nShort} `);
    const rows = book.querySelectorAll("tbody [data-ticker]");
    expect(rows.length).toBe(bucket.nLong + bucket.nShort);

    // The two filters combine, so the search starts from every sector again. The
    // search box is the drawer's own, shared by both tabs.
    fireEvent.change(within(book).getByLabelText("sector filter"), {
      target: { value: "all" },
    });
    const wanted = OK.book.names[3].ticker;
    const drawer = document.querySelector("[data-section='drawer']") as HTMLElement;
    fireEvent.change(within(drawer).getByLabelText("ticker search"), {
      target: { value: wanted.toLowerCase() },
    });
    expect(count()).toContain("showing 1 ");
    expect(book.querySelector("tbody [data-ticker]")?.getAttribute("data-ticker")).toBe(
      wanted,
    );
  });

  it("names the sector of every row from the bundled map", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const book = openDrawer("book");
    for (const name of OK.book.names.slice(0, 12)) {
      const row = book.querySelector(`[data-ticker='${name.ticker}']`) as HTMLElement;
      const cells = Array.from(row.querySelectorAll("td")).map((cell) => cell.textContent);
      expect(cells[2]).toBe(sectorLabel(sectorCodeFor(name.ticker)));
    }
  });
});

describe("actual holdings", () => {
  const section = (): HTMLElement =>
    document.querySelector("[data-section='actual-holdings']") as HTMLElement;

  it("draws the account's own book, whose read it was and the fill misses", () => {
    const block = ACTUAL.actual_holdings;
    expect(block).toBeTruthy();
    if (!block) return;
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);

    // The tab names the table and counts it, so the count is readable without
    // opening 235 rows.
    expect(screen.getByText(`Actual holdings: ${block.n_names} name(s)`)).toBeTruthy();
    const table = openDrawer("actual");
    // The read time, as a time: the evening's read and the morning's are hours
    // apart and the difference is the whole meaning of the label.
    expect(table.querySelector("[data-actual='read']")?.textContent).toContain(
      "read at 2026-09-22 15:30 UTC",
    );
    expect(table.querySelector("[data-actual='read']")?.textContent).toContain(
      `at the ${block.read_by} run`,
    );
    expect(table.querySelector("[data-actual='read']")?.textContent).toContain(
      `for the ${dateOnly(block.close)} close`,
    );
    expect(table.querySelectorAll("tbody [data-ticker]").length).toBeGreaterThan(0);

    // The fills summary is on the metrics row, filled of sent and realized against
    // expected, and the misses are their own strip with a line each, because the
    // count alone leaves the reader to open the store to find out which leg.
    const fills = block.fills;
    expect(fills).toBeTruthy();
    if (!fills) return;
    const card = document.querySelector("[data-card='fills']") as HTMLElement;
    expect(card.textContent).toContain(`${fills.n_filled} of ${fills.n_orders} filled`);
    expect(card.textContent).toContain(
      `${fills.not_sent} never sent, ${fills.n_unfilled} did not fill`,
    );
    expect(card.textContent).toContain(
      `realized ${(fills.realized_cost_bps as number).toFixed(2)}`,
    );
    expect(card.textContent).toContain("against");
    const misses = document.querySelector("[data-fills='misses']") as HTMLElement;
    expect(misses).toBeTruthy();
    expect(misses.getAttribute("data-tone")).toBe("warn");
    for (const line of fills.unfilled) expect(misses.textContent).toContain(line);
  });

  it("carries one row per name in the held book and per target it does not hold", () => {
    const block = ACTUAL.actual_holdings;
    expect(block).toBeTruthy();
    if (!block) return;
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    openDrawer("actual");
    const rows = section();

    const held = new Set(block.names.map((entry) => entry.ticker));
    const missing = ACTUAL.book.names.filter((name) => !held.has(name.ticker));
    expect(rows.querySelectorAll("tbody [data-ticker]").length).toBe(
      block.n_names + missing.length,
    );
    expect(rows.querySelectorAll("tbody [data-held='false']").length).toBe(
      missing.length,
    );
    // The two books genuinely differ, or this section would have nothing to say.
    expect(missing.length).toBeGreaterThan(0);
    expect(block.n_names).toBeLessThan(ACTUAL.book.n_names);
    // A name the account does not hold says so rather than printing 0.00%.
    const notHeld = rows.querySelector("tbody [data-held='false']") as HTMLElement;
    expect(notHeld.textContent).toContain("not held");
    expect(notHeld.textContent).not.toContain("0.00%");
    // The count line names both directions. The held names that are in the target
    // are the union's intersection, which the section derives itself.
    expect(rows.querySelector("[data-actual='unheld']")?.textContent).toContain(
      `${missing.length} of the target book's ${ACTUAL.book.n_names} name(s) are not held`,
    );
  });

  it("reports a held position against its target weight, in both units", () => {
    const block = ACTUAL.actual_holdings;
    expect(block).toBeTruthy();
    if (!block) return;
    const facts = bookFacts(ACTUAL);
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    openDrawer("actual");
    const rows = section();

    const cellsFor = (ticker: string): Array<string | null> => {
      const row = rows.querySelector(`tbody [data-ticker='${ticker}']`) as HTMLElement;
      return Array.from(row.querySelectorAll("td")).map((cell) => cell.textContent);
    };

    // A name in both books: the section says what is held against what the target
    // asked for, in weights and in dollars.
    const held = new Set(block.names.map((entry) => entry.ticker));
    const shared = block.names.find((entry) =>
      ACTUAL.book.names.some((name) => name.ticker === entry.ticker),
    );
    expect(shared).toBeTruthy();
    if (!shared) return;
    const target = ACTUAL.book.names.find((name) => name.ticker === shared.ticker);
    const sharedCells = cellsFor(shared.ticker);
    expect(sharedCells[2]).toBe(percent(shared.weight));
    expect(sharedCells[3]).toBe(dollars(shared.notional));
    expect(sharedCells[4]).toBe(percent(target?.weight ?? null));
    expect(sharedCells[5]).toBe(dollars((target?.weight as number) * (facts.nav as number)));
    expect(sharedCells[6]).toBe(
      signedPercent((shared.weight ?? 0) - (target?.weight as number)),
    );

    // A name the account holds and the target does not: the target columns are
    // absent rather than zero, and the drift is the whole position.
    const onlyHeld = block.names.find((entry) => !ACTUAL.book.names.some((name) => name.ticker === entry.ticker));
    expect(onlyHeld).toBeTruthy();
    if (!onlyHeld) return;
    const heldCells = cellsFor(onlyHeld.ticker);
    expect(heldCells[4]).toBe("n/a");
    expect(heldCells[5]).toBe("n/a");
    expect(heldCells[6]).toBe(signedPercent(onlyHeld.weight));
  });

  it("sorts on every column, by absolute size for the money and the weights", () => {
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    openDrawer("actual");
    const rows = section();
    const ordered = (): string[] =>
      Array.from(rows.querySelectorAll("tbody [data-ticker]")).map(
        (row) => row.getAttribute("data-ticker") ?? "",
      );
    const before = ordered();

    fireEvent.click(rows.querySelector("[data-sort='ticker']") as HTMLElement);
    expect(ordered()).toEqual([...before].sort((a, b) => a.localeCompare(b)));
    fireEvent.click(rows.querySelector("[data-sort='ticker']") as HTMLElement);
    expect(ordered()).toEqual([...before].sort((a, b) => b.localeCompare(a)));

    // A weight or a dollar column sorts by size, so a 5% short ranks with a 5%
    // long: the reader is asking which positions matter.
    fireEvent.click(rows.querySelector("[data-sort='heldDollars']") as HTMLElement);
    const sizes = ordered().map((ticker) => {
      const entry = ACTUAL.actual_holdings?.names.find((name) => name.ticker === ticker);
      return Math.abs(entry?.notional ?? 0);
    });
    expect(sizes).toEqual([...sizes].sort((a, b) => b - a));
  });

  it("says the account was not read rather than drawing an empty book", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(OK.actual_holdings).toBeUndefined();
    // One line, in the strip, where it is visible without opening a drawer: a
    // table of no rows reads as an account holding nothing.
    expect(document.querySelector("[data-note='account']")?.textContent).toContain(
      "the account has not been read",
    );
    const drawer = document.querySelector("[data-section='drawer']") as HTMLElement;
    expect(drawer.querySelector("[data-tab='actual']")).toBeNull();
    expect(section()).toBeNull();
  });

  it("distinguishes the evening's own read from a day on which nothing filled", () => {
    // The evening reads the account before it sends anything, so its block has no
    // fills and no close: the orders it sized from have not settled. A page that
    // read the absent block as "0 filled" would report the evening as a day the
    // market did not fill anything.
    const snapshot: Snapshot = {
      ...ACTUAL,
      actual_holdings: {
        ...(ACTUAL.actual_holdings as NonNullable<Snapshot["actual_holdings"]>),
        read_by: "evening",
        close: null,
        fills: null,
      },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);

    const summary = document.querySelector("[data-card='fills']") as HTMLElement;
    expect(summary.textContent).toContain("none to reconcile yet");
    expect(summary.textContent).toContain("before the orders went out");
    expect(summary.textContent).not.toContain("0 filled");
    const read = openDrawer("actual");
    expect(read.textContent).toContain("at the evening run");
    // No close is claimed: nothing has settled into a book read before the
    // orders went out.
    expect(read.textContent).not.toContain("close");
  });

  it("renders the read time as a time, never as a bare ISO stamp", () => {
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    const read = openDrawer("actual");
    expect(document.body.textContent ?? "").not.toContain("T00:00:00");
    expect(read.textContent).toContain("2026-09-22 15:30 UTC");
  });
});

describe("a snapshot with no book", () => {
  it("hides every section that needs the book rather than drawing it empty", () => {
    const snapshot: Snapshot = NONE;
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    expect(snapshot.book.n_names).toBe(0);
    expect(snapshot.book.reason).toBeTruthy();
    expect(document.querySelector("[data-section='sector']")).toBeNull();
    expect(document.querySelector("[data-section='top-names']")).toBeNull();
    expect(document.querySelector("[data-section='reasons']")).toBeNull();
    expect(document.querySelector("[data-section='exposures']")).toBeNull();
    expect(document.querySelector("[data-section='risk']")).toBeNull();
    expect(document.querySelector("[data-section='movers']")).toBeNull();
    // No book and no account read is nothing to put in a drawer, so there is no
    // drawer: an empty one would say the book is flat.
    expect(document.querySelector("[data-section='drawer']")).toBeNull();
    expect(document.querySelector("[data-section='holdings']")).toBeNull();
  });

  it("keeps the metrics row, and every value in it says n/a", () => {
    const snapshot: Snapshot = NONE;
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const cards = document.querySelector("[data-cards='true']") as HTMLElement;
    // The row is the page's shape, so it stays; what it must not do is invent a
    // zero for a book that was never priced.
    expect(cards).toBeTruthy();
    const card = (label: string): HTMLElement =>
      cards.querySelector(`[data-card="${label}"]`) as HTMLElement;
    for (const label of [
      "gross",
      "net",
      "long-names",
      "short-names",
      "n_eff_kept",
      "turnover",
      "largest-position",
      "expected-expense",
      "top10-share",
      "n_eff_full_book",
      "full-book-gross",
      "full-book-net",
      "full-book-vol",
    ]) {
      expect(card(label), label).toBeTruthy();
      expect(card(label).textContent, label).toContain("n/a");
    }
    expect(cards.querySelector("[data-card='fills']")).toBeNull();
  });

  it("says why the book is empty, and shouts about the run", () => {
    render(<SnapshotView snapshot={NONE} now={NOW} />);
    expect(screen.getByText(new RegExp(`no book: ${NONE.book.reason}`))).toBeTruthy();
    expect(screen.getByRole("alert")).toBeTruthy();
    // Nothing on the page claims a flat book: no zero dollars and no zero share.
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("$0");
    expect(text).not.toContain("0.00%");
    expect(text).not.toContain("T00:00:00");
  });
});

describe("the hedge's footprint", () => {
  const moved = OK.book.names.filter((name) => name.reason === "the hedge moved");
  const SHARES = [
    { ticker: "SMCI", variance_share: 0.14197 },
    { ticker: "WDC", variance_share: 0.06447 },
    { ticker: "INTC", variance_share: 0.04605 },
  ];
  const withRisk = (snapshot: Snapshot): Snapshot => ({
    ...snapshot,
    reconciliation: {
      ...snapshot.reconciliation,
      traded_risk: {
        forecast_annual_vol: 0.02765,
        gross: 1.0,
        n_eff: 122.88,
        max_weight: 0.01793,
        top_variance_shares: SHARES,
      },
    },
  });

  it("states how many names the hedge moved, and the legs it built for them", () => {
    expect(moved.length).toBeGreaterThan(0);
    render(<SnapshotView snapshot={withRisk(OK)} now={NOW} />);
    const panel = document.querySelector("[data-section='hedge']") as HTMLElement;
    expect(panel).toBeTruthy();
    // Counted from the book's own reason column rather than typed, so a
    // regenerated fixture cannot leave this asserting a number nobody wrote.
    expect(panel.textContent).toContain(`${moved.length} of ${OK.book.names.length}`);
    const notional = moved.reduce(
      (total, name) => total + Math.abs(name.traded_notional ?? 0),
      0,
    );
    expect(panel.textContent).toContain(dollars(notional));
    // The label says which claim is the proxy: the reason is the loop's own
    // record, and what it cannot say is that the hedge created the position.
    expect(panel.textContent).toContain("A proxy.");
    expect(panel.textContent).toContain("pre-hedge and post-hedge target");
  });

  it("draws the concentration behind the hedge from the reconciliation's own shares", () => {
    render(<SnapshotView snapshot={withRisk(OK)} now={NOW} />);
    const shares = document.querySelector("[data-details='hedge-shares']") as HTMLElement;
    expect(shares).toBeTruthy();
    for (const entry of SHARES) {
      const row = document.querySelector(
        `[data-variance-share='${entry.ticker}']`,
      ) as HTMLElement;
      expect(row).toBeTruthy();
      expect(row.textContent).toContain(percent(entry.variance_share, 2));
    }
    // The largest share is stated in the summary, so collapsing the disclosure
    // cannot hide the one number it exists to show.
    const summary = shares.querySelector("summary") as HTMLElement;
    expect(summary.textContent).toContain(SHARES[0].ticker);
    expect(summary.textContent).toContain(percent(SHARES[0].variance_share, 1));
  });

  it("says the shares are absent rather than drawing a share of nothing", () => {
    // The fixture carries no traded risk, which is the state a close whose
    // reconciliation did not run leaves behind.
    expect(OK.reconciliation?.traded_risk ?? null).toBeNull();
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(document.querySelector("[data-details='hedge-shares']")).toBeNull();
    const absent = document.querySelector("[data-hedge-shares='absent']") as HTMLElement;
    expect(absent).toBeTruthy();
    expect(absent.textContent).toContain("not shown rather than drawn as zero");
  });
});

describe("the names the risk model could not measure", () => {
  it("lists them, with the reason each left, under the construction telemetry", () => {
    const snapshot: Snapshot = {
      ...OK,
      breadth: {
        ...OK.breadth,
        n_dropped_no_risk: 3,
        dropped_no_risk: [
          { ticker: "AAA", reason: "no specific variance" },
          { ticker: "BBB", reason: "no specific variance" },
          { ticker: "CCC", reason: "short history" },
        ],
      },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const line = document.querySelector("[data-flag='dropped-no-risk']") as HTMLElement;
    expect(line).toBeTruthy();
    expect(line.textContent).toContain("3 name(s) never reached the book");
    expect(line.textContent).toContain("AAA (no specific variance)");
    expect(line.textContent).toContain("CCC (short history)");
  });

  it("draws nothing when the document carries none, old or empty alike", () => {
    // Absent is a document written before the evening published them; an empty list is
    // an evening that dropped none. Both mean the reader has nothing to see here.
    const { n_dropped_no_risk: _count, dropped_no_risk: _names, ...restBreadth } = OK.breadth;
    render(
      <SnapshotView snapshot={{ ...OK, breadth: restBreadth as typeof OK.breadth }} now={NOW} />,
    );
    expect(document.querySelector("[data-flag='dropped-no-risk']")).toBeNull();
    const empty: Snapshot = {
      ...OK,
      breadth: { ...OK.breadth, n_dropped_no_risk: 0, dropped_no_risk: [] },
    };
    render(<SnapshotView snapshot={empty} now={NOW} />);
    expect(document.querySelector("[data-flag='dropped-no-risk']")).toBeNull();
  });
});

describe("the turnover card", () => {
  it("reads every leg the evening built, and says so beside the per-name column", () => {
    const intended = 379430.49;
    const snapshot: Snapshot = {
      ...OK,
      reconciliation: { ...OK.reconciliation, intended_notional: intended },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const card = document.querySelector("[data-card='turnover']") as HTMLElement;
    const nav = (OK.book.gross_notional as number) / (OK.book.gross as number);
    expect(card.textContent).toContain(percent(intended / nav));
    expect(card.textContent).toContain(dollars(intended));
    // The distinction the correction rests on: the per-name column drops the legs
    // of names that left the book, so the two numbers must not be conflated.
    const note = document.querySelector("[data-flag='turnover-note']") as HTMLElement;
    expect(note.textContent).toContain("reconciliation.intended_notional");
    expect(note.textContent).toContain("predates the sent-only key");
  });

  it("stands on the legs sent once the document carries them, and keeps the built figure", () => {
    // 2026-10-09's own pair: $379,430.49 sent against $388,402.25 built, of which
    // $8,971.76 was never sent. The card must read the first, which is turnover.
    const built = 388402.25;
    const sent = 379430.49;
    const snapshot: Snapshot = {
      ...OK,
      reconciliation: {
        ...OK.reconciliation,
        intended_notional: built,
        sent_notional: sent,
        unsent_notional: built - sent,
      },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const card = document.querySelector("[data-card='turnover']") as HTMLElement;
    const nav = (OK.book.gross_notional as number) / (OK.book.gross as number);
    expect(card.textContent).toContain("legs sent");
    expect(card.textContent).toContain(percent(sent / nav));
    expect(card.textContent).toContain(dollars(sent));
    expect(card.textContent).toContain(dollars(built));
    expect(card.textContent).toContain("$8,972 was never sent");
    expect(card.textContent).not.toContain(percent(built / nav));
    const note = document.querySelector("[data-flag='turnover-note']") as HTMLElement;
    expect(note.textContent).toContain("reconciliation.sent_notional");
    expect(note.textContent).toContain("broker was sent");
    expect(note.textContent).not.toContain("predates the sent-only key");
  });

  it("says n/a when the reconciliation carries no intended notional", () => {
    expect(OK.reconciliation?.intended_notional ?? null).toBeNull();
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const card = document.querySelector("[data-card='turnover']") as HTMLElement;
    expect(card.textContent).toContain("n/a");
    expect(card.textContent).toContain("no notional for this close");
    // And no fabricated zero beside it.
    expect(document.querySelector("[data-flag='turnover-note']")?.textContent).not.toContain(
      "totals $0",
    );
  });
});

describe("the attribution tab's own panels", () => {
  const BY_FACTOR = { market: 5.9e-18, size: -0.0006073612, beta: 2.56e-5, momentum: 3.2e-5 };
  /** The fixture's live period, which is the block both panels read. */
  const LIVE = OK.attribution?.live as AttributionPeriod;
  const withLive = (live: AttributionPeriod): Snapshot => ({
    ...OK,
    attribution: { ...(OK.attribution as NonNullable<Snapshot["attribution"]>), live },
  });
  const withFactors = withLive({ ...LIVE, by_factor: BY_FACTOR });

  it("adds the factors up to the factor card, largest contribution first", () => {
    render(<SnapshotView snapshot={withFactors} now={NOW} />);
    openAttributionTab();
    const panel = document.querySelector("[data-panel='by-factor']") as HTMLElement;
    expect(panel).toBeTruthy();
    const order = Array.from(panel.querySelectorAll("[data-factor]")).map((row) =>
      row.getAttribute("data-factor"),
    );
    expect(order).toEqual([
      ...Object.entries(BY_FACTOR)
        .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
        .map(([name]) => name),
      "total",
    ]);
    for (const [factor, value] of Object.entries(BY_FACTOR)) {
      const row = panel.querySelector(`[data-factor='${factor}']`) as HTMLElement;
      expect(row.textContent).toContain((value * 1e4).toFixed(1));
    }
    const total = Object.values(BY_FACTOR).reduce((sum, value) => sum + value, 0);
    expect(
      (panel.querySelector("[data-factor='total']") as HTMLElement).textContent,
    ).toContain((total * 1e4).toFixed(1));
  });

  it("is absent when the document carries no by-factor split", () => {
    expect(Object.keys(LIVE.by_factor).length).toBe(0);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    openAttributionTab();
    expect(document.querySelector("[data-panel='by-factor']")).toBeNull();
  });

  it("puts realized beside forecast volatility, and counts the sessions", () => {
    const daily = LIVE.daily;
    const both = daily.filter(
      (day) => day.realized_vol != null && day.forecast_vol != null,
    );
    // The fixture deliberately has a session with no forecast, which is the case
    // the count exists for.
    expect(both.length).toBeLessThan(daily.length);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    openAttributionTab();
    const panel = document.querySelector("[data-panel='volatility']") as HTMLElement;
    expect(panel.textContent).toContain(`${both.length} of ${daily.length} session(s) carry both`);
    expect(panel.querySelector("svg")).toBeTruthy();
    // A session with no forecast is a gap, never a zero.
    expect(panel.textContent).not.toContain("0.00% realized");
  });

  it("says no session has a realized volatility yet rather than drawing zero", () => {
    const none = withLive({
      ...LIVE,
      daily: LIVE.daily.map((day) => ({ ...day, realized_vol: null })),
    });
    render(<SnapshotView snapshot={none} now={NOW} />);
    openAttributionTab();
    const panel = document.querySelector("[data-panel='volatility']") as HTMLElement;
    expect(panel).toBeTruthy();
    expect(panel.textContent).toContain("no session of this period carries a realized volatility");
    expect(panel.querySelector("svg")).toBeNull();
  });
});
