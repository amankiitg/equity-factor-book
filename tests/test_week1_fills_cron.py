"""The morning fills job: what it writes, what it refuses to do, what it says.

The job is read-only against the broker by construction, and these tests are what
hold that: the client they install raises on `submit_order`, the sizing and
proposal entry points are patched to raise, and the writes are recorded so the set
of tables it touches is asserted rather than assumed.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from live import alpaca, notify, positions, staleness, store
from scripts import reconcile_fills, run_live_daily

ROOT = Path(__file__).resolve().parents[1]
CLOSE = "2026-10-01"
TODAY = "2026-10-02"

PUBLISHED: dict[str, Any] = {
    "schema_version": 1,
    "generated_at": "2026-10-01T22:49:53.322476Z",
    "target_close": "2026-10-01T00:00:00",
    "book_as_of": "2026-10-01T00:00:00",
    "dry_run": False,
    "store": "postgres/efb",
    "run_status": {"status": "ok"},
    "book": {
        "n_names": 2,
        "n_kept": 2,
        "expected_cost_bps": 14.15,
        "names": [
            {"ticker": "DG", "weight": 0.01, "side": "short"},
            {"ticker": "AAA", "weight": 0.02, "side": "long"},
        ],
    },
}


def _order(
    status: str = "filled",
    *,
    order_id: str = "oid-dg",
    ticker: str = "DG",
    side: str = "sell",
    qty: str | None = "41",
    filled_qty: str | None = None,
    filled_avg_price: str | None = None,
    canceled_at: str | None = None,
    updated_at: str = "2026-10-02T13:30:00Z",
    position_intent: str = "sell_to_open",
):
    """A real Order, as the broker answers a read by id.

    A canceled order reports nothing filled: the 41 in the message is the quantity
    that was asked for, not the quantity that traded.
    """
    from alpaca.trading.models import Order

    if filled_qty is None:
        filled_qty = "41" if status == "filled" else "0"
    if filled_avg_price is None:
        filled_avg_price = "12.62" if status == "filled" else None
    return Order(
        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, order_id)),
        client_order_id=f"efb-2026-10-01-{ticker}-S-deadbeef",
        created_at="2026-10-01T22:30:00Z",
        updated_at=updated_at,
        submitted_at="2026-10-01T22:30:00Z",
        order_class="simple",
        time_in_force="day",
        status=status,
        extended_hours=False,
        symbol=ticker,
        side=side,
        qty=qty,
        filled_qty=filled_qty,
        filled_avg_price=filled_avg_price,
        canceled_at=canceled_at,
        position_intent=position_intent,
    )


class _Broker:
    """A client that answers reads and refuses to be sent anything."""

    def __init__(self, orders: dict[str, object]) -> None:
        self._orders = orders
        self.asked: list[str] = []
        self.submitted: list[object] = []

    def get_order_by_id(self, order_id: object) -> object:
        self.asked.append(str(order_id))
        return self._orders[str(order_id)]

    def submit_order(self, request: object) -> object:  # pragma: no cover - a guard
        self.submitted.append(request)
        raise AssertionError("the fills job must never send an order")


HOLDINGS: dict[str, Any] = {
    "held": {"AAA": 20000.0, "DG": -512.0},
    "held_quantities": {"AAA": 1000.0, "DG": -41.0},
    "nav": 998_580.38,
    "establishment": False,
    "matches": False,
    "note": "mismatch: the account holds 2 name(s) and the store 178",
    "source": "alpaca",
}


class _Harness:
    """One installed morning: the fakes, and what the job did with them."""

    def __init__(self, **kwargs: Any) -> None:
        self.broker: _Broker = kwargs["broker"]
        self.sent: list[dict[str, Any]] = kwargs["sent"]
        self.written: list[str] = kwargs["written"]
        self.published: list[tuple[str, str]] = kwargs["published"]
        self.recorded: list[tuple[str, str, str]] = kwargs["recorded"]


def _install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    broker_orders: dict[str, object],
    orders: pd.DataFrame | None = None,
    published: dict[str, Any] | None = None,
) -> _Harness:
    """Pin every edge of the job: store, broker, vendor, R2 and the message."""
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(staleness, "is_session", lambda day: True)
    monkeypatch.setattr(
        reconcile_fills,
        "previous_orders",
        lambda as_of=None: (
            CLOSE,
            (
                orders
                if orders is not None
                else pd.DataFrame(
                    [
                        {
                            "trade_date": CLOSE,
                            "ticker": "DG",
                            "intended_notional": 512.42,
                            "status": "ACCEPTED",
                            "reason_code": "",
                            "client_order_id": "efb-2026-10-01-DG-S-deadbeef",
                            "position_intent": "sell_to_open",
                            "broker_order_id": "oid-dg",
                        }
                    ]
                )
            ),
        ),
    )
    monkeypatch.setattr(
        reconcile_fills,
        "closes_for",
        lambda tickers, close, fetch=None: pd.Series({"DG": 12.5, "AAA": 20.0}),
    )
    monkeypatch.setattr(positions, "check", lambda **kwargs: HOLDINGS)
    broker = _Broker(broker_orders)
    monkeypatch.setattr(alpaca, "connect", lambda dry_run=True: broker)
    monkeypatch.setattr(run_live_daily, "already_ran", lambda job, day: False)
    recorded: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        run_live_daily,
        "record_run",
        lambda job, day, status, detail="": recorded.append((job, day, status)),
    )
    # A morning job or a proposal build here would be the failure this job exists
    # to make impossible, so both are patched to raise rather than to a no-op.
    monkeypatch.setattr(
        run_live_daily,
        "store_proposal",
        lambda *args, **kwargs: pytest.fail("the fills job priced a book"),
    )

    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload)
    )
    monkeypatch.setenv(notify.API_KEY_ENV, "re_" + "test-key-value")
    monkeypatch.setenv(notify.TO_ENV, "owner@example.com")

    text = json.dumps(published if published is not None else PUBLISHED)
    written: list[str] = []
    for name in ("upsert", "replace_by_date"):
        original = getattr(store, name)

        def recorder(*args: Any, _original=original, **kwargs: Any) -> Any:
            written.append(str(args[0]))
            return _original(*args, **kwargs)

        monkeypatch.setattr(store, name, recorder)

    published_keys: list[tuple[str, str]] = []
    from live import snapshot

    # The bucket: the read answers the document that is up, and every put is kept
    # so the test can read what the page would receive.
    monkeypatch.setattr(snapshot, "get_object_text", lambda *a, **k: text)
    monkeypatch.setattr(
        snapshot,
        "put_object",
        lambda key, body, **k: published_keys.append((key, body)),
    )
    return _Harness(
        broker=broker,
        sent=sent,
        written=written,
        published=published_keys,
        recorded=recorded,
    )


def test_it_writes_the_fills_for_the_evening_it_reconciles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _install(
        monkeypatch,
        tmp_path,
        broker_orders={
            "oid-dg": _order(
                "canceled",
                canceled_at="2026-10-02T12:15:00Z",
                updated_at="2026-10-02T12:15:00Z",
            )
        },
    )

    code = reconcile_fills.main([])

    assert code == 0
    stored = store.select("fills")
    assert list(stored["ticker"]) == ["DG"]
    row = stored.iloc[0]
    assert str(row["trade_date"])[:10] == CLOSE
    assert row["order_id"] == "oid-dg"
    assert row["status"] == "CANCELED"
    assert row["filled_quantity"] == 0.0
    assert str(row["cancel_time"]).startswith("2026-10-02T12:15")
    assert row["close_price"] == 12.5
    assert harness.broker.asked == ["oid-dg"], "the read is by the broker's id"
    assert harness.broker.submitted == []
    # One table for the reconciliation and one row for the run: no orders, no
    # positions, no proposal, no reconciliation row of the evening's.
    assert set(harness.written) == {"fills", "run_status"}, harness.written
    assert harness.recorded == [(reconcile_fills.JOB, TODAY, "ok")]


def test_its_own_rows_are_keyed_to_its_own_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The evening's run_status and cron_runs rows are keyed by job, so they are
    safe."""
    _install(monkeypatch, tmp_path, broker_orders={"oid-dg": _order("filled")})

    reconcile_fills.main([])

    row = store.select(staleness.TABLE).iloc[0]
    assert row["job"] == reconcile_fills.JOB != staleness.JOB
    assert str(row["target_close"])[:10] == CLOSE


def test_a_quiet_morning_sends_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every leg filled: the job records the day and says nothing to anyone."""
    harness = _install(
        monkeypatch, tmp_path, broker_orders={"oid-dg": _order("filled")}
    )

    code = reconcile_fills.main([])

    assert code == 0
    assert harness.sent == [], "an evening that filled sends no message"
    row = store.select(staleness.TABLE).iloc[0]
    assert row["status"] == "ok"
    assert row["notify_status"] == "not needed"
    assert "1 of 1 order(s) filled" in row["detail"]


def test_a_morning_with_a_miss_names_it_in_the_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _install(
        monkeypatch,
        tmp_path,
        broker_orders={
            "oid-dg": _order(
                "canceled",
                canceled_at="2026-10-02T12:15:00Z",
                updated_at="2026-10-02T12:15:00Z",
            )
        },
    )

    code = reconcile_fills.main([])

    assert code == 0
    assert len(harness.sent) == 1
    text = str(harness.sent[0]["text"])
    assert "Did not fill: DG sell_to_open 41 canceled 12:15 UTC." in text
    assert "Realized cost:" in text and "expected" in text
    assert "0 of 1 orders filled" in text


def test_the_snapshot_gains_the_actual_holdings_beside_the_target_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _install(
        monkeypatch, tmp_path, broker_orders={"oid-dg": _order("filled")}
    )

    reconcile_fills.main([])

    keys = [key for key, _ in harness.published]
    assert keys == ["latest.json", "snapshots/2026-10-01.json"]
    republished = json.loads(harness.published[0][1])
    section = republished["actual_holdings"]
    assert section["n_names"] == 2
    assert section["gross_notional"] == pytest.approx(20512.0)
    assert section["net_notional"] == pytest.approx(19488.0)
    assert [entry["ticker"] for entry in section["names"]] == ["AAA", "DG"]
    assert section["names"][0]["side"] == "long"
    assert section["names"][1]["side"] == "short"
    assert section["names"][0]["weight"] == pytest.approx(20000.0 / 998_580.38)
    assert section["fills"]["trade_date"] == CLOSE
    assert section["fills"]["n_filled"] == 1
    assert section["fills"]["expected_cost_bps"] == pytest.approx(14.15)
    # The target book the page was already showing is byte-identical: this job
    # adds a section and rewrites nothing else.
    assert republished["book"] == PUBLISHED["book"]
    assert republished["generated_at"] == PUBLISHED["generated_at"]
    for key in ("schema_version", "target_close", "book_as_of", "dry_run", "store"):
        assert republished[key] == PUBLISHED[key]


def test_a_closed_morning_reconciles_nothing_and_says_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A holiday settles nothing: the orders are still working at the broker."""
    harness = _install(
        monkeypatch, tmp_path, broker_orders={"oid-dg": _order("filled")}
    )
    monkeypatch.setattr(staleness, "is_session", lambda day: False)

    code = reconcile_fills.main([])

    assert code == 0
    assert harness.broker.asked == [] and harness.sent == []
    assert store.select("fills").empty


def test_the_job_has_no_sizing_and_no_submit_path_in_its_own_source() -> None:
    """The strongest form of "it cannot trade": no name for it in the code.

    The fakes above prove this path does not trade when it runs; this proves the
    path cannot be added by accident, because the module's own names, attributes
    and imports contain no entry point that sizes a book or sends an order. Read
    through the syntax tree rather than the text, so the prose around it is free
    to explain the rule without failing the test that enforces it.
    """
    import ast

    source = (ROOT / "scripts" / "reconcile_fills.py").read_text()
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
            if node.module:
                names.add(node.module.split(".")[-1])
        elif isinstance(node, ast.Import):
            names.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)

    forbidden = {
        "submit_market_orders",
        "submit_order",
        "MarketOrderRequest",
        "store_proposal",
        "build_proposal",
        "target_orders",
        "minimum_skips",
        "run_morning",
        "evening_job",
        "morning_job",
        "guards",
        "sizing",
        "optimize",
        "allocate",
    }
    assert not (names & forbidden), f"the fills job reaches {names & forbidden}"

    # the negative control: the evening's own script does name them, so this
    # grep is a check on the file rather than on the word list
    evening = (ROOT / "scripts" / "run_live_daily.py").read_text()
    for present in ("store_proposal", "run_morning", "morning_job"):
        assert present in evening

    # and the two entry points it does use are the read-only pair
    assert "run_live_daily.already_ran" in source
    assert "run_live_daily.record_run" in source
