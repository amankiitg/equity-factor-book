// Every chart on the page says what it draws, in words, and the series it draws.
//
// Colour alone is not a legend: a reader who cannot separate the two greens cannot
// tell which line is idio and which is the book held, and a reader who has never seen
// this page cannot tell whether a number is a volatility, a P&L or a share of risk.
// So every `figure[data-chart]` that plots a series must carry a list of entries, one
// per series it draws, naming it; and every one of them must state its unit either in
// the caption or in the legend, because "8.13" means nothing on its own.
//
// The notes are checked the same way: a dated statement about the series has to reach
// the reader as a marker at its date and as its own text, and the numbering has to
// agree between the two.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SnapshotView } from "./App";
import type { Attribution, Snapshot } from "./types";
import ok from "../fixtures/snapshot_ok.json";

const OK = ok as unknown as Snapshot;
const NOW = new Date("2026-10-08T23:00:00Z");
const ATTRIBUTION = OK.attribution as Attribution;
const LIVE_RISK_PATH = ATTRIBUTION.live?.risk?.path ?? [];
if (LIVE_RISK_PATH.length < 2) throw new Error("the ok fixture carries no risk path");

/** The attribution section is a tab, so every test opens it first. */
const open = (snapshot: Snapshot): void => {
  render(<SnapshotView snapshot={snapshot} now={NOW} />);
  fireEvent.click(screen.getByRole("tab", { name: "Attribution" }));
};

/** Every chart on the page, whether or not it is in the attribution section. */
const charts = (): HTMLElement[] => Array.from(document.querySelectorAll("figure[data-chart]"));

/** The series keys the chart actually draws. */
const drawn = (chart: HTMLElement): string[] =>
  Array.from(chart.querySelectorAll("[data-series]"))
    .map((node) => node.getAttribute("data-series") ?? "")
    .filter((key) => key !== "");

/** The series the chart's legend names. */
const named = (chart: HTMLElement): string[] =>
  Array.from(chart.querySelectorAll("li[data-series]"))
    .map((node) => node.getAttribute("data-series") ?? "")
    .filter((key) => key !== "");

describe("chart legends", () => {
  it("draws charts at all, so the checks below are not vacuous", () => {
    open(OK);
    expect(charts().length).toBeGreaterThanOrEqual(3);
  });

  it("gives every chart a legend naming every series it draws", () => {
    open(OK);
    for (const chart of charts()) {
      const series = new Set(drawn(chart));
      const legend = new Set(named(chart));
      expect(series.size, `chart ${chart.dataset.chart} draws no series`).toBeGreaterThan(0);
      for (const key of series) {
        expect(
          legend.has(key),
          `chart ${chart.dataset.chart} draws ${key} and its legend does not name it`,
        ).toBe(true);
      }
      // And a legend entry has words, not only a colour: the key alone is not a name.
      for (const item of Array.from(chart.querySelectorAll("li[data-series]"))) {
        expect((item.textContent ?? "").trim().length).toBeGreaterThan(3);
      }
    }
  });

  it("states a unit on every chart, in the caption or in the legend", () => {
    open(OK);
    const units = ["bp of NAV", "% annualized", "% of the book's predicted variance", "% of predicted variance"];
    for (const chart of charts()) {
      const text = chart.textContent ?? "";
      expect(
        units.some((unit) => text.includes(unit)),
        `chart ${chart.dataset.chart} states no unit: ${text.slice(0, 80)}`,
      ).toBe(true);
    }
  });

  it("draws the hedge as a waterfall of three steps, and as the two lines it stands between", () => {
    // What the hedge removed is one bar for the sized book, one for the points it
    // took out, one for what is left. The same two forecasts are also drawn by
    // session, because the 10-20 correction is about a line and a reader who is
    // told a line moved has to be able to see it.
    open(OK);
    expect(document.querySelector("figure[data-chart='risk-path']")).toBeNull();
    const series = document.querySelector("figure[data-chart='hedge-vol']");
    expect(series, "the by-session forecast chart is not drawn").toBeTruthy();
    for (const key of ["pre-hedge", "hedged", "removed"]) {
      expect(series?.querySelector(`[data-series='${key}']`)).toBeTruthy();
    }
    const waterfall = document.querySelector("[data-waterfall='true']") as HTMLElement;
    expect(waterfall).toBeTruthy();
    const steps = ["before", "removed", "after"].map(
      (key) => waterfall.querySelector(`[data-waterfall-step='${key}']`)?.textContent ?? "",
    );
    for (const step of steps) expect(step).toMatch(/[0-9]/);
    expect(steps[1]).toContain("pts");
    // The middle bar is the difference, in the same units as the two ends.
    const risk = ATTRIBUTION.live?.risk;
    if (!risk || risk.pre_hedge_vol === null || risk.hedged_vol === null) {
      throw new Error("the fixture carries no hedge forecast");
    }
    expect(steps[1]).toContain(
      `${((risk.pre_hedge_vol - risk.hedged_vol) * 100).toFixed(1)} pts`,
    );
  });
});

describe("the corrections to the series", () => {
  // The three statements the panel has to carry, in the words it has to carry them
  // in, with the days each one is about. A marker whose date is not on a chart would
  // be a number with nothing under it, so the days are checked against the chart.
  const CORRECTIONS = [
    {
      number: 1,
      dates: ["2026-09-28", "2026-09-29"],
      text:
        "The first two days (09-28 and 09-29) the book was still being built and not " +
        "fully hedged, so their predicted volatility can't be compared with later days.",
    },
    {
      number: 2,
      dates: ["2026-10-20"],
      text:
        "On 10-20 a formula error in the before-hedge volatility was fixed and every " +
        "earlier day recomputed. The line before 10-20 is lower than it was first drawn.",
    },
    {
      number: 3,
      dates: ["2026-10-21"],
      text:
        "On 10-21, trading costs for 10-09 to 10-20 were recomputed from the actual " +
        "fills (they had been estimated before the fills arrived). Those days' cost, " +
        "P&L and realized volatility changed slightly.",
    },
  ];

  const markers = (chart: string): HTMLElement[] =>
    Array.from(document.querySelectorAll(`figure[data-chart='${chart}'] [data-note-marker]`));

  it("lists the three corrections under the volatility panel, word for word", () => {
    open(OK);
    const group = document.querySelector("[data-group='volatility']") as HTMLElement;
    expect(group, "the volatility panel is not on the page").toBeTruthy();
    const list = group.querySelector("[data-notes]") as HTMLElement;
    expect(list).toBeTruthy();
    const items = Array.from(list.querySelectorAll("li[data-note]"));
    expect(items.length).toBe(3);
    for (const correction of CORRECTIONS) {
      const item = items.find(
        (node) => node.getAttribute("data-note") === correction.dates[0],
      );
      expect(item, `no correction listed for ${correction.dates[0]}`).toBeTruthy();
      expect(item?.textContent).toBe(`${correction.number}${correction.text}`);
      expect(item?.getAttribute("data-note-dates")).toBe(correction.dates.join(","));
    }
  });

  it("draws a marker at every date a correction names, on both dated charts", () => {
    open(OK);
    const dates = CORRECTIONS.flatMap((correction) =>
      correction.dates.map((date) => ({ date, number: correction.number })),
    );
    for (const chart of ["hedge-vol", "volatility"]) {
      const drawn = markers(chart).map((node) => ({
        date: node.getAttribute("data-note-marker-date") ?? "",
        number: node.getAttribute("data-note-marker") ?? "",
        x: Number(node.querySelector("circle")?.getAttribute("cx") ?? NaN),
      }));
      expect(drawn.length, `${chart} draws no correction markers`).toBe(dates.length);
      for (const expected of dates) {
        const marker = drawn.find((node) => node.date === expected.date);
        expect(marker, `${chart} has no marker on ${expected.date}`).toBeTruthy();
        expect(marker?.number).toBe(String(expected.number));
      }
      // Left to right is the order of the dates: a marker at the wrong session
      // would be out of that order, and the number would then sit at a date it does
      // not belong to.
      const asDrawn = [...drawn].sort((a, b) => a.x - b.x).map((node) => node.date);
      expect(asDrawn).toEqual([...dates.map((node) => node.date)].sort());
    }
  });

  it("puts the marker for a session at that session's point on the line", () => {
    open(OK);
    const chart = document.querySelector("figure[data-chart='volatility']") as HTMLElement;
    const pairs = (ATTRIBUTION.live?.daily ?? []).filter(
      (day) => day.realized_vol !== null && day.forecast_vol !== null,
    );
    const points = (chart.querySelector("[data-series='forecast']")?.getAttribute("points") ?? "")
      .split(" ")
      .filter((point) => point !== "")
      .map((point) => Number(point.split(",")[0]));
    for (const correction of CORRECTIONS) {
      for (const date of correction.dates) {
        const index = pairs.findIndex((day) => day.trade_date === date);
        if (index < 0) continue;
        const marker = chart.querySelector(
          `[data-note-marker-date='${date}'] circle`,
        ) as HTMLElement;
        expect(marker, `no marker on ${date}`).toBeTruthy();
        expect(Number(marker.getAttribute("cx"))).toBeCloseTo(points[index], 3);
      }
    }
  });

  it("opens a correction's text from the marker and closes it again", () => {
    open(OK);
    const chart = document.querySelector("figure[data-chart='hedge-vol']") as HTMLElement;
    for (const correction of CORRECTIONS) {
      const marker = chart.querySelector(
        `[data-note-marker-date='${correction.dates[0]}']`,
      ) as HTMLElement;
      fireEvent.click(marker);
      const popover = chart.querySelector(
        `[data-correction-text='${correction.number}']`,
      ) as HTMLElement;
      expect(popover, `marker ${correction.number} opens nothing`).toBeTruthy();
      expect(popover.textContent).toBe(correction.text);
      fireEvent.click(marker);
      expect(chart.querySelector("[data-correction-text]")).toBeNull();
    }
  });

  it("keeps the corrections on a document whose payload carries no notes", () => {
    // They are page copy about the series, not a row the evening wrote: a document
    // without the notes field still has to tell the reader what moved.
    const stripped = {
      ...OK,
      attribution: { ...ATTRIBUTION, notes: [] },
    } as unknown as Snapshot;
    open(stripped);
    const list = document.querySelector("[data-notes]") as HTMLElement;
    expect(list).toBeTruthy();
    expect(list.querySelectorAll("li[data-note]").length).toBe(3);
    expect(document.querySelectorAll("[data-note-marker]").length).toBeGreaterThan(0);
  });
});

describe("the realized against forecast chart", () => {
  // This chart used to be a plain panel, so the generic checks above never reached it
  // and it drew two lines with nothing naming them. It is a chart like the others now,
  // and this case is here so that a later edit cannot quietly take it back to a panel.
  const chart = (): HTMLElement => {
    const node = document.querySelector("figure[data-chart='volatility']");
    expect(node, "the realized-against-forecast chart is not a figure[data-chart]").toBeTruthy();
    return node as HTMLElement;
  };

  it("names both series it draws, with the unit in the legend", () => {
    open(OK);
    const node = chart();
    const legend = Array.from(node.querySelectorAll("li[data-series]"));
    expect(legend.map((item) => item.getAttribute("data-series"))).toEqual([
      "realized",
      "forecast",
    ]);
    const words = legend.map((item) => (item.textContent ?? "").toLowerCase());
    expect(words[0]).toContain("realized");
    expect(words[1]).toContain("forecast");
    for (const word of words) expect(word).toContain("% annualized");
    // And every series drawn has an entry, which is the rule the other charts follow.
    const drawnKeys = new Set(
      Array.from(node.querySelectorAll("[data-series]"))
        .filter((item) => item.tagName.toLowerCase() === "polyline")
        .map((item) => item.getAttribute("data-series")),
    );
    const namedKeys = new Set(legend.map((item) => item.getAttribute("data-series")));
    for (const key of drawnKeys) expect(namedKeys.has(key), `unnamed series ${key}`).toBe(true);
  });
});
