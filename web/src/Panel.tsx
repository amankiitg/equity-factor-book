// The one panel every status line on the page is drawn from.
//
// The tone decides the colour *and* the role, and the two are kept in step on
// purpose: red is an `alert` (a run failed or stopped, which is the thing the page
// must not let a reader scroll past) and everything else is a `status`, because an
// amber panel that announces itself as an alert is how a page teaches its reader to
// ignore alerts.

import type { Tone } from "./status";

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
}: {
  tone: Tone;
  title: string;
  detail: string;
  hook?: string;
}) {
  return (
    <section
      data-alert={hook}
      data-tone={tone}
      role={tone === "bad" ? "alert" : "status"}
      className={`border-l-4 px-3 py-2 ${TONE_CLASSES[tone]}`}
    >
      <p className="font-semibold">{title}</p>
      {detail ? <p className="text-sm">{detail}</p> : null}
    </section>
  );
}
