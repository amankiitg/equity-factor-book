// The overview charts, checked on the rendered document.
//
// The pictures are drawn by hand, so the rules that keep them readable are
// asserted here rather than left to a screenshot: every line is solid and thick
// enough to see, every bar is tall enough to read, the axis carries labels, and
// the exposure bars speak in sector names rather than in codes.

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SnapshotView } from "./App";
import { cumulativePoints, exposureRows } from "./Overview";
import type { Snapshot } from "./types";
import served from "../fixtures/snapshot_2026-10-30_evening.json";

const SERVED = served as unknown as Snapshot;
const NOW = new Date("2026-10-30T23:30:00Z");

const chart = (): SVGElement => {
  render(<SnapshotView snapshot={SERVED} now={NOW} />);
  return document.querySelector("[data-overview-cumulative='true']") as SVGElement;
};

describe("the overview charts", () => {
  it("draws the four cumulative lines solid, at two pixels or more", () => {
    const svg = chart();
    const lines = Array.from(svg.querySelectorAll("[data-series]"));
    expect(lines.map((line) => line.getAttribute("data-series"))).toEqual([
      "total",
      "factor",
      "idio",
      "cost",
    ]);
    for (const line of lines) {
      expect(line.getAttribute("stroke-dasharray")).toBeNull();
      expect(Number(line.getAttribute("stroke-width"))).toBeGreaterThanOrEqual(2);
    }
    const total = svg.querySelector("[data-series='total']") as SVGElement;
    expect(Number(total.getAttribute("stroke-width"))).toBe(2.5);
    const colors = lines.map((line) => line.getAttribute("stroke"));
    expect(new Set(colors).size).toBe(4);
  });

  it("labels each line at its right end with its latest value", () => {
    const svg = chart();
    const points = cumulativePoints(SERVED);
    const last = points[points.length - 1];
    const labels = Array.from(svg.querySelectorAll("[data-line-label]"));
    expect(labels.length).toBe(4);
    for (const label of labels) {
      const key = label.getAttribute("data-line-label") as "total" | "factor" | "idio" | "cost";
      expect(label.textContent?.trim()).toBe(
        `${last[key] >= 0 ? "+" : ""}${last[key].toFixed(0)}`,
      );
      // Every label sits at the same place: the right end of the drawn line.
      expect(label.getAttribute("x")).toBe(labels[0].getAttribute("x"));
    }
  });

  it("puts the legend above the chart and a hover title on every session", () => {
    render(<SnapshotView snapshot={SERVED} now={NOW} />);
    const card = document.querySelector("[data-overview-cumulative='true']") as SVGElement;
    const legend = document.querySelector("[data-legend='total']");
    expect(legend).toBeTruthy();
    const position = legend ? legend.compareDocumentPosition(card) : 0;
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const hover = card.querySelectorAll("[data-hover-point]");
    expect(hover.length).toBe((SERVED.attribution?.live?.daily ?? []).length);
    for (const band of Array.from(hover)) {
      const title = band.querySelector("title")?.textContent ?? "";
      for (const word of ["total", "factor", "stock-specific", "cost"]) {
        expect(title).toContain(word);
      }
    }
  });

  it("draws four or five labelled gridlines plus a stronger zero line", () => {
    const svg = chart();
    const gridlines = Array.from(svg.querySelectorAll("[data-gridline]"));
    expect(gridlines.length).toBeGreaterThanOrEqual(4);
    expect(gridlines.length).toBeLessThanOrEqual(5);
    for (const line of gridlines) {
      expect((line.textContent ?? "").trim().length).toBeGreaterThan(0);
    }
    const zero = svg.querySelector("[data-zero-line]") as SVGElement;
    expect(Number(zero.getAttribute("stroke-width"))).toBeGreaterThan(1);
    expect(svg.querySelectorAll("[data-x-tick]").length).toBeGreaterThanOrEqual(3);
  });

  it("marks the 10-23 rebalance and the next one with labelled dashed lines", () => {
    const svg = chart();
    const past = svg.querySelector("[data-overview-rebalance='2026-10-23']") as SVGElement;
    expect(past).toBeTruthy();
    expect(past.textContent).toContain("rebalance 10-23");
    const next = svg.querySelector("[data-overview-rebalance='2026-11-23']") as SVGElement;
    expect(next).toBeTruthy();
    expect(next.getAttribute("data-rebalance-future")).toBe("true");
    expect(next.textContent).toContain("next rebalance 11-23");
    for (const mark of [past, next]) {
      expect(mark.querySelector("line")?.getAttribute("stroke-dasharray")).toBeTruthy();
    }
  });

  it("gives the daily bars the same hover title and a visible axis", () => {
    render(<SnapshotView snapshot={SERVED} now={NOW} />);
    const svg = document.querySelector("[data-overview-daily='true']") as SVGElement;
    const rows = SERVED.attribution?.live?.daily ?? [];
    const bars = Array.from(svg.querySelectorAll("[data-daily-bar]"));
    expect(bars.length).toBe(rows.length);
    for (const bar of bars) {
      const title = bar.querySelector("title")?.textContent ?? "";
      expect(title).toContain("total");
      expect(title).toContain("factor");
    }
    expect(svg.querySelectorAll("[data-gridline]").length).toBeGreaterThanOrEqual(4);
    expect(svg.querySelector("[data-zero-line]")).toBeTruthy();
  });

  it("names sectors in words, sorted by absolute size, with bars ten pixels tall", () => {
    render(<SnapshotView snapshot={SERVED} now={NOW} />);
    const svg = document.querySelector("[data-overview-exposures='true']") as SVGElement;
    const text = svg.textContent ?? "";
    expect(text).toContain("Energy");
    expect(text).toContain("Materials");
    expect(text).not.toMatch(/Sector \d+/);
    const order = Array.from(svg.querySelectorAll("[data-exposure-factor]")).map(
      (row) => row.getAttribute("data-exposure-factor") as string,
    );
    const expected = [...exposureRows(SERVED)]
      .sort(
        (a, b) =>
          Math.max(Math.abs(a.afterHedge), Math.abs(a.now ?? 0)) -
          Math.max(Math.abs(b.afterHedge), Math.abs(b.now ?? 0)),
      )
      .reverse()
      .map((row) => row.factor);
    expect(order).toEqual(expected);
    const bars = Array.from(svg.querySelectorAll("[data-exposure-series]"));
    expect(bars.length).toBeGreaterThan(10);
    for (const bar of bars) {
      expect(Number(bar.getAttribute("height"))).toBeGreaterThanOrEqual(10);
    }
    expect(svg.querySelectorAll("[data-limit-band]").length).toBe(2);
  });

  it("heads the exposure chart with the worst exposure against the 5% limit", () => {
    render(<SnapshotView snapshot={SERVED} now={NOW} />);
    const header = document.querySelector("[data-exposure-header='true']")?.textContent ?? "";
    expect(header).toContain("worst exposure");
    expect(header).toContain("of the 5% limit");
    expect(header).toMatch(/\d/);
  });
});
