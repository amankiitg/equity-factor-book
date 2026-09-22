# E10 correction probes

Reproductions of the nine defects from the 2026-09-21 review, printed
before any code changed. Every number below was produced by running the
stored code at HEAD 5b77d6f against the stored artifacts.

## Design book

rho 0.02, phi 0.95, seed 1. Net annualized moments: mean 0.097811, vol
0.100000, Sharpe 0.978110, n 174.

## 1. F10.1 mixes signs

`drawdown_analysis` computes `abs(simulated - analytical) / abs(analytical)`
where `simulated` is a signed drawdown (-0.140308) and `analytical` is a
magnitude (+0.035433). That yields (0.140308 + 0.035433) / 0.035433 =
4.959825, which is what `RESULTS.json` stores. With consistent signs the
gap is (0.140308 - 0.035433) / 0.035433 = 2.959825.

## 2. The bootstrap is i.i.d., not block

`drawdown_analysis` draws paths with `rng.choice(x, size=n, replace=True)`,
an i.i.d. resample with replacement. There are no blocks, so the F10.1 note
that says "block-bootstrapped paths" is wrong, and an i.i.d. bootstrap
destroys volatility clustering by construction.

## 3. The Gaussian control draws down deeper than the book

2000 i.i.d. Gaussian paths at the book's own mu and sigma and the same
n = 174, median maximum drawdown -0.153969, against the bootstrap's
-0.140308. There is no fat-tail excess to explain; the Gaussian null is
deeper than the book.

## 4. The stop-loss never re-enters

`_apply_stop_loss` on `[-0.2, 0.5, 0.5, 0.5, 0.5, 0.5]` with threshold
-0.10 and re-entry -0.05 returns `[-0.2, 0.0, 0.0, 0.0, 0.0, 0.0]`. While
flat the function updates neither wealth nor peak, so the frozen drawdown
stays below -0.10 and the -0.05 re-entry test is unreachable.

## 5. The seed_ew row rests on 207 of 4193 days

Under the E5 missing-data semantics:

| book | dates available | non-missing days | window |
| --- | --- | --- | --- |
| seed_ew | 4193 | 207 | 2025-10-28 to 2026-08-27 |
| seed_mom_ls | 4092 | 4091 | 2010-05-28 to 2026-09-03 |

## 6. F10.3 compares 15 raw years against 14 targeted years

The targeted series starts in 2013 (rolling 12 then shift 1), so its year
set is 2013 to 2026 while the raw series is 2012 to 2026.

| basis | raw CV | targeted CV | reduction |
| --- | --- | --- | --- |
| as stored, 15 raw years vs 14 targeted | 0.2663 | 0.2338 | 0.122049 |
| aligned, 14 years both sides | 0.2754 | 0.2338 | 0.150769 |

## 7. F10.3's estimator is not the cause

A daily-return volatility estimate reaches a higher reduction than the
monthly 12-window estimate. The sweep is in the F10.3b step; the conclusion
is that the year-to-year dispersion is not forecastable at this horizon,
not that the estimator is too noisy.

## 8. The memo paraphrases two criteria

`write_memo.py` interpolates verdicts but types criterion text by hand.
F10.1's memo text appends "or the gap is the fat-tail and clustering the
Brownian benchmark does not have", and F10.3's replaces "more than 40%"
with the measured 0.1220.

## 9. The memo traceability test cannot catch a sign error

`test_e10_memo.py` matches with `abs(abs(v) - value)`, so a memo that
printed +0.1403 for a stored -0.1403 would pass.

## Part B1: the frozen-universe defect, reproduced

`build_membership` seeds every date with today's live members and walks the
pinned changes table backward, so a live name added after the pin has no
event row and is marked a member back to 2010. Measured against the live
Wikipedia table (503 rows, fetched 2026-09-22, the same table the reviewer
read on 2026-09-21):

| symbol | security | date_added | event row in changes | dates marked member | wrongly marked before add |
| --- | --- | --- | --- | --- | --- |
| BE | Bloom Energy | 2026-09-21 | no | 4361 | 4360 |
| P | Everpure | 2026-09-21 | no | 4361 | 4360 |
| RDDT | Reddit | 2026-08-18 | no | 4361 | 4336 |
| ILMN | Illumina | 2026-09-21 | yes (2015 add, 2024 remove) | 2828 | 585 gap |

The first three have no event row, so every business day from 2010-01-04 is
marked member. ILMN is the one the changes table covers: its 2015 add and
2024-06-24 removal are pinned, but its 2026-09-21 re-add is not, so it is
wrongly marked member for the 585 business days of the 2024-06-24 to
2026-09-18 gap when it was out of the index.

The symmetric case, names removed after the pin: BLDR, TAP and TTD are not in
the live list and have no removal event row, so a rebuild drops them from the
membership matrix entirely. Their stored history is lost: BLDR 715 dates from
2023-12-18, TAP 4355 dates from 2010-01-04, TTD 301 dates from 2025-07-18.

P is a reused symbol: it was Pandora Media's ticker before Sirius XM acquired
it, and today it is Everpure. That lands on the reused-symbol finding in
docs/open_items.md.
