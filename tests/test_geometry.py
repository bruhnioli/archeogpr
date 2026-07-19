"""Sprint 3D-0 domain tests for archaeogpr.geometry -- Qt-free, no PySide6 import anywhere.

Real per-trace geolocation is exercised via ``ogpr_builder`` -> ``read_ogpr``
(the synthetic ``.ogpr`` bytes builder already includes a real
``Sample Geolocations`` block, EPSG:32632, matching the real
``Swath003_Array02.ogpr`` file's own CRS -- see ``tests/conftest.py``).
No-geolocation cases use ``dataset_factory`` (``x=None``/``y=None`` by
design, see its docstring).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace as dc_replace
from pathlib import Path

import numpy as np
import pytest

from archaeogpr.geometry import (
    CoordinateMode,
    CrossTrackDirection,
    CrsValidationStatus,
    GeometryOverrides,
    GeometryProvenance,
    resolve_survey_geometry,
)
from archaeogpr.geometry.export import build_geometry_report, export_geometry_report
from archaeogpr.geometry.regularity import (
    DIRECTION_STD_WARNING_THRESHOLD_DEG,
    SPACING_CV_WARNING_THRESHOLD,
    assess_grid_regularity,
)
from archaeogpr.geometry.summary import compute_geometry_summary
from archaeogpr.io.ogpr_reader import read_ogpr

# -- A. Index / local / global coordinate construction -----------------------


def test_index_geometry_produces_correct_shape(dataset_factory):
    dataset = dataset_factory(slices_count=6, channels_count=4, metadata={})
    resolution = resolve_survey_geometry(dataset)
    geometry = resolution.geometry
    assert geometry.coordinate_mode is CoordinateMode.INDEX
    assert geometry.along_track_coordinates.shape == (6,)
    assert geometry.cross_track_offsets.shape == (4,)
    assert np.array_equal(geometry.along_track_coordinates, np.arange(6, dtype=np.float64))
    assert np.array_equal(geometry.cross_track_offsets, np.arange(4, dtype=np.float64))


def test_index_geometry_not_labeled_as_meters(dataset_factory):
    dataset = dataset_factory(metadata={})
    geometry = resolve_survey_geometry(dataset).geometry
    assert geometry.coordinate_mode is CoordinateMode.INDEX
    assert geometry.provenance_for("along_track_coordinates") is GeometryProvenance.INDEX_SPACE
    assert geometry.provenance_for("cross_track_offsets") is GeometryProvenance.INDEX_SPACE


def test_metric_spacing_produces_correct_along_cross_coordinates(dataset_factory):
    dataset = dataset_factory(slices_count=5, channels_count=3, metadata={})
    overrides = GeometryOverrides(trace_spacing_m=0.5, channel_spacing_m=0.2, channel_zero_offset_m=1.0)
    geometry = resolve_survey_geometry(dataset, overrides).geometry
    assert geometry.coordinate_mode is CoordinateMode.LOCAL_METRIC
    assert np.allclose(geometry.along_track_coordinates, np.arange(5) * 0.5)
    assert np.allclose(geometry.cross_track_offsets, np.arange(3) * 0.2 + 1.0)


def test_negative_or_zero_spacing_is_rejected():
    assert GeometryOverrides(trace_spacing_m=-1.0).validate() != ()
    assert GeometryOverrides(trace_spacing_m=0.0).validate() != ()
    assert GeometryOverrides(channel_spacing_m=-0.01).validate() != ()
    assert GeometryOverrides(channel_spacing_m=0.0).validate() != ()


def test_non_finite_spacing_is_rejected():
    assert GeometryOverrides(trace_spacing_m=float("nan")).validate() != ()
    assert GeometryOverrides(trace_spacing_m=float("inf")).validate() != ()
    assert GeometryOverrides(azimuth_deg=float("nan")).validate() != ()
    assert GeometryOverrides(origin_x=float("inf")).validate() != ()


# -- B. Provenance / override priority / index fallback ----------------------


def test_field_provenance_recorded_correctly(ogpr_builder, tmp_path):
    path = tmp_path / "geo.ogpr"
    path.write_bytes(ogpr_builder(slices_count=5, channels_count=3))
    dataset = read_ogpr(path)
    geometry = resolve_survey_geometry(dataset).geometry
    assert geometry.provenance_for("trace_spacing_m") is GeometryProvenance.FILE_METADATA
    assert geometry.provenance_for("channel_spacing_m") is GeometryProvenance.DERIVED
    assert geometry.provenance_for("x_coordinates") is GeometryProvenance.FILE_METADATA
    assert geometry.provenance_for("y_coordinates") is GeometryProvenance.FILE_METADATA
    assert geometry.provenance_for("crs_identifier") is GeometryProvenance.FILE_METADATA
    assert geometry.provenance_for("nonexistent_field") is GeometryProvenance.MISSING


def test_user_override_takes_precedence_over_file_metadata(ogpr_builder, tmp_path):
    path = tmp_path / "geo.ogpr"
    path.write_bytes(ogpr_builder(slices_count=5, channels_count=3))
    dataset = read_ogpr(path)
    overrides = GeometryOverrides(trace_spacing_m=9.999)
    geometry = resolve_survey_geometry(dataset, overrides).geometry
    assert geometry.trace_spacing_m == pytest.approx(9.999)
    assert geometry.provenance_for("trace_spacing_m") is GeometryProvenance.USER_SUPPLIED


def test_missing_metadata_produces_index_fallback(dataset_factory):
    dataset = dataset_factory(metadata={})
    geometry = resolve_survey_geometry(dataset).geometry
    assert geometry.provenance_for("trace_spacing_m") is GeometryProvenance.MISSING
    assert geometry.provenance_for("channel_spacing_m") is GeometryProvenance.MISSING
    assert geometry.coordinate_mode is CoordinateMode.INDEX


# -- C. Immutability -----------------------------------------------------------


def test_raw_dataset_unchanged_by_resolution(ogpr_builder, tmp_path):
    path = tmp_path / "geo.ogpr"
    path.write_bytes(ogpr_builder())
    dataset = read_ogpr(path)
    x_before = dataset.x.copy()
    metadata_before = dict(dataset.metadata)
    resolve_survey_geometry(dataset)
    assert np.array_equal(dataset.x, x_before)
    assert dict(dataset.metadata) == metadata_before


def test_input_coordinate_arrays_unchanged(ogpr_builder, tmp_path):
    path = tmp_path / "geo.ogpr"
    path.write_bytes(ogpr_builder())
    dataset = read_ogpr(path)
    x_copy, y_copy = dataset.x.copy(), dataset.y.copy()
    geometry = resolve_survey_geometry(dataset).geometry
    assert np.array_equal(dataset.x, x_copy)
    assert np.array_equal(dataset.y, y_copy)
    # x_coordinates is the same real data, not a mutated copy.
    assert np.array_equal(geometry.x_coordinates, x_copy)


def test_output_arrays_are_read_only(ogpr_builder, tmp_path):
    path = tmp_path / "geo.ogpr"
    path.write_bytes(ogpr_builder())
    dataset = read_ogpr(path)
    geometry = resolve_survey_geometry(dataset).geometry
    for array in (
        geometry.along_track_coordinates,
        geometry.cross_track_offsets,
        geometry.x_coordinates,
        geometry.y_coordinates,
    ):
        assert array.flags.writeable is False
        index = 0 if array.ndim == 1 else (0, 0)
        with pytest.raises(ValueError, match="read-only"):
            array[index] = 0.0


# -- D. Global transform conventions ------------------------------------------


def test_global_transform_azimuth_zero(dataset_factory):
    dataset = dataset_factory(slices_count=4, channels_count=3, metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=1.0,
        channel_spacing_m=1.0,
        origin_x=100.0,
        origin_y=200.0,
        azimuth_deg=0.0,
        cross_track_direction=CrossTrackDirection.CHANNEL_ASCENDING_RIGHT,
        crs_identifier="EPSG:32632",
    )
    geometry = resolve_survey_geometry(dataset, overrides).geometry
    assert geometry.x_coordinates[0, 0] == pytest.approx(100.0)
    assert geometry.y_coordinates[0, 0] == pytest.approx(200.0)
    # azimuth 0 (due north), right: increasing channel -> +east, increasing trace -> +north
    assert geometry.x_coordinates[0, 1] == pytest.approx(101.0)
    assert geometry.y_coordinates[1, 0] == pytest.approx(201.0)


def test_global_transform_azimuth_ninety(dataset_factory):
    dataset = dataset_factory(slices_count=4, channels_count=3, metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=1.0,
        channel_spacing_m=1.0,
        origin_x=0.0,
        origin_y=0.0,
        azimuth_deg=90.0,
        cross_track_direction=CrossTrackDirection.CHANNEL_ASCENDING_RIGHT,
        crs_identifier="EPSG:32632",
    )
    geometry = resolve_survey_geometry(dataset, overrides).geometry
    # azimuth 90 (due east), right of eastward travel is south: increasing
    # trace -> +east, increasing channel -> -north (south).
    assert geometry.x_coordinates[1, 0] == pytest.approx(1.0)
    assert geometry.y_coordinates[1, 0] == pytest.approx(0.0, abs=1e-9)
    assert geometry.y_coordinates[0, 1] == pytest.approx(-1.0)
    assert geometry.x_coordinates[0, 1] == pytest.approx(0.0, abs=1e-9)


def test_right_starboard_cross_track_transform(dataset_factory):
    dataset = dataset_factory(slices_count=2, channels_count=2, metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=1.0,
        channel_spacing_m=1.0,
        origin_x=0.0,
        origin_y=0.0,
        azimuth_deg=45.0,
        cross_track_direction=CrossTrackDirection.CHANNEL_ASCENDING_RIGHT,
        crs_identifier="EPSG:32632",
    )
    geometry = resolve_survey_geometry(dataset, overrides).geometry
    theta = math.radians(45.0)
    expected_x = math.cos(theta)  # c=1, s=0, right: x = c*cos(theta)
    expected_y = -math.sin(theta)  # y = -c*sin(theta)
    assert geometry.x_coordinates[0, 1] == pytest.approx(expected_x)
    assert geometry.y_coordinates[0, 1] == pytest.approx(expected_y)


def test_left_port_cross_track_transform(dataset_factory):
    dataset = dataset_factory(slices_count=2, channels_count=2, metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=1.0,
        channel_spacing_m=1.0,
        origin_x=0.0,
        origin_y=0.0,
        azimuth_deg=45.0,
        cross_track_direction=CrossTrackDirection.CHANNEL_ASCENDING_LEFT,
        crs_identifier="EPSG:32632",
    )
    geometry = resolve_survey_geometry(dataset, overrides).geometry
    theta = math.radians(45.0)
    expected_x = -math.cos(theta)  # left: cross-track sign flipped
    expected_y = math.sin(theta)
    assert geometry.x_coordinates[0, 1] == pytest.approx(expected_x)
    assert geometry.y_coordinates[0, 1] == pytest.approx(expected_y)


def test_unknown_cross_track_direction_rejects_global_grid(dataset_factory):
    dataset = dataset_factory(metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=1.0,
        channel_spacing_m=1.0,
        origin_x=0.0,
        origin_y=0.0,
        azimuth_deg=0.0,
        cross_track_direction=None,  # UNKNOWN
        crs_identifier="EPSG:32632",
    )
    geometry = resolve_survey_geometry(dataset, overrides).geometry
    assert geometry.x_coordinates is None
    assert geometry.y_coordinates is None
    assert geometry.coordinate_mode is not CoordinateMode.GLOBAL_PROJECTED


# -- E. Readiness gates --------------------------------------------------------


def test_missing_crs_blocks_global_readiness(dataset_factory):
    dataset = dataset_factory(metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=1.0,
        channel_spacing_m=1.0,
        origin_x=0.0,
        origin_y=0.0,
        azimuth_deg=0.0,
        cross_track_direction=CrossTrackDirection.CHANNEL_ASCENDING_RIGHT,
        crs_identifier=None,
    )
    readiness = resolve_survey_geometry(dataset, overrides).readiness
    assert not readiness.global_cscan_ready.ready
    assert any("CRS" in issue for issue in readiness.global_cscan_ready.blocking_issues)


# -- E2. CRS validation status (Sprint 3D-0 pre-commit audit) ------------------


def test_file_metadata_crs_is_declared_unverified(ogpr_builder, tmp_path):
    path = tmp_path / "geo.ogpr"
    path.write_bytes(ogpr_builder(slices_count=5, channels_count=3))
    dataset = read_ogpr(path)
    geometry = resolve_survey_geometry(dataset).geometry
    assert geometry.provenance_for("crs_identifier") is GeometryProvenance.FILE_METADATA
    assert geometry.crs_validation_status is CrsValidationStatus.DECLARED_UNVERIFIED


def test_user_supplied_crs_is_user_supplied_unverified(dataset_factory):
    dataset = dataset_factory(metadata={})
    overrides = GeometryOverrides(crs_identifier="EPSG:4326")
    geometry = resolve_survey_geometry(dataset, overrides).geometry
    assert geometry.provenance_for("crs_identifier") is GeometryProvenance.USER_SUPPLIED
    assert geometry.crs_validation_status is CrsValidationStatus.USER_SUPPLIED_UNVERIFIED


def test_missing_crs_status_and_blocks_global_readiness(dataset_factory):
    dataset = dataset_factory(metadata={})
    resolution = resolve_survey_geometry(dataset)
    assert resolution.geometry.crs_validation_status is CrsValidationStatus.MISSING
    assert not resolution.readiness.global_cscan_ready.ready


def test_unverified_crs_produces_global_readiness_warning(dataset_factory):
    dataset = dataset_factory(metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=1.0,
        channel_spacing_m=1.0,
        origin_x=0.0,
        origin_y=0.0,
        azimuth_deg=0.0,
        cross_track_direction=CrossTrackDirection.CHANNEL_ASCENDING_RIGHT,
        crs_identifier="EPSG:32632",
    )
    readiness = resolve_survey_geometry(dataset, overrides).readiness
    assert readiness.global_cscan_ready.ready
    assert any(
        "unverified" in w.lower() or "not authority-verified" in w
        for w in readiness.global_cscan_ready.warnings
    )


def test_export_json_includes_crs_validation_status(dataset_factory):
    dataset = dataset_factory(metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=1.0,
        channel_spacing_m=1.0,
        origin_x=0.0,
        origin_y=0.0,
        azimuth_deg=0.0,
        cross_track_direction=CrossTrackDirection.CHANNEL_ASCENDING_RIGHT,
        crs_identifier="EPSG:32632",
    )
    resolution = resolve_survey_geometry(dataset, overrides)
    payload = build_geometry_report(resolution, dataset, __file__)
    assert payload["resolved_fields"]["crs_validation_status"] == "user_supplied_unverified"


def test_local_readiness_computed_correctly(dataset_factory):
    index_only = resolve_survey_geometry(dataset_factory(metadata={})).readiness
    assert not index_only.local_parameter_grid_ready.ready

    metric = resolve_survey_geometry(
        dataset_factory(metadata={}), GeometryOverrides(trace_spacing_m=1.0, channel_spacing_m=1.0)
    ).readiness
    assert metric.local_parameter_grid_ready.ready


def test_time_volume_readiness_validated_against_time_ns(dataset_factory):
    # time_volume_ready also requires local_cscan_ready (see spec section 10)
    # -- supply valid local spacing via overrides so this test isolates the
    # time_ns check itself, rather than failing on the (separately-tested)
    # local-geometry precondition.
    local_overrides = GeometryOverrides(trace_spacing_m=1.0, channel_spacing_m=1.0)

    good = dataset_factory(samples_count=20, metadata={})
    assert resolve_survey_geometry(good, local_overrides).readiness.time_volume_ready.ready

    bad_time_ns = np.arange(20, dtype=np.float64)
    bad_time_ns[5], bad_time_ns[6] = bad_time_ns[6], bad_time_ns[5]  # break monotonicity
    bad = dataset_factory(samples_count=20, time_ns=bad_time_ns, metadata={})
    readiness = resolve_survey_geometry(bad, local_overrides).readiness
    assert not readiness.time_volume_ready.ready
    assert any("time_ns" in issue for issue in readiness.time_volume_ready.blocking_issues)


def test_depth_volume_readiness_always_false(ogpr_builder, tmp_path, dataset_factory):
    path = tmp_path / "geo.ogpr"
    path.write_bytes(ogpr_builder())
    real_dataset = read_ogpr(path)
    assert resolve_survey_geometry(real_dataset).readiness.depth_volume_ready.ready is False

    synthetic = dataset_factory(metadata={})
    readiness = resolve_survey_geometry(synthetic).readiness
    assert readiness.depth_volume_ready.ready is False
    assert readiness.depth_volume_ready.blocking_issues


# -- F. Coordinate quality detection (summary) --------------------------------


def test_duplicate_coordinate_detection(dataset_factory):
    dataset = dataset_factory(slices_count=3, channels_count=2, metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=1.0,
        channel_spacing_m=1.0,
        origin_x=0.0,
        origin_y=0.0,
        azimuth_deg=0.0,
        cross_track_direction=CrossTrackDirection.CHANNEL_ASCENDING_RIGHT,
        crs_identifier="EPSG:32632",
    )
    geometry = resolve_survey_geometry(dataset, overrides).geometry
    summary_clean = compute_geometry_summary(geometry)
    assert summary_clean.duplicate_coordinate_count == 0

    duplicated_x = geometry.x_coordinates.copy()
    duplicated_x.setflags(write=True)
    duplicated_x[1, 0] = duplicated_x[0, 0]  # force a duplicate (E, N) point
    duplicated_y = geometry.y_coordinates.copy()
    duplicated_y.setflags(write=True)
    duplicated_y[1, 0] = duplicated_y[0, 0]
    duplicated_geometry = dc_replace(geometry, x_coordinates=duplicated_x, y_coordinates=duplicated_y)
    summary_dup = compute_geometry_summary(duplicated_geometry)
    assert summary_dup.duplicate_coordinate_count == 1


def test_non_finite_coordinate_detection(dataset_factory):
    dataset = dataset_factory(slices_count=3, channels_count=2, metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=1.0,
        channel_spacing_m=1.0,
        origin_x=0.0,
        origin_y=0.0,
        azimuth_deg=0.0,
        cross_track_direction=CrossTrackDirection.CHANNEL_ASCENDING_RIGHT,
        crs_identifier="EPSG:32632",
    )
    geometry = resolve_survey_geometry(dataset, overrides).geometry
    nan_x = geometry.x_coordinates.copy()
    nan_x.setflags(write=True)
    nan_x[2, 1] = float("nan")
    nan_geometry = dc_replace(geometry, x_coordinates=nan_x)
    summary = compute_geometry_summary(nan_geometry)
    assert summary.non_finite_coordinate_count == 1
    assert summary.invalid_point_count == 1
    assert summary.valid_point_count == geometry.trace_count * geometry.channel_count - 1


def _all_nan_geometry(dataset_factory):
    dataset = dataset_factory(slices_count=4, channels_count=3, metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=1.0,
        channel_spacing_m=1.0,
        origin_x=0.0,
        origin_y=0.0,
        azimuth_deg=0.0,
        cross_track_direction=CrossTrackDirection.CHANNEL_ASCENDING_RIGHT,
        crs_identifier="EPSG:32632",
    )
    geometry = resolve_survey_geometry(dataset, overrides).geometry
    all_nan = np.full(geometry.x_coordinates.shape, float("nan"))
    return dc_replace(geometry, x_coordinates=all_nan.copy(), y_coordinates=all_nan.copy())


def test_all_nan_coordinates_summary_produces_no_warning(dataset_factory):
    """A geometry whose X/Y coordinates are entirely non-finite must not make
    compute_geometry_summary() raise numpy's RuntimeWarning (all-NaN min/max)."""
    import warnings

    geometry = _all_nan_geometry(dataset_factory)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compute_geometry_summary(geometry)
    assert caught == []


def test_all_nan_coordinates_extents_are_unavailable(dataset_factory):
    geometry = _all_nan_geometry(dataset_factory)
    summary = compute_geometry_summary(geometry)
    assert summary.x_min is None
    assert summary.x_max is None
    assert summary.y_min is None
    assert summary.y_max is None
    assert summary.rectilinear_parameter_grid_area_m2 is None
    assert summary.approximate_ribbon_area_m2 is None
    assert summary.actual_polygon_area_m2 is None


def test_all_nan_coordinates_non_finite_count_correct(dataset_factory):
    geometry = _all_nan_geometry(dataset_factory)
    summary = compute_geometry_summary(geometry)
    total = geometry.trace_count * geometry.channel_count
    assert summary.non_finite_coordinate_count == total
    assert summary.invalid_point_count == total
    assert summary.valid_point_count == 0


# -- G2. Grid rectilinearity/regularity (Sprint 3D-0 pre-commit audit) ----------


def _global_geometry_with_xy(dataset_factory, x, y, trace_spacing=1.0, channel_spacing=1.0):
    """Build a GLOBAL_PROJECTED geometry whose x_coordinates/y_coordinates are exactly ``x``/``y``.

    ``azimuth_deg=90, CHANNEL_ASCENDING_LEFT`` is the specific convention
    under which the section-9 transform's along-track term lands entirely
    on X and its cross-track term lands entirely on Y (``E = E0 + s``,
    ``N = N0 + c`` -- verify via ``project_global_from_local`` with
    ``theta=90``: ``sin=1, cos=0``). This matches ``_straight_grid()``'s own
    convention (X varies by trace, Y varies by channel) so the
    rectilinear-fit reconstruction is actually comparable to the supplied
    ``x``/``y`` -- an azimuth/direction mismatch here would inject a
    spurious residual unrelated to whatever irregularity a given test is
    deliberately introducing.
    """
    trace_count, channel_count = x.shape
    dataset = dataset_factory(slices_count=trace_count, channels_count=channel_count, metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=trace_spacing,
        channel_spacing_m=channel_spacing,
        origin_x=float(x[0, 0]),
        origin_y=float(y[0, 0]),
        azimuth_deg=90.0,
        cross_track_direction=CrossTrackDirection.CHANNEL_ASCENDING_LEFT,
        crs_identifier="EPSG:32632",
    )
    geometry = resolve_survey_geometry(dataset, overrides).geometry
    return dc_replace(geometry, x_coordinates=x.copy(), y_coordinates=y.copy())


def _straight_grid(trace_count=20, channel_count=5):
    trace_idx = np.arange(trace_count, dtype=np.float64)
    channel_idx = np.arange(channel_count, dtype=np.float64)
    x = np.broadcast_to(trace_idx[:, None], (trace_count, channel_count)).copy()
    y = np.broadcast_to(channel_idx[None, :], (trace_count, channel_count)).copy()
    return x, y


def test_perfectly_rectilinear_global_grid_is_regular(dataset_factory):
    x, y = _straight_grid()
    geometry = _global_geometry_with_xy(dataset_factory, x, y)

    regularity = assess_grid_regularity(geometry)
    assert regularity.actual_point_grid_available is True
    assert regularity.sampling_regular is True
    assert regularity.direction_consistent is True
    assert regularity.rectilinear_fit_acceptable is True


def test_curved_track_produces_regularity_warning(dataset_factory):
    """A trace path that bends (a 90-degree arc) must be flagged via direction_std_deg.

    Sampling stays regular (constant step length/cross-channel spacing along
    the arc) -- only direction consistency and, consequently, rectilinear
    fit are affected. This is the exact scientific separation the pre-commit
    audit's second round requires: a curved-but-evenly-sampled survey is not
    the same failure mode as an unevenly-sampled one.
    """
    trace_count, channel_count = 20, 5
    theta = np.linspace(0, math.pi / 2, trace_count)
    radius = 10.0
    center_x, center_y = radius * np.cos(theta), radius * np.sin(theta)
    x = np.broadcast_to(center_x[:, None], (trace_count, channel_count)).copy()
    y = center_y[:, None] + np.arange(channel_count, dtype=np.float64)[None, :]
    geometry = _global_geometry_with_xy(dataset_factory, x, y)

    regularity = assess_grid_regularity(geometry)
    assert regularity.actual_point_grid_available is True
    assert regularity.sampling_regular is True
    assert regularity.direction_consistent is False
    assert regularity.rectilinear_fit_acceptable is False
    assert regularity.direction_std_deg > DIRECTION_STD_WARNING_THRESHOLD_DEG
    assert any("curves" in w for w in regularity.warnings)


def test_variable_channel_spacing_produces_regularity_warning(dataset_factory):
    x, _ = _straight_grid()
    irregular_offsets = np.array([0.0, 1.0, 1.05, 3.0, 3.02])
    y = np.broadcast_to(irregular_offsets[None, :], x.shape).copy()
    geometry = _global_geometry_with_xy(dataset_factory, x, y)

    regularity = assess_grid_regularity(geometry)
    assert regularity.actual_point_grid_available is True
    assert regularity.sampling_regular is False
    assert regularity.cross_channel_spacing_cv > SPACING_CV_WARNING_THRESHOLD
    assert any("Cross-channel spacing varies" in w for w in regularity.warnings)


def test_irregular_trace_spacing_produces_sampling_not_regular(dataset_factory):
    """Straight heading, but along-track step lengths vary -- a different failure mode than
    variable cross-channel spacing (both are sampling irregularities, but on different axes)."""
    trace_count, channel_count = 8, 4
    irregular_trace_positions = np.array([0.0, 1.0, 1.05, 3.0, 3.02, 5.0, 5.03, 7.0])
    x = np.broadcast_to(irregular_trace_positions[:, None], (trace_count, channel_count)).copy()
    y = np.broadcast_to(
        np.arange(channel_count, dtype=np.float64)[None, :], (trace_count, channel_count)
    ).copy()
    geometry = _global_geometry_with_xy(dataset_factory, x, y)

    regularity = assess_grid_regularity(geometry)
    assert regularity.actual_point_grid_available is True
    assert regularity.sampling_regular is False
    assert regularity.segment_length_cv > SPACING_CV_WARNING_THRESHOLD
    assert any("Along-track step length varies" in w for w in regularity.warnings)


def test_large_lateral_residual_blocks_rectilinear_readiness(dataset_factory):
    """A single, precisely-known lateral offset must (a) surface as exactly that residual,
    (b) report the correct residual/channel-spacing ratio, and (c) block
    rectilinear_cscan_ready -- not just assess_grid_regularity()'s own output."""
    from archaeogpr.geometry.resolve import _compute_readiness

    trace_count, channel_count = 10, 4
    channel_spacing = 1.0
    x, y = _straight_grid(trace_count=trace_count, channel_count=channel_count)
    y = y.copy()
    known_shift = 10.0 * channel_spacing
    y[5, :] += known_shift  # one trace's whole row, shifted by a known, large lateral amount
    geometry = _global_geometry_with_xy(
        dataset_factory, x, y, trace_spacing=1.0, channel_spacing=channel_spacing
    )
    dataset = dataset_factory(slices_count=trace_count, channels_count=channel_count, metadata={})

    regularity = assess_grid_regularity(geometry)
    assert regularity.residual_max_m == pytest.approx(known_shift, rel=1e-6)
    assert regularity.residual_max_over_channel_spacing == pytest.approx(
        known_shift / channel_spacing, rel=1e-6
    )
    assert regularity.rectilinear_fit_acceptable is False

    readiness = _compute_readiness(dataset, geometry)
    assert readiness.rectilinear_cscan_ready.ready is False
    assert any("does not fit" in issue for issue in readiness.rectilinear_cscan_ready.blocking_issues)


def test_regularity_check_never_replaces_actual_coordinates(dataset_factory):
    """assess_grid_regularity() must never mutate or replace geometry.x/y_coordinates."""
    x, y = _straight_grid()
    y = y + 0.37  # a small, otherwise-arbitrary real offset the check must not "correct"
    geometry = _global_geometry_with_xy(dataset_factory, x, y)
    before_x, before_y = geometry.x_coordinates.copy(), geometry.y_coordinates.copy()
    assess_grid_regularity(geometry)
    assert np.array_equal(geometry.x_coordinates, before_x)
    assert np.array_equal(geometry.y_coordinates, before_y)


def test_approximate_ribbon_area_reported_with_warning(dataset_factory):
    """A well-behaved (rectilinear-fit-acceptable) real grid still gets the ribbon area,
    always labeled as an approximation -- distinct from the exact parameter-grid area."""
    x, y = _straight_grid()
    geometry = _global_geometry_with_xy(dataset_factory, x, y)

    summary = compute_geometry_summary(geometry)
    assert summary.approximate_ribbon_area_m2 is not None
    assert summary.rectilinear_parameter_grid_area_m2 is not None
    assert any("approximate_ribbon_area_m2" in w and "approximation" in w for w in summary.warnings)


def test_derived_local_grid_provenance_matches_its_source_spacing(ogpr_builder, tmp_path):
    """along_track_coordinates/cross_track_offsets mirror trace_spacing_m/channel_spacing_m's
    OWN provenance -- they are not always uniformly "DERIVED"; for this real-geolocation
    fixture, trace_spacing_m happens to be FILE_METADATA and channel_spacing_m DERIVED."""
    path = tmp_path / "geo.ogpr"
    path.write_bytes(ogpr_builder(slices_count=5, channels_count=3))
    dataset = read_ogpr(path)
    geometry = resolve_survey_geometry(dataset).geometry
    assert geometry.provenance_for("along_track_coordinates") is GeometryProvenance.FILE_METADATA
    assert geometry.provenance_for("cross_track_offsets") is GeometryProvenance.DERIVED


def test_export_json_includes_separated_regularity_metrics(ogpr_builder, tmp_path):
    path = tmp_path / "geo.ogpr"
    path.write_bytes(ogpr_builder(slices_count=5, channels_count=3))
    dataset = read_ogpr(path)
    resolution = resolve_survey_geometry(dataset)
    payload = build_geometry_report(resolution, dataset, path)

    regularity_payload = payload["summary"]["grid_regularity"]
    for key in (
        "actual_point_grid_available",
        "sampling_regular",
        "direction_consistent",
        "rectilinear_fit_acceptable",
        "residual_max_m",
        "residual_max_over_channel_spacing",
    ):
        assert key in regularity_payload
    for key in (
        "rectilinear_parameter_grid_area_m2",
        "approximate_ribbon_area_m2",
        "actual_polygon_area_m2",
    ):
        assert key in payload["summary"]
    for key in ("local_parameter_grid_ready", "rectilinear_cscan_ready", "actual_xy_point_grid_ready"):
        assert key in payload["readiness"]


_REAL_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "Swath003_Array02.ogpr"


@pytest.mark.skipif(not _REAL_FILE.is_file(), reason=f"Real sample file not found at {_REAL_FILE}.")
def test_real_file_regularity_and_rectilinearity_consistent():
    """The real Swath003_Array02.ogpr file: excellent sampling/direction, but a
    genuinely non-rectilinear fit -- confirming the exact scientific separation this
    audit round exists to make (see ADR-016 addendum)."""
    dataset = read_ogpr(_REAL_FILE)
    resolution = resolve_survey_geometry(dataset)
    summary = compute_geometry_summary(resolution.geometry)
    reg = summary.grid_regularity

    assert reg.actual_point_grid_available is True
    assert reg.sampling_regular is True
    assert reg.direction_consistent is True
    assert reg.rectilinear_fit_acceptable is False
    assert reg.residual_max_over_channel_spacing > 1.0  # exceeds a full channel width

    assert resolution.readiness.local_parameter_grid_ready.ready is True
    assert resolution.readiness.rectilinear_cscan_ready.ready is False
    assert resolution.readiness.actual_xy_point_grid_ready.ready is True
    assert resolution.readiness.global_cscan_ready.ready is True

    assert summary.rectilinear_parameter_grid_area_m2 is None
    assert summary.approximate_ribbon_area_m2 is not None
    assert summary.actual_polygon_area_m2 is not None


def test_irregular_grid_footprint_area_not_reported(dataset_factory):
    x, _ = _straight_grid()
    irregular_offsets = np.array([0.0, 1.0, 1.05, 3.0, 3.02])
    y = np.broadcast_to(irregular_offsets[None, :], x.shape).copy()
    geometry = _global_geometry_with_xy(dataset_factory, x, y)

    summary = compute_geometry_summary(geometry)
    assert summary.rectilinear_parameter_grid_area_m2 is None
    assert any("rectilinear_parameter_grid_area_m2 is not reported" in w for w in summary.warnings)


def test_c_order_flatten_mapping_matches_trace_channel_indices(dataset_factory):
    """The C-scan contract: flattening x/y_coordinates in C-order must map
    flat index i = trace*channel_count + channel back to cell [trace, channel] --
    the same convention amplitudes.reshape(trace*channel, samples) would use."""
    x, y = _straight_grid(trace_count=7, channel_count=4)
    geometry = _global_geometry_with_xy(dataset_factory, x, y)
    trace_count, channel_count = geometry.trace_count, geometry.channel_count

    flat_x = geometry.x_coordinates.flatten(order="C")
    flat_y = geometry.y_coordinates.flatten(order="C")
    for trace in range(trace_count):
        for channel in range(channel_count):
            flat_index = trace * channel_count + channel
            assert flat_x[flat_index] == geometry.x_coordinates[trace, channel]
            assert flat_y[flat_index] == geometry.y_coordinates[trace, channel]


# -- G. JSON export -------------------------------------------------------------


def test_geometry_report_json_is_finite_and_serializable(dataset_factory):
    dataset = dataset_factory(slices_count=3, channels_count=2, metadata={})
    overrides = GeometryOverrides(
        trace_spacing_m=1.0,
        channel_spacing_m=1.0,
        origin_x=0.0,
        origin_y=0.0,
        azimuth_deg=0.0,
        cross_track_direction=CrossTrackDirection.CHANNEL_ASCENDING_RIGHT,
        crs_identifier="EPSG:32632",
    )
    resolution = resolve_survey_geometry(dataset, overrides)
    nan_x = resolution.geometry.x_coordinates.copy()
    nan_x.setflags(write=True)
    nan_x[0, 0] = float("nan")
    resolution = dc_replace(resolution, geometry=dc_replace(resolution.geometry, x_coordinates=nan_x))

    # dataset here is synthetic (dataset_factory), not backed by a real
    # source_path -- build_geometry_report only needs *a* Path for the
    # source_sha256 field, so we point it at a real, harmless file already
    # on disk (this test file itself) instead of inventing a fake path.
    payload = build_geometry_report(resolution, dataset, __file__)
    text = json.dumps(payload)  # must not raise, and must not embed NaN/Infinity
    assert "NaN" not in text
    assert "Infinity" not in text
    reloaded = json.loads(text)
    assert reloaded["x_coordinates"]["values"][0][0] is None


def test_export_records_source_ogpr_hash(ogpr_builder, tmp_path):
    ogpr_path = tmp_path / "geo.ogpr"
    raw_bytes = ogpr_builder()
    ogpr_path.write_bytes(raw_bytes)
    dataset = read_ogpr(ogpr_path)
    resolution = resolve_survey_geometry(dataset)

    report_path = tmp_path / "geo.geometry.json"
    export_geometry_report(resolution, dataset, ogpr_path, report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["source_sha256"] == hashlib.sha256(raw_bytes).hexdigest()


def test_export_does_not_modify_raw_file(ogpr_builder, tmp_path):
    ogpr_path = tmp_path / "geo.ogpr"
    raw_bytes = ogpr_builder()
    ogpr_path.write_bytes(raw_bytes)
    hash_before = hashlib.sha256(ogpr_path.read_bytes()).hexdigest()
    mtime_before = ogpr_path.stat().st_mtime_ns

    dataset = read_ogpr(ogpr_path)
    resolution = resolve_survey_geometry(dataset)
    report_path = tmp_path / "geo.geometry.json"
    export_geometry_report(resolution, dataset, ogpr_path, report_path)

    assert hashlib.sha256(ogpr_path.read_bytes()).hexdigest() == hash_before
    assert ogpr_path.stat().st_mtime_ns == mtime_before
