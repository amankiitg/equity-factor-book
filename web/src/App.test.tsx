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
});

describe("the page", () => {
  it("shows the book, the dry-run banner and the hedge for a clean run", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(screen.getByText(/DRY RUN: no orders are sent/)).toBeTruthy();
    expect(screen.getByText(/The book: \d+ name\(s\)/)).toBeTruthy();
    expect(screen.getByText("before the hedge")).toBeTruthy();
    expect(screen.getByText("after the hedge")).toBeTruthy();
    expect(screen.getByText(/idio share after FMP/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
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
    expect(screen.getByText(/\(as of 2026-09-21T00:00:00\)/)).toBeTruthy();
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
