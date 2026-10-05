// The three rules the redesign added, each pinned where it can fail.
//
// The severity rule is the one with teeth: red is reserved for a run that failed or
// stopped, and everything else that needs attention is amber. A page that paints a
// positions drift the same red as a stopped loop has taught its reader that red is
// noise, and the next red is the one that matters. The other two are the rule for a
// missing value (never a fabricated zero) and the order the actual-holdings table
// opens in.

import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SnapshotView, runTone } from "./App";
import type { Snapshot } from "./types";
import closed from "../fixtures/snapshot_market_closed.json";
import errored from "../fixtures/snapshot_error.json";
import expired from "../fixtures/snapshot_expired.json";
import noBook from "../fixtures/snapshot_no_book.json";
import ok from "../fixtures/snapshot_ok.json";
import stale from "../fixtures/snapshot_stale_stopped.json";
import withActual from "../fixtures/snapshot_actual_holdings.json";

const OK = ok as unknown as Snapshot;
const ACTUAL = withActual as unknown as Snapshot;
const NONE = noBook as unknown as Snapshot;
const NOW = new Date("2026-09-21T23:00:00Z");
const LATE = new Date("2027-01-01T00:00:00Z");

const alerts = (): HTMLElement[] =>
  Array.from(document.querySelectorAll("[role='alert']")) as HTMLElement[];
const panel = (hook: string): HTMLElement =>
  document.querySelector(`[data-alert='${hook}']`) as HTMLElement;

describe("severity", () => {
  it("reserves red for a run that failed or stopped", () => {
    expect(runTone("error")).toBe("bad");
    expect(runTone("stale_stopped")).toBe("bad");
    // Needs a look, is not a broken loop, and is therefore amber or informational.
    expect(runTone("expired")).toBe("warn");
    expect(runTone("catch_up")).toBe("info");
    expect(runTone("market_closed")).toBe("info");
    expect(runTone("ok")).toBe("good");
  });

  it("paints a stopped run red, and only that", () => {
    render(<SnapshotView snapshot={stale as unknown as Snapshot} now={NOW} />);
    const run = panel("run");
    expect(run.getAttribute("data-tone")).toBe("bad");
    expect(run.textContent).toContain("STALE STOP");
    expect(alerts().length).toBe(1);
    expect(alerts()[0]).toBe(run);

    render(<SnapshotView snapshot={errored as unknown as Snapshot} now={NOW} />);
    expect(panel("run").getAttribute("data-tone")).toBe("bad");
  });

  it("paints a late snapshot amber rather than red", () => {
    // The run did not fail: nothing has run yet. It is loud, and it is not the same
    // statement as a loop that stopped, so it must not take the same colour.
    render(<SnapshotView snapshot={expired as unknown as Snapshot} now={LATE} />);
    const run = panel("run");
    expect(run.getAttribute("data-tone")).toBe("warn");
    expect(run.textContent).toContain("no run for the session that should have closed");
    expect(alerts()).toEqual([]);
  });

  it("paints a closed day as information, not as a failure", () => {
    render(
      <SnapshotView snapshot={closed as unknown as Snapshot} now={new Date("2026-11-26T23:00:00Z")} />,
    );
    const run = panel("run");
    expect(run.getAttribute("data-tone")).toBe("info");
    expect(run.textContent).toContain("market closed");
    expect(alerts()).toEqual([]);
  });

  it("paints a routine positions drift amber, not red", () => {
    const snapshot: Snapshot = {
      ...OK,
      positions: {
        ...OK.positions,
        matches: false,
        note: "mismatch: the account holds 2 name(s) and the store 150",
      },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const positions = panel("positions");
    expect(positions.getAttribute("data-tone")).toBe("warn");
    expect(positions.textContent).toContain("mismatch: the account holds 2 name(s)");
    // The clean run itself is not an alert, and the drift is not one either.
    expect(panel("run").getAttribute("data-tone")).toBe("good");
    expect(alerts()).toEqual([]);
  });

  it("paints the unfilled legs amber and lists each one", () => {
    const block = ACTUAL.actual_holdings;
    expect(block?.fills?.unfilled.length).toBeGreaterThan(0);
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    const misses = panel("misses");
    expect(misses.getAttribute("data-tone")).toBe("warn");
    expect(alerts()).toEqual([]);
    for (const line of block?.fills?.unfilled ?? []) {
      expect(misses.textContent).toContain(line);
    }
  });
});

describe("a missing value", () => {
  it("says n/a on the metrics row rather than zero", () => {
    const snapshot: Snapshot = {
      ...OK,
      book: { ...OK.book, gross: null, gross_notional: null, net: null, expected_cost_bps: null, full_book_gross: null },
      breadth: { ...OK.breadth, n_eff_kept: null, n_eff_full_book: null },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const cards = document.querySelector("[data-cards='true']") as HTMLElement;
    const card = (label: string): HTMLElement =>
      cards.querySelector(`[data-card='${label}']`) as HTMLElement;
    for (const label of ["gross", "net", "n_eff_kept", "n_eff_full_book", "expected cost", "full book before the floor"]) {
      expect(card(label).textContent, label).toContain("n/a");
      // Not a zero wearing a sign, and not a rounding artefact.
      expect(card(label).textContent, label).not.toMatch(/0\.00|-\$0|\$0\b/);
    }
  });

  it("shows a book that is flat to machine precision as 0.00%, never -0.00%", () => {
    // Every fixture's net is a few epsilons off zero, which (value * 100).toFixed(2)
    // renders as "-0.00%": a sign on nothing, which reads as a small short book.
    expect(OK.book.net).not.toBe(0);
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const net = document.querySelector("[data-card='net']") as HTMLElement;
    expect(net.textContent).toContain("0.00%");
    expect(net.textContent).not.toContain("-0.00%");
  });

  it("says n/a for a factor the snapshot does not carry, never 0.0000", () => {
    const snapshot: Snapshot = {
      ...OK,
      exposures_before_hedge: { ...OK.exposures_before_hedge, momentum: null },
      exposures_after_hedge: { ...OK.exposures_after_hedge, momentum: null },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const table = document.querySelector("[data-factor='momentum']") as HTMLElement;
    const cells = Array.from(table.querySelectorAll("td")).map((cell) => cell.textContent);
    expect(cells[1]).toBe("n/a");
    expect(cells[2]).toBe("n/a");
  });

  it("leaves the no-book page free of zeros and of NaN", () => {
    render(<SnapshotView snapshot={NONE} now={NOW} />);
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("NaN");
    expect(text).not.toContain("undefined");
    expect(text).not.toContain("0.0000");
    expect(text).not.toContain("$0");
    expect(text).not.toContain("T00:00:00");
  });
});

describe("the actual-holdings table", () => {
  it("opens on the largest absolute drift, largest first", () => {
    const block = ACTUAL.actual_holdings;
    expect(block).toBeTruthy();
    if (!block) return;
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    fireEvent.click(document.querySelector("[data-tab='actual']") as HTMLElement);
    const order = Array.from(document.querySelectorAll("[data-section='actual-holdings'] tbody [data-ticker]")).map(
      (row) => row.getAttribute("data-ticker") ?? "",
    );

    // Recomputed from the two books rather than typed in: a held name the target
    // has dropped drifts by its whole position, and a target name the account does
    // not hold drifts by the whole target.
    const held = new Map(block.names.map((entry) => [entry.ticker, entry.weight ?? null]));
    const target = new Map(ACTUAL.book.names.map((name) => [name.ticker, name.weight ?? null]));
    const expected = [...new Set([...held.keys(), ...target.keys()])]
      .map((ticker) => {
        const mine = held.get(ticker) ?? null;
        const theirs = target.get(ticker) ?? null;
        return { ticker, drift: mine === null ? -(theirs ?? 0) : mine - (theirs ?? 0) };
      })
      .sort((a, b) => Math.abs(b.drift) - Math.abs(a.drift) || a.ticker.localeCompare(b.ticker))
      .map((row) => row.ticker);

    expect(order).toEqual(expected);
    // And the table is genuinely ordered by drift, not by the file's own order.
    expect(order).not.toEqual([...held.keys(), ...[...target.keys()].filter((t) => !held.has(t))]);
  });

  it("re-sorts when another column is asked for", () => {
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    fireEvent.click(document.querySelector("[data-tab='actual']") as HTMLElement);
    const order = (): string[] =>
      Array.from(document.querySelectorAll("[data-section='actual-holdings'] tbody [data-ticker]")).map(
        (row) => row.getAttribute("data-ticker") ?? "",
      );
    const byDrift = order();
    fireEvent.click(document.querySelector("[data-sort='ticker']") as HTMLElement);
    expect(order()).toEqual([...byDrift].sort((a, b) => a.localeCompare(b)));
  });
});
