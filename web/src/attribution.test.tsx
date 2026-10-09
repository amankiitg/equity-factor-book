// The attribution section against the committed fixture.
//
// The numbers here are read from the fixture, never typed in: the writer owns them
// and a section test that hard-codes one is a test of the fixture's history rather
// than of the page. The one number this test does assert by hand is the one-decimal
// rendering the old section produced, because the bug it fixes is a rendering
// choice and not a value.

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AttributionSection } from "./AttributionSection";
import { SnapshotView } from "./App";
import type { Attribution, Snapshot } from "./types";
import ok from "../fixtures/snapshot_ok.json";

const OK = ok as unknown as Snapshot;
const NOW = new Date("2026-10-08T23:00:00Z");
const ATTRIBUTION = OK.attribution as Attribution;
const LIVE = ATTRIBUTION.live;
const BACKTEST = ATTRIBUTION.backtest;
if (!LIVE) throw new Error("the ok fixture carries no live period");
if (!BACKTEST) throw new Error("the ok fixture carries no backtest period");

const LIVE_PERIOD = LIVE;
const BACKTEST_PERIOD = BACKTEST;

const bps = (value: number | null): string =>
  `${(value ?? 0) >= 0 ? "+" : ""}${((value ?? 0) * 1e4).toFixed(1)} bp`;

const card = (name: string): string =>
  document.querySelector(`[data-card='${name}']`)?.textContent ?? "";

const asNumber = (text: string | null): number => Number((text ?? "").replace(/[^\d.+-]/g, ""));

const view = (): string | null =>
  document.querySelector("[data-section='attribution']")?.getAttribute("data-view") ?? null;

describe("the attribution section", () => {
  it("opens on the live book, not the research panel", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(view()).toBe("live");
    // The live period's own label is on screen; the backtest's note is not, because
    // the two are different objects and only one of them is the book.
    expect(screen.getByText(LIVE_PERIOD.label, { exact: false })).toBeTruthy();
    expect(screen.queryByText(BACKTEST_PERIOD.note, { exact: false })).toBeNull();
  });

  it("prints the four terms and the total for the live period, in bp and signed", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const cumulative = LIVE_PERIOD.cumulative;
    expect(card("pnl-total")).toContain(bps(cumulative.pnl_total));
    expect(card("pnl-factor")).toContain(bps(cumulative.pnl_factor));
    expect(card("pnl-idio")).toContain(bps(cumulative.pnl_idio));
    expect(card("pnl-cost")).toContain(bps(cumulative.pnl_cost));
    expect(card("pnl-unexplained")).toContain(bps(cumulative.pnl_unexplained));
    // The four terms are the total on the cumulative numbers too, not only per day.
    const sum =
      (cumulative.pnl_factor ?? 0) +
      (cumulative.pnl_idio ?? 0) +
      (cumulative.pnl_cost ?? 0) +
      (cumulative.pnl_unexplained ?? 0);
    expect(Math.abs(sum - (cumulative.pnl_total ?? 0))).toBeLessThan(1e-9);
    // The worst day's residual travels with the sums rather than being asserted away.
    expect(screen.getByText(/worst single day's identity residual/)).toBeTruthy();
  });

  it("renders every live day's four terms so that they add to the day's total", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const table = screen.getByRole("table", { name: "attribution by day" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.length).toBe(LIVE_PERIOD.daily.length);
    for (const row of rows) {
      const cells = within(row).getAllByRole("cell");
      const total = asNumber(cells[1].textContent);
      const sum =
        asNumber(cells[2].textContent) +
        asNumber(cells[3].textContent) +
        asNumber(cells[4].textContent) +
        asNumber(cells[5].textContent);
      // Each term is rendered to one decimal, so a row's sum lands within the
      // rounding of its total; the check column is the same test at full precision.
      expect(Math.abs(sum - total)).toBeLessThan(0.3);
      expect(cells[6].getAttribute("data-check")).toBe("ok");
    }
  });

  it("draws the cumulative and daily charts for the live book only", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(document.querySelector("[data-chart='cumulative']")).toBeTruthy();
    expect(document.querySelector("[data-chart='daily']")).toBeTruthy();
    // Every series carries a word in the legend as well as a colour.
    for (const key of ["total", "factor", "idio", "cost"]) {
      expect(document.querySelector(`[data-series='${key}']`)).toBeTruthy();
    }
    fireEvent.click(screen.getByRole("tab", { name: "the research panel (backtest)" }));
    expect(document.querySelector("[data-chart='daily']")).toBeNull();
  });

  it("reveals the backtest behind the switch, with its own note and a zero cost", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    fireEvent.click(screen.getByRole("tab", { name: "the research panel (backtest)" }));
    expect(view()).toBe("backtest");
    expect(screen.getByText(BACKTEST_PERIOD.note, { exact: false })).toBeTruthy();
    expect(screen.getByText(/This is a backtest of the seed book/)).toBeTruthy();
    expect(screen.getByText(/no leg was traded/)).toBeTruthy();
    // The backtest's cost is exactly zero, and its chart is the monthly run.
    expect(card("pnl-cost")).toContain("+0.0 bp");
    expect(document.querySelector("[data-chart='cumulative']")).toBeTruthy();
    expect(screen.getByText(BACKTEST_PERIOD.monthly[0].month as string)).toBeTruthy();
    expect(
      screen.getByText(
        BACKTEST_PERIOD.monthly[BACKTEST_PERIOD.monthly.length - 1].month as string,
      ),
    ).toBeTruthy();
  });

  it("opens a long period on its ten newest days, with the rest behind a toggle", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    fireEvent.click(screen.getByRole("tab", { name: "the research panel (backtest)" }));
    const table = screen.getByRole("table", { name: "attribution by day" });
    expect(within(table).getAllByRole("row").slice(1).length).toBe(10);
    fireEvent.click(
      screen.getByRole("button", { name: `show all ${BACKTEST_PERIOD.daily.length} days` }),
    );
    expect(within(table).getAllByRole("row").slice(1).length).toBe(BACKTEST_PERIOD.daily.length);
  });

  it("draws the live risk split when it is there, and nothing when it is not", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(document.querySelector("[data-chart='risk']")).toBeTruthy();
    const factor = document.querySelector("[data-var-share='factor']")?.textContent ?? "";
    // The traded book's factor share is under 6% of predicted variance; one decimal
    // of a small share is not the same as a missing one.
    expect(Number(factor.replace("%", ""))).toBeLessThan(6);
    expect(document.querySelector("[data-var-share='idio']")?.textContent).toBeTruthy();
  });

  it("draws no risk chart when the live period carries no risk block", () => {
    const snapshot = {
      ...OK,
      attribution: { ...ATTRIBUTION, live: { ...LIVE_PERIOD, risk: null } },
    } as unknown as Snapshot;
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    expect(document.querySelector("[data-chart='risk']")).toBeNull();
    // The rest of the section survives an absent risk read.
    expect(document.querySelector("[data-chart='daily']")).toBeTruthy();
  });

  it("says which cost the split uses, expected against realized", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const cost = document.querySelector("[data-cost='line']")?.textContent ?? "";
    expect(cost).toContain((LIVE_PERIOD.cost.expected_bps as number).toFixed(2));
    expect(cost).toContain((LIVE_PERIOD.cost.realized_bps as number).toFixed(2));
    expect(cost).toContain("realized");
  });

  it("prints the raw beta to three places, never as the 0.0 one decimal gave", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const beta = document.querySelector("[data-beta='book']")?.textContent ?? "";
    const value = LIVE_PERIOD.daily[LIVE_PERIOD.daily.length - 1].book_beta as number;
    expect(Math.abs(value)).toBeGreaterThan(0);
    // The old section rounded this to one decimal, where it read as zero.
    expect(value.toFixed(1)).toBe("0.0");
    expect(beta).toContain(value.toFixed(3));
    expect(beta).not.toMatch(/beta 0\.0\b/);
    expect(beta).toContain("bp");
  });

  it("renders the page without throwing when the attribution key is gone", () => {
    const older: Snapshot = { ...OK };
    delete older.attribution;
    expect(() => render(<SnapshotView snapshot={older} now={NOW} />)).not.toThrow();
    expect(screen.queryByRole("heading", { name: "Attribution" })).toBeNull();
  });

  it("hides itself when handed no attribution at all", () => {
    const { container } = render(<AttributionSection attribution={undefined} />);
    expect(container.querySelector("[data-section='attribution']")).toBeNull();
  });
});
