"""Display policy for one rendered C-scan value grid (Sprint 3D-1).

Mirrors ``archaeogpr.gui.models.display_settings.DisplaySettings`` closely
(immutable, ``with_changes()`` over ``dataclasses.replace``, the same
manual/symmetric/asymmetric percentile resolution order) but is kept as a
separate type rather than reusing ``DisplaySettings`` directly: a C-scan has
no A-scan mode or visible-region autoscale, and adds two fields
(``point_size``, ``geometry_view``) that ``DisplaySettings`` has no use for.
Nothing here ever touches a ``CScanResult``'s ``values``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np

from archaeogpr.cscan.models import CScanAggregation, CScanGeometryView, aggregation_is_signed

Colormap = Literal["gray", "seismic"]

MIN_CLIP_PERCENTILE = 90.0
MAX_CLIP_PERCENTILE = 100.0
DEFAULT_CLIP_PERCENTILE = 99.0
DEFAULT_POINT_SIZE = 10.0

_VALID_COLORMAPS = ("gray", "seismic")

__all__ = [
    "Colormap",
    "MIN_CLIP_PERCENTILE",
    "MAX_CLIP_PERCENTILE",
    "DEFAULT_CLIP_PERCENTILE",
    "DEFAULT_POINT_SIZE",
    "CScanDisplaySettings",
    "default_cscan_display_settings",
    "compute_cscan_display_levels",
]


@dataclass(frozen=True)
class CScanDisplaySettings:
    """Render-only state for one C-scan view. Never touches a ``CScanResult``."""

    clip_percentile: float = DEFAULT_CLIP_PERCENTILE
    symmetric_levels: bool = False
    manual_levels_enabled: bool = False
    manual_min: float | None = None
    manual_max: float | None = None
    colormap: Colormap = "gray"
    show_invalid_points: bool = True
    point_size: float = DEFAULT_POINT_SIZE
    geometry_view: CScanGeometryView = CScanGeometryView.ACTUAL_XY_POINT_MAP

    def __post_init__(self) -> None:
        if not (MIN_CLIP_PERCENTILE <= self.clip_percentile <= MAX_CLIP_PERCENTILE):
            raise ValueError(
                f"clip_percentile must be in [{MIN_CLIP_PERCENTILE}, {MAX_CLIP_PERCENTILE}], "
                f"got {self.clip_percentile}"
            )
        if self.colormap not in _VALID_COLORMAPS:
            raise ValueError(f"colormap must be one of {_VALID_COLORMAPS}, got {self.colormap!r}")
        if self.point_size <= 0:
            raise ValueError(f"point_size must be greater than zero, got {self.point_size}")

    def with_changes(self, **kwargs: object) -> CScanDisplaySettings:
        """``dataclasses.replace(self, **kwargs)`` -- the one place settings are "changed"."""
        return replace(self, **kwargs)  # type: ignore[arg-type]  # generic passthrough by design

    def manual_levels_are_valid(self) -> bool:
        if self.manual_min is None or self.manual_max is None:
            return False
        return (
            math.isfinite(self.manual_min)
            and math.isfinite(self.manual_max)
            and self.manual_min < self.manual_max
        )


def default_cscan_display_settings() -> CScanDisplaySettings:
    return CScanDisplaySettings()


def compute_cscan_display_levels(
    values: np.ndarray, aggregation: CScanAggregation, settings: CScanDisplaySettings
) -> tuple[float, float]:
    """``(low, high)`` color levels for a C-scan ``values`` grid under ``settings``.

    Read-only. Resolution order identical to
    ``display_settings.compute_display_levels``: manual (if enabled+valid) ->
    symmetric percentile -> asymmetric two-sided percentile -> symmetric
    fallback on degeneracy -> ``(-1.0, 1.0)`` for empty/all-non-finite input.
    "Symmetric" is only meaningful for a signed aggregation (see
    :func:`archaeogpr.cscan.models.aggregation_is_signed`) — the GUI layer is
    responsible for disabling that toggle for a non-negative aggregation, not
    this function (which will still compute *something* sane either way).
    """
    del aggregation  # kept in the signature for call-site clarity/future use; not needed for the math itself
    if settings.manual_levels_enabled and settings.manual_levels_are_valid():
        assert settings.manual_min is not None and settings.manual_max is not None
        return float(settings.manual_min), float(settings.manual_max)

    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return (-1.0, 1.0)

    if settings.symmetric_levels:
        return _symmetric_levels(finite, settings.clip_percentile)

    lower = float(np.percentile(finite, 100.0 - settings.clip_percentile))
    upper = float(np.percentile(finite, settings.clip_percentile))
    if not (math.isfinite(lower) and math.isfinite(upper)) or lower >= upper:
        return _symmetric_levels(finite, settings.clip_percentile)
    return lower, upper


def _symmetric_levels(finite_values: np.ndarray, clip_percentile: float) -> tuple[float, float]:
    scale = float(np.percentile(np.abs(finite_values), clip_percentile))
    if not math.isfinite(scale) or scale <= 0:
        scale = 1.0
    return (-scale, scale)


def symmetric_levels_allowed(aggregation: CScanAggregation) -> bool:
    """``True`` only for a signed aggregation — see ``CScanDisplaySettings.symmetric_levels``."""
    return aggregation_is_signed(aggregation)
