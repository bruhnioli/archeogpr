"""Plain point-count/extent/duplicate/monotonicity/area statistics for one resolved geometry.

Kept separate from ``resolve.py`` because these are display/report
statistics about a geometry that has already been resolved, not part of
resolving it. Reused by both the (Qt-free) JSON export and the GUI's
Geometry Summary panel -- neither reimplements the other.

Three genuinely different "area" figures are reported, never conflated
under one ambiguous name (see the pre-commit audit's regularity round 2):

- ``rectilinear_parameter_grid_area_m2``: ``along_span * cross_span`` of the
  *derived*, always-rectilinear-by-construction parameter grid. Reported
  whenever metric spacing is known, regardless of whether the real
  acquisition is itself rectilinear -- it describes the parameter grid, not
  a claim about the real survey.
- ``approximate_ribbon_area_m2``: real along-track path length (summed
  trace-to-trace distances, not just the span) times nominal swath width.
  A constant-width-ribbon approximation -- always reported with a warning
  making that explicit.
- ``actual_polygon_area_m2``: the shoelace-formula area of the real
  acquisition footprint's own outer boundary. Only reported when every
  boundary point is finite and a cheap consistency check against the ribbon
  estimate doesn't suggest a self-intersecting/degenerate boundary;
  otherwise withheld with a warning rather than risk reporting a wrong area.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from archaeogpr.geometry.models import CoordinateMode, SurveyGeometry
from archaeogpr.geometry.regularity import GridRegularity, assess_grid_regularity, trace_centers

__all__ = ["GeometrySummary", "compute_geometry_summary"]

#: A polygon-area heuristic sanity check (see module docstring): if the
#: shoelace area diverges from the simple ribbon-area estimate by more than
#: this factor in either direction, the boundary is treated as likely
#: self-intersecting or degenerate and the polygon area is withheld. This
#: is a cheap consistency check, not a formal simple-polygon proof -- a
#: sufficiently pathological boundary could still slip through undetected;
#: no computational-geometry dependency was added this sprint to close that
#: gap completely.
POLYGON_AREA_ROUGH_AGREEMENT_FACTOR = 3.0


@dataclass(frozen=True)
class GeometrySummary:
    """Point-count/extent/duplicate/monotonicity/area statistics for one :class:`SurveyGeometry`."""

    total_point_count: int
    valid_point_count: int
    invalid_point_count: int
    along_track_min: float | None
    along_track_max: float | None
    along_track_span: float | None
    cross_track_min: float | None
    cross_track_max: float | None
    cross_track_span: float | None
    x_min: float | None
    x_max: float | None
    y_min: float | None
    y_max: float | None
    #: Area of the derived, always-rectilinear parameter grid. See module docstring.
    rectilinear_parameter_grid_area_m2: float | None
    #: Real along-track path length x nominal swath width. See module docstring.
    approximate_ribbon_area_m2: float | None
    #: Shoelace-formula area of the real acquisition footprint's own boundary. See module docstring.
    actual_polygon_area_m2: float | None
    along_track_monotonic: bool | None
    duplicate_coordinate_count: int
    non_finite_coordinate_count: int
    #: Sampling regularity / direction consistency / rectilinear fit for the
    #: real X/Y grid (when present) -- see ``archaeogpr.geometry.regularity``.
    grid_regularity: GridRegularity
    #: Caveats produced while computing this summary itself (e.g. an area
    #: withheld, or reported only as an approximation) -- distinct from
    #: ``SurveyGeometry.warnings``, which are resolve-time.
    warnings: tuple[str, ...] = ()


def _finite_min_max(array: np.ndarray | None) -> tuple[float | None, float | None]:
    if array is None or array.size == 0:
        return None, None
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return None, None
    return float(np.min(finite)), float(np.max(finite))


def _shoelace_area(points_x: np.ndarray, points_y: np.ndarray) -> float:
    """The shoelace formula's area for a closed polygon (last point implicitly joins the first)."""
    x_next = np.roll(points_x, -1)
    y_next = np.roll(points_y, -1)
    return float(abs(np.sum(points_x * y_next - x_next * points_y)) / 2.0)


def _perimeter_points(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """The (trace, channel) grid's outer boundary, traced once around, no duplicated corners.

    ``None`` if the grid is too small to have a boundary (fewer than 2
    traces or 2 channels) or any boundary point is non-finite.
    """
    trace_count, channel_count = x.shape
    if trace_count < 2 or channel_count < 2:
        return None
    top_x, top_y = x[0, :], y[0, :]
    right_x, right_y = x[1:, -1], y[1:, -1]
    bottom_x, bottom_y = x[-1, -2::-1], y[-1, -2::-1]
    left_x, left_y = x[-2:0:-1, 0], y[-2:0:-1, 0]
    perimeter_x = np.concatenate([top_x, right_x, bottom_x, left_x])
    perimeter_y = np.concatenate([top_y, right_y, bottom_y, left_y])
    if not (np.all(np.isfinite(perimeter_x)) and np.all(np.isfinite(perimeter_y))):
        return None
    return perimeter_x, perimeter_y


def compute_geometry_summary(geometry: SurveyGeometry) -> GeometrySummary:
    """Compute display/report statistics for ``geometry``. Never mutates it."""
    total_point_count = geometry.trace_count * geometry.channel_count

    non_finite_coordinate_count = 0
    duplicate_coordinate_count = 0
    invalid_point_count = 0
    if geometry.x_coordinates is not None and geometry.y_coordinates is not None:
        finite_mask = np.isfinite(geometry.x_coordinates) & np.isfinite(geometry.y_coordinates)
        non_finite_coordinate_count = int(np.size(finite_mask) - np.count_nonzero(finite_mask))
        invalid_point_count = non_finite_coordinate_count
        if finite_mask.any():
            points = np.stack(
                [geometry.x_coordinates[finite_mask], geometry.y_coordinates[finite_mask]], axis=1
            )
            _unique, counts = np.unique(points, axis=0, return_counts=True)
            duplicate_coordinate_count = int(np.sum(counts[counts > 1] - 1))
    valid_point_count = total_point_count - invalid_point_count

    along_min, along_max = _finite_min_max(geometry.along_track_coordinates)
    along_span = (along_max - along_min) if (along_min is not None and along_max is not None) else None

    cross_min, cross_max = _finite_min_max(geometry.cross_track_offsets)
    cross_span = (cross_max - cross_min) if (cross_min is not None and cross_max is not None) else None

    x_min, x_max = _finite_min_max(geometry.x_coordinates)
    y_min, y_max = _finite_min_max(geometry.y_coordinates)

    along_track_monotonic: bool | None = None
    if geometry.along_track_coordinates is not None and geometry.along_track_coordinates.size >= 2:
        deltas = np.diff(geometry.along_track_coordinates)
        finite_deltas = deltas[np.isfinite(deltas)]
        if finite_deltas.size:
            along_track_monotonic = bool(np.all(finite_deltas > 0) or np.all(finite_deltas < 0))

    summary_warnings: list[str] = []
    grid_regularity = assess_grid_regularity(geometry)

    # -- 1. Rectilinear parameter-grid area: describes the DERIVED grid.
    # LOCAL_METRIC has no real grid to disagree with it, so it is always
    # reported there. GLOBAL_PROJECTED has a real grid that may or may not
    # actually be rectilinear -- reporting this area there requires a
    # verified-acceptable rectilinear fit, exactly like the pre-commit
    # audit's original (round 1) gating, now keyed on the correctly
    # separated ``rectilinear_fit_acceptable`` rather than a conflated
    # ``is_regular``. Never presented as "the" footprint area when the real
    # grid does not fit it (see module docstring / ADR-016 addendum).
    rectilinear_parameter_grid_area_m2: float | None = None
    if along_span is not None and cross_span is not None:
        if geometry.coordinate_mode is CoordinateMode.LOCAL_METRIC:
            rectilinear_parameter_grid_area_m2 = float(along_span * cross_span)
        elif geometry.coordinate_mode is CoordinateMode.GLOBAL_PROJECTED:
            if grid_regularity.rectilinear_fit_acceptable is True:
                rectilinear_parameter_grid_area_m2 = float(along_span * cross_span)
            elif grid_regularity.rectilinear_fit_acceptable is False:
                summary_warnings.append(
                    "rectilinear_parameter_grid_area_m2 is not reported: the real acquisition grid "
                    "does not fit a rectilinear reconstruction within tolerance (see grid_regularity)."
                )
            else:
                summary_warnings.append(
                    "rectilinear_parameter_grid_area_m2 is not reported: rectilinear fit could not be "
                    "verified (missing origin/azimuth/cross-track direction or non-finite coordinates)."
                )

    # -- 2 & 3. Approximate ribbon area and actual polygon area: both need
    # the real X/Y grid; neither is computed for LOCAL_METRIC (no real grid
    # to measure -- see regularity.py's "actual vs. idealized" distinction).
    approximate_ribbon_area_m2: float | None = None
    actual_polygon_area_m2: float | None = None
    if (
        geometry.coordinate_mode is CoordinateMode.GLOBAL_PROJECTED
        and geometry.x_coordinates is not None
        and geometry.y_coordinates is not None
        and cross_span is not None
    ):
        center_x, center_y = trace_centers(geometry.x_coordinates, geometry.y_coordinates)
        segment_lengths = np.hypot(np.diff(center_x), np.diff(center_y))
        if np.all(np.isfinite(segment_lengths)) and segment_lengths.size:
            path_length = float(np.sum(segment_lengths))
            approximate_ribbon_area_m2 = path_length * cross_span
            summary_warnings.append(
                f"approximate_ribbon_area_m2 ({approximate_ribbon_area_m2:.4f} m^2) assumes a constant "
                "swath width along the real path length -- it is an approximation, not an exact "
                "footprint area."
            )

        perimeter = _perimeter_points(geometry.x_coordinates, geometry.y_coordinates)
        if perimeter is not None:
            perimeter_x, perimeter_y = perimeter
            candidate_area = _shoelace_area(perimeter_x, perimeter_y)
            if approximate_ribbon_area_m2 and approximate_ribbon_area_m2 > 0:
                ratio = candidate_area / approximate_ribbon_area_m2
                agrees_roughly = (
                    (1.0 / POLYGON_AREA_ROUGH_AGREEMENT_FACTOR)
                    <= ratio
                    <= (POLYGON_AREA_ROUGH_AGREEMENT_FACTOR)
                )
            else:
                agrees_roughly = True  # no ribbon estimate to cross-check against; accept as-is
            if agrees_roughly:
                actual_polygon_area_m2 = candidate_area
            else:
                summary_warnings.append(
                    "actual_polygon_area_m2 is not reported: the shoelace-formula boundary area "
                    f"({candidate_area:.4f} m^2) disagrees with the approximate ribbon area by more "
                    f"than {POLYGON_AREA_ROUGH_AGREEMENT_FACTOR:.0f}x, suggesting a "
                    "self-intersecting or degenerate boundary."
                )
        else:
            summary_warnings.append(
                "actual_polygon_area_m2 is not reported: the acquisition footprint's boundary "
                "contains non-finite coordinates or the grid is too small to have a boundary."
            )

    summary_warnings.extend(grid_regularity.warnings)

    return GeometrySummary(
        total_point_count=total_point_count,
        valid_point_count=valid_point_count,
        invalid_point_count=invalid_point_count,
        along_track_min=along_min,
        along_track_max=along_max,
        along_track_span=along_span,
        cross_track_min=cross_min,
        cross_track_max=cross_max,
        cross_track_span=cross_span,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        rectilinear_parameter_grid_area_m2=rectilinear_parameter_grid_area_m2,
        approximate_ribbon_area_m2=approximate_ribbon_area_m2,
        actual_polygon_area_m2=actual_polygon_area_m2,
        along_track_monotonic=along_track_monotonic,
        duplicate_coordinate_count=duplicate_coordinate_count,
        non_finite_coordinate_count=non_finite_coordinate_count,
        grid_regularity=grid_regularity,
        warnings=tuple(summary_warnings),
    )
