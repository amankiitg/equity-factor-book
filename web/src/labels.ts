// The units, in one place, because the redesign's whole point is that a number
// without its denominator is a number nobody can check.
//
// The book's gross is 1.0 of NAV by construction, so the two denominators happen to
// coincide on this book - and the page still writes the one it means, because they do
// not coincide in general (a book at 80% of NAV has a 100% gross as a fraction of
// itself) and because a reader comparing today's page against last month's needs to
// know which of the two moved. Weights, turnover and costs are all quoted against NAV.
//
// Costs get two labels on purpose, and they are different sentences:
//
// - **expected expense**: the evening's forecast of what the rebalance costs, positive,
//   one session's spread, impact, commission and the borrow over the horizon;
// - **cost contribution to P&L**: what the fills and the borrow actually took out of
//   the day, signed, so a favourable fill is a positive contribution.
//
// The two are not a forecast and its error: they are different statistics about
// different windows, and the page says so rather than setting them side by side as
// though one were the other's outcome.

import { dollars } from "./format";

/** What every ratio on the page is quoted against. */
export const NAV = "NAV";

/** A cost in basis points of NAV, with the denominator written on it. */
export const bpOfNav = (value: number | null | undefined): string =>
  value === null || value === undefined ? "n/a" : `${value.toFixed(2)} bp of NAV`;

/** A dollar amount, named as a share of NAV. */
export const dollarsOfNav = (value: number | null | undefined): string =>
  value === null || value === undefined ? "n/a" : `${dollars(value)} of NAV`;

/**
 * A factor's name as a reader knows it.
 *
 * The stored keys are the design's own: `resid_vol`, `sector_45`. A column of
 * those reads as machine output, so the page says Residual vol and Information
 * Technology wherever it shows a factor. The sector's GICS number is part of the key,
 * not part of its name, so it is dropped. An unknown key keeps its own name rather
 * than disappearing.
 */
const FACTOR_WORDS: Record<string, string> = {
  beta: "Beta",
  liquidity: "Liquidity",
  market: "Market",
  momentum: "Momentum",
  resid_vol: "Residual vol",
  reversal: "Reversal",
  size: "Size",
  sector_10: "Energy",
  sector_15: "Materials",
  sector_20: "Industrials",
  sector_25: "Consumer Discretionary",
  sector_30: "Consumer Staples",
  sector_35: "Health Care",
  sector_40: "Financials",
  sector_45: "Information Technology",
  sector_50: "Communication Services",
  sector_55: "Utilities",
  sector_60: "Real Estate",
};

export const factorWord = (key: string): string => FACTOR_WORDS[key] ?? key;

/** The label on the evening's forecast, as distinct from what the day cost. */
export const EXPECTED_EXPENSE = "expected expense";

/** The label on the signed cost inside the attribution. */
export const COST_CONTRIBUTION = "cost contribution to P&L";
