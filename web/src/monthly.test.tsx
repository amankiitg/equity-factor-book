// The anchored panels: the four flips as four rows, and nothing at all without a block.
//
// The fixture in the flip test is the 2026-10-23 rebalance as the store holds it: CCL
// and GEHC short at the account read and long in the target, F and VZ the other way,
// each closed on 2026-10-23 and opened on 2026-10-26, and the account on the target
// side at the 2026-10-28 read.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MonthlyPanels } from "./Monthly";
import type { MonthlyBlock } from "./types";

const FLIPS: MonthlyBlock = {
  anchor: { close: "2026-10-23", day: "cadence", account_read: "2026-10-28" },
  cadence_strip: {
    k: 21,
    offset: 3,
    sessions_since: 3,
    last_rebalance: "2026-10-23",
    next_rebalance: "2026-11-23",
    guard: {
      worst_abs_exposure: 0.0341,
      threshold: null,
      fired: false,
      ran: false,
    },
  },
  rebalance_card: {
    close: "2026-10-23",
    orders: 224,
    notional: 546256.69,
    pct_nav: 0.5576,
    expected_cost_bps: 4.76,
    expected_cost_usd: 466.51,
    realized_cost_bps: 10.93,
    legs_total: 224,
    legs_complete: 208,
    legs_incomplete: 16,
    dollars_owed: 5534.48,
  },
  bridge_anchor: {
    before_dollars: 973233.81,
    after_dollars: 986541.28,
    opened: 50,
    exited: 28,
    resized: 142,
    flipped: 4,
    under_minimum: 0,
    complete_flips: 4,
    identities: [],
    holds: true,
    flip_rows: [
      {
        ticker: "GEHC",
        from_side: "short",
        to_side: "long",
        close_dollars: 2012.8,
        close_filled: "2026-10-23",
        open_dollars: 2328.08,
        open_filled: "2026-10-26",
        now_dollars: 2489.37,
        on_target_side: true,
        complete: true,
      },
      {
        ticker: "VZ",
        from_side: "long",
        to_side: "short",
        close_dollars: 961.39,
        close_filled: "2026-10-23",
        open_dollars: 2417.71,
        open_filled: "2026-10-26",
        now_dollars: -2431.69,
        on_target_side: true,
        complete: true,
      },
      {
        ticker: "F",
        from_side: "long",
        to_side: "short",
        close_dollars: 637.33,
        close_filled: "2026-10-23",
        open_dollars: 1609.03,
        open_filled: "2026-10-26",
        now_dollars: -1624.26,
        on_target_side: true,
        complete: true,
      },
      {
        ticker: "CCL",
        from_side: "short",
        to_side: "long",
        close_dollars: 605.47,
        close_filled: "2026-10-23",
        open_dollars: 677.7,
        open_filled: "2026-10-26",
        now_dollars: 687.27,
        on_target_side: true,
        complete: true,
      },
    ],
  },
  drift: {
    half_turnover_pct: 0.0154,
    half_turnover_usd: 15059.46,
    traded_usd: 30118.92,
    estimated_cost_usd: 9.95,
    largest: [
      { ticker: "KLAC", weight_now: -0.0107, weight_target: -0.0096, usd: -1164.42 },
    ],
  },
  since_anchor: {
    trades_by_reason: [
      { reason: "rebalance", legs: 224, usd: 546256.69 },
      { reason: "reversal second leg", legs: 12, usd: 10672.48 },
      { reason: "guard", legs: 167, usd: 9973.87 },
      { reason: "carried leg", legs: 1, usd: 269.37 },
    ],
  },
  tonight: { forced_legs: 1, forced_usd: 269.37 },
  rebalance_dates: ["2026-10-23"],
};

describe("the anchored panels", () => {
  it("renders the four 2026-10-23 flips as four rows, each with both legs", () => {
    render(<MonthlyPanels monthly={FLIPS} />);
    const rows = document.querySelectorAll("[data-flip]");
    expect(rows).toHaveLength(4);
    expect(FLIPS.bridge_anchor?.flip_rows.map((row) => row.ticker)).toEqual([
      "GEHC",
      "VZ",
      "F",
      "CCL",
    ]);
    for (const ticker of ["CCL", "F", "GEHC", "VZ"]) {
      const row = document.querySelector(`[data-flip="${ticker}"]`);
      expect(row).not.toBeNull();
      expect(row?.textContent).toContain("to");
      expect(row?.textContent).toContain("complete");
    }
    // Each row carries both legs' dollars, not one leg and an exit.
    const ccl = document.querySelector('[data-flip="CCL"]')?.textContent ?? "";
    expect(ccl).toContain("$605");
    expect(ccl).toContain("$678");
  });

  it("says which hold day it is, and when the next rebalance is", () => {
    render(<MonthlyPanels monthly={FLIPS} />);
    const strip = document.querySelector("[data-cadence]")?.textContent ?? "";
    expect(strip).toContain("3 of 21");
    expect(strip).toContain("2026-10-23");
    expect(strip).toContain("2026-11-23");
    expect(strip).toContain("did not run");
  });

  it("reports the rebalance's own numbers and what is still owed", () => {
    render(<MonthlyPanels monthly={FLIPS} />);
    const card = document.querySelector("[data-rebalance]")?.textContent ?? "";
    expect(card).toContain("224");
    expect(card).toContain("4.8 bp");
    expect(card).toContain("10.9 bp");
    expect(card).toContain("208 of 224 legs");
    expect(card).toContain("$5,534");
  });

  it("measures the drift from the target and prices closing it", () => {
    render(<MonthlyPanels monthly={FLIPS} />);
    const drift = document.querySelector("[data-drift]")?.textContent ?? "";
    expect(drift).toContain("1.54%");
    expect(drift).toContain("$30,119");
    expect(drift).toContain("$10");
    expect(screen.getByText("KLAC")).toBeTruthy();
  });

  it("renders every leg since the anchor by why it went", () => {
    render(<MonthlyPanels monthly={FLIPS} />);
    const trades = document.querySelector("[data-trades-reason]")?.textContent ?? "";
    for (const reason of [
      "rebalance",
      "reversal second leg",
      "guard",
      "carried leg",
    ]) {
      expect(trades).toContain(reason);
    }
    expect(document.querySelector("[data-tonight]")?.textContent).toContain("1 forced leg");
  });

  it("renders nothing at all when the document carries no block", () => {
    const { container } = render(<MonthlyPanels monthly={null} />);
    expect(container.querySelector("[data-monthly]")).toBeNull();
    expect(container.textContent).toBe("");
  });
});
