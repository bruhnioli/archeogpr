"""Qt-free C-scan / time-slice domain models.

A "C-scan" here is a single ``(trace_count, channel_count)`` value grid
derived from one time sample or one time window of a
:class:`~archaeogpr.model.dataset.GPRDataset`'s
``amplitudes`` (shape ``(trace_count, channel_count, sample_count)``, see
``GPRDataset.amplitudes`` docstring — this module's "trace" is that array's
axis 0, called "slice" internally by ``GPRDataset`` itself). Everything in
this module is independent of Qt/pyqtgraph and of the ``archaeogpr.geometry``
package: a C-scan value grid is defined purely in terms of amplitudes/time,
never coordinates. Rendering that grid on the actual X/Y point grid or on the
derived s/c parameter grid is a GUI-layer concern (see
``archaeogpr.gui.views.cscan_view``), not a domain concern.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from archaeogpr.model._frozen import freeze_array, freeze_metadata


class CScanError(ValueError):
    """Raised when a C-scan request or result violates its invariants."""


class CScanAggregation(enum.Enum):
    """How the sample(s) within a time selection are combined into one value.

    ``SINGLE_SAMPLE`` is the only signed aggregation — it reports the actual
    signed amplitude of the nearest real sample, never an absolute value.
    Sprint 3D-1 deliberately does not add a signed *window* mean: averaging
    positive and negative half-cycles of a GPR wavelet over a window can
    cancel out to a small or zero value that looks like "no reflection" even
    directly on top of a strong one — scientifically misleading. The three
    window aggregations below are non-negative by construction instead.
    """

    SINGLE_SAMPLE = "single_sample"
    RMS = "rms"
    MEAN_ABSOLUTE = "mean_absolute"
    MAXIMUM_ABSOLUTE = "maximum_absolute"


_WINDOW_AGGREGATIONS = frozenset(
    {CScanAggregation.RMS, CScanAggregation.MEAN_ABSOLUTE, CScanAggregation.MAXIMUM_ABSOLUTE}
)


def aggregation_is_signed(aggregation: CScanAggregation) -> bool:
    """``True`` only for :attr:`CScanAggregation.SINGLE_SAMPLE`.

    Used to decide whether "symmetric levels" is a meaningful display option
    (see ``CScanDisplaySettings``) — the three window aggregations can never
    produce a negative value, so a symmetric (zero-centered) color scale
    would be misleading for them.
    """
    return aggregation is CScanAggregation.SINGLE_SAMPLE


def aggregation_uses_window(aggregation: CScanAggregation) -> bool:
    """``True`` for the three window aggregations, ``False`` for ``SINGLE_SAMPLE``."""
    return aggregation in _WINDOW_AGGREGATIONS


class CScanSourceKind(enum.Enum):
    """Which of ``DatasetSession``'s three datasets a C-scan was computed from."""

    RAW = "raw"
    CURRENT = "current"
    PREVIEW = "preview"


class CScanGeometryView(enum.Enum):
    """Which of the two display paths a C-scan value grid is being rendered on.

    See ADR-017: these are never resampled into each other. ``ACTUAL_XY_POINT_MAP``
    is the default and requires only ``actual_xy_point_grid_ready``;
    ``DERIVED_PARAMETER_GRID`` requires ``local_parameter_grid_ready`` and
    is always labeled as an idealized parameter-space view, never as the
    true survey footprint.
    """

    ACTUAL_XY_POINT_MAP = "actual_xy_point_map"
    DERIVED_PARAMETER_GRID = "derived_parameter_grid"


@dataclass(frozen=True)
class CScanRequest:
    """An immutable, fully-specified request to compute one C-scan value grid.

    ``window_width_ns`` must be ``None`` for ``SINGLE_SAMPLE`` (nearest-sample
    selection has no window) and a finite, positive number of nanoseconds for
    the three window aggregations. ``source_revision``/``geometry_revision``
    are a snapshot of ``DatasetSession.current_revision`` (or
    ``preview_base_revision`` for a preview source) and
    ``GeometrySession.geometry_revision`` at the moment the request was made
    — used only for stale-result detection (see ``CScanSession``), never by
    :func:`archaeogpr.cscan.compute.compute_cscan` itself. ``token`` is a
    caller-assigned monotonic integer identifying this specific request,
    mirroring ``FileLoadWorker``/``ProcessingWorker``'s existing token
    pattern for discarding superseded async results.
    """

    aggregation: CScanAggregation
    center_time_ns: float
    window_width_ns: float | None
    source_kind: CScanSourceKind
    source_revision: int
    geometry_revision: int
    token: int

    def __post_init__(self) -> None:
        if not isinstance(self.aggregation, CScanAggregation):
            raise CScanError(f"aggregation must be a CScanAggregation, got {self.aggregation!r}")
        if not isinstance(self.source_kind, CScanSourceKind):
            raise CScanError(f"source_kind must be a CScanSourceKind, got {self.source_kind!r}")
        if not np.isfinite(self.center_time_ns):
            raise CScanError(f"center_time_ns must be finite, got {self.center_time_ns!r}")
        uses_window = aggregation_uses_window(self.aggregation)
        if uses_window:
            if self.window_width_ns is None or not np.isfinite(self.window_width_ns):
                raise CScanError(
                    f"window_width_ns must be a finite number for {self.aggregation.value}, "
                    f"got {self.window_width_ns!r}"
                )
            if self.window_width_ns <= 0:
                raise CScanError(f"window_width_ns must be greater than zero, got {self.window_width_ns!r}")
        elif self.window_width_ns is not None:
            raise CScanError(
                f"window_width_ns must be None for {self.aggregation.value} "
                "(nearest-sample selection has no window)"
            )


@dataclass(frozen=True)
class CScanStatistics:
    """Finite-value statistics over one ``CScanResult.values`` grid."""

    valid_count: int
    invalid_count: int
    min_value: float | None
    max_value: float | None
    mean_value: float | None


def _freeze_result_array(name: str, array: np.ndarray, *, ndim: int) -> np.ndarray:
    try:
        frozen = freeze_array(name, array, ndim=ndim)
    except ValueError as exc:
        raise CScanError(str(exc)) from exc
    if frozen is None:
        raise CScanError(f"{name} is required and cannot be None")
    return frozen


@dataclass(frozen=True, eq=False)
class CScanResult:
    """The immutable output of one :func:`~archaeogpr.cscan.compute.compute_cscan` call.

    ``values`` and ``valid_mask`` both have shape ``(trace_count,
    channel_count)`` — this is a per-*cell* mask (unlike
    ``ProcessingResult.valid_mask``, which is ``(channel_count,
    sample_count)`` and constant across traces): a cell can be individually
    invalid here if its own amplitude is non-finite even when the
    channel/sample itself is nominally valid. ``NaN`` in ``values`` always
    means ``valid_mask`` is ``False`` at that cell, and vice versa.

    ``selected_sample_index`` is only meaningful for ``SINGLE_SAMPLE``
    (``None`` for a window aggregation, since no single sample is "the"
    selected one). ``sample_start_index``/``sample_stop_index`` are always
    set, as a half-open ``[start, stop)`` range — for ``SINGLE_SAMPLE`` this
    collapses to ``(selected_sample_index, selected_sample_index + 1)``.
    """

    values: np.ndarray
    valid_mask: np.ndarray
    aggregation: CScanAggregation
    requested_center_time_ns: float
    requested_window_width_ns: float | None
    selected_sample_index: int | None
    sample_start_index: int
    sample_stop_index: int
    actual_start_time_ns: float
    actual_stop_time_ns: float
    source_kind: CScanSourceKind
    source_revision: int
    geometry_revision: int
    warnings: tuple[str, ...]
    statistics: CScanStatistics
    metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        values = _freeze_result_array("values", self.values, ndim=2)
        valid_mask = _freeze_result_array("valid_mask", self.valid_mask, ndim=2)
        if valid_mask.dtype != np.bool_:
            raise CScanError(f"valid_mask dtype must be bool, got {valid_mask.dtype}")
        if values.shape != valid_mask.shape:
            raise CScanError(
                f"values shape {values.shape} does not match valid_mask shape {valid_mask.shape}"
            )
        if self.sample_stop_index <= self.sample_start_index:
            raise CScanError(
                f"sample_stop_index ({self.sample_stop_index}) must be greater than "
                f"sample_start_index ({self.sample_start_index})"
            )
        if not isinstance(self.warnings, tuple):
            raise CScanError("warnings must be a tuple of strings")
        try:
            metadata = freeze_metadata(self.metadata)
        except ValueError as exc:
            raise CScanError(str(exc)) from exc

        object.__setattr__(self, "values", values)
        object.__setattr__(self, "valid_mask", valid_mask)
        object.__setattr__(self, "warnings", tuple(str(w) for w in self.warnings))
        object.__setattr__(self, "metadata", metadata)


__all__ = [
    "CScanError",
    "CScanAggregation",
    "aggregation_is_signed",
    "aggregation_uses_window",
    "CScanSourceKind",
    "CScanGeometryView",
    "CScanRequest",
    "CScanStatistics",
    "CScanResult",
]
