"""Helpers for turning a specific database `IntegrityError` into the right
domain error — and, crucially, for *not* swallowing an unrelated one.

A blanket `except IntegrityError: raise SomeDomainConflict` reports every
constraint failure (a missing NOT NULL, an unrelated FK, a different unique
index) as that one business conflict. `violated_constraint()` lets a caller
check which constraint actually failed and re-raise anything it didn't expect.
"""

from sqlalchemy.exc import IntegrityError


def violated_constraint(exc: IntegrityError) -> str | None:
    """The name of the constraint/index the failed statement violated, if the
    driver exposes it (psycopg does via `Diagnostics.constraint_name`)."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    return getattr(diag, "constraint_name", None) or None
