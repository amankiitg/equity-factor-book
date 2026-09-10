# Sprint E2: PROBES

## Task 0: point-in-time member coverage by calendar year

Ran 2026-09-10. A point-in-time member counts as covered in a year when
at least half of the business days on which it was a member have a
non-null adjusted close. The denominator is the ticker's own membership
window.

| year | n_members | n_covered | coverage |
| --- | --- | --- | --- |
| 2010 | 514 | 354 | 0.6887 |
| 2011 | 519 | 363 | 0.6994 |
| 2012 | 520 | 375 | 0.7212 |
| 2013 | 519 | 387 | 0.7457 |
| 2014 | 515 | 393 | 0.7631 |
| 2015 | 528 | 409 | 0.7746 |
| 2016 | 533 | 431 | 0.8086 |
| 2017 | 533 | 446 | 0.8368 |
| 2018 | 527 | 453 | 0.8596 |
| 2019 | 528 | 464 | 0.8788 |
| 2020 | 523 | 469 | 0.8968 |
| 2021 | 525 | 478 | 0.9105 |
| 2022 | 524 | 486 | 0.9275 |
| 2023 | 520 | 496 | 0.9538 |
| 2024 | 522 | 505 | 0.9674 |
| 2025 | 523 | 512 | 0.9790 |
| 2026 | 515 | 511 | 0.9922 |

MODEL_START = 2010. The first year with at least 300 covered
point-in-time members is 2010 (354 covered), so every E2 regression
starts at 2010-01-04 and the full E1 window is usable.

Notes.

1. Coverage improves monotonically from 68.9% in 2010 to 99.2% in 2026.
   The gradient is the survivorship effect: names deleted before 2010 or
   in the early years often have no recoverable history, while recent
   members are almost fully covered.
2. The gap is one-sided. Missing deletions are disproportionately
   failures, so the lower tail of residual returns is thin and specific
   risk on the loser side is biased downward. That is context for E3 and
   E5, not something E2 fixes.
3. F2.0a stores this table and MODEL_START rather than a single coverage
   threshold, following the E1 finding that F1.1 failed on calibration,
   not on data quality.
