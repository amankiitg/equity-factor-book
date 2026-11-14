// The one panel every status line on the page is drawn from.
//
// The tone decides the colour *and* the role, and the two are kept in step on
// purpose: red is an `alert` (a run failed or stopped, which is the thing the page
// must not let a reader scroll past) and everything else is a `status`, because an
// amber panel that announces itself as an alert is how a page teaches its reader to
// ignore alerts.

import { useState } from "react";

import type { Tone } from "./status";

/**
 * The (i) itself, drawn rather than typed.
 *
 * The marker used to be the letter `i` in the button's text, which a screen reader
 * announced as a word and a text copy pasted into whatever sat beside the title. An
 * icon element is decoration: the button keeps the accessible name, and no letter
 * joins the title when the line is read or copied.
 */
export function InfoIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      <circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <circle cx="8" cy="4.7" r="0.95" fill="currentColor" />
      <path d="M8 7.1v4.1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

const TONE_CLASSES: Record<Tone, string> = {
  bad: "bg-red-50 text-red-900 border-red-500",
  warn: "bg-amber-50 text-amber-900 border-amber-400",
  info: "bg-slate-100 text-slate-800 border-slate-400",
  good: "bg-emerald-50 text-emerald-900 border-emerald-400",
};

const PILL_CLASSES: Record<Tone, string> = {
  bad: "bg-red-600 text-white",
  warn: "bg-amber-500 text-white",
  info: "bg-slate-600 text-white",
  good: "bg-emerald-700 text-white",
};

export function toneClass(tone: Tone): string {
  return TONE_CLASSES[tone];
}

export function pillClass(tone: Tone): string {
  return PILL_CLASSES[tone];
}

export function Panel({
  tone,
  title,
  detail,
  hook,
  info,
}: {
  tone: Tone;
  title: string;
  detail: string;
  hook?: string;
  /** The (i) beside the title, on a panel that is a card rather than a page state. */
  info?: React.ReactNode;
}) {
  return (
    <section
      data-alert={hook}
      data-tone={tone}
      role={tone === "bad" ? "alert" : "status"}
      className={`border-l-4 px-3 py-2 ${TONE_CLASSES[tone]}`}
    >
      <p className="font-semibold">
        {title}
        {info ? <HowToRead>{info}</HowToRead> : null}
      </p>
      {detail ? <p className="text-sm">{detail}</p> : null}
    </section>
  );
}


/**
 * The (i) beside a title: what the number is, why it moves, one real example.
 *
 * The explanation used to be a paragraph above every panel, which cost the reader
 * a line of scroll on every panel and repeated the title in the first clause. It
 * is a popover now: the title carries the marker, and the sentence is one tap
 * away. The marker keeps its old data attribute so the page's own checks can
 * still find it.
 */
export function HowToRead({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block align-middle" data-how-to-read="true">
      <button
        type="button"
        aria-label="how to read this"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="ml-1.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
      >
        <InfoIcon />
      </button>
      {open ? (
        <span
          role="dialog"
          aria-label="how to read this"
          className="absolute left-0 top-5 z-20 w-72 rounded border border-slate-300 bg-white p-2 text-xs font-normal normal-case tracking-normal leading-snug text-slate-700 shadow-lg"
        >
          {children}
        </span>
      ) : null}
    </span>
  );
}

/**
 * The words the page uses, defined once.
 *
 * The page explained these in several places, in slightly different sentences, which
 * is how a reader ends up with two definitions of "target" and no way to tell which
 * one the number beside it meant. One dropdown, one definition each. The first three
 * are the three books the page compares; the rest are the words a first-time reader
 * meets on every card.
 */
const WORDS: Array<[string, string]> = [
  ["account", "what the broker says we hold right now"],
  ["target", "what tonight's run wants us to hold after the next fills"],
  ["store", "the loop's own record of what it last asked for"],
  ["leg", "one order in one direction: buying is one, selling is another"],
  ["NAV", "the book's own net value: what the positions are worth"],
  ["bp", "a basis point, one hundredth of a percent of NAV"],
  [
    "hedge",
    "the re-weighting of names the book already holds that cancels the market, sector and style bets it did not mean to take",
  ],
  [
    "drift guard",
    "the hold-day repair: it moves the book back to factor-neutral when a factor exposure passes 5% of NAV",
  ],
];

export function Glossary() {
  return (
    <details data-glossary="true" className="rounded border border-slate-200 bg-white">
      <summary className="cursor-pointer px-2 py-1 text-xs font-medium text-slate-700">
        What the words mean
      </summary>
      <dl className="grid gap-1 px-2 pb-2 text-xs sm:grid-cols-3">
        {WORDS.map(([word, meaning]) => (
          <div key={word}>
            <dt className="font-mono font-semibold">{word}</dt>
            <dd className="text-slate-600">{meaning}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
