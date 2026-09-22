# Evidence and archive hardening: report

Task `evidence-and-archive-hardening`, base commit 3a82ccb. Three things:
protect the SPY archive, repair the evidence chain the last rebuild broke,
and close the within-year sample asymmetry in F10.3b. Every number below
is read from an artifact.

## Table 1: gates

| gate | result |
| --- | --- |
| make test | 595 passed, exit 0 |
| make lint | clean, exit 0 |
| make verify-evidence | evidence OK, exit 0 |
| walkthrough total cells | 23 |
| walkthrough code cells | 13 |
| walkthrough error outputs | 0 |
| walkthrough null execution counts | 0 |

## Table 2: the archive

| quantity | value |
| --- | --- |
| file | data/raw/spy_holdings/spy_holdings_2026-09-18.parquet |
| bytes | 34358 |
| sha256 | e8c726ef112f9aeeb3ddc5fd92167e1ed62f53d377118f3300d1659398ab5c97 |
| present in data/VERSION.json | yes |
| present in evidence/MANIFEST.json | yes |
| survives a clean checkout | yes, as evidence/data/raw/spy_holdings/spy_holdings_2026-09-18.parquet.gz (24025 bytes) |
| projected growth | 6.1 MB per year of daily files |

The archive is protected through the evidence snapshot, not by tracking
the data parquet. `git ls-files data/raw/spy_holdings/` counts 0, but the
compressed snapshot under evidence/ is tracked, and `make verify-evidence`
decompresses it and hashes it against VERSION.json. A fresh clone contains
the 18-Sep archive in compressed form.

## Table 3: F10.3b revisions

| window | old reduction | new reduction | years dropped | n_years both sides |
| --- | --- | --- | --- | --- |
| daily 21 | 0.206317 | 0.286842 | 2012 | 14 |
| daily 42 | 0.176613 | 0.195261 | 2012 | 14 |
| daily 63 | 0.106923 | 0.163429 | 2012 | 14 |
| daily 126 | 0.204057 | 0.202698 | 2012 | 14 |
| daily 252 | 0.144861 | 0.126479 | 2012, 2013 | 13 |

The old values are in the revisions block of
sprints/E10/RESULTS.json. The criterion text and the pass verdict are
unchanged, and every window stays below 40%, so F10.3's fail stands.

## Table 4: per-year observation counts

Raw observations per year are 11 in 2012, 12 in 2013 through 2025, and 7
in 2026. Targeted observations per year, per window:

| window | 2012 targeted | 2013 targeted | 2014-2025 targeted | 2026 targeted | years dropped |
| --- | --- | --- | --- | --- | --- |
| daily 21 | 9 | 12 | 12 | 7 | 2012 |
| daily 42 | 8 | 12 | 12 | 7 | 2012 |
| daily 63 | 7 | 12 | 12 | 7 | 2012 |
| daily 126 | 4 | 12 | 12 | 7 | 2012 |
| daily 252 | 0 | 10 | 12 | 7 | 2012, 2013 |

Every kept year now carries the same count on both sides; 2026 is a
partial year with 7 observations on both sides and is kept, because the
two sides agree. The within-year asymmetry is gone.

## Table 5: no-change

| sprint | criteria | verdicts changed |
| --- | --- | --- |
| E1 | 5 | 0 |
| E2 | 13 | 0 |
| E3 | 9 | 0 |
| E4 | 7 | 0 |
| E5 | 5 | 0 |
| E6 | 7 | 0 |
| E7 | 6 | 0 |
| E8 | 8 | 0 |
| E9 | 5 | 0 |
| E10 | 6 | 0 |

E10 per-criterion before and after, verdicts only: F10.1 fail to fail,
F10.1b pass to pass, F10.2 pass to pass, F10.2b pass to pass, F10.3 fail
to fail, F10.3b pass to pass. F10.3b's five stored reductions moved, but
the verdict did not. F10.1b is byte-identical to 3a82ccb in criterion,
threshold, verdict and stored_numbers.

## Table 6: membership unchanged

Proven by data/VERSION.json sha256, not by git status, because
data/**/*.parquet is gitignored and git status proves nothing there.

| artifact | sha256 at 3a82ccb | sha256 at HEAD |
| --- | --- | --- |
| universe_membership.parquet | 532623d541928c67dd165b8a6e49c1e890ba7a57a5c732c6b2b688c819944615 | 532623d541928c67dd165b8a6e49c1e890ba7a57a5c732c6b2b688c819944615 |
| universe_constituents.parquet | d14736b7dfe56f4646a8ac5cfe4ac3b9a87dae99f9674959260e3f780d1de2d0 | d14736b7dfe56f4646a8ac5cfe4ac3b9a87dae99f9674959260e3f780d1de2d0 |
| universe_changes.parquet | 8641143074228883c2a20278e0f67e05423601be333128328f3fc116ad4c1102 | 8641143074228883c2a20278e0f67e05423601be333128328f3fc116ad4c1102 |
| sectors.parquet | 66d1b7fad9e5829e103accfc15befa2c2770e70478c6123c6635468655d31c6c | 66d1b7fad9e5829e103accfc15befa2c2770e70478c6123c6635468655d31c6c |

## Decisions

Where the task left the choice to me: the archive is tracked through the
evidence snapshot, not through a .gitignore negation for the data
directory, because the project's evidence policy already names that as the
mechanism for non-regenerable fetched inputs. The verify-evidence gate
went into the test suite as an integration test, so a rebuild that forgets
make evidence fails make test, not only a make target. The within-year fix
drops a year whenever the two sides disagree in count, with no separate
minimum count, because the requirement is equality of the two sides and a
partial year with equal counts (2026, seven observations) is the same
statistic on both sides. The size line was checked: the snapshot is 109.57
MB, already committed through Git LFS by the E8 Task 0d open item, and the
archive adds 24 KB a day, about 6.1 MB a year.

## Findings

E10-F24: the retroactive-membership defect counts carried in the previous
report's Table 7 were measured on a fresh build_membership over a
business-day range ending 2026-09-21, not on the stored membership
artifact. BE and P are not columns in data/processed/universe_membership.parquet
at all, and only RDDT's error (4355 of 4355 dates) is present in it today.
The stored artifact is unchanged and the reconstruction that would fix it
remains reserved.

