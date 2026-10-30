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


def test_sent_legs_are_counted_apart_from_under_minimum_legs() -> None:
    """A leg under the $250 minimum was built and never sent, so it is not owed.

    Measured on the 2026-10-23 anchor: 224 legs built, 208 sent and all 208 filled,
    16 under the minimum carrying $2,253.26 that was never meant to trade. The card
    reported one number for both and called the under-minimum legs unfilled.
    """
    anchor = "2026-10-23"
    tickers = [f"T{i:02d}" for i in range(3)]
    orders = pd.DataFrame(
        {
            "trade_date": [anchor] * 4,
            "ticker": tickers[:3] + ["SMALL"],
            "intended_notional": [1000.0, -500.0, 800.0, 120.0],
            "reason_code": ["", "", "", "BELOW_MIN_NOTIONAL"],
            "broker_order_id": ["b-1", "b-2", "b-3", ""],
            "status": ["ACCEPTED", "ACCEPTED", "ACCEPTED", "SKIPPED"],
        }
    )
    fills = pd.DataFrame(
        {
            "trade_date": [anchor] * 3,
            "ticker": tickers,
            "order_id": ["b-1", "b-2", "b-3"],
            "intended_notional": [1000.0, -500.0, 800.0],
            "filled_notional": [1002.0, 499.0, 805.0],
            "fill_price": [10.0, 10.0, 10.0],
            "status": ["FILLED", "FILLED", "FILLED"],
            "slippage_bps": [1.0, 1.0, 1.0],
        }
    )
    card = monthly_view.rebalance_card(anchor, {}, orders, fills, 1_000_000.0)
    assert card["orders"] == 4
    assert card["sent_legs"] == 3
    assert card["filled_legs"] == 3
    assert card["under_minimum_legs"] == 1
    assert card["under_minimum_usd"] == pytest.approx(120.0)
    assert card["legs_incomplete"] == 0
    assert card["dollars_owed"] == 0.0, "every sent leg filled, so nothing is owed"


def test_a_sent_leg_with_no_fill_is_what_is_owed() -> None:
    anchor = "2026-10-23"
    orders = pd.DataFrame(
        {
            "trade_date": [anchor, anchor],
            "ticker": ["AAA", "BBB"],
            "intended_notional": [900.0, -400.0],
            "reason_code": ["", ""],
            "broker_order_id": ["b-1", "b-2"],
            "status": ["ACCEPTED", "ACCEPTED"],
        }
    )
    fills = pd.DataFrame(
        {
            "trade_date": [anchor],
            "ticker": ["AAA"],
            "order_id": ["b-1"],
            "intended_notional": [900.0],
            "filled_notional": [910.0],
            "fill_price": [9.0],
            "status": ["FILLED"],
            "slippage_bps": [2.0],
        }
    )
    card = monthly_view.rebalance_card(anchor, {}, orders, fills, 1_000_000.0)
    assert card["filled_legs"] == 1
    assert card["legs_incomplete"] == 1
    assert card["dollars_owed"] == pytest.approx(400.0), "only the leg with no fill"


def test_each_flip_leg_carries_the_day_it_filled() -> None:
    """A leg priced from the 10-23 close filled on the 10-26 open, and says so."""
    anchor, later = "2026-10-23", "2026-10-26"
    target = pd.DataFrame(
        {"trade_date": [anchor], "ticker": ["CCL"], "side": ["long"], "weight": [0.01]}
    )
    before = pd.DataFrame(
        {
            "trade_date": [anchor],
            "ticker": ["CCL"],
            "side": ["short"],
            "market_value": [-600.0],
        }
    )
    now = pd.DataFrame(
        {
            "trade_date": [later],
            "ticker": ["CCL"],
            "side": ["long"],
            "market_value": [700.0],
        }
    )
    orders = pd.DataFrame(
        {
            "trade_date": [anchor, later],
            "ticker": ["CCL", "CCL"],
            "intended_notional": [600.0, 700.0],
            "reason_code": ["", ""],
            "position_intent": ["buy_to_close", "buy_to_open"],
        }
    )
    fills = pd.DataFrame(
        {
            "trade_date": [anchor, later],
            "ticker": ["CCL", "CCL"],
            "filled_notional": [605.0, 699.0],
            "status": ["FILLED", "FILLED"],
            "updated_at": ["2026-10-26T13:31:00+00:00", "2026-10-27T13:31:00+00:00"],
        }
    )
    rows = monthly_view.flip_rows(target, before, now, orders, fills, anchor)
    assert len(rows) == 1
    assert rows[0]["close_filled"] == "2026-10-23"
    assert rows[0]["close_filled_at"] == "2026-10-26"
    assert rows[0]["open_filled"] == "2026-10-26"
    assert rows[0]["open_filled_at"] == "2026-10-27"


def test_the_guard_threshold_is_the_setting_not_the_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A quiet evening records `drift_guard: null`; the 5% is a setting.

    Measured on the live 2026-10-29 manifest, whose `drift_guard` is null while
    `EFB_DRIFT_GUARD` is 0.05 on the evening: the strip showed no threshold at all.
    """
    monkeypatch.setenv("EFB_DRIFT_GUARD", "0.05")
    assert monthly_view.guard_threshold_from_env() == pytest.approx(0.05)
    for value in ("", "off", "none", "0", "false"):
        monkeypatch.setenv("EFB_DRIFT_GUARD", value)
        assert monthly_view.guard_threshold_from_env() is None
    monkeypatch.setenv("EFB_DRIFT_GUARD", "5")
    assert monthly_view.guard_threshold_from_env() is None, "5 is not a fraction"
    monkeypatch.setenv("EFB_DRIFT_GUARD", "typo")
    assert monthly_view.guard_threshold_from_env() is None


def _two_sector_books() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two names in one sector, one in another, and one the map does not carry."""
    target = pd.DataFrame(
        {
            "trade_date": ["2026-10-23"] * 4,
            "ticker": ["AAA", "BBB", "CCC", "ZZZ"],
            "side": ["long", "short", "long", "long"],
            "weight": [0.10, -0.10, 0.05, 0.02],
        }
    )
    now = pd.DataFrame(
        {
            "trade_date": ["2026-10-29"] * 4,
            "ticker": ["AAA", "BBB", "CCC", "ZZZ"],
            "side": ["long", "short", "long", "long"],
            "weight": [0.12, -0.12, 0.05, 0.02],
        }
    )
    return target, now


def test_the_sector_net_is_signed_and_the_traded_total_is_the_drift() -> None:
    """The identity the panel leans on: sectors add up to the drift card, exactly.

    Netting inside a sector cancels a long that is too small against a short that is
    too big, and a market- and sector-neutral book has that in every sector by design,
    so the net alone would report almost no drift. The traded figure is the one that
    reconciles: `sum(traded_usd) / 2 == drift.half_turnover_usd`.
    """
    target, now = _two_sector_books()
    sector_of = {"AAA": 45, "BBB": 45, "CCC": 20}
    nav = 1_000_000.0
    measured = monthly_view.sectors(target, now, nav, sector_of, anchor="2026-10-23")
    drift = monthly_view.drift(target, now, nav, trading_bps=None)

    by_code = {row["code"]: row for row in measured["rows"]}
    # 45 nets to zero (AAA +2%, BBB -2%) and trades $40,000 both sides;
    # 20 is at target and the unmapped name is untouched.
    assert by_code[45]["delta_usd"] == pytest.approx(0.0, abs=1e-6)
    assert by_code[45]["traded_usd"] == pytest.approx(40_000.0)
    assert by_code[20]["delta_usd"] == pytest.approx(0.0, abs=1e-6)
    assert by_code[None]["traded_usd"] == pytest.approx(0.0)
    assert by_code[None]["label"] == "Unmapped"

    assert measured["both_sides_usd"] == pytest.approx(drift["traded_usd"])
    assert measured["one_side_usd"] == pytest.approx(drift["half_turnover_usd"])
    assert measured["one_side_usd"] == pytest.approx(20_000.0)
    assert measured["n_names"] == 4
    assert measured["n_mapped"] == 3


def test_a_sector_net_moves_when_the_account_does_and_the_map_is_ranked() -> None:
    """The rows are the signed differences, largest absolute first, with drivers."""
    target, now = _two_sector_books()
    now.loc[now["ticker"] == "CCC", "weight"] = 0.03  # 20 drifts by -2%
    now.loc[now["ticker"] == "ZZZ", "weight"] = 0.03  # the unmapped name drifts +1%
    measured = monthly_view.sectors(
        target, now, 1_000_000.0, {"AAA": 45, "BBB": 45, "CCC": 20}, anchor="2026-10-23"
    )
    rows = measured["rows"]
    assert [row["code"] for row in rows][0] == 20, "the largest net comes first"
    # 45 is flat net but $40,000 away name by name: the traded figure says so.
    assert rows[0]["traded_usd"] == pytest.approx(20_000.0)
    unmapped = [row for row in rows if row["code"] is None][0]
    assert unmapped["delta_usd"] == pytest.approx(10_000.0)
    assert measured["unmapped_usd"] == pytest.approx(10_000.0)
    assert [driver["ticker"] for driver in rows[0]["drivers"]] == ["CCC"]


def test_no_map_or_no_nav_leaves_the_field_out_entirely() -> None:
    """An absent field is the page rendering exactly as it did before."""
    target, now = _two_sector_books()
    assert monthly_view.sectors(target, now, 1_000_000.0, None) == {}
    assert monthly_view.sectors(target, now, 1_000_000.0, {}) == {}
    assert monthly_view.sectors(target, now, None, {"AAA": 45}) == {}
    assert monthly_view.sectors(pd.DataFrame(), now, 1_000_000.0, {"AAA": 45}) == {}


def test_the_block_carries_the_sectors_only_when_it_is_given_a_map() -> None:
    proposals = _proposals(("2026-10-23", "rebalance"), ("2026-10-29", "cadence"))
    target, now = _two_sector_books()
    target = target.assign(trade_date="2026-10-23")
    now = now.assign(trade_date="2026-10-29")
    account = now.assign(market_value=None)
    common = {
        "proposals": proposals,
        "targets": target,
        "account": now,
        "orders": pd.DataFrame(),
        "fills": pd.DataFrame(),
        "today": "2026-10-29",
        "tonight_manifest": {"cadence": {"k": 21, "offset": 4}},
        "nav": 1_000_000.0,
    }
    without = monthly_view.block(**common)
    assert "sectors" not in without
    with_map = monthly_view.block(**common, sector_of={"AAA": 45, "BBB": 45, "CCC": 20})
    assert with_map["sectors"]["anchor"] == "2026-10-23"
    assert with_map["sectors"]["one_side_usd"] == pytest.approx(
        with_map["drift"]["half_turnover_usd"]
    )
    del account


def test_the_store_map_is_labels_to_codes_and_unknown_labels_are_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`efb.e11_sectors` holds GICS names; the block files dollars by code."""
    from live import appendix

    rows = pd.DataFrame(
        {
            "trade_date": ["2026-09-11"] * 3,
            "ticker": ["AAA", "BBB", "CCC"],
            "gics_sector": ["Information Technology", "Energy", "Something Else"],
        }
    )
    monkeypatch.setattr(appendix, "read_appendix", lambda spec: rows)
    measured = monthly_view.sector_map_from_store()
    assert measured == {"AAA": 45, "BBB": 10}


def test_the_store_map_is_empty_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from live import appendix

    def boom(spec):  # noqa: ANN001 - the store is unreachable
        raise RuntimeError("no store")

    monkeypatch.setattr(appendix, "read_appendix", boom)
    assert monthly_view.sector_map_from_store() == {}
