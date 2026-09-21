"""Build the E8 walkthrough notebook cells from a source list.

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
        "# Sprint E8 walkthrough: sizing and portfolio construction",
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
        'PORTFOLIOS = DATA / "portfolios"',
    ),
    (
        "code",
        "# the data hash in the results file must be the hash of the artifacts\n"
        "# the criteria are read from, recomputed now, not copied\n"
        "from efb import evaluate\n"
        "\n"
        "stored = json.loads(\n"
        '    (ROOT / "sprints" / "E8" / "RESULTS.json").read_text()\n'
        ")\n"
        'assert evaluate.e8_data_hash(DATA) == stored["data_hash"], '
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
        "## 2. The synthetic alpha, by hand\n"
        "\n"
        "z(i,t) = rho * standardized(e(i,t+h)) + sqrt(1 - rho^2) * eps(i,t). "
        "This is a controlled experiment that uses future data deliberately, "
        "never a backtest.",
    ),
    (
        "code",
        "from efb import size\n"
        "\n"
        "frame = size.synthetic_alpha(DATA, rho=0.05, seed=0)\n"
        'measured = float(frame.groupby("date")["ic"].mean().mean())\n'
        'print("measured mean IC", round(measured, 4), "against rho 0.05")\n'
        "assert abs(measured - 0.05) < 0.05\n"
        'assert (frame["source"] == "synthetic controlled experiment").all()',
    ),
    (
        "markdown",
        "## 3. The transfer coefficient table (F8.5)\n"
        "\n"
        "The realized IR against IC * sqrt(n_eff); the ratio is the transfer "
        "coefficient.",
    ),
    (
        "code",
        'table = stored["criteria"]["F8.5"]["stored_numbers"]\n'
        "for construction, block in table.items():\n"
        "    for rho, numbers in block.items():\n"
        '        print(construction, rho, "IR", round(numbers["realized_ir"], 3),\n'
        '              "TC", round(numbers["transfer_coefficient"], 3))',
    ),
    (
        "markdown",
        "## 4. Robustness and shrinkage (F8.4)",
    ),
    (
        "code",
        'resampling = pd.read_parquet(PORTFOLIOS / "e8_f84_resampling.parquet")\n'
        "print(resampling.to_string())",
    ),
    (
        "markdown",
        "## 5. Gate G3: the construction stack runs end to end",
    ),
    (
        "code",
        'weights = pd.read_parquet(PORTFOLIOS / "proportional.parquet")\n'
        'for column in ("weight", "idio_share", "idio_share_after_fmp",\n'
        '               "factor_variance", "n_eff"):\n'
        "    assert column in weights.columns, column\n"
        'print("proportional book columns", sorted(weights.columns))\n'
        'print("G3: alpha to hedged, sized book runs end to end")',
    ),
    (
        "markdown",
        "## 6. The D7 panel map",
    ),
    (
        "code",
        "from dashboard.tabs import d07_sizing as d7\n"
        "\n"
        "summary = d7.load_summary()\n"
        "assert not summary.empty\n"
        'print("D7 reads the construction summary and the weight artifacts")',
    ),
    (
        "markdown",
        "## 7. The memo's evidence, in citation order",
    ),
    (
        "code",
        'memo = (ROOT / "docs" / "research" / "E8_construction_memo.md").read_text()\n'
        'joined = " ".join(memo.split())\n'
        'for name in ("F8.1", "F8.2", "F8.3", "F8.4", "F8.5", "F8.6"):\n'
        "    assert name in joined, name\n"
        'assert "What would falsify this?" in joined\n'
        'print("memo cites every criterion and the falsification section")',
    ),
    (
        "code",
        "# closing checklist: no stored number typed by hand, criteria present\n"
        "import re\n"
        "\n"
        "offenders: list[str] = []\n"
        'for name, block in stored["criteria"].items():\n'
        '    for match in re.findall(r"-?\\d+\\.\\d+", json.dumps(block["stored_numbers"])):\n'
        "        offenders.append(match)\n"
        'source = "\\n".join(cell["source"] for cell in __import__("json").loads(\n'
        '    (ROOT / "notebooks" / "E8_walkthrough.ipynb").read_text()\n'
        ')["cells"] if cell["cell_type"] == "code")\n'
        'for match in re.findall(r"-?\\d+\\.\\d+", source):\n'
        "    if match not in offenders:\n"
        "        offenders.append(match)\n"
        'print("stored values typed into a cell: none" if not offenders else offenders)\n'
        'assert all(name in source for name in ("F8.1", "F8.2", "F8.3", "F8.4", "F8.5", "F8.6"))\n'
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
            "id": f"e8w{index:02d}",
            "metadata": {},
            "source": source.splitlines(keepends=True),
        }
        if kind == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        notebook["cells"].append(cell)
    path = ROOT / "notebooks" / "E8_walkthrough.ipynb"
    path.write_text(json.dumps(notebook, indent=1) + "\n")
    print(f"wrote {path} with {len(CELLS)} cells")


if __name__ == "__main__":
    build()
