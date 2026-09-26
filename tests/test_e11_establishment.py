"""Sprint E11 pre-flip, item 3: the establishment day.

The first trading day creates the book from flat, so it is a different kind of
evening from every evening after it. It is flagged, it may trade up to the full
book rather than being held to the rebalance brake, and its cost is the
establishment cost the proposal already carries and names as such.

The traded leg of every order is measured against the book the account actually
holds, which is what makes the distinction real: from flat the whole target
trades, and from an existing book only the difference does. The source of that
book is named in the message, because in dry run the store's book is the loop's
intention rather than the broker's holding.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from live import guards, morning_job, notify, store

NAV = 1_000_000.0


def _book_of(n_long: int = 10, n_short: int = 10, weight: float = 0.05) -> pd.DataFrame:
    """A gross-1.0 book whose names are all inside the position cap."""
    tickers = [f"L{i:03d}" for i in range(n_long)] + [
        f"S{i:03d}" for i in range(n_short)
    ]
    weights = [weight] * n_long + [-weight] * n_short
    return pd.DataFrame({"ticker": tickers, "weight": weights})


def _orders(proposal: pd.DataFrame) -> list[guards.OrderSpec]:
    return [
        guards.OrderSpec(
            ticker=str(row.ticker),
            target_notional=float(row.weight) * NAV,
            traded_notional=abs(float(row.weight)) * NAV,
        )
        for row in proposal.itertuples(index=False)
    ]


def test_the_establishment_day_is_held_to_the_book_not_the_brake() -> None:
    """Two limits, two bases, and the flag chooses between them."""
    limit, basis = guards.traded_notional_limit(NAV, establishment=True)
    assert limit == NAV
    assert "full book" in basis and "second trading day" in basis

    limit, basis = guards.traded_notional_limit(NAV, establishment=False)
    assert limit == guards.MAX_TRADED_NOTIONAL_PER_RUN
    assert "daily brake" in basis


def test_a_full_book_establishes_and_a_normal_brake_would_not() -> None:
    """The negative control: the same orders under a 500k brake are rejected."""
    orders = _orders(_book_of())
    assert abs(sum(order.traded_notional for order in orders) - NAV) < 1e-6

    established = guards.apply_guards(orders, NAV, establishment=True)
    assert all(order.status == guards.PASSED for order in established)

    # Held to a 500,000 brake the same book cannot be built: the run stops
    # partway, which is exactly what the establishment day is exempt from.
    rebalanced = guards.apply_guards(
        orders, NAV, max_traded=500_000.0, establishment=False
    )
    assert any(order.status == guards.REJECTED_TRADED_NOTIONAL for order in rebalanced)


def test_the_establishment_ceiling_still_trips_on_ten_times_the_book() -> None:
    """A guard that cannot fire is not a guard: the ceiling is a real bound."""
    orders = _orders(_book_of(n_long=100, n_short=100, weight=0.05))
    assert sum(order.traded_notional for order in orders) == 10 * NAV
    guarded = guards.apply_guards(orders, NAV, establishment=True)
    tripped = [o for o in guarded if o.status == guards.REJECTED_TRADED_NOTIONAL]
    assert tripped, "a book ten times the ceiling was not stopped"


def _proposal_frame(proposal: pd.DataFrame) -> pd.DataFrame:
    frame = proposal.copy()
    frame["alpha"] = 0.0
    return frame


@pytest.fixture
def _no_state_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(morning_job.state, "write_positions", lambda *a, **k: None)
    monkeypatch.setattr(morning_job, "_write_execution_log", lambda *a, **k: None)
    monkeypatch.setattr(morning_job, "_close_prices", lambda *a, **k: {})


def test_from_flat_the_whole_book_trades_and_the_day_is_establishment(
    monkeypatch: pytest.MonkeyPatch, _no_state_writes: None
) -> None:
    proposal = _proposal_frame(_book_of())
    monkeypatch.setattr(morning_job, "load_proposal", lambda *a, **k: proposal)

    summary = morning_job.run_morning("2026-09-25", nav=NAV, dry_run=True)

    assert summary["establishment"] is True
    assert summary["cost_label"] == "establishment"
    assert summary["n_held"] == 0
    # From flat every leg is the whole target, so the run trades the book.
    assert abs(summary["traded_notional"] - NAV) < 1e-6
    assert abs(summary["intended_notional"] - NAV) < 1e-6


def test_holding_the_book_makes_the_next_day_a_rebalance_that_trades_nothing(
    monkeypatch: pytest.MonkeyPatch, _no_state_writes: None
) -> None:
    """The negative control for the flag: a held book is not an establishment."""
    proposal = _proposal_frame(_book_of())
    monkeypatch.setattr(morning_job, "load_proposal", lambda *a, **k: proposal)
    held = {
        str(row.ticker): float(row.weight) * NAV
        for row in proposal.itertuples(index=False)
    }

    summary = morning_job.run_morning(
        "2026-09-25", nav=NAV, dry_run=True, positions=held, establishment=False
    )

    assert summary["establishment"] is False
    assert summary["cost_label"] == "rebalance"
    assert summary["n_held"] == len(held)
    # Already holding the targets, a rebalance trades nothing at all: the target
    # notional is unchanged, so the traded leg is zero and the brake is never
    # reached. This is the difference the flag exists to make.
    assert summary["traded_notional"] == 0.0


def test_the_message_says_the_day_and_labels_the_cost() -> None:
    establishment = notify.compose(
        status="ok",
        target_close="2026-09-25",
        orders=20,
        gross=NAV,
        dry_run=True,
        establishment=True,
        cost_label="establishment",
        cost_bps=53.73,
        brake_limit=NAV,
        store="postgres/efb",
    )
    assert "Establishment: the first trading day" in establishment
    assert "may trade up to the full book ($1,000,000 of gross)" in establishment
    assert "the daily brake starts on the second trading day" in establishment
    assert "Cost: establishment, 53.73 bps of NAV." in establishment

    rebalance = notify.compose(
        status="ok",
        target_close="2026-09-28",
        orders=20,
        gross=120_000.0,
        dry_run=True,
        establishment=False,
        cost_label="rebalance",
        cost_bps=12.1,
        brake_limit=guards.MAX_TRADED_NOTIONAL_PER_RUN,
        store="postgres/efb",
    )
    assert "Establishment:" not in rebalance
    assert (
        "Day: rebalance. The absolute traded-notional brake of $2,000,000 " in rebalance
    )
    assert "Cost: rebalance, 12.10 bps of NAV." in rebalance


def test_the_held_book_is_read_from_the_store_with_its_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from live import positions

    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    held, source = positions.store_positions()
    assert held == {}
    assert "no position row" in source

    store.upsert(
        "positions",
        [
            {"trade_date": "2026-09-24", "ticker": "AAA", "signed_notional": 1.0},
            {"trade_date": "2026-09-25", "ticker": "AAA", "signed_notional": 500.0},
            {"trade_date": "2026-09-25", "ticker": "BBB", "signed_notional": -250.0},
        ],
    )
    held, source = positions.store_positions()
    assert held == {"AAA": 500.0, "BBB": -250.0}
    assert "2026-09-25" in source
