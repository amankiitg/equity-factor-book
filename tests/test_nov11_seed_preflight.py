"""The seed covers every file a live path reads, or the run refuses before trading."""

from __future__ import annotations

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
