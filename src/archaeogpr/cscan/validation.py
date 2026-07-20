"""Validation helpers for user-supplied C-scan request values.

Mirrors ``archaeogpr.geometry.validation``: these check the *shape* of a
value a user is about to enter in the C-scan GUI form before a
``CScanRequest`` is ever constructed, so the form can show an inline error
without attempting a compute. No dataset/time-axis knowledge is required
here — that's :func:`archaeogpr.cscan.compute.compute_cscan`'s job.
"""

from __future__ import annotations

import math

from archaeogpr.cscan.models import CScanAggregation, aggregation_uses_window

__all__ = ["validate_center_time_ns", "validate_window_width_ns"]


def validate_center_time_ns(value: float | None) -> tuple[str, ...]:
    """Rejects ``None`` or a non-finite center time. Negative values are valid."""
    if value is None:
        return ("Center time is required.",)
    if not math.isfinite(value):
        return (f"Center time must be a finite number, got {value!r}.",)
    return ()


def validate_window_width_ns(value: float | None, aggregation: CScanAggregation) -> tuple[str, ...]:
    """Window width rules depend on the aggregation: required+positive for a window
    aggregation, must be absent (``None``) for ``SINGLE_SAMPLE``.
    """
    uses_window = aggregation_uses_window(aggregation)
    if not uses_window:
        if value is not None:
            return ("Window width does not apply to Single Sample (nearest-sample) selection.",)
        return ()
    if value is None:
        return ("Window width is required for this aggregation.",)
    if not math.isfinite(value):
        return (f"Window width must be a finite number, got {value!r}.",)
    if value <= 0:
        return (f"Window width must be greater than zero, got {value!r}.",)
    return ()
