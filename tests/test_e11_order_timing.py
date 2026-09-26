"""Sprint E11 pre-flip, item 1: the order timing rule and its smoke test.

The cron fires at 22:30 UTC, after the close and inside the after-hours window.
Alpaca rejects `opg` in that window ("OPG orders submitted after 9:28am but
before 7:00pm ET will be rejected"), so the loop's time-in-force is `day`, which
is queued and submitted the next trading day. The tests below pin the rule, the
window the smoke test insists on, and the smoke test's own behaviour against a
fake paper client: one 1-share order, verified, then cancelled.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from live import alpaca
from scripts import smoke_order_timing

ROOT = Path(__file__).resolve().parents[1]


def test_the_time_in_force_is_day_and_the_rule_is_written_down() -> None:
    """`opg` is rejected at the cron's hour, and the citation says so."""
    assert alpaca.NEXT_OPEN_TIF == "day"
    source = (ROOT / "live" / "alpaca.py").read_text()
    # the two facts the choice rests on, quoted from Alpaca's own page
    assert "before 7:00pm ET will be rejected" in source
    assert "it is queued and submitted the following trading day" in source
    assert "docs.alpaca.markets/docs/orders-at-alpaca#time-in-force" in source
    # and the loop uses it rather than an enum spelling of its own
    assert "TimeInForce(NEXT_OPEN_TIF)" in source
    assert "TimeInForce.DAY" not in source


@pytest.mark.parametrize(
    ("stamp", "inside"),
    [
        ("2026-09-28T18:30:00-04:00", True),  # the cron's summer slot
        ("2026-11-30T18:30:00-05:00", True),  # the winter slot, same UTC hour
        ("2026-09-28T16:00:00-04:00", True),  # the close itself
        ("2026-09-28T19:59:00-04:00", True),
        ("2026-09-28T20:00:00-04:00", False),  # overnight session opens
        ("2026-09-28T15:59:00-04:00", False),  # before the close
        ("2026-09-28T10:00:00-04:00", False),  # the middle of the session
    ],
)
def test_the_cron_window_is_the_after_hours_window(stamp: str, inside: bool) -> None:
    assert smoke_order_timing.in_cron_window(datetime.fromisoformat(stamp)) is inside


class _Order:
    def __init__(self, order_id: str = "order-1", status: str = "accepted") -> None:
        self.id = order_id
        self.status = status
        self.client_order_id = "efb-timing-smoke-test"


class _Asset:
    tradable = True
    shortable = True


class _Account:
    id = "paper-account"
    buying_power = "1000000"


class _FakeClient:
    """A paper client that records what it was asked to do."""

    def __init__(self, status_after_submit: str = "accepted") -> None:
        self.requests: list[Any] = []
        self.cancelled: list[str] = []
        self._status = status_after_submit

    def submit_order(self, order_data: Any) -> _Order:
        self.requests.append(order_data)
        return _Order(status=self._status)

    def get_order(self, order_id: str) -> _Order:
        return _Order(order_id=order_id, status=self._status)

    def cancel_order_by_id(self, order_id: str) -> None:
        self.cancelled.append(order_id)
        self._status = "canceled"

    def get_account(self) -> _Account:
        return _Account()

    def get_asset(self, symbol: str) -> _Asset:
        return _Asset()


def test_the_smoke_test_submits_one_share_then_cancels() -> None:
    client = _FakeClient()
    report = smoke_order_timing.submit_verify_cancel(
        client,
        symbol="SPY",
        now=datetime(2026, 9, 28, 22, 30, tzinfo=UTC),  # the cron's slot
    )
    assert len(client.requests) == 1
    request = client.requests[0]
    assert int(request.qty) == 1
    assert str(request.symbol) == "SPY"
    # alpaca-py's enums are `str, Enum`, so `str()` gives the member's name
    assert getattr(request.time_in_force, "value", None) == alpaca.NEXT_OPEN_TIF
    assert request.notional is None
    assert client.cancelled == ["order-1"]
    assert report["status_after_submit"] == "accepted"
    assert report["status_after_cancel"] == "canceled"
    assert report["in_cron_window"] is True
    assert report["time_in_force"] == "day"


def test_a_refused_order_raises_with_the_broker_status_and_is_not_cancelled() -> None:
    """A rejection must be loud, and must not be followed by a pointless cancel."""
    client = _FakeClient(status_after_submit="rejected")
    with pytest.raises(RuntimeError, match="rejected"):
        smoke_order_timing.submit_verify_cancel(
            client, symbol="SPY", now=datetime(2026, 9, 28, 22, 30, tzinfo=UTC)
        )
    assert client.cancelled == []


def test_the_script_refuses_without_yes_and_outside_the_window(
    capsys: pytest.CaptureFixture[str],
) -> None:
    in_window = datetime(2026, 9, 28, 22, 30, tzinfo=UTC)
    assert (
        smoke_order_timing.main(
            ["--symbol", "SPY"], client=_FakeClient(), now=in_window
        )
        == 2
    )
    assert "--yes" in capsys.readouterr().out

    # With --yes but outside the window, the hour still refuses it, and nothing
    # is submitted: an order accepted at another hour proves nothing.
    outside = _FakeClient()
    assert (
        smoke_order_timing.main(
            ["--symbol", "SPY", "--yes"],
            client=outside,
            now=datetime(2026, 9, 28, 10, 0, tzinfo=UTC),
        )
        == 2
    )
    assert "--force-hour" in capsys.readouterr().out
    assert outside.requests == []

    # --force-hour is the deliberate escape hatch, and it submits.
    forced = _FakeClient()
    assert (
        smoke_order_timing.main(
            ["--symbol", "SPY", "--yes", "--force-hour"],
            client=forced,
            now=datetime(2026, 9, 28, 10, 0, tzinfo=UTC),
        )
        == 0
    )
    assert len(forced.requests) == 1
    assert forced.cancelled == ["order-1"]


def test_a_non_tradable_symbol_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _Untradable(_FakeClient):
        def get_asset(self, symbol: str) -> Any:
            class _A:
                tradable = False
                shortable = False

            return _A()

    client = _Untradable()
    assert (
        smoke_order_timing.main(
            ["--symbol", "XYZ", "--yes"],
            client=client,
            now=datetime(2026, 9, 28, 22, 30, tzinfo=UTC),
        )
        == 2
    )
    assert "not tradable" in capsys.readouterr().out
    assert client.requests == []
