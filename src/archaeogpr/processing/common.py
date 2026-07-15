"""Shared helpers for archaeogpr.processing modules.

Nothing here mutates a GPRDataset or its arrays; these are pure utilities
used by both ``time_zero.py`` and ``dc_offset.py`` to convert nanosecond
windows to sample indices and to build consistent ``processing_history``
records.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np

from archaeogpr import __version__ as ARCHAEOGPR_VERSION

#: Required by the Sprint 2 task brief: every time-zero diagnostic/report must
#: carry this exact distinction between a signal-processing pick and an
#: independently calibrated physical surface time.
TIME_ZERO_REFERENCE_WARNING = (
    "Automatic time-zero picks are signal-processing references and are not "
    "independently calibrated physical surface times."
)


class ProcessingError(ValueError):
    """Raised when processing parameters or inputs are invalid."""


def ns_window_to_samples(
    sampling_time_ns: float,
    samples_count: int,
    start_ns: float | None,
    end_ns: float | None,
) -> tuple[int, int]:
    """Convert an optional ``[start_ns, end_ns)`` window to safe sample indices.

    ``start_ns``/``end_ns`` both ``None`` means "the full trace"
    (``(0, samples_count)``). Giving only one of the two is an error.
    Returns ``(start_sample, end_sample)`` with
    ``0 <= start_sample < end_sample <= samples_count``. Raises
    ``ProcessingError`` for a missing half, an inverted/empty ns range, or a
    range that maps to an empty (or fully out-of-bounds) sample window.
    """
    if start_ns is None and end_ns is None:
        return 0, samples_count
    if start_ns is None or end_ns is None:
        raise ProcessingError("start_ns and end_ns must both be given, or both omitted")
    if end_ns <= start_ns:
        raise ProcessingError(f"end_ns ({end_ns}) must be greater than start_ns ({start_ns})")
    if sampling_time_ns <= 0:
        raise ProcessingError(f"sampling_time_ns must be positive, got {sampling_time_ns}")

    start_sample = int(round(start_ns / sampling_time_ns))
    end_sample = int(round(end_ns / sampling_time_ns))
    clamped_start = max(0, min(start_sample, samples_count))
    clamped_end = max(0, min(end_sample, samples_count))
    if clamped_end <= clamped_start:
        raise ProcessingError(
            f"window [{start_ns}, {end_ns}) ns maps to an empty sample range "
            f"[{clamped_start}, {clamped_end}) for samples_count={samples_count}, "
            f"sampling_time_ns={sampling_time_ns}"
        )
    return clamped_start, clamped_end


def validate_target_sample(target_sample: int, samples_count: int) -> None:
    """Raise ``ProcessingError`` if ``target_sample`` is not a valid sample index."""
    if not isinstance(target_sample, int) or isinstance(target_sample, bool):
        raise ProcessingError(f"target_sample must be an int, got {type(target_sample).__name__}")
    if not (0 <= target_sample < samples_count):
        raise ProcessingError(f"target_sample={target_sample} out of range [0, {samples_count})")


def time_zero_relative_time_ns(samples_count: int, target_sample: int, sampling_time_ns: float) -> np.ndarray:
    """Corrected time axis: ``(arange(samples_count) - target_sample) * sampling_time_ns``.

    By construction ``result[target_sample] == 0.0`` exactly (up to float
    rounding), samples before ``target_sample`` are negative, samples after
    are positive, and the sample interval is unchanged. This is a
    signal-processing reference frame (see ``TIME_ZERO_REFERENCE_WARNING``),
    never an independently calibrated physical surface time.
    """
    return (np.arange(samples_count, dtype=np.float64) - target_sample) * sampling_time_ns


def dataset_time_window_mask(time_ns: np.ndarray, start_ns: float, end_ns: float) -> np.ndarray:
    """Boolean mask (shape ``(samples,)``) where ``start_ns <= time_ns < end_ns``.

    Works on whatever ``time_ns`` actually is — an unshifted absolute axis
    or a time-zero-relative one (which may start negative) — rather than
    assuming sample 0 corresponds to 0 ns. Raises ``ProcessingError`` if the
    window selects zero samples (e.g. it falls entirely outside the
    dataset's actual time range) or if ``end_ns <= start_ns``.
    """
    if end_ns <= start_ns:
        raise ProcessingError(f"end_ns ({end_ns}) must be greater than start_ns ({start_ns})")
    mask = (time_ns >= start_ns) & (time_ns < end_ns)
    if not mask.any():
        raise ProcessingError(
            f"window [{start_ns}, {end_ns}) ns selects zero samples from this dataset's time_ns "
            f"range [{float(time_ns.min())}, {float(time_ns.max())}] ns"
        )
    return mask


def contiguous_true_runs(mask_1d: np.ndarray) -> list[tuple[int, int]]:
    """Return ``[(start, end), ...]`` half-open index ranges of contiguous ``True`` runs.

    Shared by ``dewow.py`` and ``bandpass.py``: both process each
    contiguous run of valid (non-padding) samples independently, since a
    moving window or filter must never reach across a padding gap.
    """
    if not mask_1d.any():
        return []
    padded = np.concatenate(([False], mask_1d, [False]))
    edges = np.flatnonzero(np.diff(padded.astype(np.int8)))
    return [(int(edges[i]), int(edges[i + 1])) for i in range(0, len(edges), 2)]


def padding_mask(shift: int, samples_count: int) -> np.ndarray:
    """Boolean mask marking samples introduced by an ``np.roll(..., shift)`` shift.

    Single source of truth for "which samples are fill, not real shifted-in
    data" — used both by ``time_zero.py`` (to fill and to count padding) and
    by ``qc/time_zero.py`` (to shade padded regions in QC plots).
    """
    mask = np.zeros(samples_count, dtype=bool)
    if shift > 0:
        mask[: min(shift, samples_count)] = True
    elif shift < 0:
        mask[max(samples_count + shift, 0) :] = True
    return mask


def build_processing_record(
    operation: str,
    *,
    parameters: dict[str, Any],
    diagnostics: dict[str, Any],
    warnings: tuple[str, ...],
) -> dict[str, Any]:
    """Build a standard ``processing_history`` entry: what ran, with what, and any caveats."""
    return {
        "operation": operation,
        "archaeogpr_version": ARCHAEOGPR_VERSION,
        "applied_at": datetime.now(UTC).isoformat(),
        "parameters": parameters,
        "diagnostics": diagnostics,
        "warnings": list(warnings),
    }
