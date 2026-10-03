"""The corporate-actions collection command.

One run per panel rebuild, not one per build: the table it writes is the artifact
the returns build reads, so the same build command produces the same numbers twice.

    python scripts/collect_corporate_actions.py [--root data] [--years 2019-2026]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from efb import corporate_actions  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="data", help="the data root to write into")
    parser.add_argument(
        "--years",
        default=None,
        help="a year or an inclusive year range, e.g. 2019-2026 (the default)",
    )
    args = parser.parse_args()
    years = None
    if args.years:
        if "-" in args.years:
            first, last = args.years.split("-", 1)
            years = tuple(range(int(first), int(last) + 1))
        else:
            years = (int(args.years),)
    root = Path(args.root)
    frame = corporate_actions.collect(root, years=years)
    print(json.dumps(corporate_actions.summary(root), indent=1, sort_keys=True))
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
