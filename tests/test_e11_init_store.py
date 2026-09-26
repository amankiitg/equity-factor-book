"""Sprint E11, C0: first-run detection is explicit, never inferred.

`EFB_INIT_STORE` is parsed strictly and the seed marker is what "seeded" means,
so the four states a store can be in are told apart rather than guessed at: an
empty store refuses to run unless the flag says this is the first run, a flag
left set on a seeded store fails the evening, and a seeded store whose appendix
is empty is an error whatever the flag says because the data was lost.

The marker is its own table for a reason: the owner's pre-first-run database
check (`scripts/verify_store_roundtrip.py`) records a `run_status` row of its
own, and a store that holds rows is not evidence of a seed.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from live import appendix, notify, runroot, staleness, store
from scripts import run_live_daily

ROOT = Path(__file__).resolve().parents[1]
MARKER_WRITTEN_AT = "2026-09-25T22:30:00+00:00"
FAKE_KEY = "re_" + "AbCdEf123456_ghIJKl7890"
FAKE_TO = "owner@example.com"


def _local_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty store under the local fallback, which is the whole of `efb`."""
    where = tmp_path / "store"
    monkeypatch.setattr(store, "LOCAL_DIR", where)
    return where


def _write_marker() -> None:
    store.write_seed_marker(
        seeded_from=appendix.SEED_FROM.date().isoformat(),
        data_hash="abc123",
        written_at=MARKER_WRITTEN_AT,
    )


def _one_appendix_row() -> None:
    """One prices row, so the store is seeded rather than the empty case."""
    store.upsert("e11_prices", [{"trade_date": "2026-09-04", "ticker": "AAA"}])


def _record_hydrate(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Stand in for hydration and record how it was asked to run."""
    calls: list[bool] = []

    def _hydrate(*args: object, **kwargs: object) -> dict[str, int]:
        calls.append(bool(kwargs.get("seed_empty", args[1] if len(args) > 1 else True)))
        return {}

    monkeypatch.setattr(appendix, "hydrate", _hydrate)
    return calls


# The flag itself. -----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("false", False),
        ("FALSE", False),
        (" false ", False),
        ("true", True),
        ("TRUE", True),
        (" True ", True),
    ],
)
def test_the_first_run_flag_is_parsed_strictly(
    value: str | None, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    if value is None:
        monkeypatch.delenv(store.INIT_STORE_ENV, raising=False)
    else:
        monkeypatch.setenv(store.INIT_STORE_ENV, value)
    assert store.init_store_flag() is expected


@pytest.mark.parametrize("value", ["yes", "1", "0", "maybe", "tru"])
def test_any_other_first_run_value_is_an_error_that_names_it(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A spelling nobody meant must not be read as permission to seed."""
    monkeypatch.setenv(store.INIT_STORE_ENV, value)
    with pytest.raises(store.StoreNotConfigured) as err:
        store.init_store_flag()
    assert store.INIT_STORE_ENV in str(err.value)
    assert repr(value) in str(err.value)


# Case 1: no marker, the flag is not `true`. ---------------------------------


def test_no_marker_without_the_flag_refuses_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(store.INIT_STORE_ENV, raising=False)
    _local_store(tmp_path, monkeypatch)
    calls = _record_hydrate(monkeypatch)

    with pytest.raises(appendix.StoreNotSeeded) as err:
        appendix.open_store()

    assert str(err.value) == (
        "store not seeded: set EFB_INIT_STORE=true for the first run only"
    )
    assert calls == []
    assert store.seed_marker() is None
    assert appendix.is_empty() is True


# Case 2: no marker, the flag is `true`. -------------------------------------


def test_no_marker_with_the_flag_seeds_and_writes_the_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(store.INIT_STORE_ENV, "true")
    _local_store(tmp_path, monkeypatch)
    calls = _record_hydrate(monkeypatch)
    committed = json.loads((appendix.DATA_ROOT / "VERSION.json").read_text())

    seeded = appendix.open_store(now=datetime.fromisoformat(MARKER_WRITTEN_AT))

    assert seeded is True
    assert calls == [True]  # seeded, not merely hydrated
    marker = store.seed_marker()
    assert marker is not None
    assert marker["marker"] == store.SEED_MARKER_KEY
    assert marker["seeded_from"] == appendix.SEED_FROM.date().isoformat()
    assert marker["data_hash"] == committed["data_hash"]
    assert marker["written_at"] == MARKER_WRITTEN_AT


# Case 3: a marker, and the flag is `true`. ----------------------------------


def test_a_marker_with_the_flag_refuses_and_does_not_reseed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(store.INIT_STORE_ENV, "true")
    _local_store(tmp_path, monkeypatch)
    _write_marker()
    _one_appendix_row()
    calls = _record_hydrate(monkeypatch)

    with pytest.raises(appendix.StoreAlreadySeeded) as err:
        appendix.open_store()

    assert str(err.value) == "store already seeded: remove EFB_INIT_STORE"
    assert calls == []
    assert store.seed_marker()["data_hash"] == "abc123"  # nothing was replaced


# Case 4: a marker, and the appendix holds nothing. --------------------------


@pytest.mark.parametrize("flag", [None, "true"])
def test_a_marker_with_an_empty_appendix_refuses_whatever_the_flag_says(
    flag: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Data was lost after the seed, and it is never re-seeded automatically."""
    if flag is None:
        monkeypatch.delenv(store.INIT_STORE_ENV, raising=False)
    else:
        monkeypatch.setenv(store.INIT_STORE_ENV, flag)
    _local_store(tmp_path, monkeypatch)
    _write_marker()
    calls = _record_hydrate(monkeypatch)

    with pytest.raises(appendix.StoreAppendixLost) as err:
        appendix.open_store()

    assert "never re-seeded automatically" in str(err.value)
    assert calls == []
    assert store.seed_marker()["data_hash"] == "abc123"


# What "seeded" does not mean. ----------------------------------------------


def test_the_roundtrip_rows_do_not_count_as_a_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner's database check writes rows before the first run, and cannot
    make the store look seeded: the marker is the only thing that does."""
    monkeypatch.delenv(store.INIT_STORE_ENV, raising=False)
    _local_store(tmp_path, monkeypatch)
    staleness.write_run_status(
        {
            "job": "store_roundtrip",
            "target_close": "2026-09-21",
            "status": "ok",
            "checked_at": MARKER_WRITTEN_AT,
        },
        run_date="2026-09-25",
        dry_run=True,
    )

    assert not store.select("run_status").empty
    assert store.seed_marker() is None
    with pytest.raises(appendix.StoreNotSeeded):
        appendix.open_store()


# The run's own record and message. -----------------------------------------


def test_a_refusal_fails_the_run_and_names_the_fix_in_the_email(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(store.INIT_STORE_ENV, raising=False)
    _local_store(tmp_path, monkeypatch)
    # The run tree is stubbed: this test refuses before anything reads the
    # artifacts, and the guard under test is the store's, not the seed's.
    monkeypatch.setattr(
        runroot, "prepare", lambda *args, **kwargs: runroot.DEFAULT_SEED_ROOT
    )
    # `adopt` moves every live module's DATA_ROOT for the rest of the process, so
    # each one is pinned through monkeypatch here and put back after the test.
    from live import evening_job, extend, morning_job, reconcile, sanity

    for module in (
        appendix,
        evening_job,
        extend,
        morning_job,
        reconcile,
        sanity,
        staleness,
    ):
        monkeypatch.setattr(module, "DATA_ROOT", module.DATA_ROOT)
    monkeypatch.setattr(run_live_daily, "already_ran", lambda job, day: False)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload)
    )

    assert run_live_daily.main() == 1

    assert len(sent) == 1
    assert "store not seeded: set EFB_INIT_STORE=true for the first run only" in str(
        sent[0]["text"]
    )
    assert str(sent[0]["subject"]).startswith("EFB ERROR")
    row = store.select("run_status").iloc[0]
    assert row["status"] == "error"
    assert "store not seeded" in str(row["detail"])
    assert bool(row["init"]) is False


def test_a_first_run_says_so_in_the_subject_the_first_line_and_the_row() -> None:
    message = notify.compose(
        status="ok",
        target_close="2026-09-22",
        dry_run=True,
        orders=150,
        gross=2_000_000.0,
        worst_input="prices",
        worst_sessions_behind=0,
        store="postgres/efb",
        init=True,
    )
    lines = message.splitlines()
    assert lines[0] == "store: postgres/efb, first run"
    assert lines[1] == (
        "EFB live book 2026-09-22: ok, the run completed "
        "(first run, the store was seeded)"
    )
    subject = notify.subject_text(
        status="ok",
        target_close="2026-09-22",
        dry_run=True,
        orders=150,
        worst_input="prices",
        worst_sessions_behind=0,
        init=True,
    )
    assert subject.startswith("EFB ok (first run) 2026-09-22 | 150 proposed, none sent")
    # the first run after a gap can also be a catch-up, and one is not the other
    both = notify.subject_text(
        status="ok",
        target_close="2026-09-22",
        dry_run=True,
        orders=150,
        worst_input="prices",
        worst_sessions_behind=0,
        catch_up_sessions=["2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21"],
        init=True,
    )
    assert both.startswith("EFB ok (catch-up 4, first run) 2026-09-22")

    result = {"job": "live_daily", "target_close": "2026-09-22", "status": "ok"}
    assert (
        staleness.run_status_row(result, run_date="2026-09-22", init=True)["init"]
        is True
    )
    assert staleness.run_status_row(result, run_date="2026-09-22")["init"] is False


# The rule end to end, on real bytes. ---------------------------------------


@pytest.mark.slow
def test_a_first_run_seeds_the_real_appendix_and_the_second_run_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seed once from the committed artifacts, then read them on the next run."""
    root = tmp_path / "data"
    for spec in appendix.SPECS:
        source = appendix.DATA_ROOT / spec.path
        target = root / spec.path
        if spec.name == "universe":
            target.mkdir(parents=True, exist_ok=True)
            for file in sorted(source.glob("*.parquet")):
                shutil.copy2(file, target / file.name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(appendix.DATA_ROOT / "VERSION.json", root / "VERSION.json")
    _local_store(tmp_path, monkeypatch)

    monkeypatch.setenv(store.INIT_STORE_ENV, "true")
    assert appendix.open_store(root) is True
    marker = store.seed_marker()
    assert marker is not None
    assert (
        marker["data_hash"]
        == json.loads((appendix.DATA_ROOT / "VERSION.json").read_text())["data_hash"]
    )
    assert appendix.is_empty() is False
    after_seed = {
        spec.name: len(appendix.read_appendix(spec)) for spec in appendix.SPECS
    }

    # The flag comes off after the first run, and the next evening reads the
    # appendix rather than re-seeding it.
    monkeypatch.delenv(store.INIT_STORE_ENV, raising=False)
    assert appendix.open_store(root) is False
    assert {
        spec.name: len(appendix.read_appendix(spec)) for spec in appendix.SPECS
    } == after_seed
    assert store.seed_marker() == marker
