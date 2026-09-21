"""Build the E6 walkthrough notebook cells from a source list.

The notebook is generated, not edited by hand, so the criteria text and the
numbers stay as stored. Execution and rendering happen through nbconvert.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CELLS: list[tuple[str, str]] = [
    (
        "markdown",
        "# Sprint E6 walkthrough: the hedging toolkit and its realized efficacy",
    ),
    (
        "code",
        "# the repository root is importable so the package and the dashboard module can\n"
        "# be imported without installing the wheel\n"
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "\n"
        "ROOT = Path.cwd()\n"
        "if not (ROOT / \"efb\").exists():\n"
        "    ROOT = ROOT.parent\n"
        "if str(ROOT) not in sys.path:\n"
        "    sys.path.insert(0, str(ROOT))\n"
        "DATA = ROOT / \"data\"\n"
        "HEDGE = DATA / \"hedge\"",
    ),
    (
        "code",
        "# Cell 1 rule: the data hash in the results file must be the hash of the\n"
        "# artifacts the criteria are read from, recomputed now, not copied\n"
        "from efb import evaluate\n"
        "\n"
        "stored = json.loads((ROOT / \"sprints\" / \"E6\" / \"RESULTS.json\").read_text())\n"
        "assert evaluate.e6_data_hash(DATA) == stored[\"data_hash\"], \"artifact hash drift\"\n"
        "print(\"data_hash\", stored[\"data_hash\"])",
    ),
    (
        "markdown",
        "## 1. Every criterion, its stored number and its verdict",
    ),
    (
        "code",
        "# the criterion text is printed as stored, so a reworded threshold would\n"
        "# show up here as a diff against sprints/E6/RESULTS.json\n"
        "for name, block in stored[\"criteria\"].items():\n"
        "    print(name, block[\"verdict\"])\n"
        "    print(\" \", block[\"criterion\"])\n"
        "    print(\" \", json.dumps(block[\"stored_numbers\"], sort_keys=True)[:220])",
    ),
    (
        "markdown",
        "## 2. By hand: the beta hedge ratio",
    ),
    (
        "code",
        "# h = -cov(book, SPY) / var(SPY) over the trailing 252 sessions before the\n"
        "# last rebalance date, recomputed from the stored returns rather than\n"
        "# copied from the metrics\n"
        "from efb import eval_risk, hedge, race\n"
        "\n"
        "wide, _counts = eval_risk.load_clean_wide(DATA)\n"
        "portfolios = pd.read_parquet(DATA / \"eval\" / \"e5_portfolios.parquet\")\n"
        "instrument_returns = hedge.load_etf_returns(DATA)\n"
        "grid = race.race_grid(DATA)\n"
        "book_returns = hedge._seed_book_returns(\"seed_mom_ls\", wide, portfolios)\n"
        "spy = instrument_returns[\"SPY\"]\n"
        "last_date = grid[-1]\n"
        "h_by_hand = hedge.beta_hedge(\n"
        "    book_returns.loc[book_returns.index < last_date],\n"
        "    spy.loc[spy.index < last_date],\n"
        ")\n"
        "metrics = pd.read_parquet(HEDGE / \"hedge_metrics.parquet\")\n"
        "stored_h = metrics.loc[\n"
        "    (metrics[\"method\"] == \"beta\") & (metrics[\"book\"] == \"seed_mom_ls\"),\n"
        "    \"h_spy_beta\",\n"
        "].iloc[-1]\n"
        "print(\"h by hand:\", round(h_by_hand, 6))\n"
        "print(\"h stored:\", round(float(stored_h), 6))\n"
        "assert abs(h_by_hand - float(stored_h)) < 1e-6",
    ),
    (
        "markdown",
        "## 3. By hand: the minimum-variance hedge normal equations",
    ),
    (
        "code",
        "# h* = -(H' Sigma H)^-1 H' Sigma w, rebuilt on one grid date from the same\n"
        "# pieces the engine uses, and checked against the stored positions\n"
        "date = grid[-1]\n"
        "names = eval_risk._window_names(wide, date)\n"
        "supplied = eval_risk._xs_pieces(date, names, DATA)\n"
        "betas, idio = hedge._instrument_betas(date, instrument_returns, DATA)\n"
        "usable = np.isfinite(betas).all(axis=0) & np.isfinite(idio)\n"
        "sigma_hh = (\n"
        "    betas[:, usable].T @ supplied[\"factor_covariance\"] @ betas[:, usable]\n"
        "    + np.diag(idio[usable])\n"
        ")\n"
        "rows = portfolios.loc[\n"
        "    (portfolios[\"portfolio\"] == \"seed_mom_ls\")\n"
        "    & (pd.to_datetime(portfolios[\"date\"]) == date)\n"
        "]\n"
        "weights = (\n"
        "    rows.set_index(\"ticker\")[\"weight\"].reindex(names).fillna(0.0).to_numpy()\n"
        ")\n"
        "exposures = supplied[\"design\"].T @ weights\n"
        "sigma_hw = betas[:, usable].T @ supplied[\"factor_covariance\"] @ exposures\n"
        "h_by_hand = hedge.min_variance_hedge(sigma_hh, sigma_hw)\n"
        "positions = pd.read_parquet(HEDGE / \"hedge_positions.parquet\")\n"
        "stored_positions = positions.loc[\n"
        "    (positions[\"book\"] == \"seed_mom_ls\")\n"
        "    & (positions[\"method\"] == \"min_variance\")\n"
        "    & (positions[\"model\"] == \"xs_v1\")\n"
        "    & (pd.to_datetime(positions[\"date\"]) == date)\n"
        "].set_index(\"instrument\")[\"weight\"]\n"
        "stored_h = stored_positions.reindex(np.array(hedge.INSTRUMENTS)[usable]).to_numpy()\n"
        "print(\"normal equation residual:\", float(np.abs(sigma_hh @ h_by_hand + sigma_hw).max()))\n"
        "print(\"against stored positions:\", float(np.abs(h_by_hand - stored_h).max()))\n"
        "assert np.abs(sigma_hh @ h_by_hand + sigma_hw).max() < 1e-10\n"
        "assert np.abs(h_by_hand - stored_h).max() < 1e-10",
    ),
    (
        "markdown",
        "## 4. By hand: the FMP hedge is exact in model",
    ),
    (
        "code",
        "# the exact hedge is -X (X'X)^-1 x, so the post-hedge exposure is zero by\n"
        "# construction; the as-stored quarterly capped FMPs keep their cap drift\n"
        "exact_hedge, n_names = hedge.fmp_hedge_exact(supplied[\"design\"], exposures)\n"
        "after = supplied[\"design\"].T @ (weights + exact_hedge)\n"
        "exposure_rows = pd.read_parquet(HEDGE / \"e6_exposures.parquet\")\n"
        "capped_worst = exposure_rows[\"exposure_after_fmp_capped\"].abs().max()\n"
        "print(\"worst absolute exposure after the exact FMP hedge:\", float(np.abs(after).max()))\n"
        "print(\"names traded by the exact hedge:\", n_names)\n"
        "print(\"worst absolute exposure after the capped stored FMPs:\", round(float(capped_worst), 4))\n"
        "assert np.abs(after).max() < 1e-6",
    ),
    (
        "markdown",
        "## 5. The D5 panel-to-column map, and the non-empty guard",
    ),
    (
        "code",
        "from dashboard.tabs import d05_hedging as d5  # noqa: E402\n"
        "\n"
        "for panel in (\n"
        "    d5.headline_panel,\n"
        "    d5.positions_panel,\n"
        "    d5.residual_exposure_panel,\n"
        "    d5.realized_panel,\n"
        "    d5.decay_panel,\n"
        "):\n"
        "    frame = panel()\n"
        "    assert not frame.empty, panel.__name__\n"
        "    print(panel.__name__, frame.shape, list(frame.columns))",
    ),
    (
        "markdown",
        "## 6. Evidence for the deliverable, in citation order",
    ),
    (
        "code",
        "# the numbers the study cites, in the order it cites them, all read from\n"
        "# the stored artifacts rather than typed\n"
        "print(\"worst exact FMP exposure:\", exposure_rows[\"exposure_after_fmp\"].abs().max())\n"
        "print(\"idio share after FMP:\", metrics.loc[metrics[\"method\"] == \"fmp\", \"idio_share_after\"].mean())\n"
        "print(\"mean FMP name count:\", metrics.loc[metrics[\"method\"] == \"fmp\", \"name_count\"].mean())\n"
        "print(\"long-only share removed:\", metrics.loc[(metrics[\"method\"] == \"min_variance\") & (metrics[\"book\"] == \"seed_ew\"), \"factor_variance_removed_share\"].mean())\n"
        "print(\"mean instruments:\", metrics.loc[metrics[\"method\"] == \"min_variance\", \"n_instruments\"].mean())\n"
        "print(\"momentum share removed:\", metrics.loc[(metrics[\"method\"] == \"min_variance\") & (metrics[\"book\"] == \"seed_mom_ls\"), \"factor_variance_removed_share\"].mean())\n"
        "print(\"residual per factor (top 5):\")\n"
        "print(exposure_rows.loc[exposure_rows[\"book\"] == \"seed_ew\"].groupby(\"factor\")[\"exposure_after_min_variance\"].apply(lambda s: s.abs().mean()).sort_values(ascending=False).head(5))\n"
        "print(pd.read_parquet(HEDGE / \"e6_efficacy.parquet\").to_string())\n"
        "print(pd.read_parquet(HEDGE / \"e6_decay.parquet\").to_string())",
    ),
    (
        "markdown",
        "## 7. What E7 inherits",
    ),
    (
        "code",
        "# E7 builds signals on XS-v1 residuals and neutralizes them through the\n"
        "# FMP machinery this sprint exercised: the exact hedge for in-model\n"
        "# neutrality, the capped stored FMPs for tradability, and the realized\n"
        "# efficacy record as the template for judging a hedge\n"
        "print(\"FMP weights:\", DATA / \"models\" / \"XS-v1\" / \"fmp_weights.parquet\")\n"
        "print(\"exact hedge exposure floor:\", float(np.abs(after).max()))\n"
        "print(\"capped FMP drift, worst:\", round(float(capped_worst), 4))\n"
        "print(\"instrument count range:\", int(metrics.loc[metrics[\"method\"] == \"min_variance\", \"n_instruments\"].min()), int(metrics.loc[metrics[\"method\"] == \"min_variance\", \"n_instruments\"].max()))",
    ),
    (
        "markdown",
        "## 7b. Credit port note: what changes when the instruments are bonds",
    ),
    (
        "code",
        "# the same algebra ports one to one: the book's factor exposures come\n"
        "# from the same design, the hedge universe swaps ETFs for rates and CDX\n"
        "# contracts, and the residual is what no liquid contract spans. The\n"
        "# missing-data semantics carry over unchanged: an untraded contract\n"
        "# contributes zero, a held contract with no price makes the day missing\n"
        "print(\"instruments:\", hedge.INSTRUMENTS)\n"
        "print(\"credit analogues: rates and CDX tenors in place of the sector SPDRs\")\n"
        "print(\"unspanned residual stored per factor:\", bool(len(exposure_rows)))",
    ),
    (
        "markdown",
        "## 8. Closing checklist",
    ),
    (
        "code",
        "def numeric_leaves(node):\n"
        "    out = []\n"
        "    if isinstance(node, dict):\n"
        "        for value in node.values():\n"
        "            out.extend(numeric_leaves(value))\n"
        "    elif isinstance(node, list):\n"
        "        for value in node:\n"
        "            out.extend(numeric_leaves(value))\n"
        "    elif isinstance(node, float):\n"
        "        out.append(node)\n"
        "    return out\n"
        "\n"
        "\n"
        "import nbformat\n"
        "\n"
        "notebook = nbformat.read(ROOT / \"notebooks\" / \"E6_walkthrough.ipynb\", as_version=4)\n"
        "source = \"\\n\".join(\"\".join(cell.source) for cell in notebook.cells if cell.cell_type == \"code\")\n"
        "values = numeric_leaves(stored[\"criteria\"])\n"
        "offenders = []\n"
        "for value in values:\n"
        "    for text in (f\"{value:.6f}\", f\"{value:.4f}\"):\n"
        "        if len(text) > 6 and text in source:\n"
        "            offenders.append(text)\n"
        "print(\"stored values typed into a cell:\", offenders)\n"
        "assert offenders == []\n"
        "assert all(name in source for name in (\"F6.1\", \"F6.2\", \"F6.3\", \"F6.4\", \"F6.5\"))\n"
        "print(\"closing checklist: clean\")",
    ),
]


def build() -> None:
    notebook: dict = {
        "cells": [],
        "metadata": {
            "kernelspec": {"display_name": "efb-venv", "language": "python", "name": "efb-venv"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    for index, (kind, source) in enumerate(CELLS):
        cell: dict = {"cell_type": kind, "id": f"e6w{index:02d}", "metadata": {}, "source": source.splitlines(keepends=True)}
        if kind == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        notebook["cells"].append(cell)
    path = ROOT / "notebooks" / "E6_walkthrough.ipynb"
    path.write_text(json.dumps(notebook, indent=1) + "\n")
    print(f"wrote {path} with {len(CELLS)} cells")


if __name__ == "__main__":
    build()
