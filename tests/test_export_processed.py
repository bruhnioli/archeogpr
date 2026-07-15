"""Tests for archaeogpr.export.processed's NPZ round-trip of valid_mask."""

from __future__ import annotations

import numpy as np

from archaeogpr.export.processed import write_combined_npz, write_corrected_npz
from archaeogpr.processing.dc_offset import correct_dc_offset
from archaeogpr.processing.time_zero import correct_time_zero

SAMPLING_TIME_NS = 0.5


def _dataset_with_pulse(dataset_factory):
    amplitudes = np.zeros((5, 2, 100), dtype=np.float32)
    amplitudes[:, 0, 40] = 100.0
    amplitudes[:, 1, 45] = 100.0
    return dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)


def test_corrected_npz_round_trips_the_valid_mask(dataset_factory, tmp_path):
    ds = _dataset_with_pulse(dataset_factory)
    result = correct_time_zero(ds, method="manual", picks={0: 40, 1: 45}, target_sample=0)
    assert result.valid_mask is not None

    npz_path = write_corrected_npz(result, tmp_path / "time_zero.npz")
    with np.load(npz_path) as npz:
        assert bool(npz["has_valid_mask"]) is True
        np.testing.assert_array_equal(npz["valid_mask"], result.valid_mask)
        assert npz["valid_mask"].dtype == np.bool_
        assert npz["valid_mask"].shape == (ds.shape[1], ds.shape[2])


def test_combined_npz_round_trips_the_valid_mask_from_dc_offset(dataset_factory, tmp_path):
    ds = _dataset_with_pulse(dataset_factory)
    tz_result = correct_time_zero(ds, method="manual", picks={0: 40, 1: 45}, target_sample=0)
    dc_result = correct_dc_offset(tz_result.dataset, method="mean", valid_mask=tz_result.valid_mask)
    assert dc_result.valid_mask is not None

    npz_path = write_combined_npz(tz_result, dc_result, tmp_path / "combined.npz")
    with np.load(npz_path) as npz:
        assert bool(npz["has_valid_mask"]) is True
        np.testing.assert_array_equal(npz["valid_mask"], dc_result.valid_mask)


def test_combined_npz_falls_back_to_time_zero_mask_when_dc_offset_has_none(dataset_factory, tmp_path):
    ds = _dataset_with_pulse(dataset_factory)
    tz_result = correct_time_zero(ds, method="manual", picks={0: 40, 1: 45}, target_sample=0)
    dc_result = correct_dc_offset(tz_result.dataset, method="mean")  # no valid_mask passed through
    assert dc_result.valid_mask is None

    npz_path = write_combined_npz(tz_result, dc_result, tmp_path / "combined_no_mask.npz")
    with np.load(npz_path) as npz:
        assert bool(npz["has_valid_mask"]) is True
        np.testing.assert_array_equal(npz["valid_mask"], tz_result.valid_mask)


def test_corrected_npz_omits_valid_mask_key_when_none(dataset_factory, tmp_path):
    ds = dataset_factory(amplitudes=np.zeros((3, 1, 20), dtype=np.float32), sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dc_offset(ds, method="mean")
    assert result.valid_mask is None

    npz_path = write_corrected_npz(result, tmp_path / "no_mask.npz")
    with np.load(npz_path) as npz:
        assert bool(npz["has_valid_mask"]) is False
        assert "valid_mask" not in npz.files
