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
import type { BridgeBlock, Snapshot } from "./types";
import brokenFixture from "../fixtures/snapshot_bridge_broken.json";
import closed from "../fixtures/snapshot_market_closed.json";
import errored from "../fixtures/snapshot_error.json";
import expired from "../fixtures/snapshot_expired.json";
import noBook from "../fixtures/snapshot_no_book.json";
import ok from "../fixtures/snapshot_ok.json";
import stale from "../fixtures/snapshot_stale_stopped.json";
import withActual from "../fixtures/snapshot_actual_holdings.json";

const OK = ok as unknown as Snapshot;
const ACTUAL = withActual as unknown as Snapshot;
const BROKEN = brokenFixture as unknown as Snapshot;
const BROKEN_BRIDGE = BROKEN.bridge as BridgeBlock;
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

  it("keeps a mismatch the document explains out of amber, and its count visible", () => {
    // The brief's rule: only the unexpected names turn amber. This snapshot's
    // mismatch is exactly its own deferred reversals, so the reconciliation reads
    // clean-with-explained, the names are collapsed into one line, and the run's own
    // panel is untouched by it.
    const snapshot: Snapshot = {
      ...OK,
      bridge: {
        close: "2026-09-21",
        seen_by: "evening",
        book: 150,
        held_before: 150,
        in_both: 149,
        opened: 1,
        exited: 1,
        changed: 10,
        under_minimum: 0,
        orders_sent: 11,
        filled: null,
        did_not_fill: null,
        held_after: null,
        under_minimum_usd: 250,
        // The document's own list, which is what classifies the name below.
        reversals_pending: ["ZZZZ"],
        removed_without_order: [],
        unexplained: [],
        identities: [
          { name: "in both + opened = the book", left: 150, right: 150, holds: true },
        ],
        holds: true,
      },
      positions: {
        ...OK.positions,
        matches: false,
        missing_at_broker: ["ZZZZ"],
        missing_in_store: [],
        note: "mismatch: the account holds 2 name(s) and the store 150",
      },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const reconciled = panel("reconciliation");
    expect(reconciled.getAttribute("data-tone")).toBe("good");
    expect(reconciled.textContent).toContain("clean, with explained mismatches");
    // The writer's own sentence is kept: the page classifies the names, it does not
    // paraphrase what the run said about them.
    expect(reconciled.textContent).toContain("mismatch: the account holds 2 name(s)");
    const expected = reconciled.querySelector("[data-expected='true']") as HTMLElement;
    expect(expected).toBeTruthy();
    expect(expected.textContent).toContain("1 expected: deferred reversal");
    expect(expected.textContent).toContain("ZZZZ");
    expect(reconciled.querySelector("[data-alert='positions']")).toBeNull();
    expect(panel("run").getAttribute("data-tone")).toBe("good");
    expect(alerts()).toEqual([]);
  });

  it("paints a mismatch nothing explains amber, and names it", () => {
    const snapshot: Snapshot = {
      ...OK,
      positions: {
        ...OK.positions,
        matches: false,
        missing_at_broker: ["QQQQ"],
        missing_in_store: [],
        note: "mismatch: the account holds 2 name(s) and the store 150",
      },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const reconciled = panel("reconciliation");
    expect(reconciled.getAttribute("data-tone")).toBe("warn");
    const unexpected = reconciled.querySelector("[data-alert='positions']") as HTMLElement;
    expect(unexpected.getAttribute("data-tone")).toBe("warn");
    expect(unexpected.textContent).toContain("QQQQ");
    expect(unexpected.textContent).toContain("nothing on the page explains");
    // Amber, not red: a mismatch is a fact to read, not a broken loop.
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

describe("the notification state", () => {
  it("says nothing when the message went out, or has not yet been sent", () => {
    // The evening writes the snapshot before it sends, so `pending` is what the
    // document carries on a clean evening and `sent` is what the morning writes
    // back. Neither is news: a strip that names the notification every evening is
    // one the reader stops reading, and the one that matters is the failure.
    for (const notifyStatus of ["pending", "sent", null]) {
      document.body.innerHTML = "";
      const snapshot: Snapshot = {
        ...OK,
        run_status: { ...OK.run_status, notify_status: notifyStatus },
      };
      render(<SnapshotView snapshot={snapshot} now={NOW} />);
      expect(
        document.querySelector("[data-flag='notify']"),
        `notify_status ${notifyStatus} still prints a notify field`,
      ).toBeNull();
      expect(
        document.querySelector("[data-note='notify-failed']"),
        `notify_status ${notifyStatus} claims a failure`,
      ).toBeNull();
    }
  });

  it("warns when the evening's message never went out", () => {
    const snapshot: Snapshot = {
      ...OK,
      run_status: { ...OK.run_status, notify_status: "failed" },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const note = document.querySelector("[data-note='notify-failed']") as HTMLElement;
    expect(note).toBeTruthy();
    expect(note.textContent).toContain("never told");
    // The close it belongs to, not a generic warning: the owner has to know which
    // evening's message is missing.
    expect(note.textContent).toContain(String(OK.target_close).slice(0, 10));
    // A failed send is not a failed run: the book is on the page and green.
    expect(panel("run").getAttribute("data-tone")).toBe("good");
  });
});

describe("a missing value", () => {
  it("says n/a on the metrics row rather than zero", () => {
    const snapshot: Snapshot = {
      ...OK,
      book: {
        ...OK.book,
        gross: null,
        gross_notional: null,
        net: null,
        expected_cost_bps: null,
        full_book_gross: null,
        full_book_net: null,
        full_book_achieved_annual_vol: null,
      },
      breadth: { ...OK.breadth, n_eff_kept: null, n_eff_full_book: null },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    const cards = document.querySelector("[data-cards='true']") as HTMLElement;
    const card = (label: string): HTMLElement =>
      cards.querySelector(`[data-card='${label}']`) as HTMLElement;
    for (const label of [
      "gross",
      "net",
      "n_eff_kept",
      "turnover",
      "expected-expense",
      "n_eff_full_book",
      "full-book-gross",
      "full-book-net",
      "full-book-vol",
    ]) {
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

describe("the two claims the strip separates", () => {
  /** A snapshot whose account-versus-store check fails with the names of 10-09. */
  const mismatched: Snapshot = {
    ...OK,
    positions: {
      matches: false,
      max_abs_drift: 976.94,
      missing_at_broker: ["BEN", "F", "VZ", "ZTS"],
      missing_in_store: ["WBD"],
      n_broker: 172,
      n_store: 175,
      note: "mismatch: the account holds 172 name(s) and the store 175",
      source: "alpaca paper account",
    },
    bridge: {
      ...BROKEN_BRIDGE,
      reversals_pending: ["INVH"],
      removed_without_order: [],
      identities: (BROKEN.bridge?.identities ?? []).map((identity) => ({
        ...identity,
        holds: true,
      })),
    },
  };

  it("paints the reconciliation pill, not the proposal pill, for a mismatch", () => {
    render(<SnapshotView snapshot={mismatched} now={NOW} />);
    const strip = document.querySelector("[data-strip='status']") as HTMLElement;
    // The proposal run is clean and says so: a failing reconciliation is not a
    // failing run, and reading one as the other is the mistake the split fixes.
    const proposal = document.querySelector("[data-pill='status']") as HTMLElement;
    expect(proposal.textContent).toContain("proposal run");
    expect(proposal.getAttribute("data-tone")).toBe("good");
    const reconciled = document.querySelector("[data-pill='reconciliation']") as HTMLElement;
    expect(reconciled.getAttribute("data-tone")).toBe("warn");
    expect(reconciled.getAttribute("data-reconciliation")).toBe("fail");
    expect(reconciled.textContent).toContain("1 unresolved");
    // And the strip's own colour is the worse of the two, because that is the
    // element read without reading.
    expect(strip.getAttribute("data-tone")).toBe("warn");
  });

  it("counts the two kinds of mismatch apart, on both tabs", () => {
    render(<SnapshotView snapshot={mismatched} now={NOW} />);
    const count = document.querySelector("[data-flag='exceptions']") as HTMLElement;
    expect(count.textContent).toBe("5 unexpected mismatches");
    const panel_ = panel("reconciliation");
    // Every name is listed with its direction, because the two directions are
    // different failures: the store holding what the account does not is the
    // dangerous one.
    for (const ticker of ["BEN", "F", "VZ", "ZTS", "WBD"]) {
      expect(panel_.textContent).toContain(ticker);
    }
    expect(panel_.textContent).toContain("the store holds it and the account does not");
    expect(panel_.textContent).toContain("the account holds it and the store does not");
    // The classes the document cannot decide are stated as such rather than
    // silently dropped.
    expect(
      (document.querySelector("[data-unchecked='true']") as HTMLElement).textContent,
    ).toContain("previous close's bridge.reversals_pending");
  });

  it("collapses a mismatch every name of which the document explains", () => {
    const explained: Snapshot = {
      ...mismatched,
      positions: {
        ...mismatched.positions,
        missing_at_broker: ["ZTS"],
        missing_in_store: [],
        n_broker: 174,
        n_store: 175,
      },
      bridge: {
        ...(mismatched.bridge as BridgeBlock),
        reversals_pending: ["ZTS"],
      },
    };
    render(<SnapshotView snapshot={explained} now={NOW} />);
    const strip = document.querySelector("[data-strip='status']") as HTMLElement;
    expect(strip.getAttribute("data-tone")).toBe("good");
    expect(document.querySelector("[data-alert='positions']")).toBeNull();
    const line = document.querySelector("[data-expected='true']") as HTMLElement;
    expect(line.textContent).toContain("1 expected: deferred reversal");
    expect(line.textContent).toContain("ZTS");
  });

  it("says which account read is on the page, and what it certifies", () => {
    // The evening reads the account before it sends, so an evening snapshot
    // cannot certify the fills; the morning's can. A reader who mistakes the
    // first for the second reads a plan as a position.
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    const line = document.querySelector("[data-flag='account-read']") as HTMLElement;
    expect(line).toBeTruthy();
    const read = ACTUAL.actual_holdings?.read_by ?? "";
    expect(line.textContent).toContain(read === "morning" ? "morning, after the fills" : "evening");
    if (read === "morning") {
      expect(line.textContent).toContain("the fills exist");
      expect(line.textContent).toContain(String(ACTUAL.actual_holdings?.close).slice(0, 10));
    }

    document.body.innerHTML = "";
    const evening: Snapshot = {
      ...ACTUAL,
      actual_holdings: {
        ...(ACTUAL.actual_holdings as NonNullable<Snapshot["actual_holdings"]>),
        read_by: "evening",
        fills: null,
      },
    };
    render(<SnapshotView snapshot={evening} now={NOW} />);
    const stated = document.querySelector("[data-flag='account-read']") as HTMLElement;
    expect(stated.textContent).toContain("evening, before the orders");
    expect(stated.textContent).toContain("cannot certify the fills");
  });

  it("calls the account paper, and never live", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    // The fixture is a dry run, and a dry run says the louder thing.
    expect((document.querySelector("[data-flag='mode']") as HTMLElement).textContent).toContain(
      "DRY RUN",
    );
    document.body.innerHTML = "";
    render(<SnapshotView snapshot={{ ...OK, dry_run: false }} now={NOW} />);
    const mode = document.querySelector("[data-flag='mode']") as HTMLElement;
    expect(mode.textContent).toContain("PAPER");
    expect(mode.textContent).toContain("paper account");
    // "live" is the word the redesign removed: it claims real capital.
    for (const element of Array.from(document.querySelectorAll("[data-strip='status'] *"))) {
      expect(element.textContent ?? "").not.toContain("live");
    }
  });
});
