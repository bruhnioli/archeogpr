"""Generic result model for archaeogpr.processing operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from archaeogpr.model._frozen import freeze_array, freeze_metadata
from archaeogpr.model.dataset import GPRDataset


class ProcessingResultError(ValueError):
    """Raised when a ProcessingResult's arrays/diagnostics violate its invariants."""


def _freeze_array(name: str, array: np.ndarray, *, ndim: int) -> np.ndarray:
    try:
        frozen = freeze_array(name, array, ndim=ndim)
    except ValueError as exc:
        raise ProcessingResultError(str(exc)) from exc
    if frozen is None:
        raise ProcessingResultError(f"{name} is required and cannot be None")
    return frozen


def _freeze_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        return freeze_metadata(metadata)
    except ValueError as exc:
        raise ProcessingResultError(str(exc)) from exc


@dataclass(frozen=True, eq=False)
class ProcessingResult:
    """The output of one ``archaeogpr.processing`` operation.

    ``dataset`` carries the processed amplitudes as a **new** ``GPRDataset``
    — the input dataset passed to the operation is never mutated.
    ``removed_component`` has the same shape as ``dataset.amplitudes`` and
    is defined so that, up to floating-point rounding::

        input_amplitudes == dataset.amplitudes + removed_component

    For a shift-based operation (time-zero) this holds everywhere by
    construction, but is only *physically meaningful* within the common,
    non-padded sample region — see ``valid_mask``. ``diagnostics`` is
    JSON-serializable and read-only, same guarantee as
    ``GPRDataset.metadata``. ``warnings`` are also appended to
    ``dataset.processing_history``; they are duplicated here for convenience
    so callers don't need to unpack the history to see what happened.

    ``valid_mask``, when not ``None``, has shape ``(channels, samples)`` —
    **not** ``(slices, channels, samples)`` — because a channel-wide,
    constant shift (see ``processing/time_zero.py``) makes validity the same
    for every slice within a channel by construction; storing one boolean
    per (slice, channel, sample) would triple memory for no additional
    information. Broadcast it yourself where needed:
    ``valid_mask[np.newaxis, :, :]``. ``True`` = real shifted radar data,
    ``False`` = padding introduced by a shift. Downstream operations
    (e.g. DC offset) that receive this mask must exclude ``False`` positions
    from both their own statistics and their own subtraction/write.
    """

    dataset: GPRDataset
    removed_component: np.ndarray
    diagnostics: Mapping[str, Any]
    warnings: tuple[str, ...] = ()
    valid_mask: np.ndarray | None = None

    def __post_init__(self) -> None:
        removed = _freeze_array("removed_component", self.removed_component, ndim=3)
        if removed.shape != self.dataset.amplitudes.shape:
            raise ProcessingResultError(
                f"removed_component shape {removed.shape} does not match "
                f"dataset.amplitudes shape {self.dataset.amplitudes.shape}"
            )
        if not isinstance(self.warnings, tuple):
            raise ProcessingResultError("warnings must be a tuple of strings")

        frozen_mask = None
        if self.valid_mask is not None:
            frozen_mask = _freeze_array("valid_mask", self.valid_mask, ndim=2)
            _, channels_count, samples_count = self.dataset.amplitudes.shape
            if frozen_mask.shape != (channels_count, samples_count):
                raise ProcessingResultError(
                    f"valid_mask shape {frozen_mask.shape} does not match "
                    f"(channels, samples)={(channels_count, samples_count)}"
                )
            if frozen_mask.dtype != np.bool_:
                raise ProcessingResultError(f"valid_mask dtype must be bool, got {frozen_mask.dtype}")

        object.__setattr__(self, "removed_component", removed)
        object.__setattr__(self, "diagnostics", _freeze_metadata(self.diagnostics))
        object.__setattr__(self, "warnings", tuple(str(w) for w in self.warnings))
        object.__setattr__(self, "valid_mask", frozen_mask)
