"""The live loop's entry points and one-off commands.

Present so that `scripts.run_live_daily` is one module rather than two: the tests
and `scripts/push_seed.py` import these by the package path, while mypy maps a
directory without this file as a set of top-level modules and then reports the
same source file under two names.
"""
