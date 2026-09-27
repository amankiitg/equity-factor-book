// The page against the committed fixtures.
//
// The fixtures are written by the Python writer (`scripts/make_web_fixtures.py`)
// from a real proposal, so these tests drive the page with the document the cron
// actually uploads rather than a hand-made shape. Every state the owner has to be
// able to tell apart is here: clean, late, stale-stopped, errored and missing.

import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App, { health, SnapshotView } from "./App";
import type { Snapshot } from "./types";
import catchUp from "../fixtures/snapshot_catch_up.json";
import closed from "../fixtures/snapshot_market_closed.json";
import errored from "../fixtures/snapshot_error.json";
import expired from "../fixtures/snapshot_expired.json";
import ok from "../fixtures/snapshot_ok.json";
import stale from "../fixtures/snapshot_stale_stopped.json";

const OK = ok as unknown as Snapshot;
const NOW = new Date("2026-09-21T23:00:00Z");

afterEach(() => {
  vi.restoreAllMocks();
});

describe("health", () => {
  it("passes a clean run inside its window", () => {
    expect(health(OK, NOW).ok).toBe(true);
  });

  it("fails a run that stopped on staleness, with the failing input named", () => {
    const state = health(stale as unknown as Snapshot, NOW);
    expect(state.ok).toBe(false);
    expect(state.headline).toContain("STALE STOP");
    expect(state.detail).not.toBe("");
  });

  it("fails an errored run", () => {
    const state = health(errored as unknown as Snapshot, NOW);
    expect(state.ok).toBe(false);
    expect(state.headline).toContain("error");
  });

  it("fails a snapshot past the instant the next one was due", () => {
    const state = health(expired as unknown as Snapshot, new Date("2027-01-01T00:00:00Z"));
    expect(state.ok).toBe(false);
    expect(state.headline).toContain("no run for the session that should have closed");
  });

  it("passes a closed day, and says the exchange was shut rather than the loop", () => {
    const state = health(closed as unknown as Snapshot, new Date("2026-11-26T23:00:00Z"));
    expect(state.ok).toBe(true);
    expect(state.headline).toContain("market closed");
    expect(state.detail).toContain("no NYSE session");
  });

  it("still fails a closed day that is sitting past the next session's deadline", () => {
    // The holiday is not a licence to stop paying attention: the run for the
    // session after it was due the next evening, and a closed day left on the
    // page would otherwise look current for as long as nobody ran.
    const state = health(closed as unknown as Snapshot, new Date("2026-11-29T00:00:00Z"));
    expect(state.ok).toBe(false);
    expect(state.headline).toContain("no run for the session after");
  });
});

describe("the page", () => {
  it("shows the book, the dry-run banner and the hedge for a clean run", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(screen.getByText(/DRY RUN: no orders are sent/)).toBeTruthy();
    expect(screen.getByText(/The book: \d+ name\(s\)/)).toBeTruthy();
    expect(screen.getByRole("table", { name: "factor exposures" })).toBeTruthy();
    expect(screen.getByText(/idio share after FMP/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("states the exposures as one table, styles first then sectors by GICS name", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const table = screen.getByRole("table", { name: "factor exposures" });
    const rows = within(table).getAllByRole("row");
    const header = rows[0].textContent ?? "";
    expect(header).toContain("factor");
    expect(header).toContain("before");
    expect(header).toContain("after");
    const labels = rows.slice(1).map((row) => row.querySelector("td")?.textContent ?? "");
    expect(labels.slice(0, 7)).toEqual([
      "Beta",
      "Liquidity",
      "Market",
      "Momentum",
      "Residual vol",
      "Reversal",
      "Size",
    ]);
    // Every sector the design carries, named, and only the ten GICS sectors:
    // 60 is the dummy the design leaves out, so it is named in the note instead.
    expect(labels.slice(7)).toEqual([
      "10 Energy",
      "15 Materials",
      "20 Industrials",
      "25 Consumer Discretionary",
      "30 Consumer Staples",
      "35 Health Care",
      "40 Financials",
      "45 Information Technology",
      "50 Communication Services",
      "55 Utilities",
    ]);
    expect(labels.join(" ")).not.toContain("60 ");
    expect(screen.getAllByText(/60 Real Estate is the reference sector/).length).toBeGreaterThan(0);
  });

  it("shows a hedged-to-zero exposure as 0.0000, never as -0.0000", () => {
    // The after column holds values like -2.6e-18, whose four-place form is
    // "-0.0000": rounding, not a short position in a factor.
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(screen.queryByText("-0.0000")).toBeNull();
    expect(screen.queryByText("-0.0001")).toBeNull();
    const table = screen.getByRole("table", { name: "factor exposures" });
    const zeros = within(table).getAllByText("0.0000");
    expect(zeros.length).toBeGreaterThanOrEqual(17);
    // A genuinely negative exposure keeps its sign, so the rule is not a clamp:
    // the book's most negative factor renders with its minus sign.
    const negatives = Object.values(OK.exposures_before_hedge).filter(
      (value) => (value ?? 0) < 0,
    ) as number[];
    expect(negatives.length).toBeGreaterThan(0);
    expect(within(table).getByText(Math.min(...negatives).toFixed(4))).toBeTruthy();
  });

  it("draws a before and an after bar per factor, on one scale", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const table = screen.getByRole("table", { name: "factor exposures" });
    const bars = { before: table.querySelectorAll("[data-bar='before']"), after: table.querySelectorAll("[data-bar='after']") };
    expect(bars.before.length).toBe(17);
    expect(bars.after.length).toBe(17);
    const momentum = table.querySelector("[data-factor='momentum']") as HTMLElement;
    const width = (element: Element) => parseFloat((element as HTMLElement).style.width);
    const beforeBar = momentum.querySelector("[data-bar='before']") as HTMLElement;
    const afterBar = momentum.querySelector("[data-bar='after']") as HTMLElement;
    // 0.155 against a 0.155 scale: the full half-track, and nothing at all after
    // the hedge, which is the whole point of showing them.
    expect(width(beforeBar)).toBeCloseTo(50, 5);
    expect(width(afterBar)).toBeLessThan(0.001);
    expect(beforeBar.getAttribute("data-sign")).toBe("positive");
    const energy = table.querySelector("[data-factor='sector_10'] [data-bar='before']");
    expect(energy?.getAttribute("data-sign")).toBe("negative");
  });

  it("shows the attribution: the three components, the hedge's factor P&L and the beta line", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const cumulative = OK.attribution.cumulative;
    // The three components, in basis points of the book, each with its sign.
    const bps = (value: number) => `${value >= 0 ? "+" : ""}${(value * 1e4).toFixed(1)} bp`;
    expect(screen.getByText(`total: ${bps(cumulative.pnl_total as number)}`)).toBeTruthy();
    expect(screen.getByText(`factor: ${bps(cumulative.pnl_factor as number)}`)).toBeTruthy();
    expect(screen.getByText(`idio: ${bps(cumulative.pnl_idio as number)}`)).toBeTruthy();
    expect(screen.getByText(`cost: ${bps(cumulative.pnl_cost as number)}`)).toBeTruthy();
    // The worst day's residual travels with the sums rather than being asserted
    // away: a split nobody checked is not a decomposition.
    expect(screen.getByText(/worst day's identity residual/)).toBeTruthy();
    const table = screen.getByRole("table", { name: "attribution by day" });
    const header = within(table).getAllByRole("columnheader").map((cell) => cell.textContent);
    expect(header).toEqual([
      "close",
      "total",
      "factor",
      "idio",
      "cost",
      "hedge factor P&L",
      "raw beta",
      "beta line",
    ]);
    // Newest first, so the top row is the last stored day, and its dates are days.
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.length).toBe(OK.attribution.daily.length);
    expect(within(rows[0]).getAllByRole("cell")[0].textContent).toBe(OK.attribution.last_day);
    expect(within(rows[0]).getAllByRole("cell")[0].textContent).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("says why the attribution is empty instead of showing an empty table", () => {
    const snapshot = {
      ...OK,
      attribution: {
        ...OK.attribution,
        n_days: 0,
        daily: [],
        note: "no attributed day is stored yet",
      },
    } as unknown as Snapshot;
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    expect(screen.getByText("no attributed day is stored yet")).toBeTruthy();
    expect(screen.queryByRole("table", { name: "attribution by day" })).toBeNull();
  });

  it("shows the traded book's gross as the headline, and the full book as a detail", () => {
    // The manifest's own `gross` is the 499-name book before the floor. Publishing
    // it as "the gross" told the owner their book was 96.85% invested when the book
    // that trades is 100% and $1,000,000.
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(OK.book.gross).toBe(1);
    expect(screen.getByText("100.00% ($1,000,000)")).toBeTruthy();
    expect(screen.getByText("full book before the floor")).toBeTruthy();
    expect(screen.getByText("96.85%")).toBeTruthy();
  });

  it("breaks the summary into labelled items rather than a pipe run", () => {
    const { container } = render(<SnapshotView snapshot={OK} now={NOW} />);
    // Scoped to the summary itself, because the attribution table below carries
    // column headers of its own and "cost" is one of them. What this test is
    // about is that the summary labels each number, not that the word is unique
    // on the page.
    const summary = container.querySelector('[aria-label="the book\x27s summary"]');
    expect(summary).not.toBeNull();
    expect(screen.queryByText(/\|/)).toBeNull();
    expect(within(summary as HTMLElement).getByText("gross")).toBeTruthy();
    expect(within(summary as HTMLElement).getByText("net")).toBeTruthy();
    expect(within(summary as HTMLElement).getByText("n_eff_kept")).toBeTruthy();
    expect(within(summary as HTMLElement).getByText("n_eff_full_book")).toBeTruthy();
    expect(within(summary as HTMLElement).getByText("cost")).toBeTruthy();
  });

  it("gives the effective breadth to one decimal, and names what each one is", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const kept = OK.breadth.n_eff_kept as number;
    const full = OK.breadth.n_eff_full_book as number;
    expect(screen.getByText(new RegExp(`${kept.toFixed(1)} \\(`))).toBeTruthy();
    expect(screen.getByText(new RegExp(`${full.toFixed(1)} \\(`))).toBeTruthy();
    expect(screen.queryByText(String(kept))).toBeNull();
  });

  it("shows dates as days and the snapshot's age relative to now", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("T00:00:00");
    // 22:41 generated, 23:00 now.
    expect(text).toContain("19 minutes ago");
    expect(text).toContain("target close 2026-09-21");
    expect(text).toContain("snapshot generated 2026-09-21");
  });

  it("says a snapshot of a day or more in days, not in hours", () => {
    const later = new Date("2026-09-24T23:00:00Z");
    render(<SnapshotView snapshot={OK} now={later} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("3 days ago");
    expect(text).not.toContain("72 hours");
  });

  it("keeps a day-old snapshot in hours, which is the useful unit", () => {
    const later = new Date("2026-09-22T22:41:30Z");
    render(<SnapshotView snapshot={OK} now={later} />);
    expect(document.body.textContent ?? "").toContain("24 hours ago");
  });

  it("lists the names by absolute weight, the largest first", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const rows = within(screen.getByRole("table", { name: "the book" })).getAllByRole("row");
    const dataRows = rows.slice(1);
    const weights = OK.book.names.map((name) => Math.abs(name.weight ?? 0));
    const descending = [...weights].sort((a, b) => b - a);
    expect(weights).toEqual(descending);
    expect(dataRows.length).toBe(OK.book.names.length);
    for (const [index, name] of OK.book.names.entries()) {
      expect(dataRows[index].textContent).toContain(name.ticker);
    }
  });

  it("takes the top of the screen when the run stopped", () => {
    render(<SnapshotView snapshot={stale as unknown as Snapshot} now={NOW} />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("STALE STOP");
  });

  it("names the catch-up run and the sessions it caught up", () => {
    const snapshot = catchUp as unknown as Snapshot;
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    expect(
      screen.getByText(new RegExp(`catch-up run: ${snapshot.run_status.catch_up_sessions.join(", ")}`)),
    ).toBeTruthy();
  });

  it("dates the book whenever its close is not the target close", () => {
    const snapshot: Snapshot = {
      ...OK,
      target_close: "2026-09-28T00:00:00",
      book_as_of: "2026-09-21T00:00:00",
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    expect(screen.getByText(/\(as of 2026-09-21\)/)).toBeTruthy();
    expect(document.body.textContent ?? "").not.toContain("T00:00:00");
  });

  it("reports the account against the store", () => {
    const snapshot: Snapshot = {
      ...OK,
      positions: {
        ...OK.positions,
        matches: false,
        note: "mismatch: the account holds 0 name(s) and the store 150",
      },
    };
    render(<SnapshotView snapshot={snapshot} now={NOW} />);
    expect(screen.getByText(/mismatch: the account holds 0 name\(s\)/)).toBeTruthy();
  });

  it("fails loudly when there is no snapshot at all", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ missing: true }), { status: 404 }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByText(/no snapshot at all/)).toBeTruthy());
  });

  it("fails loudly when the endpoint refuses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: "forbidden" }), { status: 403 }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByText(/could not be read/)).toBeTruthy());
    expect(screen.getByRole("alert").textContent).toContain("the endpoint answered 403");
  });

  it("renders the snapshot the endpoint serves", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(OK), { status: 200 }),
    );
    render(<App now={() => NOW} />);
    await waitFor(() => expect(screen.getByText(/The book: \d+ name\(s\)/)).toBeTruthy());
  });
});
