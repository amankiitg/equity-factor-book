# Sprint E3: Probes (Task 0)

Rules. A descriptor is not available until its probe has printed rows. The
tables below were run on 2026-09-13 against the artifacts at data_hash
51f0faa935cb57e8e9f11bf620e5f551f69ca50b415f12112f880f32b3393692, before the
sprint started, so that every design decision in PRD.md is made on a printed
number rather than on an assumption. Task 0 regenerates every table from the
shipped sources (the beta and residual volatility columns below use the E2
sources, not the XS-v1 sources) and appends the regenerated tables to this
file rather than replacing them, so the design record stays intact. Where a
probe found something that contradicts a stored E1 statement, the E1 text is
never edited: the Hygiene Ledger gains a dated correction entry.

## Probe (a): descriptor coverage by year end

Computed on the post-exclusion panel (data/processed/returns.parquet, 4193
dates from 2010-01-04 to 2026-09-03, 825 names). Each column counts the names
in the panel that carry that descriptor at the year end date, with the windows
of PRD.md (momentum 252d at least 231 observations, reversal 21d at least 20,
residual vol 63d of 63, liquidity 63d at least 42, beta 252d at least 126).
`sector` counts the names with a GICS mapping, which is the same 502 names
every year because sectors are known only for current members. `full` is the
count with every one of the six dated descriptors and a sector, which is the
count the cross-section actually uses. `full no sector` drops the sector
requirement and is shown to separate the two binding constraints.

| Year | Date | Return | Size | Beta | Mom | Rev | Resid vol | Liquidity | Sector | Full | Full no sector |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2010 | 2010-12-31 | 518 | 518 | 513 | 508 | 515 | 510 | 525 | 502 | 417 | 504 |
| 2011 | 2011-12-30 | 527 | 527 | 523 | 518 | 524 | 519 | 533 | 502 | 426 | 514 |
| 2012 | 2012-12-31 | 538 | 538 | 532 | 527 | 536 | 530 | 546 | 502 | 433 | 523 |
| 2013 | 2013-12-31 | 550 | 550 | 546 | 540 | 547 | 543 | 557 | 502 | 442 | 536 |
| 2014 | 2014-12-31 | 559 | 559 | 555 | 550 | 557 | 553 | 569 | 502 | 449 | 545 |
| 2015 | 2015-12-31 | 570 | 570 | 564 | 560 | 567 | 562 | 578 | 502 | 454 | 555 |
| 2016 | 2016-12-30 | 577 | 577 | 571 | 570 | 575 | 568 | 586 | 502 | 460 | 564 |
| 2017 | 2017-12-29 | 582 | 582 | 580 | 576 | 580 | 576 | 593 | 502 | 465 | 571 |
| 2018 | 2018-12-31 | 580 | 580 | 583 | 580 | 577 | 574 | 590 | 502 | 469 | 573 |
| 2019 | 2019-12-31 | 586 | 586 | 585 | 578 | 584 | 582 | 598 | 502 | 472 | 574 |
| 2020 | 2020-12-31 | 592 | 592 | 589 | 586 | 589 | 587 | 606 | 502 | 479 | 583 |
| 2021 | 2021-12-31 | 600 | 600 | 598 | 592 | 599 | 598 | 617 | 502 | 485 | 590 |
| 2022 | 2022-12-30 | 605 | 605 | 602 | 601 | 602 | 600 | 619 | 502 | 491 | 600 |
| 2023 | 2023-12-29 | 608 | 608 | 606 | 605 | 607 | 603 | 624 | 502 | 492 | 601 |
| 2024 | 2024-12-31 | 613 | 613 | 611 | 608 | 612 | 609 | 630 | 502 | 495 | 604 |
| 2025 | 2025-12-31 | 616 | 616 | 614 | 613 | 615 | 610 | 633 | 502 | 497 | 609 |
| 2026 | 2026-09-03 | 619 | 619 | 617 | 613 | 619 | 0 | 642 | 502 | 0 | 0 |

Readings.

1. The binding constraint is the sector mapping in every year: 502 names have
   a GICS sector and no more will ever appear, because sectors are known only
   for current members. The XS-v1 universe is therefore at most 502 names and
   428 to 501 of them carry a return on a given day.
2. The second constraint is not binding: full rows run from 417 to 497 with
   the sector requirement, so the cross-section clears the 300-name floor in
   every year. MODEL_START does not move for the cross-sectional model.
3. The Size column in this table counts names with a return, not names with a
   share count, because the share count is the subject of probe (b). The real
   Size coverage is the share count ramp in probe (b), and the look-ahead rule
   in PRD.md constraint 5 follows from it.
4. The residual vol column is zero in 2026 because this pre-probe read the
   TS-v1 residual panel, which ends 2026-07-31 (see "Constraints discovered
   while probing"). The shipped descriptor is computed from the one-factor
   market model on EFB's own market proxy and runs to 2026-09-03, so Task 0's
   regenerated table is expected to show a nonzero residual vol count in 2026.
5. 2010-01-04 carries no returns at all (the warm-up boundary date is in the
   panel index with every name null). Every sector has zero members that day.
   The first estimated cross-section is therefore 2010-01-05.

## Probe (b): the shares history, and whether it is point-in-time

Five names sampled, same method the ledger's E1 note used. The decisive test is
whether the series is as filed or retroactively split adjusted: AAPL's 4-for-1
split took effect on 2020-08-28.

| Ticker | Rows | First date | Last date | Distinct values | First value | Last value |
| --- | --- | --- | --- | --- | --- | --- |
| AAPL | 420 | 2015-10-28 | 2026-08-05 | 183 | 5,575,330,000 | 14,594,180,000 |
| JPM | 664 | 2015-11-02 | 2026-08-08 | 241 | 3,680,660,000 | 2,658,186,195 |
| XOM | 662 | 2015-11-04 | 2026-08-11 | 226 | 4,162,940,000 | 4,111,911,960 |
| PG | 604 | 2015-10-23 | 2026-09-01 | 176 | 2,720,570,000 | 2,322,672,312 |
| KR | 454 | 2015-12-04 | 2026-08-28 | 227 | 966,000,000 | 612,647,282 |

The split test on AAPL:

```
2020-08-03     4,283,940,096
2020-08-04     4,383,370,240
2020-08-04     4,275,630,080
2020-08-28     4,275,630,080
2020-08-31    17,102,499,840
2020-08-31     4,275,630,080
2020-10-22    17,102,499,840
```

17,102,499,840 / 4,275,630,080 = 4.000000. The series therefore carries the
as-filed count before the split and the post-split count after it: it is not
retroactively split adjusted. The annual medians confirm it, 5.575 billion in
2015 falling to 4.379 billion in 2020, then 16.535 billion in 2021 falling to
14.681 billion in 2026.

Other findings.

1. `Ticker.shares` raises YFNotImplementedError in yfinance 1.7.0 on Python
   3.14 for all five names. `Ticker.info['sharesOutstanding']` works
   (14,594,180,000 for AAPL) and matches the last row of the series, and
   `Ticker.get_shares_full(start=..., end=...)` works.
2. `get_shares_full()` with no arguments returns a 65-row window from
   2025-03-27 for AAPL. An explicit start date is required to get the history.
3. The series start is a source artefact, not a company fact: five unrelated
   names all start between 2015-10-23 and 2015-12-04. Nothing before
   2015-10-23 is reachable from this source.
4. Duplicate dates with conflicting values exist. AAPL has 2020-08-04 twice
   and 2020-08-31 twice, the split date carrying both 4,275,630,080 and
   17,102,499,840. The de-duplication rule is in Task 0 (keep the largest
   value on a date, count the duplicate rows and the split-sized steps, and
   print both counts).
5. Consequently the E1 ledger statement that the history is "current-vintage
   data, not the value known at each date" is contradicted for 2015-10-23
   onward, and the statement that the history is unavailable is confirmed
   before that date. Both halves are recorded as a dated correction entry,
   with this evidence, and E1 is not reopened. Residual restatement risk (a
   later filing restating an earlier count) cannot be measured by this probe
   and is recorded as unquantified rather than assumed away.

## Probe (c): sector coverage and small sectors

502 of the 825 panel names carry a GICS sector. Members per sector across the
4193 dates:

| Sector | Minimum | Median | Maximum |
| --- | --- | --- | --- |
| Communication Services | 0 | 20 | 24 |
| Consumer Discretionary | 0 | 45 | 47 |
| Consumer Staples | 0 | 33 | 34 |
| Energy | 0 | 20 | 21 |
| Financials | 0 | 74 | 76 |
| Health Care | 0 | 56 | 59 |
| Industrials | 0 | 74 | 82 |
| Information Technology | 0 | 68 | 73 |
| Materials | 0 | 23 | 25 |
| Real Estate | 0 | 30 | 30 |
| Utilities | 0 | 29 | 31 |

1. Days on which at least one sector has fewer than 5 members: 1 of 4193,
   and that day is 2010-01-04, the empty warm-up row where every sector has
   zero members. Every other day has at least 5 members in every sector, so no
   sector dummy is ever estimated from a handful of names.
2. Sector-mapped names with a return, at each year end: 428, 435, 442, 452,
   457, 463, 468, 471, 474, 481, 486, 490, 493, 495, 498, 500, 501. The growth
   from 428 to 501 is the survivorship path of the current-member snapshot,
   which is why the sector dummies and the survivorship caveat are the same
   finding seen from two sides.
3. The sector dummies are therefore estimable on every day of the sample, and
   the identification constraint (cap-weighted sector returns sum to zero) has
   11 live sectors to constrain.

## Probe (d): value, and the EXPERIMENTAL variant

| Ticker | Quarterly balance sheet | Non-null Stockholders Equity | Column dates | info bookValue |
| --- | --- | --- | --- | --- |
| AAPL | 65 rows x 7 columns | 5 | 2024-12-31 to 2026-06-30 | 7.36 |
| JPM | 50 rows x 7 columns | 5 | 2024-12-31 to 2026-06-30 | 133.007 |
| KR | 68 rows x 6 columns | 5 | 2025-01-31 to 2026-04-30 | 9.252 |

1. Five quarters is the whole reachable history, and the columns are period
   ends with no filing date, so using a value at its period end would be
   look-ahead of one to three months and using it at the filing date requires
   a filing date the source does not return.
2. `info['bookValue']` is a current value only, and priceToBook is derived from
   it, so neither can be turned into a history.
3. Verdict: book to price has no point-in-time panel. The value variant is
   deferred to the optional backlog and written into the research note as
   pending with this reason, per the sprint rule that a deferred item is
   recorded, not dropped silently.

## Constraints discovered while probing

These were found while running the probes above and they changed design
decisions in PRD.md. Each is a stored fact about the current artifacts.

1. factors_ff.parquet runs 2010-01-04 to 2026-07-31 (4169 rows, rhythm
   202607). returns.parquet excess is all NaN after 2026-07-31 while r is
   non-null to 2026-09-03. XS-v1 regresses r, not excess, and the Market
   factor is a total-return factor.
2. data/models/TS-v1/residuals.parquet runs 2010-01-05 to 2026-07-31 over 628
   names (2,617,504 rows). 197 of the 825 panel names never get a TS-v1
   residual because they have fewer than 60 usable observations. A residual
   volatility descriptor read from this panel would both stop a month early
   and cover 197 fewer names, which is why the descriptor is computed from the
   one-factor market model on EFB's own market proxy.
3. data/models/TS-v1/beta_history.parquet holds 201 month-end rows for the raw
   method, not a daily panel, and data/models/TS-v1/loadings.parquet is a
   single cross-section of 825 rows. There is no daily beta to read, so XS-v1
   computes its own daily shrunk beta with the TS-v1 estimator.
4. data/models/TS-v1/factor_cov.parquet is a 6 x 6 matrix over mkt_rf, smb,
   hml, rmw, cma, mom. The factor covariance artifact for XS-v1 is a separate
   18 x 18 matrix and TS-v1 is untouched.
5. The pre-registered champion_rule in data/models/registry.json already
   requires a champion to be refreshable daily from EFB's own data. Combined
   with findings 1 and 2, that rule is what forces the beta and residual
   volatility sources chosen in PRD.md. XS-v1 is registered with champion
   false and eligible_for_champion true, and the champion_rule field is not
   edited.

## Task 0 output that still has to be printed

1. The regenerated probe (a) table using the shipped beta and residual
   volatility sources, with the nonzero 2026 residual vol count.
2. Probe (b) run over the 502 sector-mapped names: the share count coverage
   ramp by month from 2015-10 to 2016-06, the first available date per name,
   the duplicate-date and split-step counts, and the first trading day on
   which 300 or more names carry a complete descriptor row including a share
   count.
3. The E1 reference values block in sprints/E1/RESULTS.json and the repointed
   assert in notebooks/E1_walkthrough.ipynb, with the recomputed values
   printed next to the block.
4. The Hygiene Ledger entries: the shares correction, the XS-v1 parameters,
   and the two design consequences (total returns as the regressand, and the
   beta and residual volatility sources).

# Task 0, run 2026-09-17

Reproduce with `python -m efb.probes --e3-shares-all` then
`python -m efb.probes --e3`. The share history is cached in
data/raw/shares_history.parquet, so the second run is offline.

Differences from the 2026-09-13 pre-probe, all of them consequences of
running the probes on the shipped sources rather than the E2 ones:

- Every descriptor count is now conditioned on the name having a return that
  day, because a descriptor is only usable where the regression has a left
  hand side. That is why the sector column reads 428 in 2010 and not 502.
- Size (log market cap) is measured from the real share history instead of
  standing in for "has a return", so the Size column equals the Return column
  wherever a share count exists at all. The look-ahead flag inside those
  counts is the subject of the shares probe below.
- Residual volatility is computed from the one-factor market model on EFB's
  own cap-weighted proxy and no longer from the E2 TS-v1 residual panel, so
  the 2026 column is populated.

## Descriptor coverage by year end (regenerated)

Each column counts the names in the post-exclusion panel that carry that
descriptor at the year end date and also have a return that day. `sector`
counts names the sector file knows, `full` is the conjunction of all eight.

| Year | Date | Return | Size | Beta | Momentum | Reversal | Resid vol | Liquidity | Sector | Full |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2010 | 2010-12-31 | 428 | 428 | 423 | 0 | 426 | 423 | 425 | 428 | 0 |
| 2011 | 2011-12-30 | 435 | 435 | 433 | 428 | 435 | 433 | 434 | 435 | 428 |
| 2012 | 2012-12-31 | 442 | 442 | 438 | 435 | 442 | 438 | 442 | 442 | 435 |
| 2013 | 2013-12-31 | 452 | 452 | 449 | 442 | 451 | 449 | 450 | 452 | 442 |
| 2014 | 2014-12-31 | 457 | 457 | 454 | 452 | 457 | 454 | 457 | 457 | 452 |
| 2015 | 2015-12-31 | 463 | 463 | 458 | 457 | 463 | 458 | 462 | 463 | 457 |
| 2016 | 2016-12-30 | 468 | 468 | 463 | 463 | 468 | 463 | 467 | 468 | 463 |
| 2017 | 2017-12-29 | 471 | 471 | 471 | 468 | 471 | 471 | 471 | 471 | 468 |
| 2018 | 2018-12-31 | 474 | 474 | 472 | 471 | 473 | 472 | 473 | 474 | 471 |
| 2019 | 2019-12-31 | 481 | 481 | 480 | 474 | 481 | 480 | 481 | 481 | 474 |
| 2020 | 2020-12-31 | 486 | 486 | 483 | 481 | 484 | 483 | 484 | 486 | 481 |
| 2021 | 2021-12-31 | 490 | 490 | 489 | 486 | 490 | 489 | 490 | 490 | 486 |
| 2022 | 2022-12-30 | 493 | 493 | 491 | 490 | 492 | 491 | 492 | 493 | 490 |
| 2023 | 2023-12-29 | 495 | 495 | 494 | 493 | 495 | 494 | 495 | 495 | 493 |
| 2024 | 2024-12-31 | 498 | 498 | 498 | 495 | 498 | 498 | 498 | 498 | 495 |
| 2025 | 2025-12-31 | 500 | 500 | 499 | 497 | 500 | 498 | 500 | 500 | 497 |
| 2026 | 2026-09-03 | 501 | 501 | 499 | 497 | 501 | 499 | 501 | 501 | 497 |

Universe per day:

```
days                             4193
mean full rows                    439.5
min full rows                       0  on 2010-01-04 (the warm-up boundary row)
days below 300 names               252
first day with >= 300 full rows   2011-01-03
```

Readings.

1. Momentum is the descriptor that sets the start. On 2010-12-31 the panel
   has 249 usable sessions, and the 12-1 window needs 231 observations ending
   at t-21, so the first complete cross-section is 2011-01-03, not
   2010-01-05. The 252 days below the 300-name floor are exactly that
   warm-up. XS-v1 therefore estimates from 2011-01-03, and the Fama-MacBeth
   subperiods are 2011-01-03 to 2015-12-31, 2016-01-01 to 2020-12-31 and
   2021-01-01 to 2026-09-03.
2. Once past the warm-up the cross-section holds 428 to 497 names, always
   above the 300 floor, and the binding constraint is the sector file, not
   the windows.
3. Liquidity is the second tightest window in most years (425 of 428 in
   2010, 499 of 501 in 2026), because 42 of the last 63 sessions must carry
   volume.
4. The 2026 row is a partial year (169 sessions ending 2026-09-03).

## Shares history: as filed, and where it starts

503 names asked (the sector file), 502 return a history; 826 names are then
asked in total (the union with the panel), 773 return one. DD has no vendor
page under that symbol. Cached in data/raw/shares_history.parquet.

```
rows fetched                      426062  (status ok 426010, empty 52)
rows after de-duplication         365008  (61002 duplicate rows dropped, 14.3%)
split-sized steps                    341  (a jump of 1.5x or more)
names with any share count           773  of 826 asked
name-days flagged look_ahead     1245448  of 3459225 (825 names x 4193 days)
```

The ramp below counts names whose count was actually filed, so it excludes
every backfilled value. It is the month by month answer to "since when is
this point-in-time".

```
month      names with a filed count
2013-04                            1
2013-05                            2
2013-12                            3
2014-06                            4
2014-08                            5
2015-04                            6
2015-06                            8
2015-08                           15
2015-09                           22
2015-10                          149
2015-11                          396
2015-12                          435
2016-04                          436
2016-12                          440
2017-02                          441
... eventually                 502
```

Readings.

1. Before 2013-04 no name has a filed count, so every historical count is a
   backfill and every Size exposure before then is a projection. From
   2015-10 the panel is mostly real (149 names), from 2015-11 it is 396 of
   502, and it reaches 502 in 2017.
2. 1,245,448 name-days carry a backfilled count. That is the scale of the
   look-ahead in Size and in the sqrt(market cap) weights, and it is why the
   PRD prices the flagged window as a sensitivity rather than assuming it
   away.
3. The split test that decides "as filed" rather than "restated" is in the
   earlier section: AAPL steps from 4,275,630,080 on 2020-08-28 to
   17,102,499,840 on 2020-08-31, exactly 4x, so the series is not
   retroactively split adjusted. 341 split-sized steps are visible across
   the panel, which is the same evidence at panel scale.
4. The de-duplication rule is to keep the largest value on a date, because a
   share count only jumps at a split and a duplicate date carries two
   vintages of one filing. 14.3% of fetched rows are duplicates, so the rule
   matters.

## The survivor-only restriction, in names and in weight

This is the number the sprint's standing instruction A asks for. The sector
dummies restrict the cross-section to the names the sector file holds, which
are current members, so the historical cross-section is entirely survivors.
`share_outside` is the share of member name-days that the sector file cannot
reach; `share_outside_mcap` is the same thing weighted by market cap, which
is the number that matters for a cap-weighted benchmark.

| Year | Members/day | Mapped/day | Outside/day | Outside distinct | share_outside | share_outside_mcap |
| --- | --- | --- | --- | --- | --- | --- |
| 2010 | 503.9 | 292.6 | 211.3 | 219 | 0.419391 | 0.088511 |
| 2011 | 502.2 | 298.1 | 204.1 | 215 | 0.406321 | 0.089034 |
| 2012 | 503.0 | 306.8 | 196.1 | 206 | 0.389935 | 0.072907 |
| 2013 | 501.8 | 316.8 | 185.1 | 196 | 0.368782 | 0.069569 |
| 2014 | 500.5 | 323.1 | 177.4 | 188 | 0.354458 | 0.075068 |
| 2015 | 502.3 | 332.7 | 169.6 | 188 | 0.337657 | 0.054653 |
| 2016 | 503.7 | 350.3 | 153.4 | 175 | 0.304556 | 0.049406 |
| 2017 | 504.0 | 367.8 | 136.2 | 155 | 0.270173 | 0.042654 |
| 2018 | 504.0 | 380.2 | 123.8 | 140 | 0.245644 | 0.042666 |
| 2019 | 505.6 | 392.6 | 113.0 | 122 | 0.223408 | 0.027416 |
| 2020 | 506.0 | 410.4 | 95.6 | 108 | 0.189000 | 0.019593 |
| 2021 | 506.0 | 420.9 | 85.1 | 100 | 0.168195 | 0.020912 |
| 2022 | 504.7 | 432.4 | 72.3 | 83 | 0.143262 | 0.016322 |
| 2023 | 504.0 | 447.8 | 56.2 | 63 | 0.111538 | 0.010937 |
| 2024 | 504.0 | 464.1 | 39.9 | 49 | 0.079181 | 0.005767 |
| 2025 | 504.0 | 479.8 | 24.2 | 32 | 0.048094 | 0.002385 |
| 2026 | 503.3 | 496.4 | 6.9 | 13 | 0.013707 | 0.000444 |

Reading. The restriction removes 41.9% of the 2010 index by name but only
8.85% by market cap, and both decay as the missing names are the ones that
left. So the survivor-only cross-section is mostly a breadth problem and a
smaller weight problem: for a cap-weighted benchmark it costs under 9
percent of the index even in the worst year, but it removes two thirds of
the names that were not survivors, and those names are disproportionately
the failures. Both numbers are stated in the research note as a limitation
and the name share is recorded as a new open item for E4, because a
cross-section of survivors cannot be repaired inside E3.

## Sector coverage (regenerated, unchanged)

502 of the panel's 825 names are in the sector file. Members per sector across
the 4193 dates: Communication Services 0 to 24 (20), Consumer Discretionary 0
to 47 (45), Consumer Staples 0 to 34 (33), Energy 0 to 21 (20), Financials 0
to 76 (74), Health Care 0 to 59 (56), Industrials 0 to 82 (74), Information
Technology 0 to 73 (68), Materials 0 to 25 (23), Real Estate 0 to 30 (30),
Utilities 0 to 31 (29), medians in brackets. Days on which any sector has
fewer than 5 members: 1 of 4193, and it is 2010-01-04, the empty warm-up row.
Every other day has at least 5 members in every sector, so no dummy is ever
estimated from a handful of names.

## Value source (regenerated, unchanged)

| Ticker | Rows | Quarters | Equity quarters | First column | Last column | Book value now |
| --- | --- | --- | --- | --- | --- | --- |
| AAPL | 65 | 7 | 5 | 2024-12-31 | 2026-06-30 | 7.360 |
| JPM | 50 | 7 | 5 | 2024-12-31 | 2026-06-30 | 133.007 |
| KR | 68 | 6 | 5 | 2025-01-31 | 2026-04-30 | 9.252 |

Five quarters, at period-end dates, with no filing date, and a current-only
book value. The value variant stays deferred with that reason recorded.

## E1 reference values (Task 0, second half)

sprints/E1/RESULTS.json gains a `reference_values` block computed by
efb.evaluate.e1_reference_values from data/raw/factors_ff.parquet column
mkt_rf. The edit is additive: the criteria, the revisions history and the
data hash are byte-identical to the file before it. The stored values are

```
n_obs                              4169   (2010-01-04 to 2026-07-31)
sharpe_daily                       0.04788212403281411
sharpe_annualized                  0.7601051546182517
se_iid_daily                       0.015496472017044434
se_iid_annualized                  0.24599886693582632
se_lo2002_daily                    0.014288336517787974
se_lo2002_annualized               0.2268203104492176
ratio_lo_over_iid                  0.9220380291767286
lag1_autocorrelation_ff_market    -0.10289978052657538
sum_rho_weighted_q                -0.07610911247235277
sum_phi_weighted_q                 0.9598197108458648
```

The E1 walkthrough cell that computes these now reads the block, prints it,
and asserts the recomputed values against it, so no assert depends on the
prose table in docs/research/E1_data_note.md. The data note keeps its table;
it is no longer an assertion target. The values reproduce the prose exactly:
0.7601, 0.2460, 0.2268, 0.9220, -0.1029.

## The Market factor, estimated both ways (standing instruction C)

Printed by `python -m efb.probes --e3-two-ways` on 2026-09-17. The design is
built once and every one of the 3941 days is fitted twice, once on the total
return r and once on r minus rf, so the two series differ only through the
regressand. The style and sector factors are compared between the two fits
rather than assumed to be equal.

```
n_days_total                     3941
n_days_overlap                   3917   (2011-01-03 to 2026-07-31)
market_total_mean                0.000578022897
market_total_std                 0.01099506696
market_excess_mean               0.0005126478159
market_excess_std                0.01101293198
mean_rf_on_overlap               6.137350013e-05
correlation_total_vs_excess      0.9999726435
correlation_ff_market_total      0.9889255745   (Mkt-RF plus RF)
correlation_ff_market_excess     0.9889259495   (Mkt-RF)
max_abs_other_factors_gap        1.765948499e-15
max_abs_market_gap_minus_rf      6.481767163e-16
```

Readings.

1. The answer to the instruction's question is 0.9999726435. The Market factor
   estimated on total returns and the Market factor estimated on excess returns
   are the same series to four decimal places, and the only thing that moves is
   the mean: 0.000578022897 against 0.0005126478159, a difference of 6.5 basis
   points a day over the overlap, which is the risk-free rate itself.
2. That is exact and not approximate, and the reason is the design's shape. The
   market column is the constant column, so the market factor is the intercept
   of the fit, and a constant subtracted from every name's return on a day
   moves the intercept and nothing else. The probe measures that rather than
   asserting it: the largest absolute difference between the two fits on the
   other 17 factors is 1.765948499e-15, and the largest absolute deviation of
   (market gap minus rf) is 6.481767163e-16, which is floating point noise on
   both counts.
3. So the regressand choice costs a level shift and no shape. Correlating
   either series with the FF market return gives the same number to five
   decimals: 0.9889255745 against Mkt-RF plus RF for the total-return factor,
   which is the figure F3.4 stores as 0.9889255744977894, and 0.9889259495
   against Mkt-RF for the excess-return factor.
4. The practical consequence for E4 and E5 is that a model comparison against an
   excess-return benchmark needs only the risk-free series for the overlapping
   window, because every style and sector factor return is already the same
   number in both parameterizations. XS-v1 would not gain a different factor
   structure by switching regressand; it would gain five weeks of missing
   sample at the end, which is why it does not switch.
