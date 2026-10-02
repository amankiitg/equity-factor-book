// Number and date formatting, in one place so every section says a thing the
// same way. Moved out of `App.tsx` when the page grew sections: a weight shown as
// 4.20% in one panel and 4.2% in the next reads as two different numbers.

/** A fraction as a percentage. `null` is "n/a", never 0.00%. */
export const percent = (value: number | null | undefined, places = 2): string =>
  value === null || value === undefined ? "n/a" : `${(value * 100).toFixed(places)}%`;

/** A dollar amount, rounded to whole dollars, because cents are noise at this size. */
export const dollars = (value: number | null | undefined): string =>
  value === null || value === undefined
    ? "n/a"
    : `${value < 0 ? "-" : ""}$${Math.round(Math.abs(value)).toLocaleString()}`;

/**
 * A signed dollar amount with an explicit plus, for a bar label.
 *
 * A diverging bar's left and right sides mean opposite things, so the sign has
 * to be readable without the colour: -$412,000 and $412,000 must not look alike
 * on a phone in daylight.
 */
export const signedDollars = (value: number | null | undefined): string =>
  value === null || value === undefined
    ? "n/a"
    : `${value >= 0 ? "+" : "-"}$${Math.round(Math.abs(value)).toLocaleString()}`;

/** A date as the day it is, never with a midnight time stapled to it. */
export const dateOnly = (value: string | null | undefined): string | null =>
  value === null || value === undefined || value === "" ? null : value.slice(0, 10);

/** One decimal place: an effective breadth of 70.59213 is 70.6 names, not 70.59. */
export const oneDecimal = (value: number | null | undefined): string =>
  value === null || value === undefined ? "n/a" : value.toFixed(1);

/**
 * A factor exposure to four places, with negative zero shown as zero.
 *
 * The hedge drives every factor to zero to machine precision, so the "after"
 * column holds values like -2.6e-18 whose four-place form is "-0.0000". That is
 * not a negative exposure, it is rounding, and a table of minus-zeroes reads as
 * though the hedge had missed.
 */
export const exposure = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const rounded = Number(value.toFixed(4));
  return (Object.is(rounded, -0) ? 0 : rounded).toFixed(4);
};

/** A plain number, for a count. */
export const count = (value: number | null | undefined): string =>
  value === null || value === undefined ? "n/a" : String(value);

/** A share of the book, as a percentage to two places, with its own sign. */
export const signedPercent = (value: number | null | undefined, places = 2): string => {
  if (value === null || value === undefined) return "n/a";
  const text = Math.abs(value * 100).toFixed(places);
  return `${value < 0 ? "-" : "+"}${text}%`;
};
