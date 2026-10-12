"""The seed covers every file a live path reads, or the run refuses before trading."""

from __future__ import annotations

import pathlib
from pathlib import Path

import pytest

from live import seed


def test_a_tree_missing_an_input_names_the_step_and_the_file(tmp_path: Path) -> None:
    # 2026-10-09's own gap: the bundle held no `models/TS-v1/beta_history.parquet`, so
    # the attribution step was refused at its read and the evening still ended `ok`.
    for rel in seed.live_inputs():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    (tmp_path / "models/TS-v1/beta_history.parquet").unlink()
    with pytest.raises(seed.SeedUnavailable, match="attribution needs models/TS-v1"):
        seed.preflight_inputs(tmp_path)
    # The message says what to do about it, because the next reader is the one who
    # has to push the file.
    with pytest.raises(seed.SeedUnavailable, match="seed change"):
        seed.preflight_inputs(tmp_path)


def test_a_tree_holding_every_input_passes_and_counts_them(tmp_path: Path) -> None:
    for rel in seed.live_inputs():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    assert seed.preflight_inputs(tmp_path) == len(seed.live_inputs())


def test_the_declaration_covers_a_live_step_s_own_reads(tmp_path: Path) -> None:
    # The other direction: given the reads a real step recorded, none may be
    # undeclared. The step here is the cheap one - the reader the attribution block
    # uses for its beta history - wrapped in the run's own recorder.
    import pandas as pd

    from efb import attribution

    tree = tmp_path / "tree"
    (tree / "models" / "TS-v1").mkdir(parents=True)
    panel = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
            "ticker": ["AAA", "AAA"],
            "method": ["raw", "raw"],
            "beta": [1.0, 1.1],
        }
    )
    panel.to_parquet(tree / "models" / "TS-v1" / "beta_history.parquet", index=False)
    panel_reader = attribution.ModelPanel.__new__(attribution.ModelPanel)
    panel_reader.root = tree
    with seed.record_reads() as opened:
        betas = panel_reader._read_betas()
    assert list(betas.columns) == ["date", "ticker", "beta"]
    assert seed.relative_reads(tree, opened) == ["models/TS-v1/beta_history.parquet"]
    assert seed.undeclared_reads(tree, opened) == []


def test_the_declaration_is_a_list_of_paths_and_not_a_discovery() -> None:
    # Every entry is a relative path under the tree: an absolute one would pass the
    # preflight on the machine that wrote it and mean nothing anywhere else.
    for step, rels in seed.LIVE_INPUTS.items():
        assert rels, f"{step} declares nothing"
        for rel in rels:
            assert not rel.startswith("/"), f"{step} declares {rel}"
            assert rel.endswith(".parquet"), f"{step} declares {rel}"


def test_the_submission_path_reads_exactly_what_it_declares(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FIX 1: the declaration names the files this path reads, and no others.

    The entry called `morning` describes `live/morning_job.py::run_morning`, which the
    *evening* calls (`scripts/run_live_daily.py`) and `scripts/push_seed.py` rehearses
    under that name. It is not `scripts/reconcile_fills.py`: that job reads no artifact
    under `data/` at all - no `DATA_ROOT`, no `runroot`, no `read_parquet` - which is
    why the preflight's one call site, in the evening, is the only place the entry is
    checked.

    The read set is recorded rather than asserted from reading the code, so a change to
    what the path opens fails here instead of at an evening's refusal.
    """
    from live import morning_job, state

    proposal_dir = tmp_path / "proposals"
    state_dir = tmp_path / "state"
    log_dir = tmp_path / "logs"
    _write_proposal(proposal_dir, {"AAA": 0.05, "BBB": -0.05})
    monkeypatch.setattr(morning_job, "PROPOSAL_DIR", proposal_dir)
    monkeypatch.setattr(morning_job, "EXECUTION_LOG_DIR", log_dir)
    write_positions = state.write_positions
    monkeypatch.setattr(
        morning_job.state,
        "write_positions",
        lambda trade_date, rows: write_positions(trade_date, rows, state_dir=state_dir),
    )
    data = pathlib.Path(__file__).resolve().parents[1] / "data"
    with seed.record_reads() as opened:
        summary = morning_job.run_morning("2026-09-22", nav=100_000.0, data_root=data)
    assert summary["executed"] is True
    assert seed.relative_reads(data, opened) == [
        "raw/prices.parquet"
    ], "the submission path reads exactly what its entry declares"
    declared = sorted({rel for rels in seed.LIVE_INPUTS.values() for rel in rels})
    assert declared == seed.live_inputs()
    assert seed.undeclared_reads(data, opened) == []


def _write_proposal(proposal_dir: pathlib.Path, weights: dict[str, float]) -> None:
    import pandas as pd

    proposal_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "ticker": list(weights),
            "weight": [weights[ticker] for ticker in weights],
            "side": ["long" if weights[ticker] >= 0 else "short" for ticker in weights],
            "z": [0.0] * len(weights),
            "alpha": [0.0] * len(weights),
        }
    )
    frame.to_parquet(proposal_dir / "proposal_2026-09-22.parquet", index=False)


def test_the_declaration_still_covers_the_eight_live_inputs() -> None:
    # FIX 1 corrected one *entry* - the submission path does not read the returns
    # panel - and the union of declared paths, which is what the preflight checks the
    # seed against, is unchanged: eight files, the ones the production manifest holds.
    assert seed.live_inputs() == [
        "models/TS-v1/beta_history.parquet",
        "models/XS-v1/descriptors.parquet",
        "models/XS-v1/factor_returns.parquet",
        "models/XS-v1/specific_returns.parquet",
        "models/XS-v1/specific_var.parquet",
        "processed/returns.parquet",
        "processed/sectors.parquet",
        "raw/prices.parquet",
    ]
    assert sorted(seed.LIVE_INPUTS) == [
        "attribution",
        "evening",
        "prices",
        "submission",
    ]
