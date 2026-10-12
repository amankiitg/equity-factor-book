// Number and date formatting, in one place so every section says a thing the
// same way. Moved out of `App.tsx` when the page grew sections: a weight shown as
// 4.20% in one panel and 4.2% in the next reads as two different numbers.

/** A fraction as a percentage. `null` is "n/a", never 0.00%. */
export const percent = (value: number | null | undefined, places = 2): string => {
  if (value === null || value === undefined) return "n/a";
  // A book's net is a few machine epsilons off flat every evening, and (value *
  // 100).toFixed(2) turns those into "-0.00%": a sign on a number that is zero,
  // which reads as a small short position rather than as the flat book it is. The
  // rounded value decides the sign, not the raw one.
  const rounded = Number((value * 100).toFixed(places));
  // The rounded value decides the sign, not the raw one, and a rounded zero keeps
  // its decimals: 0.00% reads as flat, where 0% reads as a missing value.
  return `${(rounded === 0 ? 0 : rounded).toFixed(places)}%`;
};

/** A dollar amount, rounded to whole dollars, because cents are noise at this size. */
export const dollars = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return "n/a";
  const rounded = Math.round(Math.abs(value));
  // A value that rounds to nothing has no sign to show: the net of a long/short
  // book is a few cents off zero most evenings, and "-$0" reads as a short position
  // in nothing rather than as the zero it is.
  return `${value < 0 && rounded > 0 ? "-" : ""}$${rounded.toLocaleString()}`;
};

/**
 * A signed dollar amount with an explicit plus, for a bar label.
 *
 * A diverging bar's left and right sides mean opposite things, so the sign has
 * to be readable without the colour: -$412,000 and $412,000 must not look alike
 * on a phone in daylight.
 */
export const signedDollars = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return "n/a";
  const rounded = Math.round(Math.abs(value));
  return `${value >= 0 || rounded === 0 ? "+" : "-"}$${rounded.toLocaleString()}`;
};

/** A date as the day it is, never with a midnight time stapled to it. */
export const dateOnly = (value: string | Date | null | undefined): string | null => {
  if (value === null || value === undefined || value === "") return null;
  const text = typeof value === "string" ? value : value.toISOString();
  return text.slice(0, 10);
};

/**
 * A timestamp as its day and its time in UTC, for the one place the time matters.
 *
 * The account's read time is that place: it says whether the book below it is
 * tonight's read or this morning's, and a reader comparing it with the close it
 * belongs to needs the hour. Two cases are not given a time. A value that carries
 * no clock at all (a date, or something unparseable) would render as "T00:00:00"
 * put through a formatter, and a midnight stamp is that same thing: the time is
 * not information there, so the day is shown alone rather than 00:00 claimed as a
 * read at midnight.
 */
export const dateTime = (value: string | null | undefined): string | null => {
  if (value === null || value === undefined || value === "") return null;
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return dateOnly(value);
  const day = at.toISOString().slice(0, 10);
  const time = at.toISOString().slice(11, 16);
  return time === "00:00" ? day : `${day} ${time} UTC`;
};

/**
 * A timestamp as its day and time in New York, for the reader who is in one.
 *
 * The run's own instants are UTC, which is the right way to store them and the
 * wrong way to read them: a close at 16:00 ET is 20:00 UTC or 21:00 UTC depending
 * on the month, so a reader comparing "when was this written" against "when do I
 * look at it" is doing the conversion in their head every morning. The zone is
 * named on the face of it rather than left implied, and the UTC form stays
 * available for anyone matching the page against the logs.
 */
export const etDateTime = (value: string | Date | null | undefined): string | null => {
  if (value === null || value === undefined || value === "") return null;
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return dateOnly(String(value));
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(at);
  const grab = (type: string): string => parts.find((part) => part.type === type)?.value ?? "";
  const day = `${grab("year")}-${grab("month")}-${grab("day")}`;
  const time = `${grab("hour")}:${grab("minute")}`;
  // Intl renders midnight as 24:00 in some locales and 00:00 in others; a stock
  // close is never midnight, but a midnight stamp is a date with no clock on it,
  // and printing "00:00 ET" would claim an instant nobody recorded.
  if (time === "00:00" || time === "24:00") return `${day} ET`;
  return `${day} ${time} ET`;
};

/**
 * An instant in the form the logs carry it: UTC, to the second, with a Z.
 *
 * This is the one thing on the page that exists to be matched against another
 * document rather than read, so it is the run's own instant in the run's own zone
 * rather than a local rendering of it. Sub-second digits are dropped: the logs are
 * read by the second, and the writer's microsecond tail reads as precision nobody
 * is comparing.
 */
export const utcInstant = (value: string | Date | null | undefined): string | null => {
  if (value === null || value === undefined || value === "") return null;
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return String(value);
  return `${at.toISOString().slice(0, 19)}Z`;
};

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

/**
 * A share count: whole shares bare, a fraction to two places.
 *
 * The account's quantities are the broker's own, and a notional buy leaves a
 * fractional position of eleven significant figures: 326.072572039 shares printed
 * as it stands reads as a measurement nobody made. Two places is what the
 * position is worth stating to, and a whole count keeps no decimals because
 * "12.00 shares" claims a precision the broker never wrote down.
 */
export const shares = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const abs = Math.abs(value);
  return Number.isInteger(abs) ? abs.toLocaleString() : abs.toFixed(2);
};

/** A share of the book, as a percentage to two places, with its own sign. */
export const signedPercent = (value: number | null | undefined, places = 2): string => {
  if (value === null || value === undefined) return "n/a";
  const text = Math.abs(value * 100).toFixed(places);
  return `${value < 0 ? "-" : "+"}${text}%`;
};
