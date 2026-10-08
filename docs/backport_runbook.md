# Backport runbook, branch `backport`

Research-only branch. It changes the research panel, the criteria and the tests;
it changes one thing on the live path (`efb/race.py`) and must not merge until
**2026-11-11**, when it lands together with a regenerated live seed. Until then
`make test` is the gate, and the two merge-time checks below are the ones no
default run can perform.

## 1. What this branch changes that the live cron executes

`scripts/run_cron.py` routes to `scripts/reconcile_fills.py` (`:113`, `:122`) and
`scripts.run_live_daily` (`:124`). Everything the live chain reaches from there,
that this branch touches:

| file | what changed | reached from | effect on a live run |
|---|---|---|---|
| `efb/race.py::next_descriptor_design` | builds the next-session design on `panel["returns_clean"]` instead of `panel["returns"]` (`efb/race.py:279`) | `efb/eval_risk.py:411` ← `live/evening_job.py:1205` | **the only real live behavioural change.** On a live tree the two frames are equal, so it is inert until the seed is regenerated; on the regenerated seed it changes the cross-section the hedge is solved against |
| `efb/hygiene.py::clean_returns` | `corrected` exception: a cell the corporate-action rule repaired is no longer masked by its own flag | `efb/eval_risk.py:156` (`load_clean_wide`) ← `live/evening_job.py:1191`; also `efb/race.py:60,338`, `efb/models/statistical.py:106` | inert while the live frame has no `corrected` column, which it does not until the seed is regenerated |
| `efb/probes.py::load_panel` | returns a new key, `returns_clean` | `live/extend.py:378` (still reads `inputs["returns"]`; see §3) | additive; no reader changes until the merge commit |
| `efb/build.py::build_e3_artifacts` | builds E3 from `inputs["returns_clean"]`, applies the recorded spin-offs | not on the cron path | changes the **seed**, i.e. the 2026-11-11 regeneration |
| `efb/evaluate.py`, `efb/models/fundamental.py` | criteria, docstring | not imported by `live/` | none |
| `efb/corporate_actions.py`, `scripts/collect_corporate_actions.py` | new | not imported by `live/` | none |

The XS-v1 fit itself (`efb/models/statistical.py`, `efb/cov.py`) is unchanged:
the fit consumes whatever panel it is handed, so the panel its caller passes is
the whole of the question.

## 2. Tests that need more than the repository tree

Both are **deselected, never skipped**: a default run reports them as
`N deselected`, and skipping them quietly is how the September hedge-vintage
pairs stopped existing without any test noticing.

| file | marker | what it needs | default run |
|---|---|---|---|
| `tests/test_hedge_vintage.py` | `requires_live_tree` | a run root the live loop has extended one session at a time, so that a descriptor row exists for the session after a month end | deselected |
| `tests/test_live_panel_parity.py::test_the_live_fit_and_the_next_design_read_one_panel` | `merge_guard` | the merge commit, not a tree (§3) | deselected |

    make test                                   # green today, 2 groups deselected
    make test-all                               # everything else, slow included
    EFB_RUN_ROOT=<run root> make test-live-tree # the vintage tests
    .venv/bin/python -m pytest tests/test_live_panel_parity.py -m merge_guard

`EFB_RUN_ROOT` is the same variable `live/runroot.py` materialises a run into
(`RUN_ROOT_ENV`, `live/runroot.py:31`). A tree rebuilt by `make rebuild-e3` is
**not** live-shaped: the build publishes descriptors at month ends plus the final
session, so it has no row for the session after a month end and cannot exercise
the vintage property at all.

## 3. Merge checklist, 2026-11-11

Ordered. Each step names the check that has to pass before the next one runs.
Steps 1 to 4 are the ones no default run performs.

| # | step | the command | the check |
|---|---|---|---|
| 1 | Read one panel | edit `live/extend.py:379`, `inputs["returns"]` to `inputs["returns_clean"]` | `make test-merge-guard` turns green (it is red before the edit) |
| 2 | Re-declare the champion if E3 was rebuilt | `python -c "from efb import eval_risk; eval_risk.apply_champion()"` | `data/models/registry.json` names XS-v1 again |
| 3 | Regenerate the live seed from this branch's artifacts | `.venv/bin/python -m scripts.push_seed --dry-run`, then the same without `--dry-run` | the manifest lists this branch's artifacts and no read is refused |
| 4 | Run the vintage tests on the regenerated seed | `EFB_RUN_ROOT=<run root> make test-live-tree` | the two the seed exists to fix pass, see §6 |
| 5 | Regenerate the web fixtures | `scripts/make_web_fixtures.py` | `make web-test` green |
| 6 | Run the full suite on the merged commit, with the seed in place | `make test-all` | green, no deselected group |
| 7 | State the end date on any further rebuild | `make rebuild END=<last session before the merge>` | `data/VERSION.json` records that session |
| 8 | Re-record the frozen block baseline if the seed moved a pre-cutoff row | `.venv/bin/python -c "from live import extend; print(extend.incremental_integrity())"` | `tests/test_e11_extend.py` green |
| 9 | Clear the known reds the refresh exists to fix (the list is `docs/known_test_failures.md`, which the full suite's 55 are measured from) | `.venv/bin/python -m pytest tests/ -q -m "not slow and not requires_live_tree and not merge_guard"` | 0 failures; anything still red is fixed or written down in that file with its reason, never skipped and never `xfail` (note 9) |
| 10 | Seventeen things the live loop reports wrongly or omits, each with the day that exposed it (note 10) | `tests/test_e11_bridge.py`, `tests/test_week1_fills_cron.py`, `tests/test_e11_fills.py`, `tests/test_week1_fills_cron.py` again for the skip, an audit query for the NaN columns, and the evening's own proposal build for the universe | the bridge has an *arrived* term and 2026-10-06 holds all six identities; the morning's cost line compares realized against the trading half; `reconciliation.filled_notional` holds what filled; a morning with no new orders skips and says so; every NOT NULL numeric column is proved unable to hold a NaN; a filled risk estimate is reported rather than discarded; a name is sized only when the risk model can measure it; a name with risk but no signal has a stated treatment; `excluded` carries a reason, an age and a way back; DD's absence from the returns panel is explained; the pricing fetch no longer spells PSKY; the floor has a measured entry/exit band rather than a single line; the risk block and the sized universe are the same set of names; the drop and the write read one source; the write refuses a zero as firmly as the drop; the dropped names are on the page; the universe is deduplicated before it is sized |

1. **Read one panel.** At merge, `live/extend.py` must read `returns_clean` as
   well, in the same commit, so the live model fit and `next_descriptor_design`
   use the same panel. The change is `live/extend.py:379`,
   `returns_frame = inputs["returns"]` to `inputs["returns_clean"]`. Run the
   guard before and after so the result is attributable to the edit:
   `.venv/bin/python -m pytest tests/test_live_panel_parity.py -m merge_guard`
2. **Re-declare the champion after any E3 rebuild.** `efb.build.rebuild_e3`
   registers XS-v1 with `champion=False`, and only the E5 step
   (`efb.eval_risk.apply_champion`, `efb/build.py:1981`) sets the flag, so
   `make rebuild-e3` on the real tree leaves the registry with no champion.
   Measured on 2026-10-03: rebuilding E3 on `data/` cleared it, three tests
   failed (`test_champion`, `test_build_e3::test_registry_entry_is_eligible_but_not_champion`,
   `test_dashboard_d3`), and
   `python -c "from efb import eval_risk; eval_risk.apply_champion()"` restored
   XS-v1 as the winner (mean |bias-1| 0.060664 against XS-v2 at 0.067194, the
   same winner as before the rebuild). Run that after the seed regeneration.
   Since the item 1 fix, a rebuild no longer also drops the `live` block, so the
   20-share floor survives an E3 rebuild; the champion flag still does not.
3. **Regenerate the live seed** from this branch's research artifacts, so the
   published descriptors and the repaired returns come from the same panel.
   `--dry-run` measures and prints without uploading, which is the rehearsal.
4. **Run the hedge-vintage tests on the regenerated seed**, materialised as a run
   root: `EFB_RUN_ROOT=<run root> make test-live-tree`, or directly
   `EFB_RUN_ROOT=<run root> python -m pytest tests/test_hedge_vintage.py`. Two of
   the eight assert that the row built at the close *is* the published row; on the
   regenerated seed they pass, and on a tree whose published rows were built from
   the raw panel they fail by construction.
5. **Regenerate the web fixtures** after the seed lands
   (`scripts/make_web_fixtures.py`) and re-run `make test-all` once, on the
   merged commit, with the seed in place.
6. **Re-score E6 with the month-end finding folded in** (item 3 of the back-port):
   see the entry in `docs/hygiene_ledger.md` dated 2026-10-03.
7. **Regenerate with the end date stated.** Every rebuild is pinned (§5). At the
   merge, state the session the seed means to reach,
   `make rebuild END=<last session before the merge>`, rather than taking the
   default, which deliberately reproduces the stored panel.
8. **Re-record the frozen-block baseline.** `tests/test_e11_extend.py` pins the
   content hash of the descriptor, factor-return and specific-return rows dated
   on or before 2026-09-03, and those recorded hashes were taken from a live
   tree. A research rebuild cannot satisfy them: the 2026-10-03 propagation pass
   measured `049fe6ea`, `a43d66ce` and `d65a67f1` where the file records
   `8f93968f`, `42a31d64` and `176dc4b3`, so the test was red on the branch
   before and after that pass. The pin belongs to the seed generation event: run
   `extend.incremental_integrity()` on the regenerated seed and copy its three
   values into `BASELINE`.
9. **Clear the known reds.** The list is `docs/known_test_failures.md` (it lands on
   `main` with the 2026-10-07 merge of `fix-evening-email-wiring`), and it is
   the only copy: the full suite on `main` at `0e69f69` reports **55** failures,
   grouped there by cause with the one line that explains each group and the step
   above that clears it. This checklist used to carry the live-page eleven as its
   own table; that list is ten of the 55 (the eleventh,
   `tests/test_e11_snapshot.py::test_the_hedge_drives_the_exposures_to_zero`, is red
   on its own and in the targeted run and green inside the full suite), and a report
   measured against either list alone could let a real failure through.

   The command is the gate's own, on the merged commit with the seed in place:

   ```
   .venv/bin/python -m pytest tests/ -q -m "not slow and not requires_live_tree and not merge_guard"
   ```

   The exit condition: **0 failures**, with anything still red either fixed or
   written down in `docs/known_test_failures.md` with its reason. None of them may
   be skipped, deselected or marked `xfail` - a red that is silenced is how the
   September hedge-vintage pairs stopped existing without anyone noticing (§2).

   Until then, every report on this work splits a full-suite run three ways:
   **known** (an id in that file), **new** (an id that is not), and **newly
   passing** (an id in that file that came back green). A new failure is
   investigated on its own and is never folded into the known list, so a real
   regression cannot hide among them; zero new is the bar for a merge.
10. **Seventeen things the live loop reports wrongly or omits.** Each was found by looking
   at a real day rather than by a failing test, and each is small enough to fix in one
   commit with a test that would have caught it. They are here rather than in
   `docs/known_test_failures.md` because none of them is red: the suite passes on the
   wrong number, or says nothing about the omission at all.

   Items 4 to 6 were queued on 2026-10-07 from the evening's failure; items 7 to 11 were
   queued the same night from the questions the failure raised about the universe; items
   12 and 13 the night after, from what the three stored manifests of 2026-10-05 to 10-07
   showed when the same questions were asked of them; items 14 to 17 from the review of
   the commit that landed the fix on 2026-10-08, which is where the asymmetry between
   the two readers and the two loose ends around them were found. Every one of them
   carries the measurements that raised it.

   1. **The bridge cannot say a name arrived.** Its sixth identity is
      `held before - exited + opened = held after + reversals + removed without an
      order`, which accounts for names leaving and has no term for a name the loop
      never held and never opened. Measured 2026-10-07 on the 2026-10-06 close: the
      account holds **SKYD** (326.072572039 shares, asset `5b47111b…`) - the PSKY
      position, returned by the broker's late processing of the rename - and neither
      the evening's read (188 names) nor the book (195) holds it, so the identity
      reads `195 vs 196` and the page goes amber on a day whose block is otherwise
      perfect (all 24 departures carry a filled close leg; 31 of the 32 arrivals are
      the book's own opened names). The fix is the mirror of the existing term: an
      `arrived_without_order` list, populated the way `removed_without_order` is -
      names in the account that the block can explain neither as held-before, nor as
      opened, nor as a reversal - added to the right-hand side of the identity and
      itemised beside the gap's other names. `tests/test_e11_bridge.py`, plus the
      2026-10-06 numbers as a case, since they are now known.
   2. **The morning's cost line compares against the wrong half.** The page's cost
      card and the evening's message both split the expected cost into the trading
      half (spread + impact + commission) and borrow, because no fill price pays a
      holding cost, and the card compares realized cost against the trading half
      only. The morning email does not: 2026-10-07 printed `Realized cost: 10.23 bps
      of NAV against 14.22 bps expected`, and 14.22 is the full figure (trading 5.89
      + borrow 8.33). Since the realized side can only ever contain trading cost, the
      comparison is wrong in the flattering direction on every borrow-heavy day. The
      fix is to compare against `expected_cost_split.trading` and to say which half
      it is, the way the card's own label does.
      `tests/test_week1_fills_cron.py::test_a_morning_with_a_miss_names_it_in_the_message`
      is the call site that composes the line.
   3. **`reconciliation.filled_notional` is stored as 0 on every row.** Measured
      2026-10-07: all seven rows from 2026-09-25 to 2026-10-06 carry `0.0`, including
      the 2026-10-05 close whose 197 of 199 legs filled, because the evening writes
      the row before its orders settle and nothing back-fills it afterwards. It is
      harmless today only because nothing reads it - the page's fills block carries
      `filled_notional` from the morning - which is exactly why it should be either
      written by the morning that knows the number or dropped, so a future reader
      cannot mistake a placeholder for a measurement. `tests/test_e11_fills.py` and
      the reconciliation writer.
   4. **The morning job reconciles the previous close a second time, and does not say
      that it is doing so.** `previous_orders` takes the latest close strictly before
      today, so an evening that sent nothing leaves the day before it as the newest
      orders in the store. Measured 2026-10-07 on an evening that crashed before
      submitting: `previous_orders("2026-10-08")` returned the **2026-10-06** close with
      its 220 rows, `already_ran("fills_reconcile", "2026-10-08")` was `False` because
      the guard is keyed by date, and the run would therefore re-reconcile 2026-10-06 -
      rewriting the same fills, sending a **second** 2026-10-06 email two days late,
      and republishing `latest.json` with a fresh `actual_holdings` block for
      `close = 2026-10-06` onto a document whose `target_close` is 2026-10-07 (the keys
      come from the document that is up). Nothing distinguishes "no orders because the
      evening died" from "nothing to trade". The fix: the morning job compares the
      close it is about to reconcile with the last close it already reconciled, and
      when there is nothing new it records the day and says so instead of repeating
      the work - `tests/test_week1_fills_cron.py`, with the 2026-10-07 state as the
      case.
   5. **The NOT NULL NaN audit.** On 2026-10-07 the evening died at
      `NotNullViolation: null value in column "idio_vol" of relation "positions"`, and
      the value it was refusing was a NaN that had been a *valid* stored value until
      that morning: `select float8 'NaN' is not null` is **true** in Postgres, so a
      `double precision NOT NULL` column accepts a NaN as data and never complains.
      There are **28** NOT NULL numeric columns in `efb` (eight on `positions` -
      `weight`, `signed_notional`, `z`, `alpha`, `rank`, `idio_vol`,
      `previous_weight`, `trade` - fourteen on `proposals`, two each on `orders`,
      `fills` and `nav`, and one each on `broker_positions` and
      `e11_corporate_actions`), and every `double precision` one of them is a place a
      computed NaN can sit as if it were a measurement. The audit: for each column,
      prove it either cannot receive a NaN (the writer guards it, or the value is an
      integer type that would raise instead) or is now refused at the store boundary -
      and record the answer for all 28 in one table, so the next NaN is a known case
      rather than a new incident. `_null_missing` already converts every NaN, NaT and
      NA to NULL before the parameters are sent, which turns a silent NaN into a loud
      refusal; this audit is what makes the loud refusal *named* at each call site.
      A query over `information_schema.columns` intersected with a scan for
      `= 'NaN'::float8` is the check, and it currently returns nothing, which is the
      point: it must stay nothing.
   6. **A filled risk estimate is never reported.** `efb/race.py::_specific_for`
      returns `(aligned, missing)` and `efb/eval_risk.py::_xs_pieces` binds it as
      `specific, _missing = ...`, then fills every NaN with
      `float(np.nanmedian(specific))` - so the count it just computed is discarded and
      nothing anywhere records that a name's risk was synthesised. Measured
      2026-10-07: the book carried **Q**, which has no specific-variance row at any
      date in `efb.e11_specific_var` or in the committed artifact, with
      `specific_variance` `0.0002948594720242484` - a value shared, to the last bit,
      with **EQT**, because the median of an odd-length array is one of its elements.
      The evening then died storing that name, because `store_proposal` reads the same
      artifact through `trade_reasons.specific_std`, which has no fallback. The
      engine's median fill stays as it is; what the audit adds is that a filled name
      is *known* - the count `_missing` is reported instead of dropped, so a reader can
      see how many names the row rests on a fill. `tests/test_e11_snapshot.py` or the
      engine's own test file.
   7. **The sizing universe is not the risk universe.** `live/evening_job.py:1195-1198`
      builds the names to size from the **SPY universe intersected with the cleaned
      price matrix** (`wide_names`, from `efb/eval_risk.py:145-164`), while the risk
      model only ever measures the names the cross-sectional fit accepts -
      `efb/models/fundamental.py:376-389`, which requires all seven style descriptors,
      a GICS sector and a finite positive market cap. Nothing reconciles the two sets,
      so a name can be sized that the model cannot measure, and 2026-10-07 is what that
      costs: **Q, FDXF and HONA** were all in the 496 sized names with no
      specific-variance row anywhere (`efb.e11_specific_var`: 0 rows for each, at every
      date), and Q was kept by the floor, given the cross-sectional median as its risk
      (`efb/eval_risk.py:412-415`, the value `0.0002948594720242484` that EQT also
      carries), and then refused by `efb.positions.idio_vol` - which is `not null` -
      after the book had been priced. The fix: **no name is sized without all seven
      descriptors and a specific variance.** Drop such names before sizing, record them
      in the manifest with their reason, and name them in the evening email. The count
      to expect on 2026-10-07 is three. `tests/test_e11_evening.py` for the manifest key
      and the message line.
   8. **A name with a risk estimate but no signal has no stated treatment.** The two
      thresholds are about a year apart, because the risk estimate needs **252 sessions
      of price** (`efb/models/fundamental.py:216-220`, `MOMENTUM_WINDOW` 231 +
      `MOMENTUM_SKIP` 21) while the signal needs **252 specific returns**
      (`efb/alpha.py:71-93`, `MOMENTUM_LOOKBACK` 252 - `MOMENTUM_SKIP` 21, shifted 21),
      and a name only starts accumulating specific returns once the fit accepts it.
      Measured: `SNDK` has a risk estimate and 159 specific returns, so no signal - and
      its 252nd specific return is still ahead; `Q` has neither, gets its own risk
      estimate on its 252nd session, **2026-11-03**, and cannot have a signal before
      **2027-11-03**. Today a missing signal is silently filled with zero
      (`live/evening_job.py:1221` `z = z.fillna(0.0)`), so such a name is held at
      `alpha = 0` and its weight comes from the hedge alone - which is what Q's row
      showed (`z = 0, alpha = 0`). That is a decision made by accident. **Decide it
      explicitly** - hold it at zero, hold it hedge-only, or exclude it - and make the
      choice visible in the manifest and the email rather than implied by a `fillna`.
   9. **`excluded` is a one-way list with no reason and no age.** It is a rule, not a
      config (`live/evening_job.py:1198`, over `efb/eval_risk.py:154-158`: a SPY name
      with no GICS row or no processed returns is not a column of `wide`, so it is not
      sized), and it has **only ever grown** across the eight stored manifests: 4
      (2026-09-25, 09-29, 09-30), 5 (+VYLR, 2026-10-01, 10-02, 10-05), 7 (+SKYD, +TWLO,
      2026-10-06, 10-07). Nothing has ever left it, because nothing in the evening
      rebuilds `processed/returns.parquet` or `sectors.parquet` - the rule re-runs every
      night against the same artifacts and returns the same answer. Three distinct
      causes are collapsed into one list: **BE, ILMN, P** (no GICS row, so not in
      `mapped`), **SKYD, TWLO, VYLR** (no GICS row and no price rows), and **DD** (GICS
      row and 4,213 clean closes present, but absent from the returns panel - item 10).
      The fix: the evening email names each excluded entry **with its reason and how
      long it has been there**, and the loop has a defined path back - a rebuild
      trigger, or a fetch that fills the gap - so a name cannot sit outside the book
      forever without anyone being told why.
   10. **Why is DD missing from `processed/returns.parquet`?** DD is in the SPY universe,
      has a GICS row (`sectors.parquet`, `as_of` 2026-10-03) and has **4,213 non-null
      closes in a panel of 4,213 sessions** - a complete price series through
      2026-10-02, with no break at 2025-11-03 when Q (Qnity Electronics) was spun off.
      Yet DD is **not among the 811 tickers of `processed/returns.parquet`**, so it has
      no column in `wide` and is excluded (item 9) - while ILMN, with the same complete
      price series, *is* in the returns panel and is excluded only for want of a GICS
      row. So the two exclusions have different causes and only one is explained. The
      question to answer: **did `hygiene.clean_returns` or the panel's build drop DD at
      the 2025-11 spin-off**, and if so on what rule? Answer it with the build's own
      record; if the cause is a hygiene rule, the rule needs to say what it did.
   11. **The pricing fetch still spells PSKY, not SKYD.** `efb.e11_prices` carries
      **PSKY** (4,213 closes) and no SKYD row at all, while the broker has traded the
      same asset - id `5b47111b-5e0d-4adc-929c-3efae02f747e`, CUSIP 69932A204 - as SKYD
      since the rename, and the SPY universe already lists SKYD. So SKYD is excluded for
      want of a price series that exists under its old name (item 9), and the loop
      cannot size or trade the position it actually holds. `PSKY now trades as SKYD` is
      also the worked example in item 1 and in Part B's symbol resolution, which is what
      makes this the same defect one layer down: the *broker* side resolves the rename
      and the *vendor* side does not. The fix: resolve the rename where the prices are
      fetched, so the panel carries the broker's symbol, and record the old spelling
      rather than silently keeping it.
   12. **The floor has hysteresis, and nobody has measured it.** The kept set is the
      drop-then-admit fixed point on the day's own weights (`floor_rule`
      `drop_then_admit`, `live/construction_table.py`), so a name sitting on the
      20-share line flips in and out as its weight moves a few dollars. Measured on
      the three stored manifests of 2026-10-05 to 10-07: **16 of the 39 names that
      left on 10-07 had been admitted on 10-06** (BIIB, BRO, CTAS, GEHC, GRMN, HPE,
      LOW, MRK, MTB, O, PNC, RDDT, ROST, TXT, WELL, XYL) and **5 of the 24 that
      arrived had been dropped on 10-06** (BBY, CMS, CNC, INVH, LHX), with only 140
      names kept on all three days against 191, 195 and 180 kept. Each round trip is
      two crossings of the spread and the impact term on a leg that was already at
      its target size, and on a leg of a few hundred dollars the cost of the two
      trades is a large fraction of the position. What to do: **measure the
      round-trip churn at the floor since launch** - names that leave and return
      within k sessions, the dollars traded twice, and what the two legs cost
      against the name's own weight - and propose an **entry/exit band** (admit at
      the floor, release only below some fraction of it, so a name inside the band
      is held at its weight rather than traded) with the band's width set from that
      measurement. `tests/test_construction_table.py` for the band, and the three
      days above as its own case.
   13. **The risk block carries six names the universe does not.** `efb.e11_specific_var`
      holds 499 names on 2026-10-07 while the sized universe is 496, and the six in
      the block and not in the universe are **BLDR, CTVA, PSKY, TAP, TTD, WBD** - the
      same six the descriptor and specific-return inputs carry too. Two of them are
      explained and four are not: **PSKY** is SKYD's own old spelling (item 11), and
      **WBD** was a universe member until 2026-10-05 (the 10-05 universe is 503 names
      and it is not among the 10-06 503), while BLDR, CTVA, TAP and TTD are names the
      model still estimates and the index no longer holds. The question is whether
      this is harmless: the block is a table keyed by ticker, the sizing asks it only
      for names in `names`, and nothing iterates it - so today it changes no number,
      which is the definition of harmless *for now*. What it does do is make every
      count taken off that table wrong by six, and it is the same one-way door as the
      `excluded` list (item 9): the artifact only grows, nothing prunes it, and a
      reader comparing "499 estimated" against "496 sized" has to know why. The fix:
      decide deliberately whether the live risk inputs are the universe's own names
      or a superset, and record the answer where the counts are read - and check
      whether the vendor artifact's extra names can carry a stale descriptor row into
      the fit for a name the index has dropped.
   14. **One source for the specific variance, or two that can disagree.** The drop reads
      the artifact the evening priced from - the run tree, because `live/runroot.py:180`
      points `evening_job.DATA_ROOT` at it and `scripts/run_live_daily.py:1626` hands the
      same tree to `store_proposal` - while `store_proposal` resolves its own root:
      `Path(data_root) if data_root is not None else ROOT / "data"`
      (`scripts/run_live_daily.py:236`). On the live path the two agree twice over: same
      file, and the same block rule on both sides, "the latest artifact date at or before
      the close" (`efb/race.py:79-90` against `live/trade_reasons.py:208-212`), which was
      checked by comparing the two readers' verdicts name by name on 2026-10-07's closes
      and finding them identical (Q, FDXF, HONA, SKYD and DD in both, five of five). What
      nothing enforces is the file: a caller that omits `data_root` reads the repository's
      `data/` and can disagree with what the evening dropped, which is the 2026-10-07
      crash this change exists to remove - and a *refusal* is a crash, not a quiet
      difference. The fix: give the write one source. Either pass the variance vector the
      sizing used (or the block's own date) into `store_proposal`, or have it refuse
      against the manifest's own `dropped_no_risk` instead of re-reading the artifact, so
      the two cannot be pointed at different files. `tests/test_run_live_daily.py` for the
      refusal, with a store whose artifact lacks a name the book holds.
   15. **Zero is asymmetric.** `dropped_for_no_risk` rejects a variance that is not
      positive (`live/evening_job.py:428`: `value <= 0.0`), and `specific_std_or_refuse`
      refuses only what is not finite (`scripts/run_live_daily.py:221`), so a variance of
      exactly `0.0` passes the write's guard as `idio_vol = 0.0` - a name stored with no
      risk at all, which is the same lie as the NaN and a quieter one. It is unreachable
      from the live path, because the evening drops such a name before it is sized: that
      is the point. Two definitions of "has a risk estimate" in the same loop is one too
      many, so tighten the refusal to non-positive (a negative already arrives as NaN
      from `live/trade_reasons.py:214`, so only the zero is left) and make the two
      predicates one function both sides call.
   16. **`dropped_no_risk` is not on the page.** The manifest carries it
      (`live/evening_job.py:1438-1439`), the evening's message carries it
      (`live/notify.py:526-534`), and the store keeps the manifest - but
      `live/snapshot.py` writes no key for it, so the one fact that says *why* tonight's
      book is narrower than the index can only be read in that morning's mail or by
      opening `efb.proposals`. Every other drop the loop makes is on the page: the
      no-price names through the book's own reason, the excluded ones through the
      fixtures' counts. Put the dropped names and their reasons on the page beside the
      counts the manifest already supplies, so a reader of the document does not have to
      trust that an absence was deliberate.
   17. **The SPY ticker list is not deduplicated.** `spy_tickers` is
      `sorted(universe["ticker"].astype(str).str.upper().str.strip())`
      (`live/evening_job.py:1268`), which keeps a duplicate: the name would be in `names`
      twice, so it would be sized twice, counted twice in `n_kept`, hedged against
      itself, and written to `efb.positions` twice - where the natural key would collapse
      the two rows and leave the row count disagreeing with every count taken off the
      manifest. Measured on the 2026-09-21 archive: 503 rows, 0 duplicates, and 499
      unique tickers in the artifact's last block, so this is latent rather than live.
      The fix is `sorted(set(...))` **with** a warning when it drops one, because a
      duplicated universe row is a vendor defect the day's report should name rather
      than absorb.

   The exit condition is the seventeen of them fixed or written down here, and the day's
   own numbers as a case in each test rather than a number typed from a message.

## 4. Rollback

Before 2026-11-11 the branch is parked and a rollback is `git checkout main`:
nothing on the live path has moved. After the merge, the merge is one commit and
the seed is one measured manifest, so both sides are reversible. In order:

1. **Stop the cron first.** `scripts/run_cron.py` is the only writer, and a run
   started against a half-restored tree is the failure mode, not a stale tree.
2. **Restore the research tree.** `git revert -m 1 <merge commit>` on `main`,
   which also returns `live/extend.py` to `inputs["returns"]`. `main` is what the
   evening reads.
3. **Restore the seed.** Run `scripts.push_seed` from a checkout of the pre-merge
   `main`, which re-uploads the pre-merge artifacts and writes the pre-merge
   manifest. Until that lands, unset `EFB_SEED_R2_*` so the run refuses at the
   seed check rather than sizing from a tree it cannot describe; `live/seed.py`
   refuses rather than starting.
4. **Re-declare the champion** on the restored tree
   (`eval_risk.apply_champion()`) and run `make test`.

What a rollback does not undo:

- **The store is append-only.** A proposal written while the merge was live stays
  on the record, and the next evening sizes from the restored seed against the
  real account, so the two are reconciled by the ordinary morning job rather than
  by editing rows. The rollback records the incident; it does not erase the
  evening.
- **A published snapshot or evidence directory** is a separate artifact with its
  own history (`evidence/MANIFEST.json`). Re-uploading an older one is a
  deliberate act, not part of the revert.

## 5. The panel pin, every rebuild takes an end date

`make rebuild-e1` … `make rebuild-e10` all take `END=YYYY-MM-DD`, and the entry
point behind them takes `--end`. Left unset the pin is the **stored panel's own last
session** (`efb.build.pinned_panel_end`, read from the date index of
`data/processed/returns.parquet`), not the clock, so a rebuild that re-reads sources
cannot extend the panel by accident. A first build, with no panel on disk, still
falls back to today, because there is nothing to freeze yet.

**`END=2026-10-02` is the date every rebuild in this pass used**: the stored panel's
last session (4,213 sessions from 2010-01-04, `data/processed/returns.parquet`),
which is the panel every re-scored record here was measured on. State that date when
re-running any of these rebuilds.

Two rules come with it:

- a leg that **reads** the panel (E2 … E10) refuses a pin earlier than the panel's
owned end, because it cannot un-read rows it has already been handed;
- `rebuild-e1` is the exception: it *makes* the panel, so an earlier pin re-cuts it,
  and an `END` past the stored end is how a run says it means to extend the panel.

The price and factor artifacts are clipped at the pin
(`efb.prices.build_prices_artifact`, `efb.factors.build_factors_artifact`) and the
membership grid is built to it (`efb.universe.build_membership`). Those are the two
ways the panel used to grow on an ordinary `make rebuild`: a price cache refreshed by
a live run, and a membership grid that ran to today. `tests/test_panel_freeze.py`
holds both directions, together with the control that the newer source rows really
are in the fixture.

## 6. The 2026-10-03 dry run, and what it settled

Everything here was measured on the branch, against a materialised run root, a
read-only Alpaca account and a read-only store. Nothing was uploaded, written to
the store or sent to a broker.

**1. The parity guard responds to the edit.** In a worktree of `e87ef1d` with
`live/extend.py:379` reading `returns_clean`, and the rest of the tree untouched,
`pytest tests/test_live_panel_parity.py -m merge_guard` is 1 passed, 2
deselected. The red in §2 is therefore the branch's statement about the two
readers, not an artefact of the test.

**2. The run root.** `data/` was copied to `/tmp/efb-bp/runroot/data`, the five
XS-v1 cross-sectional artifacts were frozen at the last month end (2026-08-31,
descriptors 667,660 to 660,632 rows) and the model was extended forward to
2026-10-02, so the tree carries one published descriptor row per session, which
the repository tree cannot.

The extension was one pass, not the live loop's one session at a time, and the
reason is cost: a pass truncated at its own close refits the whole panel, measured
at 879 s, so the 23 truncated passes the window needs are about five and a half
hours, against 870 s for the single pass that publishes all 23 sessions at once.
The equivalence is a property of the artifacts rather than an assumption: every
descriptor on a row is a shifted quantity standardised over the names priced on
that row's own date, so no session after the close enters it, and the vintage
tests are the check, because they rebuild each ordinary session's row from a
panel truncated at the close and require it to agree with the published row to
1e-10. They do.

**3. The hedge-vintage tests on the branch's own panel.** Six of the eight pass,
including the two the regenerated seed exists to fix:

- `test_the_row_built_at_the_close_is_the_row_the_model_publishes`
- `test_the_book_carries_no_exposure_under_the_published_row`

On the live tree `/tmp/efb-repair/data` those same two fail (the 2026-09-17 to
2026-09-18 pair leaves 1.022e-03 of exposure against a 1e-10 bound), which is the
by-construction failure §3 step 4 removes. Two different tests fail instead, and
both are facts about the panel rather than about the change:

- `test_a_sparse_replay_keeps_the_row_dated_the_close` hardcodes the 2026-09-01
  close and expects the artifact to publish nothing for 2026-09-02. That is the
  live tree's shape: its daily tail starts 2026-09-03, so it carries 209
  published dates. A research rebuild cannot reproduce it, because
  `extend_model` appends every session after the last published row, so the
  branch's root starts its tail on 2026-09-01 and carries 211. The stale
  fallback the test asserts is real and is exercised by
  `test_the_builder_declines_rather_than_hedging_on_a_short_window`; what is
  unreachable on this tree is the month-end gap that this particular hardcoded
  date stands for.
- `test_the_session_before_a_holiday_is_bounded_and_not_exact` asserts that at
  least one name is in the 2026-09-08 cross-section but not priced at the
  2026-09-04 close. On the corrected panel the 2026-09-04 close prices 502 names
  and the built row equals the published row to 5.4e-14, so no name enters and
  the assertion is not reachable. Read across every consecutive pair in
  2026-09-01 to 2026-10-02, the live tree's priced set moves three times (32
  names leave from 2026-09-03 to 2026-09-04, 325 leave and 2 enter from 2026-09-21
  to 2026-09-22, VYLR enters from 2026-09-30 to 2026-10-01) and the branch's root
  moves at none. The docstring's "the only pair in the published daily window
  whose priced set moves" is a property of the live tree's ragged price
  coverage; the corrected panel is dense enough that Labor Day no longer moves
  it. Re-pointing the case needs a pair the corrected panel moves, and this pass
  found none in the window, so the case is left red and named here rather than
  silently re-pointed.

**4. The book the merge would trade.** Built with the live path at the account's
own equity of 996,885.53 USD, against the proposal the store holds for
2026-10-02:

| | stored (tonight's live book) | built (this branch, same NAV) |
|---|---|---|
| n_kept | 204 | 199 |
| n_eff_kept | 152.603227 | 150.975015 |
| gross | 1.000000 | 1.000000 |
| kept gross before renormalisation | | 0.526437 |
| construction / floor | | share_only / drop_then_admit |

173 names are in both, 31 only in the stored book and 26 only in the built one,
and the first evening's turnover is 332,904 USD, 33.39% of NAV. The number that
matters is `n_kept`: 199 against 204, not the 502 the disabled 20-share floor
produced before item 1. The floor, the construction and the gross are unchanged
by the merge; what moves is the cross-section the corrected panel ranks.

**5. Not done here.** No seed was regenerated (`scripts.push_seed --dry-run`
needs the R2 credentials this pass deliberately does not use), so §3 steps 3 and
5 remain unmeasured, and §3 step 8's three hashes are measured but not yet
written into `tests/test_e11_extend.py`: on the dry run's tree they are
`bc7bba30da9b6a9955ecef20fa24cb6096f7e7686d877c7d3ae40e2375113ef5`,
`a43d66ce62e08eca28adf44b74867ab9a0718d1427973fa43362140ce4913be8` and
`d65a67f15f0bb844de7e3f6b7d49f9948d78d5a3aedd37f899550476e841f7dc` for the
descriptor, factor-return and specific-return blocks dated on or before
2026-09-03, against the `8f93968f`, `42a31d64` and `176dc4b3` the file records.
Those three are seed-generation values and are re-recorded on the day the seed
moves, not before.

Nothing in §1 was executed against a live tree by this branch: the effects in its
last column are read off the call sites, and the dry run above exercises the
research side of them plus the one live file the merge changes.

**6. The three reds that belong to the seed regeneration, not to this branch.**
They are left red deliberately, and none of them is skipped, deselected or
xfailed on the branch:

- `tests/test_hedge_vintage.py::test_a_sparse_replay_keeps_the_row_dated_the_close`
  and `::test_the_session_before_a_holiday_is_bounded_and_not_exact`. Both are
  the same family as §3 step 4: the first hardcodes a close whose next session a
  live tree has not published and a research tree cannot avoid publishing, and
  the second asserts that the priced set moves across Labor Day, which it does
  on the vendor's ragged live coverage and does not on the corrected panel. They
  are read on the regenerated seed, where the tree the live loop has extended is
  the artifact under test.
- `tests/test_e11_extend.py::test_pre_cutoff_blocks_are_byte_identical`. The
  baseline it pins was taken from a live tree, so a research rebuild cannot
  satisfy it; it is re-recorded by `extend.incremental_integrity()` on the day
  the seed moves, which is §3 step 8.

Two further reds are not the branch's either and are recorded in
`docs/hygiene_ledger.md`: the APH split case in `tests/test_e11_corporate_actions.py`,
whose premise is that the vendor's raw closes halve across the split and whose
cache now serves split-adjusted closes, and the beta-magnitude inequality in
`tests/test_construction_table.py`, which the corrected panel breaks on its
sparsest row.
