// "The hedge" on a hold day: the pair that means something is the rebalance's.
//
// The document is the one the page was served for the 2026-10-30 close, with the
// anchor close's own exposure vectors in the monthly block - the numbers the evening
// published for the 2026-10-23 rebalance, not a hand-built book. On that close
// nothing was hedged, so the document's own before/after pair is one vector twice and
// the old panel called it "the hedge"; the panel now shows the rebalance's pair and
// tonight's book beside it.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  anchoredExposures,
  ExposuresSection,
  heatContrast,
  heatInk,
} from "./ExposuresSection";
import served from "../fixtures/snapshot_2026-10-30_evening.json";
import type { MonthlyBlock, Snapshot } from "./types";

const HOLD = served as unknown as Snapshot;
const HOLD_MONTHLY = HOLD.monthly as MonthlyBlock;

function headerTexts(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("thead th")).map(
    (node) => node.textContent ?? "",
  );
}

describe("the exposures panel on a hold day", () => {
  it("is anchored on the rebalance's own close", () => {
    const block = anchoredExposures(HOLD_MONTHLY);
    expect(block).not.toBeNull();
    expect(block?.anchor).toBe("2026-10-23");
  });

  it("shows before and after the anchor's hedge, then tonight", () => {
    const { container } = render(<ExposuresSection snapshot={HOLD} />);
    const headers = headerTexts(container);
    expect(headers).toContain("before the hedge 2026-10-23");
    expect(headers).toContain("after the hedge 2026-10-23");
    expect(headers.join(" ")).toContain("now 2026-10-30");
  });

  it("states the anchor's before and after in percent, with no precision claim", () => {
    const { container } = render(<ExposuresSection snapshot={HOLD} />);
    const verdict = container.querySelector("[data-hedge-verdict]");
    const text = verdict?.textContent ?? "";
    expect(text).toContain("cut the book's worst factor exposure from");
    expect(text).toContain("87.19%");
    expect(text).toContain("0.00%");
    expect(text).toContain("Nothing was hedged tonight");
    expect(text).not.toContain("machine precision");
    // Every cell carries its value in percent, and a cell's shade is the heat scale.
    const table = container.querySelector("[data-heat-table='true']");
    expect(table).toBeTruthy();
    const momentum = container.querySelector('[data-factor="momentum"] [data-heat="before"]') as HTMLElement;
    expect(momentum.textContent).toBe("87.19%");
    expect(momentum.style.backgroundColor).not.toBe("");
    const nowCell = container.querySelector('[data-now="reversal"]');
    expect(nowCell?.textContent ?? "").not.toBe("0.00%");
  });

  it("scales each column against itself, and states the range it used", () => {
    const { container } = render(<ExposuresSection snapshot={HOLD} />);
    const range = (column: string) =>
      container.querySelector(`[data-column='${column}']`)?.getAttribute("data-column-range");
    // The before column's own largest value, the capped after column, tonight's book.
    expect(range("before")).toBe("87.19%");
    expect(range("after")).toBe("0.00%");
    expect(range("now")).toBe("0.41%");
    // On one shared scale the now column was a single pale wash. On its own scale it
    // shows the moves that are in it: at least three shades, none of them the before
    // column's strongest.
    const now = Array.from(
      container.querySelectorAll("[data-heat='now']"),
    ) as HTMLElement[];
    const shades = new Set(
      now.map((cell) => cell.style.backgroundColor).filter((fill) => fill !== "transparent"),
    );
    expect(shades.size).toBeGreaterThanOrEqual(3);
    const alpha = (cell: HTMLElement) =>
      Number((cell.style.backgroundColor.match(/, ([0-9.]+)\)$/) ?? [])[1] ?? 0);
    const largest = now.reduce(
      (best, cell) => {
        const value = Math.abs(Number((cell.textContent ?? "0").replace("%", "")));
        return value > best.value ? { value, cell } : best;
      },
      { value: -1, cell: now[0] },
    );
    for (const cell of now) {
      expect(alpha(largest.cell)).toBeGreaterThanOrEqual(alpha(cell) - 1e-9);
    }
  });

  it("gives a positive cell and a negative cell different hues", () => {
    const { container } = render(<ExposuresSection snapshot={HOLD} />);
    const now = Array.from(
      container.querySelectorAll("[data-heat='now']"),
    ) as HTMLElement[];
    const positive = now.find((cell) => cell.getAttribute("data-heat-sign") === "positive");
    const negative = now.find((cell) => cell.getAttribute("data-heat-sign") === "negative");
    expect(positive, "no positive cell in the now column").toBeTruthy();
    expect(negative, "no negative cell in the now column").toBeTruthy();
    const hue = (cell: HTMLElement | undefined) =>
      (cell?.style.backgroundColor ?? "").replace(/,[^,]*\)$/, ")");
    // Blue is long, rose is short: the sign survives without reading the number.
    expect(hue(positive)).toBe("rgba(37, 99, 235)");
    expect(hue(negative)).toBe("rgba(225, 29, 72)");
    // And their sizes are still carried by the alpha, not by the hue.
    expect(hue(positive)).not.toBe(hue(negative));
    // A cell that prints 0.00% is left unpainted, not tinted a faint sign.
    for (const cell of now) {
      if ((cell.textContent ?? "").trim() === "0.00%") {
        expect(cell.style.backgroundColor).toBe("transparent");
      }
    }
  });

  it("draws the capped after column flat and says why in the caption", () => {
    const { container } = render(<ExposuresSection snapshot={HOLD} />);
    const after = Array.from(
      container.querySelectorAll("[data-heat='after']"),
    ) as HTMLElement[];
    expect(after.length).toBeGreaterThan(0);
    for (const cell of after) {
      expect(cell.style.backgroundColor).toBe("transparent");
      expect(cell.getAttribute("data-heat-sign")).toBe("zero");
    }
    const caption = container.querySelector("[data-heat-caption]")?.textContent ?? "";
    expect(caption).toContain("compares a cell only with the other cells in its own column");
    expect(caption).toContain("blue is a positive exposure, rose a negative one");
    expect(caption).toContain("at the 5% guard carries an amber ring");
    expect(caption).toContain("The shade compares a cell only with the other cells");
    expect(caption).not.toContain("one scale");
  });

  it("rings a now cell at or beyond the 5% guard line, and only that cell", () => {
    const snapshot = {
      ...HOLD,
      exposures_before_hedge: {
        ...HOLD.exposures_before_hedge,
        momentum: 0.073,
        size: -0.05,
        beta: 0.049,
      },
    } as unknown as Snapshot;
    const { container } = render(<ExposuresSection snapshot={snapshot} />);
    const cell = (key: string) => container.querySelector(`[data-now='${key}']`) as HTMLElement;
    const ringed = (key: string) =>
      cell(key).getAttribute("data-guard") === "true" && /inset/.test(cell(key).style.boxShadow);
    // Over the line, exactly on it, and just inside it.
    expect(ringed("momentum"), "a cell over the guard line has no ring").toBe(true);
    expect(ringed("size"), "a cell on the guard line has no ring").toBe(true);
    expect(ringed("beta"), "a cell inside the guard line is ringed").toBe(false);
    // The ring is an outline: the cell keeps its own shade underneath.
    expect(cell("momentum").style.backgroundColor).toMatch(/^rgba\(/);
    const caption = container.querySelector("[data-heat-caption]")?.textContent ?? "";
    expect(caption).toContain("at the 5% guard carries an amber ring");
    expect(caption).toContain("rose a negative one");
  });

  it("keeps every value at 4.5:1 against the cell it sits on", () => {
    const { container } = render(<ExposuresSection snapshot={HOLD} />);
    const cells = Array.from(
      container.querySelectorAll("[data-heat]"),
    ) as HTMLElement[];
    expect(cells.length).toBeGreaterThan(30);
    let darkest = { ratio: Infinity, cell: cells[0] };
    for (const cell of cells) {
      const value = heatContrast(cell.style.backgroundColor, cell.style.color);
      expect(
        value,
        `a cell's value is ${value.toFixed(2)}:1: ${cell.textContent}`,
      ).toBeGreaterThanOrEqual(4.5);
      if (value < darkest.ratio) darkest = { ratio: value, cell };
    }
    // The tightest cell on this document, named so a palette change cannot quietly
    // take it under the line.
    expect(darkest.ratio).toBeGreaterThanOrEqual(4.5);
    // And the rule is not one colour: a dark fill takes the light ink.
    expect(heatInk("rgba(15, 23, 42, 1)")).toBe("#efebe2");
    expect(heatInk("transparent")).toBe("#191713");
    expect(heatContrast("rgba(15, 23, 42, 1)", "#efebe2")).toBeGreaterThan(4.5);
  });

  it("shows the anchor's before column as a real exposure, not the same vector", () => {
    const { container } = render(<ExposuresSection snapshot={HOLD} />);
    const cells = (key: string) =>
      Array.from(
        container.querySelectorAll(`[data-factor="${key}"] td`),
      ).map((node) => node.textContent ?? "");
    const market = cells("market");
    // before the 2026-10-23 hedge, after it, then now: three different readings.
    expect(market[1]).not.toBe(market[2]);
    expect(market[2]).not.toBe(market[3]);
  });

  it("adds the drift guard's line, with the legs it sent", () => {
    const { container } = render(<ExposuresSection snapshot={HOLD} />);
    const line = container.querySelector("[data-hedge-guard]");
    const text = line?.textContent ?? "";
    expect(text).toContain("drift guard tonight");
    expect(text).toContain("6.41%");
    expect(text).toContain("0.41%");
    expect(text).toContain("5.00%");
    expect(text).toContain("109");
    expect(text).toContain("assumes they fill");
  });

  it("renders exactly as before when there is no monthly block", () => {
    const daily = { ...HOLD, monthly: undefined } as unknown as Snapshot;
    expect(anchoredExposures(undefined)).toBeNull();
    const { container } = render(<ExposuresSection snapshot={daily} />);
    const headers = headerTexts(container);
    expect(headers).toContain("before the hedge");
    expect(headers).toContain("after the hedge");
    expect(headers.join(" ")).not.toContain("now (");
    expect(container.querySelector("[data-hedge-guard]")).toBeNull();
    expect(container.querySelector("[data-hedge-verdict]")?.textContent ?? "").toContain(
      "the hedge removed the bet",
    );
  });

  it("renders exactly as before on a rebalance day", () => {
    const rebalance = {
      ...HOLD,
      monthly: { ...HOLD_MONTHLY, anchor: { ...HOLD_MONTHLY.anchor, day: "rebalance" } },
    } as unknown as Snapshot;
    expect(anchoredExposures(rebalance.monthly)).toBeNull();
    const { container } = render(<ExposuresSection snapshot={rebalance} />);
    expect(headerTexts(container).join(" ")).not.toContain("before the hedge (");
  });
});
