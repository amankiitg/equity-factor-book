"""Sprint E11 pre-flip, item 4: a refused short is a record, never a crash.

Credit-trading-lab v9.2 is the pattern, and it is a post-mortem from 2026-09-24,
not a theory: one Alpaca rejection of an unhandled `sell_to_open` propagated out
of `main()`, so the five legs that had filled were never written back and the
position cache sat a day behind the broker. Two things came out of it, and both
are here.

First, a live shortability check before every short. Shortability is not static:
the same name filled sell_to_open on three September days and reported
`shortable=false` on the fourth, so the flags are read from the broker per run.
Both `shortable` and `easy_to_borrow` are checked, and the refusal names the first
thing that was actually wrong.

Second, per-leg failure isolation. An `APIError` means the broker evaluated the
order and declined it: the state is known, so the leg is recorded with its code
and the book keeps trading. Anything else is transport-class, the order may or may
not have arrived, so the run halts and the remaining legs are recorded as not
attempted. Neither path raises, and the code is the durable record either way,
because Alpaca does not persist a submit-time rejection as an order at all.
"""

from __future__ import annotations

import pandas as pd
import pytest

from live import alpaca, guards, morning_job

NAV = 1_000_000.0
PRICES = {"AAA": 100.0, "BBB": 100.0, "CCC": 100.0, "DDD": 100.0}


class _Asset:
    def __init__(self, tradable=True, shortable=True, easy_to_borrow=True) -> None:
        self.tradable = tradable
        self.shortable = shortable
        self.easy_to_borrow = easy_to_borrow


class _Order:
    def __init__(self, order_id: str) -> None:
        self.id = order_id
        self.status = "accepted"
        self.filled_avg_price = None
        self.filled_qty = None


class _Client:
    """A paper client with per-symbol flags and a scripted submit."""

    def __init__(self, flags=None, fail_on=None) -> None:
        self.flags = flags or {}
        self.fail_on = fail_on or {}
        self.asset_calls: list[str] = []
        self.submitted: list[str] = []
        self._counter = 0

    def get_asset(self, symbol: str) -> _Asset:
        self.asset_calls.append(symbol)
        return self.flags.get(symbol, _Asset())

    def submit_order(self, order_data) -> _Order:
        symbol = str(order_data.symbol)
        if symbol in self.fail_on:
            raise self.fail_on[symbol]
        self._counter += 1
        self.submitted.append(symbol)
        return _Order(f"order-{self._counter}")

    def get_order(self, order_id: str) -> _Order:
        order = _Order(order_id)
        order.status = "filled"
        order.filled_avg_price = 100.0
        order.filled_qty = 1.0
        return order

    def get_account(self) -> object:
        class _Account:
            equity = "1000000"
            buying_power = "1000000"
            id = "paper-account"

        return _Account()


def _specs() -> list[guards.OrderSpec]:
    return [
        guards.OrderSpec("AAA", 50_000.0, 50_000.0),
        guards.OrderSpec("BBB", -50_000.0, 50_000.0),
        guards.OrderSpec("CCC", 50_000.0, 50_000.0),
        guards.OrderSpec("DDD", -50_000.0, 50_000.0),
    ]


@pytest.mark.parametrize(
    ("flags", "code"),
    [
        (_Asset(tradable=False), alpaca.REASON_NOT_TRADABLE),
        (_Asset(shortable=False), alpaca.REASON_NOT_SHORTABLE),
        (_Asset(easy_to_borrow=False), alpaca.REASON_NOT_EASY_TO_BORROW),
    ],
)
def test_each_flag_has_its_own_refusal_code(flags: _Asset, code: str) -> None:
    client = _Client({"BBB": flags})
    refusal = alpaca.short_refusal(client, "BBB")
    assert refusal is not None
    assert refusal[0] == code
    assert "BBB" in refusal[1]


def test_both_flags_are_checked_and_a_good_name_passes() -> None:
    assert alpaca.short_refusal(_Client(), "BBB") is None
    flags = _Client().flags  # empty
    assert flags == {}


def test_a_failed_check_is_a_refusal_not_an_exception() -> None:
    class _Broken(_Client):
        def get_asset(self, symbol: str) -> _Asset:
            raise RuntimeError("the asset endpoint is down")

    refusal = alpaca.short_refusal(_Broken(), "BBB")
    assert refusal is not None
    assert refusal[0] == alpaca.REASON_SHORT_CHECK_FAILED
    assert "RuntimeError" in refusal[1]


def test_the_flags_are_read_once_per_run() -> None:
    client = _Client()
    cache: dict[str, dict[str, bool]] = {}
    alpaca.short_refusal(client, "BBB", cache)
    alpaca.short_refusal(client, "BBB", cache)
    alpaca.short_refusal(client, "AAA", cache)
    assert client.asset_calls == ["BBB", "AAA"]


def test_a_non_shortable_name_is_skipped_and_the_longs_still_trade() -> None:
    """Continue-and-log: one refused short must not cost the book its longs."""
    client = _Client({"BBB": _Asset(shortable=False), "DDD": _Asset(tradable=False)})

    fills = alpaca.submit_market_orders(_specs(), client, PRICES)
    by_ticker = {fill.ticker: fill for fill in fills}

    assert sorted(client.submitted) == ["AAA", "CCC"]
    assert by_ticker["BBB"].status == alpaca.SKIPPED
    assert by_ticker["BBB"].reason_code == alpaca.REASON_NOT_SHORTABLE
    assert by_ticker["DDD"].reason_code == alpaca.REASON_NOT_TRADABLE
    assert by_ticker["AAA"].status == "FILLED"
    assert len(fills) == 4, "every intended leg keeps a record"


def test_a_broker_rejection_is_recorded_and_the_run_continues() -> None:
    from alpaca.common.exceptions import APIError

    client = _Client(
        fail_on={
            "AAA": APIError({"code": 42210000, "message": "insufficient buying power"})
        }
    )

    fills = alpaca.submit_market_orders(_specs(), client, PRICES)
    by_ticker = {fill.ticker: fill for fill in fills}

    assert by_ticker["AAA"].reason_code == alpaca.REASON_ALPACA_ERROR
    assert "insufficient buying power" in by_ticker["AAA"].detail
    # The rest of the book still went.
    assert "BBB" in client.submitted and "CCC" in client.submitted


def test_a_transport_failure_halts_and_the_rest_are_not_attempted() -> None:
    """Unknown state is not stacked on unknown state."""
    client = _Client(fail_on={"AAA": ConnectionError("the connection reset")})

    fills = alpaca.submit_market_orders(_specs(), client, PRICES)

    assert fills[0].reason_code == alpaca.REASON_SUBMIT_UNKNOWN
    assert client.submitted == []
    for fill in fills[1:]:
        assert fill.status == alpaca.SKIPPED
        assert fill.reason_code == alpaca.REASON_SKIPPED_AFTER_HALT


def test_a_short_with_no_price_rounds_to_zero_rather_than_guessing() -> None:
    client = _Client()
    fills = alpaca.submit_market_orders(_specs(), client, {})
    by_ticker = {fill.ticker: fill for fill in fills}
    assert by_ticker["BBB"].reason_code == alpaca.REASON_QTY_ROUNDS_TO_ZERO
    assert sorted(client.submitted) == ["AAA", "CCC"]


def test_the_execution_records_carry_the_reason_code() -> None:
    """The row is the audit trail: Alpaca keeps no record of a refused leg."""
    records = morning_job.submit_orders(
        [
            guards.OrderSpec("AAA", 50_000.0, 50_000.0),
            guards.OrderSpec(
                "BBB", -50_000.0, 50_000.0, guards.REJECTED_TRADED_NOTIONAL
            ),
        ],
        client=None,
        dry_run=True,
    )
    assert list(records.columns) == morning_job.EXECUTION_COLUMNS[1:]
    assert records.loc[0, "reason_code"] == "DRY_RUN"
    assert records.loc[1, "reason_code"] == guards.REJECTED_TRADED_NOTIONAL

    counts = morning_job._reason_code_counts(records)
    assert counts == {guards.REJECTED_TRADED_NOTIONAL: 1}
    assert "DRY_RUN" not in counts, "a dry-run leg is not a refusal"


def test_a_live_run_with_a_refused_short_still_reaches_a_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end through the morning job, with a broker that refuses shorts."""
    proposal = pd.DataFrame(
        {"ticker": ["AAA", "BBB"], "weight": [0.05, -0.05], "alpha": [0.0, 0.0]}
    )
    client = _Client({"BBB": _Asset(easy_to_borrow=False)})
    monkeypatch.setattr(morning_job, "load_proposal", lambda *a, **k: proposal)
    monkeypatch.setattr(morning_job, "connect", lambda dry_run: client)
    monkeypatch.setattr(morning_job, "_close_prices", lambda *a, **k: PRICES)
    monkeypatch.setattr(morning_job.state, "write_positions", lambda *a, **k: None)
    monkeypatch.setattr(morning_job, "_write_execution_log", lambda *a, **k: None)

    summary = morning_job.run_morning("2026-09-25", nav=NAV, dry_run=False)

    assert summary["executed"] is True
    assert summary["skipped"] == 1
    assert summary["reason_codes"] == {alpaca.REASON_NOT_EASY_TO_BORROW: 1}
    assert client.submitted == ["AAA"]
