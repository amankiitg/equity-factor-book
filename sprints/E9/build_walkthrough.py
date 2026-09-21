"""Build the E9 walkthrough notebook cells from a source list.

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
        "# Sprint E9 walkthrough: transaction costs and capacity",
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
        'if not (ROOT / "efb").exists():\n'
        "    ROOT = ROOT.parent\n"
        "if str(ROOT) not in sys.path:\n"
        "    sys.path.insert(0, str(ROOT))\n"
        'DATA = ROOT / "data"\n'
        'COSTS = DATA / "costs"',
    ),
    (
        "code",
        "# the data hash in the results file must be the hash of the artifacts\n"
        "# the criteria are read from, recomputed now, not copied\n"
        "from efb import evaluate\n"
        "\n"
        "stored = json.loads(\n"
        '    (ROOT / "sprints" / "E9" / "RESULTS.json").read_text()\n'
        ")\n"
        'assert evaluate.e9_data_hash(DATA) == stored["data_hash"], '
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
        "## 2. The Corwin-Schultz half-spread, by hand\n"
        "\n"
        "beta and gamma from the high-low ranges; alpha = "
        "(sqrt(2 beta) - sqrt(beta)) / (3 - 2 sqrt(2)); the spread is "
        "2 (exp(alpha) - 1) / (1 + exp(alpha)).",
    ),
    (
        "code",
        "from efb import costs\n"
        "\n"
        'prices = pd.read_parquet(DATA / "raw" / "prices.parquet")\n'
        "spread = costs.corwin_schultz(prices)\n"
        'print("names with a spread estimate", spread.notna().sum())\n'
        'print("median half-spread", round(float(spread.median()), 6))\n'
        "assert spread.notna().sum() > 100",
    ),
    (
        "markdown",
        "## 3. The capacity curve, live\n"
        "\n"
        "Net Sharpe against AUM, per rho and impact coefficient; the halving "
        "AUM is stored per rho.",
    ),
    (
        "code",
        'capacity = pd.read_parquet(COSTS / "capacity.parquet")\n'
        'halving = pd.read_parquet(COSTS / "capacity_halving.parquet")\n'
        "print(halving.to_string())\n"
        "assert not capacity.empty",
    ),
    (
        "markdown",
        "## 4. The turnover versus IR trade-off (F9.2)",
    ),
    (
        "code",
        'tradeoff = pd.read_parquet(COSTS / "turnover_tradeoff.parquet")\n'
        "print(tradeoff.to_string())",
    ),
    (
        "markdown",
        "## 5. The D8 panel map",
    ),
    (
        "code",
        "from dashboard.tabs import d08_costs as d8\n"
        "\n"
        "curves = d8.load_cost_curves()\n"
        "assert not curves.empty\n"
        'print("D8 reads the cost curves, the capacity curve and the trade-off")',
    ),
    (
        "markdown",
        "## 6. The memo's evidence, in citation order",
    ),
    (
        "code",
        'memo = (ROOT / "docs" / "research" / "E9_tcost_capacity.md").read_text()\n'
        'joined = " ".join(memo.split())\n'
        'for name in ("F9.1", "F9.2", "F9.3", "F9.4"):\n'
        "    assert name in joined, name\n"
        'assert "What would falsify this?" in joined\n'
        'assert "synthetic" in joined\n'
        'print("memo cites every criterion and the falsification section")',
    ),
    (
        "code",
        "# closing checklist: criteria present, no stored number typed by hand\n"
        "import re\n"
        "\n"
        "offenders: list[str] = []\n"
        'for name, block in stored["criteria"].items():\n'
        '    for match in re.findall(r"-?\\d+\\.\\d+", json.dumps(block["stored_numbers"])):\n'
        "        offenders.append(match)\n"
        'source = "\\n".join(cell["source"] for cell in __import__("json").loads(\n'
        '    (ROOT / "notebooks" / "E9_walkthrough.ipynb").read_text()\n'
        ')["cells"] if cell["cell_type"] == "code")\n'
        'print("stored values typed into a cell: none" if not offenders else offenders)\n'
        'assert all(name in source for name in ("F9.1", "F9.2", "F9.3", "F9.4"))\n'
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
            "id": f"e9w{index:02d}",
            "metadata": {},
            "source": source.splitlines(keepends=True),
        }
        if kind == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        notebook["cells"].append(cell)
    path = ROOT / "notebooks" / "E9_walkthrough.ipynb"
    path.write_text(json.dumps(notebook, indent=1) + "\n")
    print(f"wrote {path} with {len(CELLS)} cells")


if __name__ == "__main__":
    build()
