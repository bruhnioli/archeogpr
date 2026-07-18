"""Display policy: contrast/colormap/A-scan-mode state, and the pure functions
that turn it + a read-only amplitude view into render-only levels.

**This module is display policy, not processing** (see
``obsidian/ArchaeoGPR_Vault/06_DECISIONS/
ADR_013_Display_Policy_and_Non_Destructive_Visualization.md``): nothing here
ever writes to a ``GPRDataset``, appends to ``processing_history``, or
mutates an amplitude array in place. Every function below takes a NumPy
array and returns either new, small scalars (levels) or a new,
independently-allocated array (the normalized display copy in
``ascan_view.py`` uses this same guarantee) -- the source array passed in is
only ever read.

``DisplaySettings`` is immutable (frozen dataclass); "changing" a setting
means building a new instance via :func:`dataclasses.replace`, exactly like
``GPRDataset`` itself (ADR-001) -- the same immutability discipline applied
to display state instead of radar data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np

Colormap = Literal["gray", "seismic"]
AScanMode = Literal["full", "robust", "normalize"]

MIN_CLIP_PERCENTILE = 90.0
MAX_CLIP_PERCENTILE = 100.0
DEFAULT_CLIP_PERCENTILE = 99.0
#: A-scan "robust autoscale" mode's own percentile (axis range only -- see
#: ascan_view.py); reported here so it has one documented value, not a
#: magic number duplicated at each call site.
ASCAN_ROBUST_PERCENTILE = 99.0

_VALID_COLORMAPS = ("gray", "seismic")
_VALID_ASCAN_MODES = ("full", "robust", "normalize")


@dataclass(frozen=True)
class DisplaySettings:
    """Render-only state for one B-scan/A-scan view. Never touches a dataset."""

    clip_percentile: float = DEFAULT_CLIP_PERCENTILE
    symmetric_levels: bool = True
    manual_levels_enabled: bool = False
    manual_min: float | None = None
    manual_max: float | None = None
    colormap: Colormap = "gray"
    ascan_mode: AScanMode = "full"
    visible_region_autoscale: bool = False

    def __post_init__(self) -> None:
        if not (MIN_CLIP_PERCENTILE <= self.clip_percentile <= MAX_CLIP_PERCENTILE):
            raise ValueError(
                f"clip_percentile must be in [{MIN_CLIP_PERCENTILE}, {MAX_CLIP_PERCENTILE}], "
                f"got {self.clip_percentile}"
            )
        if self.colormap not in _VALID_COLORMAPS:
            raise ValueError(f"colormap must be one of {_VALID_COLORMAPS}, got {self.colormap!r}")
        if self.ascan_mode not in _VALID_ASCAN_MODES:
            raise ValueError(f"ascan_mode must be one of {_VALID_ASCAN_MODES}, got {self.ascan_mode!r}")

    def with_changes(self, **kwargs: object) -> DisplaySettings:
        """``dataclasses.replace(self, **kwargs)`` -- the one place settings are "changed"."""
        return replace(self, **kwargs)  # type: ignore[arg-type]  # generic passthrough by design

    def manual_levels_are_valid(self) -> bool:
        """``True`` iff both manual bounds are finite numbers with ``min < max``."""
        if self.manual_min is None or self.manual_max is None:
            return False
        return (
            math.isfinite(self.manual_min)
            and math.isfinite(self.manual_max)
            and self.manual_min < self.manual_max
        )


def default_display_settings() -> DisplaySettings:
    """``Reset Display``'s target state -- see ``main_window.py``."""
    return DisplaySettings()


def compute_display_levels(amplitude: np.ndarray, settings: DisplaySettings) -> tuple[float, float]:
    """``(low, high)`` color/axis levels for ``amplitude`` under ``settings``.

    Read-only: never modifies ``amplitude``. Resolution order:

    1. **Manual levels**, only if enabled *and* valid (see
       :meth:`DisplaySettings.manual_levels_are_valid`) -- an enabled-but-
       invalid manual range is never applied; this function silently falls
       through to the automatic levels below instead (the GUI layer is
       responsible for also surfacing the invalid-input error to the user
       -- see ``main_window.py``).
    2. **Symmetric**: ``scale = percentile(|finite amplitude|,
       clip_percentile)`` -> ``(-scale, scale)``. Zero-centered by
       construction, independent of the actual sign balance of the data.
    3. **Asymmetric** (``symmetric_levels=False``): a two-sided robust range,
       ``lower = percentile(finite amplitude, 100 - clip_percentile)``,
       ``upper = percentile(finite amplitude, clip_percentile)`` -- e.g. at
       ``clip_percentile=99`` this keeps the central 98% of the amplitude
       distribution and clips the outer 1% on each side. Falls back to the
       symmetric computation if this ever produces a degenerate
       (``lower >= upper`` or non-finite) range.

    An all-non-finite or empty ``amplitude`` (or any other degenerate case)
    safely falls back to ``(-1.0, 1.0)`` rather than raising or producing a
    zero-width/NaN color range.
    """
    if settings.manual_levels_enabled and settings.manual_levels_are_valid():
        assert settings.manual_min is not None and settings.manual_max is not None
        return float(settings.manual_min), float(settings.manual_max)

    finite = amplitude[np.isfinite(amplitude)]
    if finite.size == 0:
        return (-1.0, 1.0)

    if settings.symmetric_levels:
        return _symmetric_levels(finite, settings.clip_percentile)

    lower = float(np.percentile(finite, 100.0 - settings.clip_percentile))
    upper = float(np.percentile(finite, settings.clip_percentile))
    if not (math.isfinite(lower) and math.isfinite(upper)) or lower >= upper:
        return _symmetric_levels(finite, settings.clip_percentile)
    return lower, upper


def _symmetric_levels(finite_amplitude: np.ndarray, clip_percentile: float) -> tuple[float, float]:
    scale = float(np.percentile(np.abs(finite_amplitude), clip_percentile))
    if not math.isfinite(scale) or scale <= 0:
        scale = 1.0
    return (-scale, scale)
