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
from typing import Any

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
    # The stable code for a leg that never became a submitted order. Alpaca does
    # not persist a submit-time rejection, so this column is the durable record
    # that the leg was intended at all.
    "reason_code",
    # The id the leg was sent with: deterministic from the close, the ticker and
    # the side, so a rerun is refused by the broker rather than doubling the book.
    "client_order_id",
]


def should_execute(decision: str | None, auto_approve: bool) -> bool:
    """The Option A gate: reject always vetoes; approve always runs;
    otherwise execution needs auto-approve on."""
    if decision == "reject":
        return False
    if not auto_approve and decision != "approve":
        return False
    return True


def load_proposal(as_of: str, data_root: Path | None = None) -> pd.DataFrame:
    """The evening proposal for a trade date, weights gross-normalized."""
    path = PROPOSAL_DIR / f"proposal_{as_of}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"no proposal for {as_of} at {path}")
    return pd.read_parquet(path)


def _close_prices(as_of: str, data_root: Path | None = None) -> dict[str, float]:
    """{ticker: close} at the proposal close, for short-share quantization."""
    root = Path(data_root) if data_root is not None else DATA_ROOT
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
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
    close: str | None = None,
) -> pd.DataFrame:
    """Submit guarded orders and record one row per order, filled or not.

    Dry run records every order with zero fill and status DRY_RUN. The live path
    submits market orders through live.alpaca and records the fills, so no order
    is dropped without a record. Every row carries a `reason_code`: the guard's
    own status for a leg a guard rejected, the broker's classification for a leg
    the broker refused, and the run's own halt code for a leg never attempted.
    """
    records: list[dict[str, object]] = []
    from live import alpaca

    for order in orders:
        if order.status != guards.PASSED:
            records.append(
                {
                    "ticker": order.ticker,
                    "intended_notional": order.target_notional,
                    "filled_notional": 0.0,
                    "status": order.status,
                    "reason": "guard rejected the order",
                    "reason_code": order.status,
                    "client_order_id": "",
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
                    "reason_code": "DRY_RUN",
                    # The id the leg would have carried, computed the same way the
                    # live path computes it, so a dry evening shows the rerun-proof
                    # ticket the live evening will send.
                    "client_order_id": (
                        alpaca.client_order_id(
                            close,
                            order.ticker,
                            "buy" if order.target_notional >= 0 else "sell",
                        )
                        if close
                        else ""
                    ),
                }
            )
            continue
        if client is None:  # pragma: no cover - guarded by connect()
            raise RuntimeError("live submission needs a client")
    if not dry_run and client is not None:
        fills = alpaca.submit_market_orders(orders, client, prices or {}, close=close)
        for fill in fills:
            records.append(
                {
                    "ticker": fill.ticker,
                    "intended_notional": fill.intended_notional,
                    "filled_notional": fill.filled_notional,
                    "status": fill.status,
                    "reason": fill.detail or "live paper fill",
                    "reason_code": fill.reason_code,
                    "client_order_id": fill.client_order_id,
                }
            )
    return pd.DataFrame(records, columns=EXECUTION_COLUMNS[1:])


def run_morning(
    as_of: str,
    nav: float = PAPER_NAV_DEFAULT,
    decision: str | None = None,
    auto_approve: bool = True,
    dry_run: bool = DRY_RUN_DEFAULT,
    data_root: Path | None = None,
    positions: dict[str, float] | None = None,
    establishment: bool | None = None,
) -> dict[str, Any]:
    """The whole morning flow: gate, propose, guard, submit, reconcile.

    Returns the summary with the decision, the guard outcomes and the
    fill-vs-intent reconciliation.

    `positions` is the book the account actually holds, in signed notional, and
    `establishment` says whether this run creates the book or rebalances it.
    Every traded leg is measured against `positions`, so a rebalance trades the
    difference instead of the whole book; when the account holds nothing the two
    are the same thing and the run is an establishment run, which the caller
    names explicitly or leaves to be inferred from the empty book. The day's cost
    is labelled from the same flag, because the proposal's cost is the cost of
    building the book from flat and calling a rebalance that would be wrong.
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
    held = {str(key): float(value) for key, value in (positions or {}).items()}
    is_establishment = (not held) if establishment is None else bool(establishment)
    proposal = load_proposal(as_of, data_root)
    client = connect(dry_run)
    if not dry_run:
        # The live NAV anchors every guard. A failed read raises, so the run
        # fails before any order is built or submitted: no fallback NAV.
        from live import alpaca

        nav = alpaca.get_nav(client)
    # From flat, the traded leg is the whole target; from a book, it is the
    # difference. An establishment run is by definition the former.
    orders = target_orders(proposal, nav, None if is_establishment else held)
    brake_limit, brake_basis = guards.traded_notional_limit(
        nav, establishment=is_establishment
    )
    guarded = guards.apply_guards(orders, nav, establishment=is_establishment)
    prices = _close_prices(as_of, data_root)
    if not dry_run and client is not None:
        # Enough buying power for the whole run, checked before the first order.
        # Alpaca checks leg by leg and reduces available buying power by every open
        # order, so a book that does not fit ends half-built; a failure here raises
        # and nothing is submitted.
        from live import alpaca as alpaca_module

        alpaca_module.check_buying_power(
            client, [order for order in guarded if order.status == guards.PASSED]
        )
    records = submit_orders(guarded, client, dry_run, prices, close=as_of)
    records["trade_date"] = as_of
    positions_frame = _positions_from_records(records, proposal)
    state.write_positions(as_of, positions_frame.to_dict("records"))
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
        # The dollars this run would actually move: the brake's own basis, and
        # the number that separates an establishment (the whole book) from a
        # rebalance that already holds it (nothing, when the target is unchanged).
        "traded_notional": float(
            sum(
                order.traded_notional
                for order in guarded
                if order.status == guards.PASSED
            )
        ),
        # The legs the broker refused or the run never attempted, by code. A
        # refused short is a decision the book made, not an error: it is reported
        # with the code that says why rather than being dropped in silence.
        "skipped": int((records["status"] == "SKIPPED").sum()),
        "reason_codes": _reason_code_counts(records),
        # The day's kind, the limit it was held to, and why: the three things the
        # owner needs to read a first evening's order list correctly.
        "establishment": is_establishment,
        "brake_limit": brake_limit,
        "brake_basis": brake_basis,
        "cost_label": "establishment" if is_establishment else "rebalance",
        "n_held": len(held),
        "held_notional": float(sum(abs(value) for value in held.values())),
    }


def _reason_code_counts(records: pd.DataFrame) -> dict[str, int]:
    """How many legs carry each reason code, refusals only.

    Submitted legs have no code and dry-run legs carry DRY_RUN, so neither is a
    refusal; both are excluded, which is what makes the count readable as "what
    was refused tonight".
    """
    codes = records.get("reason_code")
    if codes is None:
        return {}
    counts = codes[(codes != "") & (codes != "DRY_RUN")].value_counts()
    return {str(code): int(count) for code, count in counts.items()}


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
