"""Sprint E11, Task 6: the dry-run execution path records every order.

No credentials, no order leaves the process. The test proves the morning
flow runs end to end in dry run and that every order is recorded with its
intended notional and a zero fill.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from live import morning_job, state


def _write_proposal(proposal_dir: Path, weights: dict[str, float]) -> None:
    proposal_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "ticker": list(weights),
            "weight": [weights[t] for t in weights],
            "side": ["long" if weights[t] >= 0 else "short" for t in weights],
            "z": [0.0] * len(weights),
            "alpha": [0.0] * len(weights),
        }
    )
    frame.to_parquet(proposal_dir / "proposal_2026-09-22.parquet", index=False)


def test_dry_run_flow_records_every_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run writes its day to the test's own tree, not to the repository's.

    `write_positions` and `_write_execution_log` default to `live/state/` and
    `live/logs/`, and this test used to leave both unpinned: every suite run
    rewrote the local execution log and the local positions parquet. Pinning them
    is what the two assertions at the end check, and without the pins the writes
    land back in the repository and the test fails rather than the tree being
    quietly restaged.
    """
    proposal_dir = tmp_path / "proposals"
    state_dir = tmp_path / "state"
    log_dir = tmp_path / "logs"
    _write_proposal(proposal_dir, {"AAA": 0.05, "BBB": -0.05})
    monkeypatch.setattr(morning_job, "PROPOSAL_DIR", proposal_dir)
    monkeypatch.setattr(morning_job, "EXECUTION_LOG_DIR", log_dir)
    # The state writer takes its directory as an argument, and the default is
    # bound when the function is defined, so `state.STATE_DIR` cannot redirect it:
    # the call has to carry the directory. The real writer is saved first, because
    # `morning_job.state` is `live.state` and patching the attribute would
    # otherwise make this wrapper call itself.
    write_positions = state.write_positions
    monkeypatch.setattr(
        morning_job.state,
        "write_positions",
        lambda trade_date, rows: write_positions(trade_date, rows, state_dir=state_dir),
    )

    summary = morning_job.run_morning("2026-09-22", nav=100_000.0)
    assert summary["executed"] is True
    assert summary["dry_run"] is True
    assert summary["orders"] == 2
    assert summary["passed"] == 2
    assert summary["filled_notional"] == 0.0
    assert summary["intended_notional"] == pytest.approx(10_000.0)
    # both writes landed in the test's tree, and the log is the day's own record
    logged = pd.read_parquet(log_dir / "execution_2026-09-22.parquet")
    assert sorted(logged["ticker"]) == ["AAA", "BBB"]
    assert set(logged["status"]) == {"DRY_RUN"}
    held = pd.read_parquet(state_dir / "positions.parquet")
    assert sorted(held["ticker"]) == ["AAA", "BBB"]


def test_morning_flow_skips_on_reject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(morning_job, "PROPOSAL_DIR", tmp_path / "proposals")
    monkeypatch.setattr(morning_job.state, "STATE_DIR", tmp_path / "state")
    summary = morning_job.run_morning("2026-09-22", decision="reject")
    assert summary["executed"] is False
    assert summary["reason"] == "decision=reject"


def test_morning_flow_skips_without_approve_when_auto_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(morning_job, "PROPOSAL_DIR", tmp_path / "proposals")
    monkeypatch.setattr(morning_job.state, "STATE_DIR", tmp_path / "state")
    summary = morning_job.run_morning("2026-09-22", decision=None, auto_approve=False)
    assert summary["executed"] is False


def test_connect_is_none_in_dry_run() -> None:
    assert morning_job.connect(dry_run=True) is None


def test_connect_requires_keys_outside_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EFB_ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("EFB_ALPACA_PAPER_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="paper keys are required"):
        morning_job.connect(dry_run=False)


def test_target_orders_converts_weights_to_notional() -> None:
    proposal = pd.DataFrame({"ticker": ["AAA", "BBB"], "weight": [0.6, -0.4]})
    orders = morning_job.target_orders(proposal, nav=100_000.0)
    by_ticker = {order.ticker: order for order in orders}
    assert by_ticker["AAA"].target_notional == pytest.approx(60_000.0)
    assert by_ticker["BBB"].target_notional == pytest.approx(-40_000.0)
    assert by_ticker["AAA"].traded_notional == pytest.approx(60_000.0)


def test_a_leg_under_the_minimum_is_a_recorded_skip_not_a_silent_drop() -> None:
    """The kept name the floor leaves out is a leg of the day, with a reason.

    A book quietly a few names short of its own target is a book nobody can check,
    so the leg the $250 minimum leaves untraded is returned from the same pass that
    leaves it out: never an order, but always a record, with the size that made it
    too small to send.
    """
    from live import alpaca

    nav = 1_000_000.0
    proposal = pd.DataFrame({"ticker": ["BIG", "SMALL"], "weight": [0.10, 0.0001]})

    orders = morning_job.target_orders(proposal, nav=nav)
    skipped = morning_job.minimum_skips(proposal, nav=nav)

    assert [order.ticker for order in orders] == ["BIG"]
    assert [row["ticker"] for row in skipped] == ["SMALL"]
    leg = skipped[0]
    assert leg["intended_notional"] == pytest.approx(100.0)
    assert leg["status"] == alpaca.SKIPPED
    assert leg["reason_code"] == alpaca.REASON_BELOW_MIN_NOTIONAL
    assert "under the $250 minimum" in str(leg["reason"])
    # every name in the union is either an order or a recorded skip
    assert len(orders) + len(skipped) == 2


def test_a_name_already_at_its_target_is_not_a_skipped_leg() -> None:
    """A zero change is not a leg the floor refused, and a rerun has one per name.

    On a rerun of an unchanged book every delta is zero. Recording those as
    skipped legs would fill the day with names that had nothing to do, and the
    message would name a dozen of them every evening the book stood still.
    """
    nav = 1_000_000.0
    proposal = pd.DataFrame({"ticker": ["AAA", "BBB"], "weight": [0.10, -0.05]})
    held = {"AAA": 100_000.0, "BBB": -50_000.0}

    orders = morning_job.target_orders(proposal, nav=nav, current=held)
    skipped = morning_job.minimum_skips(proposal, nav=nav, current=held)

    assert orders == [] and skipped == []
    # the negative control: a change the floor really refused, on the same book
    moved = morning_job.minimum_skips(
        proposal, nav=nav, current={"AAA": 100_000.0, "BBB": -50_100.0}
    )
    assert [row["ticker"] for row in moved] == ["BBB"]


def test_a_close_under_the_minimum_is_still_sent() -> None:
    """The floor never leaves a leftover holding behind.

    A held name absent from tonight's target is a close, and a close is emitted
    whatever its size: a $40 remainder that could not be sold would sit in the
    account forever, and every later evening would measure against it.
    """
    proposal = pd.DataFrame({"ticker": ["BIG"], "weight": [0.10]})
    nav = 1_000_000.0

    orders = morning_job.target_orders(proposal, nav=nav, current={"LEFTOVER": 40.0})
    skipped = morning_job.minimum_skips(proposal, nav=nav, current={"LEFTOVER": 40.0})

    assert "LEFTOVER" in [order.ticker for order in orders]
    assert skipped == []


def test_an_expected_skip_does_not_make_the_run_incomplete() -> None:
    """The two skips differ: one is the book not moving, one is a leg not taken.

    `SKIPPED` on its own means the run could not do what it intended, which is why
    the status is in the incomplete set. A leg the minimum left untraded is the
    evening doing exactly what it should, so it must not make the day unfiled; any
    other skip on the same records still does.
    """
    from live import alpaca

    frame = pd.DataFrame(
        {
            "ticker": ["SMALL", "AAA"],
            "status": [alpaca.SKIPPED, "ACCEPTED"],
            "reason_code": [alpaca.REASON_BELOW_MIN_NOTIONAL, ""],
        }
    )

    assert morning_job.incomplete_legs(frame) == []

    # the negative control: the same skip status carrying any other code is a leg
    # the run failed to place
    refused = frame.copy()
    refused.loc[0, "reason_code"] = alpaca.REASON_NOT_SHORTABLE
    assert [leg["ticker"] for leg in morning_job.incomplete_legs(refused)] == ["SMALL"]


class _FakeAccount:
    def __init__(self, equity: float | None, raise_on_read: bool = False) -> None:
        self._equity = equity
        self._raise = raise_on_read

    @property
    def equity(self) -> float:
        if self._raise:
            raise ConnectionError("account read failed")
        return float(self._equity)


class _FakeClient:
    def __init__(
        self, equity: float | None = 1_000_000.0, raise_on_read: bool = False
    ) -> None:
        self._account = _FakeAccount(equity, raise_on_read)

    def get_account(self) -> _FakeAccount:
        return self._account


def test_get_nav_returns_the_live_equity() -> None:
    from live import alpaca

    assert alpaca.get_nav(_FakeClient(equity=1_234_567.89)) == pytest.approx(
        1_234_567.89
    )


def test_get_nav_has_no_fallback_it_raises_on_a_failed_read() -> None:
    from live import alpaca

    with pytest.raises(ConnectionError, match="account read failed"):
        alpaca.get_nav(_FakeClient(raise_on_read=True))


def test_get_nav_raises_on_a_non_positive_equity() -> None:
    from live import alpaca

    with pytest.raises(RuntimeError, match="invalid live account equity"):
        alpaca.get_nav(_FakeClient(equity=0.0))
    with pytest.raises(RuntimeError, match="invalid live account equity"):
        alpaca.get_nav(_FakeClient(equity=-5.0))
