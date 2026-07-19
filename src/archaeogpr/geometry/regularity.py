"""Sampling regularity, direction consistency, and rectilinear-fit checks for a
resolved geometry's real X/Y grid (Sprint 3D-0 pre-commit audit, round 2).

These are three **scientifically distinct** questions about a real
acquisition's actual per-(trace, channel) coordinates, and this module
answers them separately rather than collapsing them into one boolean:

1. **Sampling regularity** -- are trace-to-trace step lengths and
   channel-to-channel spacings close to constant? A survey can be sampled
   very regularly while still following a curved path.
2. **Direction consistency** -- does the trace-to-trace heading stay close
   to constant? This is what actually detects a curving/wandering survey
   line, independent of how evenly it was sampled.
3. **Rectilinear fit** -- does the real grid actually coincide (within a
   documented, physically-scaled tolerance) with the single-origin,
   single-azimuth rectilinear reconstruction ``SurveyGeometry.
   along_track_coordinates``/``cross_track_offsets`` implies? A real file
   can pass (1) and (2) with excellent scores and still fail (3), because
   real GPS-/odometer-triggered trace positions drift from that low-order,
   two-point reconstruction by an amount that grows with profile length --
   confirmed empirically against this project's own real file (see
   ``ADR_016`` addendum). Conflating (3) with (1)/(2) under one
   ``is_regular`` flag was the exact defect this round of the audit fixes.

``actual_point_grid_available`` is a plain, unconditional fact (does a real
``x_coordinates``/``y_coordinates`` grid exist at all) -- independent of all
three checks above, which only apply *when* that grid exists.

Never reads ``dataset.amplitudes`` and never mutates its input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from archaeogpr.geometry.models import CrossTrackDirection, SurveyGeometry
from archaeogpr.geometry.transform import project_global_from_local

__all__ = ["GridRegularity", "assess_grid_regularity", "trace_centers"]

#: A coefficient of variation (std / mean) above this, on either the
#: along-track step lengths or the cross-channel spacings, flags a survey
#: whose spacing is not close to constant. Gates ``sampling_regular``.
SPACING_CV_WARNING_THRESHOLD = 0.15

#: A circular standard deviation of trace-to-trace heading above this many
#: degrees means the survey line curves enough that a single global azimuth
#: is a materially incomplete description of the actual path. Gates
#: ``direction_consistent`` (and, per the accepted policy, also
#: ``rectilinear_fit_acceptable``).
DIRECTION_STD_WARNING_THRESHOLD_DEG = 10.0

#: Rectilinear-fit acceptance tolerance, as a fraction of channel spacing.
#: Accepted policy (see ADR-016 addendum): a real point may lie up to half a
#: channel-width away from the idealized rectilinear reconstruction before
#: the fit is rejected -- half a channel spacing is the point at which a
#: real position could plausibly be mistaken for an *adjacent* channel's
#: position, which is the scale at which "this is still basically the same
#: rectangle" stops being a reasonable claim.
RECTILINEAR_FIT_CHANNEL_SPACING_FRACTION = 0.5

#: Rectilinear-fit acceptance tolerance, as a fraction of the along-track
#: span. A fixed per-step tolerance (like the channel-spacing one above)
#: does not scale for a very long profile, where small, realistic per-step
#: drift accumulates; 1% of the total along-track distance travelled is a
#: conventional order-of-magnitude bound for accumulated dead-reckoning/
#: GPS-relative drift over a traverse of that length.
RECTILINEAR_FIT_ALONG_TRACK_SPAN_FRACTION = 0.01


@dataclass(frozen=True)
class GridRegularity:
    """Sampling regularity, direction consistency, and rectilinear fit for one geometry.

    Every ``bool | None`` field is ``None`` when there was nothing to check
    (no real X/Y grid, or -- for ``rectilinear_fit_acceptable`` only -- no
    origin/azimuth/direction/spacing to build the comparison grid) -- not a
    failure, just "not applicable". ``actual_point_grid_available`` is the
    one plain, unconditional field.
    """

    actual_point_grid_available: bool

    sampling_regular: bool | None
    segment_length_cv: float | None
    cross_channel_spacing_cv: float | None

    direction_consistent: bool | None
    direction_std_deg: float | None

    rectilinear_fit_acceptable: bool | None
    residual_max_m: float | None
    residual_rmse_m: float | None
    residual_max_over_channel_spacing: float | None
    residual_rmse_over_channel_spacing: float | None
    residual_max_over_along_track_span: float | None
    residual_tolerance_m: float | None

    warnings: tuple[str, ...] = ()


def _coefficient_of_variation(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    if finite.size < 2:
        return None
    mean = float(np.mean(finite))
    if mean == 0.0:
        return None
    return float(np.std(finite) / abs(mean))


def _circular_std_deg(headings_rad: np.ndarray) -> float | None:
    """Standard circular-statistics dispersion (Mardia & Jupp): sigma = sqrt(-2 ln R)."""
    finite = headings_rad[np.isfinite(headings_rad)]
    if finite.size < 2:
        return None
    mean_cos, mean_sin = float(np.mean(np.cos(finite))), float(np.mean(np.sin(finite)))
    resultant_length = min(math.hypot(mean_cos, mean_sin), 1.0)
    if resultant_length <= 0.0:
        return None
    return math.degrees(math.sqrt(-2.0 * math.log(resultant_length)))


def trace_centers(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-trace mean (x, y) over finite channels; NaN for a trace with none finite.

    A plain Python loop (never ``np.nanmean``) so a fully-non-finite row can
    never trigger numpy's all-NaN RuntimeWarning -- the exact class of bug
    fixed in ``PlanView`` earlier in this same audit.
    """
    trace_count = x.shape[0]
    center_x = np.full(trace_count, np.nan)
    center_y = np.full(trace_count, np.nan)
    finite = np.isfinite(x) & np.isfinite(y)
    for i in range(trace_count):
        row_mask = finite[i]
        if row_mask.any():
            center_x[i] = np.mean(x[i, row_mask])
            center_y[i] = np.mean(y[i, row_mask])
    return center_x, center_y


def assess_grid_regularity(geometry: SurveyGeometry) -> GridRegularity:
    """Assess ``geometry``'s real X/Y grid: sampling regularity, direction consistency,
    and rectilinear fit to its own idealized reconstruction, each independently.

    Never mutates ``geometry``.
    """
    actual_point_grid_available = geometry.x_coordinates is not None and geometry.y_coordinates is not None

    not_available = GridRegularity(
        actual_point_grid_available=False,
        sampling_regular=None,
        segment_length_cv=None,
        cross_channel_spacing_cv=None,
        direction_consistent=None,
        direction_std_deg=None,
        rectilinear_fit_acceptable=None,
        residual_max_m=None,
        residual_rmse_m=None,
        residual_max_over_channel_spacing=None,
        residual_rmse_over_channel_spacing=None,
        residual_max_over_along_track_span=None,
        residual_tolerance_m=None,
    )
    if not actual_point_grid_available:
        return not_available
    assert geometry.x_coordinates is not None and geometry.y_coordinates is not None
    real_x, real_y = geometry.x_coordinates, geometry.y_coordinates

    # -- Sampling regularity + direction consistency: only need the real grid itself,
    # never a reconstruction -- robust to having no origin/azimuth at all.
    trace_center_x, trace_center_y = trace_centers(real_x, real_y)
    seg_dx, seg_dy = np.diff(trace_center_x), np.diff(trace_center_y)
    segment_length_cv = _coefficient_of_variation(np.hypot(seg_dx, seg_dy))
    cross_spacing = np.hypot(np.diff(real_x, axis=1), np.diff(real_y, axis=1))
    cross_channel_spacing_cv = _coefficient_of_variation(cross_spacing.ravel())
    # Same "clockwise from grid north" convention as azimuth_deg (see ADR-016).
    direction_std_deg = _circular_std_deg(np.arctan2(seg_dx, seg_dy))

    sampling_cvs = [cv for cv in (segment_length_cv, cross_channel_spacing_cv) if cv is not None]
    sampling_regular = bool(sampling_cvs) and all(cv <= SPACING_CV_WARNING_THRESHOLD for cv in sampling_cvs)
    direction_consistent = (
        direction_std_deg <= DIRECTION_STD_WARNING_THRESHOLD_DEG if direction_std_deg is not None else None
    )

    warnings: list[str] = []
    if segment_length_cv is not None and segment_length_cv > SPACING_CV_WARNING_THRESHOLD:
        warnings.append(
            f"Along-track step length varies by {segment_length_cv:.1%} (coefficient of variation), "
            f"above the {SPACING_CV_WARNING_THRESHOLD:.0%} threshold -- trace spacing is not close to "
            "constant."
        )
    if cross_channel_spacing_cv is not None and cross_channel_spacing_cv > SPACING_CV_WARNING_THRESHOLD:
        warnings.append(
            f"Cross-channel spacing varies by {cross_channel_spacing_cv:.1%} (coefficient of variation), "
            f"above the {SPACING_CV_WARNING_THRESHOLD:.0%} threshold -- channel spacing is not close to "
            "constant."
        )
    if direction_consistent is False:
        warnings.append(
            f"Trace-to-trace heading varies by {direction_std_deg:.1f} deg (circular std), above the "
            f"{DIRECTION_STD_WARNING_THRESHOLD_DEG:.0f} deg threshold -- the survey line curves enough "
            "that a single global azimuth does not fully represent its path."
        )

    # -- Rectilinear fit: needs origin/azimuth/direction/spacing to build the comparison grid.
    rectilinear_fit_acceptable: bool | None = None
    residual_max_m = residual_rmse_m = None
    residual_max_over_channel_spacing = residual_rmse_over_channel_spacing = None
    residual_max_over_along_track_span = None
    residual_tolerance_m = None
    if (
        geometry.origin_x is not None
        and geometry.origin_y is not None
        and geometry.azimuth_deg is not None
        and geometry.cross_track_direction is not CrossTrackDirection.UNKNOWN
        and geometry.along_track_coordinates is not None
        and geometry.cross_track_offsets is not None
        and geometry.trace_spacing_m is not None
        and geometry.channel_spacing_m is not None
    ):
        expected_x, expected_y = project_global_from_local(
            geometry.along_track_coordinates,
            geometry.cross_track_offsets,
            geometry.origin_x,
            geometry.origin_y,
            geometry.azimuth_deg,
            geometry.cross_track_direction,
        )
        finite_mask = (
            np.isfinite(real_x) & np.isfinite(real_y) & np.isfinite(expected_x) & np.isfinite(expected_y)
        )
        along_min, along_max = _finite_span(geometry.along_track_coordinates)
        if finite_mask.any() and along_min is not None and along_max is not None and along_max > along_min:
            residual = np.hypot(real_x - expected_x, real_y - expected_y)[finite_mask]
            residual_max_m = float(np.max(residual))
            residual_rmse_m = float(np.sqrt(np.mean(residual**2)))
            channel_spacing = geometry.channel_spacing_m
            along_track_span = along_max - along_min
            residual_max_over_channel_spacing = residual_max_m / channel_spacing
            residual_rmse_over_channel_spacing = residual_rmse_m / channel_spacing
            residual_max_over_along_track_span = residual_max_m / along_track_span
            residual_tolerance_m = max(
                RECTILINEAR_FIT_CHANNEL_SPACING_FRACTION * channel_spacing,
                RECTILINEAR_FIT_ALONG_TRACK_SPAN_FRACTION * along_track_span,
            )
            rectilinear_fit_acceptable = residual_max_m <= residual_tolerance_m and bool(direction_consistent)

    if rectilinear_fit_acceptable is False:
        assert residual_max_m is not None and residual_tolerance_m is not None
        warnings.append(
            f"Real acquisition grid deviates from a perfectly rectilinear reconstruction by up to "
            f"{residual_max_m:.4f} m ({residual_max_over_channel_spacing:.2f}x channel spacing), "
            f"exceeding the {residual_tolerance_m:.4f} m tolerance "
            f"(max of {RECTILINEAR_FIT_CHANNEL_SPACING_FRACTION:.0%} channel spacing and "
            f"{RECTILINEAR_FIT_ALONG_TRACK_SPAN_FRACTION:.0%} along-track span) -- this is a real, "
            "regularly-sampled acquisition, but is not geometrically equivalent to a single-origin, "
            "single-azimuth rectilinear grid."
        )

    return GridRegularity(
        actual_point_grid_available=True,
        sampling_regular=sampling_regular,
        segment_length_cv=segment_length_cv,
        cross_channel_spacing_cv=cross_channel_spacing_cv,
        direction_consistent=direction_consistent,
        direction_std_deg=direction_std_deg,
        rectilinear_fit_acceptable=rectilinear_fit_acceptable,
        residual_max_m=residual_max_m,
        residual_rmse_m=residual_rmse_m,
        residual_max_over_channel_spacing=residual_max_over_channel_spacing,
        residual_rmse_over_channel_spacing=residual_rmse_over_channel_spacing,
        residual_max_over_along_track_span=residual_max_over_along_track_span,
        residual_tolerance_m=residual_tolerance_m,
        warnings=tuple(warnings),
    )


def _finite_span(array: np.ndarray) -> tuple[float | None, float | None]:
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return None, None
    return float(np.min(finite)), float(np.max(finite))
