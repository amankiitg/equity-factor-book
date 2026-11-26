// The anchored panels, rendered from the document the evening actually published.
//
// The fixture is the 2026-10-29 close: the document the page was served, with the
// real anchored block in it. Nothing here is hand-built, because the hand-built
// fixture is what let the panels pass in the suite while the live page rendered the
// nightly ones: the test and the page disagreed about the shape of a real document.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActualHoldingsTable } from "./ActualHoldingsTable";
import { SnapshotView } from "./App";
import { FlipBridge, incompleteFields, MonthlyPanels } from "./Monthly";
import { HedgePanel } from "./HedgePanel";
import { SectorSection } from "./SectorSection";
import { bookFacts } from "./book";
import type { MonthlyBlock, Snapshot } from "./types";
import served from "../fixtures/snapshot_2026-10-29_evening.json";
import real from "../fixtures/snapshot_2026-11-13_monthly.json";

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

  it("measures the drift from the target and prices closing it, in one line", () => {
    render(<MonthlyPanels monthly={MONTHLY} />);
    const drift = document.querySelector("[data-drift]")?.textContent ?? "";
    expect(drift).toContain("2.30%");
    expect(drift).toContain("$44,801");
    expect(drift).toContain("0.4 bp of NAV");
    expect(drift).toContain("$38");
    // The target is fixed between rebalances, and the gap includes the guard's
    // deliberate repairs, which is what stops the line reading as pure price drift.
    expect(drift).toContain("The target stays fixed until the");
    expect(drift).toContain("The gap includes every move the guard made on purpose");
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
    // JBL's $269 is under one share, so it is stated as a refusal rather than as a
    // leg in flight, and the count that would be sent is stated separately.
    const tonight = document.querySelector("[data-tonight]")?.textContent ?? "";
    expect(tonight).toContain("cannot be sent");
    expect(tonight).toContain("$269");
    expect(tonight).toContain("JBL");
    // The code is the store's word for it; the page says what happened.
    expect(tonight).toContain("under one share");
    expect(tonight).not.toContain("COVER_UNDER_ONE_SHARE");
  });

  it("counts sent legs apart from the ones under the $250 minimum", () => {
    // The live 2026-11-11 shape: 224 rebalance rows of which 16 never went, the
    // guard's 249 sent legs, JBL owed at $269, and the 315 legs the guard could not
    // size. The table must not add the last group to a reason: it is not a leg.
    const block: MonthlyBlock = {
      ...MONTHLY,
      since_anchor: {
        trades_by_reason: [
          { reason: "rebalance", legs: 224, usd: 546_256.69, sent_legs: 208, sent_usd: 544_003.43 },
          { reason: "guard", legs: 249, usd: 165_797.76, sent_legs: 249, sent_usd: 165_797.76 },
          { reason: "carried leg", legs: 1, usd: 269.37, sent_legs: 0, sent_usd: 0 },
        ],
        not_sent: {
          legs: 315,
          usd: 91_697.42,
          under_minimum: { legs: 315, usd: 91_697.42 },
          other: [],
        },
      },
    };
    render(<MonthlyPanels monthly={block} />);
    const table = document.querySelector("[data-trades-reason]")?.textContent ?? "";
    expect(table).toContain("208 sent, 16 not sent (under $250)");
    expect(table).toContain("1 leg, impossible (under one share)");
    expect(table).toContain("$269");
    const line = document.querySelector("[data-not-sent]")?.textContent ?? "";
    expect(line).toContain("315 under $250");
    expect(line).toContain("$91,697");
  });

  it("renders the 2026-10-26 re-trade as its own row, not a remainder", () => {
    // The unfilled-remainder bug (fixed 10-27) re-sent 8 legs of a rebalance that
    // had already filled. They are not a remainder and not a rebalance, and the
    // table says so in its own row.
    const block: MonthlyBlock = {
      ...MONTHLY,
      since_anchor: {
        trades_by_reason: [
          {
            reason: "remainder re-trade (bug, fixed 10-27)",
            legs: 8,
            usd: 3_632.0,
            sent_legs: 8,
            sent_usd: 3_632.0,
          },
        ],
        not_sent: {
          legs: 0,
          usd: 0,
          under_minimum: { legs: 0, usd: 0 },
          other: [],
        },
      },
    };
    render(<MonthlyPanels monthly={block} />);
    const table = document.querySelector("[data-trades-reason]")?.textContent ?? "";
    expect(table).toContain("remainder re-trade (bug, fixed 10-27)");
    expect(table).toContain("8 legs");
    expect(table).toContain("$3,632");
  });

  it("renders nothing at all when the document carries no block", () => {
    const { container } = render(<MonthlyPanels monthly={null} />);
    expect(container.querySelector("[data-monthly]")).toBeNull();
    expect(container.textContent).toBe("");
  });
});

// The sector panel, on the same real document.
//
// The page's own sector panel compares the account with tonight's book, and on a hold
// day tonight's book *is* the account: eleven rows of +$0, which is why the panel had
// to be measured from the rebalance instead. These tests are on the served document,
// so the numbers are the ones the page is reading.
describe("the sector panel against the rebalance target", () => {
  const SECTORS = MONTHLY.sectors;
  if (!SECTORS) throw new Error("the served fixture carries no anchored sectors");

  it("measures the account against the 2026-10-23 target and not against tonight", () => {
    render(<SectorSection snapshot={SERVED} sectors={[]} monthly={MONTHLY} />);
    const panel = document.querySelector('[data-sector-anchored="true"]');
    expect(panel).not.toBeNull();
    expect(panel?.textContent).toContain("account against the 2026-10-23 target");
    // Crucially not the nightly panel: that one reads +$0 for every sector on a hold
    // day, and this one must not render it.
    expect(document.querySelector('[data-sector-deltas="no-account"]')).toBeNull();
  });

  it("shows non-zero differences, and the traded total is the drift card's", () => {
    render(<SectorSection snapshot={SERVED} sectors={[]} monthly={MONTHLY} />);
    const rows = [...document.querySelectorAll("[data-delta]")];
    expect(rows.length).toBeGreaterThanOrEqual(10);
    const deltas = rows.map((row) => Number(row.getAttribute("data-delta")));
    expect(deltas.some((delta) => Math.abs(delta) > 100)).toBe(true);
    // The identity: sum(traded) / 2 is the drift card's one-side turnover, and
    // sum(traded) is its both-sides figure, name for name.
    const traded = rows
      .map((row) => Number(row.getAttribute("data-traded")))
      .reduce((total, value) => total + value, 0);
    // The rows carry cents, so the sums are to the cent rather than to the machine.
    expect(traded / 2).toBeCloseTo(MONTHLY.drift?.half_turnover_usd ?? -1, 1);
    expect(traded).toBeCloseTo(MONTHLY.drift?.traded_usd ?? -1, 1);
    expect(traded).toBeCloseTo(44800.75, 1);
    expect(screen.getByText("$44,801")).toBeTruthy();
  });

  it("leaves a rebalance day to the panel's own comparison", () => {
    // Same document, anchor moved to tonight: the nightly comparison is the right one
    // there, because tonight's book is not the account.
    const rebalance: MonthlyBlock = {
      ...MONTHLY,
      anchor: { close: "2026-10-29", day: "rebalance", account_read: "2026-10-29" },
    };
    const { container } = render(
      <SectorSection snapshot={SERVED} sectors={[]} monthly={rebalance} />,
    );
    expect(container.querySelector('[data-sector-anchored="true"]')).toBeNull();
  });

  it("leaves a document with no block exactly as it was", () => {
    const { container } = render(
      <SectorSection snapshot={SERVED} sectors={[]} monthly={null} />,
    );
    expect(container.querySelector('[data-sector-anchored="true"]')).toBeNull();
  });
});

// The hedge footprint, on the same real document.
describe("the hedge footprint against the rebalance", () => {
  const HEDGE = MONTHLY.hedge;
  if (!HEDGE) throw new Error("the served fixture carries no anchored hedge");

  it("reports the close that hedged rather than a hold day's nothing", () => {
    render(<HedgePanel snapshot={SERVED} facts={bookFacts(SERVED)} monthly={MONTHLY} />);
    const panel = document.querySelector('[data-hedge-anchored="true"]');
    expect(panel).not.toBeNull();
    const text = panel?.textContent ?? "";
    // 88 of 196 names and $122,327 of legs, on 2026-10-23 - not "0 of 196".
    expect(text).toContain("88");
    expect(text).toContain("196");
    expect(text).toContain("$122,327");
    expect(text).toContain("2026-10-23");
    expect(text).toContain("Nothing was hedged tonight");
  });

  it("leaves a rebalance day to tonight's own legs", () => {
    const rebalance: MonthlyBlock = {
      ...MONTHLY,
      anchor: { close: "2026-10-29", day: "rebalance", account_read: "2026-10-29" },
    };
    const { container } = render(
      <HedgePanel snapshot={SERVED} facts={bookFacts(SERVED)} monthly={rebalance} />,
    );
    expect(container.querySelector('[data-hedge-anchored="true"]')).toBeNull();
  });
});

// The phone layout, as a property of the markup rather than of a stylesheet.
describe("the flip and drift lists do not need a sideways scroll", () => {
  it("carries no minimum width and no horizontal overflow on either list", () => {
    render(<MonthlyPanels monthly={MONTHLY} />);
    for (const list of document.querySelectorAll("[data-flip-table], [data-drift-table]")) {
      const className = list.getAttribute("class") ?? "";
      expect(className).not.toMatch(/min-w-\[/);
      expect(list.parentElement?.getAttribute("class") ?? "").not.toContain("overflow-x-auto");
    }
  });

  it("keeps the name, the side, the dollars and the state on the flip row", () => {
    render(<MonthlyPanels monthly={MONTHLY} />);
    const ccl = document.querySelector('[data-flip="CCL"]')?.textContent ?? "";
    expect(ccl).toContain("CCL");
    expect(ccl).toContain("short to long");
    expect(ccl).toContain("$605");
    expect(ccl).toContain("$678");
    expect(ccl).toContain("complete");
    expect(
      document.querySelector('[data-flip="CCL"] [data-flip-state]')?.getAttribute("data-flip-state"),
    ).toBe("complete");
  });

  it("states the gap without a name-by-name list to scroll", () => {
    render(<MonthlyPanels monthly={MONTHLY} />);
    // The three largest gaps and their dollars are named in the card's (i), and the
    // card itself is one sentence: there is no sideways table left to scroll.
    expect(document.querySelector("[data-drift-row]")).toBeNull();
    const card = document.querySelector("[data-drift='true']") as HTMLElement;
    expect(card).toBeTruthy();
    const title = card.closest("[data-panel='monthly']")?.querySelector("h3")?.textContent ?? "";
    expect(title).toContain("distance from the rebalance target");
  });
});

describe("the tonight line's refusal reads as a sentence", () => {
  it("puts the ticker and its reason after a colon, not in nested brackets", () => {
    render(<MonthlyPanels monthly={MONTHLY} />);
    const text = document.querySelector("[data-tonight]")?.textContent ?? "";
    expect(text).toContain("$269: JBL, under one share");
    expect(text).not.toContain("(JBL");
    expect(text).not.toContain("COVER_UNDER_ONE_SHARE");
  });
});

describe("plain language on the anchored panels", () => {
  it("gives every anchored panel one how-to-read line", () => {
    render(<MonthlyPanels monthly={MONTHLY} />);
    const panels = [...document.querySelectorAll('[data-panel="monthly"]')];
    expect(panels.length).toBeGreaterThan(0);
    for (const panel of panels) {
      expect(panel.querySelector("[data-how-to-read]")).not.toBeNull();
    }
  });

  it("reads a rebalance day and a daily run as today's mode", () => {
    const strip = MONTHLY.cadence_strip;
    if (!strip) throw new Error("the served fixture carries no cadence strip");
    const rebalance: MonthlyBlock = {
      ...MONTHLY,
      cadence_strip: { ...strip, day: "rebalance" },
    };
    const first = render(<MonthlyPanels monthly={rebalance} />);
    expect(
      first.container.querySelector("[data-cadence]")?.textContent,
    ).toContain("rebalance");
    first.unmount();
    const daily: MonthlyBlock = {
      ...MONTHLY,
      cadence_strip: { ...strip, day: null, k: 1, sessions_since: 0 },
    };
    const second = render(<MonthlyPanels monthly={daily} />);
    expect(
      second.container.querySelector("[data-cadence]")?.textContent,
    ).toContain("daily");
  });
});

describe("the holdings tables against the rebalance", () => {
  it("marks CCL as re-flipped and gives KVUE its own retired row", () => {
    const monthly: MonthlyBlock = {
      ...MONTHLY,
      holdings: {
        anchor: "2026-10-23",
        as_of: "2026-11-05",
        rows: [
          {
            ticker: "CCL",
            since:
              "flipped (2026-10-23 to 2026-10-26); drift guard leg (2026-11-04)",
            since_kind: "flipped",
            since_date: "2026-11-04",
            weight_now: 0.0007,
            weight_target: 0.00069,
            gap_weight: 0.00001,
            gap_usd: 10,
            tonight: null,
            retired: false,
            owed: false,
            note: null,
          },
          {
            ticker: "KVUE",
            since: "retired (acquired by KMB), owed, cannot be traded",
            since_kind: "retired",
            since_date: "2026-10-23",
            weight_now: 0,
            weight_target: 0.004,
            gap_weight: -0.004,
            gap_usd: -4000,
            tonight: null,
            retired: true,
            owed: true,
            note: "retired (acquired by KMB), owed, cannot be traded",
          },
        ],
      },
    };
    const actual = SERVED.actual_holdings;
    if (!actual) throw new Error("the served fixture carries no actual holdings");
    render(
      <ActualHoldingsTable
        actual={actual}
        names={SERVED.book?.names ?? []}
        nav={bookFacts(SERVED).nav}
        monthly={monthly}
      />,
    );
    const ccl = document.querySelector('[data-ticker="CCL"]');
    expect(ccl?.textContent).toContain("drift guard leg (2026-11-04)");
    const kvue = document.querySelector('[data-ticker="KVUE"]');
    expect(kvue?.getAttribute("data-retired")).toBe("true");
    expect(kvue?.textContent).toContain(
      "retired (acquired by KMB), owed, cannot be traded",
    );
    expect(kvue?.textContent).toContain("n/a, cannot trade");
  });

  it("says a re-flip happened on the day the drift guard moved it", () => {
    const bridge = MONTHLY.bridge_anchor;
    const ccl = bridge?.flip_rows.find((row) => row.ticker === "CCL");
    if (!bridge || !ccl) throw new Error("the served fixture carries no CCL flip");
    const monthly: MonthlyBlock = {
      ...MONTHLY,
      bridge_anchor: {
        ...bridge,
        flip_rows: [
          {
            ...ccl,
            legs_filled: true,
            state: "refipped",
            state_label: "re-flipped later by the drift guard on 2026-11-04",
            refipped_on: "2026-11-04",
          },
        ],
      },
    };
    render(<FlipBridge monthly={monthly} />);
    const header = document.querySelector("[data-flip-header]")?.textContent ?? "";
    expect(header).toContain("leg 1: closed the old position (trade size)");
    expect(header).toContain("leg 2: opened the new side (trade size)");
    expect(header).toContain(
      "position now (minus = short, at today's price)",
    );
    expect(
      document.querySelector('[data-flip="CCL"] [data-flip-state]')?.textContent,
    ).toContain("re-flipped later by the drift guard on 2026-11-04");
  });
});

/**
 * The live 2026-11-13 facts, as the block carries them.
 *
 * The 10-23 rebalance flipped CCL, F, GEHC and VZ. The drift guard then flipped
 * CCL and NFLX on 11-04 and MKC on 11-12. VZ, GEHC and F were traded by the guard on
 * those evenings and did not change side, so no row of theirs may say re-flipped.
 */
function liveFactsBlock(): MonthlyBlock {
  const bridge = MONTHLY.bridge_anchor;
  if (!bridge) throw new Error("the served fixture carries no bridge");
  const flips = [
    { ticker: "CCL", from: "short", to: "long", close: 605, open: 678, now: -650,
      refipped: "2026-11-04" },
    { ticker: "F", from: "long", to: "short", close: 633, open: 1600, now: -650,
      refipped: null },
    { ticker: "GEHC", from: "short", to: "long", close: 2000, open: 2328, now: 650,
      refipped: null },
    { ticker: "VZ", from: "long", to: "short", close: 988, open: 2434, now: -650,
      refipped: null },
  ];
  return {
    ...MONTHLY,
    bridge_anchor: {
      ...bridge,
      flipped: flips.length,
      complete_flips: 3,
      flip_rows: flips.map((flip) => ({
        ticker: flip.ticker,
        from_side: flip.from,
        to_side: flip.to,
        close_dollars: flip.close,
        close_filled: "2026-10-23",
        open_dollars: flip.open,
        open_filled: "2026-10-26",
        now_dollars: flip.now,
        on_target_side: flip.refipped === null,
        complete: flip.refipped === null,
        legs_filled: true,
        refipped_on: flip.refipped,
        state: flip.refipped ? "refipped" : "complete",
        state_label: flip.refipped
          ? `re-flipped later by the drift guard on ${flip.refipped}`
          : "complete",
      })),
    },
    since_anchor: {
      ...(MONTHLY.since_anchor as NonNullable<MonthlyBlock["since_anchor"]>),
      guard_history: [
        {
          date: "2026-10-30",
          exposure_before: 0.0641,
          exposure_after: 0.0041,
          threshold: 0.05,
          legs_sent: 109,
          legs_under_minimum: 12,
          usd: 68_000,
          cost_bps: 2.1,
          flips: [],
        },
        {
          date: "2026-11-04",
          exposure_before: 0.0641,
          exposure_after: 0.0041,
          threshold: 0.05,
          legs_sent: 140,
          legs_under_minimum: 9,
          usd: 91_000,
          cost_bps: 2.4,
          flips: ["CCL", "NFLX"],
          // CCL is a guard flip and the reverse of the rebalance's own 10-23 flip.
          reversals: { CCL: "2026-10-23" },
        },
        {
          date: "2026-11-12",
          exposure_before: 0.0532,
          exposure_after: 0.0021,
          threshold: 0.05,
          legs_sent: 88,
          legs_under_minimum: 4,
          usd: 44_000,
          cost_bps: 1.2,
          flips: ["MKC"],
          reversals: {},
        },
      ],
      guard_flips: [
        { ticker: "CCL", date: "2026-11-04", from_side: "long", to_side: "short", usd: 19_506 },
        { ticker: "NFLX", date: "2026-11-04", from_side: "long", to_side: "short", usd: 910 },
        { ticker: "MKC", date: "2026-11-12", from_side: "short", to_side: "long", usd: 430 },
      ],
    },
  };
}

describe("the flips panel on the live facts", () => {
  it("marks only CCL as re-flipped and leaves VZ, GEHC and F alone", () => {
    render(<MonthlyPanels monthly={liveFactsBlock()} />);
    const text = (ticker: string): string =>
      document.querySelector(`[data-flip="${ticker}"]`)?.textContent ?? "";
    expect(text("CCL")).toContain("re-flipped later by the drift guard on 2026-11-04");
    for (const ticker of ["VZ", "GEHC", "F"]) {
      expect(text(ticker)).not.toContain("re-flipped");
      expect(text(ticker)).toContain("complete");
    }
  });

  it("shows the guard flips the rebalance did not make in the same list", () => {
    render(<MonthlyPanels monthly={liveFactsBlock()} />);
    const nflx = document.querySelector("[data-guard-flip='NFLX']")?.textContent ?? "";
    expect(nflx).toContain("long to short");
    expect(nflx).toContain("2026-11-04");
    expect(nflx).toContain("$910");
    const mkc = document.querySelector("[data-guard-flip='MKC']")?.textContent ?? "";
    expect(mkc).toContain("short to long");
    expect(mkc).toContain("2026-11-12");
  });

  it("names the flips each guard firing caused on its own card", () => {
    render(<MonthlyPanels monthly={liveFactsBlock()} />);
    const card = (day: string): string =>
      document.querySelector(`[data-guard-firing='${day}']`)?.closest("section")
        ?.textContent ?? "";
    expect(card("2026-11-04")).toContain("it moved CCL, NFLX back to the other side");
    expect(card("2026-11-12")).toContain("it moved MKC back to the other side");
  });

  it("labels CCL as reversing the 10-23 flip, and NFLX as a plain guard flip", () => {
    render(<MonthlyPanels monthly={liveFactsBlock()} />);
    const card = (day: string): string =>
      document.querySelector(`[data-guard-firing='${day}']`)?.closest("section")
        ?.textContent ?? "";
    expect(card("2026-11-04")).toContain("CCL reverses the 2026-10-23 flip");
    expect(card("2026-11-04")).not.toContain("NFLX reverses");
    const reversal = document.querySelector('[data-guard-reversal="CCL"]');
    expect(reversal?.textContent).toContain("CCL reverses the 2026-10-23 flip");
    expect(document.querySelector('[data-guard-reversal="NFLX"]')).toBeNull();
    expect(document.querySelector('[data-guard-reversal="MKC"]')).toBeNull();
  });

  it("carries CCL, NFLX and MKC in the guard flips list with their dates", () => {
    render(<MonthlyPanels monthly={liveFactsBlock()} />);
    const row = (ticker: string): string =>
      document.querySelector(`[data-guard-flip='${ticker}']`)?.textContent ?? "";
    expect(row("CCL")).toContain("2026-11-04");
    expect(row("CCL")).toContain("long to short");
    expect(row("NFLX")).toContain("2026-11-04");
    expect(row("MKC")).toContain("2026-11-12");
  });
});

describe("no stored code reaches the reader", () => {
  it("says what happened instead of printing the leg reason code", () => {
    const base = liveFactsBlock();
    const monthly: MonthlyBlock = {
      ...base,
      since_anchor: {
        ...(base.since_anchor as NonNullable<MonthlyBlock["since_anchor"]>),
        not_sent: {
          legs: 2,
          usd: 14_000,
          under_minimum: { legs: 0, usd: 0 },
          other: [
            { code: "ASSET_INACTIVE", legs: 1, usd: 13_615 },
            { code: "ALPACA_API_ERROR", legs: 1, usd: 450 },
          ],
        },
      },
      tonight: {
        ...(MONTHLY.tonight as NonNullable<MonthlyBlock["tonight"]>),
        cannot_send: [{ ticker: "KVUE", usd: 13_615, code: "ASSET_INACTIVE" }],
        cannot_send_legs: 1,
        cannot_send_usd: 13_615,
      },
    };
    render(<MonthlyPanels monthly={monthly} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("no longer trades");
    expect(text).toContain("no longer trades");
    for (const code of [
      "ASSET_INACTIVE",
      "ALPACA_API_ERROR",
      "COVER_UNDER_ONE_SHARE",
      "BELOW_MIN_NOTIONAL",
    ]) {
      expect(text, `${code} is visible on the page`).not.toContain(code);
    }
  });
});

// The 2026-11-13 close, the document the page is served. Every assertion below is
// the published number, not a hand-built one: the audit's items are claims about
// this close, so a fixture that changed with the code could not catch them.
const REAL = real as unknown as Snapshot;
const REAL_MONTHLY = REAL.monthly as MonthlyBlock;

const money = (text: string | null | undefined): number | null => {
  const match = /^([-+]?)\$([\d,]+)/.exec((text ?? "").trim());
  if (!match) return null;
  const value = Number(match[2].replace(/,/g, ""));
  return match[1] === "-" ? -value : value;
};

describe("the 11-13 close, from the published block", () => {
  it("1 counts a refusal by name, not one row per night", () => {
    render(<MonthlyPanels monthly={REAL_MONTHLY} />);
    const line = document.querySelector("[data-not-sent]")?.textContent ?? "";
    expect(line).toContain("KVUE $13,615");
    expect(line).not.toContain("$95,308");
  });

  it("2 shows the 10-23 target and a gap that adds up on every row", () => {
    const actual = REAL.actual_holdings;
    if (!actual) throw new Error("the 11-13 fixture carries no account read");
    render(
      <ActualHoldingsTable
        actual={actual}
        names={REAL.book?.names ?? []}
        nav={bookFacts(REAL).nav}
        monthly={REAL_MONTHLY}
      />,
    );
    const head =
      document.querySelector("table[aria-label='actual holdings'] thead")?.textContent ?? "";
    expect(head).toContain("10-23 target weight");
    let checked = 0;
    for (const row of Array.from(
      document.querySelectorAll("table[aria-label='actual holdings'] tbody tr"),
    )) {
      if (row.getAttribute("data-retired") === "true") continue;
      const cells = Array.from(row.querySelectorAll("td")).map((cell) => cell.textContent ?? "");
      const held = money(cells[3]);
      const target = money(cells[5]);
      const gap = money(cells[7]);
      if (held === null || target === null || gap === null) continue;
      expect(
        Math.abs(held + gap - target),
        `${row.getAttribute("data-ticker")} does not add up`,
      ).toBeLessThanOrEqual(1);
      checked += 1;
    }
    expect(checked).toBeGreaterThan(100);
    const mrvl = document.querySelector("tr[data-ticker='MRVL']")?.textContent ?? "";
    expect(mrvl).toContain("1.43%");
    expect(mrvl).toContain("$5,018");
  });

  it("3 shows KVUE as retired with no gap to trade", () => {
    const actual = REAL.actual_holdings;
    if (!actual) throw new Error("the 11-13 fixture carries no account read");
    render(
      <ActualHoldingsTable
        actual={actual}
        names={REAL.book?.names ?? []}
        nav={bookFacts(REAL).nav}
        monthly={REAL_MONTHLY}
      />,
    );
    const kvue = document.querySelector("tr[data-ticker='KVUE']")?.textContent ?? "";
    expect(kvue).toContain("retired");
    expect(kvue).toContain("n/a, cannot trade");
    expect(kvue).not.toContain("$102");
  });

  it("4 prices closing the gap at the document's own rate, bp and dollars in step", () => {
    const base = REAL_MONTHLY.drift;
    const nav = REAL_MONTHLY.sectors?.nav;
    if (!base || nav === null || nav === undefined) {
      throw new Error("the 11-13 fixture carries no priced drift");
    }
    // The live publish carries the cost as bp of NAV: 0.62618 on this close. The
    // card has to price the trade from that rate and NAV, so the bp it prints and
    // the dollars beside it are the same number twice rather than two rates.
    const priced: MonthlyBlock = {
      ...REAL_MONTHLY,
      drift: { ...base, estimated_cost_bps: 0.62618 },
    };
    render(<MonthlyPanels monthly={priced} />);
    const drift = document.querySelector("[data-drift]")?.textContent ?? "";
    expect(drift).toContain("$184,968");
    expect(drift).toContain("0.6 bp of NAV");
    expect(drift).toContain("$61");
    expect(drift).not.toContain("$158");
    expect(drift).not.toContain("($0)");
    const shown = /([0-9.]+) bp of NAV \(\$([\d,]+)\)/.exec(drift);
    if (!shown) throw new Error(`the card printed no priced cost: ${drift}`);
    expect(Number(shown[1])).toBe(0.6);
    const usdShown = Number(shown[2].replace(/,/g, ""));
    // The card rounds the rate it prints to one place, so the agreement is
    // checked against the document's rate before that rounding: the dollars
    // are that rate times NAV, not a second rate applied to the trade.
    const atNav = (0.62618 / 1e4) * nav;
    expect(Math.abs(usdShown - atNav)).toBeLessThan(1);
  });

  it("5 gives the guard both costs, measured and estimated, negative", () => {
    render(<SnapshotView snapshot={REAL} now={new Date("2026-11-15T14:00:00Z")} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("-1.81 bp estimated");
    expect(text).toContain("-6.3 bp measured from fills");
    expect(text).toContain("-3.1 bp");
    expect(text).toContain("sits inside the monthly era");
  });

  it("6 splits the guard's legs into sent and not sent", () => {
    render(<MonthlyPanels monthly={REAL_MONTHLY} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("97 not sent, under the $250 floor");
    expect(text).not.toContain("97 under the $250 minimum");
    expect(text).toContain("$10,010");
  });

  it("7 calls the sixteen unsent legs unsent, and explains the carried one", () => {
    render(<MonthlyPanels monthly={REAL_MONTHLY} />);
    const table = document.querySelector("[data-trades-reason]")?.textContent ?? "";
    expect(table).toContain("208 sent, 16 not sent (under $250)");
    expect(table).not.toContain("16 owed");
    expect(table).toContain("impossible (under one share)");
  });

  it("8 uses one order count in the bridge", () => {
    render(<SnapshotView snapshot={REAL} now={new Date("2026-11-15T14:00:00Z")} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("1 order");
    expect(text).toContain("orders sent: 1 = 1 order");
    expect(text).not.toContain("2 = 2");
    expect(text).toContain("The book bridge, for tonight");
  });

  it("9 labels the gross position value apart from NAV", () => {
    render(<MonthlyPanels monthly={REAL_MONTHLY} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("now, gross positions");
    expect(text).toContain("$951,949");
    expect(text).toContain("not NAV");
    expect(text).toContain("NAV nets the shorts and adds cash");
  });

  it("10 reconciles the holdings header with its 224 rows", () => {
    render(<SnapshotView snapshot={REAL} now={new Date("2026-11-15T14:00:00Z")} />);
    fireEvent.click(document.querySelector("[data-view='book']") as HTMLElement);
    fireEvent.click(document.querySelector("[data-tab='actual']") as HTMLElement);
    const tab = document.querySelector("[data-tab='actual']")?.textContent ?? "";
    expect(tab).toBe(
      "Actual holdings: 195 held, 28 exited since 10-23, 1 opening tonight (MKC): 224 rows",
    );
    expect(document.querySelectorAll("table[aria-label='actual holdings'] tbody tr")).toHaveLength(
      224,
    );
    const note = document.querySelector("[data-latest-reason]")?.textContent ?? "";
    expect(note).toContain("5 opened, 13 resized, 171 moved by the guard");
  });

  it("11 says the account read once", () => {
    render(<SnapshotView snapshot={REAL} now={new Date("2026-11-15T14:00:00Z")} />);
    const read = document.querySelector("[data-flag='account-read']")?.textContent ?? "";
    expect((read.match(/before the orders went out/g) ?? []).length).toBe(1);
    expect(read).toContain("cannot confirm fills");
  });

  it("12 draws round cumulative ticks", () => {
    render(<SnapshotView snapshot={REAL} now={new Date("2026-11-15T14:00:00Z")} />);
    const ticks = Array.from(
      document.querySelectorAll("[data-overview-cumulative] [data-gridline]"),
    ).map((node) => node.getAttribute("data-gridline"));
    expect(ticks).toEqual(["-250", "-200", "-150", "-100", "-50", "0"]);
  });

  it("13 calls stock P&L stock-specific everywhere", () => {
    render(<SnapshotView snapshot={REAL} now={new Date("2026-11-15T14:00:00Z")} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("stock-specific");
    expect(text).not.toContain("IDIO");
  });

  it("14 points at the Distance card and explains 196 of 196", () => {
    render(<SnapshotView snapshot={REAL} now={new Date("2026-11-15T14:00:00Z")} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("Distance card on Since the rebalance");
    expect(text).not.toContain("the drift card");
    expect(text).toContain("all 196 names in the 2026-10-23 target");
    expect(text).toContain("account holds 195 names now");
  });

  it("15 names the remainder and gives the average a unit", () => {
    render(<SnapshotView snapshot={REAL} now={new Date("2026-11-15T14:00:00Z")} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("unexplained remainder (rounding and data gaps)");
    expect(text).toContain("Average cost per day with fills");
    expect(text).toContain("Hold days since 10-27 show about 1.4 bp");
    expect(text).not.toContain("timing residue");
  });

  it("16 puts the reconciliation above and names both known names", () => {
    render(<SnapshotView snapshot={REAL} now={new Date("2026-11-15T14:00:00Z")} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("reconciliation above");
    expect(text).not.toContain("reconciliation below");
    expect(text).toContain("all 4 steps of the bridge check out");
    expect(text).toContain("cash plus the value of all positions, longs minus shorts");
    expect(text).toContain("run detail: the run's verdict and how the book was built");
    // Derived from the document's close and the holiday calendar, not typed in.
    expect(text).toContain(
      "MKC (its reopening order went out on 11-13 and fills on the next session)",
    );
    expect(text).toContain("KVUE (acquired by KMB; the broker has not converted the shares yet)");
  });
});
