"""The broker-review fixes, tested where each one lives.

An order is the signed change to a name, over the union of the target book and the
book the account holds. Every leg carries an Alpaca **position intent**: a long
increase is BUY_TO_OPEN (notional), a long decrease or close is SELL_TO_CLOSE (a
quantity, exact for a full close), a new or larger short is SELL_TO_OPEN (whole
shares, shortable-checked), and a short cover is BUY_TO_CLOSE (a quantity). A
change that would cross zero is split: closed tonight, opened next evening, and the
deferred target is named in the email. Submitted after the close, an accepted DAY
order is success and nothing polls for a fill; a refusal or rejection still makes
the run incomplete. A rerun resolves the orders the broker already holds by their
deterministic `client_order_id` before submitting anything.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from live import alpaca, guards, morning_job, notify
from scripts import smoke_position_intents

NAV = 1_000_000.0
PRICES = {"AAA": 100.0, "BBB": 100.0, "CCC": 200.0, "SPY": 100.0}
# 18:30 ET, inside the 16:00-20:00 window; 10:00 ET, outside it.
IN_WINDOW = datetime(2026, 9, 25, 22, 30, tzinfo=UTC)
OUT_OF_WINDOW = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)


def _proposal(weights: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"ticker": list(weights), "weight": [weights[name] for name in weights]}
    )


@pytest.mark.parametrize(
    ("held", "target", "expected_trade", "expected_intent", "deferred_target"),
    [
        pytest.param(
            {"AAA": 60_000.0}, 0.10, 40_000.0, "buy_to_open", 0.0, id="increase"
        ),
        pytest.param(
            {"AAA": 140_000.0}, 0.10, -40_000.0, "sell_to_close", 0.0, id="decrease"
        ),
        pytest.param(
            {"AAA": -100_000.0},
            -0.05,
            50_000.0,
            "buy_to_close",
            0.0,
            id="cover-a-short",
        ),
        pytest.param(
            {"AAA": 100_000.0},
            -0.05,
            -100_000.0,
            "sell_to_close",
            -50_000.0,
            id="long-to-short-is-closed-then-deferred",
        ),
        pytest.param(
            {"AAA": -100_000.0},
            0.05,
            100_000.0,
            "buy_to_close",
            50_000.0,
            id="short-to-long-is-closed-then-deferred",
        ),
        pytest.param(
            {"AAA": 80_000.0}, None, -80_000.0, "sell_to_close", 0.0, id="removal"
        ),
    ],
)
def test_an_order_is_the_signed_change_with_a_position_intent(
    held: dict[str, float],
    target: float | None,
    expected_trade: float,
    expected_intent: str,
    deferred_target: float,
) -> None:
    """Every case the target-as-order bug got wrong, and both reversal directions."""
    weights = {} if target is None else {"AAA": target}
    orders = morning_job.target_orders(_proposal(weights), NAV, held)

    assert [order.ticker for order in orders] == ["AAA"], "the union was not built"
    order = orders[0]
    assert order.trade_notional == pytest.approx(expected_trade)
    assert order.traded_notional == pytest.approx(abs(expected_trade))
    assert order.intent == expected_intent
    # A reversal is closed tonight and deferred; every other leg targets its book.
    if deferred_target:
        assert order.target_notional == 0.0
        assert order.deferred_target_notional == pytest.approx(deferred_target)
    else:
        assert order.target_notional == pytest.approx((target or 0.0) * NAV)
        assert order.deferred_target_notional == 0.0


def test_holding_the_target_trades_nothing() -> None:
    """A rerun of an unchanged book has no leg to send."""
    orders = morning_job.target_orders(
        _proposal({"AAA": 0.10}), NAV, {"AAA": 100_000.0}
    )
    assert orders == []


def test_a_held_name_absent_from_the_target_is_always_closed() -> None:
    """Even below the usual minimum, a leftover cannot survive the evening."""
    orders = morning_job.target_orders(_proposal({"BBB": 0.10}), NAV, {"AAA": 100.0})
    assert [order.ticker for order in orders] == ["AAA", "BBB"]
    close = {order.ticker: order for order in orders}["AAA"]
    assert close.trade_notional == pytest.approx(-100.0)
    assert close.target_notional == 0.0
    assert close.intent == "sell_to_close"


class _Asset:
    def __init__(self, shortable: bool = True, easy_to_borrow: bool = True) -> None:
        self.tradable = True
        self.shortable = shortable
        self.easy_to_borrow = easy_to_borrow


class _Submitted:
    def __init__(self, order_id: str, status: str = "accepted") -> None:
        self.id = order_id
        self.status = status
        self.filled_avg_price = None
        self.filled_qty = None


class _RecordingClient:
    """A broker that records what it was asked to submit and never polls."""

    def __init__(self, assets: dict[str, _Asset] | None = None) -> None:
        self.assets = assets or {}
        self.requests: list[object] = []

    def get_account(self) -> object:
        class _Account:
            equity = "1000000"
            buying_power = "1000000"
            id = "paper-account"

        return _Account()

    def get_asset(self, symbol: str) -> _Asset:
        return self.assets.get(symbol, _Asset())

    def submit_order(self, order_data: object) -> _Submitted:
        self.requests.append(order_data)
        return _Submitted(f"order-{len(self.requests)}")

    def get_order(self, order_id: str) -> _Submitted:  # pragma: no cover - never called
        raise AssertionError("submit_market_orders must not poll for a fill")


def _intent(request: object) -> str:
    value = getattr(request, "position_intent", None)
    return str(getattr(value, "value", value) or "")


def _side(request: object) -> str:
    return str(getattr(getattr(request, "side", None), "value", ""))


def _submit(orders, client, prices, close="2026-09-25"):
    return alpaca.submit_market_orders(
        orders, client, prices, close=close, throttle=alpaca.Throttle(0)
    )


def test_each_intent_builds_the_order_shape_alpaca_expects() -> None:
    """Notional opens a long; quantity closes; whole shares open a short."""
    # BUY_TO_OPEN: a notional order, the one TIF a notional order may carry.
    client = _RecordingClient()
    _submit([guards.OrderSpec("AAA", 50_000.0, 50_000.0)], client, PRICES)
    open_long = client.requests[0]
    assert _intent(open_long) == "buy_to_open"
    assert _side(open_long) == "buy"
    assert float(open_long.notional) == pytest.approx(50_000.0)

    # SELL_TO_CLOSE: a quantity order for a partial decrease.
    client = _RecordingClient()
    _submit([guards.OrderSpec("AAA", 40_000.0, -10_000.0)], client, PRICES)
    trim = client.requests[0]
    assert _intent(trim) == "sell_to_close"
    assert _side(trim) == "sell"
    assert float(trim.qty) == pytest.approx(100.0)  # 10,000 at 100

    # SELL_TO_OPEN: whole shares, shortable-checked.
    client = _RecordingClient()
    _submit([guards.OrderSpec("AAA", -60_000.0, -60_000.0)], client, PRICES)
    open_short = client.requests[0]
    assert _intent(open_short) == "sell_to_open"
    assert _side(open_short) == "sell"
    assert int(open_short.qty) == 600

    # BUY_TO_CLOSE: a quantity order for a cover.
    client = _RecordingClient()
    _submit([guards.OrderSpec("AAA", -20_000.0, 40_000.0)], client, PRICES)
    cover = client.requests[0]
    assert _intent(cover) == "buy_to_close"
    assert _side(cover) == "buy"
    assert float(cover.qty) == pytest.approx(400.0)  # 40,000 at 100


def test_a_full_close_sends_the_exact_held_quantity_fractional_allowed() -> None:
    """A close lands on zero from the broker's own size, not a re-derived one."""
    client = _RecordingClient()
    _submit(
        [
            guards.OrderSpec(
                "AAA",
                target_notional=0.0,
                trade_notional=-150.0,
                intent=alpaca.INTENT_SELL_TO_CLOSE,
                held_quantity=1.5,
            )
        ],
        client,
        {"AAA": 100.0},
    )
    assert float(client.requests[0].qty) == pytest.approx(1.5)


def test_a_partial_short_cover_rounds_down_to_whole_shares() -> None:
    """A cover is floored, because one share too many closes the short.

    The account is short five shares at $100 and the target is one share short, so
    $490 buys back 4.9 shares' worth. Four shares leave one short, which is the
    target; the nearest whole share (five) or the ceiling would close the position
    and leave the book flat in a name it is supposed to be short. Whole shares
    too: the sizing step never asks for a half-covered short.
    """
    client = _RecordingClient()
    _submit(
        [
            guards.OrderSpec(
                "AAA",
                target_notional=-100.0,
                trade_notional=490.0,
                intent=alpaca.INTENT_BUY_TO_CLOSE,
                held_quantity=-5.0,
            )
        ],
        client,
        {"AAA": 100.0},
    )

    assert _intent(client.requests[0]) == "buy_to_close"
    assert float(client.requests[0].qty) == pytest.approx(4.0)
    # the cover leaves the target position, still a short
    assert -5.0 + float(client.requests[0].qty) == pytest.approx(-1.0)
    # the negative control: the size that was sent before this rule, and the
    # nearest whole share, both over-cover
    assert 490.0 / 100.0 == pytest.approx(4.9)
    assert -5.0 + round(490.0 / 100.0) == pytest.approx(0.0)


def test_a_cover_under_one_whole_share_is_skipped_rather_than_rounded() -> None:
    """Under a share there is no cover to send, and rounding up is the one thing
    that must not happen.

    Half a share's worth of cover is not a size the book asked for; the leg is
    recorded as skipped, with the reason, and nothing is submitted. The negative
    control is the fractional order the code sent before: no request is built here.
    """
    client = _RecordingClient()
    fills = _submit(
        [
            guards.OrderSpec(
                "AAA",
                target_notional=-450.0,
                trade_notional=50.0,
                intent=alpaca.INTENT_BUY_TO_CLOSE,
                held_quantity=-5.0,
            )
        ],
        client,
        {"AAA": 100.0},
    )

    assert client.requests == []
    assert fills[0].status == alpaca.SKIPPED
    assert fills[0].reason_code == alpaca.REASON_COVER_UNDER_ONE_SHARE
    assert "under one whole share" in fills[0].detail


def test_a_cover_under_a_share_does_not_make_the_run_incomplete() -> None:
    """The cover sits in the same class as a leg the $250 minimum leaves out.

    It is a leg the run chose not to send, not a leg it failed to place: the short
    stays that much bigger than its target until the next evening, which is
    reported, but there is nothing for the next tick to retry. The negative
    controls are the two skips that *are* failures: a short open that rounds to
    zero whole shares, and the same cover carrying the generic rounds-to-zero code.
    """
    cover = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "status": [alpaca.SKIPPED],
            "reason_code": [alpaca.REASON_COVER_UNDER_ONE_SHARE],
        }
    )

    assert morning_job.incomplete_legs(cover) == []

    # a new short whose notional rounds to no whole share is a leg the run wanted
    # and could not place
    short_open = cover.copy()
    short_open.loc[0, "reason_code"] = alpaca.REASON_QTY_ROUNDS_TO_ZERO
    assert [leg["ticker"] for leg in morning_job.incomplete_legs(short_open)] == ["AAA"]


def test_a_partial_long_decrease_keeps_its_fraction() -> None:
    """The rule is about covers. A long trim still sends the size it was sized at.

    Selling part of a share cannot make the position short while the target holds
    shares, and flooring a small trim would round it away and skip a leg that
    should trade.
    """
    client = _RecordingClient()
    _submit(
        [
            guards.OrderSpec(
                "AAA",
                target_notional=248_750.0,
                trade_notional=-1_250.0,
                intent=alpaca.INTENT_SELL_TO_CLOSE,
                held_quantity=250.0,
            )
        ],
        client,
        {"AAA": 100.0},
    )

    assert _intent(client.requests[0]) == "sell_to_close"
    assert float(client.requests[0].qty) == pytest.approx(12.5)


def test_the_shortability_checks_run_only_on_sell_to_open() -> None:
    """Closing a long is not a short, even when the asset reports shortable=false."""
    refusing = _RecordingClient({"BBB": _Asset(shortable=False, easy_to_borrow=False)})
    fills = _submit(
        [
            guards.OrderSpec(
                "AAA",
                target_notional=0.0,
                trade_notional=-10_000.0,
                intent=alpaca.INTENT_SELL_TO_CLOSE,
                held_quantity=100.0,
            ),
            guards.OrderSpec("BBB", -60_000.0, -60_000.0),
        ],
        refusing,
        PRICES,
    )
    by_ticker = {fill.ticker: fill for fill in fills}
    # The close was submitted although AAA reports shortable=false: it is not a short.
    assert by_ticker["AAA"].status == "ACCEPTED"
    assert by_ticker["AAA"].reason_code == ""
    assert by_ticker["BBB"].reason_code == alpaca.REASON_NOT_SHORTABLE
    assert [request.symbol for request in refusing.requests] == ["AAA"]


def test_a_submitted_leg_is_never_polled_for_a_fill() -> None:
    """The client's get_order raises if called: accepted is success."""
    client = _RecordingClient()
    fills = _submit([guards.OrderSpec("AAA", 50_000.0, 50_000.0)], client, PRICES)
    assert fills[0].status == "ACCEPTED"
    assert fills[0].intent == "buy_to_open"
    assert fills[0].filled_notional == 0.0


def test_a_dry_run_is_complete_and_a_refusal_is_not() -> None:
    dry = pd.DataFrame(
        {"ticker": ["AAA"], "status": ["DRY_RUN"], "reason_code": ["DRY_RUN"]}
    )
    assert morning_job.incomplete_legs(dry) == []

    live = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC", "DDD", "EEE"],
            "status": ["ACCEPTED", "NEW", "SKIPPED", "REJECTED", "CANCELED"],
            "reason_code": ["", "", "ASSET_NOT_SHORTABLE", "", ""],
        }
    )
    legs = morning_job.incomplete_legs(live)
    assert [leg["ticker"] for leg in legs] == ["CCC", "DDD", "EEE"]
    # An accepted order stays accepted until the open, and that is complete.
    assert not any(leg["ticker"] in {"AAA", "BBB"} for leg in legs)


class _ExistingOrder:
    def __init__(self, status: str = "accepted") -> None:
        self.id = "order-existing"
        self.status = status
        self.filled_avg_price = None
        self.filled_qty = None


class _ExistingClient(_RecordingClient):
    """A broker that already holds an order under some deterministic ids."""

    def __init__(self, existing: dict[str, _ExistingOrder]) -> None:
        super().__init__()
        self.existing = existing

    def get_order_by_client_id(self, ticket: str) -> _ExistingOrder | None:
        return self.existing.get(ticket)


def test_a_rerun_resolves_existing_orders_before_submitting_anything() -> None:
    """The id the first attempt sent is looked up, not sent again."""
    first = alpaca.client_order_id("2026-09-25", "AAA", "buy")
    second = alpaca.client_order_id("2026-09-25", "BBB", "buy")
    client = _ExistingClient({first: _ExistingOrder()})

    fills = _submit(
        [
            guards.OrderSpec("AAA", 50_000.0, 50_000.0),
            guards.OrderSpec("BBB", 50_000.0, 50_000.0),
        ],
        client,
        PRICES,
    )
    by_ticker = {fill.ticker: fill for fill in fills}
    assert by_ticker["AAA"].resolved is True
    assert by_ticker["AAA"].client_order_id == first
    assert by_ticker["BBB"].resolved is False
    # Only the leg the broker did not hold was submitted.
    assert [request.symbol for request in client.requests] == ["BBB"]

    client.existing[second] = _ExistingOrder()
    again = _submit(
        [
            guards.OrderSpec("AAA", 50_000.0, 50_000.0),
            guards.OrderSpec("BBB", 50_000.0, 50_000.0),
        ],
        client,
        PRICES,
    )
    assert all(fill.resolved for fill in again)
    assert [request.symbol for request in client.requests] == ["BBB"]


def test_a_live_run_with_a_refused_short_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end: the summary says the run is not done, with the leg named."""
    proposal = pd.DataFrame(
        {"ticker": ["AAA", "BBB"], "weight": [0.05, -0.05], "alpha": [0.0, 0.0]}
    )
    client = _RecordingClient({"BBB": _Asset(shortable=True, easy_to_borrow=False)})
    monkeypatch.setattr(morning_job, "load_proposal", lambda *a, **k: proposal)
    monkeypatch.setattr(morning_job, "connect", lambda dry_run: client)
    monkeypatch.setattr(morning_job, "_close_prices", lambda *a, **k: PRICES)
    monkeypatch.setattr(morning_job.state, "write_positions", lambda *a, **k: None)
    monkeypatch.setattr(morning_job, "_write_execution_log", lambda *a, **k: None)

    summary = morning_job.run_morning("2026-09-25", nav=NAV, dry_run=False)

    assert summary["complete"] is False
    assert [leg["ticker"] for leg in summary["incomplete_legs"]] == ["BBB"]
    assert (
        summary["incomplete_legs"][0]["reason_code"] == alpaca.REASON_NOT_EASY_TO_BORROW
    )


def test_a_reversal_is_reported_as_deferred_and_named_in_the_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run trades a close, and the message says which side waits for tomorrow."""
    proposal = pd.DataFrame({"ticker": ["CCC"], "weight": [-0.06], "alpha": [0.0]})
    client = _RecordingClient()
    monkeypatch.setattr(morning_job, "load_proposal", lambda *a, **k: proposal)
    monkeypatch.setattr(morning_job, "connect", lambda dry_run: client)
    monkeypatch.setattr(morning_job, "_close_prices", lambda *a, **k: PRICES)
    monkeypatch.setattr(morning_job.state, "write_positions", lambda *a, **k: None)
    monkeypatch.setattr(morning_job, "_write_execution_log", lambda *a, **k: None)

    summary = morning_job.run_morning(
        "2026-09-28",
        nav=NAV,
        dry_run=False,
        positions={"CCC": 80_000.0},
        quantities={"CCC": 400.0},
    )

    assert summary["complete"] is True
    deferred = summary["deferred_reversals"]
    assert len(deferred) == 1 and deferred[0]["ticker"] == "CCC"
    assert deferred[0]["held_notional"] == pytest.approx(80_000.0)
    assert deferred[0]["target_notional"] == pytest.approx(-60_000.0)
    # One leg, a close, sent as the broker's exact held quantity.
    assert len(client.requests) == 1
    assert _intent(client.requests[0]) == "sell_to_close"
    assert float(client.requests[0].qty) == pytest.approx(400.0)

    message = notify.compose(
        status="ok",
        target_close="2026-09-28",
        dry_run=True,
        orders=1,
        gross=80_000.0,
        deferred_reversals=deferred,
    )
    assert (
        "Reversals deferred: CCC closed tonight, short $60,000 opens next evening."
        in message
    )


class _SmokeBroker(_RecordingClient):
    """A broker with positions that accepts after-close DAY orders."""

    def __init__(self, positions: dict[str, float] | None = None) -> None:
        super().__init__()
        self.positions = dict(positions or {})

    def get_all_positions(self) -> list[object]:
        class _Position:
            def __init__(self, symbol: str, shares: float) -> None:
                self.symbol = symbol
                # A real short Position reports a signed quantity, and the sign is
                # what `position_book` reads; an unsigned one here would make the
                # short read as a long.
                self.qty = str(shares)
                self.market_value = str(shares * PRICES[symbol])
                self.side = "long" if shares >= 0 else "short"

        return [
            _Position(symbol, shares)
            for symbol, shares in sorted(self.positions.items())
            if abs(shares) > 1e-9
        ]


def test_the_smoke_opens_then_closes_with_ids_that_never_collide() -> None:
    """Two evenings, four intents, ids prefixed so the book can never clash."""
    broker = _SmokeBroker()

    opened = smoke_position_intents.evening_one(
        broker,
        long_symbol="SPY",
        short_symbol="AAA",
        notional=500.0,
        short_qty=1,
        short_price=100.0,
        close="2026-09-25",
    )
    assert [leg["position_intent"] for leg in opened] == [
        "buy_to_open",
        "sell_to_open",
    ]
    assert all(leg["accepted"] for leg in opened)
    for request in broker.requests:
        ticket = str(request.client_order_id)
        assert ticket.startswith("efb-smoke-")
        book_ticket = alpaca.client_order_id(
            "2026-09-25", str(request.symbol), _side(request)
        )
        assert ticket != book_ticket

    # The one-share short is a quantity order; the long is a notional order.
    by_intent = {_intent(request): request for request in broker.requests}
    assert float(by_intent["buy_to_open"].notional) == pytest.approx(500.0)
    assert int(by_intent["sell_to_open"].qty) == 1

    # Overnight the two orders fill: a long of five shares and a one-share short.
    broker.positions = {"SPY": 5.0, "AAA": -1.0}
    broker.requests.clear()

    closed = smoke_position_intents.evening_two(
        broker, long_symbol="SPY", short_symbol="AAA", close="2026-09-28"
    )
    assert [leg["position_intent"] for leg in closed] == [
        "sell_to_close",
        "buy_to_close",
    ]
    assert all(leg["accepted"] for leg in closed)
    by_intent = {_intent(request): request for request in broker.requests}
    assert float(by_intent["sell_to_close"].qty) == pytest.approx(5.0)
    assert float(by_intent["buy_to_close"].qty) == pytest.approx(1.0)


def test_the_smoke_reports_whether_every_order_was_accepted(capsys) -> None:
    """The two commands the owner runs print their verdict and exit on it."""
    broker = _SmokeBroker({"SPY": 5.0, "AAA": -1.0})
    code = smoke_position_intents.main(
        [
            "--evening",
            "two",
            "--long-symbol",
            "SPY",
            "--short-symbol",
            "AAA",
            "--yes",
        ],
        client=broker,
        now=IN_WINDOW,
    )
    assert code == 0
    assert "every order was accepted" in capsys.readouterr().out

    # A refused leg is reported and fails the evening, not buried.
    refusing = _SmokeBroker()
    refusing.assets = {"AAA": _Asset(shortable=False, easy_to_borrow=False)}
    code = smoke_position_intents.main(
        [
            "--evening",
            "one",
            "--long-symbol",
            "SPY",
            "--short-symbol",
            "AAA",
            "--price",
            "100",
            "--yes",
        ],
        client=refusing,
        now=IN_WINDOW,
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "SOME ORDERS WERE REFUSED" in out
    assert alpaca.REASON_NOT_SHORTABLE in out


def test_the_smoke_window_is_1600_to_2000_new_york() -> None:
    """The same hours smoke_order_timing enforces, on New York wall time."""
    ny = ZoneInfo("America/New_York")
    assert smoke_position_intents.in_cron_window(
        datetime(2026, 9, 25, 16, 0, tzinfo=ny)
    )
    assert smoke_position_intents.in_cron_window(
        datetime(2026, 9, 25, 19, 59, tzinfo=ny)
    )
    assert not smoke_position_intents.in_cron_window(
        datetime(2026, 9, 25, 15, 59, tzinfo=ny)
    )
    assert not smoke_position_intents.in_cron_window(
        datetime(2026, 9, 25, 20, 0, tzinfo=ny)
    )


def test_the_smoke_refuses_outside_the_after_close_window(capsys) -> None:
    """Outside the window it refuses, and --force-hour is the deliberate bypass."""
    broker = _SmokeBroker()
    code = smoke_position_intents.main(
        [
            "--evening",
            "one",
            "--long-symbol",
            "SPY",
            "--short-symbol",
            "AAA",
            "--price",
            "100",
            "--yes",
        ],
        client=broker,
        now=OUT_OF_WINDOW,
    )
    assert code == 2
    assert broker.requests == [], "an order was sent outside the window"
    err = capsys.readouterr().err
    assert "refusing to submit at" in err
    assert "16:00 and 20:00 ET" in err

    # The bypass runs, and says which hour it used.
    code = smoke_position_intents.main(
        [
            "--evening",
            "one",
            "--long-symbol",
            "SPY",
            "--short-symbol",
            "AAA",
            "--price",
            "100",
            "--yes",
            "--force-hour",
        ],
        client=broker,
        now=OUT_OF_WINDOW,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "--force-hour" in captured.err
    assert len(broker.requests) == 2


def test_the_smoke_refuses_without_yes(capsys) -> None:
    broker = _SmokeBroker()
    assert (
        smoke_position_intents.main(["--evening", "one"], client=broker, now=IN_WINDOW)
        == 2
    )
    assert broker.requests == []
    assert "refusing to submit without --yes" in capsys.readouterr().err
