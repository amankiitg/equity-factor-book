"""Part B: the broker's own symbol for a ticker, and the removal it explains.

Two things happened on 2026-10-05/06 and both are here, with that session's own
numbers. The vendor and the loop still said **PSKY** while the broker's asset feed
carried the same security - asset id `5b47111b-5e0d-4adc-929c-3efae02f747e`, CUSIP
69932A204 - as **SKYD**, so the closing leg was sent under a spelling the broker no
longer had and was rejected at the next open. And the 326.072572039 PSKY shares
worth $3,211.81 that the account held at the 10-05 close were simply not there when
it was read again, with no order, no fill and no credit behind the disappearance.

The identity is therefore the asset id, not the ticker: a run that resolves each
ticker to the symbol the broker currently carries it under trades the company it
sized, and a book that compares the two by asset id sees one name rather than one
missing and one appearing. The disappearance is read the same way - by comparing
the previous broker read with this one and asking what explains the difference -
because a name that leaves the account unaccounted for is invisible in every other
number the loop writes.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from live import alpaca, fills, guards, morning_job, notify, positions, store

PRICES = {"PSKY": 9.85, "SKYD": 9.85, "AAA": 100.0}

# The asset id both spellings are, and the CUSIP behind it. Taken from the
# account's own order history, which is the only read that connects the spelling
# the feed has dropped to the asset that still exists.
PSKY_ASSET_ID = "5b47111b-5e0d-4adc-929c-3efae02f747e"
PSKY_CUSIP = "69932A204"

# What the account held when the 2026-10-05 evening read it, from
# `efb.broker_positions` for that close.
HELD_PSKY = 326.072572039
PSKY_VALUE = 3211.814835


class _Asset:
    def __init__(
        self,
        symbol: str,
        asset_id: str = "",
        tradable: bool = True,
        shortable: bool = True,
        easy_to_borrow: bool = True,
    ) -> None:
        self.symbol = symbol
        self.id = asset_id or f"asset-{symbol}"
        self.tradable = tradable
        self.shortable = shortable
        self.easy_to_borrow = easy_to_borrow
        self.cusip = PSKY_CUSIP if symbol == "SKYD" else f"cusip-{symbol}"


class _Order:
    def __init__(self, order_id: str, asset_id: str = "") -> None:
        self.id = order_id
        self.asset_id = asset_id
        self.status = "accepted"
        self.filled_avg_price = None
        self.filled_qty = None


class _Client:
    """A paper client with an asset feed, a history and a scripted submit."""

    def __init__(
        self,
        feed: list[_Asset] | None = None,
        history: dict[str, str] | None = None,
        flags: dict[str, _Asset] | None = None,
    ) -> None:
        self.feed = list(feed or [])
        self.history = dict(history or {})
        self.flags = dict(flags or {})
        self.asset_calls: list[str] = []
        self.feed_calls = 0
        self.history_calls: list[str] = []
        self.submitted: list[Any] = []
        self._counter = 0

    def get_all_assets(self, request: Any = None) -> list[_Asset]:
        self.feed_calls += 1
        return list(self.feed)

    def get_orders(self, filter: Any = None) -> list[_Order]:
        symbol = str(getattr(filter, "symbols", [""])[0])
        self.history_calls.append(symbol)
        asset_id = self.history.get(symbol, "")
        return [_Order(f"order-{symbol}", asset_id)] if asset_id else []

    def get_asset(self, symbol: str) -> _Asset:
        self.asset_calls.append(symbol)
        return self.flags.get(symbol, _Asset(symbol))

    def submit_order(self, order_data: Any) -> _Order:
        self._counter += 1
        self.submitted.append(order_data)
        return _Order(f"order-{self._counter}")

    def get_order(self, order_id: str) -> _Order:
        order = _Order(order_id)
        order.status = "accepted"
        return order


def _resolver(client: _Client) -> alpaca.SymbolResolver:
    """The resolver over the client's own feed, so the read is the one the run makes.

    The feed is one request for the whole active US-equity list, so the count of
    those requests is part of what these tests pin: a book of two hundred legs must
    cost one.
    """
    return alpaca.SymbolResolver(client)


# ------------------------------------------------------------------ resolution


def test_a_renamed_company_is_resolved_to_the_symbol_the_broker_carries() -> None:
    """The real case: the feed says SKYD, the order history says PSKY is that asset."""
    client = _Client(
        feed=[_Asset("SKYD", PSKY_ASSET_ID), _Asset("AAA")],
        history={"PSKY": PSKY_ASSET_ID},
    )
    resolver = _resolver(client)

    resolution = resolver.resolve("PSKY")

    assert resolution.symbol == "SKYD"
    assert resolution.renamed is True
    assert resolution.missing is False
    assert resolution.asset_id == PSKY_ASSET_ID
    assert resolution.detail == "PSKY now trades as SKYD"
    # A ticker the feed carries keeps its own spelling, and the order history is
    # not consulted for it: the ordinary case costs one request per run.
    assert resolver.resolve("AAA").symbol == "AAA"
    assert client.history_calls == ["PSKY"]
    # And the cached answer is the same object, so a book of 200 legs is one read.
    assert resolver.resolve("PSKY") is resolution


def test_the_feed_is_read_once_per_run() -> None:
    client = _Client(feed=[_Asset("AAA"), _Asset("BBB")])
    resolver = _resolver(client)
    resolver.resolve("AAA")
    resolver.resolve("BBB")
    resolver.resolve("AAA")
    assert client.feed_calls == 1


def test_a_ticker_the_feed_does_not_carry_under_any_symbol_is_missing() -> None:
    """The loud case: nothing to submit, and the reason says which ticker."""
    client = _Client(feed=[_Asset("AAA")], history={})
    resolution = _resolver(client).resolve("ZZZZ")

    assert resolution.missing is True
    assert resolution.symbol == ""
    assert "no asset for this ticker" in resolution.detail
    assert resolution.asset_id == ""


def test_a_feed_that_cannot_be_read_keeps_the_loops_own_spelling() -> None:
    """A failed read is not an answer, and it must not stop the whole book.

    Every ticker unresolved would stop a 200-leg evening over a transport failure,
    which is why the fallback is the run's own spelling: the broker decides, as it
    did before this class existed.
    """

    class _Broken(_Client):
        def get_all_assets(self, request: Any = None) -> list[_Asset]:
            raise RuntimeError("the asset endpoint is down")

    resolver = _resolver(_Broken())
    resolution = resolver.resolve("PSKY")

    assert resolution.symbol == "PSKY"
    assert resolution.missing is False
    assert resolution.renamed is False


def test_the_positions_check_sees_one_name_and_not_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loop's PSKY and the broker's SKYD are one holding, renamed.

    Without this the check reports one name the loop holds and the account does
    not, plus one the account holds and the loop does not: one company counted
    twice, and on the morning of 2026-10-06 exactly what it said.
    """

    class _Stub:
        def __init__(self, client: Any = None) -> None:
            self.client = client

        def renames(self, tickers: Any) -> dict[str, str]:
            assert list(tickers) == ["PSKY"]
            return {"PSKY": "SKYD"}

    monkeypatch.setattr(alpaca, "SymbolResolver", _Stub)

    found = positions.broker_renames({"PSKY": PSKY_VALUE}, {"SKYD": PSKY_VALUE})

    assert found == {"SKYD": "PSKY"}
    # The renamed book is compared under the loop's own name, so the two agree and
    # the check has nothing to report.
    result = positions.compare(
        positions._relabel({"SKYD": PSKY_VALUE}, found), {"PSKY": PSKY_VALUE}
    )
    assert result["matches"] is True
    assert result["missing_at_broker"] == []
    assert result["missing_in_store"] == []


def test_a_rename_the_account_no_longer_holds_is_not_translated_away(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A name that was renamed and is gone is a name that left, not a spelling."""

    class _Stub:
        def __init__(self, client: Any = None) -> None:
            pass

        def renames(self, tickers: Any) -> dict[str, str]:
            return {"PSKY": "SKYD"}

    monkeypatch.setattr(alpaca, "SymbolResolver", _Stub)

    assert positions.broker_renames({"PSKY": PSKY_VALUE}, {"AAA": 500.0}) == {}


# ------------------------------------------------------------------- the submit


def test_the_order_goes_out_under_the_resolved_symbol() -> None:
    """The order carries SKYD and the record still says PSKY, with the rename on it."""
    client = _Client(
        feed=[_Asset("SKYD", PSKY_ASSET_ID), _Asset("AAA")],
        history={"PSKY": PSKY_ASSET_ID},
    )
    # The real leg of that evening: the target went to zero and the closing size is
    # the broker's own quantity, fractional tail included.
    order = guards.OrderSpec(
        "PSKY",
        0.0,
        -2_917.19,
        intent=alpaca.INTENT_SELL_TO_CLOSE,
        held_quantity=HELD_PSKY,
    )

    fills_out = alpaca.submit_market_orders(
        [order],
        client,
        PRICES,
        close="2026-10-05",
        throttle=alpaca.Throttle(0.0),
        resolver=_resolver(client),
    )

    assert len(client.submitted) == 1
    assert str(client.submitted[0].symbol) == "SKYD"
    assert fills_out[0].ticker == "PSKY"
    assert fills_out[0].broker_symbol == "SKYD"


def test_the_short_check_reads_the_symbol_the_order_will_carry() -> None:
    """The borrow flags belong to the name that trades, not to the stale spelling."""
    skyd = _Asset("SKYD", PSKY_ASSET_ID, easy_to_borrow=False)
    client = _Client(
        feed=[_Asset("SKYD", PSKY_ASSET_ID), _Asset("AAA")],
        history={"PSKY": PSKY_ASSET_ID},
        flags={"SKYD": skyd},
    )

    fills_out = alpaca.submit_market_orders(
        [guards.OrderSpec("PSKY", -50_000.0, -50_000.0)],
        client,
        PRICES,
        close="2026-10-05",
        throttle=alpaca.Throttle(0.0),
        resolver=_resolver(client),
    )

    assert client.asset_calls == ["SKYD"]
    assert client.submitted == []
    assert fills_out[0].reason_code == alpaca.REASON_NOT_EASY_TO_BORROW


def test_a_leg_with_no_broker_asset_is_recorded_and_never_sent() -> None:
    """An order under a symbol the broker does not have is refused every night."""
    client = _Client(feed=[_Asset("AAA")], history={})

    fills_out = alpaca.submit_market_orders(
        [guards.OrderSpec("ZZZZ", 5_000.0, 5_000.0)],
        client,
        PRICES,
        close="2026-10-05",
        throttle=alpaca.Throttle(0.0),
        resolver=_resolver(client),
    )

    assert client.submitted == []
    assert fills_out[0].status == alpaca.SKIPPED
    assert fills_out[0].reason_code == alpaca.REASON_SYMBOL_NOT_FOUND
    assert fills_out[0].order_id == ""
    assert "no asset for this ticker" in fills_out[0].detail
    # The borrow flags are not consulted for a leg the broker cannot price: it
    # would be a read of a symbol that does not exist.
    assert client.asset_calls == []


def test_the_guard_reason_is_named_in_the_evening_message() -> None:
    rows = [
        {
            "ticker": "ZZZZ",
            "intended_notional": 5_000.0,
            "reason": "no asset",
            "reason_code": alpaca.REASON_SYMBOL_NOT_FOUND,
        },
        {
            "ticker": "AAA",
            "intended_notional": 250.0,
            "reason": "under the minimum",
            "reason_code": alpaca.REASON_BELOW_MIN_NOTIONAL,
        },
    ]
    records = pd.DataFrame(
        rows, columns=["ticker", "intended_notional", "reason", "reason_code"]
    )

    assert [row["ticker"] for row in morning_job.no_asset_rows(records)] == ["ZZZZ"]
    text = notify.compose(
        status="ok",
        target_close="2026-10-05",
        dry_run=False,
        orders=1,
        gross=5_000.0,
        sent_notional=5_000.0,
        no_asset=morning_job.no_asset_rows(records),
    )
    assert "No broker asset, so not sent: ZZZZ $5,000." in text


def test_the_rename_is_named_in_the_evening_message() -> None:
    text = notify.compose(
        status="ok",
        target_close="2026-10-05",
        dry_run=False,
        orders=199,
        gross=433_479.55,
        sent_notional=429_217.60,
        renames={"PSKY": "SKYD"},
    )

    assert "Renamed at the broker: PSKY now trades as SKYD." in text


def test_the_evening_line_separates_what_was_sized_from_what_was_sent() -> None:
    """One `gross` figure counted 34 legs that were never sent."""
    text = notify.compose(
        status="ok",
        target_close="2026-10-05",
        dry_run=False,
        orders=199,
        gross=433_479.55,
        sent_notional=429_217.60,
    )

    assert "Orders: 199 orders sent, $429,218 sent of $433,480 sized" in text
    assert "$433,480 gross" not in text


# ------------------------------------------------------- the records the evening wrote


def test_the_renamed_symbol_and_the_sized_and_sent_dollars_come_from_the_records() -> (
    None
):
    records = pd.DataFrame(
        [
            {
                "ticker": "PSKY",
                "intended_notional": -2_917.19,
                "broker_order_id": "order-1",
                "broker_symbol": "SKYD",
            },
            {
                "ticker": "INVH",
                "intended_notional": 4_000.0,
                "broker_order_id": "order-2",
                "broker_symbol": "",
            },
            {
                "ticker": "AAPL",
                "intended_notional": 1_344.76,
                "broker_order_id": "",
                "broker_symbol": "",
            },
        ],
        columns=[
            "ticker",
            "intended_notional",
            "broker_order_id",
            "broker_symbol",
        ],
    )

    assert morning_job.renamed_symbols(records) == {"PSKY": "SKYD"}
    # Sized is every leg the run built, sent is the legs that became orders: the
    # difference is the turnover that never happened.
    sent = records.loc[records["broker_order_id"].astype(str).str.len() > 0]
    assert float(sent["intended_notional"].abs().sum()) == pytest.approx(6_917.19)
    assert float(records["intended_notional"].abs().sum()) == pytest.approx(8_261.95)


# ------------------------------------------------------------------ the removal


def _real_book_without_psky() -> dict[str, float]:
    """The account as the 2026-10-06 read found it: flat of PSKY and of SKYD."""
    return {"AAA": 500_000.0}


def _rejected_close() -> pd.DataFrame:
    """The one closing leg of that evening: rejected at the open, filled nothing."""
    return pd.DataFrame(
        [
            {
                "ticker": "PSKY",
                "filled_quantity": 0.0,
                "position_intent": "sell_to_close",
                "status": "REJECTED",
            }
        ],
        columns=["ticker", "filled_quantity", "position_intent", "status"],
    )


def _previous_store(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The real 2026-10-05 broker read, as the store holds it."""
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    store.replace_by_date(
        "broker_positions",
        "2026-10-05",
        [
            {
                "trade_date": "2026-10-05",
                "ticker": "PSKY",
                "side": "long",
                "quantity": HELD_PSKY,
                "market_value": PSKY_VALUE,
                "weight": PSKY_VALUE / 994_523.69,
            },
            {
                "trade_date": "2026-10-05",
                "ticker": "AAA",
                "side": "long",
                "quantity": 10.0,
                "market_value": 500_000.0,
                "weight": 0.5,
            },
        ],
    )


def test_the_psky_removal_is_reported_with_its_own_shares_and_dollars(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real case, end to end: no filled close, no activity, one name reported."""
    _previous_store(tmp_path, monkeypatch)

    block = positions.unexplained_since_last_read(
        "2026-10-05",
        _real_book_without_psky(),
        closed=positions.closed_shares(_rejected_close()),
        reader=lambda after, until: {"AAA", "INVH", "SLB"},
        now=pd.Timestamp("2026-10-06T15:30:04Z").to_pydatetime(),
    )

    assert block["previous_read"] == "2026-10-05"
    assert block["feed"] == positions.FEED_READ
    # The window starts the day after the read, so the previous session's own
    # fills - the buy that opened the position - cannot explain it away.
    assert block["window"].startswith("2026-10-06T00:00:00Z")
    assert [item["ticker"] for item in block["exits"]] == ["PSKY"]
    assert block["exits"][0]["quantity"] == pytest.approx(HELD_PSKY)
    assert block["exits"][0]["notional"] == pytest.approx(PSKY_VALUE)


def test_the_line_the_morning_sends_says_what_left_and_what_was_checked(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _previous_store(tmp_path, monkeypatch)
    gone = positions.unexplained_since_last_read(
        "2026-10-05",
        _real_book_without_psky(),
        closed=positions.closed_shares(_rejected_close()),
        reader=lambda after, until: {"AAA"},
        now=pd.Timestamp("2026-10-06T15:30:04Z").to_pydatetime(),
    )

    line = notify._departure_line(gone["exits"], gone["feed"])

    assert line == (
        "PSKY: 326.07 shares ($3,212) left the account with no order or activity."
    )


def test_a_close_that_filled_the_position_explains_the_departure(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ordinary evening: the name is gone because the loop sold it."""
    _previous_store(tmp_path, monkeypatch)
    closed = _rejected_close()
    closed.loc[0, "filled_quantity"] = HELD_PSKY
    closed.loc[0, "status"] = "FILLED"

    block = positions.unexplained_since_last_read(
        "2026-10-05",
        _real_book_without_psky(),
        closed=positions.closed_shares(closed),
        reader=lambda after, until: {"AAA"},
    )

    assert block["exits"] == []
    assert notify._departure_line(block["exits"], block["feed"]) is None


def test_a_partial_close_does_not_explain_a_position_that_left_anyway(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """30 of 326 shares filled is a leg, not the 326 shares that went missing."""
    _previous_store(tmp_path, monkeypatch)
    closed = _rejected_close()
    closed.loc[0, "filled_quantity"] = 30.110012095

    block = positions.unexplained_since_last_read(
        "2026-10-05",
        _real_book_without_psky(),
        closed=positions.closed_shares(closed),
        reader=lambda after, until: {"AAA"},
    )

    assert [item["ticker"] for item in block["exits"]] == ["PSKY"]


def test_an_activity_of_the_brokers_own_explains_the_departure(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transfer or a corporate action is the broker's answer, not the loop's."""
    _previous_store(tmp_path, monkeypatch)

    block = positions.unexplained_since_last_read(
        "2026-10-05",
        _real_book_without_psky(),
        closed=positions.closed_shares(_rejected_close()),
        reader=lambda after, until: {"PSKY"},
    )

    assert block["exits"] == []


def test_a_feed_that_could_not_be_read_reports_the_departure_and_says_so(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Not read" is not "nothing there", and the sentence must not claim it is."""
    _previous_store(tmp_path, monkeypatch)

    def _broken(after: str, until: str) -> set[str]:
        raise RuntimeError("the activity endpoint is down")

    block = positions.unexplained_since_last_read(
        "2026-10-05",
        _real_book_without_psky(),
        closed=positions.closed_shares(_rejected_close()),
        reader=_broken,
    )

    assert [item["ticker"] for item in block["exits"]] == ["PSKY"]
    assert block["feed"] == positions.FEED_NOT_READ
    line = notify._departure_line(block["exits"], block["feed"])
    assert line is not None
    assert "no closing order" in line
    assert "activity feed could not be read" in line


def test_a_position_still_held_under_its_new_name_is_not_a_departure(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rename that keeps the position is a rename, and nothing left."""
    _previous_store(tmp_path, monkeypatch)

    block = positions.unexplained_since_last_read(
        "2026-10-05",
        {"PSKY": PSKY_VALUE, "AAA": 500_000.0},
        closed={},
        reader=lambda after, until: {"AAA"},
    )

    assert block["exits"] == []


def test_an_account_that_could_not_be_read_reports_no_departures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed read is not evidence about the book, so nothing is claimed."""
    import scripts.run_live_daily as run_live_daily

    block = run_live_daily.departures_since_last_read(
        "2026-10-05", {"account_read": False, "broker": None}
    )

    assert block == {"previous_read": "", "exits": [], "feed": "", "window": ""}


# --------------------------------------------------------- what the morning says


def test_a_leg_the_evening_could_not_send_is_named_with_its_derived_reason() -> None:
    """No order exists to read back, so the reason is derived from the record."""
    orders = pd.DataFrame(
        [
            {
                "ticker": "SKYD",
                "broker_order_id": "",
                "reason_code": alpaca.REASON_SYMBOL_NOT_FOUND,
                "intended_notional": 500.0,
                "position_intent": "buy_to_open",
            },
            {
                "ticker": "AAPL",
                "broker_order_id": "",
                "reason_code": alpaca.REASON_BELOW_MIN_NOTIONAL,
                "intended_notional": 84.0,
                "position_intent": "buy_to_open",
            },
        ],
        columns=[
            "ticker",
            "broker_order_id",
            "reason_code",
            "intended_notional",
            "position_intent",
        ],
    )

    lines = fills.never_sent_lines(orders)

    assert lines == ["SKYD buy_to_open $500 never sent (SYMBOL_NOT_FOUND)"]
    line = notify._miss_line(
        {
            "unfilled": ["PSKY sell_to_close 30.11 rejected 08:00 UTC"],
            "not_sent_lines": lines,
        }
    )
    assert line == (
        "Did not fill: PSKY sell_to_close 30.11 rejected 08:00 UTC; "
        "SKYD buy_to_open $500 never sent (SYMBOL_NOT_FOUND)."
    )


def test_a_rejected_leg_is_dated_by_the_instant_the_broker_failed_it() -> None:
    """Alpaca's only field for a rejection is `failed_at`, and it is the reason."""

    class _Rejected:
        status = "rejected"
        position_intent = "sell_to_close"
        qty = "30.110012095"
        canceled_at = None
        failed_at = "2026-10-06T08:00:02.963893Z"
        updated_at = "2026-10-06T08:00:02.963914Z"

    # The size is the order's own quantity as the message writes it, and the instant
    # is `failed_at` rather than an `updated_at` a millisecond later.
    assert fills.unfilled_line("PSKY", _Rejected()) == (
        "PSKY sell_to_close 30.11 rejected 08:00 UTC"
    )


def test_include_close_is_the_mornings_question_and_not_the_evenings(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row dated for the close is the book the evening's orders were *for*.

    The morning asks whether the account holds the book the close was sized to, so
    that row is the answer. Excluding it compared the account against the book the
    evening had already replaced, which on 2026-10-06 read as 45 names the loop
    held and the account did not, plus 29 the account held and the loop did not.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    store.upsert(
        "positions",
        [
            {"trade_date": "2026-10-02", "ticker": "PSKY", "signed_notional": 3_055.42},
            {"trade_date": "2026-10-05", "ticker": "PSKY", "signed_notional": 2_917.19},
            {"trade_date": "2026-10-05", "ticker": "AAA", "signed_notional": 500.0},
        ],
    )

    with_close, source = positions.store_positions("2026-10-05", include_close=True)
    without, other = positions.store_positions("2026-10-05")

    assert sorted(with_close) == ["AAA", "PSKY"]
    assert with_close["PSKY"] == pytest.approx(2_917.19)
    assert source == "the 2026-10-05 position row"
    # The evening's own question, on the same store: the last book the loop held
    # before tonight's target, which is the previous close's row.
    assert without == {"PSKY": pytest.approx(3_055.42)}
    assert other == "the 2026-10-02 position row"
