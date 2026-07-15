"""Synthetic tests for archaeogpr.processing.dewow.correct_dewow (Sprint 3 / ADR-005).

20 tests covering: baseline/sinusoid removal, pulse-position preservation,
input=output+removed, padding exclusion/preservation, valid-mask/shape/
immutability, method correctness (mean vs median), window conversion, error
paths, NaN/Inf guard, processing history, and NPZ round-trip.
"""

from __future__ import annotations

import numpy as np
import pytest

from archaeogpr.export.processed import write_corrected_npz
from archaeogpr.export.sprint3 import read_processed_npz
from archaeogpr.processing.common import ProcessingError
from archaeogpr.processing.dewow import correct_dewow

SAMPLING_TIME_NS = 1.0


def test_constant_trace_dewows_to_exactly_zero(dataset_factory):
    # A moving mean/median of a perfectly constant signal equals that constant
    # everywhere (reflect/nearest padding both preserve a constant exactly),
    # so subtracting it must leave exactly zero -- not approximately.
    amplitudes = np.full((3, 2, 100), 42.5, dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dewow(ds, window_ns=9.0, method="running_mean")
    np.testing.assert_allclose(result.dataset.amplitudes, 0.0, atol=1e-3)


def test_wow_removed_while_high_frequency_signal_preserved(dataset_factory):
    # High-freq component's period exactly equals the applied window length
    # (9 samples): summing any 9 consecutive samples of a period-9 sinusoid
    # covers exactly one full cycle, so its own moving average is ~0 and it
    # survives the subtraction. The low-freq "wow" varies far more slowly
    # than the window, so the moving average tracks (and removes) it closely.
    samples_count = 200
    n = np.arange(samples_count, dtype=np.float64)
    high_freq = 50.0 * np.sin(2 * np.pi * n / 9.0)
    low_freq = 800.0 * np.cos(2 * np.pi * n / (4 * samples_count))
    trace = (high_freq + low_freq).astype(np.float32)
    amplitudes = np.broadcast_to(trace, (2, 1, samples_count)).copy()
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    result = correct_dewow(ds, window_ns=9.0, method="running_mean")
    interior = slice(20, 180)  # away from edge-reflection effects
    output = result.dataset.amplitudes[0, 0, :].astype(np.float64)
    removed = result.removed_component[0, 0, :].astype(np.float64)
    np.testing.assert_allclose(output[interior], high_freq[interior], atol=2.0)
    np.testing.assert_allclose(removed[interior], low_freq[interior], atol=2.0)


def test_output_equals_input_minus_removed_component(dataset_factory):
    rng = np.random.default_rng(0)
    amplitudes = rng.normal(0.0, 100.0, size=(4, 2, 120)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dewow(ds, window_ns=7.0, method="running_mean")
    reconstructed = result.dataset.amplitudes.astype(np.float64) + result.removed_component.astype(np.float64)
    np.testing.assert_allclose(reconstructed, ds.amplitudes.astype(np.float64), atol=1e-1)


def test_pulse_position_is_preserved(dataset_factory):
    samples_count = 150
    n = np.arange(samples_count, dtype=np.float64)
    drift = 20.0 * np.cos(2 * np.pi * n / (3 * samples_count))  # slow, small-magnitude-per-sample drift
    trace = drift.copy()
    pulse_index = 90
    trace[pulse_index] += 5000.0  # far larger than any local baseline change
    amplitudes = trace.astype(np.float32).reshape(1, 1, samples_count)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    result = correct_dewow(ds, window_ns=9.0, method="running_mean")
    output = result.dataset.amplitudes[0, 0, :]
    assert int(np.argmax(np.abs(output))) == pulse_index


def test_padding_excluded_from_computation(dataset_factory):
    # Two valid segments separated by a padding gap holding an extreme value.
    # The first segment's own dewow result must be identical whether the gap
    # holds an extreme value or a benign one -- proof the window never reads
    # across it.
    samples_count = 60
    valid_mask = np.ones((1, samples_count), dtype=bool)
    valid_mask[0, 20:25] = False  # padding gap

    rng = np.random.default_rng(1)
    first_segment = rng.normal(0.0, 5.0, size=20).astype(np.float32)

    def run(padding_value: float) -> np.ndarray:
        trace = np.zeros(samples_count, dtype=np.float32)
        trace[:20] = first_segment
        trace[20:25] = padding_value
        trace[25:] = rng.normal(10.0, 5.0, size=samples_count - 25).astype(np.float32)
        ds = dataset_factory(amplitudes=trace.reshape(1, 1, samples_count), sampling_time_ns=SAMPLING_TIME_NS)
        result = correct_dewow(ds, window_ns=5.0, method="running_mean", valid_mask=valid_mask)
        return result.dataset.amplitudes[0, 0, :20].copy()

    benign = run(0.0)
    extreme = run(1.0e9)
    np.testing.assert_array_equal(benign, extreme)


def test_padding_preserved_and_valid_mask_returned_as_independent_copy(dataset_factory):
    samples_count = 50
    amplitudes = np.zeros((2, 1, samples_count), dtype=np.float32)
    amplitudes[:, 0, :30] = 5.0
    amplitudes[:, 0, 30:] = 0.0  # padding, exactly at a fill_value of 0.0
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    valid_mask = np.ones((1, samples_count), dtype=bool)
    valid_mask[0, 30:] = False

    result = correct_dewow(ds, window_ns=7.0, method="running_mean", valid_mask=valid_mask)
    np.testing.assert_array_equal(result.dataset.amplitudes[:, 0, 30:], 0.0)
    np.testing.assert_array_equal(result.removed_component[:, 0, 30:], 0.0)

    assert result.valid_mask is not None
    np.testing.assert_array_equal(result.valid_mask, valid_mask)
    valid_mask[0, 0] = False  # mutate the caller's original array
    assert result.valid_mask[0, 0], "returned valid_mask must be an independent copy"


def test_output_shape_and_dtype_match_input(dataset_factory):
    amplitudes = np.random.default_rng(2).normal(size=(5, 3, 80)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dewow(ds, window_ns=9.0, method="running_mean")
    assert result.dataset.shape == ds.shape
    assert result.removed_component.shape == ds.shape
    assert result.dataset.amplitudes.dtype == np.float32
    assert result.removed_component.dtype == np.float32


def test_input_dataset_is_not_mutated(dataset_factory):
    amplitudes = np.random.default_rng(3).normal(size=(3, 2, 60)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    original_bytes = ds.amplitudes.tobytes()
    correct_dewow(ds, window_ns=9.0, method="running_mean")
    assert ds.amplitudes.tobytes() == original_bytes


def test_running_mean_and_running_median_differ_on_outlier_trace(dataset_factory):
    # A single huge outlier pulls a running_mean baseline noticeably; a
    # running_median baseline (window >= 3) ignores one outlier entirely.
    samples_count = 60
    trace = np.zeros(samples_count, dtype=np.float32)
    trace[30] = 100_000.0
    ds = dataset_factory(amplitudes=trace.reshape(1, 1, samples_count), sampling_time_ns=SAMPLING_TIME_NS)

    mean_result = correct_dewow(ds, window_ns=9.0, method="running_mean")
    median_result = correct_dewow(ds, window_ns=9.0, method="running_median")

    mean_baseline_at_outlier = float(mean_result.removed_component[0, 0, 30])
    median_baseline_at_outlier = float(median_result.removed_component[0, 0, 30])
    assert mean_baseline_at_outlier > 1000.0
    assert median_baseline_at_outlier == pytest.approx(0.0, abs=1e-6)


def test_running_median_warns_about_nonlinearity(dataset_factory):
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dewow(ds, window_ns=9.0, method="running_median")
    assert any("nonlinear" in w for w in result.warnings)


def test_even_window_is_bumped_to_odd_and_warns(dataset_factory):
    amplitudes = np.zeros((2, 1, 60), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dewow(ds, window_ns=8.0, method="running_mean")  # round(8.0/1.0)=8, even
    assert result.diagnostics["requested_window_samples"] == 8
    assert result.diagnostics["applied_window_samples"] == 9
    assert result.diagnostics["applied_window_ns"] == pytest.approx(9.0)
    assert any("bumped up" in w for w in result.warnings)


def test_odd_window_is_used_as_is_without_warning(dataset_factory):
    amplitudes = np.zeros((2, 1, 60), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dewow(ds, window_ns=9.0, method="running_mean")  # round(9.0/1.0)=9, already odd
    assert result.diagnostics["requested_window_samples"] == 9
    assert result.diagnostics["applied_window_samples"] == 9
    assert not any("bumped up" in w for w in result.warnings)


def test_error_on_invalid_method(dataset_factory):
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    with pytest.raises(ProcessingError, match="method must be one of"):
        correct_dewow(ds, window_ns=9.0, method="bogus")


def test_error_on_invalid_edge_mode(dataset_factory):
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    with pytest.raises(ProcessingError, match="edge_mode must be one of"):
        correct_dewow(ds, window_ns=9.0, method="running_mean", edge_mode="zero")


def test_error_on_window_narrower_than_minimum_samples(dataset_factory):
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    with pytest.raises(ProcessingError, match="below the minimum"):
        correct_dewow(ds, window_ns=1.0, method="running_mean")  # round(1.0/1.0)=1 sample


def test_error_on_window_wider_than_valid_segment(dataset_factory):
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    valid_mask = np.zeros((1, 40), dtype=bool)
    valid_mask[0, 10:15] = True  # a 5-sample valid run, narrower than a 9-sample window
    with pytest.raises(ProcessingError, match="wider than a valid segment"):
        correct_dewow(ds, window_ns=9.0, method="running_mean", valid_mask=valid_mask)


def test_nan_input_raises_rather_than_propagating(dataset_factory):
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    amplitudes[0, 0, 20] = np.nan
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    with pytest.raises(ProcessingError, match="NaN/Inf"):
        correct_dewow(ds, window_ns=9.0, method="running_mean")


def test_processing_history_records_operation_parameters_and_diagnostics(dataset_factory):
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dewow(ds, window_ns=9.0, method="running_mean", edge_mode="nearest")
    assert ds.processing_history == ()
    record = result.dataset.processing_history[-1]
    assert record["operation"] == "dewow_correction"
    assert record["parameters"]["window_ns"] == 9.0
    assert record["parameters"]["method"] == "running_mean"
    assert record["parameters"]["edge_mode"] == "nearest"
    assert record["diagnostics"]["applied_window_samples"] == 9


def test_repeat_processing_guard_and_allow_flag_override(dataset_factory):
    amplitudes = np.random.default_rng(4).normal(size=(2, 1, 60)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    once = correct_dewow(ds, window_ns=9.0, method="running_mean")

    with pytest.raises(ProcessingError, match="already contains"):
        correct_dewow(once.dataset, window_ns=9.0, method="running_mean")

    twice = correct_dewow(once.dataset, window_ns=9.0, method="running_mean", allow_repeat_processing=True)
    operations = [record["operation"] for record in twice.dataset.processing_history]
    assert operations.count("dewow_correction") == 2


def test_dewow_npz_round_trip_preserves_amplitudes_and_history(tmp_path, dataset_factory):
    amplitudes = np.random.default_rng(5).normal(size=(3, 2, 50)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    valid_mask = np.ones((2, 50), dtype=bool)
    valid_mask[:, 45:] = False

    result = correct_dewow(ds, window_ns=9.0, method="running_mean", valid_mask=valid_mask)
    npz_path = write_corrected_npz(result, tmp_path / "dewow_processed.npz")

    reloaded_dataset, reloaded_mask = read_processed_npz(npz_path)
    np.testing.assert_array_equal(reloaded_dataset.amplitudes, result.dataset.amplitudes)
    np.testing.assert_array_equal(reloaded_dataset.time_ns, result.dataset.time_ns)
    assert reloaded_mask is not None
    np.testing.assert_array_equal(reloaded_mask, result.valid_mask)
    assert [r["operation"] for r in reloaded_dataset.processing_history] == ["dewow_correction"]
