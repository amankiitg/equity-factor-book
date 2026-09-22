"""The evidence snapshot chain is intact.

`make verify-evidence` runs the same check, but a rebuild that forgets
`make evidence` must fail the test suite too, not only a make target that
a close-out step might skip.
"""

from __future__ import annotations

import pytest

from efb import evidence


@pytest.mark.integration
def test_the_evidence_chain_verifies() -> None:
    problems = evidence.verify()
    assert problems == [], f"evidence chain broken: {problems}"
