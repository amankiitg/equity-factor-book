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

## 2026-09-17: the XS-v1 cross-section is survivors only, 41.9% of the 2010 index by name

Owner: E4. The sector dummies restrict the cross-sectional model to the 502
names the sector file holds, and that file is a current-member snapshot, so
the historical cross-section is entirely survivors. Measured in the E3 Task 0
probes (sprints/E3/PROBES.md): in 2010 an average of 503.9 point-in-time
members per day, of which 292.6 are in the sector file and 211.3 are not,
which is 41.9% of the index by name and 8.85% by market capitalisation. The
name share decays as the missing names leave (33.8% in 2015, 18.9% in 2020,
4.8% in 2025) and the cap share decays faster (5.5% in 2015, 2.0% in 2020,
0.24% in 2025), so the bias is mostly a breadth problem and a smaller weight
problem.

This is a stronger restriction than the F1.5 survivorship measurement of
365.1 bp per year on the full panel, because F1.5 is estimated from the
members the panel does hold while the sector dummies remove the members it
does not. Two consequences are recorded rather than fixed: the historical
cross-section has no non-survivors in it at all, and the sector exposures
themselves are assigned from a snapshot, so a name's 2010 sector is its
2026 sector.

E3 states both numbers in the research note as a limitation and does not
attempt a repair. A repair needs a point-in-time sector and constituent
source, which is the same dependency as the E11 ongoing constituent item
above, and it should be priced in E4's evaluation of the model rather than
patched inside the risk model.
