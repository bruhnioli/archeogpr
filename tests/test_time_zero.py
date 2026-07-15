"""Synthetic tests for archaeogpr.processing.time_zero.correct_time_zero."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from archaeogpr.processing.common import TIME_ZERO_REFERENCE_WARNING, ProcessingError, padding_mask
from archaeogpr.processing.time_zero import correct_time_zero

SAMPLING_TIME_NS = 0.5  # -> 2 samples/ns, so 10-30 ns search window = samples [20, 60)


def _single_pulse_dataset(
    dataset_factory, *, channel=0, sample=40, amplitude=1.0, channels_count=3, samples_count=200
):
    amplitudes = np.zeros((6, channels_count, samples_count), dtype=np.float32)
    amplitudes[:, channel, sample] = amplitude
    return dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)


# --- peak-polarity correctness -------------------------------------------------


def test_max_abs_finds_correct_sample_for_a_negative_pulse(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, amplitude=-500.0)
    result = correct_time_zero(
        ds, method="channel_median_peak", search_start_ns=10.0, search_end_ns=30.0, peak_polarity="max_abs"
    )
    assert result.diagnostics["channel_picks"]["0"] == 40


def test_positive_peak_finds_the_positive_pulse_even_if_a_larger_negative_pulse_exists(dataset_factory):
    amplitudes = np.zeros((6, 1, 200), dtype=np.float32)
    amplitudes[:, 0, 35] = 50.0  # smaller positive
    amplitudes[:, 0, 45] = -900.0  # larger negative, must be ignored by positive_peak
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_time_zero(
        ds,
        method="channel_median_peak",
        search_start_ns=10.0,
        search_end_ns=30.0,
        peak_polarity="positive_peak",
    )
    assert result.diagnostics["channel_picks"]["0"] == 35


def test_negative_peak_finds_the_negative_pulse_even_if_a_larger_positive_pulse_exists(dataset_factory):
    amplitudes = np.zeros((6, 1, 200), dtype=np.float32)
    amplitudes[:, 0, 35] = 900.0  # larger positive, must be ignored by negative_peak
    amplitudes[:, 0, 45] = -50.0  # smaller negative
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_time_zero(
        ds,
        method="channel_median_peak",
        search_start_ns=10.0,
        search_end_ns=30.0,
        peak_polarity="negative_peak",
    )
    assert result.diagnostics["channel_picks"]["0"] == 45


# --- manual picks ---------------------------------------------------------------


def test_manual_pick_applies_correct_shift(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, amplitude=100.0, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=10)
    assert result.diagnostics["channel_shifts"]["0"] == -30
    assert result.dataset.amplitudes[0, 0, 10] == pytest.approx(100.0)


def test_manual_pick_requires_all_channels(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channels_count=3)
    with pytest.raises(ProcessingError, match="missing channel"):
        correct_time_zero(ds, method="manual", picks={0: 40, 1: 41})


# --- channel-wide (not per-trace) shifting --------------------------------------


def test_channel_wide_shift_is_applied_identically_to_every_slice(dataset_factory):
    channels_count, samples_count = 1, 200
    amplitudes = np.zeros((5, channels_count, samples_count), dtype=np.float32)
    amplitudes[:4, 0, 40] = 100.0  # 4 of 5 slices agree the event is at sample 40
    amplitudes[4, 0, 90] = 100.0  # one outlier slice has its own peak at sample 90
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    result = correct_time_zero(
        ds, method="channel_median_peak", search_start_ns=10.0, search_end_ns=60.0, target_sample=0
    )
    # Median trace picks sample 40 (the majority), so shift = -40 for the WHOLE channel.
    assert result.diagnostics["channel_shifts"]["0"] == -40
    # The outlier slice's own peak (at 90) must have moved to 90-40=50, NOT to 0 —
    # proving the shift is channel-wide, not independently fitted per trace.
    assert result.dataset.amplitudes[4, 0, 50] == pytest.approx(100.0)
    assert result.dataset.amplitudes[4, 0, 0] == pytest.approx(0.0)


# --- shifting mechanics: wrap-around, padding, shape, immutability -------------


def test_no_wrap_around_garbage_after_shift(dataset_factory):
    channels_count, samples_count = 1, 50
    amplitudes = np.arange(6 * channels_count * samples_count, dtype=np.float32).reshape(
        6, channels_count, samples_count
    )
    amplitudes[:, 0, 20] += 10_000.0  # a findable peak on top of the ramp, at sample 20
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    result = correct_time_zero(ds, method="manual", picks={0: 20}, target_sample=0, fill_value=-1.0)
    # shift = 0 - 20 = -20: the last 20 samples are padding and must be exactly fill_value,
    # never a wrapped-around copy of the original first 20 samples.
    np.testing.assert_array_equal(result.dataset.amplitudes[:, 0, -20:], -1.0)


def test_padding_mask_matches_diagnostics_padding_counts(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=5)
    shift = result.diagnostics["channel_shifts"]["0"]
    expected_count = int(padding_mask(shift, ds.shape[2]).sum())
    assert result.diagnostics["padding_sample_counts"]["0"] == expected_count
    assert expected_count == abs(shift)


def test_output_shape_matches_input_shape(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channels_count=4, samples_count=150)
    result = correct_time_zero(ds, method="manual", picks={c: 40 for c in range(4)})
    assert result.dataset.shape == ds.shape
    assert result.removed_component.shape == ds.shape


def test_input_dataset_is_not_mutated(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=2)
    original_bytes = ds.amplitudes.tobytes()
    correct_time_zero(ds, method="channel_median_peak", search_start_ns=10.0, search_end_ns=30.0)
    assert ds.amplitudes.tobytes() == original_bytes


# --- search window behavior ------------------------------------------------------


def test_strong_event_outside_search_window_is_ignored(dataset_factory):
    amplitudes = np.zeros((6, 1, 200), dtype=np.float32)
    amplitudes[:, 0, 150] = 1_000_000.0  # huge, but far outside the search window
    amplitudes[:, 0, 40] = 50.0  # small, but inside the search window
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    result = correct_time_zero(
        ds, method="channel_median_peak", search_start_ns=10.0, search_end_ns=30.0, peak_polarity="max_abs"
    )
    assert result.diagnostics["channel_picks"]["0"] == 40


def test_invalid_search_window_raises(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory)
    with pytest.raises(ProcessingError):
        correct_time_zero(ds, method="channel_median_peak", search_start_ns=30.0, search_end_ns=10.0)


# --- max_shift_samples overflow policy --------------------------------------------


def test_shift_exceeding_max_shift_samples_is_clipped_with_warning_when_clip_is_requested(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=100, channels_count=1)
    result = correct_time_zero(
        ds, method="manual", picks={0: 100}, target_sample=0, max_shift_samples=10, overflow_policy="clip"
    )
    assert result.diagnostics["channel_shifts"]["0"] == -10
    assert any("clipped" in w for w in result.warnings)


def test_default_overflow_policy_aborts_before_touching_any_data(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=100, channels_count=1)
    original_bytes = ds.amplitudes.tobytes()
    with pytest.raises(ProcessingError, match="max_shift_samples"):
        correct_time_zero(ds, method="manual", picks={0: 100}, target_sample=0, max_shift_samples=10)
    # Confirms the default really is "error", not a silent clip: the input must be
    # completely untouched by the aborted call, and no partial result exists at all.
    assert ds.amplitudes.tobytes() == original_bytes


def test_overflow_policy_error_also_aborts_when_passed_explicitly(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=100, channels_count=1)
    with pytest.raises(ProcessingError, match="max_shift_samples"):
        correct_time_zero(
            ds,
            method="manual",
            picks={0: 100},
            target_sample=0,
            max_shift_samples=10,
            overflow_policy="error",
        )


def test_clipped_result_is_only_reachable_via_explicit_opt_in(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=100, channels_count=1)
    kwargs = dict(method="manual", picks={0: 100}, target_sample=0, max_shift_samples=10)

    with pytest.raises(ProcessingError):
        correct_time_zero(ds, **kwargs)  # default -> no clipped result reachable this way

    clipped = correct_time_zero(ds, **kwargs, overflow_policy="clip")  # explicit opt-in -> succeeds
    assert clipped.diagnostics["has_clipped_shifts"] is True


def test_clipped_result_is_marked_invalid_for_downstream_processing(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=100, channels_count=1)
    result = correct_time_zero(
        ds, method="manual", picks={0: 100}, target_sample=0, max_shift_samples=10, overflow_policy="clip"
    )
    assert result.diagnostics["has_clipped_shifts"] is True
    assert result.diagnostics["valid_for_downstream_processing"] is False
    assert result.diagnostics["requested_shifts"]["0"] == -100
    assert result.diagnostics["channel_shifts"]["0"] == -10


def test_non_clipped_result_is_marked_valid_for_downstream_processing(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=0, max_shift_samples=64)
    assert result.diagnostics["has_clipped_shifts"] is False
    assert result.diagnostics["valid_for_downstream_processing"] is True
    assert result.diagnostics["requested_shifts"]["0"] == result.diagnostics["channel_shifts"]["0"]


# --- valid_mask / padding-mask correctness -----------------------------------------


def test_valid_mask_marks_trailing_samples_as_padding_for_a_left_shift(dataset_factory):
    # pick=40, target=0 -> shift = 0 - 40 = -40 (a "left" shift): the LAST 40
    # samples are padding (np.roll wraps the front around to the tail, which
    # then gets overwritten by fill_value).
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1, samples_count=200)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=0)
    assert result.diagnostics["channel_shifts"]["0"] == -40
    mask = result.valid_mask[0]
    assert not mask[-40:].any()
    assert mask[:-40].all()


def test_valid_mask_marks_leading_samples_as_padding_for_a_right_shift(dataset_factory):
    # pick=10, target=50 -> shift = 50 - 10 = +40 (a "right" shift): the FIRST
    # 40 samples are padding.
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=10, channels_count=1, samples_count=200)
    result = correct_time_zero(ds, method="manual", picks={0: 10}, target_sample=50)
    assert result.diagnostics["channel_shifts"]["0"] == 40
    mask = result.valid_mask[0]
    assert not mask[:40].any()
    assert mask[40:].all()


def test_valid_mask_is_all_true_when_shift_is_zero(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1, samples_count=200)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=40)
    assert result.diagnostics["channel_shifts"]["0"] == 0
    assert result.valid_mask[0].all()


def test_valid_mask_shape_matches_channels_and_samples(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channels_count=4, samples_count=150)
    result = correct_time_zero(ds, method="manual", picks={c: 40 for c in range(4)})
    assert result.valid_mask.shape == (4, 150)
    assert result.valid_mask.dtype == np.bool_


def test_valid_mask_is_read_only(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40})
    assert result.valid_mask.flags.writeable is False
    with pytest.raises(ValueError):
        result.valid_mask[0, 0] = False


# --- corrected (time-zero-relative) time axis (Sprint 2.2 / ADR-004) ---------------


def test_time_ns_at_target_sample_is_exactly_zero(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=16)
    assert result.dataset.time_ns[16] == pytest.approx(0.0, abs=1e-9)


def test_time_before_target_sample_is_negative(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=16)
    assert (result.dataset.time_ns[:16] < 0).all()


def test_time_after_target_sample_is_positive(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=16)
    assert (result.dataset.time_ns[17:] > 0).all()


def test_corrected_time_axis_preserves_the_sample_interval(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=16)
    assert np.allclose(np.diff(result.dataset.time_ns), SAMPLING_TIME_NS)


def test_target_sample_zero_time_axis_starts_at_zero(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=0)
    assert result.dataset.time_ns[0] == pytest.approx(0.0, abs=1e-9)


def test_target_sample_16_sample_zero_is_minus_16_dt(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=16)
    assert result.dataset.time_ns[0] == pytest.approx(-16 * SAMPLING_TIME_NS)


def test_input_time_axis_is_not_mutated(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    original_time_ns = ds.time_ns.copy()
    correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=16)
    np.testing.assert_array_equal(ds.time_ns, original_time_ns)


def test_corrected_time_axis_is_read_only(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=16)
    assert result.dataset.time_ns.flags.writeable is False
    with pytest.raises(ValueError):
        result.dataset.time_ns[0] = 123.0


def test_time_axis_diagnostics_record_target_and_reference(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40}, target_sample=16)
    time_axis = result.diagnostics["time_axis"]
    assert time_axis["target_sample"] == 16
    assert time_axis["time_zero_reference_ns"] == 0.0
    assert time_axis["previous_time_ns_start"] == pytest.approx(0.0)
    assert time_axis["corrected_time_ns_start"] == pytest.approx(-16 * SAMPLING_TIME_NS)


def test_sampling_time_ns_is_now_required_for_manual_method_too(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    ds_no_sampling = replace(ds, metadata={"radar": {}, "warnings": []})
    with pytest.raises(ProcessingError, match="sampling_time_ns"):
        correct_time_zero(ds_no_sampling, method="manual", picks={0: 40}, target_sample=0)


# --- processing history + the required time-zero warning ------------------------


def test_processing_history_entry_is_recorded(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40})
    assert ds.processing_history == ()  # input untouched
    record = result.dataset.processing_history[-1]
    assert record["operation"] == "time_zero_correction"
    assert record["parameters"]["method"] == "manual"
    assert "channel_shifts" in record["diagnostics"]


def test_time_zero_reference_warning_is_always_present(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=1)
    result = correct_time_zero(ds, method="manual", picks={0: 40})
    assert TIME_ZERO_REFERENCE_WARNING in result.warnings


# --- end-to-end alignment check --------------------------------------------------


def test_corrected_channel_median_picks_align_at_target_sample(dataset_factory):
    channels_count, samples_count = 3, 200
    amplitudes = np.zeros((8, channels_count, samples_count), dtype=np.float32)
    for channel, sample in enumerate((35, 42, 50)):
        amplitudes[:, channel, sample] = 100.0
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    result = correct_time_zero(
        ds,
        method="channel_median_peak",
        search_start_ns=10.0,
        search_end_ns=30.0,
        target_sample=5,
        max_shift_samples=64,
    )
    # Re-pick on the corrected dataset: every channel's median peak must now sit at target_sample=5.
    verification = correct_time_zero(
        result.dataset,
        method="channel_median_peak",
        search_start_ns=0.0,
        search_end_ns=100.0,
        target_sample=5,
    )
    for channel in range(channels_count):
        assert verification.diagnostics["channel_picks"][str(channel)] == 5


# --- removed_component identity --------------------------------------------------


def test_removed_component_identity_holds_exactly(dataset_factory):
    ds = _single_pulse_dataset(dataset_factory, channel=0, sample=40, channels_count=2, samples_count=100)
    result = correct_time_zero(ds, method="manual", picks={0: 40, 1: 40}, target_sample=5)
    reconstructed = result.dataset.amplitudes.astype(np.float64) + result.removed_component.astype(np.float64)
    np.testing.assert_allclose(reconstructed, ds.amplitudes.astype(np.float64))


# --- noise and DC-bias robustness (picker stability) -----------------------------


def test_picking_is_robust_to_gaussian_noise(dataset_factory):
    rng = np.random.default_rng(42)
    channels_count, samples_count = 1, 200
    amplitudes = rng.normal(0.0, 0.5, size=(10, channels_count, samples_count)).astype(np.float32)
    amplitudes[:, 0, 40] += 200.0  # large, clearly-findable pulse on top of light noise
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    result = correct_time_zero(
        ds, method="channel_median_peak", search_start_ns=10.0, search_end_ns=30.0, peak_polarity="max_abs"
    )
    assert result.diagnostics["channel_picks"]["0"] == 40


def test_picking_is_robust_to_dc_bias(dataset_factory):
    channels_count, samples_count = 1, 200
    amplitudes = np.full(
        (6, channels_count, samples_count), 5000.0, dtype=np.float32
    )  # strong constant DC bias
    amplitudes[:, 0, 40] += 50.0  # small pulse riding on top of the bias
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    result = correct_time_zero(
        ds, method="channel_median_peak", search_start_ns=10.0, search_end_ns=30.0, peak_polarity="max_abs"
    )
    assert result.diagnostics["channel_picks"]["0"] == 40


def test_picking_near_search_window_edge(dataset_factory):
    # Window is samples [20, 60); put the pulse one sample inside each edge.
    amplitudes = np.zeros((6, 1, 200), dtype=np.float32)
    amplitudes[:, 0, 21] = 300.0
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_time_zero(
        ds, method="channel_median_peak", search_start_ns=10.0, search_end_ns=30.0, peak_polarity="max_abs"
    )
    assert result.diagnostics["channel_picks"]["0"] == 21
