# `EFB_HEDGE_MODE`: the cap-then-rehedge hedge, behind a default-off flag

Two research notes recommend the construction this flag switches on:
`docs/research/nov11_hedge.md` (origin/nov11) and
`docs/research/etf_overlay_hedge.md` (origin/research-etf-hedge). Measured on the live
books they report the worst single-name share of predicted specific risk falling from
about 12-20% to 9.6% (SMCI was the worst name at 11-12%), predicted vol from 2.02% to
1.84%, exact factor neutrality kept, and slightly lower cost. This is the live
implementation of it, off by default: **unset is the hedge the loop has always built,
byte for byte**, and turning it on is the owner's decision, not this branch's.

## The flag

| `EFB_HEDGE_MODE` | what the loop builds |
|---|---|
| unset, empty, `exact` (any case, surrounding space ignored) | today's hedge: size, cap the variance shares, renormalize, exact FMP hedge, renormalize |
| `cap_then_rehedge` | the same sizing, then the cap applied *after* the hedge with the factor neutrality restored after it, three passes |
| anything else | **exact**, with one warning naming the value, because a typo must never change the book |

The value is read once per process (`live/evening_job.hedge_mode`, cached in
`_HEDGE_MODE_CACHE`). The floor search calls the sizing hundreds of times per row, so
reading it per call would let a value that changed mid-run build a book out of two
hedges and would log a typo once per candidate set. A change therefore takes effect on
the next run, never mid-run.

## Where it applies

An evening builds the hedge in exactly two places, and the flag is applied at both.

1. **`live/evening_job.sized_kept_weights`** — `w_sub, pre_hedge =
   sizing.procedure_6_3_hedged_with_exposures(...)`, then
   `w_sub = apply_hedge_mode(w_sub, design[idx], specific[idx])`. This is the traded
   vector: every kept set the floor considers goes through this function
   (`finalize_kept_set`, `kept_set_clears_floor`), and the floor's drop-then-admit
   fixed point (`enforce_floor_by_drop_then_admit` -> `enforce_floor_on_final_weights`)
   rebuilds the set's weights through it on every pass. Applying the flag here, and
   only here for the kept book, is what makes the cap hold on the vector that actually
   trades rather than on the one that existed before the floor ran.
2. **`live/evening_job.build_proposal`** — the full-book construction,
   `weights = size.procedure_6_3(alpha_vec, design, factor_covariance, specific)`
   followed by `weights = apply_hedge_mode(weights, design, specific)`. This book is
   before the floor exists; it is what the manifest's full-book risk numbers describe,
   and it is the vector whose `|w_i| / floor_i` order decides the order in which the
   floor *admits* names (`floor_order_within`). Leaving it out would mean the run
   reported one hedge and built its kept set from another.

The construction itself is `live/sizing.cap_then_rehedge`: cap the variance shares,
re-project onto the factor-neutral space with the same exact projection the hedge uses
(`hedge_exact_robust`), repeat `REHEDGE_ROUNDS = 3` times. The last operation of the
last pass is a projection, so the book ends factor-neutral to machine precision and the
cap is met to within whatever that final projection moves it.

Nothing else changes: same universe, same sizing, same floor, same vol target, same
cost model. The flag is recorded on the manifest so a later reader can tell which hedge
built a book:

```sql
select trade_date, manifest->>'hedge_mode', manifest->>'max_variance_share'
  from efb.proposals order by trade_date desc;
```

## Proof 1: flag off is the book the loop already builds

`build_proposal(store=False)` on the 2026-10-13, -14 and -15 inputs, from
`origin/main` and from this branch, each on its own copy of a tree built to be the
live one: the 20 files of the R2 seed (`efb-seed`, downloaded read-only) plus the
store's appendix rows dated on or before the close, rebuilt with
`live.extend.extend_returns`, and the session's own rows present exactly as
`extend_model` leaves them (the pipeline order is `extend_model()` then
`build_proposal`, `scripts/run_live_daily.py:1465` and `:1614`). Every date's
`hedge_design_vintage` label comes out as the live run's own —
`built from data through 2026-10-13`, `-14`, `-15` — and the 2026-10-13 and 2026-10-15
books reproduce the stored live manifests on the kept count, the predicted vol and the
worst variance share to the last digit they were stored at:

| close | live manifest (`efb.proposals`) | rebuilt on `origin/main` | rebuilt on this branch, flag unset |
|---|---|---|---|
| 2026-10-13 | n_kept 171, 2.759925%, 10.987672% (SMCI) | n_kept 171, 2.75992544%, 10.98767172% (SMCI) | identical |
| 2026-10-15 | n_kept 169, 2.747942%, 11.980927% (SMCI) | n_kept 169, 2.74794188%, 11.98092696% (SMCI) | identical |
| 2026-10-14 | no manifest: the run failed before sizing | n_kept 176, 2.649821%, 8.836417% (SMCI) | identical |

**The identity itself.** For all three closes, on the two code trees and one input tree
each: the kept name sets are equal, the **maximum absolute weight difference is exactly
0.0**, and `kept_gross`, `n_kept`, `excluded`, `dropped_no_price`, `dropped_no_risk`,
the achieved vols, the variance shares, the traded notional and every other manifest
field are equal too — not approximately, equal. The flag's only effect on a run that
does not set it is the new `hedge_mode: "exact"` key on the manifest.

## Proof 2: flag on, for information only

Same three closes, same trees, `EFB_HEDGE_MODE=cap_then_rehedge`, on the **final traded
book**:

| close | mode | n_kept | predicted vol | worst single-name share | max abs residual factor exposure | gross | traded notional vs the previous close's book | cost |
|---|---|---|---|---|---|---|---|---|
| 2026-10-13 | exact | 171 | 2.7599% | 10.9877% (SMCI) | 1.13e-15 | 1.0000000000 | $449,701 | 14.24 bp |
| 2026-10-13 | cap_then_rehedge | 191 | 2.5920% | **10.0193%** (SMCI) | 6.94e-17 | 1.0000000000 | $455,449 (+1.28%) | 14.22 bp |
| 2026-10-14 | exact | 176 | 2.6498% | 8.8364% (SMCI) | 5.20e-16 | 1.0000000000 | $485,040 | 14.43 bp |
| 2026-10-14 | cap_then_rehedge | 187 | 2.5456% | **6.9646%** (SMCI) | 8.33e-17 | 1.0000000000 | $491,274 (+1.29%) | 14.43 bp |
| 2026-10-15 | exact | 169 | 2.7479% | 11.9809% (SMCI) | 1.45e-15 | 1.0000000000 | $441,589 | 14.26 bp |
| 2026-10-15 | cap_then_rehedge | 171 | 2.8249% | **10.0081%** (SMCI) | 7.29e-17 | 1.0000000000 | $464,457 (+5.18%) | 14.27 bp |

Reading it honestly:

- **The cap holds.** On the noisiest close (2026-10-15) the worst name goes from
  11.98% to 10.0081% of the book's predicted specific variance; on 2026-10-13 from
  10.99% to 10.0193%, and on 2026-10-14, where the exact book was already inside the
  cap at 8.84%, the flag's book is inside it at 6.96%. The residual overage on the
  first two is the last re-projection's own move, not a failed pass: the cap is applied
  and then the neutrality is restored, and the second step is what the research asks
  for. SMCI is the worst name on every close either way, which is the one the research
  named.
- **Neutrality is kept, and is tighter.** The traded book's residual exposure is
  7e-17 to 8e-17 with the flag on, against 5e-16 to 1.5e-15 on the exact book: the
  projection the flag ends with is the same projection, applied one more time.
- **The kept set moves, and that is the flag's largest visible effect.** 171 -> 191,
  176 -> 187, 169 -> 171 names, with 22/42, 12/23 and 16/18 names leaving and joining
  respectively, and 149/164/153 names keeping a position at a changed weight. The
  reason is the second application site: capping the *full* book changes its
  `|w_i| / floor_i` order, so the floor admits different names. This is a book change,
  not a cosmetic one, and it is why the flag is off.
- **Turnover is slightly up on these three closes** (+1.3%, +1.3%, +5.2%) even though
  the research measured the cap-then-rehedge *hedge leg* trading about 6% less. Both
  are true: the research compares the hedge leg alone on a fixed book, while the traded
  notional here is the whole rebalance, and the changed kept set adds the difference.
- **Predicted vol is lower on two closes and higher on one** (2.7599 -> 2.5920,
  2.6498 -> 2.5456, 2.7479 -> 2.8249): the cap is a concentration rule, not a vol rule,
  and on 2026-10-15 the book it produces is a little less diversified in dollars.

## The research's input was the pre-hedge book, not the traded one

The question the ETF study left open: in `scripts/etf_overlay_research.py:live_books()`
(origin/research-etf-hedge), is the input `u` the pre-hedge sized book or the
already-hedged traded book?

**It is the pre-hedge sized book**, the book the hedge acts *on*, not the book that
trades. `live_books()` reads `efb.positions` for each close's `alpha` and `idio_vol` and
rebuilds it with the three calls the live path uses before it hedges - proportional
sizing, the variance-share cap, renormalized to gross 1.0 - and never hedges it. That
is the same vector `live/evening_job.sized_kept_weights` hands to
`procedure_6_3_hedged_with_exposures` as `sized`, and the study then applies each
variant's own hedge to it.

**One thing to know when reading its numbers.** The live path's diagonal is the
specific *variance*, and the store's `idio_vol` column is the specific *volatility*:
for SMCI on 2026-10-13, `efb.positions.idio_vol` is 0.0499164 and
`efb.e11_specific_var.specific_var` is 0.0024916, which is its square, and the live
manifest's own `specific_variance` for that name is the same 0.0024916. The live
sizing divides by the variance (`size.proportional`, "w proportional to alpha /
sigma^2"); `live_books()` passes `sigma = np.sqrt(idio_vol)` to the sizing and
`idio_vol` itself to the cap, so its `u` divides by the square root of the variance
where the loop divides by the variance. Measured against the live run's own stored
`exposures_before_hedge` for 2026-10-13, and rebuilding that vector from the store's
columns both ways:

| diagonal used | max abs difference from the live manifest's `exposures_before_hedge` |
|---|---|
| `idio_vol ** 2` (the model's variance, what the loop sizes on) | **0.0** |
| `idio_vol` (what the study's rebuild uses) | 0.526 |

So the study's `u` is a pre-hedge book, but not exactly the live one: it is the store's
alpha over the square root of the specific variance, capped on the specific volatility
as if it were the variance, which tilts it towards the names with the largest specific
volatility. That is why the study's worst-name share for 2026-10-13 is 19.99% where the
live manifest records 10.99%, and why its `exact` variant's volatility for the window
(2.02%) is not the traded book's (2.60-2.76% on these three closes). The relative
comparison - A, B, C, D all measured on the same `u` - is unaffected; the absolute
levels should be read as that book's, not the loop's. The flag's own table above is
measured on the traded book with the model's variance, and it confirms the study's
recommendation independently: 10.99% -> 10.02%, 11.98% -> 10.01% on the two closes
where the cap bound.

The same `idio_vol`-as-variance convention appears in the study's sibling on
origin/nov11 (`scripts/nov11_hedge_research.py:live_books()`) and in the callers of
`efb/attribution.pre_hedge_weights`, which documents its argument as the variance.
None of that is touched by this branch: the note here is for reading those numbers,
and the research scripts and their stored JSONs are unchanged.

## Tests, lint and the gate

- `tests/test_e11_variance_cap.py` pins the flag's semantics (unset, empty, `exact` in
  any case, the one value that switches, five typos that fall back with a warning, and
  the read-once-per-process rule), the default mode's byte-for-byte identity
  (`apply_hedge_mode` returns the same array it was handed; the traded vector equals
  the explicit cap-hedge-renormalize construction), and the construction itself on a
  fixture where the exact book's worst name is 11.94% of the variance and the flag's is
  10.00508% with the neutrality to 1e-12.
- `tests/test_e11_evening.py` builds two real proposals on the tree — one with no flag,
  one with `cap_then_rehedge` — and asserts the manifest records the mode, that the
  default leaves a name over the cap, and that the flag's traded book is inside it and
  still neutral.
- `make lint` (ruff, mypy over `live scripts`, black) is green.
- The gate suite `.venv/bin/python -m pytest tests/ -q -m "not slow and not
  requires_live_tree and not merge_guard"`, run on `origin/main` and on this branch in
  the same environment, fails on **exactly the same id set** — 60 failures with the
  committed seed tree present (48 of them in `docs/known_test_failures.md`; the other
  12, including four `tests/test_week2_spinoff.py` tests that stop on a live vendor
  split answer for CTVA, fail identically on `origin/main`), and 84 failures plus 50
  errors in a worktree with no artifacts at all. Zero new, zero newly passing, and the
  branch's own new tests are the only difference in the pass count.

## How to turn it on, and off

`EFB_HEDGE_MODE` is an environment variable, so it is set where the loop runs: the
Render cron service `efb-live-daily` (`render.yaml`, `startCommand: python
scripts/run_cron.py`).

1. Render dashboard -> the `efb-live-daily` service -> Environment -> add
   `EFB_HEDGE_MODE` = `cap_then_rehedge`, and let Render restart the service.
2. The next evening run builds the cap-then-rehedge book and records
   `"hedge_mode": "cap_then_rehedge"` on its manifest; the email and the page are
   unchanged apart from the numbers.
3. To go back: set it to `exact`, or delete the variable. Unset, empty and `exact` are
   the same thing, and any other value also falls back to `exact` — with a warning
   naming the value in the log, so a typo cannot quietly trade a different book.

Nothing else has to change, and nothing is persisted differently: the flag is read from
the environment on every run, so the previous behaviour is one variable away, and
`manifest->>'hedge_mode'` on any stored proposal says which hedge built it.
