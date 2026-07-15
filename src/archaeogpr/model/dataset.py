"""Immutable in-memory data model for one OpenGPR radar array.

``GPRDataset`` is the single object every reader, QC function, processing
function, and exporter in this package passes around. It intentionally has
no methods that mutate radar data in place: processing steps produce a new
``GPRDataset`` (see ``archaeogpr.processing``) rather than editing an
existing one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from archaeogpr.model._frozen import FrozenDict, freeze_array, freeze_metadata

__all__ = ["GPRDataset", "DatasetValidationError", "FrozenDict"]


class DatasetValidationError(ValueError):
    """Raised when array shapes, dtypes, or metadata violate GPRDataset's invariants."""


def _freeze_array(name: str, array: np.ndarray | None, *, ndim: int) -> np.ndarray | None:
    try:
        return freeze_array(name, array, ndim=ndim)
    except ValueError as exc:
        raise DatasetValidationError(str(exc)) from exc


def _freeze_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        return freeze_metadata(metadata)
    except ValueError as exc:
        raise DatasetValidationError(str(exc)) from exc


@dataclass(frozen=True, eq=False)
class GPRDataset:
    """One OpenGPR radar array plus its geolocation, metadata, and processing history.

    ``amplitudes`` axis order is always ``(slice, channel, sample)``. All
    arrays are copied and marked read-only on construction, so in-place
    mutation (e.g. ``dataset.amplitudes[0] = 0``) raises ``ValueError``.
    Coordinate/depth/elevation arrays are ``None`` when the source file has
    no ``Sample Geolocations`` block. ``x``/``y`` are the top (surface)
    horizontal position of each trace; ``x_bottom``/``y_bottom`` are kept
    separately (usually, but not always, equal to ``x``/``y``) so the raw
    geolocation record can be fully reconstructed for export/QC.
    """

    amplitudes: np.ndarray
    time_ns: np.ndarray
    x: np.ndarray | None
    y: np.ndarray | None
    depth_top_m: np.ndarray | None
    elevation_top_m: np.ndarray | None
    depth_bottom_m: np.ndarray | None
    elevation_bottom_m: np.ndarray | None
    metadata: Mapping[str, Any]
    processing_history: tuple[Mapping[str, Any], ...] = ()
    x_bottom: np.ndarray | None = None
    y_bottom: np.ndarray | None = None

    def __post_init__(self) -> None:
        amplitudes = _freeze_array("amplitudes", self.amplitudes, ndim=3)
        if amplitudes is None:
            raise DatasetValidationError("amplitudes is required and cannot be None")
        slices, channels, samples = amplitudes.shape

        time_ns = _freeze_array("time_ns", self.time_ns, ndim=1)
        if time_ns is None:
            raise DatasetValidationError("time_ns is required and cannot be None")
        if time_ns.shape[0] != samples:
            raise DatasetValidationError(
                f"time_ns has length {time_ns.shape[0]}, expected {samples} (amplitudes.shape[2])"
            )

        coordinate_arrays = {
            "x": self.x,
            "y": self.y,
            "depth_top_m": self.depth_top_m,
            "elevation_top_m": self.elevation_top_m,
            "depth_bottom_m": self.depth_bottom_m,
            "elevation_bottom_m": self.elevation_bottom_m,
            "x_bottom": self.x_bottom,
            "y_bottom": self.y_bottom,
        }
        frozen_coordinates: dict[str, np.ndarray | None] = {}
        for name, array in coordinate_arrays.items():
            frozen = _freeze_array(name, array, ndim=2)
            if frozen is not None and frozen.shape != (slices, channels):
                raise DatasetValidationError(
                    f"{name} has shape {frozen.shape}, expected {(slices, channels)} (slices, channels)"
                )
            frozen_coordinates[name] = frozen

        if not isinstance(self.processing_history, tuple):
            raise DatasetValidationError("processing_history must be a tuple of mappings")

        object.__setattr__(self, "amplitudes", amplitudes)
        object.__setattr__(self, "time_ns", time_ns)
        for name, frozen in frozen_coordinates.items():
            object.__setattr__(self, name, frozen)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def __repr__(self) -> str:
        slices, channels, samples = self.amplitudes.shape
        return (
            f"GPRDataset(slices={slices}, channels={channels}, samples={samples}, "
            f"has_geolocation={self.has_geolocation}, processing_steps={len(self.processing_history)})"
        )

    @property
    def shape(self) -> tuple[int, int, int]:
        """``(slices, channels, samples)``; also see ``metadata['dimensions']['axis_order']``."""
        return self.amplitudes.shape

    @property
    def has_geolocation(self) -> bool:
        return self.x is not None and self.y is not None

    def with_processing_step(self, record: Mapping[str, Any]) -> GPRDataset:
        """Return a new dataset with ``record`` appended to ``processing_history``.

        Does not modify ``self`` or any of its arrays. This is the API
        boundary ``archaeogpr.processing`` functions use to record what they
        did (name, parameters, warnings) without mutating their input.
        """
        try:
            json.dumps(dict(record))
        except (TypeError, ValueError) as exc:
            raise DatasetValidationError(
                f"processing_history record must be JSON-serializable: {exc}"
            ) from exc
        return replace(self, processing_history=self.processing_history + (FrozenDict(record),))
