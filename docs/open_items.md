# Open items

Append-only list of issues that a later sprint must resolve before a
stated milestone. Each item names the owning sprint and the blocker it
removes. No work is scheduled for these in the sprint that records them.

## 2026-09-10: E11 requires an ongoing constituent source before the book runs

Owner: E11. The Wikipedia changes table is pinned to revision 1368675864
and freezes the universe at 2026-08-05 (see the Hygiene Ledger and
sprints/E1/PROBES.md). A paper-traded book cannot run on a frozen
universe; E11 must secure an ongoing constituent source (a vendor feed
or a maintained open source) and re-run the universe reconstruction
before the book goes live. Recorded in Sprint E2, no work in E2.

## 2026-09-10: price vendor history needs security identity, found by F2.6

Owner: E1 follow-up, blocking any use of the pre-2017 panel for names
whose symbols were reused. Four of the 858 tickers in the price universe
(CPWR, EP, MI, POM) have reused symbols: each was a real S&P 500 member
that was acquired or delisted, and the symbol was later taken by an
unrelated listing. The vendor splices both histories into one series with
no split to explain the jump, so adjusted-close ratios above 5x appear
with no corporate action behind them. The real history of the original
issuer, Compuware, El Paso, Marshall & Ilsley and Pepco, is absent from
the panel.

E2 drops these four names from the estimation panel and records the
exclusion in the TS-v1 registry entry, but dropping is a mitigation:
every portfolio that used those names as point-in-time members during
2010 to 2016 (the equal-weight seed book is the visible case, with POM
held for 1,627 member days) loses that exposure instead of regaining the
correct one. The fix is a security-identity source so that prices attach
to an issuer rather than to a symbol: FIGI or CRSP PERMNO via a vendor
with delisting-aware history. Until then, no result in EFB may claim
point-in-time universe coverage for 2010 to 2016 without this caveat.
Recorded in Sprint E2 as the failing criterion F2.6.
