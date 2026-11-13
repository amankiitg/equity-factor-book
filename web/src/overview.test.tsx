// The overview, against the committed documents.
//
// The tab exists to answer "how is the book doing" without opening a diagnostic,
// so these tests read the strategy sentence, the four numbers, the banner, the
// cadence pill and the three charts off the real fixtures.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SnapshotView } from "./App";
import { navOf } from "./book";
import { cumulativePoints, lastDay, overviewExceptions } from "./Overview";
import { classify } from "./exceptions";
import { reconciliation, runState } from "./status";
import type { MonthlyBlock, Snapshot } from "./types";
import ok from "../fixtures/snapshot_ok.json";
import served from "../fixtures/snapshot_2026-10-30_evening.json";

const OK = ok as unknown as Snapshot;
const SERVED = served as unknown as Snapshot;
const NOW = new Date("2026-10-30T23:00:00Z");
const NOW_OK = new Date("2026-09-21T23:00:00Z");

describe("the overview tab", () => {
  it("is the first tab and the one the page opens on", () => {
    render(<SnapshotView snapshot={OK} now={NOW_OK} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0].textContent).toBe("Overview");
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      "Overview",
      "Positions",
      "Attribution",
      "Since the rebalance",
      "Operations",
    ]);
  });

  it("switches to positions without losing the overview from the document", () => {
    render(<SnapshotView snapshot={OK} now={NOW_OK} />);
    fireEvent.click(screen.getByRole("tab", { name: "Positions" }));
    const overview = document.querySelector("#panel-overview") as HTMLElement;
    expect(overview.hasAttribute("hidden")).toBe(true);
    expect(document.querySelector("[data-section='exposures']")).toBeTruthy();
  });

  it("states the strategy in one sentence", () => {
    render(<SnapshotView snapshot={OK} now={NOW_OK} />);
    const text = document.querySelector("[data-strategy='true']")?.textContent ?? "";
    expect(text).toContain("market-neutral");
    expect(text).toContain("21 sessions");
    expect(text).toContain("hedged");
  });

  it("puts NAV, today, the go-live split and the run's own state in cards", () => {
    render(<SnapshotView snapshot={OK} now={NOW_OK} />);
    const nav = navOf(OK) as number;
    const card = (hook: string): HTMLElement =>
      document.querySelector(`[data-kpi='${hook}']`) as HTMLElement;
    expect(card("nav").textContent).toContain(`$${Math.round(nav).toLocaleString()}`);
    const latest = lastDay(OK) as NonNullable<ReturnType<typeof lastDay>>;
    expect(card("today").textContent).toContain(
      `${latest.pnl_total && latest.pnl_total >= 0 ? "+" : ""}${(
        (latest.pnl_total ?? 0) * 1e4
      ).toFixed(1)} bp`,
    );
    expect(card("since").textContent).toContain("factor");
    expect(card("since").textContent).toContain("stock-specific");
    expect(card("since").textContent).toContain("cost");
    expect(card("run").textContent).toContain(runState(OK, NOW_OK).pill);
  });

  it("reads the cadence, the drift guard and the next rebalance from the block", () => {
    render(<SnapshotView snapshot={SERVED} now={NOW} />);
    const pill = document.querySelector("[data-cadence-pill='hold']")?.textContent ?? "";
    expect(pill).toContain("hold day 5 of 21");
    expect(pill).toContain("next rebalance 11-23");
    const guard = document.querySelector("[data-drift-guard='true']")?.textContent ?? "";
    // The 10-30 manifest: 6.41% before the guard, 5% threshold, so the bar is full.
    expect(guard).toContain("6.41% of 5%");
    const bar = document.querySelector("[role='progressbar']") as HTMLElement;
    expect(bar.getAttribute("aria-valuenow")).toBe("100");
  });

  it("says all clear when nothing needs a person", () => {
    render(<SnapshotView snapshot={OK} now={NOW_OK} />);
    const banner = document.querySelector("[data-exception-banner='clear']") as HTMLElement;
    expect(banner.textContent).toContain("All clear");
  });

  it("puts a retired name on its own line, one line each", () => {
    const monthly = SERVED.monthly as MonthlyBlock;
    const withHolding: MonthlyBlock = {
      ...monthly,
      holdings: {
        anchor: "2026-10-23",
        as_of: "2026-11-05",
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
    };
    const snapshot: Snapshot = { ...SERVED, monthly: withHolding };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const line = document.querySelector("[data-exception='KVUE']")?.textContent ?? "";
    expect(line).toBe("KVUE: acquired by KMB, symbol inactive, held $13,615, cannot be traded");
  });

  it("draws the cumulative lines, the daily bars and the exposure comparison", () => {
    render(<SnapshotView snapshot={SERVED} now={NOW} />);
    const chart = document.querySelector("[data-overview-cumulative='true']");
    expect(chart).toBeTruthy();
    expect(chart?.querySelectorAll("[data-series]").length).toBe(4);
    expect(chart?.querySelector("[data-overview-rebalance='2026-10-23']")).toBeTruthy();
    const rows = SERVED.attribution?.live?.daily ?? [];
    expect(document.querySelectorAll("[data-daily-bar]").length).toBe(rows.length);
    expect(cumulativePoints(SERVED).length).toBe(rows.length);
    const exposures = document.querySelector("[data-overview-exposures='true']");
    expect(exposures).toBeTruthy();
    expect(exposures?.querySelectorAll("[data-threshold='5']").length).toBe(2);
    expect(exposures?.querySelectorAll("[data-exposure-factor]").length).toBeGreaterThan(10);
  });

  it("opens a title's explanation on the (i)", () => {
    render(<SnapshotView snapshot={OK} now={NOW_OK} />);
    fireEvent.click(screen.getByRole("button", { name: "about NAV" }));
    const popover = document.querySelector("[data-info='NAV']") as HTMLElement;
    expect(popover).toBeTruthy();
    expect(popover.textContent).not.toMatch(/^NAV is/);
    expect(popover.textContent).toContain("equity");
  });

  it("builds no exception line from an expected mismatch", () => {
    const state = runState(OK, NOW_OK);
    const exceptions = classify(OK);
    const reconciled = reconciliation(OK, exceptions);
    expect(overviewExceptions(OK, state, reconciled, exceptions)).toEqual([]);
  });
});
