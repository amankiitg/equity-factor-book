"""The previous close's deferrals are published beside this close's own list."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pandas as pd

from live import bridge, snapshot

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_live_daily.py"


def _evening_module() -> Any:
    spec = importlib.util.spec_from_file_location("nov11_evening_reversals", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _orders(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": ticker, "intended_notional": 1_000.0, "broker_order_id": broker}
            for ticker, broker in rows
        ]
    )


def test_the_evening_block_carries_the_previous_list_and_this_close_s_own():
    block = bridge.evening(
        close="2026-10-09",
        held_before=["AAA", "BEN"],
        book=["AAA", "BEN"],
        orders=_orders([("AAA", "id-1"), ("BEN", "")]),
        reversals=["BEN"],
        previous_reversals=["BEN", "F", "VZ", "ZTS"],
    )
    assert block["reversals_pending"] == ["BEN"]
    assert block["previous_reversals_pending"] == ["BEN", "F", "VZ", "ZTS"]


def test_an_unknown_previous_list_is_null_and_an_empty_one_is_a_list():
    # The page reads these two differently: null is a page that could not look, and
    # an empty list is the previous close having deferred nothing.
    unknown = bridge.evening(
        close="2026-10-09",
        held_before=["AAA"],
        book=["AAA"],
        orders=_orders([("AAA", "id-1")]),
    )
    assert unknown["previous_reversals_pending"] is None
    empty = bridge.evening(
        close="2026-10-09",
        held_before=["AAA"],
        book=["AAA"],
        orders=_orders([("AAA", "id-1")]),
        previous_reversals=[],
    )
    assert empty["previous_reversals_pending"] == []


def test_the_document_keeps_the_null_and_the_list_apart():
    published = snapshot._bridge_block(
        {
            "close": "2026-10-09",
            "reversals_pending": ["BEN"],
            "previous_reversals_pending": ["BEN", "F"],
        }
    )
    assert published["previous_reversals_pending"] == ["BEN", "F"]
    assert (
        snapshot._bridge_block(
            {"close": "2026-10-09", "previous_reversals_pending": None}
        )["previous_reversals_pending"]
        is None
    )
    no_key = snapshot._bridge_block({"close": "2026-10-09"})
    assert no_key.get("previous_reversals_pending") is None


SETTINGS = {"EFB_R2_BUCKET": "test-bucket"}


class _Body:
    """The one attribute `get_object_text` reads off an S3 response's body."""

    def __init__(self, text: str) -> None:
        self.text = text

    def read(self) -> bytes:
        return self.text.encode()


def test_the_published_document_is_read_for_its_own_list():
    seen: list[str] = []

    def getter(*, Bucket: str, Key: str) -> dict[str, Any]:
        seen.append(Key)
        return {
            "Body": _Body(
                json.dumps(
                    {
                        "target_close": "2026-10-08",
                        "bridge": {"reversals_pending": ["BEN", "F", "VZ", "ZTS"]},
                    }
                )
            )
        }

    close, block = snapshot.published_bridge(settings=SETTINGS, getter=getter)
    assert seen == [snapshot.LATEST_KEY]
    assert close == "2026-10-08"
    assert block is not None
    assert block["reversals_pending"] == ["BEN", "F", "VZ", "ZTS"]


def test_a_read_that_cannot_be_made_is_named_rather_than_guessed():
    def broken(**_kwargs: Any) -> Any:
        raise RuntimeError("no credentials")

    assert snapshot.published_bridge(settings=SETTINGS, getter=broken) == (None, None)

    def no_bridge(**_kwargs: Any) -> Any:
        return {"Body": _Body("[]")}

    assert snapshot.published_bridge(settings=SETTINGS, getter=no_bridge) == (
        None,
        None,
    )


def test_the_evening_passes_the_previous_list_only_for_another_close(monkeypatch: Any):
    module = _evening_module()
    calls: list[tuple[str | None, dict[str, Any] | None]] = []

    def published() -> tuple[str | None, dict[str, Any] | None]:
        return calls.pop(0)

    monkeypatch.setattr(snapshot, "published_bridge", published)
    calls.append(("2026-10-08", {"reversals_pending": ["BEN", "F"]}))
    assert module.previous_close_reversals("2026-10-09") == ["BEN", "F"]
    # A document naming this close is a rerun, and its list is this close's own.
    calls.append(("2026-10-09", {"reversals_pending": ["BEN"]}))
    assert module.previous_close_reversals("2026-10-09") is None
    # No document at all, and a document whose bridge carries no list.
    calls.append((None, None))
    assert module.previous_close_reversals("2026-10-09") is None
    calls.append(("2026-10-08", {"reversals_pending": "BEN"}))
    assert module.previous_close_reversals("2026-10-09") is None
