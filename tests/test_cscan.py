"""Sprint 3D-1 domain tests for archaeogpr.cscan -- Qt-free, no PySide6 import anywhere.

Real-file integration tests are skipif-gated on the bundled
``data/raw/Swath003_Array02.ogpr`` sample, matching ``tests/test_geometry.py``'s
convention exactly (a per-test decorator, not a module-level ``pytestmark``,
since most tests here use ``dataset_factory`` and must never be skipped).
"""

from __future__ import annotations

import json
import math
import warnings as warnings_module
from pathlib import Path

import numpy as np
import pytest

from archaeogpr.cscan import (
    CScanAggregation,
    CScanError,
    CScanGeometryView,
    CScanRequest,
    CScanSourceKind,
    build_cscan_report,
    compute_cscan,
    export_cscan_report,
)
from archaeogpr.io.ogpr_reader import read_ogpr

_REAL_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "Swath003_Array02.ogpr"


def _request(
    *,
    aggregation: CScanAggregation = CScanAggregation.SINGLE_SAMPLE,
    center_time_ns: float = 0.0,
    window_width_ns: float | None = None,
    source_kind: CScanSourceKind = CScanSourceKind.CURRENT,
    source_revision: int = 0,
    geometry_revision: int = 0,
    token: int = 1,
) -> CScanRequest:
    return CScanRequest(
        aggregation=aggregation,
        center_time_ns=center_time_ns,
        window_width_ns=window_width_ns,
        source_kind=source_kind,
        source_revision=source_revision,
        geometry_revision=geometry_revision,
        token=token,
    )


# -- 1-3: sample selection ----------------------------------------------------


def test_single_sample_nearest_index_selection(dataset_factory):
    dataset = dataset_factory(slices_count=3, channels_count=2, samples_count=10, sampling_time_ns=1.0)
    # time_ns = [0, 1, ..., 9]; center 4.6 should select index 5 (nearest).
    result = compute_cscan(dataset, _request(center_time_ns=4.6))
    assert result.selected_sample_index == 5


def test_negative_time_axis_sample_selection(dataset_factory):
    time_ns = (np.arange(20, dtype=np.float64) - 12) * 0.5  # starts at -6.0, time-zero-relative
    dataset = dataset_factory(slices_count=2, channels_count=2, samples_count=20, time_ns=time_ns)
    result = compute_cscan(dataset, _request(center_time_ns=-5.0))
    # time_ns[i] == (i-12)*0.5 == -5.0 exactly at i == 2.
    assert result.selected_sample_index == 2
    assert math.isclose(time_ns[result.selected_sample_index], -5.0)


def test_exact_sample_time_selection_has_no_warning(dataset_factory):
    dataset = dataset_factory(slices_count=2, channels_count=2, samples_count=10, sampling_time_ns=2.0)
    result = compute_cscan(dataset, _request(center_time_ns=6.0))
    assert dataset.time_ns[result.selected_sample_index] == 6.0
    assert result.warnings == ()


# -- 4-6: aggregation math -----------------------------------------------------


def test_rms_computed_correctly(dataset_factory):
    samples_count = 8
    amplitudes = np.zeros((1, 1, samples_count), dtype=np.float64)
    amplitudes[0, 0, :] = [1.0, -1.0, 2.0, -2.0, 3.0, -3.0, 4.0, -4.0]
    dataset = dataset_factory(amplitudes=amplitudes.astype(np.float32), sampling_time_ns=1.0)
    result = compute_cscan(
        dataset, _request(aggregation=CScanAggregation.RMS, center_time_ns=3.5, window_width_ns=8.0)
    )
    expected = math.sqrt(np.mean(np.square(amplitudes[0, 0, :])))
    assert math.isclose(float(result.values[0, 0]), expected, rel_tol=1e-5)


def test_mean_absolute_computed_correctly(dataset_factory):
    amplitudes = np.zeros((1, 1, 4), dtype=np.float32)
    amplitudes[0, 0, :] = [1.0, -2.0, 3.0, -4.0]
    dataset = dataset_factory(amplitudes=amplitudes, sampling_time_ns=1.0)
    result = compute_cscan(
        dataset, _request(aggregation=CScanAggregation.MEAN_ABSOLUTE, center_time_ns=1.5, window_width_ns=4.0)
    )
    assert math.isclose(float(result.values[0, 0]), 2.5, rel_tol=1e-6)


def test_maximum_absolute_computed_correctly(dataset_factory):
    amplitudes = np.zeros((1, 1, 4), dtype=np.float32)
    amplitudes[0, 0, :] = [1.0, -7.0, 3.0, 4.0]
    dataset = dataset_factory(amplitudes=amplitudes, sampling_time_ns=1.0)
    result = compute_cscan(
        dataset,
        _request(aggregation=CScanAggregation.MAXIMUM_ABSOLUTE, center_time_ns=1.5, window_width_ns=4.0),
    )
    assert math.isclose(float(result.values[0, 0]), 7.0, rel_tol=1e-6)


# -- 7: signed polarity --------------------------------------------------------


def test_signed_single_sample_polarity_preserved(dataset_factory):
    amplitudes = np.zeros((1, 1, 4), dtype=np.float32)
    amplitudes[0, 0, :] = [1.0, -7.0, 3.0, 4.0]
    dataset = dataset_factory(amplitudes=amplitudes, sampling_time_ns=1.0)
    result = compute_cscan(dataset, _request(aggregation=CScanAggregation.SINGLE_SAMPLE, center_time_ns=1.0))
    assert float(result.values[0, 0]) == -7.0


# -- 8-11: window semantics -----------------------------------------------------


def test_window_half_open_contract(dataset_factory):
    dataset = dataset_factory(slices_count=1, channels_count=1, samples_count=10, sampling_time_ns=1.0)
    result = compute_cscan(
        dataset, _request(aggregation=CScanAggregation.RMS, center_time_ns=4.0, window_width_ns=4.0)
    )
    # [start, stop) = [2, 6) -- 4 samples, time [2,3,4,5]
    assert (result.sample_start_index, result.sample_stop_index) == (2, 6)
    assert int(result.metadata["window_sample_count"]) == 4


def test_window_boundary_clamp_produces_warning(dataset_factory):
    dataset = dataset_factory(slices_count=1, channels_count=1, samples_count=10, sampling_time_ns=1.0)
    result = compute_cscan(
        dataset, _request(aggregation=CScanAggregation.RMS, center_time_ns=1.0, window_width_ns=6.0)
    )
    # requested [-2, 4) but axis starts at 0 -- must clamp, not error, and warn.
    assert result.sample_start_index == 0
    assert any("clamped" in w for w in result.warnings)


def test_window_entirely_out_of_axis_is_rejected(dataset_factory):
    dataset = dataset_factory(slices_count=1, channels_count=1, samples_count=10, sampling_time_ns=1.0)
    with pytest.raises(CScanError):
        compute_cscan(
            dataset, _request(aggregation=CScanAggregation.RMS, center_time_ns=100.0, window_width_ns=4.0)
        )


def test_zero_or_negative_window_width_is_rejected():
    with pytest.raises(CScanError):
        _request(aggregation=CScanAggregation.RMS, center_time_ns=0.0, window_width_ns=0.0)
    with pytest.raises(CScanError):
        _request(aggregation=CScanAggregation.RMS, center_time_ns=0.0, window_width_ns=-1.0)


# -- 12-14: output invariants ---------------------------------------------------


def test_output_shape_is_trace_by_channel(dataset_factory):
    dataset = dataset_factory(slices_count=7, channels_count=3, samples_count=50)
    result = compute_cscan(dataset, _request(center_time_ns=0.0))
    assert result.values.shape == (7, 3)
    assert result.valid_mask.shape == (7, 3)


def test_input_amplitudes_unchanged(dataset_factory):
    rng = np.random.default_rng(1)
    amplitudes = rng.normal(size=(4, 2, 30)).astype(np.float32)
    original = amplitudes.copy()
    dataset = dataset_factory(amplitudes=amplitudes, sampling_time_ns=1.0)
    compute_cscan(
        dataset, _request(aggregation=CScanAggregation.RMS, center_time_ns=15.0, window_width_ns=10.0)
    )
    np.testing.assert_array_equal(dataset.amplitudes, original)


def test_result_values_are_read_only(dataset_factory):
    dataset = dataset_factory(slices_count=2, channels_count=2, samples_count=10)
    result = compute_cscan(dataset, _request(center_time_ns=0.0))
    with pytest.raises(ValueError):
        result.values[0, 0] = 99.0
    with pytest.raises(ValueError):
        result.valid_mask[0, 0] = False


# -- 15-16: mask/invalid handling -------------------------------------------------


def test_valid_mask_correct_for_partially_masked_channel(dataset_factory):
    channels_count, samples_count = 2, 10
    valid_mask = np.ones((channels_count, samples_count), dtype=bool)
    valid_mask[1, :] = False  # channel 1 entirely invalid
    dataset = dataset_factory(slices_count=3, channels_count=channels_count, samples_count=samples_count)
    result = compute_cscan(dataset, _request(center_time_ns=0.0), valid_mask=valid_mask)
    assert np.all(result.valid_mask[:, 0])
    assert not np.any(result.valid_mask[:, 1])
    assert np.all(np.isnan(result.values[:, 1]))


def test_invalid_trace_cell_is_nan(dataset_factory):
    amplitudes = np.zeros((2, 1, 5), dtype=np.float32)
    amplitudes[1, 0, 2] = np.nan  # only trace 1's selected sample is non-finite
    dataset = dataset_factory(amplitudes=amplitudes, sampling_time_ns=1.0)
    result = compute_cscan(dataset, _request(center_time_ns=2.0))
    assert not math.isnan(result.values[0, 0])
    assert math.isnan(result.values[1, 0])
    assert result.valid_mask[0, 0] and not result.valid_mask[1, 0]


# -- 17-19: numerical safety under -W error --------------------------------------


def test_all_invalid_window_produces_no_spurious_runtime_warning(dataset_factory):
    channels_count, samples_count = 1, 10
    valid_mask = np.zeros((channels_count, samples_count), dtype=bool)
    dataset = dataset_factory(slices_count=3, channels_count=channels_count, samples_count=samples_count)
    with warnings_module.catch_warnings():
        warnings_module.simplefilter("error")
        result = compute_cscan(
            dataset,
            _request(aggregation=CScanAggregation.RMS, center_time_ns=4.0, window_width_ns=8.0),
            valid_mask=valid_mask,
        )
    assert np.all(np.isnan(result.values))
    assert result.statistics.valid_count == 0
    assert any("invalid" in w for w in result.warnings)


def test_nan_inf_input_handled_safely(dataset_factory):
    amplitudes = np.zeros((1, 1, 6), dtype=np.float64)
    amplitudes[0, 0, :] = [1.0, np.nan, np.inf, -np.inf, 2.0, 3.0]
    dataset = dataset_factory(amplitudes=amplitudes.astype(np.float32), sampling_time_ns=1.0)
    with warnings_module.catch_warnings():
        warnings_module.simplefilter("error")
        result = compute_cscan(
            dataset,
            _request(aggregation=CScanAggregation.MEAN_ABSOLUTE, center_time_ns=2.5, window_width_ns=6.0),
        )
    # Only finite, valid samples (1.0, 2.0, 3.0) contribute.
    assert math.isclose(float(result.values[0, 0]), (1.0 + 2.0 + 3.0) / 3.0, rel_tol=1e-6)


def test_float_overflow_avoided_for_large_amplitudes(dataset_factory):
    amplitudes = np.full((1, 1, 4), 1e30, dtype=np.float32)
    dataset = dataset_factory(amplitudes=amplitudes, sampling_time_ns=1.0)
    with warnings_module.catch_warnings():
        warnings_module.simplefilter("error")
        result = compute_cscan(
            dataset, _request(aggregation=CScanAggregation.RMS, center_time_ns=1.5, window_width_ns=4.0)
        )
    assert np.isfinite(result.values[0, 0])


# -- 20: C-order mapping ----------------------------------------------------------


def test_c_order_mapping_matches_trace_channel_indices(dataset_factory):
    trace_count, channel_count, samples_count = 4, 3, 5
    amplitudes = np.arange(trace_count * channel_count * samples_count, dtype=np.float32).reshape(
        trace_count, channel_count, samples_count
    )
    dataset = dataset_factory(amplitudes=amplitudes, sampling_time_ns=1.0)
    result = compute_cscan(dataset, _request(aggregation=CScanAggregation.SINGLE_SAMPLE, center_time_ns=2.0))
    flat_amplitudes = amplitudes[:, :, 2].reshape(-1)
    flat_values = result.values.reshape(-1)
    for trace_index in range(trace_count):
        for channel_index in range(channel_count):
            flat_index = trace_index * channel_count + channel_index
            assert flat_values[flat_index] == flat_amplitudes[flat_index]
            assert flat_values[flat_index] == amplitudes[trace_index, channel_index, 2]


# -- 21-22: revision fields preserved ----------------------------------------------


def test_source_revision_preserved_in_result(dataset_factory):
    dataset = dataset_factory(slices_count=2, channels_count=2, samples_count=5)
    result = compute_cscan(dataset, _request(center_time_ns=0.0, source_revision=7))
    assert result.source_revision == 7


def test_geometry_revision_preserved_in_result(dataset_factory):
    dataset = dataset_factory(slices_count=2, channels_count=2, samples_count=5)
    result = compute_cscan(dataset, _request(center_time_ns=0.0, geometry_revision=3))
    assert result.geometry_revision == 3


# -- 23: JSON sidecar ---------------------------------------------------------------


def test_json_sidecar_finite_and_serializable(tmp_path, ogpr_builder):
    ogpr_bytes = ogpr_builder()
    source_path = tmp_path / "source.ogpr"
    source_path.write_bytes(ogpr_bytes)
    dataset = read_ogpr(source_path)
    result = compute_cscan(dataset, _request(center_time_ns=float(dataset.time_ns[0])))

    output_path = tmp_path / "out.cscan.json"
    export_cscan_report(
        result,
        output_path,
        source_path=source_path,
        geometry_view=CScanGeometryView.ACTUAL_XY_POINT_MAP,
        colormap="gray",
        display_min=-1.0,
        display_max=1.0,
        crs_identifier="EPSG:32632",
        crs_validation_status="declared_unverified",
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["no_interpolation"] is True
    text = json.dumps(payload)
    assert "NaN" not in text and "Infinity" not in text


def test_build_cscan_report_is_json_safe_with_nan_statistics(dataset_factory, tmp_path):
    channels_count, samples_count = 1, 5
    valid_mask = np.zeros((channels_count, samples_count), dtype=bool)
    dataset = dataset_factory(slices_count=2, channels_count=channels_count, samples_count=samples_count)
    result = compute_cscan(dataset, _request(center_time_ns=0.0), valid_mask=valid_mask)
    fake_source = tmp_path / "fake.ogpr"
    fake_source.write_bytes(b"0" * 16)
    payload = build_cscan_report(
        result,
        source_path=fake_source,
        geometry_view=CScanGeometryView.DERIVED_PARAMETER_GRID,
        colormap="seismic",
        display_min=-1.0,
        display_max=1.0,
        crs_identifier=None,
        crs_validation_status="missing",
    )
    assert payload["min_value"] is None
    json.dumps(payload)  # must not raise


# -- 24-25: real raw OGPR file ----------------------------------------------------


@pytest.mark.skipif(not _REAL_FILE.is_file(), reason=f"Real sample file not found at {_REAL_FILE}.")
def test_real_file_hash_recorded_in_cscan_report(tmp_path):
    import hashlib

    dataset = read_ogpr(_REAL_FILE)
    result = compute_cscan(dataset, _request(center_time_ns=float(dataset.time_ns[0])))
    output_path = tmp_path / "real.cscan.json"
    export_cscan_report(
        result,
        output_path,
        source_path=_REAL_FILE,
        geometry_view=CScanGeometryView.ACTUAL_XY_POINT_MAP,
        colormap="gray",
        display_min=-1.0,
        display_max=1.0,
        crs_identifier="EPSG:32632",
        crs_validation_status="declared_unverified",
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    expected_hash = hashlib.sha256(_REAL_FILE.read_bytes()).hexdigest()
    assert payload["source_sha256"] == expected_hash


@pytest.mark.skipif(not _REAL_FILE.is_file(), reason=f"Real sample file not found at {_REAL_FILE}.")
def test_real_file_unchanged_by_cscan_compute_and_export(tmp_path):
    import hashlib

    before_hash = hashlib.sha256(_REAL_FILE.read_bytes()).hexdigest()
    before_mtime = _REAL_FILE.stat().st_mtime

    dataset = read_ogpr(_REAL_FILE)
    assert dataset.shape == (175, 11, 1024)
    result = compute_cscan(
        dataset,
        _request(
            aggregation=CScanAggregation.RMS, center_time_ns=float(dataset.time_ns[50]), window_width_ns=5.0
        ),
    )
    assert result.values.shape == (175, 11)
    export_cscan_report(
        result,
        tmp_path / "real2.cscan.json",
        source_path=_REAL_FILE,
        geometry_view=CScanGeometryView.ACTUAL_XY_POINT_MAP,
        colormap="gray",
        display_min=-1.0,
        display_max=1.0,
        crs_identifier="EPSG:32632",
        crs_validation_status="declared_unverified",
    )

    after_hash = hashlib.sha256(_REAL_FILE.read_bytes()).hexdigest()
    after_mtime = _REAL_FILE.stat().st_mtime
    assert after_hash == before_hash
    assert after_mtime == before_mtime


# -- 27-29: degenerate grid shapes (Section-11 hardening) ----------------------


def test_single_trace_multi_channel_shape(dataset_factory):
    """27: a 1xN grid (one trace, several channels) computes without error or warning."""
    dataset = dataset_factory(slices_count=1, channels_count=5, samples_count=16, sampling_time_ns=1.0)
    result = compute_cscan(
        dataset, _request(aggregation=CScanAggregation.RMS, center_time_ns=8.0, window_width_ns=4.0)
    )
    assert result.values.shape == (1, 5)
    assert result.valid_mask.shape == (1, 5)
    assert bool(result.valid_mask.all())


def test_multi_trace_single_channel_shape(dataset_factory):
    """28: an Nx1 grid (several traces, one channel) computes without error or warning."""
    dataset = dataset_factory(slices_count=7, channels_count=1, samples_count=16, sampling_time_ns=1.0)
    result = compute_cscan(dataset, _request(center_time_ns=8.0))
    assert result.values.shape == (7, 1)
    assert result.valid_mask.shape == (7, 1)
    assert bool(result.valid_mask.all())


def test_single_trace_single_channel_shape(dataset_factory):
    """29: a 1x1 grid computes; statistics degenerate cleanly to that one cell."""
    amplitudes = np.full((1, 1, 16), 2.5, dtype=np.float32)
    dataset = dataset_factory(amplitudes=amplitudes, sampling_time_ns=1.0)
    result = compute_cscan(
        dataset,
        _request(aggregation=CScanAggregation.MEAN_ABSOLUTE, center_time_ns=8.0, window_width_ns=16.0),
    )
    assert result.values.shape == (1, 1)
    assert math.isclose(float(result.values[0, 0]), 2.5, rel_tol=1e-6)
    assert result.statistics.valid_count == 1
    assert result.statistics.invalid_count == 0
    assert result.statistics.min_value == result.statistics.max_value == result.statistics.mean_value
