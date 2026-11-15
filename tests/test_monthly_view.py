"""The anchored page block: what it measures, and what it must never do.

The numbers here are synthetic and small, except the fixture that reproduces the four
2026-10-23 flips from the shapes the store actually holds: CCL and GEHC short at the
account read and long in the target, F and VZ long and short, each closed on the
rebalance and opened on the next session, each complete at the next account read.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

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


def test_the_hedge_footprint_is_the_rebalances_and_not_tonights() -> None:
    """The page's hedge panel reads tonight's book, which on a hold day is nothing."""
    target = pd.DataFrame(
        {
            "trade_date": ["2026-10-23"] * 3,
            "ticker": ["AAA", "BBB", "CCC"],
            "side": ["long", "short", "long"],
            "weight": [0.10, -0.12, 0.05],
            "previous_weight": [0.08, -0.10, 0.05],
            "reason": ["the hedge moved", "the hedge moved", "new name"],
        }
    )
    reconciliation = pd.DataFrame(
        {
            "trade_date": ["2026-10-23"],
            "traded_risk": [
                json.dumps(
                    {
                        "n_eff": 143.7,
                        "max_weight": 0.0154,
                        "top_variance_shares": [
                            {"ticker": "AAA", "variance_share": 0.0837},
                            {"ticker": "CCC", "variance_share": 0.05},
                        ],
                    }
                )
            ],
        }
    )
    measured = monthly_view.hedge(
        target, reconciliation, "2026-10-23", nav=1_000_000.0, turnover_usd=500_000.0
    )
    assert measured["anchor"] == "2026-10-23"
    assert measured["moved_names"] == 2
    assert measured["book_names"] == 3
    # |0.10 - 0.08| + |-0.12 + 0.10| = 0.04, and the new name is not the hedge's.
    assert measured["moved_usd"] == pytest.approx(40_000.0)
    assert measured["share_of_turnover"] == pytest.approx(0.08)
    assert measured["n_eff"] == pytest.approx(143.7)
    assert [entry["ticker"] for entry in measured["variance_shares"]] == ["AAA", "CCC"]
    assert measured["variance_shares"][0]["weight"] == pytest.approx(0.10)


def test_a_close_with_no_risk_block_still_reports_the_footprint() -> None:
    target = pd.DataFrame(
        {
            "trade_date": ["2026-10-23"],
            "ticker": ["AAA"],
            "weight": [0.10],
            "previous_weight": [0.09],
            "reason": ["the hedge moved"],
        }
    )
    measured = monthly_view.hedge(target, None, "2026-10-23", 1_000_000.0, 500_000.0)
    assert measured["variance_shares"] == []
    assert measured["n_eff"] is None
    assert measured["moved_usd"] == pytest.approx(10_000.0)
    assert monthly_view.hedge(pd.DataFrame(), None, "2026-10-23", 1.0, 1.0) == {}


def test_the_block_carries_the_hedge_with_the_anchor() -> None:
    proposals = _proposals(("2026-10-23", "rebalance"), ("2026-10-29", "cadence"))
    anchor = pd.DataFrame(
        {
            "trade_date": ["2026-10-23"],
            "ticker": ["AAA"],
            "side": ["long"],
            "weight": [0.10],
            "previous_weight": [0.08],
            "reason": ["the hedge moved"],
        }
    )
    block = monthly_view.block(
        proposals=proposals,
        targets=anchor,
        account=anchor.assign(trade_date="2026-10-29", weight=0.10),
        orders=pd.DataFrame(),
        fills=pd.DataFrame(),
        today="2026-10-29",
        tonight_manifest={"cadence": {"k": 21, "offset": 4}},
        nav=1_000_000.0,
    )
    assert block["hedge"]["anchor"] == "2026-10-23"
    assert block["hedge"]["moved_names"] == 1


def test_the_email_line_says_whether_the_block_was_built() -> None:
    """A block that never got built still leaves a page, so the message must say so."""
    from live import notify

    assert monthly_view.state_line(None).startswith("not built: the block raised")
    assert monthly_view.state_line({}).startswith("not built: the store had no anchor")
    assert monthly_view.state_line({"anchor": {}}).startswith(
        "not built: the block carries"
    )
    assert monthly_view.state_line({"anchor": {"close": "2026-10-23"}}) == (
        "built (anchor 2026-10-23)"
    )
    body = notify.compose(
        status="ok",
        target_close="2026-10-29",
        dry_run=False,
        monthly_view=monthly_view.state_line({"anchor": {"close": "2026-10-23"}}),
    )
    assert "Monthly view: built (anchor 2026-10-23)." in body
    without = notify.compose(status="ok", target_close="2026-10-29", dry_run=False)
    assert "Monthly view" not in without
    failed = notify.compose(
        status="ok",
        target_close="2026-10-29",
        dry_run=False,
        monthly_view=monthly_view.state_line(None),
    )
    assert "Monthly view: not built: the block raised" in failed


def test_a_leg_that_cannot_be_sent_is_not_counted_as_one_that_will() -> None:
    """JBL's $269 is under one share: no order can be placed, so it is not in flight."""
    proposals = _proposals(("2026-10-23", "rebalance"), ("2026-10-29", "cadence"))
    target = pd.DataFrame(
        {
            "trade_date": ["2026-10-23"],
            "ticker": ["AAA"],
            "side": ["long"],
            "weight": [0.01],
        }
    )
    manifest = {
        "cadence": {"k": 21, "offset": 4},
        "unfilled_remainder": {"AAA": 120.0},
        "unfilled_unreachable": [
            {
                "ticker": "JBL",
                "unfilled_dollars": 269.37,
                "reason_code": "COVER_UNDER_ONE_SHARE",
                "sent": False,
                "close": "2026-10-26",
            }
        ],
    }
    block = monthly_view.block(
        proposals=proposals,
        targets=target,
        account=target.assign(trade_date="2026-10-29"),
        orders=pd.DataFrame(),
        fills=pd.DataFrame(),
        today="2026-10-29",
        tonight_manifest=manifest,
        nav=1_000_000.0,
    )
    tonight = block["tonight"]
    assert tonight["owed_legs"] == 1
    assert tonight["owed_usd"] == pytest.approx(120.0)
    assert tonight["cannot_send_legs"] == 1
    assert tonight["cannot_send_usd"] == pytest.approx(269.37)
    assert tonight["cannot_send"] == [
        {"ticker": "JBL", "usd": pytest.approx(269.37), "code": "COVER_UNDER_ONE_SHARE"}
    ]
    # The old total is still there, and still the sum of both.
    assert tonight["forced_usd"] == pytest.approx(389.37)


def _anchored_block(anchor_manifest: dict) -> dict:
    anchor, later = "2026-10-23", "2026-10-30"
    proposals = pd.DataFrame(
        {
            "trade_date": [anchor, later],
            "manifest": [
                {"cadence": {"day": "rebalance"}, **anchor_manifest},
                {"cadence": {"day": "hold", "k": 21}},
            ],
        }
    )
    target = pd.DataFrame(
        {"trade_date": [anchor], "ticker": ["AAA"], "side": ["long"], "weight": [0.01]}
    )
    account = pd.DataFrame(
        {
            "trade_date": [later],
            "ticker": ["AAA"],
            "side": ["long"],
            "market_value": [10_000.0],
        }
    )
    return monthly_view.block(
        proposals=proposals,
        targets=target,
        account=account,
        orders=pd.DataFrame(
            {
                "trade_date": [anchor],
                "ticker": ["AAA"],
                "intended_notional": [10.0],
                "reason_code": [""],
                "position_intent": ["buy_to_open"],
            }
        ),
        fills=pd.DataFrame(
            {
                "trade_date": [anchor],
                "ticker": ["AAA"],
                "filled_notional": [10.0],
                "status": ["FILLED"],
            }
        ),
        today=later,
        tonight_manifest={"cadence": {"k": 21}},
        nav=1_000_000.0,
    )


def test_the_block_carries_the_anchors_own_exposures() -> None:
    """A hold day's own pair is one vector twice, so the pair shown is the anchor's.

    The numbers are the 2026-10-23 rebalance's own: the book carried 87.2% of a unit
    exposure at its worst factor going into that hedge, and 3.3e-17 after it.
    """
    block = _anchored_block(
        {
            "exposures_before_hedge": {"market": 0.872, "beta": -0.31},
            "exposures_after_hedge": {"market": 3.3e-17, "beta": -1e-17},
        }
    )
    carried = block["anchor_exposures"]
    assert carried["anchor"] == "2026-10-23"
    assert carried["before"]["market"] == pytest.approx(0.872)
    assert abs(carried["after"]["market"]) < 1e-12


def test_a_close_whose_anchor_carries_no_vectors_leaves_the_field_out() -> None:
    block = _anchored_block({})
    assert "anchor_exposures" not in block


def _ccl_reflip_block() -> dict:
    """The 2026-10-23 flip, the 2026-10-26 open, and the 2026-11-04 guard leg."""
    anchor, opened, guard, latest = (
        "2026-10-23",
        "2026-10-26",
        "2026-11-04",
        "2026-11-05",
    )
    proposals = pd.DataFrame(
        {
            "trade_date": [anchor, "2026-10-29", guard],
            "manifest": [
                {"cadence": {"day": "rebalance"}},
                {"cadence": {"day": "hold", "k": 21}},
                {
                    "cadence": {"day": "hold", "k": 21},
                    "drift_guard": {
                        "fired": True,
                        "legs": [{"ticker": "CCL", "traded": True}],
                    },
                },
            ],
        }
    )
    target = pd.DataFrame(
        {
            "trade_date": [anchor],
            "ticker": ["CCL"],
            "side": ["long"],
            "weight": [0.01],
        }
    )
    before = pd.DataFrame(
        {
            "trade_date": [anchor],
            "ticker": ["CCL"],
            "side": ["short"],
            "market_value": [-600.0],
        }
    )
    # The guard closed the long and opened a short on 11-04, so the account is short
    # by the latest read. A re-flip the account does not show is not a re-flip.
    now = pd.DataFrame(
        {
            "trade_date": [latest],
            "ticker": ["CCL"],
            "side": ["short"],
            "market_value": [-680.0],
        }
    )
    orders = pd.DataFrame(
        {
            "trade_date": [anchor, opened, guard, guard],
            "ticker": ["CCL", "CCL", "CCL", "CCL"],
            "intended_notional": [600.0, 700.0, -650.0, -680.0],
            "reason_code": ["", "", "", ""],
            "position_intent": [
                "buy_to_close",
                "buy_to_open",
                "sell_to_close",
                "sell_to_open",
            ],
        }
    )
    fills = pd.DataFrame(
        {
            "trade_date": [anchor, opened, guard],
            "ticker": ["CCL", "CCL", "CCL"],
            "filled_notional": [605.0, 699.0, 648.0],
            "status": ["FILLED", "FILLED", "FILLED"],
        }
    )
    return monthly_view.block(
        proposals=proposals,
        targets=target,
        account=pd.concat([before, now]),
        orders=orders,
        fills=fills,
        today=latest,
        tonight_manifest={"cadence": {"day": "hold", "k": 21}},
        nav=1_000_000.0,
    )


def test_a_later_guard_leg_is_a_reflip_and_says_so() -> None:
    block = _ccl_reflip_block()
    row = block["bridge_anchor"]["flip_rows"][0]
    assert row["ticker"] == "CCL"
    assert row["refipped_on"] == "2026-11-04"
    assert row["state"] == "refipped"
    assert row["state_label"] == ("re-flipped later by the drift guard on 2026-11-04")
    held = {item["ticker"]: item for item in block["holdings"]["rows"]}["CCL"]
    assert "flipped (2026-10-23 to 2026-10-26)" in held["since"]
    assert "flipped again by the drift guard (2026-11-04)" in held["since"]
    # The pill names the latest event, not the flip the sentence starts with.
    assert held["since_label"] == "Flipped 11-04"


def test_the_guard_history_is_one_row_per_firing_from_the_manifest() -> None:
    """The card per firing reads the hold day's own manifest, and invents nothing.

    The manifest in this fixture records the legs and the firing but no turnover and
    no exposures, so the row says those are unknown rather than printing zero. The
    flip the firing caused comes from the bridge's own refipped_on date.
    """
    block = _ccl_reflip_block()
    rows = block["since_anchor"]["guard_history"]
    assert [row["date"] for row in rows] == ["2026-11-04"]
    row = rows[0]
    assert row["legs_sent"] == 1
    assert row["flips"] == ["CCL"]
    assert row["usd"] is None
    assert row["exposure_before"] is None
    assert "cost_bps" in row


# The guard's NAV on the evenings in this fixture. The 2026-11-12 leg is worth
# $542.96 at it: 0.0005567 of NAV, the weight it moved from -0.0000957 to 0.0004610.
_GUARD_NAV = 975_319.0


def _live_flip_facts_block() -> dict:
    """The 2026-11-13 close, with the flips the live QA sweep found.

    Four names flipped at the 2026-10-23 rebalance (CCL, F, GEHC, VZ). The drift guard
    then flipped CCL and NFLX on 2026-11-04 and MKC on 2026-11-12. The guard also
    traded VZ and F on those evenings to resize them, and their weights keep their
    sign, which is how the page tells a resize from a side change.

    MKC's legs are the live shape and are deliberately cross-day: buy_to_close on
    2026-11-12 and buy_to_open on 2026-11-13. An order pair that demands both legs on
    one date cannot see it, and the 2026-11-13 account read omits MKC, so the guard
    manifest's weight sign is the only evidence the page has. That is the source this
    fixture pins.
    """
    anchor, opened, first_guard, second_guard, latest = (
        "2026-10-23",
        "2026-10-26",
        "2026-11-04",
        "2026-11-12",
        "2026-11-13",
    )
    proposals = pd.DataFrame(
        {
            "trade_date": [anchor, "2026-10-29", first_guard, second_guard],
            "manifest": [
                {"cadence": {"day": "rebalance"}},
                {"cadence": {"day": "hold", "k": 21}},
                {
                    "cadence": {"day": "hold", "k": 21},
                    "drift_guard": {
                        "fired": True,
                        "nav": _GUARD_NAV,
                        # A leg's ticker alone cannot say whether it changed side:
                        # VZ is here because the guard resized it, and its weight
                        # keeps the sign it had. CCL's and NFLX's weights cross zero.
                        "legs": [
                            {
                                "ticker": "CCL",
                                "traded": True,
                                "weight_before": 0.01,
                                "weight_after": -0.01,
                                "delta_notional_pct": -0.02,
                            },
                            {
                                "ticker": "NFLX",
                                "traded": True,
                                "weight_before": 0.004,
                                "weight_after": -0.004,
                                "delta_notional_pct": -0.008,
                            },
                            {
                                "ticker": "VZ",
                                "traded": True,
                                "weight_before": -0.012,
                                "weight_after": -0.009,
                                "delta_notional_pct": 0.003,
                            },
                        ],
                    },
                },
                {
                    "cadence": {"day": "hold", "k": 21},
                    "drift_guard": {
                        "fired": True,
                        "nav": _GUARD_NAV,
                        "legs": [
                            # The live 2026-11-12 leg: short to long, $542.96.
                            {
                                "ticker": "MKC",
                                "traded": True,
                                "weight_before": -0.0000957,
                                "weight_after": 0.0004610,
                                "delta_notional_pct": 0.0005567,
                            },
                            {
                                "ticker": "F",
                                "traded": True,
                                "weight_before": -0.02,
                                "weight_after": -0.015,
                                "delta_notional_pct": 0.005,
                            },
                        ],
                    },
                },
            ],
        }
    )
    names = ["CCL", "F", "GEHC", "VZ", "NFLX", "MKC"]
    target_side = {"CCL": "long", "F": "short", "GEHC": "long", "VZ": "short",
                   "NFLX": "long", "MKC": "short"}
    before_side = {"CCL": "short", "F": "long", "GEHC": "short", "VZ": "long",
                   "NFLX": "long", "MKC": "short"}
    # MKC is deliberately absent from the account read. The 11-12 guard's reopening
    # buy_to_open was submitted after the read, so the read shows no side for MKC at
    # all. The flip still happened, and the page has to say so from the legs.
    now_side = {"CCL": "short", "F": "short", "GEHC": "long", "VZ": "short",
                "NFLX": "short"}
    target = pd.DataFrame(
        {
            "trade_date": [anchor] * len(names),
            "ticker": names,
            "side": [target_side[name] for name in names],
            "weight": [0.01] * len(names),
        }
    )
    before = pd.DataFrame(
        {
            "trade_date": [anchor] * len(names),
            "ticker": names,
            "side": [before_side[name] for name in names],
            "market_value": [(-600.0 if before_side[name] == "short" else 600.0)
                             for name in names],
        }
    )
    now_names = [name for name in names if name in now_side]
    now = pd.DataFrame(
        {
            "trade_date": [latest] * len(now_names),
            "ticker": now_names,
            "side": [now_side[name] for name in now_names],
            "market_value": [(-650.0 if now_side[name] == "short" else 650.0)
                             for name in now_names],
        }
    )
    orders = pd.DataFrame(
        {
            "trade_date": [
                anchor, anchor, anchor, anchor,
                opened, opened, opened, opened,
                first_guard, first_guard, first_guard, first_guard, first_guard,
                second_guard, latest, second_guard,
            ],
            "ticker": [
                "CCL", "F", "GEHC", "VZ",
                "CCL", "F", "GEHC", "VZ",
                "CCL", "CCL", "NFLX", "NFLX", "VZ",
                "MKC", "MKC", "F",
            ],
            "intended_notional": [
                600.0, -633.0, 2000.0, -988.0,
                677.0, -1600.0, 2328.0, -2434.0,
                -650.0, -660.0, 900.0, -910.0, -300.0,
                420.0, 430.0, -200.0,
            ],
            "reason_code": [""] * 16,
            "position_intent": [
                "buy_to_close", "sell_to_close", "buy_to_close", "sell_to_close",
                "buy_to_open", "sell_to_open", "buy_to_open", "sell_to_open",
                "sell_to_close", "sell_to_open", "sell_to_close", "sell_to_open",
                "sell_to_open",
                "buy_to_close", "buy_to_open", "sell_to_open",
            ],
        }
    )
    fills = pd.DataFrame(
        {
            "trade_date": list(orders["trade_date"]),
            "ticker": list(orders["ticker"]),
            "filled_notional": [abs(value) for value in orders["intended_notional"]],
            "status": ["FILLED"] * len(orders),
        }
    )
    return monthly_view.block(
        proposals=proposals,
        targets=target,
        account=pd.concat([before, now]),
        orders=orders,
        fills=fills,
        today=latest,
        tonight_manifest={"cadence": {"day": "hold", "k": 21}},
        nav=1_000_000.0,
    )


def test_the_rebalance_flipped_four_names_and_only_ccl_flipped_again() -> None:
    """The live facts: CCL, F, GEHC and VZ flipped once; CCL flipped back on 11-04.

    VZ, GEHC and F must not read as re-flipped. The guard traded all three, and a
    guard leg is not a side change.
    """
    block = _live_flip_facts_block()
    rows = {row["ticker"]: row for row in block["bridge_anchor"]["flip_rows"]}
    assert sorted(rows) == ["CCL", "F", "GEHC", "VZ"]
    assert rows["CCL"]["refipped_on"] == "2026-11-04"
    assert rows["CCL"]["state"] == "refipped"
    for ticker in ("VZ", "GEHC", "F"):
        assert rows[ticker]["refipped_on"] is None, ticker
        assert rows[ticker]["state"] != "refipped", ticker
        assert "re-flipped" not in rows[ticker]["state_label"], ticker


def test_the_guard_cards_name_the_flips_each_firing_caused() -> None:
    """11-04 flipped CCL and NFLX; 11-12 flipped MKC. The manifest legs are not it."""
    block = _live_flip_facts_block()
    firings = {row["date"]: row for row in block["since_anchor"]["guard_history"]}
    assert firings["2026-11-04"]["flips"] == ["CCL", "NFLX"]
    assert firings["2026-11-12"]["flips"] == ["MKC"]
    # CCL is on the 11-04 card as a guard flip, and the card says it is reversing
    # the rebalance's own flip rather than being a plain one like NFLX.
    assert firings["2026-11-04"]["reversals"] == {"CCL": "2026-10-23"}
    assert firings["2026-11-12"]["reversals"] == {}
    # VZ and F were guard legs on those evenings and did not change side.
    assert "VZ" not in firings["2026-11-04"]["flips"]
    assert "F" not in firings["2026-11-12"]["flips"]


def test_the_flips_list_carries_every_guard_sign_change() -> None:
    """The guard list is the whole sign-change set: CCL, NFLX and MKC.

    CCL is both a rebalance flip and a guard flip. The rebalance took it from short
    to long on 2026-10-23 and the guard took it back on 2026-11-04. Dropping it from
    this list would hide half of what the guard did; the 11-04 card labels it as a
    reversal instead, so the two rows are read together.
    """
    block = _live_flip_facts_block()
    guard_flips = {row["ticker"]: row for row in block["since_anchor"]["guard_flips"]}
    assert sorted(guard_flips) == ["CCL", "MKC", "NFLX"]
    assert guard_flips["CCL"]["date"] == "2026-11-04"
    assert guard_flips["CCL"]["from_side"] == "long"
    assert guard_flips["CCL"]["to_side"] == "short"
    assert guard_flips["CCL"]["usd"] == pytest.approx(0.02 * _GUARD_NAV)
    assert guard_flips["NFLX"]["date"] == "2026-11-04"
    assert guard_flips["NFLX"]["usd"] == pytest.approx(0.008 * _GUARD_NAV)
    assert guard_flips["MKC"]["date"] == "2026-11-12"
    assert guard_flips["MKC"]["usd"] == pytest.approx(542.96, abs=0.01)
    assert guard_flips["NFLX"]["from_side"] == "long"
    assert guard_flips["NFLX"]["to_side"] == "short"
    assert guard_flips["MKC"]["from_side"] == "short"
    assert guard_flips["MKC"]["to_side"] == "long"
    # A resize is not a sign change and is never in this list.
    for ticker in ("VZ", "GEHC", "F"):
        assert ticker not in guard_flips, ticker


def test_the_guard_manifest_finds_the_cross_day_flip_the_order_pair_cannot() -> None:
    """MKC's live shape: close on 11-12, open on 11-13, and no side in the read.

    The order-pair path needs both legs on one trade_date, so it sees neither
    evening. The guard manifest records one leg, traded, whose weight crossed zero,
    which is the same fact without the same-day assumption.
    """
    anchor, close_day, open_day = "2026-10-23", "2026-11-12", "2026-11-13"
    proposals = pd.DataFrame(
        {
            "trade_date": [anchor, close_day],
            "manifest": [
                {"cadence": {"day": "rebalance"}},
                {
                    "cadence": {"day": "hold", "k": 21},
                    "drift_guard": {
                        "fired": True,
                        "nav": _GUARD_NAV,
                        "legs": [
                            {
                                "ticker": "MKC",
                                "traded": True,
                                "weight_before": -0.0000957,
                                "weight_after": 0.0004610,
                                "delta_notional_pct": 0.0005567,
                            },
                            # A resize that kept its sign, beside the flip.
                            {
                                "ticker": "VZ",
                                "traded": True,
                                "weight_before": -0.012,
                                "weight_after": -0.009,
                                "delta_notional_pct": 0.003,
                            },
                        ],
                    },
                },
            ],
        }
    )
    target = pd.DataFrame(
        {
            "trade_date": [anchor],
            "ticker": ["MKC"],
            "side": ["short"],
            "weight": [0.01],
        }
    )
    before = pd.DataFrame(
        {
            "trade_date": [anchor],
            "ticker": ["MKC"],
            "side": ["short"],
            "market_value": [-500.0],
        }
    )
    orders = pd.DataFrame(
        {
            "trade_date": [close_day, open_day],
            "ticker": ["MKC", "MKC"],
            "position_intent": ["buy_to_close", "buy_to_open"],
            "intended_notional": [93.32, 449.85],
            "broker_order_id": ["id-1", "id-2"],
        }
    )
    now = pd.DataFrame(columns=["trade_date", "ticker", "side", "market_value"])
    alone = monthly_view.order_flips(orders, before, target, now, anchor, open_day)
    assert "MKC" not in {event["ticker"] for event in alone}, (
        "the order pair cannot see a flip whose two legs fall on different days"
    )
    manifest = monthly_view.guard_manifest_flips(
        proposals, anchor, open_day, 1_000_000.0
    )
    assert [event["ticker"] for event in manifest] == ["MKC"]
    assert manifest[0]["date"] == close_day
    assert manifest[0]["from_side"] == "short"
    assert manifest[0]["to_side"] == "long"
    assert manifest[0]["usd"] == pytest.approx(542.96, abs=0.01)
    merged = monthly_view.merge_flip_events(manifest, alone)
    assert [event["ticker"] for event in merged] == ["MKC"]
    assert merged[0]["date"] == close_day


def test_two_sources_of_the_same_flip_produce_one_row() -> None:
    """CCL is seen by both sources on 2026-11-04, and the list must carry it once.

    The manifest supplies the sides; where it has no dollar figure the order path
    fills it in. A duplicate (ticker, date) is dropped, not merged into a second row.
    """
    manifest = [
        {
            "ticker": "CCL",
            "date": "2026-11-04",
            "from_side": "long",
            "to_side": "short",
            "usd": None,
        }
    ]
    orders = [
        {
            "ticker": "CCL",
            "date": "2026-11-04",
            "from_side": "long",
            "to_side": "short",
            "usd": 650.0,
        },
        {
            "ticker": "NFLX",
            "date": "2026-11-04",
            "from_side": "long",
            "to_side": "short",
            "usd": 900.0,
        },
    ]
    merged = monthly_view.merge_flip_events(manifest, orders)
    assert [(event["ticker"], event["date"]) for event in merged] == [
        ("CCL", "2026-11-04"),
        ("NFLX", "2026-11-04"),
    ]
    ccl = merged[0]
    assert ccl["usd"] == 650.0
    # The guard list keeps every sign change, CCL included.
    guard_rows = monthly_view._guard_flip_rows(merged)
    assert [row["ticker"] for row in guard_rows] == ["CCL", "NFLX"]


def test_mkc_has_a_flips_list_row_and_a_holdings_row() -> None:
    """The MKC the republish needs: in the flips list and in the holdings table."""
    block = _live_flip_facts_block()
    guard_flips = {row["ticker"]: row for row in block["since_anchor"]["guard_flips"]}
    assert "MKC" in guard_flips
    assert guard_flips["MKC"]["date"] == "2026-11-12"
    assert guard_flips["MKC"]["from_side"] == "short"
    assert guard_flips["MKC"]["to_side"] == "long"
    assert guard_flips["MKC"]["usd"] == pytest.approx(542.96, abs=0.01)
    held = {
        row["ticker"]: row for row in block["holdings"]["rows"]
    }
    assert "MKC" in held
    assert held["MKC"]["since_kind"] == "flipped"
    assert "flipped by the drift guard (2026-11-12)" in held["MKC"]["since"]
    assert held["MKC"]["since_label"] == "Flipped 11-12"


def test_the_manifest_does_not_call_a_resize_a_flip() -> None:
    """VZ and F are guard legs on those evenings, and their weights keep their sign."""
    block = _live_flip_facts_block()
    flips = {event["ticker"] for event in block["since_anchor"]["guard_flips"]}
    for ticker in ("VZ", "GEHC", "F"):
        assert ticker not in flips, ticker
    firings = {row["date"]: row for row in block["since_anchor"]["guard_history"]}
    assert "VZ" not in firings["2026-11-04"]["flips"]
    assert "F" not in firings["2026-11-12"]["flips"]


def test_a_submitted_opening_leg_counts_when_the_account_read_lags() -> None:
    """MKC's shape: the close filled, the reopen went out after the account read.

    order_flips used to require a current side, so a name the read had not caught up
    with was skipped. The legs are the evidence: the buy_to_close leaves the short
    target side, and the buy_to_open submitted that night opens the long. A close
    with no sent open is an exit, not a flip, and an unsent open proves nothing.
    """
    anchor, guard, latest = "2026-10-23", "2026-11-12", "2026-11-13"
    target = pd.DataFrame(
        {
            "trade_date": [anchor, anchor],
            "ticker": ["MKC", "AAA"],
            "side": ["short", "long"],
            "weight": [0.01, 0.01],
        }
    )
    before = pd.DataFrame(
        {
            "trade_date": [anchor, anchor],
            "ticker": ["MKC", "AAA"],
            "side": ["short", "long"],
            "market_value": [-500.0, 500.0],
        }
    )
    orders = pd.DataFrame(
        {
            "trade_date": [guard, guard, guard],
            "ticker": ["MKC", "MKC", "AAA"],
            "position_intent": ["buy_to_close", "buy_to_open", "sell_to_close"],
            "intended_notional": [93.32, 449.85, 500.0],
            "broker_order_id": ["id-1", "id-2", ""],
        }
    )
    now = pd.DataFrame(columns=["trade_date", "ticker", "side", "market_value"])
    events = monthly_view.order_flips(orders, before, target, now, anchor, latest)
    assert events == [
        {
            "ticker": "MKC",
            "date": guard,
            "from_side": "short",
            "to_side": "long",
            "usd": pytest.approx(543.17),
        }
    ]


def test_an_unsent_opening_leg_is_not_a_flip() -> None:
    """A refused open carries a close but no broker id, so nothing proves the side."""
    anchor, guard, latest = "2026-10-23", "2026-11-12", "2026-11-13"
    target = pd.DataFrame(
        {"trade_date": [anchor], "ticker": ["MKC"], "side": ["short"], "weight": [0.01]}
    )
    before = pd.DataFrame(
        {
            "trade_date": [anchor],
            "ticker": ["MKC"],
            "side": ["short"],
            "market_value": [-500.0],
        }
    )
    orders = pd.DataFrame(
        {
            "trade_date": [guard, guard],
            "ticker": ["MKC", "MKC"],
            "position_intent": ["buy_to_close", "buy_to_open"],
            "intended_notional": [93.32, 449.85],
            "broker_order_id": ["id-1", ""],
        }
    )
    now = pd.DataFrame(columns=["trade_date", "ticker", "side", "market_value"])
    assert monthly_view.order_flips(orders, before, target, now, anchor, latest) == []


def test_the_holdings_rows_name_a_guard_flip_as_a_flip() -> None:
    block = _live_flip_facts_block()
    held = {row["ticker"]: row for row in block["holdings"]["rows"]}
    assert held["NFLX"]["since"] == "flipped by the drift guard (2026-11-04)"
    assert held["MKC"]["since"] == "flipped by the drift guard (2026-11-12)"
    # The names the guard only resized keep the resize note: VZ's own rebalance flip
    # is stated once, and neither name is said to have flipped again.
    assert "drift guard leg (2026-11-04)" in held["VZ"]["since"]
    assert "flipped again" not in held["VZ"]["since"]
    assert "drift guard leg (2026-11-12)" in held["F"]["since"]
    assert "flipped again" not in held["F"]["since"]


def test_kvues_own_row_says_retired_owed_and_cannot_be_traded() -> None:
    anchor, latest = "2026-10-23", "2026-11-05"
    target = pd.DataFrame(
        {
            "trade_date": [anchor, anchor],
            "ticker": ["KVUE", "AAA"],
            "side": ["long", "long"],
            "weight": [0.004, 0.01],
        }
    )
    now = pd.DataFrame(
        {
            "trade_date": [latest],
            "ticker": ["AAA"],
            "side": ["long"],
            "weight": [0.01],
        }
    )
    block = monthly_view.block(
        proposals=_proposals((anchor, "rebalance"), (latest, "hold")),
        targets=target,
        account=now,
        orders=pd.DataFrame(),
        fills=pd.DataFrame(),
        today=latest,
        tonight_manifest={"cadence": {"day": "hold", "k": 21}},
        nav=1_000_000.0,
    )
    rows = {item["ticker"]: item for item in block["holdings"]["rows"]}
    kvue = rows["KVUE"]
    assert kvue["retired"] is True and kvue["owed"] is True
    assert kvue["since"] == "retired (acquired by KMB), owed, cannot be traded"
    assert kvue["since_label"] == "Retired"
    assert kvue["gap_weight"] == pytest.approx(-0.004)
    assert kvue["gap_usd"] == pytest.approx(-4_000.0)
    assert rows["AAA"]["since"] == "opened at the rebalance (2026-10-23)"
    assert rows["AAA"]["since_label"] == "Opened 10-23"


def _spread(
    rows: list[dict], total: float, key: str = "intended_notional"
) -> list[dict]:
    """Give `rows` dollars that sum to `total`, the last one carrying the rest."""
    share = round(total / len(rows), 2)
    for row in rows:
        row[key] = share
    rows[-1][key] = round(total - share * (len(rows) - 1), 2)
    return rows


def _leg(
    day: str, ticker: str, intent: str, code: str = "", broker: str | None = None
) -> dict:
    return {
        "trade_date": day,
        "ticker": ticker,
        "position_intent": intent,
        "reason_code": code,
        "broker_order_id": (f"id-{ticker}-{day}" if broker is None else broker),
        "intended_notional": 0.0,
        "filled_notional": 0.0,
        "status": "FILLED",
    }


def _the_live_leg_table() -> dict:
    """Every leg the store held on 2026-11-11, in the shapes it holds them.

    The counts and dollars are the live ones: 224 rows on the 2026-10-23 rebalance
    ($546,256.69, of which 16 were under the minimum and never sent), 12 sent legs
    on 2026-10-26 (the four second legs, plus the eight legs that re-traded a
    rebalance that had already filled, $3,632.28 including CHTR, the
    unfilled-remainder bug fixed on
    2026-10-27), the guard's 109 sent legs on 2026-10-30 ($68,859) and 140 on
    2026-11-04 ($96,938.76), two second legs on 2026-11-05, JBL's $269.37 that is
    under one share, and the 315 legs under the $250 minimum ($91,697.42) that the
    old table counted as guard.
    """
    anchor, hold, guard_1, guard_2, flip_2 = (
        "2026-10-23",
        "2026-10-26",
        "2026-10-30",
        "2026-11-04",
        "2026-11-05",
    )
    closes = ["CCL", "F", "GEHC", "VZ"]
    legs: list[dict] = []
    # The rebalance: 208 sent and 16 under the minimum, one row per name per side.
    for index in range(208):
        ticker = f"N{index:03d}"
        legs.append(
            _leg(anchor, ticker, "buy_to_open" if index % 2 else "sell_to_close")
        )
    # Four of those 208 are the flip closes, so 2026-10-26's opens have a close to
    # answer and are second legs. The other eight on 2026-10-26 are the rebalance's
    # own remainder, sent again on the next close.
    for index, ticker in enumerate(closes):
        legs[index]["ticker"] = ticker
        legs[index]["position_intent"] = (
            "buy_to_close" if ticker in ("CCL", "GEHC") else "sell_to_close"
        )
    _spread(legs[-208:], 544_003.43)
    for index in range(16):
        legs.append(
            _leg(
                anchor,
                f"M{index:03d}",
                "sell_to_close",
                "BELOW_MIN_NOTIONAL",
                broker="",
            )
        )
    _spread(legs[-16:], 2_253.26)
    # 2026-10-26's twelve sent legs, on the store's own rows and dollars: the
    # four second legs of the rebalance's flips (CCL, F, GEHC, VZ) and the eight
    # that re-traded a rebalance that had already filled ($3,632.28, CHTR in it).
    # CHTR is the case the flip rule settles: its side did not change across the
    # rebalance, so its open is a re-trade even though a close went out earlier.
    for ticker, intent, dollars in [
        ("CCL", "buy_to_open", 677.706005),
        ("F", "sell_to_open", -1_600.356208),
        ("GEHC", "buy_to_open", 2_328.089088),
        ("VZ", "sell_to_open", -2_434.046379),
        ("AKAM", "buy_to_close", 290.448717),
        ("CHTR", "buy_to_open", 431.043870),
        ("HPE", "sell_to_close", -413.676752),
        ("INTC", "sell_to_close", -808.253874),
        ("MRVL", "sell_to_close", -517.467381),
        ("NVDA", "buy_to_close", 257.463043),
        ("STX", "sell_to_close", -471.735590),
        ("WDC", "sell_to_close", -442.191471),
    ]:
        legs.append(_leg(hold, ticker, intent))
        legs[-1]["intended_notional"] = dollars
    # The guard's two evenings.
    for index in range(109):
        legs.append(_leg(guard_1, f"G{index:03d}", "sell_to_close"))
    _spread(legs[-109:], 68_859.00)
    for index in range(140):
        legs.append(_leg(guard_2, f"H{index:03d}", "buy_to_close"))
    legs[-140].update({"ticker": "CCL", "position_intent": "sell_to_close"})
    legs[-139].update({"ticker": "NFLX", "position_intent": "buy_to_close"})
    _spread(legs[-140:], 96_938.76)
    # Their second legs, the day after, on the store's own dollars.
    legs.append(_leg(flip_2, "CCL", "sell_to_open"))
    legs[-1]["intended_notional"] = -315.757109
    legs.append(_leg(flip_2, "NFLX", "buy_to_open"))
    legs[-1]["intended_notional"] = 682.697473
    # JBL: owed, under one share, never an order.
    legs.append(_leg(hold, "JBL", "buy_to_close", "COVER_UNDER_ONE_SHARE", broker=""))
    legs[-1]["intended_notional"] = 269.37
    # The 315 the guard could not size, spread over its two evenings.
    refused = [
        _leg(
            guard_1 if index % 2 else guard_2,
            f"U{index:03d}",
            "sell_to_close",
            "BELOW_MIN_NOTIONAL",
            broker="",
        )
        for index in range(315)
    ]
    _spread(refused, 91_697.42)
    legs.extend(refused)

    orders = pd.DataFrame(legs)
    proposals = pd.DataFrame(
        {
            "trade_date": [anchor, guard_1, guard_2],
            "manifest": [
                {"cadence": {"day": "rebalance"}},
                {
                    "cadence": {"day": "hold", "k": 21},
                    "drift_guard": {"fired": True, "legs": []},
                },
                {
                    "cadence": {"day": "hold", "k": 21},
                    "drift_guard": {"fired": True, "legs": []},
                },
            ],
        }
    )
    target = pd.DataFrame(
        {
            "trade_date": [anchor] * 6,
            "ticker": ["CCL", "F", "GEHC", "VZ", "CHTR", "NFLX"],
            "side": ["long", "short", "long", "short", "long", "short"],
            "weight": [0.01, -0.002, 0.002, -0.003, 0.0075, -0.0016],
        }
    )
    # The account at the anchor close, before the rebalance traded: the four
    # names whose side it changed there are the flip rows (CCL, F, GEHC, VZ).
    # CHTR was long before and long at the target, so it is not a flip.
    account = pd.DataFrame(
        [
            (anchor, "CCL", "short", -600.5369),
            (anchor, "F", "long", 633.191546),
            (anchor, "GEHC", "short", -2_000.6),
            (anchor, "VZ", "long", 988.565164),
            (anchor, "CHTR", "long", 8_935.301232),
            (anchor, "NFLX", "short", -3_156.48),
            (flip_2, "CCL", "long", 700.0),
            (flip_2, "F", "short", -700.0),
            (flip_2, "GEHC", "long", 700.0),
            (flip_2, "VZ", "short", -700.0),
            (flip_2, "CHTR", "long", 900.0),
            (flip_2, "NFLX", "short", -350.0),
        ],
        columns=["trade_date", "ticker", "side", "market_value"],
    )
    return monthly_view.block(
        proposals=proposals,
        targets=target,
        account=account,
        orders=orders,
        fills=pd.DataFrame(),
        today=flip_2,
        tonight_manifest={"cadence": {"day": "hold", "k": 21}},
        nav=1_000_000.0,
    )


def test_legs_are_counted_by_the_event_that_asked_for_them() -> None:
    """The live table, reason by reason, on the store's own 2026-11-11 rows.

    The old table read `position_intent` on every submitted order (which every order
    carries) as "reversal second leg", and read the refusal code `BELOW_MIN_NOTIONAL`
    as "guard", so 315 legs the guard never sent were counted as guard legs and every
    guard leg that did go was counted as a flip.
    """
    block = _the_live_leg_table()
    assert block is not None
    rows = {row["reason"]: row for row in block["since_anchor"]["trades_by_reason"]}

    rebalance = rows["rebalance"]
    assert (rebalance["legs"], rebalance["sent_legs"]) == (224, 208)
    assert rebalance["usd"] == pytest.approx(546_256.69, abs=0.01)

    guard = rows["guard"]
    assert (guard["legs"], guard["sent_legs"]) == (249, 249)
    assert guard["usd"] == pytest.approx(68_859.00 + 96_938.76, abs=0.01)

    flip = rows["reversal second leg"]
    assert (flip["legs"], flip["sent_legs"]) == (6, 6)
    # The six are CCL, F, GEHC and VZ on 2026-10-26 and CCL and NFLX on
    # 2026-11-05; CHTR is not among them. Its 2026-10-26 open is in the
    # re-trade row below, which is why the row's dollars carry CHTR's 431.04.
    assert flip["usd"] == pytest.approx(8_038.65, abs=0.01)

    carried = rows["carried leg"]
    assert (carried["legs"], carried["sent_legs"]) == (1, 0)
    assert carried["usd"] == pytest.approx(269.37, abs=0.01)

    # The eight sent legs on 2026-10-26 that are neither a guard leg nor a second
    # leg: they re-traded a rebalance that had already filled, which was the
    # unfilled-remainder bug, fixed on 2026-10-27. They are not a remainder and
    # they are not a rebalance: they get their own row.
    retrade = rows["remainder re-trade (bug, fixed 10-27)"]
    assert (retrade["legs"], retrade["sent_legs"]) == (8, 8)
    assert retrade["usd"] == pytest.approx(3_632.28, abs=0.01)
    assert retrade["usd"] > 3_632.28 - 431.05  # CHTR is inside this total
    assert "rebalance remainder" not in rows

    not_sent = block["since_anchor"]["not_sent"]
    assert (not_sent["legs"], not_sent["under_minimum"]["legs"]) == (315, 315)
    assert not_sent["usd"] == pytest.approx(91_697.42, abs=0.01)
    assert not_sent["other"] == []

    # And the whole table adds up to the rows the store holds: 803, not 804 and not
    # a count that silently dropped the legs that never went.
    total = sum(row["legs"] for row in rows.values()) + not_sent["legs"]
    assert total == 803


def test_a_hold_day_never_resizes_a_holding() -> None:
    """The 2026-11-04 labels: BNY, MET, WMT and FLEX were guard work, not resizes.

    Nothing resizes a holding on a hold day, and the page said four names did
    because it read any row in `efb.orders` as a trade: the guard's candidates
    under the minimum carry a reason code and no broker id, and were counted as
    a resize. A name the guard sent but its manifest omitted is a guard leg; a
    name it could not size is still held, and the row says which.
    """
    anchor, guard_day, latest = "2026-10-23", "2026-11-04", "2026-11-05"
    proposals = pd.DataFrame(
        {
            "trade_date": [anchor, guard_day],
            "manifest": [
                {"cadence": {"day": "rebalance"}},
                {
                    "cadence": {"day": "hold", "k": 21},
                    "drift_guard": {
                        "fired": True,
                        "legs": [
                            {"ticker": "NVDA", "traded": True},
                            {"ticker": "BNY", "traded": False},
                        ],
                    },
                },
            ],
        }
    )
    tickers = ["BNY", "MET", "WMT", "FLEX"]
    weights = [-0.0118, 0.0112, -0.0094, -0.0080]
    now_weights = [-0.0126, 0.0118, -0.0098, -0.0081]
    target = pd.DataFrame(
        {
            "trade_date": [anchor] * 4,
            "ticker": tickers,
            "side": ["short", "long", "short", "short"],
            "weight": weights,
        }
    )
    account = pd.DataFrame(
        {
            "trade_date": [anchor] * 4 + [latest] * 4,
            "ticker": tickers * 2,
            "side": ["short", "long", "short", "short"] * 2,
            "weight": weights + now_weights,
            "market_value": [
                -11_800.0,
                11_200.0,
                -9_400.0,
                -8_000.0,
                -12_600.0,
                11_800.0,
                -9_800.0,
                -8_100.0,
            ],
        }
    )
    orders = pd.DataFrame(
        {
            "trade_date": [guard_day] * 4,
            "ticker": tickers,
            "intended_notional": [180.0, 160.0, 120.0, 90.0],
            "reason_code": ["BELOW_MIN_NOTIONAL", "", "BELOW_MIN_NOTIONAL", ""],
            "position_intent": ["buy_to_close"] * 4,
            "broker_order_id": ["", "id-met", "", "id-flex"],
        }
    )
    block = monthly_view.block(
        proposals=proposals,
        targets=target,
        account=account,
        orders=orders,
        fills=pd.DataFrame(),
        today=latest,
        tonight_manifest={"cadence": {"day": "hold", "k": 21}},
        nav=1_000_000.0,
    )
    assert block is not None
    rows = {row["ticker"]: row for row in block["holdings"]["rows"]}
    assert rows["BNY"]["since"] == "held, guard leg under the minimum (2026-11-04)"
    assert rows["WMT"]["since"] == "held, guard leg under the minimum (2026-11-04)"
    assert rows["MET"]["since"] == "drift guard leg (2026-11-04)"
    assert rows["FLEX"]["since"] == "drift guard leg (2026-11-04)"
    for ticker in tickers:
        assert rows[ticker]["since_kind"] != "resized"
        assert "resized" not in rows[ticker]["since"]


def test_an_under_minimum_leg_on_a_guard_day_is_not_a_guard_leg() -> None:
    """The exact misclassification: the guard's unsizeable candidates are not legs."""
    anchor, guard_day = "2026-10-23", "2026-10-30"
    proposals = pd.DataFrame(
        {
            "trade_date": [anchor, guard_day],
            "manifest": [
                {"cadence": {"day": "rebalance"}},
                {
                    "cadence": {"day": "hold", "k": 21},
                    "drift_guard": {"fired": True, "legs": []},
                },
            ],
        }
    )
    orders = pd.DataFrame(
        {
            "trade_date": [guard_day, guard_day],
            "ticker": ["AAA", "BBB"],
            "intended_notional": [1_000.0, 120.0],
            "reason_code": ["", "BELOW_MIN_NOTIONAL"],
            "position_intent": ["sell_to_close", "sell_to_close"],
            "broker_order_id": ["id-1", ""],
        }
    )
    block = monthly_view.block(
        proposals=proposals,
        targets=pd.DataFrame(
            {
                "trade_date": [anchor],
                "ticker": ["AAA"],
                "side": ["long"],
                "weight": [0.01],
            }
        ),
        account=pd.DataFrame(
            {
                "trade_date": [guard_day],
                "ticker": ["AAA"],
                "side": ["long"],
                "market_value": [1_000.0],
            }
        ),
        orders=orders,
        fills=pd.DataFrame(),
        today=guard_day,
        tonight_manifest={},
        nav=1_000_000.0,
    )
    assert block is not None
    rows = {row["reason"]: row for row in block["since_anchor"]["trades_by_reason"]}
    assert rows["guard"]["legs"] == 1
    assert block["since_anchor"]["not_sent"]["legs"] == 1
    assert block["since_anchor"]["not_sent"]["under_minimum"]["usd"] == pytest.approx(
        120.0
    )


def test_a_close_and_open_in_one_evening_is_not_a_second_leg() -> None:
    """A guard evening flips a name inside itself; that open is not a second day."""
    anchor, guard_day = "2026-10-23", "2026-11-04"
    proposals = pd.DataFrame(
        {
            "trade_date": [anchor, guard_day],
            "manifest": [
                {"cadence": {"day": "rebalance"}},
                {
                    "cadence": {"day": "hold", "k": 21},
                    "drift_guard": {"fired": True, "legs": []},
                },
            ],
        }
    )
    orders = pd.DataFrame(
        {
            "trade_date": [guard_day, guard_day],
            "ticker": ["CCL", "CCL"],
            "intended_notional": [-600.0, 650.0],
            "reason_code": ["", ""],
            "position_intent": ["sell_to_close", "sell_to_open"],
            "broker_order_id": ["id-1", "id-2"],
        }
    )
    block = monthly_view.block(
        proposals=proposals,
        targets=pd.DataFrame(
            {
                "trade_date": [anchor],
                "ticker": ["CCL"],
                "side": ["long"],
                "weight": [0.01],
            }
        ),
        account=pd.DataFrame(
            {
                "trade_date": [guard_day],
                "ticker": ["CCL"],
                "side": ["short"],
                "market_value": [-650.0],
            }
        ),
        orders=orders,
        fills=pd.DataFrame(),
        today=guard_day,
        tonight_manifest={},
        nav=1_000_000.0,
    )
    assert block is not None
    rows = {row["reason"]: row for row in block["since_anchor"]["trades_by_reason"]}
    assert rows["guard"]["legs"] == 2
    assert "reversal second leg" not in rows


def test_the_anchors_construction_is_the_book_that_traded() -> None:
    """The one construction the page may show, read from the anchor's own record."""
    manifest = {
        "n_names": 496,
        "n_excluded": 0,
        "n_dropped_no_risk": 3,
        "n_dropped": 300,
        "n_kept": 196,
        "dropped_no_risk": [
            {"ticker": "FDXF", "reason": "no specific variance"},
            {"ticker": "HONA", "reason": "no specific variance"},
            {"ticker": "Q", "reason": "no specific variance"},
        ],
        "excluded_detail": [],
        "construction_floor_shares": 20,
        "kept_gross": 1.0,
        "kept_net": 0.0,
        "kept_achieved_annual_vol": 0.027929290997962,
    }
    built = monthly_view.anchor_construction("2026-10-23", manifest)
    assert built is not None
    # The universe the run looked at: the sized book plus the two drop lists.
    assert built["considered"] == 499
    assert built["left_out_no_risk"] == 3
    assert [row["ticker"] for row in built["left_out_no_risk_names"]] == [
        "FDXF",
        "HONA",
        "Q",
    ]
    assert built["removed_too_small"] == 300
    assert built["final_names"] == 196
    assert built["gross"] == 1.0
    assert built["net"] == 0.0
    assert built["vol"] == 0.027929290997962
    assert built["floor"] == "20 shares"


def test_a_manifest_without_a_kept_count_leaves_the_construction_out() -> None:
    # A document that cannot answer says nothing: the page draws no panel, rather
    # than falling back to the nightly book.
    assert monthly_view.anchor_construction("2026-10-23", {}) is None
    assert monthly_view.anchor_construction("2026-10-23", {"n_names": 499}) is None


def test_the_excluded_line_lists_every_name_it_counts() -> None:
    """Seven names were kept out before the sizing, and all seven are listed.

    The block used to slice the list at six, so the line said "7 more" and named
    six: VYLR was counted but never shown. A count line that hides a name it
    counted is a lie about the record, and the reader cannot see which name it is.
    """
    excluded = ["BE", "DD", "ILMN", "P", "SKYD", "TWLO", "VYLR"]
    manifest = {
        "n_names": 203,
        "n_excluded": len(excluded),
        "n_dropped_no_risk": 0,
        "n_dropped": 0,
        "n_kept": 196,
        "excluded_detail": [{"ticker": ticker} for ticker in excluded],
    }
    built = monthly_view.anchor_construction("2026-10-23", manifest)
    assert built is not None
    assert built["excluded"] == 7
    assert built["excluded_names"] == excluded


def test_no_em_or_en_dash_in_page_text_or_block_strings() -> None:
    """A dash that renders as punctuation is still a dash. The test forbids it."""
    root = Path(__file__).resolve().parents[1]
    forbidden = ("\u2014", "\u2013")
    for path in sorted((root / "web" / "src").glob("*.ts*")):
        if ".test." in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        for dash in forbidden:
            assert dash not in text, f"{path.name} carries {dash!r}"
    tree = ast.parse((root / "live" / "monthly_view.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for dash in forbidden:
                assert dash not in node.value, f"monthly_view string carries {dash!r}"
