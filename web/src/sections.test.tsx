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
import { dateOnly, dollars, percent, signedDollars, signedPercent } from "./format";
import { sectorCodeFor, sectorLabel, UNMAPPED } from "./sectors";
import type { Snapshot } from "./types";
import noBook from "../fixtures/snapshot_no_book.json";
import ok from "../fixtures/snapshot_ok.json";
import withActual from "../fixtures/snapshot_actual_holdings.json";

const OK = ok as unknown as Snapshot;
const NONE = noBook as unknown as Snapshot;
const ACTUAL = withActual as unknown as Snapshot;
const NOW = new Date("2026-09-21T23:00:00Z");

describe("the summary cards", () => {
  it("states the counts, the dollars, the breadth, the largest name and the cost", () => {
    const facts = bookFacts(OK);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const cards = document.querySelector("[data-cards='true']") as HTMLElement;
    expect(cards).toBeTruthy();
    const card = (label: string): HTMLElement =>
      cards.querySelector(`[data-card="${label}"]`) as HTMLElement;

    expect(card("long names").textContent).toContain(String(facts.nLong));
    expect(card("short names").textContent).toContain(String(facts.nShort));
    expect(card("long dollars").textContent).toContain(dollars(facts.longNotional));
    expect(card("short dollars").textContent).toContain(dollars(facts.shortNotional));
    expect(card("net dollars").textContent).toContain(signedDollars(facts.netNotional));
    expect(card("n_eff kept").textContent).toContain(
      (OK.breadth.n_eff_kept as number).toFixed(1),
    );
    expect(card("largest position").textContent).toContain(facts.largest?.ticker as string);
    // The ten largest weights as a share of the book's absolute weight.
    expect(card("top 10 share of gross").textContent).toContain(percent(facts.top10Share));
    expect(card("expected cost").textContent).toContain(
      (OK.book.expected_cost_bps as number).toFixed(2),
    );
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
  it("draws a row per sector the book holds, long to the right and short to the left", () => {
    const facts = bookFacts(OK);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const section = document.querySelector("[data-section='sector']") as HTMLElement;
    expect(section).toBeTruthy();
    expect(facts.sectors.length).toBeGreaterThan(1);
    for (const bucket of facts.sectors) {
      const key = bucket.code === null ? "unmapped" : String(bucket.code);
      const row = section.querySelector(`[data-sector="${key}"]`) as HTMLElement;
      expect(row, `no row for ${bucket.label}`).toBeTruthy();
      expect(row.querySelector("[data-side='long']")).toBeTruthy();
      expect(row.querySelector("[data-side='short']")).toBeTruthy();
      expect(row.querySelector("[data-counts='names']")?.textContent).toContain(
        `${bucket.nLong}L`,
      );
      expect(row.querySelector("[data-net='sector']")?.textContent).toContain(
        signedDollars(bucket.netNotional),
      );
    }
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
    expect(row.querySelector("[data-counts='names']")?.textContent).toContain("1L");
    const holdings = document.querySelector("[data-holdings='true']") as HTMLElement;
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

  it("puts the largest side on the page at half the track, so the bars share one scale", () => {
    const facts = bookFacts(OK);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const bars = Array.from(
      document.querySelectorAll("[data-side='long'], [data-side='short']"),
    ) as HTMLElement[];
    expect(bars.length).toBeGreaterThan(0);
    const widths = bars.map((bar) => parseFloat(bar.style.width));
    expect(Math.max(...widths)).toBeCloseTo(50, 5);
    const largest = Math.max(
      ...facts.sectors.map((bucket) => Math.max(bucket.longNotional, bucket.shortNotional)),
    );
    const smallest = Math.min(
      ...facts.sectors.map((bucket) => Math.max(bucket.longNotional, bucket.shortNotional)),
    );
    expect(Math.min(...widths)).toBeCloseTo((smallest / largest) * 50, 5);
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

  it("names the ten largest positions beside it", () => {
    const facts = bookFacts(OK);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const panel = document.querySelector("[data-largest='names']") as HTMLElement;
    const rows = Array.from(panel.querySelectorAll("[data-ticker]")) as HTMLElement[];
    expect(rows.length).toBe(Math.min(10, OK.book.names.length));
    expect(rows[0].textContent).toContain(facts.largestNames[0].ticker);
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

describe("the full holdings table", () => {
  it("is collapsed by default", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const details = document.querySelector("[data-holdings='true']") as HTMLDetailsElement;
    expect(details).toBeTruthy();
    expect(details.open).toBe(false);
    expect(details.querySelector("summary")?.textContent).toContain(
      `${OK.book.names.length} name`,
    );
  });

  it("starts in the snapshot's own order, then sorts on any column", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const details = document.querySelector("[data-holdings='true']") as HTMLElement;
    const first = (): string | null =>
      details.querySelector("tbody [data-ticker]")?.getAttribute("data-ticker") ?? null;
    expect(first()).toBe(OK.book.names[0].ticker);
    const ascending = [...OK.book.names]
      .map((name) => name.ticker)
      .sort((a, b) => a.localeCompare(b))[0];
    fireEvent.click(details.querySelector("[data-sort='ticker']") as HTMLElement);
    expect(first()).toBe(ascending);
    // The weight column sorts on the absolute value, and a first click on a
    // numeric column sorts descending: the heaviest position comes first.
    const heaviest = [...OK.book.names].sort(
      (a, b) => Math.abs(b.weight ?? 0) - Math.abs(a.weight ?? 0),
    )[0].ticker;
    fireEvent.click(details.querySelector("[data-sort='weight']") as HTMLElement);
    expect(first()).toBe(heaviest);
  });

  it("filters by sector and searches by ticker, and says how many it is showing", () => {
    const facts = bookFacts(OK);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const details = document.querySelector("[data-holdings='true']") as HTMLElement;
    const count = (): string =>
      details.querySelector("[data-count='shown']")?.textContent ?? "";
    expect(count()).toContain(`of ${OK.book.names.length}`);

    const bucket = facts.sectors.find((entry) => (entry.nLong + entry.nShort) > 2) as {
      label: string;
      nLong: number;
      nShort: number;
    };
    fireEvent.change(within(details as HTMLElement).getByLabelText("sector filter"), {
      target: { value: bucket.label },
    });
    expect(count()).toContain(`showing ${bucket.nLong + bucket.nShort} `);
    const rows = details.querySelectorAll("tbody [data-ticker]");
    expect(rows.length).toBe(bucket.nLong + bucket.nShort);

    // The two filters combine, so the search starts from every sector again.
    fireEvent.change(within(details as HTMLElement).getByLabelText("sector filter"), {
      target: { value: "all" },
    });
    const wanted = OK.book.names[3].ticker;
    fireEvent.change(within(details as HTMLElement).getByLabelText("ticker search"), {
      target: { value: wanted.toLowerCase() },
    });
    expect(count()).toContain("showing 1 ");
    expect(details.querySelector("tbody [data-ticker]")?.getAttribute("data-ticker")).toBe(
      wanted,
    );
  });

  it("names the sector of every row from the bundled map", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const details = document.querySelector("[data-holdings='true']") as HTMLElement;
    for (const name of OK.book.names.slice(0, 12)) {
      const row = details.querySelector(`[data-ticker='${name.ticker}']`) as HTMLElement;
      const cells = Array.from(row.querySelectorAll("td")).map((cell) => cell.textContent);
      expect(cells[2]).toBe(sectorLabel(sectorCodeFor(name.ticker)));
    }
  });
});

describe("actual holdings", () => {
  const section = (): HTMLElement =>
    document.querySelector("[data-section='actual-holdings']") as HTMLElement;

  it("draws the account's own book, its read time and the fills behind it", () => {
    const block = ACTUAL.actual_holdings;
    expect(block).toBeTruthy();
    if (!block) return;
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);

    expect(screen.getByText(`Actual holdings: ${block.n_names} names`)).toBeTruthy();
    // The read time, as a time: the evening's read and the morning's are hours
    // apart and the difference is the whole meaning of the label.
    expect(section().textContent).toContain("read at 2026-09-22 15:30 UTC");
    expect(section().textContent).toContain(`at the ${block.read_by} run`);
    expect(section().textContent).toContain(`for the ${dateOnly(block.close)} close`);
    // Long and short gross are summed from the block's own notionals, not from the
    // block's precomputed pair: the table's rows and these lines cannot disagree.
    const long = block.names
      .filter((entry) => (entry.notional ?? 0) > 0)
      .reduce((total, entry) => total + (entry.notional ?? 0), 0);
    const short = block.names
      .filter((entry) => (entry.notional ?? 0) < 0)
      .reduce((total, entry) => total - (entry.notional ?? 0), 0);
    expect(section().textContent).toContain(dollars(long));
    expect(section().textContent).toContain(dollars(short));
    expect(section().textContent).toContain(dollars(block.net_notional));
    expect(long + short).toBeCloseTo(block.gross_notional as number, 6);
    const fills = block.fills;
    expect(fills).toBeTruthy();
    if (!fills) return;
    const summary = section().querySelector("[data-fills='summary']") as HTMLElement;
    expect(summary.textContent).toContain(`${fills.n_filled} filled`);
    expect(summary.textContent).toContain(`${fills.n_unfilled} did not fill`);
    expect(summary.textContent).toContain(`${fills.not_sent} never sent`);
    expect(fills.realized_cost_bps).not.toBeNull();
    expect(summary.textContent).toContain(
      `realized ${(fills.realized_cost_bps as number).toFixed(2)} bps`,
    );
    // And the legs behind the count, in the email's own wording.
    const misses = section().querySelector("[data-fills='misses']") as HTMLElement;
    for (const line of fills.unfilled) expect(misses.textContent).toContain(line);
  });

  it("carries one row per name in the held book and per target it does not hold", () => {
    const block = ACTUAL.actual_holdings;
    expect(block).toBeTruthy();
    if (!block) return;
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);

    const rows = section().querySelectorAll("tbody [data-ticker]");
    const held = new Set(block.names.map((entry) => entry.ticker));
    const missing = ACTUAL.book.names.filter((name) => !held.has(name.ticker));
    expect(rows.length).toBe(block.n_names + missing.length);
    expect(section().querySelectorAll("tbody [data-held='false']").length).toBe(
      missing.length,
    );
    // The two books genuinely differ, or this section would have nothing to say.
    expect(missing.length).toBeGreaterThan(0);
    expect(block.n_names).toBeLessThan(ACTUAL.book.n_names);
    // A name the account does not hold says so rather than printing 0.00%.
    const notHeld = section().querySelector("tbody [data-held='false']") as HTMLElement;
    expect(notHeld.textContent).toContain("not held");
    expect(notHeld.textContent).not.toContain("0.00%");
    // The count line names both directions. The held names that are in the target
    // are the union's intersection, which the section derives itself.
    expect(section().querySelector("[data-actual='unheld']")?.textContent).toContain(
      `${missing.length} of the target book's ${ACTUAL.book.n_names} name(s) are not held`,
    );
  });

  it("reports a held position against its target weight, in both units", () => {
    const block = ACTUAL.actual_holdings;
    expect(block).toBeTruthy();
    if (!block) return;
    const facts = bookFacts(ACTUAL);
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);

    const cellsFor = (ticker: string): Array<string | null> => {
      const row = section().querySelector(`tbody [data-ticker='${ticker}']`) as HTMLElement;
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
    const ordered = (): string[] =>
      Array.from(section().querySelectorAll("tbody [data-ticker]")).map(
        (row) => row.getAttribute("data-ticker") ?? "",
      );
    const before = ordered();

    fireEvent.click(section().querySelector("[data-sort='ticker']") as HTMLElement);
    expect(ordered()).toEqual([...before].sort((a, b) => a.localeCompare(b)));
    fireEvent.click(section().querySelector("[data-sort='ticker']") as HTMLElement);
    expect(ordered()).toEqual([...before].sort((a, b) => b.localeCompare(a)));

    // A weight or a dollar column sorts by size, so a 5% short ranks with a 5%
    // long: the reader is asking which positions matter.
    fireEvent.click(section().querySelector("[data-sort='heldDollars']") as HTMLElement);
    const sizes = ordered().map((ticker) => {
      const entry = ACTUAL.actual_holdings?.names.find((name) => name.ticker === ticker);
      return Math.abs(entry?.notional ?? 0);
    });
    expect(sizes).toEqual([...sizes].sort((a, b) => b - a));
  });

  it("says the account was not read rather than drawing an empty book", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(OK.actual_holdings).toBeUndefined();
    expect(section().textContent).toContain("the account has not been read");
    expect(section().querySelector("table")).toBeNull();
    // One line, not a heading over a blank: a table of no rows reads as an
    // account holding nothing.
    expect(section().querySelectorAll("p").length).toBe(1);
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

    const summary = section().querySelector("[data-fills='summary']") as HTMLElement;
    expect(summary.textContent).toContain("none to reconcile yet");
    expect(summary.textContent).toContain("before the orders went out");
    expect(summary.textContent).not.toContain("0 filled");
    expect(section().textContent).toContain("at the evening run");
    expect(section().textContent).not.toContain("close");
  });

  it("renders the read time as a time, never as a bare ISO stamp", () => {
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    expect(document.body.textContent ?? "").not.toContain("T00:00:00");
    expect(section().textContent).toContain("2026-09-22 15:30 UTC");
  });
});

describe("a snapshot with no book", () => {
  it("hides every section that needs the book rather than drawing it empty", () => {
    const snapshot: Snapshot = NONE;
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    expect(snapshot.book.n_names).toBe(0);
    expect(snapshot.book.reason).toBeTruthy();
    expect(document.querySelector("[data-cards='true']")).toBeNull();
    expect(document.querySelector("[data-section='sector']")).toBeNull();
    expect(document.querySelector("[data-section='top-names']")).toBeNull();
    expect(document.querySelector("[data-section='reasons']")).toBeNull();
    expect(document.querySelector("[data-section='holdings']")).toBeNull();
    expect(document.querySelector("[data-section='exposures']")).toBeNull();
    expect(document.querySelector("[data-section='risk']")).toBeNull();
    expect(document.querySelector("[data-section='movers']")).toBeNull();
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
