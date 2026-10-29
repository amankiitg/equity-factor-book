// The anchored panels, rendered from the document the evening actually published.
//
// The fixture is the 2026-10-29 close: the document the page was served, with the
// real anchored block in it. Nothing here is hand-built, because the hand-built
// fixture is what let the panels pass in the suite while the live page rendered the
// nightly ones: the test and the page disagreed about the shape of a real document.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { incompleteFields, MonthlyPanels } from "./Monthly";
import type { MonthlyBlock, Snapshot } from "./types";
import served from "../fixtures/snapshot_2026-10-29_evening.json";

const SERVED = served as unknown as Snapshot;
const MONTHLY = SERVED.monthly as MonthlyBlock;
if (!MONTHLY) throw new Error("the served fixture carries no monthly block");

describe("the anchored panels", () => {
  it("renders the four 2026-10-23 flips as four rows, each with both legs", () => {
    render(<MonthlyPanels monthly={MONTHLY} />);
    const rows = document.querySelectorAll("[data-flip]");
    expect(rows).toHaveLength(4);
    expect(
      MONTHLY.bridge_anchor?.flip_rows.map((row) => row.ticker).sort(),
    ).toEqual(["CCL", "F", "GEHC", "VZ"]);
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
    render(<MonthlyPanels monthly={MONTHLY} />);
    const strip = document.querySelector("[data-cadence]")?.textContent ?? "";
    expect(strip).toContain("4 of 21");
    expect(strip).toContain("2026-10-23");
    expect(strip).toContain("2026-11-23");
    // The guard looked and left the book alone: 3.0% carried against the 5% it is
    // set to, and the reading has to say both numbers rather than "no threshold".
    expect(strip).toContain("3.02% of 5.00%");
    expect(strip).toContain("did not run");
  });

  it("reports the rebalance's own numbers and what is still owed", () => {
    render(<MonthlyPanels monthly={MONTHLY} />);
    const card = document.querySelector("[data-rebalance]")?.textContent ?? "";
    expect(card).toContain("224");
    expect(card).toContain("4.8 bp");
    expect(card).toContain("11.0 bp");
    // Sent legs are counted apart from the ones under the $250 minimum, which were
    // never meant to be sent and are not owed.
    expect(card).toContain("208 of 208 sent legs filled");
    expect(card).toContain("16 under $250 not sent");
    expect(card).toContain("$2,253");
    expect(card).toContain("nothing owed");
  });

  it("measures the drift from the target and prices closing it", () => {
    render(<MonthlyPanels monthly={MONTHLY} />);
    const drift = document.querySelector("[data-drift]")?.textContent ?? "";
    expect(drift).toContain("2.30%");
    expect(drift).toContain("$44,801");
    expect(drift).toContain("$15");
    expect(screen.getByText("KLAC")).toBeTruthy();
  });

  it("renders every leg since the anchor by why it went", () => {
    render(<MonthlyPanels monthly={MONTHLY} />);
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
