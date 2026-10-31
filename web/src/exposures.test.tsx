// "The hedge" on a hold day: the pair that means something is the rebalance's.
//
// The document is the one the page was served for the 2026-10-30 close, with the
// anchor close's own exposure vectors in the monthly block - the numbers the evening
// published for the 2026-10-23 rebalance, not a hand-built book. On that close
// nothing was hedged, so the document's own before/after pair is one vector twice and
// the old panel called it "the hedge"; the panel now shows the rebalance's pair and
// tonight's book beside it.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { anchoredExposures, ExposuresSection } from "./ExposuresSection";
import served from "../fixtures/snapshot_2026-10-30_evening.json";
import type { MonthlyBlock, Snapshot } from "./types";

const HOLD = served as unknown as Snapshot;
const HOLD_MONTHLY = HOLD.monthly as MonthlyBlock;

function headerTexts(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("thead th")).map(
    (node) => node.textContent ?? "",
  );
}

describe("the exposures panel on a hold day", () => {
  it("is anchored on the rebalance's own close", () => {
    const block = anchoredExposures(HOLD_MONTHLY);
    expect(block).not.toBeNull();
    expect(block?.anchor).toBe("2026-10-23");
  });

  it("shows before and after the anchor's hedge, then tonight", () => {
    const { container } = render(<ExposuresSection snapshot={HOLD} />);
    const headers = headerTexts(container);
    expect(headers).toContain("before the hedge (2026-10-23)");
    expect(headers).toContain("after the hedge (2026-10-23)");
    expect(headers.join(" ")).toContain("now (2026-10-30)");
  });

  it("keeps the machine-precision claim on the anchor's after column only", () => {
    const { container } = render(<ExposuresSection snapshot={HOLD} />);
    const verdict = container.querySelector("[data-hedge-verdict]");
    const text = verdict?.textContent ?? "";
    expect(text).toContain("after the 2026-10-23 hedge");
    expect(text).toContain("zero to machine precision");
    expect(text).toContain("Nothing was hedged tonight");
    // The anchor's after column really is flat, and tonight's own book is not.
    expect(text).not.toContain("worst residual factor exposure after the hedge: 0.41%");
    const nowCell = container.querySelector('[data-now="reversal"]');
    expect(nowCell?.textContent ?? "").not.toBe("0.00%");
  });

  it("shows the anchor's before column as a real exposure, not the same vector", () => {
    const { container } = render(<ExposuresSection snapshot={HOLD} />);
    const cells = (key: string) =>
      Array.from(
        container.querySelectorAll(`[data-factor="${key}"] td`),
      ).map((node) => node.textContent ?? "");
    const market = cells("market");
    // before the 2026-10-23 hedge, after it, then now: three different readings.
    expect(market[1]).not.toBe(market[2]);
    expect(market[2]).not.toBe(market[3]);
  });

  it("adds the drift guard's line, with the legs it sent", () => {
    const { container } = render(<ExposuresSection snapshot={HOLD} />);
    const line = container.querySelector("[data-hedge-guard]");
    const text = line?.textContent ?? "";
    expect(text).toContain("drift guard tonight");
    expect(text).toContain("6.41%");
    expect(text).toContain("0.41%");
    expect(text).toContain("5.00%");
    expect(text).toContain("109");
    expect(text).toContain("assumes they fill");
  });

  it("renders exactly as before when there is no monthly block", () => {
    const daily = { ...HOLD, monthly: undefined } as unknown as Snapshot;
    expect(anchoredExposures(undefined)).toBeNull();
    const { container } = render(<ExposuresSection snapshot={daily} />);
    const headers = headerTexts(container);
    expect(headers).toContain("before");
    expect(headers).toContain("after");
    expect(headers.join(" ")).not.toContain("now (");
    expect(container.querySelector("[data-hedge-guard]")).toBeNull();
    expect(container.querySelector("[data-hedge-verdict]")?.textContent ?? "").toContain(
      "the hedge is exact",
    );
  });

  it("renders exactly as before on a rebalance day", () => {
    const rebalance = {
      ...HOLD,
      monthly: { ...HOLD_MONTHLY, anchor: { ...HOLD_MONTHLY.anchor, day: "rebalance" } },
    } as unknown as Snapshot;
    expect(anchoredExposures(rebalance.monthly)).toBeNull();
    const { container } = render(<ExposuresSection snapshot={rebalance} />);
    expect(headerTexts(container).join(" ")).not.toContain("before the hedge (");
  });
});
