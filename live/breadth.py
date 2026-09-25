"""The book's effective breadth, and the full book's, with no unqualified `n_eff`.

E11's artifacts carried one `n_eff` field, and it was the **full 499-name book's**
number before the floor was enforced: at the 2026-09-21 close, 157.33 beside a
book whose own breadth is 70.59. On a page the owner watches, a number named
`n_eff` is read as the breadth of the book that trades, so the field meant more
than it said. The stored names are now:

- `n_eff_kept`: the book that trades, after the floor and the renormalization to
  gross 1.0. This is what a page means by "breadth".
- `n_eff_full_book`: the full universe book before the floor. Reported beside it
  and never as the book's.

Older artifacts still carry the unqualified `n_eff`. `full_book_breadth` reads it
as the full book's number, with `LEGACY_NOTE` available for the page to show, and
**nothing in this module ever maps a legacy `n_eff` to the book's breadth.**
"""

from __future__ import annotations

from typing import Any

BOOK_LABEL = "the book's effective breadth"
FULL_BOOK_LABEL = "the full 499-name book's, before the floor"
LEGACY_NOTE = (
    "this artifact predates the split and its n_eff is the full book's number, "
    "so it is shown as the full book's and not as the book's"
)


def book_breadth(record: dict[str, Any] | None) -> float | None:
    """The breadth of the book that trades, or None when the artifact predates it."""
    if not record:
        return None
    value = record.get("n_eff_kept")
    return None if value is None else float(value)


def full_book_breadth(record: dict[str, Any] | None) -> float | None:
    """The full universe book's breadth, reading a legacy `n_eff` as that."""
    if not record:
        return None
    value = record.get("n_eff_full_book")
    if value is None:
        value = record.get("n_eff")
    return None if value is None else float(value)


def legacy_artifact(record: dict[str, Any] | None) -> bool:
    """Whether the artifact's breadth has to be read through the legacy name."""
    if not record:
        return False
    return record.get("n_eff_full_book") is None and record.get("n_eff") is not None


def breadths(record: dict[str, Any] | None) -> dict[str, Any]:
    """Both numbers and the labels, ready for a page or a snapshot."""
    return {
        "book": book_breadth(record),
        "full_book": full_book_breadth(record),
        "book_label": BOOK_LABEL,
        "full_book_label": FULL_BOOK_LABEL,
        "legacy": legacy_artifact(record),
        "note": LEGACY_NOTE if legacy_artifact(record) else "",
    }
