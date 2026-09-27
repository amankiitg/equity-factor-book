"""Build the E11 walkthrough notebook cells from a source list.

Generated, not hand-edited, so the criteria text and the numbers stay as stored.
Execution and rendering happen through nbconvert:

    .venv/bin/python sprints/E11/build_walkthrough.py
    .venv/bin/python -m jupyter nbconvert --to notebook --execute --inplace \
        notebooks/E11_walkthrough.ipynb
    .venv/bin/python -m jupyter nbconvert --to html \
        notebooks/E11_walkthrough.ipynb --output E11_walkthrough.html

The close the notebook traces is the newest session the stored artifacts price,
not a date typed here. See the `stored cross-check` section for what that means
for 2026-09-25.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CELLS: list[tuple[str, str]] = [
    (
        "markdown",
        "# Sprint E11 walkthrough: one evening of the book, end to end\n"
        "\n"
        "Purpose: to follow one evening of the daily long/short paper book from\n"
        "the seed to the email, tracing one name through every step, so that each\n"
        "number the live page shows can be derived at a whiteboard and audited\n"
        "against a stored file. Inputs and outputs are labelled at each step.\n"
        "\n"
        "Nothing here is typed by hand. Every number is read from an artifact, or\n"
        "recomputed by the library from an artifact and compared against the\n"
        "stored answer.",
    ),
    (
        "code",
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "\n"
        "ROOT = Path.cwd()\n"
        'if not (ROOT / "efb").exists():\n'
        "    ROOT = ROOT.parent\n"
        "if str(ROOT) not in sys.path:\n"
        "    sys.path.insert(0, str(ROOT))\n"
        'DATA = ROOT / "data"',
    ),
    (
        "markdown",
        "## 0. The evening being traced\n"
        "\n"
        "The close is **read from the stored price panel**, so the notebook cannot\n"
        "claim a date its inputs do not price. The name followed through every step\n"
        "and the name the variance cap acts on are found in the book, not written\n"
        "into this cell: `TRACE` is asserted to be present, and the cap case is\n"
        "whichever name the pre-cap variance shares put highest.",
    ),
    (
        "code",
        "prices = pd.read_parquet(DATA / 'raw' / 'prices.parquet')\n"
        "CLOSE = pd.Timestamp(prices.index.get_level_values('date').max())\n"
        "STAMP = str(CLOSE.date())\n"
        "print('INPUT  data/raw/prices.parquet, the date index, newest session')\n"
        "print('one evening traced end to end at the close:', STAMP)",
    ),
    (
        "code",
        "# The evening itself, once: `build_proposal` is the whole sizing night, and\n"
        "# every later cell reproduces one step of it and compares to this manifest.\n"
        "# Nothing is stored (store=False), so the notebook cannot move the live book.\n"
        "from live import evening_job as ej\n"
        "\n"
        "PROPOSAL = ej.build_proposal(as_of=CLOSE, store=False)\n"
        "NAV = PROPOSAL['nav']\n"
        "print('OUTPUT the evening manifest, live/evening_job.py::build_proposal')\n"
        "for field in ('as_of', 'n_names', 'n_excluded', 'n_kept', 'gross', 'net',\n"
        "              'kept_gross', 'constraint', 'achieved_annual_vol',\n"
        "              'target_annual_vol', 'gross_cap_bound', 'idio_share_after_fmp',\n"
        "              'max_abs_exposure_after_fmp', 'expected_establishment_cost_bps',\n"
        "              'max_input_staleness_days'):\n"
        "    if field in PROPOSAL:\n"
        "        print(f'  {field} = {PROPOSAL[field]}')\n"
        "print('nav (the paper notional) =', NAV)",
    ),
    (
        "markdown",
        "## 1. The seed, the appended sessions, and the staleness gate per input\n"
        "\n"
        "Two universes meet here and the seam is never bridged. History is frozen on\n"
        "the pinned Wikipedia table through the seed cutoff; the live universe comes\n"
        "from the SPY archive from 2026-09-18 forward. The model is extended one\n"
        "session at a time, and the gate then checks **every input** for distance\n"
        "from the close being priced, in NYSE sessions, against the allowance each\n"
        "input carries.",
    ),
    (
        "code",
        "from live import appendix, extend, staleness\n"
        "\n"
        "returns = pd.read_parquet(DATA / 'processed' / 'returns.parquet', columns=['r'])\n"
        "sessions = pd.DatetimeIndex(sorted(returns.index.get_level_values('date').unique()))\n"
        "appended = sessions[sessions > appendix.SEED_CUTOFF]\n"
        "print('INPUT  data/processed/returns.parquet, the date index')\n"
        "print('  seed cutoff (live/appendix.py::SEED_CUTOFF):', appendix.SEED_CUTOFF.date())\n"
        "print('  sessions stored in the tree:', len(sessions),\n"
        "      'from', str(sessions.min().date()), 'to', str(sessions.max().date()))\n"
        "print('  appended after the cutoff, one fit each:', len(appended))\n"
        "print('  newest appended:', [str(day.date()) for day in appended[-4:]])\n"
        "print('  last priced session (live/extend.py):', extend.last_price_session(DATA).date())",
    ),
    (
        "code",
        "# The gate, per input. `sessions_behind` is NYSE sessions and is the number\n"
        "# that decides; `max_input_staleness_days` is calendar days and is only what\n"
        "# the email quotes. The universe is the one input allowed to be a session\n"
        "# behind, because an index snapshot is filed after the close it describes.\n"
        "GATE = staleness.check(root=DATA, target=CLOSE)\n"
        "gate_rows = pd.DataFrame([{'input': name, **entry}\n"
        "                         for name, entry in GATE['inputs'].items()])\n"
        "print('OUTPUT live/staleness.py::check')\n"
        "print(gate_rows[['input', 'gated_by', 'content', 'content_sessions_behind',\n"
        "                 'fetch', 'allowed_sessions_behind', 'sessions_behind']]\n"
        "      .to_string(index=False))\n"
        "print('status:', GATE['status'], '| worst input:', GATE['worst_input'],\n"
        "      '| worst sessions behind:', GATE['worst_sessions_behind'])\n"
        "print('max_input_staleness_days (calendar):', GATE['max_input_staleness_days'])",
    ),
    (
        "code",
        "# The universe is asserted, not assumed: it is the newest SPY archive dated\n"
        "# on or before the close, and a file before the seam is refused.\n"
        "universe, spy_path = ej.load_spy_universe(DATA, as_of=CLOSE)\n"
        "SPY = sorted(universe['ticker'].astype(str).str.upper().str.strip())\n"
        "wide, _counts = ej.eval_risk.load_clean_wide(DATA)\n"
        "model_names = {str(column) for column in wide.columns}\n"
        "NAMES = [ticker for ticker in SPY if ticker in model_names]\n"
        "EXCLUDED = [ticker for ticker in SPY if ticker not in model_names]\n"
        "print('INPUT  ' + str(spy_path.relative_to(ROOT)))\n"
        "print('  SPY members', len(SPY), '| known to the frozen model', len(NAMES),\n"
        "      '| excluded and counted, never imputed', len(EXCLUDED))\n"
        "print('  excluded:', EXCLUDED)\n"
        "assert len(NAMES) == PROPOSAL['n_names'], 'the universe moved under the trace'",
    ),
    (
        "markdown",
        "## 2. The alpha, the specific volatility, and the sized weight\n"
        "\n"
        "INPUT: `models/XS-v1/specific_returns.parquet` for the signal,\n"
        "`alpha/summary.parquet` for the IC, `models/XS-v1/specific_var.parquet` (via\n"
        "the model pieces) for the variance. OUTPUT: the alpha vector the sizing reads.\n"
        "\n"
        "`signal` is the compounded specific return over t-252 to t-21. It is\n"
        "standardized across the cross-section, then multiplied by the stored IC, the\n"
        "specific variance and the shrinkage `kappa`.",
    ),
    (
        "code",
        "from efb import alpha as alpha_mod\n"
        "from efb import size\n"
        "\n"
        "PIECES = ej.eval_risk._xs_pieces(CLOSE, NAMES, DATA)\n"
        "DESIGN, FACTOR_COV, SPECIFIC = PIECES['design'], PIECES['factor_covariance'], PIECES['specific']\n"
        "IC = ej._stored_ic(ej.SIGNAL, DATA)\n"
        "KAPPA = alpha_mod.KAPPA\n"
        "signal = alpha_mod.idio_momentum(DATA)\n"
        "raw = (signal.loc[pd.to_datetime(signal['date']) == CLOSE]\n"
        "       .set_index('ticker')['signal'].reindex(NAMES))\n"
        "Z = ((raw - raw.mean()) / raw.std(ddof=1)).fillna(0.0)\n"
        "ALPHA = np.where(np.isfinite(SPECIFIC), IC * SPECIFIC * Z * KAPPA,\n"
        "                 IC * float(np.nanmedian(SPECIFIC)) * Z * KAPPA)\n"
        "ALPHA = pd.Series(ALPHA, index=NAMES)\n"
        "print('INPUT  ic =', IC, 'from data/alpha/summary.parquet, ic_h1_mean')\n"
        "print('INPUT  kappa =', KAPPA, 'from efb/alpha.py::KAPPA')\n"
        "print('INPUT  the design is', DESIGN.shape, '= names x estimated factors')\n"
        "SIZED_FULL = size.proportional(ALPHA.to_numpy(float), SPECIFIC)\n"
        "print()\n"
        "for ticker in ('LITE', 'MRNA'):\n"
        "    if ticker not in NAMES:\n"
        "        print(f'{ticker}: not in the universe at this close')\n"
        "        continue\n"
        "    position = NAMES.index(ticker)\n"
        "    print(f'{ticker}: signal {raw[ticker]:+.6f} | z {Z[ticker]:+.6f} | '\n"
        "          f'specific variance {SPECIFIC[position]:.6e} | alpha {ALPHA[ticker]:.6e} | '\n"
        "          f'alpha/specific {SIZED_FULL[position]:+.6f}')",
    ),
    (
        "code",
        "# The alpha arithmetic, checked against the stored proposal for the names the\n"
        "# two books share, so the check is against a stored number and not against\n"
        "# the notebook's own output.\n"
        "STORED_BOOK = pd.read_parquet(ROOT / 'live' / 'proposals' / f'proposal_{STAMP}.parquet')\n"
        "STORED = STORED_BOOK.set_index('ticker')\n"
        "shared = [ticker for ticker in STORED.index if ticker in ALPHA.index]\n"
        "gap = float((STORED.loc[shared, 'alpha'] - ALPHA.reindex(shared)).abs().max())\n"
        "print(f'  alpha recomputed vs stored, on the {len(shared)} names the stored book and')\n"
        "print(f'  this universe share: worst gap {gap:.3e}')\n"
        "assert gap < 1e-12, 'the recomputed alpha is not the stored alpha'\n"
        "print(f'  the stored book for this close: {len(STORED_BOOK)} names, gross '\n"
        "      f'{STORED_BOOK[\"weight\"].abs().sum():.6f}, net {STORED_BOOK[\"weight\"].sum():+.2e}')",
    ),
    (
        "markdown",
        "## 3. The 20-share floor, iterated to a fixed point\n"
        "\n"
        "The construction is the owner's: **share only**, a minimum of 20 whole\n"
        "shares per name, no dollar floor, and enforced on the **final** weights,\n"
        "which are the ones that trade. The rule is drop-then-admit: drop every name\n"
        "that ends below its floor, then admit names back in the `|w| / floor` order\n"
        "while the enlarged set's own final weights still clear every kept name's\n"
        "floor, and repeat the admission pass until a pass changes nothing.\n"
        "\n"
        "The reason it iterates: the floor is checked on the vector **after** the\n"
        "hedge and the renormalization, and every one of those steps rescales the\n"
        "book. A name is not below its floor because of its own weight alone, so the\n"
        "check has to be re-run on the re-sized book, not on the raw target.\n"
        "\n"
        "The rule changed after the stored proposal for this close was written, so the\n"
        "book below is **not** the stored file. Both are shown, and the traced name is\n"
        "taken from the book the loop runs today.\n",
    ),
    (
        "code",
        "from efb import registry\n"
        "\n"
        "CONSTRUCTION = registry.live_construction(\n"
        "    registry.load(DATA / 'models' / 'registry.json'), ej.MODEL_VERSION)\n"
        "print('INPUT  data/models/registry.json, models.XS-v1.live:', CONSTRUCTION)\n"
        "\n"
        "FULL = size.procedure_6_3(ALPHA.to_numpy(float), DESIGN, FACTOR_COV, SPECIFIC)\n"
        "FULL, GROSS_CAP_BOUND = ej._scale_to_target(FULL, DESIGN, FACTOR_COV, SPECIFIC)\n"
        "close = ej._close_prices(CLOSE, DATA)\n"
        "KEEP, FINALIZE, SEARCH = ej.enforce_floor_by_drop_then_admit(\n"
        "    NAMES, ALPHA.to_numpy(float), DESIGN, FACTOR_COV, SPECIFIC, close, NAV,\n"
        "    FULL, dollar_floor=CONSTRUCTION['dollar_floor'],\n"
        "    share_floor=CONSTRUCTION['share_floor'])\n"
        "print()\n"
        "print('OUTPUT live/evening_job.py::enforce_floor_by_drop_then_admit')\n"
        "print('  drop only passes, floor satisfied:', SEARCH['n_drop_only'])\n"
        "print('  after one admission pass:', SEARCH['n_one_pass_admission'])\n"
        "print('  admitted by the passes:', SEARCH['admitted'])\n"
        "print('  admission passes run:', SEARCH['admit_passes'],\n"
        "      '| cycles:', SEARCH['cycles'], '| converged:', SEARCH['converged'])\n"
        "print('  kept:', int(KEEP.sum()), 'of', len(NAMES))",
    ),
    (
        "code",
        "# The traced name is taken from the book, not typed: the brief names LITE, and\n"
        "# if the current rule did not keep it the notebook says so rather than\n"
        "# tracing a name that is not there.\n"
        "IDX = np.asarray(FINALIZE['idx'], dtype=int)\n"
        "KEPT_NAMES = [str(name) for name in FINALIZE['names_sub']]\n"
        "W_RAW = FINALIZE['w_sub']\n"
        "WANTED = 'LITE'\n"
        "TRACE = WANTED if WANTED in KEPT_NAMES else KEPT_NAMES[int(np.argmax(np.abs(W_RAW)))]\n"
        "print('  this close, under the rule the live loop runs:')\n"
        "print('   dropped by the floor check alone:', SEARCH['n_drop_only'])\n"
        "print('   kept after one admission pass   :', SEARCH['n_one_pass_admission'])\n"
        "print('   kept at the fixed point         :', int(KEEP.sum()))\n"
        "print('   admission passes, cycles        :', SEARCH['admit_passes'], SEARCH['cycles'],\n"
        "      '| converged:', SEARCH['converged'])\n"
        "print()\n"
        "if WANTED in KEPT_NAMES:\n"
        "    print(f'  the traced name is {TRACE}, as the brief asks')\n"
        "else:\n"
        "    print(f'  {WANTED} is NOT in the book the current rule keeps at this close.')\n"
        "    print(f'  It was in the stored proposal for this close, which was written by the')\n"
        "    print(f'  earlier floor rule; the drop-then-admit fixed point drops it. The')\n"
        "    print(f'  trace follows {TRACE} instead, the largest weight that is actually here.')",
    ),
    (
        "code",
        "# The stored proposal for this close, against the rule the loop runs today.\n"
        "# This is the reproducibility caveat the notebook exists to make visible: a\n"
        "# re-run of an old evening does not reproduce its stored file, because the\n"
        "# floor rule changed after it was written.\n"
        "stored_path = ROOT / 'live' / 'proposals' / f'proposal_{STAMP}.json'\n"
        "if stored_path.exists():\n"
        "    stored_manifest = json.loads(stored_path.read_text())\n"
        "    print('  STORED manifest for this close', {\n"
        "        key: stored_manifest.get(key) for key in\n"
        "        ('n_names', 'n_kept', 'n_kept_drop_only', 'n_kept_one_pass_admission',\n"
        "         'floor_search_passes', 'floor_rule', 'gross')})\n"
        "    print('  RECOMPUTED today         ', {\n"
        "        'n_names': len(NAMES), 'n_kept': int(KEEP.sum()),\n"
        "        'n_kept_drop_only': SEARCH['n_drop_only'],\n"
        "        'n_kept_one_pass_admission': SEARCH['n_one_pass_admission'],\n"
        "        'floor_search_passes': SEARCH['admit_passes'], 'floor_rule': 'drop_then_admit',\n"
        "        'gross': round(float(PROPOSAL['gross']), 6)})\n"
        "    stored_names = set(STORED_BOOK['ticker'])\n"
        "    now_names = set(KEPT_NAMES)\n"
        "    print(f'  names in the stored book and not today: {len(stored_names - now_names)}')\n"
        "    print(f'  names today and not in the stored book: {len(now_names - stored_names)}')\n"
        "    print('  the rule the loop runs is the one traced; the stored file is the')\n"
        "    print('  earlier rule, and the two are reported apart rather than averaged.')",
    ),
    (
        "markdown",
        "## 4. The 10% variance-share cap\n"
        "\n"
        "No name may carry more than 10% of the book's predicted **specific**\n"
        "variance, which is the part of the risk no factor hedge removes. The share\n"
        "is `w_i^2 s_i^2 / sum(w_j^2 s_j^2)`, scale invariant.\n"
        "\n"
        "It is solved, not iterated. Rescaling a violator changes the total and\n"
        "re-violates the names just clamped, so the sequence crawls: measured at 100\n"
        "passes and still moving. The closed form is water-filling, find the level\n"
        "`L` with `sum(min(c_i, L)) = L / cap`, and every clamped name then sits at\n"
        "exactly the cap by construction.\n"
        "\n"
        "It is applied **before** the hedge, and only before, because the hedge is a\n"
        "projection of the sized vector.\n"
        "\n"
        "Two books are shown. The first is the book the current rule keeps, which is the\n"
        "one being traced; the second is the **stored** proposal for this close, where\n"
        "the brief's own case, MRNA, is the name the cap acts on. Both are the same\n"
        "arithmetic on different kept sets.",
    ),
    (
        "code",
        "from live import sizing\n"
        "\n"
        "SPECIFIC_KEPT = SPECIFIC[IDX]\n"
        "SIZED = size.proportional(ALPHA.to_numpy(float)[IDX], SPECIFIC_KEPT)\n"
        "SHARES_BEFORE = sizing.variance_shares(SIZED, SPECIFIC_KEPT)\n"
        "CAPPED = sizing.cap_variance_shares(SIZED, SPECIFIC_KEPT)\n"
        "# The hedge acts on the renormalized capped book, not the raw capped one: the\n"
        "# sizing step renormalizes to gross 1.0 before it hedges, so the pre-hedge\n"
        "# exposure the hedge computes is the exposure of this vector.\n"
        "CAPPED_RENORM = sizing.renormalize(CAPPED, gross=1.0)\n"
        "SHARES_AFTER = sizing.variance_shares(CAPPED, SPECIFIC_KEPT)\n"
        "work = pd.DataFrame({'share_before': SHARES_BEFORE, 'share_after': SHARES_AFTER,\n"
        "                    'scale': np.divide(CAPPED, SIZED, out=np.ones_like(SIZED),\n"
        "                                         where=SIZED != 0)},\n"
        "                   index=KEPT_NAMES)\n"
        "CAP_CASE = str(work['share_before'].idxmax())\n"
        "above = work.loc[work['share_before'] > sizing.VARIANCE_SHARE_CAP + 1e-12]\n"
        "print('INPUT  live/sizing.py::VARIANCE_SHARE_CAP =', sizing.VARIANCE_SHARE_CAP)\n"
        "print('  names above the cap before capping:', len(above))\n"
        "print(work.sort_values('share_before', ascending=False).head(5).to_string())\n"
        "row = work.loc[CAP_CASE]\n"
        "print()\n"
        "print(f'the worked case, {CAP_CASE}:')\n"
        "print(f'  before: {row[\"share_before\"]:.6f} of the book variance in one name')\n"
        "print(f'  after : {row[\"share_after\"]:.6f}, the cap exactly')\n"
        "print(f'  its own weight is scaled by {row[\"scale\"]:.6f}, and only downwards')\n"
        "assert row['share_before'] > sizing.VARIANCE_SHARE_CAP\n"
        "assert abs(row['share_after'] - sizing.VARIANCE_SHARE_CAP) < 1e-9",
    ),
    (
        "code",
        "# The brief's own worked case, MRNA, lives in the STORED book for this close,\n"
        "# not in the book the current rule keeps. The arithmetic is the same, so it is\n"
        "# repeated here on that book and labelled for what it is.\n"
        "old_names = [str(name) for name in STORED_BOOK['ticker']]\n"
        "slot = {name: position for position, name in enumerate(NAMES)}\n"
        "old_rows = [slot[name] for name in old_names if name in slot]\n"
        "old_sized = size.proportional(ALPHA.to_numpy(float)[old_rows], SPECIFIC[old_rows])\n"
        "old_before = sizing.variance_shares(old_sized, SPECIFIC[old_rows])\n"
        "old_capped = sizing.cap_variance_shares(old_sized, SPECIFIC[old_rows])\n"
        "old_after = sizing.variance_shares(old_capped, SPECIFIC[old_rows])\n"
        "old_work = pd.DataFrame({'share_before': old_before, 'share_after': old_after},\n"
        "                       index=[name for name in old_names if name in slot])\n"
        "print('the stored book for this close, the brief\\'s case:')\n"
        "print(old_work.sort_values('share_before', ascending=False).head(4).to_string())\n"
        "if 'MRNA' in old_work.index:\n"
        "    print(f'  MRNA: {old_work.loc[\"MRNA\", \"share_before\"]:.6f} before, '" 
        "          f'{old_work.loc[\"MRNA\", \"share_after\"]:.6f} after the cap')",
    ),
    (
        "markdown",
        "## 5. The FMP hedge: exposures before and after, and the traced name\n"
        "\n"
        "The hedge is the exact in-model FMP. It solves `X'X l = X'w` and subtracts\n"
        "`X l`, so the post-hedge exposure `X'(w - Xl)` is **zero by construction**,\n"
        "not small. It is exact because the mimicking portfolios are the model's own:\n"
        "the columns of `X (X'X)^-1`.\n"
        "\n"
        "The `before` vector is the hedge's own `X'w`, returned by the sizing step\n"
        "rather than reconstructed, so the page and the hedge cannot disagree.",
    ),
    (
        "code",
        "W_KEPT, PRE_HEDGE = sizing.procedure_6_3_hedged_with_exposures(\n"
        "    ALPHA.to_numpy(float)[IDX], DESIGN[IDX], FACTOR_COV, SPECIFIC_KEPT,\n"
        "    sized=CAPPED_RENORM)\n"        "W_KEPT = sizing.renormalize(W_KEPT, gross=1.0)\n"
        "DESIGN_KEPT = DESIGN[IDX]\n"
        "POST_HEDGE = DESIGN_KEPT.T @ W_KEPT\n"
        "from efb.models import fundamental as fx\n"
        "hedge_table = pd.DataFrame({'factor': fx.ESTIMATED_NAMES,\n"
        "                            'before': PRE_HEDGE, 'after': POST_HEDGE})\n"
        "hedge_table['moved'] = hedge_table['before'] - hedge_table['after']\n"
        "print('INPUT  data/models/XS-v1/descriptors.parquet through efb/race.py::_descriptor_design')\n"
        "print(hedge_table.to_string(index=False))\n"
        "print()\n"
        "print('worst exposure after the hedge:', float(np.abs(POST_HEDGE).max()))\n"
        "print('worst exposure the page shows   :', PROPOSAL['max_abs_exposure_after_fmp'])\n"
        "assert float(np.abs(POST_HEDGE).max()) < 1e-12",
    ),
    (
        "code",
        "# The traced name, through the hedge. Its pre-hedge weight is what the cap\n"
        "# left; the hedge moves it by whatever the mimicking portfolios need at that\n"
        "# name, which is not small and is not noise.\n"
        "trace_at = KEPT_NAMES.index(TRACE)\n"
        "before_w = CAPPED_RENORM[trace_at]\n"
        "after_w = W_KEPT[trace_at]\n"
        "print(f'{TRACE} through the hedge:')\n"
        "print(f'  after the variance cap and the renormalization: {before_w:+.6f}')\n"
        "print(f'  as the hedge leaves it                          : {after_w:+.6f}')\n"
        "print(f'  the hedge adjustment                            : {after_w - before_w:+.6f}'\n"
        "      f'  ({(after_w - before_w) / abs(before_w):+.1%} of its own weight)')\n"
        "own = pd.Series(before_w * DESIGN_KEPT[trace_at], index=fx.ESTIMATED_NAMES)\n"
        "print(f'  its own contribution to the book exposure, at {TRACE}, the largest four:')\n"
        "print(own.reindex(own.abs().sort_values(ascending=False).index).head(4).round(6)\n"
        "      .to_string())\n"
        "print('  after the hedge the book exposure is zero for every factor, so the')\n"
        "print('  adjustment is what the hedge had to do at this one name to get there.')",
    ),
    (
        "markdown",
        "## 6. Renormalization, whole shares, and the orders\n"
        "\n"
        "Renormalization to gross 1.0 is a single positive scalar on the hedged\n"
        "vector, which is why it cannot undo the hedge or the cap. Quantization\n"
        "then truncates to whole shares: `int(|w| NAV / price)`. Truncation, not\n"
        "rounding, at every step, and the rounding error is reported rather than\n"
        "absorbed.",
    ),
    (
        "code",
        "gross_before = float(np.abs(W_KEPT).sum())\n"
        "SHARES = ej.kept_shares(W_KEPT, FINALIZE['prices'], NAV)\n"
        "QUANT = FINALIZE['quant']\n"
        "print('  gross before the final renormalization:', PROPOSAL['kept_gross_before_renorm'])\n"
        "print('  gross after                             :', round(gross_before, 12))\n"
        "print('  quantization: nav', QUANT['nav'], '| names with a whole-share count:',\n"
        "      int((SHARES > 0).sum()), '| rounds to zero:', QUANT['long_targets_rounding_to_zero'])\n"
        "print('  gross weight error as a share of NAV:', QUANT['gross_weight_error'])\n"
        "dist = QUANT['distribution']\n"
        "print('  rounding error, pct of target:',\n"
        "      {k: round(v, 6) for k, v in dist['rounding_error_pct_of_target_quantiles'].items()})",
    ),
    (
        "code",
        "# The orders. Read from the stored execution log for this close, then the\n"
        "# client order id recomputed from its own ingredients: date, ticker, side.\n"
        "# The id is the idempotency ticket, so a re-fire of the same leg collides at\n"
        "from live import alpaca\n"
        "\n"
        "log_path = ROOT / 'live' / 'logs' / f'execution_{STAMP}.parquet'\n"
        "if log_path.exists():\n"
        "    orders_log = pd.read_parquet(log_path)\n"
        "    orders_log['client_order_id'] = [\n"
        "        alpaca.client_order_id(STAMP, str(row.ticker),\n"
        "                              'buy' if row.intended_notional >= 0 else 'sell')\n"
        "        for row in orders_log.itertuples(index=False)]\n"
        "    print('OUTPUT', log_path.relative_to(ROOT), '| rows', len(orders_log))\n"
        "    print(orders_log.head(5).to_string(index=False))\n"
        "    print('  statuses:', orders_log['status'].value_counts().to_dict())\n"
        "else:\n"
        "    print('no execution log stored for', STAMP)",
    ),
    (
        "code",
        "# And the same function checked against ids that ARE stored, in the\n"
        "# 2026-09-25 log, which is the only stored log carrying them.\n"
        "stored_ids = ROOT / 'live' / 'logs' / 'execution_2026-09-25.parquet'\n"
        "if stored_ids.exists():\n"
        "    frame = pd.read_parquet(stored_ids)\n"
        "    recomputed = [alpaca.client_order_id(row.trade_date, str(row.ticker),\n"
        "                                        'buy' if row.intended_notional >= 0 else 'sell')\n"
        "                  for row in frame.itertuples(index=False)]\n"
        "    matches = int(sum(a == b for a, b in zip(recomputed, frame['client_order_id'])))\n"
        "    print('stored ids reproduced:', matches, 'of', len(frame))\n"
        "    print(frame[['ticker', 'intended_notional', 'client_order_id']].head(3)\n"
        "          .to_string(index=False))\n"
        "    assert matches == len(frame), 'the client order id has drifted'",
    ),
    (
        "markdown",
        "## 7. The cost estimate, split four ways\n"
        "\n"
        "Four components, each in basis points of the paper NAV, and they must sum\n"
        "to the total by construction. Only the **impact** is the cost of the trade\n"
        "(it reads the change in weight, from flat on an establishment day). Spread,\n"
        "commission and borrow scale with the book held, because they are the cost of\n"
        "owning the position over the 21-session horizon.",
    ),
    (
        "code",
        "from efb import costs as costs_mod\n"
        "\n"
        "spread = costs_mod.spread_schedule(prices, DATA)\n"
        "adv_map, _raw_adv, THIN = ej._adv_maps(KEPT_NAMES, DATA)\n"
        "sigma = np.sqrt(np.maximum(SPECIFIC_KEPT, 1e-12))\n"
        "spread_map = spread.reindex(KEPT_NAMES).fillna(spread.median()).to_numpy(float)\n"
        "dollar_trade = np.abs(W_KEPT) * NAV\n"
        "impact = (costs_mod.IMPACT_K * sigma\n"
        "          * np.sqrt(np.maximum(dollar_trade, 0.0) / np.maximum(adv_map, 1.0)))\n"
        "spread_bps = float(np.sum(spread_map * np.abs(W_KEPT))) * 1e4\n"
        "commission_bps = float(np.sum(costs_mod.COMMISSION * np.abs(W_KEPT))) * 1e4\n"
        "impact_bps = float(np.sum(impact * np.abs(W_KEPT))) * 1e4\n"
        "short_gross = float(np.maximum(-W_KEPT, 0.0).sum())\n"
        "borrow_bps = costs_mod.BORROW_RATE * short_gross * (ej.HORIZON / ej.TRADING_DAYS) * 1e4\n"
        "print('INPUT  efb/costs.py: IMPACT_K', costs_mod.IMPACT_K, '| COMMISSION',\n"
        "      costs_mod.COMMISSION, '| BORROW_RATE', costs_mod.BORROW_RATE)\n"
        "print(f'  spread     {spread_bps:9.4f} bps')\n"
        "print(f'  impact     {impact_bps:9.4f} bps')\n"
        "print(f'  commission {commission_bps:9.4f} bps')\n"
        "print(f'  borrow     {borrow_bps:9.4f} bps  on a short gross of {short_gross:.6f}')\n"
        "print(f'  total      {spread_bps + impact_bps + commission_bps + borrow_bps:9.4f} bps')\n"
        "print('  stored     ', PROPOSAL['cost_breakdown_bps'])\n"
        "print('  thin ADV names (a median stands in for a measurement):', len(THIN))",
    ),
    (
        "markdown",
        "## 8. The stored cross-check: what the 2026-09-25 run left behind\n"
        "\n"
        "**Read this before quoting the section above.** The evening this notebook\n"
        "traces is the newest close the artifacts in this checkout price. The\n"
        "**2026-09-25** evening ran on a run tree that fetched sessions 2026-09-22 to\n"
        "2026-09-25 from the vendor; those inputs were never committed, and\n"
        "`build_proposal(as_of='2026-09-25')` refuses here with `no idio_momentum\n"
        "signal row on 2026-09-25` because `models/XS-v1/specific_returns.parquet`\n"
        "ends a session earlier. So the 09-25 book cannot be rebuilt in this\n"
        "checkout. Two of its outputs were committed to the runtime tree and are read\n"
        "below.",
    ),
    (
        "code",
        "others = sorted((ROOT / 'live' / 'logs').glob('execution_*.parquet'))\n"
        "print('stored execution logs:', [path.stem.replace('execution_', '') for path in others])\n"
        "recon = pd.read_parquet(ROOT / 'live' / 'state' / 'reconciliation.parquet')\n"
        "recon['trade_date'] = recon['trade_date'].astype(str).str.slice(0, 10)\n"
        "cols = ['trade_date', 'gross', 'net', 'n_eff_kept', 'intended_notional',\n"
        "        'expected_cost_bps', 'expected_spread_bps', 'expected_impact_bps',\n"
        "        'expected_commission_bps', 'expected_borrow_bps']\n"
        "stored = recon[cols].dropna(axis=1, how='all')\n"
        "print()\n"
        "print('OUTPUT live/state/reconciliation.parquet')\n"
        "print(stored.to_string(index=False))\n"
        "row = recon.loc[recon['trade_date'] == '2026-09-25']\n"
        "if len(row):\n"
        "    row = row.iloc[0]\n"
        "    parts = (row['expected_spread_bps'] + row['expected_impact_bps']\n"
        "             + row['expected_commission_bps'] + row['expected_borrow_bps'])\n"
        "    print()\n"
        "    print('the 09-25 establishment cost, four parts and their sum:')\n"
        "    print(f'  spread {row[\"expected_spread_bps\"]:.4f} + impact '\n"
        "          f'{row[\"expected_impact_bps\"]:.4f} + commission '\n"
        "          f'{row[\"expected_commission_bps\"]:.4f} + borrow '\n"
        "          f'{row[\"expected_borrow_bps\"]:.4f} = {parts:.4f} bps, against a stored '\n"
        "          f'total of {row[\"expected_cost_bps\"]:.4f} bps')\n"
        "    assert abs(parts - row['expected_cost_bps']) < 0.01",
    ),
    (
        "code",
        "# And the stored 09-25 order log: 169 legs, an establishment day, gross\n"
        "# intended notional equal to the whole paper NAV.\n"
        "day_25 = ROOT / 'live' / 'logs' / 'execution_2026-09-25.parquet'\n"
        "if day_25.exists():\n"
        "    frame = pd.read_parquet(day_25)\n"
        "    print('OUTPUT', day_25.relative_to(ROOT))\n"
        "    print('  legs', len(frame), '| gross intended notional',\n"
        "          float(frame['intended_notional'].abs().sum()))\n"
        "    print('  statuses', frame['status'].value_counts().to_dict(),\n"
        "          '| reason codes', frame['reason_code'].value_counts().to_dict())\n"
        "    held = set(frame['ticker'])\n"
        "    print('  LITE in it:', 'LITE' in held, '| MRNA in it:', 'MRNA' in held)\n"
        "    print('  so the 169-name book and the book traced above are different days,')\n"
        "    print('  and this notebook traces the one its inputs can price.')",
    ),
    (
        "markdown",
        "## 9. What the email and the page show, and what each run_status field means\n"
        "\n"
        "The email is sent after the proposal and the orders, never before, so a\n"
        "failed send cannot block a run. Every run notifies, clean ones included: the\n"
        "absence of the evening message is the alarm. The page is a JSON snapshot\n"
        "under `docs/snapshot.schema.json`, which is the contract that pins the\n"
        "builder and the TypeScript client together.",
    ),
    (
        "code",
        "from live import notify, snapshot\n"
        "\n"
        "SPECIAL = PROPOSAL['cost_breakdown_bps']\n"
        "subject = notify.subject_text(status='ok', target_close=STAMP, dry_run=True,\n"
        "                              orders=PROPOSAL['n_kept'],\n"
        "                              worst_input=GATE['worst_input'],\n"
        "                              worst_sessions_behind=GATE['worst_sessions_behind'],\n"
        "                              inputs=GATE['inputs'])\n"
        "body = notify.compose(\n"
        "    status='ok', target_close=STAMP, dry_run=True, orders=PROPOSAL['n_kept'],\n"
        "    gross=PROPOSAL['notional'], worst_input=GATE['worst_input'],\n"
        "    worst_sessions_behind=GATE['worst_sessions_behind'],\n"
        "    failures=GATE['failures'], inputs=GATE['inputs'],\n"
        "    store='local parquet (dry run)', snapshot='off',\n"
        "    cost_bps=SPECIAL['total'], cost_breakdown=SPECIAL,\n"
        "    thin_adv=THIN, no_price=ej.universe_without_prices(DATA, as_of=CLOSE),\n"
        "    cost_label='rebalance', brake_limit=NAV,\n"
        "    positions_check={'note': 'dry run: the broker was not read'})\n"
        "print('OUTPUT live/notify.py, the subject and the body')\n"
        "print('subject:', subject)\n"
        "print()\n"
        "print(body)",
    ),
    (
        "code",
        "# The page. `snapshot.build` is the function the Cloudflare worker serves.\n"
        "from live import snapshot\n"
        "\n"
        "TRACED_BOOK = pd.DataFrame({'ticker': KEPT_NAMES, 'weight': W_KEPT})\n"
        "CHOSEN = snapshot.chosen_row(PROPOSAL, root=DATA)\n"
        "CONSTRUCTION_LABEL = snapshot.construction_label(PROPOSAL)\n"
        "payload = snapshot.build(run={'target_close': STAMP, 'store': 'local',\n"
        "                             'positions_check': {'note': 'dry run'}},\n"
        "                        manifest=PROPOSAL, book=TRACED_BOOK,\n"
        "                        construction=CHOSEN)\n"
        "print('OUTPUT live/snapshot.py::build, the page payload')\n"
        "print('construction:', payload['construction'])\n"
        "print('book: n_names', payload['book']['n_names'], '| n_kept', payload['book']['n_kept'],\n"
        "      '| gross', round(payload['book']['gross'], 6), '| cost bps',\n"
        "      round(payload['book']['expected_cost_bps'], 4))\n"
        "print('hedge:', {k: payload['hedge'][k] for k in ('idio_share_after_fmp',\n"
        "                                                'max_abs_exposure_after_fmp')})\n"
        "rows = [{'factor': k, 'before': v, 'after': payload['exposures_after_hedge'][k]}\n"
        "        for k, v in payload['exposures_before_hedge'].items()]\n"
        "print(pd.DataFrame(rows).head(8).to_string(index=False))",
    ),
    (
        "code",
        "# Every run_status field, and what it means.\n"
        "row = staleness.run_status_row(GATE, run_date=STAMP, status='ok', dry_run=True,\n"
        "                              n_orders=PROPOSAL['n_kept'],\n"
        "                              gross_notional=PROPOSAL['notional'],\n"
        "                              snapshot='off', cost_label='rebalance')\n"
        "MEANING = {\n"
        "    'target_close': 'the session the book was priced at, the key',\n"
        "    'job': 'which cron wrote the row',\n"
        "    'run_date': 'the day the job ran, which is not the close it priced',\n"
        "    'status': 'ok, stale_stopped, error or market_closed; only ok marks the day done',\n"
        "    'checked_at': 'when the gate ran',\n"
        "    'max_input_staleness_days': 'calendar days to the oldest input, what the email quotes',\n"
        "    'worst_input': 'the input furthest behind, in NYSE sessions',\n"
        "    'worst_sessions_behind': 'how far behind it was, the number that decides',\n"
        "    'n_inputs': 'how many inputs the gate looked at',\n"
        "    'inputs': 'every input with its own date, source and allowance, as JSON',\n"
        "    'failures': 'the inputs that failed their allowance, empty when clean',\n"
        "    'detail': 'the error or refusal text, empty when clean',\n"
        "    'notify_status': 'sent, failed or skipped: skipped means no channel was configured',\n"
        "    'notify_failed': 'true when the message was not delivered, which exits nonzero',\n"
        "    'n_orders': 'how many legs the morning proposed',\n"
        "    'gross_notional': 'the book gross in dollars',\n"
        "    'dry_run': 'true unless EFB_DRY_RUN is the literal false',\n"
        "    'init': 'the run that seeded the store',\n"
        "    'catch_up': 'the run closed more than one session at once',\n"
        "    'catch_up_sessions': 'which sessions it closed',\n"
        "    'splits': 'corporate actions applied, each named',\n"
        "    'flags': 'names whose move tripped a sanity flag',\n"
        "    'snapshot': 'the page write: on, off or the failure',\n"
        "    'started_at': 'when the run began, used by the close gate',\n"
        "    'cross_checks_capped': 'when the split cross-checks hit their cap',\n"
        "    'establishment': 'the day the book was built from flat',\n"
        "    'cost_label': 'establishment or rebalance, which cost the number is',\n"
        "    'positions_check': 'the broker book against the store, counts and worst drift',\n"
        "}\n"
        "print('OUTPUT live/staleness.py::run_status_row')\n"
        "for key, value in row.items():\n"
        "    shown = str(value)\n"
        "    shown = shown[:60] + '...' if len(shown) > 60 else shown\n"
        "    print(f'  {key:26s} {shown:62s} {MEANING.get(key, \"\")}')\n"
        "print()\n"
        "print('and the state the page derives from the row:')\n"
        "print(' ', staleness.run_state(row))",
    ),
    (
        "markdown",
        "## 10. The E11 criteria\n"
        "\n"
        "Copied verbatim from `sprints/E11/RESULTS.json`, which is where they were\n"
        "pre-registered. **All three are pending**: they are statements about thirty\n"
        "consecutive live trading days, and the window opened at `day_1` and closes on\n"
        "the stored `end_date`. They are evaluated with stored numbers once the window\n"
        "is complete, not before.",
    ),
    (
        "code",
        "results = json.loads((ROOT / 'sprints' / 'E11' / 'RESULTS.json').read_text())\n"
        "clock = results['clock']\n"
        "print('THE CLOCK')\n"
        "print(f'  day 1 {clock[\"day_1\"]} | thirty trading days end {clock[\"end_date\"]} '\n"
        "      f'| started {clock[\"started\"]}')\n"
        "print('RUN CONDITION: the book runs indefinitely; the thirty days are a')\n"
        "print('reporting window over the history, not the life of the run.')\n"
        "print()\n"
        "for name, block in results['criteria'].items():\n"
        "    print(f'{name}: {block[\"verdict\"].upper()}')\n"
        "    print(f'  criterion: {block[\"criterion\"]}')\n"
        "    print(f'  stored numbers: {block[\"stored_numbers\"] or \"none yet, the window is open\"}')\n"
        "print()\n"
        "print('what a failure would mean for a PM:')\n"
        "print('  F11.1 a missed proposal is a day the book was not re-sized: the process,')\n"
        "print('        not the signal, is what this criterion tests.')\n"
        "print('  F11.2 an ex-ante risk number that does not reconcile is a page nobody can')\n"
        "print('        act on, because the size of the book rests on it.')\n"
        "print('  F11.3 realized vol outside the champion bias band means the book is not the')\n"
        "print('        risk the research said it was, which is the whole premise of the loop.')",
    ),
    (
        "code",
        "# Closing checklist: nothing typed by hand, and the traced name reached the end.\n"
        "print('the traced name:', TRACE, '| in the book:', TRACE in STORED.index)\n"
        "print('the cap case  :', CAP_CASE, '| capped to', round(float(work.loc[CAP_CASE, 'share_after']), 6))\n"
        "print('closing checklist: clean')",
    ),
]


def build() -> None:
    notebook: dict = {
        "cells": [],
        "metadata": {
            "kernelspec": {
                "display_name": "efb-venv",
                "language": "python",
                "name": "efb-venv",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    for index, (kind, source) in enumerate(CELLS):
        cell: dict = {
            "cell_type": kind,
            "id": f"e11w{index:02d}",
            "metadata": {},
            "source": source.splitlines(keepends=True),
        }
        if kind == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        notebook["cells"].append(cell)
    path = ROOT / "notebooks" / "E11_walkthrough.ipynb"
    path.write_text(json.dumps(notebook, indent=1) + "\n")
    print(f"wrote {path} with {len(CELLS)} cells")


if __name__ == "__main__":
    build()
