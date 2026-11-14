// Every card title on every tab opens an (i).
//
// The page's writing standard is that a title is a word and the explanation is one
// tap away: what the number is, why it moves, and one real example. A card that
// grows a title without a popover is a card that reads as a name and nothing else,
// and the reader has to guess. This test enumerates the cards the five tabs render
// and asserts each one carries either the page's (i) or the overview's own Info
// marker, so a new panel cannot be added without one.

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SnapshotView } from "./App";
import type { Snapshot } from "./types";
import served from "../fixtures/snapshot_2026-10-30_evening.json";
import ok from "../fixtures/snapshot_ok.json";
import withActual from "../fixtures/snapshot_actual_holdings.json";

const SERVED = served as unknown as Snapshot;
const OK = ok as unknown as Snapshot;
const ACTUAL = withActual as unknown as Snapshot;
const NOW = new Date("2026-10-30T23:00:00Z");

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
].join(",");

function cardsMissingAnInfo(panel: HTMLElement): string[] {
  const found: string[] = [];
  for (const node of Array.from(panel.querySelectorAll<HTMLElement>(CARDS))) {
    // The construction telemetry's four stats are a definition list inside one
    // disclosure, not cards of their own.
    if (node.closest("dl") && node.matches("[data-card]")) continue;
    const marker =
      node.querySelector("[data-how-to-read]") ?? node.querySelector("[data-info]");
    if (!marker) {
      const title = (node.querySelector("h2, h3, dt, p, div")?.textContent ?? "").trim();
      found.push(`${node.tagName.toLowerCase()} ${title.slice(0, 40)}`);
    }
  }
  return found;
}

function audit(snapshot: Snapshot): void {
  render(<SnapshotView snapshot={snapshot} now={NOW} />);
  for (const view of VIEWS) {
    const panel = document.querySelector(`#panel-${view}`) as HTMLElement;
    expect(panel, view).toBeTruthy();
    const cards = panel.querySelectorAll(CARDS);
    // Every tab but "Since the rebalance" always draws cards; that one draws none
    // on a document with no anchored block, which is the point of its own notice.
    if (view !== "rebalance") {
      expect(cards.length, `${view} drew no cards at all`).toBeGreaterThan(0);
    }
    expect(cardsMissingAnInfo(panel), view).toEqual([]);
  }
  document.body.innerHTML = "";
}

describe("the (i) on every card title", () => {
  it("is on every card of every tab for the served hold-day document", () => {
    audit(SERVED);
  });

  it("is on every card of the document that carries no anchored block", () => {
    // The fallback branches are their own panels: the nightly hedge footprint,
    // the sector net with no account read, and trades by reason.
    audit(OK);
    audit(ACTUAL);
  });
});
