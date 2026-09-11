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

## 2026-09-10: the risk model needs a residual covariance, not a diagonal

Owner: E3. Found by close-out task C4. The portfolio risk decomposition
uses sigma_p^2 = w' B F B' w + w' D w with D diagonal, so residual
co-movement between names is assumed away. For the equal-weight seed book
that is harmless, because the factor share is 99.2 percent either way. For
the sector-neutral momentum long/short seed book it changes the answer
completely: the factor share is 0.0939 with name-level TS betas and
last-month weights, 0.1381 with the portfolio regression betas and MOM
removed, and 0.8951 with the same betas and all six factors, while the
regression explains 0.5606 of daily variance. The C4 check itself passes
(the MOM loading is +0.2947 with t 29.0, so the book is a genuine momentum
position), which is what makes the share discrepancy a risk-model problem
rather than a book-construction problem.

E3 should estimate w' Sigma_resid w directly, from the cross-sectional
residual covariance, and report the factor share with that term in place.
Until then, no EFB result may quote a single idio share for a long/short
book without the measurement method attached.

## 2026-09-10: the 32 dropped symbols need identity repair, not exclusion

Owner: E1 follow-up. Close-out C1 dropped 36 reused symbols. Four show the
splice in the prices; the other 32 have a name mismatch and clean prices,
so the member's own history is missing from the vendor data entirely. Nine
of the 32 look like real renames of the same issuer (ATI, CCE, CLF, CNX,
DD, FOX, FOXA, OI, PCG) and were dropped anyway, because a rename and a
hidden reuse cannot be told apart from names and prices alone. Repairing
rather than dropping them needs a security-identity source (FIGI or CRSP
PERMNO). The full list with removed and current names is in
sprints/E2/PROBES.md and the decision is in the Hygiene Ledger.
