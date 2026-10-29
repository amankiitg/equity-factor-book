"""The anchored page block: what it measures, and what it must never do.

The numbers here are synthetic and small, except the fixture that reproduces the four
2026-10-23 flips from the shapes the store actually holds: CCL and GEHC short at the
account read and long in the target, F and VZ long and short, each closed on the
rebalance and opened on the next session, each complete at the next account read.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from live import monthly_view


def _proposals(*rows: tuple[str, str | None]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": [close for close, _ in rows],
            "manifest": [
                {} if day is None else {"cadence": {"day": day}} for _, day in rows
            ],
        }
    )


def test_the_anchor_is_the_last_rebalance_on_a_hold_day() -> None:
    proposals = _proposals(
        ("2026-10-22", "hold"), ("2026-10-23", "rebalance"), ("2026-10-26", "hold")
    )
    assert monthly_view.anchor_close(proposals) == ("2026-10-23", "cadence")


def test_a_rebalance_day_anchors_on_tonight() -> None:
    proposals = _proposals(("2026-10-22", "hold"), ("2026-10-23", "rebalance"))
    assert monthly_view.anchor_close(proposals) == ("2026-10-23", "rebalance")


def test_no_cadence_block_anchors_on_tonight_the_daily_way() -> None:
    proposals = _proposals(("2026-10-22", None), ("2026-10-23", None))
    assert monthly_view.anchor_close(proposals) == ("2026-10-23", "daily")
    assert monthly_view.anchor_close(pd.DataFrame()) == (None, "daily")


def test_four_flips_are_four_rows_and_not_four_exits_plus_four_opens() -> None:
    """The 2026-10-23 rebalance, in the shapes the store holds for it."""
    anchor, later = "2026-10-23", "2026-10-26"
    target = pd.DataFrame(
        {
            "trade_date": [anchor] * 4,
            "ticker": ["CCL", "F", "GEHC", "VZ"],
            "side": ["long", "short", "long", "short"],
            "weight": [0.000692, -0.001633, 0.002376, -0.002484],
        }
    )
    before = pd.DataFrame(
        {
            "trade_date": [anchor] * 4,
            "ticker": ["CCL", "F", "GEHC", "VZ"],
            "side": ["short", "long", "short", "long"],
            "market_value": [-600.53, 633.19, -2000.60, 988.56],
        }
    )
    now = pd.DataFrame(
        {
            "trade_date": [later] * 4,
            "ticker": ["CCL", "F", "GEHC", "VZ"],
            "side": ["long", "short", "long", "short"],
            "market_value": [687.27, -1624.26, 2489.36, -2431.68],
        }
    )
    orders = pd.DataFrame(
        {
            "trade_date": [anchor] * 4 + [later] * 4,
            "ticker": ["CCL", "F", "GEHC", "VZ"] * 2,
            "intended_notional": [600.53, -633.19, 2000.60, -988.56]
            + [677.70, -1600.35, 2328.08, -2434.04],
            "reason_code": [""] * 8,
            "position_intent": [
                "buy_to_close",
                "sell_to_close",
                "buy_to_close",
                "sell_to_close",
                "buy_to_open",
                "sell_to_open",
                "buy_to_open",
                "sell_to_open",
            ],
        }
    )
    fills = pd.DataFrame(
        {
            "trade_date": [anchor] * 4 + [later] * 4,
            "ticker": ["CCL", "F", "GEHC", "VZ"] * 2,
            "filled_notional": [605.47, 637.32, 2012.79, 961.38]
            + [677.70, 1609.03, 2328.08, 2417.71],
            "status": ["FILLED"] * 8,
        }
    )
    bridge = monthly_view.bridge(target, before, now, orders, fills, anchor)
    assert bridge["flipped"] == 4
    assert bridge["complete_flips"] == 4
    assert bridge["exited"] == 0 and bridge["opened"] == 0
    rows = {row["ticker"]: row for row in bridge["flip_rows"]}
    assert rows["CCL"]["from_side"] == "short" and rows["CCL"]["to_side"] == "long"
    assert rows["CCL"]["close_filled"] == anchor
    assert rows["CCL"]["open_filled"] == later
    assert rows["CCL"]["open_dollars"] == pytest.approx(677.70)
    assert rows["VZ"]["complete"] is True and rows["VZ"]["on_target_side"] is True


def test_the_bridge_identity_is_gross_and_exact() -> None:
    anchor, later = "2026-10-23", "2026-10-26"
    target = pd.DataFrame(
        {
            "trade_date": [anchor] * 2,
            "ticker": ["AAA", "BBB"],
            "side": ["long", "short"],
            "weight": [0.01, -0.01],
        }
    )
    before = pd.DataFrame(
        {
            "trade_date": [anchor] * 3,
            "ticker": ["AAA", "BBB", "CCC"],
            "side": ["long", "short", "long"],
            "market_value": [1000.0, -1000.0, 500.0],
        }
    )
    now = pd.DataFrame(
        {
            "trade_date": [later] * 2,
            "ticker": ["AAA", "BBB"],
            "side": ["long", "short"],
            "market_value": [1100.0, -900.0],
        }
    )
    bridge = monthly_view.bridge(
        target, before, now, pd.DataFrame(), pd.DataFrame(), anchor
    )
    assert bridge["exited"] == 1  # CCC left and is not in the target
    assert bridge["before_dollars"] == pytest.approx(2500.0)
    assert bridge["after_dollars"] == pytest.approx(2000.0)
    assert bridge["holds"] is True
    assert bridge["identities"][0]["left"] == pytest.approx(
        bridge["identities"][0]["right"], abs=1.0
    )


def test_the_drift_is_half_the_sum_of_the_gaps_and_the_cost_is_the_traded_half() -> (
    None
):
    target = pd.DataFrame(
        {
            "trade_date": ["2026-10-23"] * 2,
            "ticker": ["AAA", "BBB"],
            "side": ["long", "short"],
            "weight": [0.10, -0.10],
        }
    )
    now = pd.DataFrame(
        {
            "trade_date": ["2026-10-28"] * 2,
            "ticker": ["AAA", "BBB"],
            "side": ["long", "short"],
            "weight": [0.08, -0.12],
        }
    )
    measured = monthly_view.drift(target, now, nav=1_000_000.0, trading_bps=3.3)
    # Gaps: AAA -2%, BBB -2%. sum|gap| = 4%, half = 2%, traded = 4%.
    assert measured["half_turnover_pct"] == pytest.approx(0.02)
    assert measured["half_turnover_usd"] == pytest.approx(20_000.0)
    assert measured["traded_usd"] == pytest.approx(40_000.0)
    assert measured["estimated_cost_usd"] == pytest.approx(40_000.0 * 3.3 / 1e4)
    assert [row["ticker"] for row in measured["largest"]] == ["AAA", "BBB"]


def test_the_trading_cost_is_the_three_parts_and_not_the_total() -> None:
    """Borrow is paid whether or not anything trades."""
    manifest = {
        "cost_breakdown_bps": {
            "spread": 2.57,
            "impact": 0.17,
            "commission": 0.56,
            "borrow": 1.46,
            "total": 4.76,
        }
    }
    assert monthly_view._trading_bps(manifest) == pytest.approx(3.30)
    assert monthly_view._trading_bps({"cost_breakdown_bps": {"trading": 2.0}}) == 2.0
    assert monthly_view._trading_bps({}) is None


def test_the_block_returns_none_rather_than_raising() -> None:
    """Reporting must never be the thing that stops an evening."""
    broken = pd.DataFrame({"nonsense": [1, 2, 3]})
    assert (
        monthly_view.block(
            proposals=broken,
            targets=broken,
            account=broken,
            orders=broken,
            fills=broken,
            today="2026-10-28",
        )
        is not None
    ), "a frame it cannot use is an empty block, not an exception"
    assert (
        monthly_view.block(
            proposals=None,
            targets=None,
            account=None,
            orders=None,
            fills=None,
            today="2026-10-28",
        )
        == {}
    )


def test_the_block_carries_no_identifier() -> None:
    """A ticker, a date or a number: never an order, account or client order id."""
    anchor, later = "2026-10-23", "2026-10-26"
    target = pd.DataFrame(
        {"trade_date": [anchor], "ticker": ["AAA"], "side": ["long"], "weight": [0.01]}
    )
    before = pd.DataFrame(
        {
            "trade_date": [anchor],
            "ticker": ["AAA"],
            "side": ["long"],
            "market_value": [1000.0],
        }
    )
    now = pd.DataFrame(
        {
            "trade_date": [later],
            "ticker": ["AAA"],
            "side": ["long"],
            "market_value": [1010.0],
        }
    )
    orders = pd.DataFrame(
        {
            "trade_date": [anchor],
            "ticker": ["AAA"],
            "intended_notional": [10.0],
            "reason_code": [""],
            "position_intent": ["buy_to_open"],
        }
    )
    fills = pd.DataFrame(
        {
            "trade_date": [anchor],
            "ticker": ["AAA"],
            "filled_notional": [10.0],
            "status": ["FILLED"],
        }
    )
    block = monthly_view.block(
        proposals=_proposals((anchor, "rebalance"), (later, "hold")),
        targets=target,
        account=pd.concat([before, now]),
        orders=orders,
        fills=fills,
        today=later,
        tonight_manifest={"cadence": {"k": 21}},
        nav=1_000_000.0,
    )
    text = json.dumps(block)
    for shape in ("order_id", "account_id", "client_order_id", "oid-"):
        assert shape not in text
    assert block["anchor"]["close"] == anchor
