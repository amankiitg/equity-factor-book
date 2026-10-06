// The bridge panel, against the two fixtures built for it.
//
// The 2026-10-05 session's own arithmetic is what the reader sees on the ordinary
// day: one line from the account the evening read to the account the next morning
// read, with the names the gap is made of behind it. The second fixture is the
// same morning with one name missing from the account and nothing explaining it,
// which is the case the block's own identities exist to catch, and the page has to
// draw that in amber with both sides of the failing check rather than as a fifth
// number to trust.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SnapshotView } from "./App";
import { count, dollars } from "./format";
import type { Snapshot } from "./types";
import broken from "../fixtures/snapshot_bridge_broken.json";
import rejected from "../fixtures/snapshot_fills_rejected.json";

const REAL = rejected as unknown as Snapshot;
const BROKEN = broken as unknown as Snapshot;
const NOW = new Date("2026-10-06T16:00:00Z");

const bridge = (snapshot: Snapshot): HTMLElement =>
  document.querySelector("[data-section='bridge']") as HTMLElement;

const line = (snapshot: Snapshot): string =>
  (bridge(snapshot).querySelector("[data-bridge-line='true']") as HTMLElement).textContent ??
  "";

describe("the book bridge", () => {
  it("draws the session's own numbers as one line of arithmetic", () => {
    render(<SnapshotView snapshot={REAL} now={NOW} />);
    const block = REAL.bridge as NonNullable<Snapshot["bridge"]>;

    const text = line(REAL);
    // Every count the fixture carries, printed: the reader is meant to be able to
    // check the line against the three panels around it without a calculator.
    expect(text).toContain(`held ${count(block.held_before ?? 0)}`);
    expect(text).toContain(`+${count(block.opened ?? 0)} opened`);
    expect(text).toContain(`-${count(block.exited ?? 0)} exited`);
    expect(text).toContain(`${count(block.changed ?? 0)} changed`);
    expect(text).toContain(
      `${count(block.under_minimum ?? 0)} under ${dollars(block.under_minimum_usd ?? 0)}`,
    );
    expect(text).toContain(`${count(block.orders_sent ?? 0)} orders`);
    expect(text).toContain(
      `${count(block.filled ?? 0)} filled of ${count(block.orders_sent ?? 0)}`,
    );
    expect(text).toContain(`held ${count(block.held_after ?? 0)}`);
    // The numbers themselves, so a page that printed two of its own figures in the
    // right shape could not pass this.
    expect(text).toContain("201");
    expect(text).toContain("188");
    expect(text).toContain("197");
    expect(text).toContain("199");
  });

  it("is plain when the block's own checks hold, and says so", () => {
    render(<SnapshotView snapshot={REAL} now={NOW} />);
    expect(bridge(REAL).getAttribute("data-bridge")).toBe("reconciled");
    expect(bridge(REAL).getAttribute("data-tone")).toBe("plain");
    expect(bridge(REAL).querySelector("[data-bridge-check='failed']")).toBeNull();
    // The gap's itemised names are behind the disclosure rather than on the line:
    // the two reversed names and the removal, which is what `held after` less
    // `book` is made of.
    expect(bridge(REAL).textContent).toContain("INVH");
    expect(bridge(REAL).textContent).toContain("PSKY");
    // ... and every identity is listed with both of its sides.
    const identities = bridge(REAL).querySelectorAll("[data-identity]");
    expect(identities.length).toBe(6);
    for (const identity of identities) {
      expect(identity.getAttribute("data-holds")).toBe("true");
    }
  });

  it("turns amber and names the two sides when a check fails", () => {
    render(<SnapshotView snapshot={BROKEN} now={NOW} />);
    const block = BROKEN.bridge as NonNullable<Snapshot["bridge"]>;
    const panel = bridge(BROKEN);

    expect(block.holds).toBe(false);
    expect(panel.getAttribute("data-bridge")).toBe("broken");
    expect(panel.getAttribute("data-tone")).toBe("warn");
    const failed = panel.querySelector("[data-bridge-check='failed']") as HTMLElement;
    expect(failed).toBeTruthy();
    // The failing identity's name and both of its numbers, which is what turns the
    // amber from a warning into something a reader can act on.
    const check = block.identities.find((item) => !item.holds);
    expect(failed.textContent).toContain(check?.name);
    expect(failed.textContent).toContain(String(check?.left));
    expect(failed.textContent).toContain(String(check?.right));
    // ... and the name that is in neither list, which is the finding itself.
    expect(failed.textContent).toContain("AEP");
    // The one line is still drawn: the counts are the session's own even when the
    // arithmetic does not close.
    expect(line(BROKEN)).toContain(`held ${count(block.held_before ?? 0)}`);
  });

  it("is absent from a snapshot no run has written a bridge for", () => {
    // An evening whose bridge failed to build publishes no block at all, and the
    // page has to leave the space rather than draw zeroes: a bridge of zeroes reads
    // as an evening that moved nothing.
    const without: Snapshot = { ...REAL };
    delete (without as unknown as Record<string, unknown>).bridge;
    render(<SnapshotView snapshot={without} now={NOW} />);
    expect(document.querySelector("[data-section='bridge']")).toBeNull();
  });

  it("says the fills are the morning's when the evening has not been completed", () => {
    // Half a bridge is what the page shows for the sixteen hours between the
    // evening and the next 15:30 UTC, so the line has to read as the evening's
    // statement rather than as a morning with zero fills. The block here is the
    // same session's own, with the morning's three fields removed - the shape
    // `live.bridge.evening` produces, which `tests/test_e11_bridge.py` pins.
    const block = REAL.bridge as NonNullable<Snapshot["bridge"]>;
    const evening: Snapshot = {
      ...REAL,
      bridge: {
        ...block,
        seen_by: "evening",
        filled: null,
        did_not_fill: null,
        held_after: null,
        removed_without_order: [],
        unexplained: [],
        identities: block.identities.slice(0, 4),
        holds: true,
      },
    };
    render(<SnapshotView snapshot={evening} now={NOW} />);

    const text = line(evening);
    // The four counts the evening knows, and no `filled of sent`: an order count
    // with no fills beside it is the evening's own statement, and a zero would be
    // a claim about a morning that has not run.
    expect(text).toContain(`${count(block.orders_sent ?? 0)} orders`);
    expect(text).toContain("fills from the morning");
    expect(text).not.toContain(`${count(block.filled ?? 0)} filled`);
    expect(text).not.toContain(`held ${count(block.held_after ?? 0)}`);
    expect(bridge(evening).getAttribute("data-bridge")).toBe("reconciled");
    expect(bridge(evening).querySelectorAll("[data-identity]").length).toBe(4);
    expect(bridge(evening).textContent).toContain("the morning adds the account");
  });

  it("opens the names behind the line when asked", () => {
    render(<SnapshotView snapshot={REAL} now={NOW} />);
    const summary = bridge(REAL).querySelector("summary") as HTMLElement;
    const details = bridge(REAL).querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    fireEvent.click(summary);
    expect(details.open).toBe(true);
    // The removal carries its own shares and dollars: the evidence under the count.
    const removed = bridge(REAL).querySelector("[data-removed='PSKY']") as HTMLElement;
    expect(removed.textContent).toContain(dollars(3211.814835));
    expect(screen.getByText(/closed tonight, reopening next evening/)).toBeTruthy();
  });
});
