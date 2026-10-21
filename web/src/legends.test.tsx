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
import type { Attribution, AttributionNote, Snapshot } from "./types";
import establishment from "../fixtures/snapshot_establishment.json";
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
    expect(charts().length).toBeGreaterThanOrEqual(4);
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

  it("marks an area series as an area and a line as a line", () => {
    open(OK);
    const riskPath = document.querySelector("figure[data-chart='risk-path']") as HTMLElement;
    const ids = Array.from(riskPath.querySelectorAll("li[data-series]")).map(
      (node) => node.getAttribute("data-series"),
    );
    expect(ids).toContain("factor");
    expect(ids).toContain("idio");
    // The swatch is a filled rect for a band and a line for a line.
    expect(riskPath.querySelector("li[data-series='factor'] rect")).toBeTruthy();
    const hedge = document.querySelector("figure[data-chart='hedge-vol']") as HTMLElement;
    expect(hedge.querySelector("li[data-series='pre-hedge'] line")).toBeTruthy();
    expect(hedge.querySelector("li[data-series='removed'] rect")).toBeTruthy();
  });
});

describe("dated notes", () => {
  const notes = (ATTRIBUTION.notes ?? []) as AttributionNote[];

  it("carries the correction that moved the series, with its date", () => {
    expect(notes.length).toBeGreaterThan(0);
    const correction = notes.find((note) => note.date === "2026-10-20");
    expect(correction, "the 10-20 correction has no note").toBeTruthy();
    expect((correction?.text ?? "").toLowerCase()).toContain("pre-hedge");
  });

  it("lists every note with its date and its text", () => {
    open(OK);
    const list = document.querySelector("[data-notes]") as HTMLElement;
    expect(list).toBeTruthy();
    const items = Array.from(list.querySelectorAll("li[data-note]"));
    expect(items.length).toBe(notes.length);
    for (const note of notes) {
      const item = items.find((node) => node.getAttribute("data-note") === note.date);
      expect(item, `no note listed for ${note.date}`).toBeTruthy();
      expect(item?.textContent ?? "").toContain(note.text);
      expect(item?.textContent ?? "").toContain(note.date ?? "");
    }
  });

  it("numbers the markers on the charts to match the list", () => {
    // A marker is drawn only at a date the chart actually spans, and the fixture's
    // live window closes before any of the notes, so this document carries one note
    // dated the first session it draws. The mechanism is what is under test here; the
    // codes' own notes are asserted above.
    const first = LIVE_RISK_PATH[0]?.trade_date ?? "";
    const dotted = {
      ...OK,
      attribution: {
        ...ATTRIBUTION,
        notes: [{ date: first, text: "a note on the first drawn session" }],
      },
    } as unknown as Snapshot;
    open(dotted);
    const markers = Array.from(document.querySelectorAll("[data-note-marker]")).map((node) =>
      Number(node.getAttribute("data-note-marker")),
    );
    // A note whose date is not in the drawn window has no marker; every marker that
    // is drawn has to point at a numbered line in the list.
    expect(markers.length).toBeGreaterThan(0);
    const items = document.querySelectorAll("[data-notes] li[data-note]").length;
    for (const number of markers) {
      expect(number).toBeGreaterThanOrEqual(1);
      expect(number).toBeLessThanOrEqual(items);
    }
    // The marker carries the note's text as its title, so the text travels with the
    // point and not only with the list.
    const titleNode = document.querySelector(`[data-note-marker='${markers[0]}'] title`);
    expect((titleNode?.textContent ?? "").length).toBeGreaterThan(10);
  });

  it("draws no notes when the document carries none", () => {
    const stripped = {
      ...OK,
      attribution: { ...ATTRIBUTION, notes: [] },
    } as unknown as Snapshot;
    open(stripped);
    expect(document.querySelector("[data-notes]")).toBeNull();
    expect(document.querySelector("[data-note-marker]")).toBeNull();
  });

  it("keeps the notes on an establishment document, whose live period is one day", () => {
    const empty = establishment as unknown as Snapshot;
    const itsNotes = ((empty.attribution as Attribution).notes ?? []) as AttributionNote[];
    open(empty);
    const list = document.querySelector("[data-notes]");
    // The notes are about the series rather than about the book, so an evening that
    // could barely price one does not lose the record of what changed.
    expect(list === null).toBe(itsNotes.length === 0);
    if (list) {
      expect(list.querySelectorAll("li[data-note]").length).toBe(itsNotes.length);
    }
  });
});
