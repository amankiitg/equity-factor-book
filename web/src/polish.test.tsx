// The page's polish rules, checked on the rendered document rather than on the source.
//
// Five things are asserted here because each was a way the page could look finished
// while being wrong: a letter standing in for an icon, a chart that was a sentence,
// a tab click that left another tab's sections on screen, a cost total that read as
// the guard's, and the same name counted from three places. The fixtures are the
// committed documents, so the values come from the writer rather than from a test.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SnapshotView } from "./App";
import type { Snapshot } from "./types";
import latest from "../fixtures/snapshot_2026-10-30_evening.json";
import ok from "../fixtures/snapshot_ok.json";
import withActual from "../fixtures/snapshot_actual_holdings.json";

const LATEST = latest as unknown as Snapshot;
const OK = ok as unknown as Snapshot;
const ACTUAL = withActual as unknown as Snapshot;
const NOW = new Date("2026-10-30T23:30:00Z");

const panels = (): HTMLElement[] =>
  Array.from(document.querySelectorAll("[role=tabpanel]")) as HTMLElement[];

describe("the rendered page", () => {
  it("draws the info markers as icons, with no letter in the title", () => {
    render(<SnapshotView snapshot={LATEST} now={NOW} />);
    const markers = Array.from(
      document.querySelectorAll("[aria-label^='about '], [data-how-to-read] button"),
    );
    expect(markers.length).toBeGreaterThan(0);
    for (const marker of markers) {
      expect((marker.textContent ?? "").trim()).toBe("");
      expect(marker.querySelector("svg")).toBeTruthy();
    }
  });

  it("shows only the selected tab's panel", () => {
    render(<SnapshotView snapshot={LATEST} now={NOW} />);
    for (const key of ["overview", "book", "attribution", "rebalance", "operations"]) {
      fireEvent.click(document.querySelector(`[data-view='${key}']`) as HTMLElement);
      const shown = panels().filter((panel) => !panel.hasAttribute("hidden"));
      expect(shown.length, `${key} left more than one panel visible`).toBe(1);
      expect(shown[0].id).toBe(`panel-${key}`);
    }
  });

  it("draws the cumulative P&L as a chart with a hover title for every session", () => {
    render(<SnapshotView snapshot={LATEST} now={NOW} />);
    const chart = document.querySelector("[data-overview-cumulative='true']") as SVGElement;
    expect(chart.tagName.toLowerCase()).toBe("svg");
    const rows = LATEST.attribution?.live?.daily ?? [];
    const hover = Array.from(chart.querySelectorAll("[data-hover-point]"));
    expect(hover.length).toBe(rows.length);
    for (const point of hover) {
      expect((point.querySelector("title")?.textContent ?? "").length).toBeGreaterThan(12);
    }
    const bars = document.querySelectorAll("[data-daily-bar]");
    expect(bars.length).toBe(rows.length);
    for (const bar of Array.from(bars)) {
      expect(bar.querySelector("title")).toBeTruthy();
    }
  });

  it("keeps the metric, the basis points and the dollars in separate cells", () => {
    render(<SnapshotView snapshot={LATEST} now={NOW} />);
    const split = document.querySelector("[data-since-split]") as HTMLElement;
    expect(split).toBeTruthy();
    for (const row of Array.from(split.querySelectorAll("div"))) {
      const term = row.querySelector("dt")?.textContent ?? "";
      const values = Array.from(row.querySelectorAll("dd"));
      expect(values.length, `${term} did not separate bp from dollars`).toBe(2);
      expect(values[0].textContent ?? "").toContain("bp");
      expect(values[1].textContent ?? "").toMatch(/^[-+]?\$/);
    }
    // The sign is also a colour, from the light tokens.
    const total = document.querySelector("[data-kpi='since'] p.font-mono") as HTMLElement;
    const value = LATEST.attribution?.live?.cumulative?.pnl_total ?? 0;
    expect(total.className).toContain(value >= 0 ? "efb-up" : "efb-down");
  });

  it("splits the cost by era and names the guard's own share", () => {
    render(<SnapshotView snapshot={LATEST} now={NOW} />);
    fireEvent.click(document.querySelector("[data-view='attribution']") as HTMLElement);
    const card = document.querySelector("[data-cost='eras']") as HTMLElement;
    expect(card).toBeTruthy();
    expect(card.textContent).toContain("daily trading, to 10-23");
    expect(card.textContent).toContain("monthly cadence, since 10-23");
    expect(card.textContent).toContain("drift guard, since 10-23");
    const read = (era: string): number => {
      const node = card.querySelector(`[data-cost-era='${era}'] dd`) as HTMLElement;
      return Number((node.textContent ?? "").replace(/[^\d.+-]/g, ""));
    };
    const total = LATEST.attribution?.live?.cumulative?.pnl_cost ?? 0;
    expect(Math.abs(read("daily") + read("monthly") - total * 1e4)).toBeLessThan(0.2);
    // The guard is a small part of the monthly era, not the whole of it.
    expect(Math.abs(read("guard"))).toBeLessThan(Math.abs(read("monthly")));
  });

  it("calls the banner Needs attention", () => {
    render(<SnapshotView snapshot={LATEST} now={NOW} />);
    const banner = document.querySelector("[data-exception-banner]") as HTMLElement;
    expect(banner.textContent).toContain("Needs attention");
  });

  it("counts an inactive name once, from whichever source names it", () => {
    const snapshot = {
      ...LATEST,
      monthly: {
        ...LATEST.monthly,
        holdings: {
          anchor: "2026-10-23",
          as_of: "2026-10-30",
          rows: [
            {
              ticker: "KVUE",
              since: "retired (acquired by KMB), owed, cannot be traded",
              since_kind: "retired",
              since_date: "2026-11-05",
              weight_now: 0,
              weight_target: 0.0066,
              gap_weight: -0.0066,
              gap_usd: -13615,
              tonight: null,
              retired: true,
              owed: true,
              note: "retired (acquired by KMB), owed, cannot be traded",
            },
          ],
        },
        tonight: {
          ...(LATEST.monthly?.tonight ?? {}),
          cannot_send: [{ ticker: "KVUE", usd: 13615, code: "COVER_UNDER_ONE_SHARE" }],
        },
      },
      actual_holdings: {
        ...LATEST.actual_holdings,
        exits: { feed: "read", names: [{ ticker: "KVUE", quantity: 1, notional: 13615 }] },
      },
    } as unknown as Snapshot;
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const cards = document.querySelectorAll("[data-exception='KVUE']");
    expect(cards.length).toBe(1);
    expect(cards[0].textContent).toBe(
      "KVUE: acquired by KMB, symbol inactive, held $13,615, cannot be traded",
    );
  });

  it("leaves Operations to the run's own facts, with the method where it is read", () => {
    render(<SnapshotView snapshot={OK} now={new Date("2026-10-08T23:00:00Z")} />);
    fireEvent.click(screen.getByRole("tab", { name: "Operations" }));
    const operations = document.querySelector("#panel-operations") as HTMLElement;
    // The notes drawer is gone, and with it the methodology that was three tabs from
    // the numbers it explained.
    expect(operations.querySelector("[data-details='notes']")).toBeNull();
    expect(operations.textContent ?? "").not.toContain("how the four terms are computed");
    expect(operations.textContent ?? "").not.toContain("sample size");
    expect(operations.textContent ?? "").not.toContain("corrections to the series");
    // The method is now the (i) on the heading whose cards it explains, the
    // corrections are under the volatility panel, and the sample size sits beside
    // the bias it qualifies.
    fireEvent.click(screen.getByRole("tab", { name: "Attribution" }));
    const attribution = document.querySelector("[data-section='attribution']") as HTMLElement;
    expect(attribution.querySelector("[data-notes]")).toBeTruthy();
    const sample = attribution.querySelector("[data-vol='sample']") as HTMLElement;
    expect(sample).toBeTruthy();
    expect(sample.textContent ?? "").toContain("Not enough live days yet to judge the model");
    expect(sample.querySelector("[data-how-to-read]")).toBeTruthy();
    const earned = Array.from(attribution.querySelectorAll("h3")).find((node) =>
      (node.textContent ?? "").startsWith("What the book earned"),
    ) as HTMLElement;
    fireEvent.click(earned.querySelector("[data-how-to-read] button") as HTMLElement);
    expect(attribution.textContent ?? "").toContain(
      "factor P&L is the book's exposure times the factor returns",
    );
    expect(attribution.textContent ?? "").toContain("the check column in the table is for");
  });

  it("reads the attribution tab in the order the questions are asked", () => {
    render(<SnapshotView snapshot={LATEST} now={NOW} />);
    fireEvent.click(screen.getByRole("tab", { name: "Attribution" }));
    const section = document.querySelector("[data-section='attribution']") as HTMLElement;
    const earned = Array.from(section.querySelectorAll("h3")).find((node) =>
      (node.textContent ?? "").startsWith("What the book earned"),
    ) as HTMLElement;
    expect(earned, "the earnings heading is missing").toBeTruthy();
    const cards = section.querySelector("[data-card='pnl-total']") as HTMLElement;
    const cumulative = section.querySelector("[data-chart='cumulative']") as HTMLElement;
    const daily = section.querySelector("[data-chart='daily']") as HTMLElement;
    const risk = section.querySelector("[data-group='volatility']") as HTMLElement;
    const byFactor = section.querySelector("[data-panel='by-factor']") as HTMLElement;
    for (const node of [cards, cumulative, daily, risk, byFactor]) {
      expect(node, "a section of the attribution tab is missing").toBeTruthy();
    }
    // What the book earned, then how much risk produced it, then which factors.
    const order = [earned, cards, cumulative, daily, risk, byFactor];
    for (let index = 1; index < order.length; index += 1) {
      const before = order[index - 1].compareDocumentPosition(order[index]);
      expect(
        before & Node.DOCUMENT_POSITION_FOLLOWING,
        `${order[index - 1].dataset.chart ?? order[index - 1].id ?? index} is not before the next section`,
      ).toBeTruthy();
    }
    // The volatility panel carries the waterfall, the by-session line and the chart.
    expect(risk.querySelector("[data-waterfall='true']")).toBeTruthy();
    expect(risk.querySelector("[data-chart='hedge-vol']")).toBeTruthy();
    expect(risk.querySelector("[data-chart='volatility']")).toBeTruthy();
    expect(risk.querySelector("[data-corrections='true']")).toBeTruthy();
  });

  it("opens the glossary as one disclosure, with no header over a header", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    fireEvent.click(screen.getByRole("tab", { name: "Operations" }));
    const glossary = document.querySelector("[data-glossary='true']") as HTMLElement;
    expect(glossary.tagName.toLowerCase()).toBe("details");
    // It was a details wrapped in a details with the same words, which reads as a
    // collapsed row that opens onto another collapsed row.
    expect(glossary.parentElement?.closest("details")).toBeNull();
    const summaries = Array.from(
      document.querySelectorAll("#panel-operations summary"),
    ).filter((node) => (node.textContent ?? "").trim().toLowerCase() === "what the words mean");
    expect(summaries.length).toBe(1);
  });

  it("keeps Operations to the run's own record", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    fireEvent.click(screen.getByRole("tab", { name: "Operations" }));
    const operations = document.querySelector("#panel-operations") as HTMLElement;
    // The six things the tab holds, and nothing that is a method note.
    expect(operations.querySelector("[data-alert='reconciliation']")).toBeTruthy();
    expect(operations.querySelector("[data-details='run-detail']")).toBeTruthy();
    expect(operations.querySelector("[data-glossary='true']")).toBeTruthy();
    const text = operations.textContent ?? "";
    expect(text).toContain("reconcil");
    expect(text.length).toBeGreaterThan(0);
    for (const gone of [
      "corrections to the series",
      "sample size",
      "the research panel:",
      "how the four terms are computed",
    ]) {
      expect(text, `Operations still carries a method note: ${gone}`).not.toContain(gone);
    }
  });
});

// Every card title on every tab opens an (i).
//
// The writing standard is that a title is a word and the explanation is one tap
// away: what the number is, why it moves, and one real example. A card that grows a
// title without a popover reads as a name and nothing else. This enumerates the
// cards the five tabs draw and asserts each one carries the marker, so a new panel
// cannot be added without one.
describe("the (i) on every card title", () => {
  const VIEWS = ["overview", "book", "attribution", "rebalance", "operations"] as const;

  /** The things the page draws as a card with a title. */
  const CARDS = [
    "[data-kpi]",
    "[data-cards] [data-card]",
    "[data-section='hedge']",
    "[data-section='exposures']",
    "[data-section='sector']",
    "[data-section='top-names']",
    "[data-section='reasons']",
    "[data-section='risk']",
    "[data-section='movers']",
    "[data-section='attribution']",
    "[data-panel='monthly']",
    "[data-panel='by-factor']",
    "[data-panel='volatility']",
    "[data-cost='eras']",
    "[data-alert='run']",
    "[data-alert='reconciliation']",
    "[data-exception-banner]",
  ].join(",");

  const missing = (panel: HTMLElement): string[] => {
    const found: string[] = [];
    for (const node of Array.from(panel.querySelectorAll<HTMLElement>(CARDS))) {
      // The construction telemetry's four stats are a definition list inside one
      // disclosure, not cards of their own.
      if (node.matches("[data-card]") && node.closest("dl")) continue;
      if (!node.querySelector("[data-how-to-read]")) {
        const title = (node.querySelector("h2, h3, dt, p, div")?.textContent ?? "").trim();
        found.push(`${node.tagName.toLowerCase()} ${title.slice(0, 40)}`);
      }
    }
    return found;
  };

  const audit = (snapshot: Snapshot, label: string): void => {
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    for (const view of VIEWS) {
      const panel = document.querySelector(`#panel-${view}`) as HTMLElement;
      expect(panel, label).toBeTruthy();
      // Every tab but "Since the rebalance" always draws cards; that one draws none
      // on a document with no anchored block, which is what its own notice says.
      if (view !== "rebalance") {
        expect(panel.querySelectorAll(CARDS).length, `${label} ${view}`).toBeGreaterThan(0);
      }
      expect(missing(panel), `${label} ${view}`).toEqual([]);
    }
    document.body.innerHTML = "";
  };

  it("is on every card of every tab, on the served hold day and on the older documents", () => {
    audit(LATEST, "hold day");
    audit(OK, "no anchored block");
    audit(ACTUAL, "morning with fills");
  });
});


describe("the (i) on the cards that were missing one", () => {
  /** The last rebalance's construction, which no committed fixture carries yet. */
  const CONSTRUCTED: Snapshot = {
    ...LATEST,
    monthly: {
      ...(LATEST.monthly as NonNullable<Snapshot["monthly"]>),
      anchor_construction: {
        close: "2026-10-23",
        considered: 499,
        left_out_no_risk: 3,
        left_out_no_risk_names: [
          { ticker: "FDXF", reason: "no specific variance" },
          { ticker: "HONA", reason: "no specific variance" },
          { ticker: "Q", reason: "no specific variance" },
        ],
        excluded: 7,
        excluded_names: ["AAA"],
        removed_too_small: 300,
        final_names: 196,
        gross: 1,
        net: 0,
        vol: 0.0279,
        floor: "20 shares",
      },
    },
  };

  it("puts one on the construction disclosure and the glossary", () => {
    render(<SnapshotView snapshot={CONSTRUCTED} now={NOW} />);
    fireEvent.click(screen.getByRole("tab", { name: "Operations" }));
    const construction = document.querySelector(
      "[data-details='construction'] summary",
    ) as HTMLElement;
    expect(construction, "the construction disclosure is missing").toBeTruthy();
    expect(construction.querySelector("[data-how-to-read]")).toBeTruthy();
    const glossary = document.querySelector(
      "[data-glossary='true'] summary",
    ) as HTMLElement;
    expect(glossary).toBeTruthy();
    expect(glossary.querySelector("[data-how-to-read]")).toBeTruthy();
  });

  it("dates the 10-23 left-out line and keeps every name on it", () => {
    render(<SnapshotView snapshot={CONSTRUCTED} now={NOW} />);
    fireEvent.click(screen.getByRole("tab", { name: "Operations" }));
    const line = document.querySelector("[data-construction='left-out']") as HTMLElement;
    expect(line.textContent).toContain("At the 10-23 rebalance, 3 were left out");
    for (const ticker of ["FDXF", "HONA", "Q"]) expect(line.textContent).toContain(ticker);
  });
});
