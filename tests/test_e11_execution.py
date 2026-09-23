"""Sprint E11, Task 6: the dry-run execution path records every order.

No credentials, no order leaves the process. The test proves the morning
flow runs end to end in dry run and that every order is recorded with its
intended notional and a zero fill.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from live import morning_job


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
    proposal_dir = tmp_path / "proposals"
    state_dir = tmp_path / "state"
    _write_proposal(proposal_dir, {"AAA": 0.05, "BBB": -0.05})
    monkeypatch.setattr(morning_job, "PROPOSAL_DIR", proposal_dir)
    monkeypatch.setattr(morning_job.state, "STATE_DIR", state_dir)

    summary = morning_job.run_morning("2026-09-22", nav=100_000.0)
    assert summary["executed"] is True
    assert summary["dry_run"] is True
    assert summary["orders"] == 2
    assert summary["passed"] == 2
    assert summary["filled_notional"] == 0.0
    assert summary["intended_notional"] == pytest.approx(10_000.0)


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
