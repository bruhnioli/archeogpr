"""Synthetic tests for archaeogpr.processing.dc_offset.correct_dc_offset."""

from __future__ import annotations

import numpy as np
import pytest

from archaeogpr.processing.common import ProcessingError
from archaeogpr.processing.dc_offset import correct_dc_offset

SAMPLING_TIME_NS = 1.0


def test_known_constant_offset_is_removed_by_mean(dataset_factory):
    amplitudes = np.full((4, 2, 50), 7.5, dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dc_offset(ds, method="mean")
    np.testing.assert_allclose(result.dataset.amplitudes, 0.0, atol=1e-4)


def test_known_constant_offset_is_removed_by_median(dataset_factory):
    amplitudes = np.full((4, 2, 50), -3.25, dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dc_offset(ds, method="median")
    np.testing.assert_allclose(result.dataset.amplitudes, 0.0, atol=1e-4)


def test_each_trace_is_corrected_independently(dataset_factory):
    slices_count, channels_count, samples_count = 3, 2, 20
    amplitudes = np.zeros((slices_count, channels_count, samples_count), dtype=np.float32)
    # A different constant offset per (slice, channel) trace.
    true_offsets = np.array([[1.0, -2.0], [3.5, 0.0], [-4.0, 2.5]], dtype=np.float32)
    for i in range(slices_count):
        for j in range(channels_count):
            amplitudes[i, j, :] = true_offsets[i, j]
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    result = correct_dc_offset(ds, method="mean")
    offset = result.removed_component[:, :, 0]
    np.testing.assert_allclose(offset, true_offsets, atol=1e-4)
    np.testing.assert_allclose(result.dataset.amplitudes, 0.0, atol=1e-4)


def test_window_is_used_to_compute_offset_not_the_full_trace(dataset_factory):
    # Window [0, 10) ns == samples [0, 10) at 1.0 ns/sample: offset should come
    # only from that region, ignoring a very different value later in the trace.
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    amplitudes[:, 0, :10] = 2.0
    amplitudes[:, 0, 10:] = 1000.0
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    result = correct_dc_offset(ds, method="mean", window_start_ns=0.0, window_end_ns=10.0)
    assert result.diagnostics["offset_statistics"]["mean"] == pytest.approx(2.0)
    np.testing.assert_allclose(result.dataset.amplitudes[:, 0, :10], 0.0, atol=1e-4)
    np.testing.assert_allclose(result.dataset.amplitudes[:, 0, 10:], 998.0, atol=1e-4)


def test_output_shape_matches_input_shape(dataset_factory):
    amplitudes = np.random.default_rng(0).normal(size=(5, 3, 60)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dc_offset(ds, method="mean")
    assert result.dataset.shape == ds.shape
    assert result.removed_component.shape == ds.shape


def test_input_dataset_is_not_mutated(dataset_factory):
    amplitudes = np.full((3, 2, 30), 9.0, dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    original_bytes = ds.amplitudes.tobytes()
    correct_dc_offset(ds, method="mean")
    assert ds.amplitudes.tobytes() == original_bytes


def test_removed_component_is_correct(dataset_factory):
    amplitudes = np.full((3, 2, 30), 9.0, dtype=np.float32)
    amplitudes[1, 0, :] = -4.0
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dc_offset(ds, method="mean")
    # removed_component must equal the per-trace offset, repeated across every sample.
    assert result.removed_component[0, 0, 0] == pytest.approx(9.0)
    assert result.removed_component[1, 0, 0] == pytest.approx(-4.0)
    np.testing.assert_allclose(result.removed_component[0, 0, :], result.removed_component[0, 0, 0])
    reconstructed = result.dataset.amplitudes.astype(np.float64) + result.removed_component.astype(np.float64)
    np.testing.assert_allclose(reconstructed, ds.amplitudes.astype(np.float64), atol=1e-4)


def test_trace_means_after_correction_approach_zero(dataset_factory):
    rng = np.random.default_rng(1)
    amplitudes = (rng.normal(0.0, 1.0, size=(10, 3, 100)) + rng.normal(50.0, 20.0, size=(10, 3, 1))).astype(
        np.float32
    )
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dc_offset(ds, method="mean")
    trace_means_after = result.dataset.amplitudes.astype(np.float64).mean(axis=2)
    np.testing.assert_allclose(trace_means_after, 0.0, atol=1e-3)


def test_nan_input_raises_rather_than_propagating(dataset_factory):
    amplitudes = np.zeros((2, 1, 10), dtype=np.float32)
    amplitudes[0, 0, 3] = np.nan
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    with pytest.raises(ProcessingError):
        correct_dc_offset(ds, method="mean")


def test_invalid_one_sided_window_raises(dataset_factory):
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    with pytest.raises(ProcessingError):
        correct_dc_offset(ds, method="mean", window_start_ns=5.0)


def test_invalid_window_order_raises(dataset_factory):
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    with pytest.raises(ProcessingError):
        correct_dc_offset(ds, method="mean", window_start_ns=20.0, window_end_ns=5.0)


def test_processing_history_entry_is_recorded(dataset_factory):
    amplitudes = np.full((2, 1, 20), 3.0, dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dc_offset(ds, method="median", window_start_ns=0.0, window_end_ns=10.0)
    assert ds.processing_history == ()
    record = result.dataset.processing_history[-1]
    assert record["operation"] == "dc_offset_correction"
    assert record["parameters"]["method"] == "median"
    assert record["diagnostics"]["window_start_ns"] == 0.0


def test_float32_input_produces_float32_output(dataset_factory):
    amplitudes = np.full((2, 1, 20), 3.0, dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dc_offset(ds, method="mean")
    assert result.dataset.amplitudes.dtype == np.float32
    assert result.removed_component.dtype == np.float32


def test_full_trace_mean_without_window_warns_about_direct_wave(dataset_factory):
    amplitudes = np.full((2, 1, 20), 3.0, dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dc_offset(ds, method="mean")
    assert any("direct/air wave" in w for w in result.warnings)


def test_windowed_median_does_not_warn_about_direct_wave(dataset_factory):
    amplitudes = np.full((2, 1, 20), 3.0, dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dc_offset(ds, method="median", window_start_ns=0.0, window_end_ns=5.0)
    assert not any("direct/air wave" in w for w in result.warnings)


# --- valid_mask integration (padding-aware DC offset, e.g. from correct_time_zero) --


def test_padding_is_excluded_from_offset_computation(dataset_factory):
    # Window [0, 20) ns == samples [0, 20) at 1.0 ns/sample. Samples [15, 20) are
    # marked as padding by the mask even though they fall inside the window, and
    # hold an extreme value that must never influence the computed offset.
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    amplitudes[:, 0, :15] = 2.0
    amplitudes[:, 0, 15:20] = 9999.0  # padding-within-window, must be excluded
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    valid_mask = np.ones((1, 40), dtype=bool)
    valid_mask[0, 15:20] = False

    result = correct_dc_offset(
        ds, method="mean", window_start_ns=0.0, window_end_ns=20.0, valid_mask=valid_mask
    )
    assert result.diagnostics["offset_statistics"]["mean"] == pytest.approx(2.0)


def test_padding_is_unaffected_by_the_subtraction(dataset_factory):
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    amplitudes[:, 0, :15] = 2.0
    amplitudes[:, 0, 15:20] = 9999.0
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    valid_mask = np.ones((1, 40), dtype=bool)
    valid_mask[0, 15:20] = False

    result = correct_dc_offset(
        ds, method="mean", window_start_ns=0.0, window_end_ns=20.0, valid_mask=valid_mask
    )
    # Padding at [15:20) must remain exactly 9999.0 -- untouched by the -2.0 offset
    # applied everywhere else, even though 9999.0 sits inside the averaging window.
    np.testing.assert_array_equal(result.dataset.amplitudes[:, 0, 15:20], 9999.0)


def test_zero_padding_value_stays_exactly_zero_after_correction(dataset_factory):
    # Reproduces the audited Sprint 2 bug directly: a time-zero fill_value=0.0
    # padding region must still read exactly 0.0 after DC offset, never `0.0 - offset`.
    amplitudes = np.zeros((3, 1, 30), dtype=np.float32)
    amplitudes[:, 0, :20] = 5.0  # valid region, constant bias to remove
    amplitudes[:, 0, 20:] = 0.0  # padding, exactly at fill_value
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    valid_mask = np.ones((1, 30), dtype=bool)
    valid_mask[0, 20:] = False

    result = correct_dc_offset(ds, method="mean", valid_mask=valid_mask)
    np.testing.assert_array_equal(result.dataset.amplitudes[:, 0, 20:], 0.0)
    assert result.diagnostics["padding_value_statistics"]["min"] == 0.0
    assert result.diagnostics["padding_value_statistics"]["max"] == 0.0
    assert result.diagnostics["padding_value_statistics"]["unique_count"] == 1


def test_valid_region_mean_approaches_zero_while_padding_is_left_alone(dataset_factory):
    rng = np.random.default_rng(7)
    amplitudes = np.zeros((20, 1, 60), dtype=np.float32)
    amplitudes[:, 0, :40] = (rng.normal(0.0, 1.0, size=(20, 40)) + 50.0).astype(np.float32)
    amplitudes[:, 0, 40:] = -777.0  # untouched padding constant, must not be pulled toward zero
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    valid_mask = np.ones((1, 60), dtype=bool)
    valid_mask[0, 40:] = False

    result = correct_dc_offset(ds, method="mean", valid_mask=valid_mask)
    valid_after = result.dataset.amplitudes[:, 0, :40].astype(np.float64)
    padding_after = result.dataset.amplitudes[:, 0, 40:].astype(np.float64)
    assert abs(valid_after.mean()) < 1e-3
    np.testing.assert_array_equal(padding_after, -777.0)


def test_offset_is_computed_only_from_the_window_and_mask_intersection(dataset_factory):
    # window = [0, 30) samples; valid_mask True only for [10, 40).
    # Intersection = [10, 30): only that region may determine the offset.
    amplitudes = np.zeros((2, 1, 50), dtype=np.float32)
    amplitudes[:, 0, :10] = -500.0  # inside window, NOT valid -> must be excluded
    amplitudes[:, 0, 10:30] = 3.0  # inside window AND valid -> the only region used
    amplitudes[:, 0, 30:40] = 500.0  # valid, but OUTSIDE window -> must be excluded
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    valid_mask = np.zeros((1, 50), dtype=bool)
    valid_mask[0, 10:40] = True

    result = correct_dc_offset(
        ds, method="mean", window_start_ns=0.0, window_end_ns=30.0, valid_mask=valid_mask
    )
    assert result.diagnostics["offset_statistics"]["mean"] == pytest.approx(3.0)
    assert result.diagnostics["valid_samples_per_channel_in_window"]["0"] == 20  # [10, 30)


def test_zero_valid_samples_in_window_raises_a_clear_error(dataset_factory):
    amplitudes = np.zeros((2, 1, 40), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    valid_mask = np.zeros((1, 40), dtype=bool)
    valid_mask[0, 30:] = True  # valid only OUTSIDE the window used below

    with pytest.raises(ProcessingError, match="no valid samples"):
        correct_dc_offset(ds, method="mean", window_start_ns=0.0, window_end_ns=20.0, valid_mask=valid_mask)


def test_no_mask_and_an_all_true_mask_produce_identical_results(dataset_factory):
    amplitudes = np.random.default_rng(3).normal(10.0, 2.0, size=(4, 2, 30)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    without_mask = correct_dc_offset(ds, method="mean")
    all_true_mask = np.ones((2, 30), dtype=bool)
    with_all_true_mask = correct_dc_offset(ds, method="mean", valid_mask=all_true_mask)

    np.testing.assert_array_equal(without_mask.dataset.amplitudes, with_all_true_mask.dataset.amplitudes)
    assert (
        without_mask.diagnostics["offset_statistics"] == with_all_true_mask.diagnostics["offset_statistics"]
    )
    assert with_all_true_mask.diagnostics["valid_mask_provided"] is True
    assert without_mask.diagnostics["valid_mask_provided"] is False


def test_input_dataset_is_not_mutated_when_a_valid_mask_is_given(dataset_factory):
    amplitudes = np.full((3, 1, 30), 9.0, dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    original_bytes = ds.amplitudes.tobytes()

    valid_mask = np.ones((1, 30), dtype=bool)
    valid_mask[0, 20:] = False

    correct_dc_offset(ds, method="mean", valid_mask=valid_mask)
    assert ds.amplitudes.tobytes() == original_bytes


def test_processing_history_records_mask_policy_and_diagnostics(dataset_factory):
    amplitudes = np.full((2, 1, 20), 4.0, dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    valid_mask = np.ones((1, 20), dtype=bool)
    valid_mask[0, 15:] = False

    result = correct_dc_offset(ds, method="mean", valid_mask=valid_mask)
    record = result.dataset.processing_history[-1]
    assert record["parameters"]["valid_mask_provided"] is True
    assert "valid_mask" in record["diagnostics"]["mask_policy"]
    assert record["diagnostics"]["valid_samples_per_trace_min"] == 15
    assert record["diagnostics"]["valid_samples_per_trace_max"] == 15
    assert record["diagnostics"]["excluded_padding_count"] == 5


# --- window_reference: dataset_time vs sample_index (Sprint 2.2 / ADR-004) ---------


def test_dataset_time_window_selects_correct_samples(dataset_factory):
    # time_ns = (arange(40) - 10) * dt -- as if target_sample=10 had already been
    # applied by correct_time_zero. Window [5, 15) ns must select exactly the
    # samples whose time_ns falls in that range: samples 15..24 (time_ns 5..14).
    samples_count = 40
    time_ns = (np.arange(samples_count, dtype=np.float64) - 10) * SAMPLING_TIME_NS
    amplitudes = np.zeros((2, 1, samples_count), dtype=np.float32)
    amplitudes[:, 0, :] = np.arange(samples_count, dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS, time_ns=time_ns)

    result = correct_dc_offset(ds, method="mean", window_start_ns=5.0, window_end_ns=15.0)
    assert result.diagnostics["window_reference"] == "dataset_time"
    assert result.diagnostics["window_start_sample"] == 15
    assert result.diagnostics["window_end_sample"] == 25
    assert result.diagnostics["offset_statistics"]["mean"] == pytest.approx(np.arange(15, 25).mean())


def test_dataset_time_window_bounds_are_half_open(dataset_factory):
    samples_count = 40
    time_ns = np.arange(samples_count, dtype=np.float64) * SAMPLING_TIME_NS
    ds = dataset_factory(
        amplitudes=np.zeros((2, 1, samples_count), dtype=np.float32),
        sampling_time_ns=SAMPLING_TIME_NS,
        time_ns=time_ns,
    )
    result = correct_dc_offset(ds, method="mean", window_start_ns=5.0, window_end_ns=15.0)
    # [5, 15) ns at dt=1.0 ns/sample -> exactly 10 samples (5..14); 15.0 itself excluded.
    assert result.diagnostics["window_end_sample"] - result.diagnostics["window_start_sample"] == 10


def test_negative_time_samples_never_enter_a_positive_ns_window(dataset_factory):
    samples_count = 140
    time_ns = (np.arange(samples_count, dtype=np.float64) - 16) * SAMPLING_TIME_NS
    ds = dataset_factory(
        amplitudes=np.zeros((2, 1, samples_count), dtype=np.float32),
        sampling_time_ns=SAMPLING_TIME_NS,
        time_ns=time_ns,
    )
    result = correct_dc_offset(ds, method="mean", window_start_ns=20.0, window_end_ns=100.0)
    selected = time_ns[result.diagnostics["window_start_sample"] : result.diagnostics["window_end_sample"]]
    assert (selected >= 20.0).all()
    assert (selected < 100.0).all()
    assert not (selected < 0).any()


def test_dataset_time_window_intersects_correctly_with_valid_mask(dataset_factory):
    # time_ns relative to a target_sample=10-like shift; valid_mask marks the first
    # 12 samples (time_ns < 2) as padding, even though the window [0, 20) ns would
    # otherwise include some of them.
    samples_count = 40
    time_ns = (np.arange(samples_count, dtype=np.float64) - 10) * SAMPLING_TIME_NS
    amplitudes = np.zeros((2, 1, samples_count), dtype=np.float32)
    amplitudes[:, 0, 10:12] = 9999.0  # inside the window but padding -> must be excluded
    amplitudes[:, 0, 12:30] = 3.0  # inside the window AND valid -> the only region used
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS, time_ns=time_ns)

    valid_mask = np.ones((1, samples_count), dtype=bool)
    valid_mask[0, :12] = False

    result = correct_dc_offset(
        ds, method="mean", window_start_ns=0.0, window_end_ns=20.0, valid_mask=valid_mask
    )
    assert result.diagnostics["offset_statistics"]["mean"] == pytest.approx(3.0)


def test_padding_is_not_counted_in_dataset_time_window_offset(dataset_factory):
    samples_count = 40
    time_ns = (np.arange(samples_count, dtype=np.float64) - 10) * SAMPLING_TIME_NS
    amplitudes = np.zeros((2, 1, samples_count), dtype=np.float32)
    amplitudes[:, 0, 10:12] = 9999.0
    amplitudes[:, 0, 12:30] = 3.0
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS, time_ns=time_ns)

    valid_mask = np.ones((1, samples_count), dtype=bool)
    valid_mask[0, :12] = False

    result = correct_dc_offset(
        ds, method="mean", window_start_ns=0.0, window_end_ns=20.0, valid_mask=valid_mask
    )
    # The padding positions (samples 10, 11) must remain exactly 9999.0 -- untouched.
    np.testing.assert_array_equal(result.dataset.amplitudes[:, 0, 10:12], 9999.0)


def test_zero_valid_samples_in_dataset_time_window_raises_error(dataset_factory):
    samples_count = 40
    time_ns = (np.arange(samples_count, dtype=np.float64) - 10) * SAMPLING_TIME_NS
    ds = dataset_factory(
        amplitudes=np.zeros((2, 1, samples_count), dtype=np.float32),
        sampling_time_ns=SAMPLING_TIME_NS,
        time_ns=time_ns,
    )
    # Window [0, 20) ns -> samples [10, 30) (time_ns = sample - 10). Mark valid only
    # from sample 30 onward, i.e. entirely outside the window.
    valid_mask = np.zeros((1, samples_count), dtype=bool)
    valid_mask[0, 30:] = True

    with pytest.raises(ProcessingError, match="no valid samples"):
        correct_dc_offset(ds, method="mean", window_start_ns=0.0, window_end_ns=20.0, valid_mask=valid_mask)


def test_mean_and_median_use_the_same_window(dataset_factory):
    samples_count = 40
    time_ns = (np.arange(samples_count, dtype=np.float64) - 10) * SAMPLING_TIME_NS
    amplitudes = np.random.default_rng(5).normal(10.0, 2.0, size=(4, 1, samples_count)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS, time_ns=time_ns)

    mean_result = correct_dc_offset(ds, method="mean", window_start_ns=0.0, window_end_ns=20.0)
    median_result = correct_dc_offset(ds, method="median", window_start_ns=0.0, window_end_ns=20.0)

    assert mean_result.diagnostics["window_start_sample"] == median_result.diagnostics["window_start_sample"]
    assert mean_result.diagnostics["window_end_sample"] == median_result.diagnostics["window_end_sample"]
    assert (
        mean_result.diagnostics["valid_samples_per_channel_in_window"]
        == median_result.diagnostics["valid_samples_per_channel_in_window"]
    )
