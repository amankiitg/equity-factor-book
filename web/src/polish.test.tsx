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

const LATEST = latest as unknown as Snapshot;
const OK = ok as unknown as Snapshot;
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

  it("keeps the method, the corrections and the caveats in the Operations Notes drawer", () => {
    render(<SnapshotView snapshot={OK} now={new Date("2026-10-08T23:00:00Z")} />);
    fireEvent.click(screen.getByRole("tab", { name: "Operations" }));
    const drawer = document.querySelector("[data-details='notes']") as HTMLElement;
    expect(drawer).toBeTruthy();
    expect(drawer.textContent).toContain("how the four terms are computed");
    expect(drawer.querySelector("[data-notes]")).toBeTruthy();
    expect(drawer.textContent).toContain("sample size");
    const attribution = document.querySelector("[data-section='attribution']") as HTMLElement;
    expect(attribution.querySelector("[data-notes]")).toBeNull();
  });
});
