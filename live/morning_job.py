"""Sprint E11: the morning execution job.

Submit the evening proposal to Alpaca paper under Option A governance and
the two fail-safe guards, then reconcile fills against targets. Dry run by
default: no credentials are read and no order leaves the process, but the
whole state machine advances and every order is recorded.

Option A governance, ported from v8.x: the loop proposes, the rules
decide, nothing discretionary. Execution runs only when the dated decision
is `approve`, or when auto-approve is on and the decision is not `reject`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from live import guards, state
from live.guards import OrderSpec

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
PROPOSAL_DIR = ROOT / "live" / "proposals"
EXECUTION_LOG_DIR = ROOT / "live" / "logs"

PAPER_NAV_DEFAULT = 1_000_000.0
DRY_RUN_DEFAULT = True

EXECUTION_COLUMNS = [
    "trade_date",
    "ticker",
    "intended_notional",
    "filled_notional",
    "status",
    "reason",
]


def should_execute(decision: str | None, auto_approve: bool) -> bool:
    """The Option A gate: reject always vetoes; approve always runs;
    otherwise execution needs auto-approve on."""
    if decision == "reject":
        return False
    if not auto_approve and decision != "approve":
        return False
    return True


def load_proposal(as_of: str, data_root: Path = DATA_ROOT) -> pd.DataFrame:
    """The evening proposal for a trade date, weights gross-normalized."""
    path = PROPOSAL_DIR / f"proposal_{as_of}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"no proposal for {as_of} at {path}")
    return pd.read_parquet(path)


def _close_prices(as_of: str, data_root: Path = DATA_ROOT) -> dict[str, float]:
    """{ticker: close} at the proposal close, for short-share quantization."""
    prices = pd.read_parquet(data_root / "raw" / "prices.parquet")
    day = prices[prices.index.get_level_values("date") == pd.Timestamp(as_of)]
    close = day["close"].droplevel("date") if not day.empty else pd.Series(dtype=float)
    return {str(ticker): float(value) for ticker, value in close.items()}


def target_orders(
    proposal: pd.DataFrame,
    nav: float,
    current: dict[str, float] | None = None,
) -> list[OrderSpec]:
    """Weights to OrderSpecs: signed target notional and the traded leg."""
    held = current or {}
    orders: list[OrderSpec] = []
    for row in proposal.itertuples(index=False):
        target = float(row.weight) * nav
        traded = abs(target - held.get(row.ticker, 0.0))
        orders.append(OrderSpec(row.ticker, target, traded))
    return orders


def connect(dry_run: bool = True) -> object | None:
    """The Alpaca paper client, or None in dry run.

    Delegates to live.alpaca, which reads paper keys from the environment
    (`EFB_ALPACA_PAPER_API_KEY`, `EFB_ALPACA_PAPER_SECRET_KEY`), never
    from a file and never from the repo. The names are distinct from
    credit-trading-lab's so a stale shell cannot cross the two books.
    """
    from live import alpaca

    return alpaca.connect(dry_run)


def submit_orders(
    orders: list[OrderSpec],
    client: object | None,
    dry_run: bool,
    prices: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Submit guarded orders and record one row per order, filled or not.

    Dry run records every order with zero fill and status DRY_RUN. The
    live path submits market orders through live.alpaca and records the
    fills, so no order is dropped without a record.
    """
    records: list[dict[str, object]] = []
    for order in orders:
        if order.status != guards.PASSED:
            records.append(
                {
                    "ticker": order.ticker,
                    "intended_notional": order.target_notional,
                    "filled_notional": 0.0,
                    "status": order.status,
                    "reason": "guard rejected the order",
                }
            )
            continue
        if dry_run:
            records.append(
                {
                    "ticker": order.ticker,
                    "intended_notional": order.target_notional,
                    "filled_notional": 0.0,
                    "status": "DRY_RUN",
                    "reason": "dry run: no order sent",
                }
            )
            continue
        if client is None:  # pragma: no cover - guarded by connect()
            raise RuntimeError("live submission needs a client")
    if not dry_run and client is not None:
        from live import alpaca

        fills = alpaca.submit_market_orders(orders, client, prices or {})
        for fill in fills:
            records.append(
                {
                    "ticker": fill.ticker,
                    "intended_notional": fill.intended_notional,
                    "filled_notional": fill.filled_notional,
                    "status": fill.status,
                    "reason": "live paper fill",
                }
            )
    return pd.DataFrame(records, columns=EXECUTION_COLUMNS[1:])


def run_morning(
    as_of: str,
    nav: float = PAPER_NAV_DEFAULT,
    decision: str | None = None,
    auto_approve: bool = True,
    dry_run: bool = DRY_RUN_DEFAULT,
    data_root: Path = DATA_ROOT,
) -> dict[str, object]:
    """The whole morning flow: gate, propose, guard, submit, reconcile.

    Returns the summary with the decision, the guard outcomes and the
    fill-vs-intent reconciliation.
    """
    if not should_execute(decision, auto_approve):
        return {
            "as_of": as_of,
            "executed": False,
            "reason": (
                "decision=reject"
                if decision == "reject"
                else "auto_approve off and no approve"
            ),
            "orders": 0,
        }
    proposal = load_proposal(as_of, data_root)
    client = connect(dry_run)
    if not dry_run:
        # The live NAV anchors every guard. A failed read raises, so the run
        # fails before any order is built or submitted: no fallback NAV.
        from live import alpaca

        nav = alpaca.get_nav(client)
    orders = target_orders(proposal, nav)
    guarded = guards.apply_guards(orders, nav)
    prices = _close_prices(as_of, data_root)
    records = submit_orders(guarded, client, dry_run, prices)
    records["trade_date"] = as_of
    positions = _positions_from_records(records, proposal)
    state.write_positions(as_of, positions.to_dict("records"))
    _write_execution_log(as_of, records)
    return {
        "as_of": as_of,
        "executed": True,
        "dry_run": dry_run,
        "orders": int(len(orders)),
        "passed": int((records["status"] == guards.PASSED).sum())
        + int((records["status"] == "DRY_RUN").sum()),
        "rejected_cap": int((records["status"] == guards.REJECTED_CAP).sum()),
        "rejected_brake": int(
            (records["status"] == guards.REJECTED_TRADED_NOTIONAL).sum()
        ),
        "intended_notional": float(records["intended_notional"].abs().sum()),
        "filled_notional": float(records["filled_notional"].abs().sum()),
    }


def _positions_from_records(
    records: pd.DataFrame, proposal: pd.DataFrame
) -> pd.DataFrame:
    """The positions the loop records: intended targets, dry-run labeled.

    In dry run nothing is filled, so the book the loop intends to hold is
    stored as the position state and the fill gap is the reconciliation.
    """
    weights = proposal.set_index("ticker")["weight"]
    rows: list[dict[str, object]] = []
    for record in records.itertuples(index=False):
        weight = float(weights.get(record.ticker, 0.0))
        rows.append(
            {
                "ticker": record.ticker,
                "signed_notional": record.intended_notional,
                "weight": weight,
                "side": "long" if weight >= 0 else "short",
            }
        )
    return pd.DataFrame(rows)


def _write_execution_log(as_of: str, records: pd.DataFrame) -> None:
    EXECUTION_LOG_DIR.mkdir(parents=True, exist_ok=True)
    records.to_parquet(EXECUTION_LOG_DIR / f"execution_{as_of}.parquet", index=False)


def main() -> int:
    """The cron entrypoint: run the morning flow for the latest proposal."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--decision", default=None)
    parser.add_argument("--auto-approve", action="store_true", default=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    as_of = args.as_of
    if as_of is None:
        proposals = sorted(PROPOSAL_DIR.glob("proposal_*.parquet"))
        if not proposals:
            raise SystemExit("no proposals to execute")
        as_of = proposals[-1].stem.replace("proposal_", "")
    summary = run_morning(
        as_of,
        decision=args.decision,
        auto_approve=args.auto_approve,
        dry_run=not args.live,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
