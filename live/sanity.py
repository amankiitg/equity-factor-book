"""Sprint E11 live: the day-1 sanity gate.

The clock does not start until this passes. The loop is run on two
consecutive real closes and the weight turnover between them is stored.
Two identical proposals on two different closes means the data is not
actually live and the gate fails.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from live import evening_job

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
GATE_PATH = ROOT / "live" / "sanity_gate.json"


def _weights(as_of: str) -> pd.Series:
    path = evening_job.PROPOSAL_DIR / f"proposal_{as_of}.parquet"
    frame = pd.read_parquet(path)
    return frame.set_index("ticker")["weight"].astype(float)


def _weight_turnover(before: pd.Series, after: pd.Series) -> float:
    """0.5 * sum(abs(w_t - w_{t-1})), the two-way turnover definition."""
    both = pd.concat([before.rename("before"), after.rename("after")], axis=1).fillna(
        0.0
    )
    return float(0.5 * (both["after"] - both["before"]).abs().sum())


def run_gate(
    data_root: Path = DATA_ROOT,
    nav: float = evening_job.PAPER_NAV,
    path: Path = GATE_PATH,
) -> dict:
    """Run the loop on the two most recent closes and store the turnover."""
    wide, _counts = evening_job.eval_risk.load_clean_wide(data_root)
    closes = sorted(wide.index.unique())[-2:]
    before = evening_job.build_proposal(data_root, as_of=closes[0], nav=nav, store=True)
    after = evening_job.build_proposal(data_root, as_of=closes[1], nav=nav, store=True)
    w_before = _weights(str(before["as_of"]))
    w_after = _weights(str(after["as_of"]))
    turnover = _weight_turnover(w_before, w_after)
    result = {
        "closes": [str(pd.Timestamp(d).date()) for d in closes],
        "n_names_before": before["n_names"],
        "n_names_after": after["n_names"],
        "weight_turnover": turnover,
        "definition": "0.5 * sum(abs(w_t - w_{t-1}))",
        "proposals_differ": bool(turnover > 0),
        "passed": bool(turnover > 0),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result
