"""Validation helpers for user-supplied geometry override values.

These never touch a :class:`~archaeogpr.model.dataset.GPRDataset` or the raw
``.ogpr`` file -- they only validate the *shape* of a value a user is about
to enter (finite, positive where physically required, a plausible EPSG
identifier) before :mod:`archaeogpr.geometry.resolve` ever sees it. No
network/EPSG-registry lookup is performed (see Sprint 3D-0 scope: EPSG
format + positivity only).
"""

from __future__ import annotations

import math

__all__ = [
    "validate_positive_spacing",
    "validate_finite",
    "validate_epsg_identifier",
]


def validate_positive_spacing(value: float | None, field_label: str) -> tuple[str, ...]:
    """Rejects ``None`` (caller's choice whether that's an error), non-finite, zero, or negative spacing."""
    if value is None:
        return ()
    if not math.isfinite(value):
        return (f"{field_label} must be a finite number, got {value!r}",)
    if value <= 0:
        return (f"{field_label} must be greater than zero, got {value!r}",)
    return ()


def validate_finite(value: float | None, field_label: str) -> tuple[str, ...]:
    """Rejects a non-finite (NaN/inf) value. Unlike spacing, zero and negative are valid here."""
    if value is None:
        return ()
    if not math.isfinite(value):
        return (f"{field_label} must be a finite number, got {value!r}",)
    return ()


def validate_epsg_identifier(value: str | None) -> tuple[str, ...]:
    """Format + positivity check only -- never an EPSG-registry/network lookup (Sprint 3D-0 scope).

    Accepts ``"EPSG:<positive integer>"`` (case-insensitive on the prefix)
    or a bare positive integer string. Anything else is rejected as
    malformed, not merely "unvalidated" -- an empty/whitespace-only string
    is treated as "no identifier supplied" (not an error), matching how
    every other optional override field here treats an unfilled form
    field.
    """
    if value is None:
        return ()
    text = value.strip()
    if not text:
        return ()
    candidate = text
    if ":" in text:
        prefix, _, candidate = text.partition(":")
        if prefix.strip().upper() != "EPSG":
            return (f"CRS identifier must be of the form 'EPSG:<code>', got {value!r}",)
    candidate = candidate.strip()
    if not candidate.isdigit():
        return (f"CRS identifier's numeric code must be a positive integer, got {value!r}",)
    if int(candidate) <= 0:
        return (f"CRS identifier's numeric code must be a positive integer, got {value!r}",)
    return ()
