"""Sprint E11 live: the day-1 sanity gate.

The clock does not start until this passes. The loop is run on two
consecutive real closes and the weight turnover between them is stored.
Two identical proposals on two different closes means the data is not
actually live and the gate fails.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

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
    data_root: Path | None = None,
    nav: float = evening_job.PAPER_NAV,
    path: Path = GATE_PATH,
) -> dict:
    """Run the loop on the two most recent closes and store the turnover.

    The gate also stores both breadths on each close and the as-of date of every
    model input, so a failure names the input that is not advancing rather
    than only reporting that the proposals matched.
    """
    root = Path(data_root) if data_root is not None else DATA_ROOT
    wide, _counts = evening_job.eval_risk.load_clean_wide(root)
    closes = sorted(wide.index.unique())[-2:]
    before = evening_job.build_proposal(root, as_of=closes[0], nav=nav, store=True)
    after = evening_job.build_proposal(root, as_of=closes[1], nav=nav, store=True)
    w_before = _weights(str(before["as_of"]))
    w_after = _weights(str(after["as_of"]))
    turnover = _weight_turnover(w_before, w_after)
    proposals_differ = bool(turnover > 0)
    before_inputs = cast(dict[str, str], before.get("input_as_of", {}))
    after_inputs = cast(dict[str, str], after.get("input_as_of", {}))
    stalled = sorted(
        key
        for key in after_inputs
        if key in before_inputs and after_inputs[key] == before_inputs[key]
    )
    result = {
        "closes": [str(pd.Timestamp(d).date()) for d in closes],
        "n_names_before": before["n_names"],
        "n_names_after": after["n_names"],
        "n_kept_before": before.get("n_kept"),
        "n_kept_after": after.get("n_kept"),
        "n_eff_full_book_before": before.get("n_eff_full_book"),
        "n_eff_full_book_after": after.get("n_eff_full_book"),
        "n_eff_kept_before": before.get("n_eff_kept"),
        "n_eff_kept_after": after.get("n_eff_kept"),
        "weight_turnover": turnover,
        "definition": "0.5 * sum(abs(w_t - w_{t-1}))",
        "proposals_differ": proposals_differ,
        "passed": proposals_differ,
        "input_as_of_before": before_inputs,
        "input_as_of_after": after_inputs,
        "max_input_staleness_days_before": before.get("max_input_staleness_days"),
        "max_input_staleness_days_after": after.get("max_input_staleness_days"),
        # a failure names the inputs whose as-of date did not advance between
        # the two closes; empty when the proposals differ
        "stalled_inputs": stalled if not proposals_differ else [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result
