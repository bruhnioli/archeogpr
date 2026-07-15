"""Tests for the combined time-zero -> DC offset pipeline's processing_history."""

from __future__ import annotations

import json

import numpy as np

from archaeogpr.processing.dc_offset import correct_dc_offset
from archaeogpr.processing.time_zero import correct_time_zero

SAMPLING_TIME_NS = 0.5


def _dataset_with_pulse_and_bias(dataset_factory):
    amplitudes = np.full((5, 2, 100), 4.0, dtype=np.float32)
    amplitudes[:, :, 40] += 200.0
    return dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)


def test_combined_pipeline_records_time_zero_then_dc_offset_in_order(dataset_factory):
    raw = _dataset_with_pulse_and_bias(dataset_factory)

    tz_result = correct_time_zero(raw, method="channel_median_peak", search_start_ns=10.0, search_end_ns=30.0)
    dc_result = correct_dc_offset(tz_result.dataset, method="mean")

    operations = [record["operation"] for record in dc_result.dataset.processing_history]
    assert operations == ["time_zero_correction", "dc_offset_correction"]


def test_combined_pipeline_never_mutates_the_original_raw_dataset(dataset_factory):
    raw = _dataset_with_pulse_and_bias(dataset_factory)
    original_bytes = raw.amplitudes.tobytes()
    assert raw.processing_history == ()

    tz_result = correct_time_zero(raw, method="channel_median_peak", search_start_ns=10.0, search_end_ns=30.0)
    correct_dc_offset(tz_result.dataset, method="mean")

    assert raw.amplitudes.tobytes() == original_bytes
    assert raw.processing_history == ()  # still untouched after both downstream stages ran


def test_intermediate_dataset_keeps_only_its_own_stage_in_history(dataset_factory):
    raw = _dataset_with_pulse_and_bias(dataset_factory)
    tz_result = correct_time_zero(raw, method="channel_median_peak", search_start_ns=10.0, search_end_ns=30.0)

    assert [r["operation"] for r in tz_result.dataset.processing_history] == ["time_zero_correction"]

    dc_result = correct_dc_offset(tz_result.dataset, method="mean")

    # Chaining downstream must not retroactively change the intermediate dataset's own history.
    assert [r["operation"] for r in tz_result.dataset.processing_history] == ["time_zero_correction"]
    assert [r["operation"] for r in dc_result.dataset.processing_history] == [
        "time_zero_correction",
        "dc_offset_correction",
    ]
    # The carried-over time_zero record itself must be byte-for-byte identical, not recomputed.
    assert dc_result.dataset.processing_history[0] == tz_result.dataset.processing_history[0]


def test_operations_are_composable_in_either_order(dataset_factory):
    raw = _dataset_with_pulse_and_bias(dataset_factory)

    dc_result = correct_dc_offset(raw, method="mean")
    tz_after_dc = correct_time_zero(
        dc_result.dataset, method="channel_median_peak", search_start_ns=10.0, search_end_ns=30.0
    )

    operations = [record["operation"] for record in tz_after_dc.dataset.processing_history]
    assert operations == ["dc_offset_correction", "time_zero_correction"]


def test_full_processing_history_is_json_serializable(dataset_factory):
    raw = _dataset_with_pulse_and_bias(dataset_factory)
    tz_result = correct_time_zero(raw, method="channel_median_peak", search_start_ns=10.0, search_end_ns=30.0)
    dc_result = correct_dc_offset(tz_result.dataset, method="mean")

    history_as_dicts = [dict(record) for record in dc_result.dataset.processing_history]
    serialized = json.dumps(history_as_dicts)
    assert json.loads(serialized) == history_as_dicts
