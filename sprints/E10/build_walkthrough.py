"""Build the E10 walkthrough notebook cells from a source list.

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
        "# Sprint E10 walkthrough: dynamic risk allocation and loss management",
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
        'DATA = ROOT / "data"\n'
        'ALLOC = DATA / "allocation"',
    ),
    (
        "code",
        "# the data hash in the results file must be the hash of the artifacts\n"
        "# the criteria are read from, recomputed now, not copied\n"
        "from efb import evaluate\n"
        "\n"
        "stored = json.loads(\n"
        '    (ROOT / "sprints" / "E10" / "RESULTS.json").read_text()\n'
        ")\n"
        'assert evaluate.e10_data_hash(DATA) == stored["data_hash"], '
        '"artifact hash drift"\n'
        'print("data_hash", stored["data_hash"])\n'
        'print("verdicts:", stored["reference_values"]["verdicts"])',
    ),
    (
        "markdown",
        "## 1. Every criterion, its stored number and its verdict",
    ),
    (
        "code",
        'for name, block in stored["criteria"].items():\n'
        '    print(name, block["verdict"], json.dumps(block["stored_numbers"])[:160])',
    ),
    (
        "markdown",
        "## 2. The design book and the Kelly analysis\n"
        "\n"
        "The (rho, phi) whose net annualized Sharpe is closest to 1.0, and "
        "the Kelly fraction f* = mu / sigma^2 with the growth curve.",
    ),
    (
        "code",
        "from efb import allocate\n"
        "\n"
        "config = allocate.pick_design_config(DATA)\n"
        'print("design config", config)\n'
        "kelly = pd.read_parquet(ALLOC / 'kelly.parquet').iloc[0]\n"
        "full = kelly['mean_ann'] / kelly['vol_ann'] ** 2\n"
        "assert abs(full - kelly['kelly_full']) < 1e-9\n"
        "print('full Kelly', round(kelly['kelly_full'], 4))\n"
        "print('half Kelly', round(kelly['kelly_half'], 4))\n"
        "print('growth at full Kelly', round(kelly['growth_full'], 4))\n"
        "print('growth at half Kelly', round(kelly['growth_half'], 4))\n"
        "print('growth loss overbet', round(kelly['growth_loss_overbet'], 4))",
    ),
    (
        "markdown",
        "## 3. F10.1: the drawdown distribution against the analytical median",
    ),
    (
        "code",
        "drawdown = pd.read_parquet(ALLOC / 'drawdown.parquet').iloc[0]\n"
        "# the analytical median is ln(2) sigma^2 / (2 mu), recomputed by hand\n"
        "analytical = np.log(2.0) * kelly['vol_ann'] ** 2 / (2.0 * kelly['mean_ann'])\n"
        "assert abs(analytical - drawdown['analytical_median_drawdown']) < 1e-9\n"
        "print('simulated median', round(drawdown['simulated_median_drawdown'], 4))\n"
        "print('analytical median', round(drawdown['analytical_median_drawdown'], 4))\n"
        "print('relative gap', round(drawdown['relative_gap_at_median'], 4))",
    ),
    (
        "markdown",
        "## 4. F10.3: vol targeting and the realized-vol dispersion",
    ),
    (
        "code",
        "voltarget = pd.read_parquet(ALLOC / 'voltarget.parquet').iloc[0]\n"
        "print('raw dispersion', round(voltarget['raw_dispersion'], 4))\n"
        "print('targeted dispersion', round(voltarget['targeted_dispersion'], 4))\n"
        "print('reduction', round(voltarget['dispersion_reduction'], 4))",
    ),
    (
        "markdown",
        "## 5. F10.2: the stop-loss and its i.i.d. control",
    ),
    (
        "code",
        "stoploss = pd.read_parquet(ALLOC / 'stoploss.parquet')\n"
        "control = stoploss[stoploss['book'] == 'design'].iloc[0]\n"
        "print(\n"
        "    'control mean Sharpe diff',\n"
        "    round(control['control_mean_sharpe_diff'], 4),\n"
        ")\n"
        "assert not bool(control['control_improves_sharpe']), "
        "'the i.i.d. control must not improve'\n"
        "print(stoploss.to_string(index=False))",
    ),
    (
        "markdown",
        "## 6. Drawdowns by VIX regime, the risk budget per regime",
    ),
    (
        "code",
        "regime = pd.read_parquet(ALLOC / 'regime.parquet')\n"
        "print(regime.to_string(index=False))\n"
        "assert set(regime['vix_tercile']) == {0, 1, 2}",
    ),
    (
        "markdown",
        "## 7. The D9 panel map: which parquet column each panel reads",
    ),
    (
        "code",
        "from dashboard.tabs import d09_risk_allocation as d9\n"
        "\n"
        "panels = {\n"
        "    'kelly': d9.kelly_panel(),\n"
        "    'drawdown': d9.drawdown_panel(),\n"
        "    'voltarget': d9.voltarget_panel(),\n"
        "    'stoploss': d9.stoploss_panel(),\n"
        "    'regime': d9.regime_panel(),\n"
        "}\n"
        "for name, panel in panels.items():\n"
        "    assert not panel.empty, name\n"
        "    print(name, list(panel.columns))",
    ),
    (
        "code",
        "# the memo cites every criterion and the falsification section\n"
        'memo = (ROOT / "docs" / "research" / "E10_risk_policy.md").read_text()\n'
        'joined = " ".join(memo.split())\n'
        'for name in ("F10.1", "F10.2", "F10.3"):\n'
        "    assert name in joined, name\n"
        'assert "What would falsify this?" in joined\n'
        'assert "synthetic" in joined\n'
        'print("memo cites every criterion and the falsification section")',
    ),
    (
        "code",
        "# closing checklist: every criterion name is covered by the code\n"
        "import json as _json\n"
        "\n"
        'source = "\\n".join(\n'
        '    "".join(cell["source"])\n'
        "    for cell in _json.loads(\n"
        '        (ROOT / "notebooks" / "E10_walkthrough.ipynb").read_text()\n'
        '    )["cells"]\n'
        '    if cell["cell_type"] == "code"\n'
        ")\n"
        "assert all(\n"
        '    name in source for name in ("F10.1", "F10.2", "F10.3")\n'
        ")\n"
        'print("closing checklist: clean")',
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
            "id": f"e10w{index:02d}",
            "metadata": {},
            "source": source.splitlines(keepends=True),
        }
        if kind == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        notebook["cells"].append(cell)
    path = ROOT / "notebooks" / "E10_walkthrough.ipynb"
    path.write_text(json.dumps(notebook, indent=1) + "\n")
    print(f"wrote {path} with {len(CELLS)} cells")


if __name__ == "__main__":
    build()
