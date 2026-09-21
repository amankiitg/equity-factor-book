"""Build the E7 walkthrough notebook cells from a source list.

Generated, not hand-edited, so the criteria text and the numbers stay as
stored. Execution and rendering happen through nbconvert.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CELLS: list[tuple[str, str]] = [
    (
        "markdown",
        "# Sprint E7 walkthrough: the alpha lab and backtest hygiene",
    ),
    (
        "code",
        "# the repository root is importable so the package and the dashboard\n"
        "# module can be imported without installing the wheel\n"
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
        "ALPHA = DATA / \"alpha\"",
    ),
    (
        "code",
        "# Cell 1 rule: the data hash in the results file must be the hash of\n"
        "# the artifacts the criteria are read from, recomputed now, not copied\n"
        "from efb import evaluate\n"
        "\n"
        "stored = json.loads(\n"
        "    (ROOT / \"sprints\" / \"E7\" / \"RESULTS.json\").read_text()\n"
        ")\n"
        "gate = json.loads(\n"
        "    (ROOT / \"sprints\" / \"E7\" / \"RG_SIGNAL.json\").read_text()\n"
        ")\n"
        "assert evaluate.e7_data_hash(DATA) == stored[\"data_hash\"], "
        "\"artifact hash drift\"\n"
        "print(\"data_hash\", stored[\"data_hash\"])\n"
        "print(\"gate verdicts:\",\n"
        "      {name: block[\"verdict\"] for name, block in gate.items()})",
    ),
    (
        "markdown",
        "## 1. Every criterion, its stored number and its verdict",
    ),
    (
        "code",
        "# the criterion text is printed as stored, so a reworded threshold\n"
        "# would show up here as a diff against sprints/E7/RESULTS.json\n"
        "for name, block in stored[\"criteria\"].items():\n"
        "    print(name, block[\"verdict\"])\n"
        "    print(\" \", block[\"criterion\"])\n"
        "    print(\" \", json.dumps(block[\"stored_numbers\"], sort_keys=True)[:220])",
    ),
    (
        "markdown",
        "## 2. By hand: the information coefficient on one day",
    ),
    (
        "code",
        "# IC = rank-correlation(s_t, r_t), recomputed on one date from the\n"
        "# stored signal and returns rather than copied from the IC artifact\n"
        "from efb import alpha, eval_risk, hygiene, race\n"
        "\n"
        "wide, _counts = eval_risk.load_clean_wide(DATA)\n"
        "signal = alpha._signal_for(\"momentum_12_1\", wide, DATA)\n"
        "ic = hygiene.spearman_ic(signal, wide, 1)\n"
        "date = ic.index[-1]\n"
        "s_wide = signal.pivot(index=\"date\", columns=\"ticker\", values=\"signal\")\n"
        "s = s_wide.loc[date]\n"
        "r = wide.loc[date]\n"
        "both = pd.concat([s, r], axis=1).dropna()\n"
        "by_hand = both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank())\n"
        "stored_ic = pd.read_parquet(\n"
        "    ALPHA / \"momentum_12_1\" / \"ic.parquet\"\n"
        ")[\"ic_h1\"].loc[date]\n"
        "print(\"IC by hand:\", round(float(by_hand), 6))\n"
        "print(\"IC stored:\", round(float(stored_ic), 6))\n"
        "assert abs(by_hand - float(stored_ic)) < 1e-9",
    ),
    (
        "markdown",
        "## 3. By hand: factor neutralization",
    ),
    (
        "code",
        "# s_perp = s - X (X'X)^-1 X' s on one rebalance date; the residual must\n"
        "# be orthogonal to every non-constant design column\n"
        "grid = race.race_grid(DATA)\n"
        "date = grid[-1]\n"
        "neutral = hygiene.neutralize(signal, wide, date, DATA)\n"
        "names = list(neutral[\"ticker\"])\n"
        "design = race._descriptor_design(date, names, DATA)\n"
        "residual = neutral[\"signal\"].to_numpy(dtype=float)\n"
        "correlations = [\n"
        "    abs(np.corrcoef(design[:, k], residual)[0, 1])\n"
        "    for k in range(design.shape[1])\n"
        "    if np.std(design[:, k]) > 0\n"
        "]\n"
        "print(\"max abs correlation with a design column:\",\n"
        "      float(max(correlations)))\n"
        "assert max(correlations) < 1e-6",
    ),
    (
        "markdown",
        "## 4. The shift audit, run live",
    ),
    (
        "code",
        "# the lagged-construction probe: every input moved one day back, the\n"
        "# lagged IC against r_t decides leakage or fast decay\n"
        "for name in (\"momentum_12_1\", \"post_earnings_drift\"):\n"
        "    signal_i = alpha._signal_for(name, wide, DATA)\n"
        "    lagged = alpha.lagged_signal(name, wide, DATA)\n"
        "    audit = hygiene.shift_audit(signal_i, lagged, wide)\n"
        "    print(name, \"leak:\", bool(audit[\"leak_flag\"].iloc[-1]),\n"
        "          \"t_now:\", round(float(audit[\"t_ic\"].iloc[-1]), 2),\n"
        "          \"t_lagged:\", round(float(audit[\"t_ic_lagged\"].iloc[-1]), 2))",
    ),
    (
        "markdown",
        "## 5. The D6 panel-to-column map, and the non-empty guard",
    ),
    (
        "code",
        "from dashboard.tabs import d06_alpha_lab as d6  # noqa: E402\n"
        "\n"
        "summary = d6.load_summary()\n"
        "print(\"summary\", summary.shape, list(summary.columns))\n"
        "for name in d6.SIGNALS:\n"
        "    path = d6.ALPHA / name / \"ic.parquet\"\n"
        "    if not path.exists():\n"
        "        continue\n"
        "    assert not d6.ic_panel(name).empty\n"
        "    print(name, d6.ic_panel(name).shape)\n"
        "ledger = d6.ledger_panel()\n"
        "assert not ledger.empty\n"
        "print(\"ledger\", ledger.shape)",
    ),
    (
        "markdown",
        "## 6. Evidence for the reports, in citation order",
    ),
    (
        "code",
        "# the numbers the six reports cite, read from the artifacts, not typed\n"
        "summary = pd.read_parquet(ALPHA / \"summary.parquet\")\n"
        "print(summary[[\"signal\", \"ic_h1_mean\", \"ic_h1_t\",\n"
        "              \"neutral_ic_h21_mean\", \"out_of_sample_t\",\n"
        "              \"oos_spread_sharpe\", \"audit_leak_flag\"]].to_string())\n"
        "print(pd.read_parquet(\n"
        "    ALPHA / \"momentum_12_1\" / \"regime_ic.parquet\"\n"
        ").to_string())",
    ),
    (
        "markdown",
        "## 7. What E8 inherits",
    ),
    (
        "code",
        "# E8 sizes positions from the stored alpha contract; every signal is\n"
        "# NULL, so construction runs on synthetic alpha with a known IC\n"
        "contract = pd.read_parquet(ALPHA / \"momentum_12_1\" / \"alpha.parquet\")\n"
        "print(\"alpha contract columns:\", list(contract.columns))\n"
        "print(\"gate verdicts:\",\n"
        "      {name: block[\"verdict\"] for name, block in gate.items()})",
    ),
    (
        "markdown",
        "## 7b. Credit port note: what changes when the cross-section is bonds",
    ),
    (
        "code",
        "# the IC and decay machinery is instrument-agnostic; the signals that\n"
        "# exist only in equities (earnings drift) have no bond analogue, and\n"
        "# the design columns are the credit factors instead of the equity ones\n"
        "print(\"equity-only signals: post_earnings_drift, short_interest\")\n"
        "print(\"bond analogues: carry and roll-down instead of\\n\"\n"
        "      \"momentum and reversal\")",
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
        "notebook = nbformat.read(\n"
        "    ROOT / \"notebooks\" / \"E7_walkthrough.ipynb\", as_version=4\n"
        ")\n"
        "source = \"\\n\".join(\n"
        "    \"\".join(cell.source)\n"
        "    for cell in notebook.cells\n"
        "    if cell.cell_type == \"code\"\n"
        ")\n"
        "values = numeric_leaves(stored[\"criteria\"]) + numeric_leaves(gate)\n"
        "offenders = []\n"
        "for value in values:\n"
        "    for text in (f\"{value:.6f}\", f\"{value:.4f}\"):\n"
        "        if len(text) > 6 and text in source:\n"
        "            offenders.append(text)\n"
        "print(\"stored values typed into a cell:\", offenders)\n"
        "assert offenders == []\n"
        "assert all(\n"
        "    name in source for name in (\"F7.1\", \"F7.2\", \"F7.3\", \"F7.4\")\n"
        ")\n"
        "print(\"closing checklist: clean\")",
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
            "id": f"e7w{index:02d}",
            "metadata": {},
            "source": source.splitlines(keepends=True),
        }
        if kind == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        notebook["cells"].append(cell)
    path = ROOT / "notebooks" / "E7_walkthrough.ipynb"
    path.write_text(json.dumps(notebook, indent=1) + "\n")
    print(f"wrote {path} with {len(CELLS)} cells")


if __name__ == "__main__":
    build()
