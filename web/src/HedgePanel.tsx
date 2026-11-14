// The hedge's own footprint on the book: what it moved, and what carries the risk.
//
// Two numbers about the same thing, and neither is a causal claim. The first is the
// reason the loop recorded on each name. On 2026-10-09 that is 58 of the 159 names,
// carrying $64,028 of the evening's legs: names the sizing did not want for their
// alpha and the projection moved anyway. The second is the book's predicted specific
// variance, name by name, from `reconciliation.traded_risk.top_variance_shares` -
// SMCI at 14.2% of it on that close, on a book whose largest *weight* is 1.79%.
//
// The two are shown together because the gap between them is the finding: a name can
// be a rounding error by weight and the largest single risk in the book. What the
// panel cannot say is that the hedge *created* a position or flipped its side - that
// needs the pre-hedge and post-hedge target on each name, which the evening does not
// publish - so it is labelled a proxy, and the label says which claim is the proxy and
// which is measured.
//
// The variance shares come from the reconciliation, so they are the traded book's own
// risk figures rather than the page's recomputation, and when the block is absent the
// panel says so instead of drawing a share of nothing.

import { Details } from "./Details";
import { HowToRead } from "./Panel";
import { count, dateOnly, dollars, percent } from "./format";
import type { BookFacts } from "./book";
import type { MonthlyBlock, Snapshot } from "./types";

/**
 * The block's hedge footprint, when it is the one to show.
 *
 * `null` on a rebalance day, on a daily book and on any document written before the
 * field existed: those are the closes where tonight's own legs are the right answer,
 * because tonight is the close that hedged.
 */
export function anchoredHedge(monthly?: MonthlyBlock | null) {
  const block = monthly?.hedge;
  if (!block || !block.anchor) return null;
  if (monthly?.anchor?.day !== "cadence") return null;
  return block;
}

/** A close as the page writes it: the month and the day, never the year. */
function shortDay(value: string | null | undefined): string {
  if (!value) return "last";
  return value.slice(5, 10);
}

/** The one sentence a hedge footprint is: who it moved, how much, and what share. */
function footprint(day: string, moved: number | null, book: number | null, usd: number | null, share: number | null): string {
  const name = moved === 1 ? "name" : "names";
  const tail = share === null ? "" : `, ${percent(share, 0)} of that day's trading`;
  return `At the ${day} rebalance the hedge adjusted ${count(moved)} of ${count(book)} ${name} (${dollars(usd)}${tail}).`;
}

/** The rebalance's footprint: one line, measured on the close that hedged. */
function AnchoredHedge({ block }: { block: NonNullable<MonthlyBlock["hedge"]> }) {
  const shares = block.variance_shares ?? [];
  return (
    <>
      <p className="mt-1 text-sm text-slate-700" data-hedge="opening">
        {footprint(
          shortDay(block.anchor),
          block.moved_names,
          block.book_names,
          block.moved_usd,
          block.share_of_turnover,
        )}{" "}
        Nothing was hedged tonight, which is what a hold day is.
      </p>
      {shares.length > 0 ? (
        <Details
          hook="hedge-shares"
          summary={
            <>
              {shares[0]?.ticker} carries {percent(shares[0]?.variance_share, 1)} of the
              rebalance book&apos;s predicted stock-specific risk
            </>
          }
        >
          <table aria-label="top variance shares" className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="py-1 pr-2">name</th>
                <th className="py-1 pr-2">share of the book&apos;s predicted specific risk</th>
                <th className="py-1">weight</th>
              </tr>
            </thead>
            <tbody>
              {shares.map((entry) => (
                <tr key={entry.ticker} data-variance-share={entry.ticker}>
                  <td className="py-1 pr-2 font-mono">{entry.ticker}</td>
                  <td className="py-1 pr-2 tabular-nums">{percent(entry.variance_share, 2)}</td>
                  <td className="py-1 tabular-nums">{percent(entry.weight)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-slate-500">
            From <code>reconciliation.traded_risk</code> for the {block.anchor} close
            {block.n_eff === null ? "" : `; effective breadth ${count(Math.round(block.n_eff))}`}
            {block.max_weight === null ? "" : `, largest weight ${percent(block.max_weight)}`}
            .
          </p>
        </Details>
      ) : null}
    </>
  );
}

/** The reason string the loop writes on a name the hedge moved. */
const HEDGE_REASON = "the hedge moved";

export function HedgePanel({
  snapshot,
  facts,
  monthly,
}: {
  snapshot: Snapshot;
  facts: BookFacts;
  /** The anchored block: a hold day's hedge is the rebalance's, not tonight's. */
  monthly?: MonthlyBlock | null;
}) {
  const names = snapshot.book?.names ?? [];
  const moved = names.filter((name) => (name.reason ?? "").trim() === HEDGE_REASON);
  const movedNotional = moved.reduce(
    (total, name) => total + Math.abs(name.traded_notional ?? 0),
    0,
  );
  const risk = snapshot.reconciliation?.traded_risk ?? null;
  // The hedge's legs as a share of the day's turnover, against the card's own basis.
  const turnover =
    snapshot.reconciliation?.sent_notional ?? snapshot.reconciliation?.intended_notional ?? null;
  const shareOfTurnover = turnover === null || turnover === 0 ? null : movedNotional / turnover;
  const shares = risk?.top_variance_shares ?? [];
  const anchored = anchoredHedge(monthly);
  if (names.length === 0 && !anchored) return null;

  if (anchored) {
    return (
      <section
        data-section="hedge"
        data-hedge-anchored="true"
        className="rounded border border-slate-200 bg-white p-3"
      >
        <h2 className="text-base font-semibold">
          The hedge&apos;s own footprint
          <HowToRead>
            Without a hedge the book would still move with the market, with sectors and with
            styles, because the stocks it holds share those exposures. The hedge is the part
            of each position that cancels them, so it re-weights names the book already holds
            instead of adding new ones. Example: at the 10-23 rebalance it adjusted 88 of 196
            names for $122,805.
          </HowToRead>
        </h2>
        <AnchoredHedge block={anchored} />
      </section>
    );
  }

  return (
    <section data-section="hedge" className="rounded border border-slate-200 bg-white p-3">
      <h2 className="text-base font-semibold">
        The hedge&apos;s own footprint
        <HowToRead>
          Without a hedge the book would still move with the market, with sectors and with
          styles, because the stocks it holds share those exposures. The hedge is the part
          of each position that cancels them, so it re-weights names the book already holds
          instead of adding new ones. Example: this close adjusted {count(moved.length)} of{" "}
          {count(names.length)} names for {dollars(movedNotional)}.
        </HowToRead>
      </h2>
      <p className="mt-1 text-sm text-slate-700" data-hedge="opening">
        {footprint(
          shortDay(dateOnly(snapshot.target_close)),
          moved.length,
          names.length,
          movedNotional,
          shareOfTurnover,
        )}
      </p>

      {shares.length > 0 ? (
        <Details
          hook="hedge-shares"
          summary={
            <>
              {shares[0]?.ticker} carries {percent(shares[0]?.variance_share, 1)} of the
              book&apos;s predicted stock-specific risk
            </>
          }
        >
          <table aria-label="top variance shares" className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="py-1 pr-2">name</th>
                <th className="py-1 pr-2">share of the book&apos;s predicted specific risk</th>
                <th className="py-1">weight</th>
              </tr>
            </thead>
            <tbody>
              {shares.map((entry) => {
                const row = names.find((name) => name.ticker === entry.ticker);
                return (
                  <tr key={entry.ticker} data-variance-share={entry.ticker}>
                    <td className="py-1 pr-2 font-mono">{entry.ticker}</td>
                    <td className="py-1 pr-2 tabular-nums">
                      {percent(entry.variance_share, 2)}
                    </td>
                    <td className="py-1 tabular-nums">{percent(row?.weight)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-slate-500">
            From <code>reconciliation.traded_risk</code>, the traded book&apos;s own risk
            figures
            {risk?.n_eff === null || risk?.n_eff === undefined
              ? ""
              : `; effective breadth ${count(Math.round(risk.n_eff))}`}
            {risk?.max_weight === undefined
              ? ""
              : `, largest weight ${percent(risk.max_weight)}`}
            . A name at the top of this table can be a small weight and a large risk at
            once, which is the reason to read it beside the weights rather than instead of
            them.
          </p>
        </Details>
      ) : (
        <p data-hedge-shares="absent" className="mt-2 text-xs text-slate-500">
          the reconciliation carries no predicted-variance shares for this close, so the
          concentration behind the hedge is not shown rather than drawn as zero
        </p>
      )}

      {moved.length > 0 ? (
        <ul data-hedge-names="true" className="mt-2 text-xs text-slate-600">
          {moved
            .slice()
            .sort(
              (a, b) =>
                Math.abs(b.traded_notional ?? 0) - Math.abs(a.traded_notional ?? 0),
            )
            .slice(0, 8)
            .map((name) => (
              <li key={name.ticker}>
                <span className="font-mono">{name.ticker}</span>{" "}
                {dollars(name.traded_notional ?? 0)} moved, holds {percent(name.weight)}
              </li>
            ))}
          {moved.length > 8 ? <li>and {moved.length - 8} more</li> : null}
        </ul>
      ) : null}
    </section>
  );
}
