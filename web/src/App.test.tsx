// The page against the committed fixtures.
//
// The fixtures are written by the Python writer (`scripts/make_web_fixtures.py`)
// from a real proposal, so these tests drive the page with the document the cron
// actually uploads rather than a hand-made shape. Every state the owner has to be
// able to tell apart is here: clean, late, stale-stopped, errored and missing.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App, { health, SnapshotView } from "./App";
import type { Snapshot } from "./types";
import catchUp from "../fixtures/snapshot_catch_up.json";
import closed from "../fixtures/snapshot_market_closed.json";
import errored from "../fixtures/snapshot_error.json";
import expired from "../fixtures/snapshot_expired.json";
import ok from "../fixtures/snapshot_ok.json";
import stale from "../fixtures/snapshot_stale_stopped.json";
import withActual from "../fixtures/snapshot_actual_holdings.json";
import withRemoval from "../fixtures/snapshot_position_removed.json";

const OK = ok as unknown as Snapshot;
const ACTUAL = withActual as unknown as Snapshot;
const REMOVAL = withRemoval as unknown as Snapshot;
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

  it("puts the detail drawer last and the status first", () => {
    // The order is the reading order: what happened, what needs a look, the
    // numbers, the pictures, then the tables, which are the only thing on the
    // page that is not needed to answer "does the book look like the book".
    // The two columns are the same order the phone reads in one, so the trades
    // come before the sectors: the hedge and the trades share the long left
    // column and the book's own shape the right one.
    render(<SnapshotView snapshot={ACTUAL} now={NOW} />);
    expect(document.querySelector("[data-strip='status']")).toBeTruthy();
    expect(document.querySelector("[data-alerts='true']")).toBeTruthy();
    expect(document.querySelector("[data-cards='true']")).toBeTruthy();
    const order = Array.from(document.querySelectorAll("[data-section]")).map((node) =>
      node.getAttribute("data-section"),
    );
    expect(order.indexOf("exposures")).toBeLessThan(order.indexOf("reasons"));
    expect(order.indexOf("reasons")).toBeLessThan(order.indexOf("sector"));
    expect(order.indexOf("sector")).toBeLessThan(order.indexOf("top-names"));
    expect(order.indexOf("top-names")).toBeLessThan(order.indexOf("drawer"));
    // The two columns, and which section is in which: a layout test that only
    // read the document order would pass with both long panels stacked in the
    // right column.
    const columns = Array.from(
      document.querySelectorAll("[data-columns='true'] > div"),
    ).map((column) =>
      Array.from(column.querySelectorAll("[data-section]")).map((node) =>
        node.getAttribute("data-section"),
      ),
    );
    expect(columns.length).toBe(2);
    expect(columns[0]).toContain("exposures");
    expect(columns[0]).toContain("reasons");
    expect(columns[1]).toContain("sector");
    expect(columns[1]).toContain("top-names");
    expect(columns[1]).not.toContain("reasons");
    // Both tables live in the drawer, and it is the last thing on the page.
    expect(order[order.length - 1]).toBe("drawer");
    expect(order).not.toContain("holdings");
    expect(order).not.toContain("actual-holdings");
  });

  it("says the account was not read when the snapshot carries no account", () => {
    // The state every snapshot was in before the runs published this block, and
    // the state a run that could not read the account is in: one line, and no
    // second tab to open.
    expect(OK.actual_holdings).toBeUndefined();
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(screen.getByText(/the account has not been read/)).toBeTruthy();
    const drawer = document.querySelector("[data-section='drawer']") as HTMLElement;
    expect(drawer.querySelector("[data-tab='actual']")).toBeNull();
  });

  it("states the exposures as one table, styles first then sectors by GICS name", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const table = screen.getByRole("table", { name: "factor exposures" });
    const rows = within(table).getAllByRole("row");
    // Four separate header cells. Rendered as one, the last two read
    // "afterbefore / after": the value columns are only as wide as their own
    // numbers, so the labels touch unless each column states its width.
    const headers = Array.from(rows[0].querySelectorAll("th")).map(
      (cell) => cell.textContent,
    );
    expect(headers).toEqual(["factor", "before", "after", "before / after"]);
    expect(headers.join(" ")).not.toContain("afterbefore");
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
    // "-0.0000": rounding, not a short position in a factor. Only the after
    // column is held to this: a before value of -0.0001 is a real, tiny pre-hedge
    // tilt and keeps its sign, which the last check below pins.
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const table = screen.getByRole("table", { name: "factor exposures" });
    const after = Array.from(
      table.querySelectorAll("[data-factor] td:nth-child(3)"),
    ).map((cell) => cell.textContent ?? "");
    expect(after.length).toBeGreaterThanOrEqual(17);
    expect(after.filter((text) => text !== "0.0000")).toEqual([]);
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
    // that trades is 100% and $1,000,000. The full book's own number is read from
    // the fixture rather than typed in, so regenerating it cannot break this.
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(OK.book.gross).toBe(1);
    const gross = document.querySelector("[data-card='gross']") as HTMLElement;
    expect(gross.textContent).toContain("100.00%");
    expect(gross.textContent).toContain("$1,000,000");
    const full = document.querySelector("[data-card='full book before the floor']") as HTMLElement;
    expect(full).toBeTruthy();
    expect(full.textContent).toContain(`${((OK.book.full_book_gross ?? 0) * 100).toFixed(2)}%`);
  });

  it("breaks the summary into labelled items rather than a pipe run", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    expect(screen.queryByText(/\|/)).toBeNull();
    // Main's own locator, kept over e12's: the summary is a row of cards with a
    // `data-card` per label since the page was split into components, and e12's
    // `[aria-label="the book's summary"]` named a `<dl>` that refactor removed.
    const cards = document.querySelector("[data-cards='true']") as HTMLElement;
    for (const label of ["gross", "net", "n_eff_kept", "n_eff_full_book", "expected cost"]) {
      expect(cards.querySelector(`[data-card="${label}"]`), label).toBeTruthy();
    }
  });

  it("gives the effective breadth to one decimal, and names what each one is", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const kept = OK.breadth.n_eff_kept as number;
    const full = OK.breadth.n_eff_full_book as number;
    const card = (label: string): HTMLElement =>
      document.querySelector(`[data-card='${label}']`) as HTMLElement;
    expect(card("n_eff_kept").textContent).toContain(kept.toFixed(1));
    expect(card("n_eff_kept").textContent).toContain(OK.breadth.kept_label);
    expect(card("n_eff_full_book").textContent).toContain(full.toFixed(1));
    // The stored value to seventeen places is not on the page.
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

  it("shows a position that left the account with no order behind it", () => {
    // The PSKY case: the book, the orders and the fill count can all be right
    // while a name has walked out of the account, so this is the one line on the
    // page that nothing else implies.
    render(<SnapshotView snapshot={REMOVAL} now={new Date("2026-10-06T23:00:00Z")} />);
    const panel = document.querySelector("[data-alert='exits']") as HTMLElement;
    expect(panel).toBeTruthy();
    expect(panel.textContent).toContain("1 position left the account with no order behind it");
    expect(panel.textContent).toContain("PSKY");
    expect(panel.textContent).toContain("326.07 shares");
    expect(panel.textContent).toContain("$3,212");
    // The dollars are labelled where the day's reconciled figures are, rather than
    // netted out of the P&L: a number quietly adjusted is one nobody can check.
    const figure = document.querySelector(
      "[data-figure='unexplained-adjustment']",
    ) as HTMLElement;
    expect(figure.textContent).toContain("unexplained adjustment");
    expect(figure.textContent).toContain("-$3,212");
  });

  it("says a departure the activity feed could not be asked about is weaker, not absent", () => {
    const unread: Snapshot = {
      ...REMOVAL,
      actual_holdings: {
        ...(REMOVAL.actual_holdings as NonNullable<Snapshot["actual_holdings"]>),
        exits: {
          ...(REMOVAL.actual_holdings?.exits as NonNullable<
            NonNullable<Snapshot["actual_holdings"]>["exits"]
          >),
          feed: "not read",
        },
      },
    };
    render(<SnapshotView snapshot={unread} now={new Date("2026-10-06T23:00:00Z")} />);
    const panel = document.querySelector("[data-alert='exits']") as HTMLElement;
    expect(panel.textContent).toContain("no closing order filled");
    expect(panel.textContent).not.toContain("no activity of the broker's");
    expect(panel.textContent).toContain("could not be read");
  });

  it("names a leg the evening could not send at all", () => {
    // A ticker the broker's asset feed carries under no symbol: no order was sent,
    // so it is not a miss, and the line carries the derived reason because the
    // broker never saw the order and holds no record of it.
    const unsendable: Snapshot = {
      ...ACTUAL,
      actual_holdings: {
        ...(ACTUAL.actual_holdings as NonNullable<Snapshot["actual_holdings"]>),
        fills: {
          ...(ACTUAL.actual_holdings?.fills as NonNullable<
            NonNullable<Snapshot["actual_holdings"]>["fills"]
          >),
          not_sent_lines: ["SKYD sell_to_open $500 never sent (SYMBOL_NOT_FOUND)"],
        },
      },
    };
    render(<SnapshotView snapshot={unsendable} now={NOW} />);
    const panel = document.querySelector("[data-alert='misses']") as HTMLElement;
    expect(panel.textContent).toContain("could not be sent");
    const line = document.querySelector("[data-not-sent='true']") as HTMLElement;
    expect(line.textContent).toContain("SKYD");
    expect(line.textContent).toContain("SYMBOL_NOT_FOUND");
  });

  it("lists the names by absolute weight, the largest first", () => {
    render(<SnapshotView snapshot={OK} now={NOW} />);
    fireEvent.click(document.querySelector("[data-tab='book']") as HTMLElement);
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

  it("draws one row per kept name and counts them in the table's own tab", () => {
    // The 2026-10-01 shape: the page drew "The book: 0 name(s)" over an empty
    // table while every number around it was right, because the writer was
    // handed no frame for the names. The fixture is the writer's own output, so
    // the table has to draw one row per kept name and the tab has to count the
    // same book.
    render(<SnapshotView snapshot={OK} now={NOW} />);
    const kept = OK.book.n_kept;
    expect(kept).toBeGreaterThan(0);
    expect(screen.getByText(new RegExp(`The book: ${kept} name\\(s\\)`))).toBeTruthy();
    fireEvent.click(document.querySelector("[data-tab='book']") as HTMLElement);
    const rows = within(screen.getByRole("table", { name: "the book" })).getAllByRole("row");
    const dataRows = rows.slice(1);
    expect(dataRows.length).toBe(kept);
    expect(dataRows.length).toBe(OK.book.n_names);
    for (const row of dataRows) {
      expect(row.querySelector("td")?.textContent).toBeTruthy();
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
