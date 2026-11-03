# The KVUE merger: what the true return is, and how the loop should record one

Read-only, 2026-11-03. Nothing here is implemented.

## What happened

Kimberly-Clark completed its acquisition of Kenvue on **2026-11-02**. The terms, from
KMB's Form 8-K Item 2.01: each KVUE share converted into **0.14625 KMB shares plus
$3.50 cash**. KVUE will not trade again.

The broker agrees the security is gone and disagrees about nothing else:

| read | answer |
| --- | --- |
| `GET /v2/assets/KVUE` | `status=inactive`, `tradable=false`, `name=Kenvue Inc.` |
| `GET /v2/assets/KMB` | `status=active`, `tradable=true` |
| corporate announcements, `ca_type=merger`, 2026-10-25..11-03 | `merger_completion`, initiating `KMB`, target `KVUE`, no dates, `cash=0.0` |
| account activities since 2026-10-30 | **no** `CSD`, `CSW`, `MISC` or cash-in-lieu row for either name |
| the account's positions | KVUE `705.098617682` shares, KMB `66.92550207` shares |

So the paper account still holds KVUE at the broker's last mark of **$19.31**, which is
KVUE's 2026-10-30 close (the vendor's last print for it), and the merger proceeds have
not been posted.

## The true 2026-11-02 return

Inputs, all measured: KVUE close 2026-10-30 **$19.31**; KMB close 2026-11-02
**$108.25**; terms 0.14625 KMB plus $3.50.

```
consideration per KVUE share = 0.14625 * 108.25 + 3.50 = 15.83156250 + 3.50 = 19.3315625
return on 2026-11-02        = 19.3315625 / 19.31 - 1        = +0.0011166 = +11.17 bp
```

The stale mark is therefore not misleading in size: $19.31 against a true $19.3316 is
**11 bp**, or $15.20 on the 705.098617682 shares. The vendor prints nothing for KVUE on
2026-11-02, which is why the evening's price map has a NaN for it, and why the price
drop fired rather than a 100% loss being recorded.

What the account should end up with once the action is applied:

```
103.120672836 KMB shares and $2,467.85 cash, worth 13,630.66 at the 2026-11-02 closes
against the 13,615.45 the stale mark says, on 1.4% of NAV
```

KMB is already held at 66.92550207 shares, so the post-action KMB position is
**170.046174906** shares, about 1.9% of NAV, which is a book change the loop did not
make and cannot explain from its own orders.

## How the panel, the model and the attribution should record it

**Returns panel.** A merger is not a price series ending; it is a total return with a
cash and a stock leg. The correct row for the target on the completion session is

```
r_KVUE = (0.14625 * P_KMB,t + 3.50) / P_KVUE,t-1 - 1
```

and no row at all after it, because the security has no series to continue. The panel
has no writer for that shape today: `extend_returns` computes returns from closes and
carries a NaN when a close is missing, and `corporate_actions.apply_to_artifact` knows
the split and spin-off shapes only - a split carries a factor, a spin-off carries a
child, a cash-and-stock merger carries a ratio **and** a cash amount **and** the
acquirer's own close. It should become the third contract, with the same rule the other
two follow: apply it only when it can be reproduced from a recorded row, and null the
cell rather than guess.

**Risk model.** The target must leave the fitted panel on the completion session, not
five days later when the descriptor panel notices: its specific variance is undefined
once the security stops printing, and a name with a NaN close but a fitted variance is
exactly what sizing will try to hold. The acquirer's own variance is unaffected in
principle but its realised volatility rises through the deal, so nothing about KMB
should be backfilled from before the close.

**Attribution.** The position's P&L for the session is `consideration - previous close`,
attributed to the name, not a price return: the loop's `attribution` table has one
`pnl` per name per close and would otherwise record a total loss the day the print
disappears. The cash leg is not a trade and must not appear as a fill; the stock leg is
not a trade either. Both are corporate-action receipts, and neither has an order id -
which is why the broker's own activity feed, not the order table, is where they will
appear when they do.

## The plan for held names and announced mergers

1. **A pre-trade check, not a post-mortem.** Before building any leg, ask the broker for
   the asset's status; refuse a leg for an asset that is not `active` and `tradable`.
   This is implemented for 2026-11-03 (`live/alpaca.py`, the inactive feed plus the
   `ASSET_INACTIVE` code, recorded as owed and never carried). It catches the event on
   the day it happens rather than five days later.
2. **A forward-looking read while the asset is still active.** The status flips on the
   completion day, and the position can be held right up to it. One daily read of the
   broker's `merger` announcements for *held* symbols, from the same feed already used
   for spin-offs, gives the loop a warning it can act on: name the holding in the
   email, and mark it unaddable on the completion date. The filter is a completion date
   the loop has, not a guess about whether a deal will close.
3. **A written-off position is not a position.** When the record arrives, the name must
   leave the book, the weights, the drift and the guard reading in one step, and the
   account's stale mark must stop counting toward NAV. Until the broker posts the
   proceeds there is a real asset (the consideration) and a fake price; the loop should
   value the consideration, or say it cannot, rather than leave $13,615 of dead mark on
   the page.
4. **What must not happen again.** A name with no print must never reach the
   quantization (`int(NaN / price)` cost the 2026-11-02 evening), and a leg for a
   retired asset must never be carried every evening as though it might fill tomorrow.

## Caveats

The paper account has not applied the action, so every post-action number here is
computed from the terms and the closes, not observed. The cash leg may arrive with the
stock leg or later; the broker's announcement carries `cash=0.0`, so the record itself
does not say $3.50 is owed, which is one more reason the terms have to come from the
filing rather than from the account.
