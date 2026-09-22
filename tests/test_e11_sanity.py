"""Sprint E11 live: the day-1 sanity gate."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from live import sanity


def test_weight_turnover_matches_the_definition() -> None:
    before = pd.Series({"AAA": 0.10, "BBB": -0.10})
    after = pd.Series({"AAA": 0.16, "BBB": -0.04})
    expected = 0.5 * (abs(0.16 - 0.10) + abs(-0.04 - (-0.10)))
    assert sanity._weight_turnover(before, after) == pytest.approx(expected)


def test_zero_turnover_means_identical_proposals() -> None:
    weights = pd.Series({"AAA": 0.10, "BBB": -0.10})
    assert sanity._weight_turnover(weights, weights) == 0.0


def test_run_gate_flags_differing_proposals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Wide:
        index = pd.DatetimeIndex(["2026-09-18", "2026-09-21"])

    monkeypatch.setattr(
        sanity.evening_job.eval_risk, "load_clean_wide", lambda root: (_Wide(), {})
    )
    manifests = {
        "2026-09-18": {"as_of": "2026-09-18", "n_names": 500},
        "2026-09-21": {"as_of": "2026-09-21", "n_names": 500},
    }

    def fake_build(data_root, as_of=None, nav=100000.0, store=True):
        stamp = str(pd.Timestamp(as_of).date())
        proposal_dir = tmp_path / "proposals"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        weights = (
            {"AAA": 0.05, "BBB": -0.05}
            if stamp == "2026-09-18"
            else {
                "AAA": 0.08,
                "BBB": -0.02,
            }
        )
        pd.DataFrame(
            {"ticker": list(weights), "weight": list(weights.values())}
        ).to_parquet(proposal_dir / f"proposal_{stamp}.parquet", index=False)
        return manifests[stamp]

    monkeypatch.setattr(sanity.evening_job, "build_proposal", fake_build)
    monkeypatch.setattr(sanity.evening_job, "PROPOSAL_DIR", tmp_path / "proposals")
    result = sanity.run_gate(path=tmp_path / "gate.json")
    assert result["passed"] is True
    assert result["weight_turnover"] > 0
    assert result["closes"] == ["2026-09-18", "2026-09-21"]
