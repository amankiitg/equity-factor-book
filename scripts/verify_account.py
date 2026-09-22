"""One-time pre-flight: confirm the EFB paper account is empty and distinct.

Run once before the first live order:
    source .env
    python scripts/verify_account.py

Prints the account id and the position count, never any key or secret.
The operator compares the printed account id against the
credit-trading-lab account id shown in that project's dashboard; they
differ because EFB uses a separate paper account with its own keys.
"""

from __future__ import annotations

import json

from live import alpaca


def main() -> int:
    client = alpaca.connect(dry_run=False)
    state = alpaca.verify_account(client)
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0 if state["empty"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
