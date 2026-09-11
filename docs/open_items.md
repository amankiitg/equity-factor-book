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

## 2026-09-10: the risk model needs conditional exposures first, a residual covariance second

Owner: E3. Found by close-out task C4, reordered by close-out task C8. The
portfolio risk decomposition uses sigma_p^2 = w' B F B' w + w' D w with D
diagonal, and B taken from one full-sample fit. For the equal-weight seed
book that is harmless, because the factor share is 99.2 percent either way
and its bias statistic is 1.0225.

For the sector-neutral momentum long/short seed book the root cause is the
static exposure, not the diagonal: static full-sample betas cannot measure
a dynamically sorted portfolio's exposure, so conditional exposures
(rolling betas now, descriptor exposures in E3) are the primary fix, and
residual co-movement is the secondary one. C8 shows both halves. Measured
against the weights actually held and 252-day name-level betas dated at
each rebalance, the book's MOM exposure averages +0.0698 over 195
rebalances and ranges from -0.3322 to +0.3905, while the static full-sample
aggregate with the last month's weights reports -0.0162, essentially no
exposure at all, on a book whose own return series loads +0.2885 on MOM
with a t statistic of 29.10. The same construction puts the factor share at
0.7390 on average, against 0.0968 for the static decomposition with
last-month weights, and the diagonal model's bias statistic for the book is
1.8544 by year (21-day forward window), between 1.1063 and 2.9259, while
the equal-weight book is at 1.0225.

E3 should price the book from descriptor exposures recomputed at each
rebalance, so the book's factor position is measured when it is held, and
then replace the diagonal D with w' Sigma_resid w from a cross-sectional
residual covariance. Until both are in place, no EFB result may quote a
single idio share for a long/short book without the measurement method
attached, and no long/short risk number may be published from the static
decomposition.

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
