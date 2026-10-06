// The book bridge: how the held book became the orders and then the positions.
//
// The page draws three sets side by side - the book, the orders and the account's
// own positions - and each is right on its own. Without the arithmetic between
// them they read as three disagreements: 191 names, 199 orders and 188 positions,
// with nothing saying which names were opened, which were closed, which merely
// moved and which never traded at all.
//
// The numbers are the writers' own, computed in `live/bridge.py` by the evening and
// completed by the morning; nothing here recomputes them, because a page that
// recomputed the arithmetic could disagree with the store about it and there would
// be no way to tell which was right. What the page adds is the check: the block
// carries its own identities, and a block that does not add up is drawn in amber
// with the two numbers that disagree, rather than as a fifth figure to trust.

import { count, dollars, shares } from "./format";
import type { BridgeBlock, Snapshot } from "./types";

/** How many names each gap list prints before it counts the rest. */
const NAMES = 8;

function Named({ names, label }: { names: string[]; label: string }) {
  if (names.length === 0) return null;
  return (
    <li>
      {label}: {names.slice(0, NAMES).join(", ")}
      {names.length > NAMES ? ` and ${names.length - NAMES} more` : ""}
    </li>
  );
}

export function Bridge({ snapshot }: { snapshot: Snapshot }) {
  const block: BridgeBlock | null | undefined = snapshot.bridge;
  if (!block) return null;

  const partial = block.held_after === null || block.held_after === undefined;
  // The one line the reader gets when everything reconciles: held, what moved,
  // what was sent, what filled, what is held now, and what the gap is made of.
  const line = [
    `held ${count(block.held_before)}`,
    `+${count(block.opened)} opened, -${count(block.exited)} exited, ` +
      `${count(block.changed)} changed, ${count(block.under_minimum)} under ` +
      `${dollars(block.under_minimum_usd)}`,
    `${count(block.orders_sent)} orders`,
    partial
      ? "fills from the morning"
      : `${count(block.filled)} filled of ${count(block.orders_sent)}`,
    partial ? null : `held ${count(block.held_after)}`,
  ]
    .filter((part): part is string => part !== null)
    .join(" → ");

  return (
    <section
      data-section="bridge"
      data-bridge={block.holds ? "reconciled" : "broken"}
      data-tone={block.holds ? "plain" : "warn"}
      className={
        block.holds
          ? "rounded border border-slate-200 bg-white p-3"
          : "rounded border border-amber-300 bg-amber-50 p-3 text-amber-900"
      }
    >
      <h2 className="text-base font-semibold">The book bridge</h2>
      <p className="mt-1 font-mono text-sm tabular-nums" data-bridge-line="true">
        {line}
      </p>

      {!block.holds ? (
        <div data-bridge-check="failed" role="status" className="mt-2 text-sm">
          <p className="font-semibold">This bridge does not add up</p>
          <ul>
            {block.identities
              .filter((check) => !check.holds)
              .map((check) => (
                <li key={check.name}>
                  {check.name}: <span className="font-mono">{check.left}</span> against{" "}
                  <span className="font-mono">{check.right}</span>
                </li>
              ))}
          </ul>
          {block.unexplained.length > 0 ? (
            <p className="mt-1">
              In the book and not in the account, with nothing explaining it:{" "}
              {block.unexplained.join(", ")}
            </p>
          ) : null}
        </div>
      ) : null}

      <details className="mt-2 text-sm" data-bridge-names="true">
        <summary className="cursor-pointer">
          the names the gap is made of{partial ? " (the morning adds the account)" : ""}
        </summary>
        <ul className="mt-1 list-disc pl-5">
          <Named
            names={block.reversals_pending}
            label="closed tonight, reopening next evening"
          />
          <Named
            names={block.removed_without_order.map((item) => item.ticker)}
            label="left the account with no order behind it"
          />
          <Named names={block.unexplained} label="in neither list" />
          {block.removed_without_order.map((item) => (
            <li key={item.ticker} data-removed={item.ticker}>
              {item.ticker}: {shares(item.quantity)} shares (
              {dollars(item.notional)})
            </li>
          ))}
        </ul>
        <ul className="mt-1 text-xs text-slate-500">
          {block.identities.map((check) => (
            <li key={check.name} data-identity={check.name} data-holds={String(check.holds)}>
              {check.name}: {check.left}
              {check.holds ? " = " : " ≠ "}
              {check.right}
            </li>
          ))}
        </ul>
        <p className="mt-1 text-xs text-slate-500">
          {partial
            ? "The evening published what it had read, sized and sent; the 15:30 UTC morning completes it with the fills and the account."
            : "Every identity above is checked by the runs that wrote the block, not by this page: a bridge that does not add up is shown in amber rather than smoothed over."}
        </p>
      </details>
    </section>
  );
}
