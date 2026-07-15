"""Sprint 2.2 (ADR-004): target_sample=0 vs target_sample=16 must be DC-offset-invariant.

Uses the canonical policy (method=mean, window 20-100 ns, window_reference=
dataset_time) on synthetic data shaped like the real file: a strong early
pulse near the pick, then quieter content further out. The whole point of
the time-zero-relative time axis is that the *same* ns window resolves to
the *same* underlying raw samples regardless of target_sample -- these
tests prove that claim directly, not just via aggregate statistics.
"""

from __future__ import annotations

import numpy as np
import pytest

from archaeogpr.processing.dc_offset import correct_dc_offset
from archaeogpr.processing.time_zero import correct_time_zero

SAMPLING_TIME_NS = 0.125
SAMPLES_COUNT = 1024
DC_WINDOW_START_NS = 20.0
DC_WINDOW_END_NS = 100.0


def _synthetic_multi_channel_dataset(dataset_factory):
    rng = np.random.default_rng(42)
    channels_count, slices_count = 3, 6
    picks = {0: 70, 1: 73, 2: 77}
    amplitudes = np.zeros((slices_count, channels_count, SAMPLES_COUNT), dtype=np.float32)
    for channel, pick in picks.items():
        amplitudes[:, channel, pick] = 400_000.0
        amplitudes[:, channel, pick + 5] = -480_000.0
        amplitudes[:, channel, 200:900] += rng.normal(50.0, 20.0, size=(slices_count, 700)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    return ds, picks


def _run_candidate(dataset_factory, target_sample: int):
    ds, picks = _synthetic_multi_channel_dataset(dataset_factory)
    tz_result = correct_time_zero(
        ds,
        method="manual",
        picks=picks,
        target_sample=target_sample,
        max_shift_samples=96,
        overflow_policy="error",
    )
    dc_result = correct_dc_offset(
        tz_result.dataset,
        method="mean",
        window_start_ns=DC_WINDOW_START_NS,
        window_end_ns=DC_WINDOW_END_NS,
        valid_mask=tz_result.valid_mask,
        window_reference="dataset_time",
    )
    return tz_result, dc_result


def test_same_relative_window_selects_the_same_raw_samples(dataset_factory):
    tz0, dc0 = _run_candidate(dataset_factory, target_sample=0)
    tz16, dc16 = _run_candidate(dataset_factory, target_sample=16)

    channels_count = tz0.dataset.shape[1]
    for channel in range(channels_count):
        shift0 = tz0.diagnostics["channel_shifts"][str(channel)]
        shift16 = tz16.diagnostics["channel_shifts"][str(channel)]
        raw_start_0 = dc0.diagnostics["window_start_sample"] - shift0
        raw_end_0 = dc0.diagnostics["window_end_sample"] - shift0
        raw_start_16 = dc16.diagnostics["window_start_sample"] - shift16
        raw_end_16 = dc16.diagnostics["window_end_sample"] - shift16
        assert raw_start_0 == raw_start_16, f"channel {channel}: raw window start differs"
        assert raw_end_0 == raw_end_16, f"channel {channel}: raw window end differs"


def test_offset_arrays_are_equal_between_target_candidates(dataset_factory):
    _, dc0 = _run_candidate(dataset_factory, target_sample=0)
    _, dc16 = _run_candidate(dataset_factory, target_sample=16)

    offsets_0 = dc0.removed_component[:, :, 0].astype(np.float64)
    offsets_16 = dc16.removed_component[:, :, 0].astype(np.float64)
    np.testing.assert_allclose(offsets_0, offsets_16, rtol=1e-6, atol=1e-3)


def test_final_amplitudes_equal_in_the_common_relative_time_region(dataset_factory):
    tz0, dc0 = _run_candidate(dataset_factory, target_sample=0)
    tz16, dc16 = _run_candidate(dataset_factory, target_sample=16)

    time0 = dc0.dataset.time_ns
    time16 = dc16.dataset.time_ns
    common_end = min(time0[-1], time16[-1])
    mask0 = (time0 >= 0) & (time0 <= common_end)
    mask16 = (time16 >= 0) & (time16 <= common_end)
    assert int(mask0.sum()) == int(mask16.sum())

    common0 = dc0.dataset.amplitudes[:, :, mask0].astype(np.float64)
    common16 = dc16.dataset.amplitudes[:, :, mask16].astype(np.float64)
    np.testing.assert_allclose(common0, common16, rtol=1e-6, atol=1e-3)


def test_target_16_has_fewer_padding_samples_than_target_0(dataset_factory):
    tz0, _ = _run_candidate(dataset_factory, target_sample=0)
    tz16, _ = _run_candidate(dataset_factory, target_sample=16)

    channels_count = tz0.dataset.shape[1]
    for channel in range(channels_count):
        padding_0 = int((~tz0.valid_mask[channel]).sum())
        padding_16 = int((~tz16.valid_mask[channel]).sum())
        assert padding_16 == padding_0 - 16, f"channel {channel}: expected exactly 16 fewer padding samples"


def test_processing_history_records_time_axis_and_dc_window(dataset_factory):
    tz_result, dc_result = _run_candidate(dataset_factory, target_sample=16)

    tz_record = tz_result.dataset.processing_history[-1]
    assert tz_record["operation"] == "time_zero_correction"
    assert tz_record["diagnostics"]["time_axis"]["target_sample"] == 16
    assert tz_record["diagnostics"]["time_axis"]["time_zero_reference_ns"] == 0.0

    dc_record = dc_result.dataset.processing_history[-1]
    assert dc_record["operation"] == "dc_offset_correction"
    assert dc_record["parameters"]["window_start_ns"] == pytest.approx(DC_WINDOW_START_NS)
    assert dc_record["parameters"]["window_end_ns"] == pytest.approx(DC_WINDOW_END_NS)
    assert dc_record["parameters"]["window_reference"] == "dataset_time"
