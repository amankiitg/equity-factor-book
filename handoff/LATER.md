# LATER

Out of scope while the goal is the cron running on Render in dry run and emailing
the owner every evening. One line each, and nothing here is raised until that run
works.

- The Cloudflare page and the dashboard: needs `EFB_SNAPSHOT=on` plus the four
  `EFB_R2_*` credentials and the `efb-snapshots` bucket, and `EFB_SNAPSHOT` cannot
  be `on` without them.
- Going live (execution hardening): `EFB_DRY_RUN=false`, the Alpaca paper keys
  `EFB_ALPACA_PAPER_API_KEY` and `EFB_ALPACA_PAPER_SECRET_KEY`, and the guard cap
  `MAX_TRADED_NOTIONAL_PER_RUN`.
- The seed's download time and peak memory on Render, to be read off the first
  real run's metrics rather than assumed.
- The `--durations=25` listing of the slowest tests, and any further slow markers
  it would earn; the 120 second timeout and the `make test` / `make test-all`
  split are in, the listing is diagnostic.
- The phase-end `make test-all` on the final tree, with its output pasted into
  `handoff/REPORT.md`.
- The momentum-window name list and the exclusion counts already reported in
  `REPORT.md`: findings, not deploy blockers.
- `REPORT.md` still describes the single-path 617.84 MB seed set; the union
  measurement's own numbers replace it once that run finishes.
- The Cloudflare Access setup in front of the page, and the read-only Supabase
  role `efb_reader`, which nothing uses while the page is out of scope.
