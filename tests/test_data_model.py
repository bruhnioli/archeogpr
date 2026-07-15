"""Unit tests for the GPRDataset model and qc.metadata derivation functions.

These use small hand-built numpy arrays rather than a real/synthetic .ogpr
file, since they are testing computation and invariants, not file parsing.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from archaeogpr.model.dataset import DatasetValidationError, GPRDataset
from archaeogpr.qc.metadata import (
    compute_along_track_spacing_m,
    compute_amplitude_statistics,
    compute_cross_channel_spacing_m,
    compute_depth_per_sample_m,
    compute_max_depth_m,
    compute_profile_length_m,
    compute_swath_width_m,
    compute_time_window_ns,
    derive_metadata,
)

SLICES, CHANNELS, SAMPLES = 3, 2, 4


def make_dataset(**overrides) -> GPRDataset:
    amplitudes = np.arange(SLICES * CHANNELS * SAMPLES, dtype=np.float32).reshape(SLICES, CHANNELS, SAMPLES)
    kwargs = dict(
        amplitudes=amplitudes,
        time_ns=np.arange(SAMPLES, dtype=np.float64) * 0.5,
        x=np.array([[0.0, 0.0], [3.0, 3.0], [6.0, 6.0]]),
        y=np.array([[0.0, 0.0], [4.0, 4.0], [8.0, 8.0]]),
        depth_top_m=np.zeros((SLICES, CHANNELS)),
        elevation_top_m=np.full((SLICES, CHANNELS), 10.0),
        depth_bottom_m=np.full((SLICES, CHANNELS), -2.0),
        elevation_bottom_m=np.full((SLICES, CHANNELS), 8.0),
        metadata={
            "sampling": {"sampling_time_ns": 0.5},
            "radar": {"propagation_velocity_m_per_ns": 0.1},
            "warnings": [],
        },
    )
    kwargs.update(overrides)
    return GPRDataset(**kwargs)


# --- GPRDataset invariants --------------------------------------------------


def test_amplitudes_are_read_only():
    dataset = make_dataset()
    with pytest.raises(ValueError):
        dataset.amplitudes[0, 0, 0] = 123.0


def test_functions_do_not_mutate_amplitudes_in_place():
    dataset = make_dataset()
    original = dataset.amplitudes.copy()
    compute_amplitude_statistics(dataset.amplitudes)
    derive_metadata(dataset)
    np.testing.assert_array_equal(dataset.amplitudes, original)


def test_metadata_is_json_serializable_directly():
    dataset = make_dataset()
    json.dumps(dataset.metadata)  # must not raise


def test_metadata_mapping_rejects_item_assignment():
    dataset = make_dataset()
    with pytest.raises(TypeError):
        dataset.metadata["new_key"] = 1


def test_constructing_with_non_serializable_metadata_raises():
    with pytest.raises(DatasetValidationError):
        make_dataset(metadata={"bad": object()})


def test_processing_history_starts_empty():
    assert make_dataset().processing_history == ()


def test_with_processing_step_does_not_mutate_original():
    dataset = make_dataset()
    updated = dataset.with_processing_step({"step": "example", "params": {}})
    assert dataset.processing_history == ()
    assert len(updated.processing_history) == 1
    assert updated.processing_history[0]["step"] == "example"


@pytest.mark.parametrize("field", ["x", "y", "depth_top_m", "elevation_top_m", "depth_bottom_m"])
def test_mismatched_coordinate_shape_raises(field):
    with pytest.raises(DatasetValidationError):
        make_dataset(**{field: np.zeros((5, 5))})


def test_mismatched_time_ns_length_raises():
    with pytest.raises(DatasetValidationError):
        make_dataset(time_ns=np.arange(10, dtype=np.float64))


def test_dataset_without_geolocation_is_constructible():
    dataset = make_dataset(
        x=None, y=None, depth_top_m=None, elevation_top_m=None, depth_bottom_m=None, elevation_bottom_m=None
    )
    assert dataset.has_geolocation is False


# --- qc.metadata derivation correctness ------------------------------------


def test_compute_time_window_ns():
    assert compute_time_window_ns(samples_count=8, sampling_time_ns=0.25) == 2.0


def test_compute_depth_estimates():
    assert compute_depth_per_sample_m(velocity_m_per_ns=0.1, sampling_time_ns=0.5) == pytest.approx(0.025)
    assert compute_max_depth_m(
        velocity_m_per_ns=0.1, sampling_time_ns=0.5, samples_count=10
    ) == pytest.approx(0.25)


def test_compute_profile_length_and_along_track_spacing():
    # Slice centers at (0,0), (3,4), (6,8): two consecutive 3-4-5-triangle segments.
    x = np.array([[0.0, 0.0], [3.0, 3.0], [6.0, 6.0]])
    y = np.array([[0.0, 0.0], [4.0, 4.0], [8.0, 8.0]])
    assert compute_profile_length_m(x, y) == pytest.approx(10.0)
    assert compute_along_track_spacing_m(x, y) == pytest.approx(5.0)


def test_compute_cross_channel_spacing_and_swath_width():
    x = np.array([[0.0, 3.0, 6.0]])
    y = np.array([[0.0, 4.0, 8.0]])
    assert compute_cross_channel_spacing_m(x, y) == pytest.approx(5.0)
    assert compute_swath_width_m(x, y) == pytest.approx(10.0)


def test_compute_amplitude_statistics_known_values():
    amplitudes = np.array([-2.0, -1.0, 0.0, 1.0, 2.0], dtype=np.float32)
    stats = compute_amplitude_statistics(amplitudes)
    assert stats["min"] == -2.0
    assert stats["max"] == 2.0
    assert stats["mean"] == pytest.approx(0.0)
    assert stats["p50"] == pytest.approx(0.0)


def test_derive_metadata_reports_missing_velocity_warning():
    dataset = make_dataset(metadata={"sampling": {"sampling_time_ns": 0.5}, "radar": {}, "warnings": []})
    derived = derive_metadata(dataset)
    assert derived["depth_estimate"]["max_depth_m"] is None
    assert any("propagation velocity" in w for w in derived["warnings"])


def test_derive_metadata_geometry_matches_dataset_coordinates():
    dataset = make_dataset()
    derived = derive_metadata(dataset)
    assert derived["geometry"]["profile_length_m"] == pytest.approx(10.0)
    assert derived["geometry"]["x_min"] == 0.0
    assert derived["geometry"]["x_max"] == 6.0
    assert derived["geometry"]["elevation_min_m"] == 8.0
    assert derived["geometry"]["elevation_max_m"] == 10.0
