"""The published turnover is the legs sent, and the built figure travels beside it."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from live import snapshot

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_live_daily.py"


def _evening_module() -> Any:
    # `scripts/` is not a package, so the helper is loaded by path rather than by
    # import. Only the one function is used, and it takes plain arguments.
    spec = importlib.util.spec_from_file_location("nov11_evening", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_snapshot_publishes_both_halves():
    # 2026-10-09's own numbers: 193 legs built for $388,402.25, 171 sent for
    # $379,430.49, so $8,971.76 was never sent.
    block = _evening_module()._with_sent_halves(
        {"intended_notional": 388_402.25},
        sent_notional=379_430.49,
        built=388_402.25,
    )
    assert block["sent_notional"] == 379_430.49
    assert block["unsent_notional"] == pytest.approx(8_971.76)
    assert block["intended_notional"] == 388_402.25


def test_an_unknown_half_publishes_nothing_rather_than_a_zero():
    module = _evening_module()
    assert (
        module._with_sent_halves(
            {"intended_notional": 388_402.25}, sent_notional=None, built=388_402.25
        ).get("sent_notional")
        is None
    )
    unknown_built = module._with_sent_halves({}, sent_notional=1.0, built=None)
    assert unknown_built.get("unsent_notional") is None


def test_a_sent_figure_larger_than_the_built_one_is_not_published(caplog: Any):
    # A break in the bookkeeping, not a negative "never sent": the halves are
    # withheld and the warning names it, which is what the run's log is for.
    with caplog.at_level("WARNING"):
        block = _evening_module()._with_sent_halves(
            {"intended_notional": 100.0}, sent_notional=200.0, built=100.0
        )
    assert "sent_notional" not in block
    assert "exceeds the built notional" in caplog.text


def test_the_document_carries_the_keys_and_nulls_them_when_absent():
    # The key is in the document's own shape, always: a page reading `null` and a
    # page reading a missing key must not be able to differ.
    both_halves = {
        "intended_notional": 388_402.25,
        "sent_notional": 379_430.49,
        "unsent_notional": 8_971.76,
    }
    for block in (both_halves, {"intended_notional": 388_402.25}):
        document = snapshot.build(
            run={"target_close": "2026-10-09"},
            reconciliation=block,
        )
        published = document["reconciliation"]
        assert "sent_notional" in published
        assert "unsent_notional" in published
    lone = snapshot.build(run={}, reconciliation={"sent_notional": 1.0})
    assert lone["reconciliation"]["sent_notional"] == 1.0
