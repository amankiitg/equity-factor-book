# The universe the loop reads, and the constituent source it does not (P1d)

Read-only diff, 2026-10-31. Both sources were fetched live; nothing was written.

## What the loop reads

`live/evening_job.py` takes the universe from the newest
`raw/spy_holdings/spy_holdings_<yyyy-mm-dd>.parquet`, which `efb.spy.fetch_spy_holdings`
downloads nightly from the sponsor's own daily holdings file. It is the vehicle's own
list, so it is authoritative for what SPY holds, including the lines a third-party
constituent table does not carry.

Today's fetch: **as of 29-Oct-2026, 504 equity rows**, with one row dropped as
non-equity. Names arrive with a CUSIP, a SEDOL and a weight, and the two share classes
are spelled `BRK.B` and `BF.B`.

The archive in the tree runs 2026-09-18 to 2026-10-26 (24 files).

## What is built and not applied

`efb.universe.fetch_constituents` reads the Wikipedia constituents table and
`efb.universe.archive_constituents` writes it to `raw/wikipedia_constituents/`. That
archive holds one file, `wikipedia_constituents_2026-09-22.parquet`, and no live path
reads it: it feeds the GICS table and the page's sector map, not the universe.

Today's fetch: **503 rows**, with `symbol`, `security`, `gics_sector`,
`gics_sub_industry`, `headquarters`, `date_added`, `cik` and `founded`.

## The diff

| | count |
| --- | --- |
| sponsor equity rows (2026-10-29) | 504 |
| Wikipedia constituent rows (2026-10-31) | 503 |
| in both | 503 |
| sponsor only | 1 |
| Wikipedia only | 0 |

The one difference:

| name | ticker | identifier | weight |
| --- | --- | --- | --- |
| CONTRA HOLOGIC INCORPO | 2602335D | 436CVR021 | 0.000003 |

That is a CVR/contra line from the Hologic deal, not common stock: it is 3 parts per
million of the fund and cannot be bought or shorted as a share. Every other name
matches one for one, including the two dotted share classes and the six recent
additions (BE, ILMN, P, SKYD, TWLO, VYLR).

**Every difference is explained.** The condition the brief puts on applying the built
source is met, and applying it would still change nothing the loop computes: the CVR
line is already excluded from the book ("no GICS row"), and the universe the book is
built on is the sponsor's 504 rows either way. So the source stays unapplied, for a
reason that is not caution: swapping a sponsor feed for a third-party list loses the
CUSIP, the SEDOL and the weight, and buys no name the model can size.

The vintage problem this source was built to fix is the **sector table**, not the
universe: `processed/sectors.parquet` predates six index additions. That repair is
`scripts/refresh_sectors.py`, and it is parked with its own evidence in
`docs/research/excluded_names.md` - it changes the book, so it needs an identity proof
it does not yet have.

## The warrant line that broke 2026-10-14

No archived sponsor file from 2026-09-18 to 2026-10-26, and not today's, carries a
ticker with a slash. `SKYD/WS` was a one-off line in the 2026-10-14 holdings file, which
is why the run's ticker was a warrant and why the vendor 404'd on it; the price loader
now returns a shaped empty frame for such a request instead of raising, so a repeat
fails at the guard rather than at `wide_to_long`.
