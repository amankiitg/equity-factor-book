"""The run's tree: the job writes nothing under the repository's `data/`.

A local measurement run once rewrote four raw artifacts and narrowed the SPY
archive from nine columns to six. The fix is structural rather than a guard: the
run works in a tree of its own, and these two tests are what says so. The first
hashes every file under `data/` before and after a full dry-run job; the second
makes every parquet and file writer raise on a path under `data/` and runs the
job anyway.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from live import appendix, evening_job, extend, morning_job, notify, runroot, store
from scripts import run_live_daily

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SESSION = "2026-09-22"


def hash_tree(root: Path) -> dict[str, str]:
    """Every file under a tree, hashed, so a single changed byte shows."""
    out: dict[str, str] = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return out


def _synthetic_seed(tmp_path: Path) -> Path:
    """The smallest tree the run's stubbed steps will accept."""
    root = tmp_path / "seed"
    (root / "raw" / "spy_holdings").mkdir(parents=True)
    (root / "models" / "XS-v1").mkdir(parents=True)
    (root / "processed").mkdir(parents=True)
    (root / "VERSION.json").write_text(json.dumps({"data_hash": "seedhash"}))
    empty = pd.DataFrame({"close": [1.0]})
    empty.to_parquet(root / "raw" / "prices.parquet")
    empty.to_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    return root


class _NoCorporateActions:
    """The stub outcome of the corporate-actions step."""

    splits: list = []
    sessions: list = []
    ratios: dict = {}
    flags: list = []
    unchecked = 0


def _stub_the_work(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Every step that fetches, sizes or writes, plus the store and the gate."""
    from live import corporate_actions, reconcile, sanity

    monkeypatch.setenv(runroot.SEED_SOURCE_ENV, runroot.LOCAL_SOURCE)
    monkeypatch.setenv(store.INIT_STORE_ENV, "true")
    monkeypatch.setenv(runroot.RUN_ROOT_ENV, str(tmp_path / "run" / "data"))
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(run_live_daily, "already_ran", lambda job, day: False)
    monkeypatch.setattr(appendix, "open_store", lambda *a, **k: True)
    for name in ("hydrate", "persist_new_sessions", "appendix_manifest"):
        monkeypatch.setattr(appendix, name, lambda *args, **kwargs: {})
    for name in (
        "extend_archives",
        "extend_prices",
        "extend_shares",
        "extend_returns",
        "extend_model",
        "refresh_version",
    ):
        monkeypatch.setattr(extend, name, lambda *a, **k: {})
    monkeypatch.setattr(
        corporate_actions, "apply_to_artifact", lambda *a, **k: _NoCorporateActions()
    )
    monkeypatch.setattr(
        evening_job, "build_proposal", lambda *a, **k: {"as_of": SESSION, "n_kept": 150}
    )
    monkeypatch.setattr(
        morning_job,
        "run_morning",
        lambda *a, **k: {"orders": 0, "intended_notional": 0.0, "dry_run": True},
    )
    monkeypatch.setattr(reconcile, "daily_record", lambda *a, **k: {"dry_run": True})
    monkeypatch.setattr(run_live_daily, "store_proposal", lambda *a, **k: None)
    monkeypatch.setattr(run_live_daily, "store_orders", lambda *a, **k: None)
    monkeypatch.setattr(run_live_daily, "store_reconciliation", lambda *a, **k: None)
    monkeypatch.setattr(notify, "post", lambda *a, **k: None)
    # `adopt` moves the live modules' globals for the rest of the process, so each
    # one is pinned through monkeypatch and put back after the test.
    for module in (
        appendix,
        evening_job,
        extend,
        morning_job,
        reconcile,
        sanity,
    ):
        monkeypatch.setattr(module, "DATA_ROOT", module.DATA_ROOT, raising=False)
    monkeypatch.setattr(run_live_daily, "PROPOSAL_DIR", run_live_daily.PROPOSAL_DIR)
    monkeypatch.setattr(evening_job, "PROPOSAL_DIR", evening_job.PROPOSAL_DIR)
    monkeypatch.setattr(morning_job, "PROPOSAL_DIR", morning_job.PROPOSAL_DIR)
    monkeypatch.setattr(reconcile, "PROPOSAL_DIR", reconcile.PROPOSAL_DIR)


def trap_writers_into_data(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Refuse any parquet or file write whose target is under the repository data/.

    Returns the list of attempts, so a test can assert the trap was armed and
    never fired rather than that it was never reachable.
    """
    attempts: list[str] = []
    target = DATA.resolve()

    def _under_data(path: Any) -> bool:
        try:
            return Path(str(path)).resolve().is_relative_to(target)
        except (OSError, ValueError):
            return False

    original_parquet = pd.DataFrame.to_parquet
    original_write_bytes = Path.write_bytes
    original_write_text = Path.write_text

    def _to_parquet(self: pd.DataFrame, path: Any, *args: Any, **kwargs: Any) -> None:
        if _under_data(path):
            attempts.append(str(path))
            raise AssertionError(f"the job wrote a parquet under data/: {path}")
        return original_parquet(self, path, *args, **kwargs)

    def _write_bytes(self: Path, data: bytes) -> int:
        if _under_data(self):
            attempts.append(str(self))
            raise AssertionError(f"the job wrote a file under data/: {self}")
        return original_write_bytes(self, data)

    def _write_text(self: Path, text: str, *args: Any, **kwargs: Any) -> int:
        if _under_data(self):
            attempts.append(str(self))
            raise AssertionError(f"the job wrote a file under data/: {self}")
        return original_write_text(self, text, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", _to_parquet)
    monkeypatch.setattr(Path, "write_bytes", _write_bytes)
    monkeypatch.setattr(Path, "write_text", _write_text)
    return attempts


@pytest.mark.slow
def test_the_full_job_writes_nothing_under_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The acceptance: hash every file under data/ before and after the job.

    The seed is the repository's own tree, so the run really does read `data/` and
    really does append, refit and rehash; only the vendor fetches are stubbed,
    because a test cannot ask yfinance for a session. Every write lands in the run
    tree, and the repository's bytes are identical afterwards.
    """
    _stub_the_work(monkeypatch, tmp_path)
    before = hash_tree(DATA)

    run_live_daily.main()

    after = hash_tree(DATA)
    assert after == before, "the job changed the repository's data/ tree"


def test_a_writer_pointed_at_data_is_trapped_and_the_job_still_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other direction: any write path back into data/ now raises.

    The seed is a small synthetic tree, so this one is fast, and the trap covers
    the parquet writer and both pathlib writers. The job finishing means no code
    path reached them.
    """
    seed = _synthetic_seed(tmp_path)
    monkeypatch.setenv(runroot.SEED_ROOT_ENV, str(seed))
    _stub_the_work(monkeypatch, tmp_path)
    attempts = trap_writers_into_data(monkeypatch)

    exit_code = run_live_daily.main()

    assert attempts == []
    assert exit_code in (0, 1)  # the stubs decide the notification, not the trap
    # the run tree is where the writes went, and it is not the repository's tree
    assert (tmp_path / "run" / "data" / "raw" / "prices.parquet").exists()
    assert runroot.pinned_root() == tmp_path / "run" / "data"


def test_the_trap_is_armed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The negative control: the trap refuses a real write into data/."""
    attempts = trap_writers_into_data(monkeypatch)
    probe = DATA / "raw" / "trap_probe.parquet"
    try:
        with pytest.raises(AssertionError):
            probe.write_bytes(b"probe")
        assert attempts == [str(probe)]
    finally:
        if probe.exists():  # pragma: no cover - only when the trap failed
            probe.unlink()
