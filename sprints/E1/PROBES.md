# Sprint E1: PROBES

Ran 2026-09-04. A source is not available until its probe has printed rows.
Output below is the verbatim printout of `python -m efb.probes` (stderr
warnings from yfinance suppressed). Task 0 acceptance: every source printed
rows or recorded a documented failure.

### wikipedia_constituents
status: ok
rows: 503 | first: 1957-03-04 | last: 2026-08-18
ticker_coverage: NA | nan_share: 0.0000
notes: live page; columns symbol, security, gics_sector, gics_sub_industry, date_added, cik, founded

### wikipedia_changes
status: ok
rows: 407 | first: 1976-07-01 | last: 2026-08-05
ticker_coverage: NA | nan_share: 0.0516
notes: pinned revision 1368675864 (2026-08-10), the last revision that still publishes the table; 388 additions with ticker, 384 removals with ticker

### yfinance_prices
status: ok
rows: 3607890 | first: 2009-12-15 | last: 2026-09-03
ticker_coverage: 0.7716 | nan_share: 0.3121
notes: requested 858 tickers, 662 returned at least one non-null adjusted close; auto_adjust=False, actions=True; cached at data/raw/yf_cache.parquet

### french_ff5
status: ok
rows: 15876 | first: 1963-07-01 | last: 2026-07-31
ticker_coverage: NA | nan_share: 0.0000
notes: columns: ['mkt_rf', 'smb', 'hml', 'rmw', 'cma', 'rf']

### french_mom
status: ok
rows: 26195 | first: 1926-11-03 | last: 2026-07-31
ticker_coverage: NA | nan_share: 0.0000
notes: columns: ['mom']

### french_strev
status: ok
rows: 26425 | first: 1926-01-26 | last: 2026-07-31
ticker_coverage: NA | nan_share: 0.0000
notes: columns: ['st_rev']

### french_ind12
status: ok
rows: 26296 | first: 1926-07-01 | last: 2026-07-31
ticker_coverage: NA | nan_share: 0.0000
notes: columns: ['ind1', 'ind2', 'ind3', 'ind4', 'ind5', 'ind6', 'ind7', 'ind8', 'ind9', 'ind10', 'ind11', 'ind12']

### gics_sectors
status: ok
rows: 503 | first: None | last: None
ticker_coverage: 1.0000 | nan_share: 0.0000
notes: sector read from the Wikipedia constituents table; current members only, not point-in-time (ledger entry)

### shares_outstanding
status: ok
rows: 12 | first: None | last: None
ticker_coverage: 0.8333 | nan_share: 0.0000
notes: sample of 12 tickers: 10 return a history from get_shares_full, the rest return only the current value; NOT point-in-time from free sources (ledger entry)

### ff_risk_free
status: ok
rows: 15876 | first: 1963-07-01 | last: 2026-07-31
ticker_coverage: NA | nan_share: 0.0000
notes: FF daily RF column; annualized mean 4.33%

### fred_dtb3
status: failed
rows: 0 | first: None | last: None
ticker_coverage: NA | nan_share: NA
notes: unreachable from the build host (ReadTimeout); recorded as null, FF RF is the authoritative risk-free rate for E1 (ledger entry)

## Probe findings that shape the design

1. The Wikipedia changes table was removed from the live page on
   2026-08-11. E1 pins revision 1368675864 (2026-08-10), the last revision
   that still publishes it. The table covers 1976-07-01 to 2026-08-05,
   which is enough for the 2010-to-today universe.
2. yfinance returned no price data for 196 of 858 requested tickers, all
   of them deleted names (current-member coverage is 503 of 503 after
   mapping BF.B and BRK.B to the yfinance BF-B and BRK-B convention).
3. FRED is unreachable from the build host. The FF RF column is the
   authoritative risk-free rate; the DTB3 cross-check is recorded as null.
4. The Kenneth French daily files are the 202607 vintage and end on
   2026-07-31, so excess returns end there while prices run to 2026-09-03.
5. Shares outstanding via yfinance returns a history for 10 of 12 sampled
   names; the field is not point-in-time from free sources and no artifact
   is built this sprint.
