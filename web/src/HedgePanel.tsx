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

/** The rebalance's footprint: the same two numbers, measured on the close that hedged. */
function AnchoredHedge({ block }: { block: NonNullable<MonthlyBlock["hedge"]> }) {
  const shares = block.variance_shares ?? [];
  return (
    <>
      <p className="mt-1 text-sm text-slate-700" data-hedge="opening">
        The hedge re-weights the stocks we already hold so the book does not move with the market,
        sectors or style factors. On the {block.anchor} close it moved {count(block.moved_names)}{" "}
        names, {dollars(block.moved_usd)} of trading
        {block.share_of_turnover === null
          ? ""
          : ` (${percent(block.share_of_turnover, 0)} of that rebalance's turnover)`}
        . Nothing was hedged tonight, which is what a hold day is.
      </p>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
        <div data-card="hedge-moved">
          <div className="text-[0.65rem] uppercase tracking-wide text-slate-500">
            names the hedge moved
          </div>
          <div className="font-mono text-base tabular-nums">
            {count(block.moved_names)} of {count(block.book_names)}
          </div>
          <div className="text-xs text-slate-600">{dollars(block.moved_usd)} of legs</div>
        </div>
        <div data-card="hedge-share">
          <div className="text-[0.65rem] uppercase tracking-wide text-slate-500">
            largest share of specific risk
          </div>
          <div className="font-mono text-base tabular-nums">
            {percent(shares[0]?.variance_share, 1)}
          </div>
          <div className="text-xs text-slate-600">
            {shares[0]?.ticker ?? "n/a"} at that share, {percent(shares[0]?.weight)} of NAV
          </div>
        </div>
      </div>
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
        <h2 className="text-base font-semibold">The hedge&apos;s own footprint</h2>
        <AnchoredHedge block={anchored} />
        <p className="mt-1 text-xs text-slate-600">
          <span className="font-medium">A proxy.</span> The names carry the loop&apos;s own
          record that the hedge moved them, and the shares are that close&apos;s
          reconciliation of the traded book&apos;s predicted specific variance. Neither says a
          position exists <em>because</em> of the hedge.
        </p>
      </section>
    );
  }

  return (
    <section data-section="hedge" className="rounded border border-slate-200 bg-white p-3">
      <h2 className="text-base font-semibold">The hedge&apos;s own footprint</h2>
      <p className="mt-1 text-sm text-slate-700" data-hedge="opening">
        The hedge re-weights the stocks we already hold so the book does not move with the market,
        sectors or style factors. On {dateOnly(snapshot.target_close) ?? "this"} close it moved{" "}
        {count(moved.length)} names, {dollars(movedNotional)} of trading
        {shareOfTurnover === null ? "" : ` (${percent(shareOfTurnover, 0)} of the day's turnover)`}.
      </p>
      <p className="mt-1 text-xs text-slate-600">
        <span className="font-medium">A proxy.</span> The names below carry the loop's own
        record that the hedge moved them, and the notional of the leg it built; the shares
        beside them are the traded book's predicted specific variance as the reconciliation
        computed it. Neither says a position exists <em>because</em> of the hedge — that
        needs each name's pre-hedge and post-hedge target, which the evening does not
        publish.
      </p>

      <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
        <div data-card="hedge-moved">
          <div className="text-[0.65rem] uppercase tracking-wide text-slate-500">
            names the hedge moved
          </div>
          <div className="font-mono text-base tabular-nums">
            {count(moved.length)} of {count(names.length)}
          </div>
          <div className="text-xs text-slate-600">{dollars(movedNotional)} of legs</div>
        </div>
        <div data-card="hedge-share">
          <div className="text-[0.65rem] uppercase tracking-wide text-slate-500">
            gross those names carry
          </div>
          <div className="font-mono text-base tabular-nums">
            {percent(
              facts.nav === null
                ? null
                : moved.reduce(
                    (total, name) => total + Math.abs(name.weight ?? 0),
                    0,
                  ),
            )}{" "}
            of NAV
          </div>
          <div className="text-xs text-slate-600">as the book holds them now</div>
        </div>
      </div>

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
