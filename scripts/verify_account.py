"""One-time pre-flight: name the EFB paper account and confirm it is its own.

Run once before the first live order:

    set -a && source .env && set +a
    python scripts/verify_account.py

It reads the account once, prints the account **number** (the PA... value Alpaca's
dashboard shows) on a line of its own for the owner to copy into
`EFB_ALPACA_ACCOUNT_ID` on Render and in .env, and prints the internal account id
beside it because the broker's own order records carry that. No key and no secret
is printed, logged or written anywhere.

The number is the point of the exercise. Every run compares the number the broker
reports against `EFB_ALPACA_ACCOUNT_ID` and refuses when they differ or when the
variable is unset, because EFB's keys and the credit lab's are both paper accounts
under one login: a key pasted from the wrong project trades the wrong book, and
every number after that is about somebody else's account. This script prints the
number so the owner never retypes it, and reports the comparison itself, so a typo
is caught here rather than at the flip.
"""

from __future__ import annotations

import json
import os

from live import alpaca


def main() -> int:
    client = alpaca.connect(dry_run=False)
    state = alpaca.verify_account(client)
    print(json.dumps(state, indent=2, sort_keys=True))
    number = str(state.get("account_number") or "")
    if not number:
        print()
        print(
            "the account reported no account_number, so the guard has nothing to "
            "compare: check that the keys belong to an Alpaca account"
        )
        return 1
    print()
    print(f"EFB_ALPACA_ACCOUNT_ID={number}")
    print("  copy that line into the Render cron's environment and into .env")
    print()
    try:
        note = alpaca.check_account_identity(
            number, os.environ.get(alpaca.ACCOUNT_ID_ENV)
        )
    except alpaca.AccountMismatch as exc:
        print(f"IDENTITY: {exc}")
        return 1
    print(f"IDENTITY: {note}")
    return 0 if state["empty"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
