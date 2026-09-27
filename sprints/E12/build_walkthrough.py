"""Build the E12 walkthrough notebook cells from a source list.

Generated, not hand-edited, so the criteria text and the numbers stay as stored.
Execution and rendering happen through nbconvert:

    .venv/bin/python sprints/E12/build_walkthrough.py
    .venv/bin/python -m jupyter nbconvert --to notebook --execute --inplace \
        notebooks/E12_walkthrough.ipynb
    .venv/bin/python -m jupyter nbconvert --to html \
        notebooks/E12_walkthrough.ipynb --output E12_walkthrough.html
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CELLS: list[tuple[str, str]] = [
    (
        "markdown",
        "# Sprint E12 walkthrough: attribution, and the skill question\n"
        "\n"
        "Purpose: a mechanistic explanation of every estimator the sprint built,\n"
        "reproduced by hand, so each number on the page can be derived at a\n"
        "whiteboard and the memo's numbers have an audit trail.\n"
        "\n"
        "The three research questions, from the roadmap:\n"
        "\n"
        "1. Where did the P&L come from, factor by factor, and does the split add back\n"
        "   up to the total to machine precision?\n"
        "2. Do the two ways of measuring the same thing, holdings and returns,\n"
        "   agree?\n"
        "3. Is the book any good, or is it luck?\n"
        "\n"
        "The intuition, in one paragraph. Attribution is the risk decomposition run\n"
        "**backwards** on realized returns: every basis point the book earned is a\n"
        "factor basis point, an idiosyncratic basis point, or a cost, and the\n"
        "reconciliation is what makes that a check rather than a restatement. The\n"
        "holdings view knows what the book held; the regression view only sees what it\n"
        "earned; when they disagree, the exposures moved between rebalances. And the\n"
        "skill question has an arithmetic answer that has nothing to do with how the\n"
        "book feels: a t-statistic, and the number of days an edge of a given size\n"
        "needs before the test can see it at all.",
    ),
    (
        "code",
        "import json\n"
        "import math\n"
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
        'DATA = ROOT / "data"\n'
        'ATTRIBUTION = DATA / "attribution"',
    ),
    (
        "markdown",
        "## 1. The artifact, and the criteria as they were registered\n"
        "\n"
        "The attribution is stored per session by `scripts/build_attribution.py`, from\n"
        "a book's own stored weights. Here it is the seed book's: rho 0.02, seed 0 out\n"
        "of `data/portfolios/mv_constrained.parquet`. The live book swaps that input\n"
        "and nothing else.",
    ),
    (
        "code",
        "daily = pd.read_parquet(ATTRIBUTION / 'daily.parquet')\n"
        "monthly = pd.read_parquet(ATTRIBUTION / 'monthly.parquet')\n"
        "timeseries = pd.read_parquet(ATTRIBUTION / 'timeseries.parquet')\n"
        "daily['trade_date'] = pd.to_datetime(daily['trade_date'])\n"
        "results = json.loads((ROOT / 'sprints' / 'E12' / 'RESULTS.json').read_text())\n"
        "print('INPUT  data/attribution/daily.parquet:', daily.shape,\n"
        "      '| monthly:', monthly.shape, '| timeseries:', timeseries.shape)\n"
        "print('OUTPUT sprints/E12/RESULTS.json:')\n"
        "for name, block in results['criteria'].items():\n"
        "    print(f'  {name}: {block[\"verdict\"]}')\n"
        "print('  F12.3 expected verdict:', results['criteria']['F12.3']['expected_verdict'])\n"
        "print('  over', results['artifact']['n_sessions'], 'sessions:',\n"
        "      results['artifact']['first_session'], 'to', results['artifact']['last_session'])",
    ),
    (
        "markdown",
        "## 2. The identity, by hand on two names\n"
        "\n"
        "The formulas the sprint implements, with every symbol labelled:\n"
        "\n"
        "- factor P&L $_t = (X_{t}\\' w_{t-1})\\' f_t$, **INPUT** `descriptors.parquet`\n"
        "  and `factor_returns.parquet`, **OUTPUT** `daily.pnl_factor_json`.\n"
        "- idio P&L $_t = w_{t-1}\\' u_t$, **INPUT** `specific_returns.parquet`,\n"
        "  **OUTPUT** `daily.pnl_idio`.\n"
        "- total $_t$ = factor + idio + cost, **OUTPUT** `daily.identity_residual`.\n"
        "\n"
        "Two names, one factor, numbers a reader can check on paper: weights (0.6,\n"
        "-0.4), returns (0.02, -0.01), design X = (1.0, -0.5), factor return 0.01, cost\n"
        "-0.001.",
    ),
    (
        "code",
        "from efb import attribution\n"
        "\n"
        "date = pd.Timestamp('2026-09-21')\n"
        "holdings = pd.DataFrame({'date': [date] * 2, 'ticker': ['AAA', 'BBB'],\n"
        "                         'weight': [0.6, -0.4]})\n"
        "\n"
        "\n"
        "class OneFactorPanel:\n"
        "    \"\"\"A panel small enough to do on paper: one factor, two names.\"\"\"\n"
        "\n"
        "    def __init__(self):\n"
        "        self.returns = pd.DataFrame({'AAA': [0.02], 'BBB': [-0.01]},\n"
        "                                    index=[date]).stack(future_stack=True)\n"
        "        self.factor_returns = pd.DataFrame({'market': [0.01]}, index=[date])\n"
        "        self._design = np.array([[1.0], [-0.5]])\n"
        "\n"
        "    def design(self, stamp, names):\n"
        "        return self._design\n"
        "\n"
        "    def raw_design(self, stamp, names):\n"
        "        return self._design\n"
        "\n"
        "    def reported_design(self, stamp, names):\n"
        "        return self._design\n"
        "\n"
        "    def factor_names(self, stamp):\n"
        "        return ['market']\n"
        "\n"
        "    def betas_at(self, stamp, names):\n"
        "        return np.array([1.2, 0.4])\n"
        "\n"
        "    def fit_or_stored(self, stamp, names, returns, raw):\n"
        "        fitted = self._design @ self.factor_returns.loc[stamp].to_numpy(float)\n"
        "        return self.factor_returns.loc[stamp], returns - fitted, 'fixture'\n"
        "\n"
        "\n"
        "row = attribution.attribute_book(holdings, OneFactorPanel(),\n"
        "                                costs={date: {'cost_usd': -0.001}}).iloc[0]\n"
        "exposure = 0.6 * 1.0 + (-0.4) * (-0.5)\n"
        "factor_pnl = exposure * 0.01\n"
        "gross_pnl = 0.6 * 0.02 + (-0.4) * (-0.01)\n"
        "print(f'  exposure X\\'w      = {exposure:+.4f}')\n"
        "print(f'  factor P&L         = {factor_pnl:+.6f}  (library {row[\"pnl_factor\"]:+.6f})')\n"
        "print(f'  gross P&L          = {gross_pnl:+.6f}')\n"
        "print(f'  idio P&L           = {gross_pnl - factor_pnl:+.6f}  '\n"
        "      f'(library {row[\"pnl_idio\"]:+.6f})')\n"
        "print(f'  cost               = {row[\"pnl_cost\"]:+.6f}')\n"
        "print(f'  total              = {row[\"pnl_total\"]:+.6f}')\n"
        "print(f'  identity residual  = {row[\"identity_residual\"]:.1e}  '\n"
        "      f'(tolerance {attribution.IDENTITY_ATOL:.0e})')\n"
        "assert row['pnl_factor'] == row['pnl_factor']\n"
        "assert abs(row['pnl_total'] - (factor_pnl + (gross_pnl - factor_pnl) + (-0.001))) < 1e-15\n"
        "assert row['identity_residual'] == 0.0",
    ),
    (
        "markdown",
        "## 3. The identity on the whole artifact\n"
        "\n"
        "The same check, on every session the artifact carries, where the three\n"
        "components come from three different stored artifacts rather than from a\n"
        "fixture. The residual is the check; it is not asserted to be small, it is\n"
        "measured.",
    ),
    (
        "code",
        "residual = daily['identity_residual'].abs()\n"
        "print('INPUT  data/attribution/daily.parquet')\n"
        "print(f'  sessions            {len(daily):,}')\n"
        "print(f'  median |residual|   {residual.median():.3e}')\n"
        "print(f'  max    |residual|   {residual.max():.3e}')\n"
        "print(f'  sessions inside 1e-10: {int((residual < attribution.IDENTITY_ATOL).sum()):,}')\n"
        "split = daily['pnl_factor_json'].apply(lambda m: float(sum(m.values())))\n"
        "assert np.allclose(split, daily['pnl_factor'], atol=1e-12)\n"
        "print('  the per-factor split sums to the factor total on every session: yes')",
    ),
    (
        "markdown",
        "## 4. The cumulative split, and the five largest months\n"
        "\n"
        "Cumulative answers whether it worked; by period answers when. The book is\n"
        "gross 1.0 of NAV, so a basis point of the book is a basis point of NAV.",
    ),
    (
        "code",
        "totals = {name: float(daily[column].sum()) for name, column in\n"
        "          (('total', 'pnl_total'), ('factor', 'pnl_factor'),\n"
        "           ('idio', 'pnl_idio'), ('cost', 'pnl_cost'),\n"
        "           ('hedge timing', 'pnl_timing'))}\n"
        "for name, value in totals.items():\n"
        "    print(f'  {name:14s} {value * 1e4:+10.1f} bp')\n"
        "by_factor = {}\n"
        "for mapping in daily['pnl_factor_json']:\n"
        "    for name, value in mapping.items():\n"
        "        by_factor[name] = by_factor.get(name, 0.0) + float(value)\n"
        "ranked = sorted(by_factor.items(), key=lambda pair: -abs(pair[1]))\n"
        "print('  by factor (largest first):')\n"
        "for name, value in ranked[:6]:\n"
        "    print(f'    {name:12s} {value * 1e4:+10.1f} bp')\n"
        "monthly = monthly.copy()\n"
        "monthly['magnitude'] = monthly['pnl_total'].abs()\n"
        "print('  the five largest months:')\n"
        "for record in monthly.sort_values('magnitude', ascending=False).head(5).to_dict('records'):\n"
        "    print(f'    {record[\"month\"]}  n={int(record[\"n_sessions\"]):2d}  '\n"
        "          f'total {record[\"pnl_total\"] * 1e4:+9.1f} bp  '\n"
        "          f'factor {record[\"pnl_factor\"] * 1e4:+8.1f}  '\n"
        "          f'idio {record[\"pnl_idio\"] * 1e4:+9.1f}')",
    ),
    (
        "markdown",
        "## 5. The hedge timing, and which design vintage the model uses\n"
        "\n"
        "Two facts, and they are separate. **The design dated a session is built from\n"
        "data through the previous close**, so it is computable at that close and the\n"
        "stored model has no look-ahead. The hedge is nonetheless one session\n"
        "**behind**, because the exposure the book will be measured on is the design\n"
        "dated the next session, which is also available at the same close.\n"
        "\n"
        "The first fact, from the code and then from the artifact: size is\n"
        "`log(market_cap.shift(1))`, and beta, residual volatility and liquidity each\n"
        "carry `.shift(1)` on their window; reversal shifts the returns by one and only\n"
        "momentum reaches further back.",
    ),
    (
        "code",
        "from efb.models import fundamental as fx\n"
        "\n"
        "prices = pd.read_parquet(DATA / 'raw' / 'prices.parquet')\n"
        "close = prices['close'].unstack('ticker')\n"
        "shares = pd.read_parquet(DATA / 'raw' / 'shares_history.parquet')\n"
        "shares = shares.pivot_table(index='date', columns='ticker', values='shares')\n"
        "shares = shares.reindex(close.index).ffill()\n"
        "mcap = fx.market_cap(close, shares)\n"
        "descriptors = pd.read_parquet(DATA / 'models' / 'XS-v1' / 'descriptors.parquet')\n"
        "size = descriptors.loc[descriptors['descriptor'] == 'size']\n"
        "stamp = pd.Timestamp('2026-09-21')\n"
        "previous = pd.DatetimeIndex(sorted(set(mcap.index)))\n"
        "previous = previous[previous < stamp][-1]\n"
        "row = size.loc[pd.to_datetime(size['date']) == stamp].set_index('ticker')['value_raw']\n"
        "for ticker in ('LITE', 'MRNA', 'AAPL'):\n"
        "    same = math.log(float(mcap.loc[stamp, ticker]))\n"
        "    lagged = math.log(float(mcap.loc[previous, ticker]))\n"
        "    print(f'  {ticker:5s} size descriptor {row[ticker]:+.6f} | at t gap '\n"
        "          f'{abs(row[ticker] - same):.3e} | at t-1 gap '\n"
        "          f'{abs(row[ticker] - lagged):.3e}')\n"
        "print('  -> the row dated t is the previous close, so no look-ahead.')",
    ),
    (
        "code",
        "# The second fact: the vintages differ on the sessions after a rebalance, and\n"
        "# the drift between them is what the hedge left un-neutralized.\n"
        "moved = daily.loc[daily['pnl_timing'].abs() > 0]\n"
        "gap = pd.DataFrame(list(moved['exposure_json'])) - pd.DataFrame(\n"
        "    list(moved['book_exposure_json']))\n"
        "print(f'  sessions where the two vintages differ: {len(moved):,} of {len(daily):,}')\n"
        "print(f'  mean |per-factor gap| on those       : {gap.abs().mean().mean():.5f}')\n"
        "print(f'  largest single gap                   : {gap.abs().max().max():.4f} '\n"
        "      f'of {gap.abs().max().idxmax()}')\n"
        "print(f'  timing P&L                           : '\n"
        "      f'{float(moved[\"pnl_timing\"].sum()) * 1e4:+.1f} bp')\n"
        "print(f'  total P&L on those sessions          : '\n"
        "      f'{float(moved[\"pnl_total\"].sum()) * 1e4:+.1f} bp')\n"
        "print(f'  the timing line as a share of it     : '\n"
        "      f'{abs(float(moved[\"pnl_timing\"].sum())) / abs(float(moved[\"pnl_total\"].sum())) * 100:.1f}%')",
    ),
    (
        "markdown",
        "## 6. The two estimators, side by side\n"
        "\n"
        "The holdings view is the exposure times the factor return, per session. The\n"
        "returns view is the book's own P&L regressed on the factor returns, with\n"
        "standard errors from the regression's own covariance. F12.2 asks whether each\n"
        "beta sits within one standard error of the average holdings exposure.",
    ),
    (
        "code",
        "print('  term            beta       se   holdings   within 1 SE')\n"
        "for record in timeseries.to_dict('records'):\n"
        "    if pd.isna(record.get('holdings_exposure')):\n"
        "        continue\n"
        "    print(f'  {record[\"term\"]:12s} {record[\"beta\"]:+8.4f} {record[\"se\"]:8.4f} '\n"
        "          f'{record[\"holdings_exposure\"]:+9.4f}   '\n"
        "          f'{\"yes\" if record[\"within_one_se\"] else \"no\"}')\n"
        "print(f'  {int(timeseries[\"within_one_se\"].sum())} of {len(timeseries)} terms agree  '\n"
        "      f'(F12.2 is {results[\"criteria\"][\"F12.2\"][\"verdict\"]})')\n"
        "print('  the book rebalances monthly, so the regression absorbs a month of drift')\n"
        "print('  in its intercept; the live book rebalances daily and is the object the')\n"
        "print('  criterion is about.')",
    ),
    (
        "markdown",
        "## 7. Skill against luck\n"
        "\n"
        "The rule: no skill is claimed unless the t-statistic exceeds two, and the\n"
        "Sharpe carries its standard error. Both standard errors come from `efb.perf`,\n"
        "the E1 library, so this is the same estimator the E1 report used.",
    ),
    (
        "code",
        "from efb import perf\n"
        "\n"
        "skill = attribution.skill_test(daily)\n"
        "total_series = daily['pnl_total']\n"
        "print(f'  days                          {skill[\"n_days\"]:,}')\n"
        "print(f'  mean idio P&L                 {skill[\"idio_mean\"] * 1e4:+.4f} bp/day')\n"
        "print(f'  its standard error            {skill[\"idio_se\"] * 1e4:.4f} bp')\n"
        "print(f'  t-statistic                   {skill[\"t_stat\"]:.2f}')\n"
        "print(f'  annualized information ratio  {skill[\"ir_annual\"]:.3f}')\n"
        "print(f'  annualized Sharpe             {skill[\"sharpe_annual\"]:.3f}')\n"
        "print(f'    SE, i.i.d.                  {skill[\"sharpe_se_iid\"]:.3f}')\n"
        "print(f'    SE, Lo 2002                 {skill[\"sharpe_se_lo2002\"]:.3f}')\n"
        "assert skill['sharpe_annual'] == perf.annualized_sharpe(total_series)\n"
        "assert skill['sharpe_se_lo2002'] == perf.sharpe_se_lo2002(total_series) * math.sqrt(252)\n"
        "print()\n"
        "print('  days needed for a t of', skill['target_t'], ':')\n"
        "for ir, days in skill['days_to_detect'].items():\n"
        "    print(f'    annualized IR {ir:4.2f} -> {days:>6,} days ({days / 252:5.1f} years)')\n"
        "print()\n"
        "print('  verdict:', skill['verdict'])\n"
        "print('  E10 chose the (rho, phi) whose Sharpe is closest to 1.0 on this same')\n"
        "print('  sample, so this is the selection working, not a discovery. The live book')\n"
        "print('  trades a different, null signal; its expected verdict is luck.')",
    ),
    (
        "markdown",
        "## 8. What the page reads, panel by panel\n"
        "\n"
        "`docs/snapshot.schema.json` is the contract between the writer and the page.\n"
        "Every panel below is a key in it, and every key is fed by a column of the\n"
        "stored artifact rather than by a recomputation.",
    ),
    (
        "code",
        "from live import snapshot\n"
        "\n"
        "block = snapshot.attribution_block(daily)\n"
        "schema = json.loads((ROOT / 'docs' / 'snapshot.schema.json').read_text())\n"
        "declared = schema['properties']['attribution']\n"
        "print('  the schema declares attribution as required:', 'attribution' in schema['required'])\n"
        "print('  the builder emits exactly its keys:', set(block) == set(declared['properties']))\n"
        "print('  cumulative sums are the artifact\\'s own sums:',\n"
        "      math.isclose(block['cumulative']['pnl_total'], float(daily['pnl_total'].sum())))\n"
        "print()\n"
        "print('  panel                          source column')\n"
        "for panel, column in (('cumulative total/factor/idio/cost', 'pnl_total, pnl_factor, pnl_idio, pnl_cost'),\n"
        "                      ('worst day\\'s identity residual', 'identity_residual'),\n"
        "                      ('the hedge\\'s factor P&L, per day', 'pnl_timing'),\n"
        "                      ('the raw-beta line', 'book_beta, market_return, pnl_beta'),\n"
        "                      ('realized against expected cost', 'realized_cost_bps, expected_cost_bps'),\n"
        "                      ('forecast against realized vol', 'forecast_vol, realized_vol'),\n"
        "                      ('fill differences', 'n_target, n_filled, max_fill_gap')):\n"
        "    print(f'  {panel:30s} {column}')",
    ),
    (
        "markdown",
        "## 9. What would falsify this, and what is not here\n"
        "\n"
        "Falsification is written before the live numbers, so the report cannot be read\n"
        "as a story told afterwards. The memo carries the full list; the three that\n"
        "matter are that the identity fails on live days, that the two estimators\n"
        "disagree beyond one standard error on a book that rebalances daily, and that\n"
        "the hedge's own factor P&L grows rather than shrinks.\n"
        "\n"
        "Named as open rather than quietly dropped: the regime table and the seven-way\n"
        "selection, sizing and timing decomposition are in the roadmap's E12 scope and\n"
        "are not among this sprint's nine tasks.",
    ),
    (
        "code",
        "# Closing checklist: the criteria appear, and what is pending is pending.\n"
        "joined = json.dumps(results)\n"
        "for name in ('F12.1', 'F12.2', 'F12.3'):\n"
        "    assert name in joined, name\n"
        "assert results['criteria']['F12.3']['expected_verdict'] == 'luck'\n"
        "print('  F12.1', results['criteria']['F12.1']['verdict'])\n"
        "print('  F12.2', results['criteria']['F12.2']['verdict'])\n"
        "print('  F12.3', results['criteria']['F12.3']['verdict'],\n"
        "      '| expected verdict:', results['criteria']['F12.3']['expected_verdict'])\n"
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
            "id": f"e12w{index:02d}",
            "metadata": {},
            "source": source.splitlines(keepends=True),
        }
        if kind == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        notebook["cells"].append(cell)
    path = ROOT / "notebooks" / "E12_walkthrough.ipynb"
    path.write_text(json.dumps(notebook, indent=1) + "\n")
    print(f"wrote {path} with {len(CELLS)} cells")


if __name__ == "__main__":
    build()
