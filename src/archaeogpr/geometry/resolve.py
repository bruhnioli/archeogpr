"""Resolves one dataset's :class:`~archaeogpr.geometry.models.SurveyGeometry` and readiness gates.

Priority order for every field (see ``ADR_016_Geometry_Provenance_and_
Readiness_Gates.md``): a valid user override, then real file metadata, then
a value reliably derived from file metadata, then an index-space fallback,
then missing. This module never invents a physical value it cannot trace
back to one of those four sources.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from archaeogpr.geometry.models import (
    CoordinateMode,
    CrossTrackDirection,
    GeometryProvenance,
    ReadinessGates,
    ReadinessStatus,
    SurveyGeometry,
)
from archaeogpr.geometry.regularity import assess_grid_regularity
from archaeogpr.geometry.transform import project_global_from_local
from archaeogpr.geometry.validation import (
    validate_epsg_identifier,
    validate_finite,
    validate_positive_spacing,
)
from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.background import compute_trace_spacing
from archaeogpr.qc.metadata import compute_cross_channel_spacing_m

__all__ = ["GeometryOverrides", "GeometryResolution", "resolve_survey_geometry"]


@dataclass(frozen=True)
class GeometryOverrides:
    """Session-level user-supplied geometry values. Never written to the raw dataset or file.

    Every field is optional; a ``None`` field means "no override -- let the
    resolver fall through to file metadata / derived / index-space".
    """

    trace_spacing_m: float | None = None
    channel_spacing_m: float | None = None
    channel_zero_offset_m: float | None = None
    origin_x: float | None = None
    origin_y: float | None = None
    azimuth_deg: float | None = None
    cross_track_direction: CrossTrackDirection | None = None
    crs_identifier: str | None = None

    def validate(self) -> tuple[str, ...]:
        """Aggregate validation errors across every supplied field. Empty tuple means valid."""
        errors: list[str] = []
        errors.extend(validate_positive_spacing(self.trace_spacing_m, "Trace spacing"))
        errors.extend(validate_positive_spacing(self.channel_spacing_m, "Channel spacing"))
        errors.extend(validate_finite(self.channel_zero_offset_m, "Channel zero offset"))
        errors.extend(validate_finite(self.origin_x, "Origin Easting/X"))
        errors.extend(validate_finite(self.origin_y, "Origin Northing/Y"))
        errors.extend(validate_finite(self.azimuth_deg, "Azimuth"))
        errors.extend(validate_epsg_identifier(self.crs_identifier))
        return tuple(errors)


@dataclass(frozen=True)
class GeometryResolution:
    """Everything :func:`resolve_survey_geometry` produces: geometry, readiness, and source summary."""

    geometry: SurveyGeometry
    readiness: ReadinessGates
    source_summary: dict[str, Any]


def _normalize_crs(
    dataset: GPRDataset, overrides: GeometryOverrides
) -> tuple[str | None, GeometryProvenance]:
    if overrides.crs_identifier:
        errors = validate_epsg_identifier(overrides.crs_identifier)
        if not errors:
            text = overrides.crs_identifier.strip()
            if ":" not in text:
                text = f"EPSG:{text}"
            else:
                prefix, _, code = text.partition(":")
                text = f"{prefix.strip().upper()}:{code.strip()}"
            return text, GeometryProvenance.USER_SUPPLIED
    spatial_reference = dataset.metadata.get("spatial_reference")
    if isinstance(spatial_reference, dict):
        srs_type = spatial_reference.get("type")
        srs_value = spatial_reference.get("value")
        if srs_type and srs_value is not None:
            return f"{srs_type}:{srs_value}", GeometryProvenance.FILE_METADATA
    return None, GeometryProvenance.MISSING


def _resolve_trace_spacing(
    dataset: GPRDataset, overrides: GeometryOverrides
) -> tuple[float | None, GeometryProvenance, tuple[str, ...]]:
    if overrides.trace_spacing_m is not None:
        return overrides.trace_spacing_m, GeometryProvenance.USER_SUPPLIED, ()
    info = compute_trace_spacing(dataset)
    spacing = info["trace_spacing_m"]
    warnings = tuple(info["warnings"])
    if spacing is None:
        return None, GeometryProvenance.MISSING, warnings
    provenance = (
        GeometryProvenance.FILE_METADATA
        if info["trace_spacing_source"] == "geolocation"
        else GeometryProvenance.DERIVED
    )
    return float(spacing), provenance, warnings


def _resolve_channel_spacing(
    dataset: GPRDataset, overrides: GeometryOverrides
) -> tuple[float | None, GeometryProvenance]:
    if overrides.channel_spacing_m is not None:
        return overrides.channel_spacing_m, GeometryProvenance.USER_SUPPLIED
    if dataset.has_geolocation:
        spacing = compute_cross_channel_spacing_m(dataset.x, dataset.y)
        if spacing is not None:
            return spacing, GeometryProvenance.DERIVED
    return None, GeometryProvenance.MISSING


def _resolve_channel_zero_offset(overrides: GeometryOverrides) -> tuple[float, GeometryProvenance]:
    if overrides.channel_zero_offset_m is not None:
        return overrides.channel_zero_offset_m, GeometryProvenance.USER_SUPPLIED
    # Choosing channel 0 as the local cross-track origin (offset 0.0) is a
    # coordinate-system convention, not a claim about a physically measured
    # quantity -- unlike azimuth or spacing, a coordinate origin is always
    # an arbitrary, legitimate choice. See ADR-016.
    return 0.0, GeometryProvenance.INDEX_SPACE


def _derive_origin_and_azimuth_from_real_coordinates(
    dataset: GPRDataset,
) -> tuple[float | None, float | None, float | None, CrossTrackDirection, tuple[str, ...]]:
    """origin_x/origin_y/azimuth_deg/cross_track_direction, derived from real per-trace x/y.

    Only called when ``dataset.has_geolocation``. Returns ``(None, None,
    None, UNKNOWN, ())`` if there are too few finite points to derive a
    direction from (a single trace, or first/last trace centers coinciding).
    """
    assert dataset.x is not None and dataset.y is not None
    x, y = dataset.x, dataset.y
    warnings: list[str] = []
    trace_count, channel_count = x.shape

    finite_first = np.isfinite(x[0, :]) & np.isfinite(y[0, :])
    finite_last = np.isfinite(x[-1, :]) & np.isfinite(y[-1, :])
    if trace_count < 2 or not finite_first.any() or not finite_last.any():
        return None, None, None, CrossTrackDirection.UNKNOWN, ()

    origin_x = float(np.mean(x[0, finite_first]))
    origin_y = float(np.mean(y[0, finite_first]))

    start_x, start_y = origin_x, origin_y
    end_x, end_y = float(np.mean(x[-1, finite_last])), float(np.mean(y[-1, finite_last]))
    along_dx, along_dy = end_x - start_x, end_y - start_y
    along_track_length = math.hypot(along_dx, along_dy)
    if along_track_length == 0.0:
        warnings.append("Along-track direction could not be derived: first and last trace centers coincide.")
        return origin_x, origin_y, None, CrossTrackDirection.UNKNOWN, tuple(warnings)

    # Azimuth convention: degrees clockwise from grid north (see ADR-016) --
    # atan2(east_component, north_component).
    azimuth_deg = math.degrees(math.atan2(along_dx, along_dy)) % 360.0
    warnings.append(
        "Azimuth is derived as the single net direction from the first to the last trace "
        "center -- an average over the whole profile, not a per-segment heading."
    )

    cross_track_direction = CrossTrackDirection.UNKNOWN
    if channel_count >= 2:
        finite_channels = (
            np.isfinite(x[:, 0]) & np.isfinite(y[:, 0]) & np.isfinite(x[:, -1]) & np.isfinite(y[:, -1])
        )
        if finite_channels.any():
            cross_dx = float(np.mean(x[finite_channels, -1] - x[finite_channels, 0]))
            cross_dy = float(np.mean(y[finite_channels, -1] - y[finite_channels, 0]))
            if cross_dx != 0.0 or cross_dy != 0.0:
                # Along-track unit vector (sin, cos) in (E, N); "right" of it
                # is (cos, -sin) -- see ADR-016 / module docstring formula.
                along_unit_e = along_dx / along_track_length
                along_unit_n = along_dy / along_track_length
                right_unit_e = along_unit_n
                right_unit_n = -along_unit_e
                # Projection of the real cross-track vector onto the "right"
                # unit vector: positive => channels ascend to the right.
                projection = cross_dx * right_unit_e + cross_dy * right_unit_n
                cross_track_direction = (
                    CrossTrackDirection.CHANNEL_ASCENDING_RIGHT
                    if projection >= 0
                    else CrossTrackDirection.CHANNEL_ASCENDING_LEFT
                )

    return origin_x, origin_y, azimuth_deg, cross_track_direction, tuple(warnings)


def _build_local_coordinates(
    trace_count: int,
    channel_count: int,
    trace_spacing_m: float | None,
    channel_spacing_m: float | None,
    channel_zero_offset_m: float,
) -> tuple[np.ndarray, np.ndarray, CoordinateMode]:
    if trace_spacing_m is not None and channel_spacing_m is not None:
        along_track = np.arange(trace_count, dtype=np.float64) * trace_spacing_m
        cross_track = np.arange(channel_count, dtype=np.float64) * channel_spacing_m + channel_zero_offset_m
        return along_track, cross_track, CoordinateMode.LOCAL_METRIC
    along_track = np.arange(trace_count, dtype=np.float64)
    cross_track = np.arange(channel_count, dtype=np.float64)
    return along_track, cross_track, CoordinateMode.INDEX


def resolve_survey_geometry(
    dataset: GPRDataset,
    overrides: GeometryOverrides | None = None,
    *,
    geometry_revision: int = 0,
) -> GeometryResolution:
    """Resolve everything Sprint 3D-0 needs to know about ``dataset``'s survey geometry.

    Never mutates ``dataset``. ``overrides`` (if any) must already be
    ``GeometryOverrides.validate()``-clean -- this function does not
    re-validate; it assumes the caller (the GUI's Apply Geometry handler)
    already rejected an invalid override before calling this.
    """
    overrides = overrides or GeometryOverrides()
    trace_count, channel_count, _samples_count = dataset.shape
    provenance: dict[str, GeometryProvenance] = {}
    warnings: list[str] = []
    errors: list[str] = []

    trace_spacing_m, trace_spacing_provenance, spacing_warnings = _resolve_trace_spacing(dataset, overrides)
    provenance["trace_spacing_m"] = trace_spacing_provenance
    warnings.extend(spacing_warnings)

    channel_spacing_m, channel_spacing_provenance = _resolve_channel_spacing(dataset, overrides)
    provenance["channel_spacing_m"] = channel_spacing_provenance

    channel_zero_offset_m, channel_zero_offset_provenance = _resolve_channel_zero_offset(overrides)
    provenance["channel_zero_offset_m"] = channel_zero_offset_provenance

    along_track_coordinates, cross_track_offsets, coordinate_mode = _build_local_coordinates(
        trace_count, channel_count, trace_spacing_m, channel_spacing_m, channel_zero_offset_m
    )
    provenance["along_track_coordinates"] = (
        trace_spacing_provenance
        if coordinate_mode is CoordinateMode.LOCAL_METRIC
        else GeometryProvenance.INDEX_SPACE
    )
    provenance["cross_track_offsets"] = (
        channel_spacing_provenance
        if coordinate_mode is CoordinateMode.LOCAL_METRIC
        else GeometryProvenance.INDEX_SPACE
    )

    crs_identifier, crs_provenance = _normalize_crs(dataset, overrides)
    provenance["crs_identifier"] = crs_provenance

    x_coordinates: np.ndarray | None = None
    y_coordinates: np.ndarray | None = None
    origin_x = overrides.origin_x
    origin_y = overrides.origin_y
    azimuth_deg = overrides.azimuth_deg
    cross_track_direction = overrides.cross_track_direction or CrossTrackDirection.UNKNOWN
    origin_provenance = (
        GeometryProvenance.USER_SUPPLIED if overrides.origin_x is not None else GeometryProvenance.MISSING
    )
    azimuth_provenance = (
        GeometryProvenance.USER_SUPPLIED if overrides.azimuth_deg is not None else GeometryProvenance.MISSING
    )
    cross_track_direction_provenance = (
        GeometryProvenance.USER_SUPPLIED
        if overrides.cross_track_direction is not None
        else GeometryProvenance.MISSING
    )

    if dataset.has_geolocation:
        # Real per-(trace, channel) coordinates already exist -- use them
        # directly. No azimuth/origin/cross-track-direction reconstruction
        # is needed or performed; those three are instead *derived*, purely
        # for display/plan-view-arrow purposes, from the same real
        # coordinates (see ADR-016's "why two global paths" rationale).
        assert dataset.x is not None and dataset.y is not None
        x_coordinates = dataset.x
        y_coordinates = dataset.y
        coordinate_mode = CoordinateMode.GLOBAL_PROJECTED
        provenance["x_coordinates"] = GeometryProvenance.FILE_METADATA
        provenance["y_coordinates"] = GeometryProvenance.FILE_METADATA

        if overrides.origin_x is None or overrides.origin_y is None:
            (derived_origin_x, derived_origin_y, derived_azimuth, derived_direction, derive_warnings) = (
                _derive_origin_and_azimuth_from_real_coordinates(dataset)
            )
            warnings.extend(derive_warnings)
            if overrides.origin_x is None and derived_origin_x is not None:
                origin_x = derived_origin_x
                origin_provenance = GeometryProvenance.DERIVED
            if overrides.origin_y is None and derived_origin_y is not None:
                origin_y = derived_origin_y
                origin_provenance = GeometryProvenance.DERIVED
            if overrides.azimuth_deg is None and derived_azimuth is not None:
                azimuth_deg = derived_azimuth
                azimuth_provenance = GeometryProvenance.DERIVED
            if (
                overrides.cross_track_direction is None
                and derived_direction is not CrossTrackDirection.UNKNOWN
            ):
                cross_track_direction = derived_direction
                cross_track_direction_provenance = GeometryProvenance.DERIVED
    elif (
        coordinate_mode is CoordinateMode.LOCAL_METRIC
        and overrides.origin_x is not None
        and overrides.origin_y is not None
        and overrides.azimuth_deg is not None
        and overrides.cross_track_direction is not None
        and overrides.cross_track_direction is not CrossTrackDirection.UNKNOWN
        and crs_identifier is not None
    ):
        # No real per-trace coordinates exist -- reconstruct a global grid
        # from local geometry, but only when every required input is a
        # real, user-confirmed value (see rules in ADR-016 / Sprint 3D-0
        # spec section 9). An unknown cross-track direction always blocks
        # this path; there is no fallback guess.
        x_coordinates, y_coordinates = project_global_from_local(
            along_track_coordinates,
            cross_track_offsets,
            overrides.origin_x,
            overrides.origin_y,
            overrides.azimuth_deg,
            overrides.cross_track_direction,
        )
        coordinate_mode = CoordinateMode.GLOBAL_PROJECTED
        provenance["x_coordinates"] = GeometryProvenance.USER_SUPPLIED
        provenance["y_coordinates"] = GeometryProvenance.USER_SUPPLIED
    else:
        provenance["x_coordinates"] = GeometryProvenance.MISSING
        provenance["y_coordinates"] = GeometryProvenance.MISSING

    provenance["origin_x"] = origin_provenance
    provenance["origin_y"] = origin_provenance
    provenance["azimuth_deg"] = azimuth_provenance
    provenance["cross_track_direction"] = cross_track_direction_provenance

    geometry = SurveyGeometry(
        trace_count=trace_count,
        channel_count=channel_count,
        coordinate_mode=coordinate_mode,
        along_track_coordinates=along_track_coordinates,
        cross_track_offsets=cross_track_offsets,
        trace_spacing_m=trace_spacing_m,
        channel_spacing_m=channel_spacing_m,
        channel_zero_offset_m=channel_zero_offset_m,
        origin_x=origin_x,
        origin_y=origin_y,
        azimuth_deg=azimuth_deg,
        cross_track_direction=cross_track_direction,
        crs_identifier=crs_identifier,
        x_coordinates=x_coordinates,
        y_coordinates=y_coordinates,
        provenance=provenance,
        warnings=tuple(warnings),
        errors=tuple(errors),
        geometry_revision=geometry_revision,
    )

    readiness = _compute_readiness(dataset, geometry)
    source_summary = {
        "has_geolocation": dataset.has_geolocation,
        "spatial_reference": dataset.metadata.get("spatial_reference"),
        "axis_order": (dataset.metadata.get("dimensions") or {}).get("axis_order"),
    }
    return GeometryResolution(geometry=geometry, readiness=readiness, source_summary=source_summary)


def _compute_readiness(dataset: GPRDataset, geometry: SurveyGeometry) -> ReadinessGates:
    index_blocking: list[str] = []
    if geometry.trace_count <= 0 or geometry.channel_count <= 0:
        index_blocking.append("Dataset has zero traces or zero channels.")
    index_view_ready = ReadinessStatus(ready=not index_blocking, blocking_issues=tuple(index_blocking))

    local_blocking: list[str] = []
    if geometry.along_track_coordinates is None or not np.all(np.isfinite(geometry.along_track_coordinates)):
        local_blocking.append("Along-track coordinates are missing or non-finite.")
    if geometry.cross_track_offsets is None or not np.all(np.isfinite(geometry.cross_track_offsets)):
        local_blocking.append("Cross-track offsets are missing or non-finite.")
    if geometry.coordinate_mode is CoordinateMode.INDEX:
        local_blocking.append("No trace/channel spacing is known -- coordinates are index-only.")
    local_warnings: list[str] = [
        "This gate reports readiness for the DERIVED, always-rectilinear-by-construction s/c "
        "parameter grid -- it does not claim the real acquisition is itself rectilinear (see "
        "rectilinear_cscan_ready)."
    ]
    if (
        not local_blocking
        and geometry.along_track_coordinates is not None
        and geometry.along_track_coordinates.size >= 2
    ):
        deltas = np.diff(geometry.along_track_coordinates)
        if not (np.all(deltas > 0) or np.all(deltas < 0)):
            local_warnings.append("Along-track coordinates are not monotonic (possible direction reversal).")
    local_parameter_grid_ready = ReadinessStatus(
        ready=not local_blocking, blocking_issues=tuple(local_blocking), warnings=tuple(local_warnings)
    )

    grid_regularity = assess_grid_regularity(geometry)

    actual_blocking: list[str] = []
    if geometry.x_coordinates is None or geometry.y_coordinates is None:
        actual_blocking.append("No real per-(trace, channel) X/Y coordinates exist.")
    elif not (np.all(np.isfinite(geometry.x_coordinates)) and np.all(np.isfinite(geometry.y_coordinates))):
        actual_blocking.append("Real X/Y coordinates contain non-finite values.")
    actual_xy_point_grid_ready = ReadinessStatus(
        ready=not actual_blocking, blocking_issues=tuple(actual_blocking)
    )

    rectilinear_blocking: list[str] = []
    if not local_parameter_grid_ready.ready:
        rectilinear_blocking.append("Local parameter grid is not ready.")
    if grid_regularity.actual_point_grid_available:
        if grid_regularity.sampling_regular is False:
            rectilinear_blocking.append("Real acquisition sampling is not regular (see grid_regularity).")
        if grid_regularity.rectilinear_fit_acceptable is False:
            rectilinear_blocking.append(
                "Real acquisition grid does not fit a single-origin, single-azimuth rectilinear "
                "reconstruction within tolerance (see grid_regularity)."
            )
    rectilinear_cscan_ready = ReadinessStatus(
        ready=not rectilinear_blocking,
        blocking_issues=tuple(rectilinear_blocking),
        warnings=grid_regularity.warnings if grid_regularity.actual_point_grid_available else (),
    )

    global_blocking: list[str] = list(actual_xy_point_grid_ready.blocking_issues)
    if geometry.crs_identifier is None:
        global_blocking.append("No CRS/EPSG identifier is known.")
    global_warnings: list[str] = []
    if geometry.crs_identifier is not None:
        # "Ready" here means a computationally usable actual X/Y point grid
        # plus a declared CRS -- never a claim that the declared CRS is the
        # correct authority code for this survey's real-world location (see
        # ISSUE-001 / ADR-016's CrsValidationStatus), and never a claim that
        # the grid is rectilinear (see rectilinear_cscan_ready, a separate
        # gate). This warning is unconditional whenever a CRS is present,
        # since this sprint performs no authority/network check.
        global_warnings.append(
            f"CRS '{geometry.crs_identifier}' is declared but not authority-verified "
            "(see SurveyGeometry.crs_validation_status)."
        )
    global_cscan_ready = ReadinessStatus(
        ready=not global_blocking, blocking_issues=tuple(global_blocking), warnings=tuple(global_warnings)
    )

    time_blocking: list[str] = []
    time_ns = dataset.time_ns
    if time_ns is None or time_ns.size == 0 or not np.all(np.isfinite(time_ns)):
        time_blocking.append("time_ns axis is missing or non-finite.")
    elif time_ns.size >= 2 and not np.all(np.diff(time_ns) > 0):
        time_blocking.append("time_ns axis is not strictly increasing.")
    if not rectilinear_cscan_ready.ready:
        time_blocking.append("Rectilinear C-scan geometry is not ready.")
    time_volume_ready = ReadinessStatus(
        ready=not time_blocking,
        blocking_issues=tuple(time_blocking),
        warnings=(
            "This gate reports readiness for a RECTILINEAR time volume specifically (a regular "
            "(nu, nv, nsamples) array). Readiness for a time representation on the actual/"
            "curvilinear X/Y point grid instead depends on actual_xy_point_grid_ready, reported "
            "separately.",
        ),
    )

    depth_volume_ready = ReadinessStatus(
        ready=False,
        blocking_issues=(
            "Depth-domain volumes are out of scope for Sprint 3D-0 -- no propagation velocity has "
            "been explicitly confirmed by the user (see ADR-016 / 3D_Volume_Data_Model.md).",
        ),
    )

    return ReadinessGates(
        index_view_ready=index_view_ready,
        local_parameter_grid_ready=local_parameter_grid_ready,
        rectilinear_cscan_ready=rectilinear_cscan_ready,
        actual_xy_point_grid_ready=actual_xy_point_grid_ready,
        global_cscan_ready=global_cscan_ready,
        time_volume_ready=time_volume_ready,
        depth_volume_ready=depth_volume_ready,
    )
