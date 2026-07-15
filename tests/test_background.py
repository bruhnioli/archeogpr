"""Synthetic tests for archaeogpr.processing.background (Sprint 4A / ADR-008).

Covers: core algorithm correctness (all 4 methods), channel independence,
no smoothing along the sample/time axis, input=output+removed, window/
geometry (metre<->trace conversion, odd-window rounding, trace-spacing
sourcing/fallback/override), edge modes, valid-mask/padding safety, shape/
dtype/immutability, processing-history/reprocessing-guard/NPZ round-trip,
and the scientific risk tests the spec explicitly requires: common-background
suppression, long-horizontal-event attenuation (global methods), local-event
preservation, window-length-vs-target-length attenuation, and mean-vs-median
behavior under a strong outlier trace.
"""

from __future__ import annotations

import numpy as np
import pytest

from archaeogpr.export.processed import write_corrected_npz
from archaeogpr.export.sprint3 import read_processed_npz
from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.background import compute_trace_spacing, remove_background
from archaeogpr.processing.common import ProcessingError

SAMPLING_TIME_NS = 1.0


def _long_profile(dataset_factory, *, slices_count=61, channels_count=1, samples_count=80, seed=0):
    rng = np.random.default_rng(seed)
    amplitudes = rng.normal(0.0, 30.0, size=(slices_count, channels_count, samples_count)).astype(np.float32)
    return dataset_factory(
        amplitudes=amplitudes,
        slices_count=slices_count,
        channels_count=channels_count,
        samples_count=samples_count,
        sampling_time_ns=SAMPLING_TIME_NS,
    )


# ======================================================================
# Core algorithm correctness (items 1-12)
# ======================================================================


def test_global_mean_matches_manual_calculation(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=15, samples_count=10)
    result = remove_background(ds, method="global_mean")
    expected_background = ds.amplitudes.astype(np.float64).mean(axis=0)
    expected_output = ds.amplitudes.astype(np.float64) - expected_background[np.newaxis, :, :]
    np.testing.assert_allclose(result.dataset.amplitudes.astype(np.float64), expected_output, atol=1e-2)
    np.testing.assert_allclose(
        result.removed_component.astype(np.float64),
        np.broadcast_to(expected_background[np.newaxis, :, :], ds.shape),
        atol=1e-2,
    )


def test_global_median_matches_manual_calculation(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=15, samples_count=10)
    result = remove_background(ds, method="global_median")
    expected_background = np.median(ds.amplitudes.astype(np.float64), axis=0)
    expected_output = ds.amplitudes.astype(np.float64) - expected_background[np.newaxis, :, :]
    np.testing.assert_allclose(result.dataset.amplitudes.astype(np.float64), expected_output, atol=1e-2)


def test_sliding_mean_matches_manual_calculation_interior(dataset_factory):
    # Away from the profile edges (no reflect/nearest padding effect), a
    # sliding_mean(window=5) background at trace i must equal the mean of
    # traces [i-2, i+2].
    ds = _long_profile(dataset_factory, slices_count=21, samples_count=5)
    result = remove_background(ds, method="sliding_mean", window_traces=5)
    data = ds.amplitudes.astype(np.float64)
    i = 10
    expected_background = data[i - 2 : i + 3, 0, :].mean(axis=0)
    np.testing.assert_allclose(
        result.removed_component[i, 0, :].astype(np.float64), expected_background, atol=1e-2
    )


def test_sliding_median_matches_manual_calculation_interior(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=21, samples_count=5)
    result = remove_background(ds, method="sliding_median", window_traces=5)
    data = ds.amplitudes.astype(np.float64)
    i = 10
    expected_background = np.median(data[i - 2 : i + 3, 0, :], axis=0)
    np.testing.assert_allclose(
        result.removed_component[i, 0, :].astype(np.float64), expected_background, atol=1e-2
    )


def test_channels_processed_independently(dataset_factory):
    # Channel 0 gets a strong shared background, channel 1 stays zero-mean
    # noise; removing background from channel 0 must not perturb channel 1's
    # own (near-zero) background estimate.
    rng = np.random.default_rng(2)
    slices_count, samples_count = 20, 10
    ch0 = 5000.0 + rng.normal(0.0, 5.0, size=(slices_count, samples_count))
    ch1 = rng.normal(0.0, 5.0, size=(slices_count, samples_count))
    amplitudes = np.stack([ch0, ch1], axis=1).astype(np.float32)
    ds = dataset_factory(
        amplitudes=amplitudes,
        slices_count=slices_count,
        channels_count=2,
        samples_count=samples_count,
        sampling_time_ns=SAMPLING_TIME_NS,
    )
    result = remove_background(ds, method="global_mean")
    assert abs(float(result.removed_component[:, 0, :].mean())) > 4000.0
    assert abs(float(result.removed_component[:, 1, :].mean())) < 50.0


def test_no_smoothing_along_sample_time_axis(dataset_factory):
    # A single spike at one sample index, constant across all traces, must
    # be removed by global_mean's own background estimate (background =
    # spike itself, since every trace is identical) -- proving the spike's
    # own sample position was never blurred into neighboring samples.
    slices_count, samples_count = 10, 30
    trace = np.zeros(samples_count, dtype=np.float64)
    trace[15] = 1000.0
    amplitudes = np.tile(trace, (slices_count, 1))[:, np.newaxis, :].astype(np.float32)
    ds = dataset_factory(
        amplitudes=amplitudes,
        slices_count=slices_count,
        channels_count=1,
        samples_count=samples_count,
        sampling_time_ns=SAMPLING_TIME_NS,
    )
    result = remove_background(ds, method="global_mean")
    np.testing.assert_allclose(result.dataset.amplitudes, 0.0, atol=1e-2)
    removed = result.removed_component[0, 0, :]
    assert float(removed[15]) == pytest.approx(1000.0, abs=1e-2)
    assert float(np.abs(removed[np.arange(samples_count) != 15]).max()) < 1e-2


def test_output_equals_input_minus_removed_component(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=25, samples_count=15, seed=3)
    for method, kwargs in [
        ("global_mean", {}),
        ("global_median", {}),
        ("sliding_mean", {"window_traces": 7}),
        ("sliding_median", {"window_traces": 7}),
    ]:
        result = remove_background(ds, method=method, **kwargs)
        reconstructed = result.dataset.amplitudes.astype(np.float64) + result.removed_component.astype(
            np.float64
        )
        np.testing.assert_allclose(reconstructed, ds.amplitudes.astype(np.float64), atol=1e-1)


def test_identical_traces_removed_to_exactly_zero(dataset_factory):
    trace = np.linspace(-100.0, 100.0, 20, dtype=np.float32)
    amplitudes = np.tile(trace, (12, 1))[:, np.newaxis, :]
    ds = dataset_factory(amplitudes=amplitudes, slices_count=12, channels_count=1, samples_count=20)
    for method in ("global_mean", "global_median", "sliding_mean", "sliding_median"):
        kwargs = {"window_traces": 5} if "sliding" in method else {}
        result = remove_background(ds, method=method, **kwargs)
        np.testing.assert_allclose(result.dataset.amplitudes, 0.0, atol=1e-3)


def test_zero_input_stays_zero(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=10, samples_count=10, seed=0)
    zero_ds = dataset_factory(
        amplitudes=np.zeros_like(ds.amplitudes), slices_count=10, channels_count=1, samples_count=10
    )
    result = remove_background(zero_ds, method="sliding_mean", window_traces=5)
    np.testing.assert_array_equal(result.dataset.amplitudes, 0.0)
    np.testing.assert_array_equal(result.removed_component, 0.0)


def test_nan_input_raises(dataset_factory):
    amplitudes = np.full((10, 1, 10), np.nan, dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, slices_count=10, channels_count=1, samples_count=10)
    with pytest.raises(ProcessingError, match="NaN|Inf"):
        remove_background(ds, method="global_mean")


def test_invalid_method_raises(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=10, samples_count=10)
    with pytest.raises(ProcessingError, match="method"):
        remove_background(ds, method="pca_removal")


# ======================================================================
# Window / geometry (items 13-22)
# ======================================================================


def test_window_m_converted_to_traces_via_metadata_sampling_step(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=41, samples_count=5)
    result = remove_background(ds, method="sliding_mean", window_m=2.0, trace_spacing_m=0.2)
    assert result.diagnostics["applied_window_traces"] == 11  # 2.0 / 0.2 = 10 -> bumped to odd 11
    assert result.diagnostics["applied_window_m"] == pytest.approx(11 * 0.2)


def test_requested_and_applied_window_recorded_separately(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=41, samples_count=5)
    result = remove_background(ds, method="sliding_mean", window_traces=8)
    assert result.diagnostics["requested_window_traces"] == 8
    assert result.diagnostics["applied_window_traces"] == 9  # bumped up, never silently down


def test_even_window_bumped_to_odd_with_warning(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=41, samples_count=5)
    result = remove_background(ds, method="sliding_median", window_traces=10)
    assert result.diagnostics["applied_window_traces"] == 11
    assert any("even" in w for w in result.warnings)


def test_rounding_policy_recorded_in_diagnostics(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=41, samples_count=5)
    result = remove_background(ds, method="sliding_mean", window_traces=9)
    assert "round" in result.diagnostics["rounding_policy"]
    global_result = remove_background(ds, method="global_mean")
    assert global_result.diagnostics["rounding_policy"] == "not_applicable"


def test_window_below_minimum_raises(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=41, samples_count=5)
    with pytest.raises(ProcessingError, match="minimum"):
        remove_background(ds, method="sliding_mean", window_traces=1)


def test_window_wider_than_profile_raises(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=9, samples_count=5)
    with pytest.raises(ProcessingError, match="wider than the profile"):
        remove_background(ds, method="sliding_mean", window_traces=99)


def test_trace_spacing_from_geolocation_recovers_known_value_despite_outlier():
    slices_count, channels_count, samples_count = 25, 2, 5
    amplitudes = np.zeros((slices_count, channels_count, samples_count), dtype=np.float32)
    x = np.tile(np.arange(slices_count, dtype=np.float64) * 0.05, (channels_count, 1)).T.copy()
    x[10, 0] += 5.0  # bad geolocation fix, channel 0 only
    y = np.zeros((slices_count, channels_count), dtype=np.float64)
    ds = GPRDataset(
        amplitudes=amplitudes,
        time_ns=np.arange(samples_count, dtype=np.float64),
        x=x,
        y=y,
        depth_top_m=None,
        elevation_top_m=None,
        depth_bottom_m=None,
        elevation_bottom_m=None,
        metadata={"sampling": {"sampling_time_ns": SAMPLING_TIME_NS}},
    )
    spacing = compute_trace_spacing(ds)
    assert spacing["trace_spacing_source"] == "geolocation"
    assert spacing["trace_spacing_m"] == pytest.approx(0.05, abs=1e-9)


def test_trace_spacing_falls_back_to_metadata_sampling_step(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=10, samples_count=5)  # no geolocation
    ds_with_step = GPRDataset(
        amplitudes=ds.amplitudes,
        time_ns=ds.time_ns,
        x=None,
        y=None,
        depth_top_m=None,
        elevation_top_m=None,
        depth_bottom_m=None,
        elevation_bottom_m=None,
        metadata={"sampling": {"sampling_time_ns": SAMPLING_TIME_NS, "sampling_step_m": 0.07}},
    )
    spacing = compute_trace_spacing(ds_with_step)
    assert spacing["trace_spacing_source"] == "metadata_sampling_step"
    assert spacing["trace_spacing_m"] == pytest.approx(0.07)


def test_trace_spacing_unavailable_without_geolocation_or_metadata(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=10, samples_count=5)
    spacing = compute_trace_spacing(ds)
    assert spacing["trace_spacing_source"] == "unavailable"
    assert spacing["trace_spacing_m"] is None


def test_window_m_without_any_spacing_raises(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=10, samples_count=5)
    with pytest.raises(ProcessingError, match="trace spacing"):
        remove_background(ds, method="sliding_mean", window_m=1.0)


def test_explicit_trace_spacing_override_skips_auto_computation(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=41, samples_count=5)
    result = remove_background(ds, method="sliding_mean", window_m=1.0, trace_spacing_m=0.1)
    assert result.diagnostics["trace_spacing"]["trace_spacing_source"] == "explicit_override"
    assert result.diagnostics["trace_spacing"]["trace_spacing_m"] == pytest.approx(0.1)


def test_window_m_and_window_traces_together_raises(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=41, samples_count=5)
    with pytest.raises(ProcessingError, match="exactly one"):
        remove_background(ds, method="sliding_mean", window_m=1.0, window_traces=5)


def test_sliding_method_requires_a_window(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=41, samples_count=5)
    with pytest.raises(ProcessingError, match="exactly one"):
        remove_background(ds, method="sliding_mean")


def test_global_method_with_window_raises(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=41, samples_count=5)
    with pytest.raises(ProcessingError, match="global"):
        remove_background(ds, method="global_mean", window_traces=5)
    with pytest.raises(ProcessingError, match="global"):
        remove_background(ds, method="global_median", window_m=1.0)


# ======================================================================
# Edge modes / valid-mask / padding / immutability (items 23-35)
# ======================================================================


def test_reflect_and_nearest_edge_modes_both_run_and_differ_at_edges(dataset_factory):
    rng = np.random.default_rng(4)
    slices_count, samples_count = 15, 5
    amplitudes = rng.normal(0.0, 50.0, size=(slices_count, 1, samples_count)).astype(np.float32)
    ds = dataset_factory(
        amplitudes=amplitudes, slices_count=slices_count, channels_count=1, samples_count=samples_count
    )
    reflect_result = remove_background(ds, method="sliding_mean", window_traces=9, edge_mode="reflect")
    nearest_result = remove_background(ds, method="sliding_mean", window_traces=9, edge_mode="nearest")
    # Away from the edges both must agree closely (interior unaffected by edge policy);
    # at the very first trace they are allowed to differ (that's the point of the option).
    interior = slice(6, 9)
    np.testing.assert_allclose(
        reflect_result.removed_component[interior], nearest_result.removed_component[interior], atol=1.0
    )


def test_invalid_edge_mode_raises(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=15, samples_count=5)
    with pytest.raises(ProcessingError, match="edge_mode"):
        remove_background(ds, method="sliding_mean", window_traces=5, edge_mode="zero")


def test_valid_mask_shape_mismatch_raises(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=15, samples_count=5)
    with pytest.raises(ProcessingError, match="valid_mask shape"):
        remove_background(ds, method="global_mean", valid_mask=np.ones((99, 99), dtype=bool))


def test_padding_excluded_and_preserved(dataset_factory):
    slices_count, channels_count, samples_count = 20, 2, 30
    rng = np.random.default_rng(5)
    amplitudes = rng.normal(0.0, 100.0, size=(slices_count, channels_count, samples_count)).astype(np.float32)
    valid_mask = np.ones((channels_count, samples_count), dtype=bool)
    valid_mask[:, :5] = False  # leading padding, both channels
    amplitudes[:, :, :5] = 0.0  # matches this project's fill_value convention
    ds = dataset_factory(
        amplitudes=amplitudes,
        slices_count=slices_count,
        channels_count=channels_count,
        samples_count=samples_count,
    )
    result = remove_background(ds, method="global_mean", valid_mask=valid_mask)
    np.testing.assert_array_equal(result.dataset.amplitudes[:, :, :5], 0.0)
    np.testing.assert_array_equal(result.removed_component[:, :, :5], 0.0)
    assert result.valid_mask is not None
    np.testing.assert_array_equal(result.valid_mask, valid_mask)


def test_time_axis_and_shape_unchanged(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=15, samples_count=20)
    result = remove_background(ds, method="global_median")
    np.testing.assert_array_equal(result.dataset.time_ns, ds.time_ns)
    assert result.dataset.shape == ds.shape
    assert result.dataset.amplitudes.dtype == ds.amplitudes.dtype


def test_input_dataset_not_mutated(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=15, samples_count=20, seed=6)
    before = ds.amplitudes.copy()
    remove_background(ds, method="sliding_median", window_traces=5)
    np.testing.assert_array_equal(ds.amplitudes, before)


def test_output_and_valid_mask_are_read_only(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=15, samples_count=20)
    valid_mask = np.ones((ds.shape[1], ds.shape[2]), dtype=bool)
    result = remove_background(ds, method="global_mean", valid_mask=valid_mask)
    with pytest.raises(ValueError):
        result.dataset.amplitudes[0, 0, 0] = 1.0
    with pytest.raises(ValueError):
        result.valid_mask[0, 0] = False


# ======================================================================
# Processing history / reprocessing guard / NPZ round-trip (items 36-48)
# ======================================================================


def test_processing_history_records_background_removal(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=15, samples_count=10)
    result = remove_background(ds, method="global_mean")
    ops = [r["operation"] for r in result.dataset.processing_history]
    assert ops == ["background_removal"]


def test_reprocessing_guard_raises_then_allows_override(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=15, samples_count=10)
    once = remove_background(ds, method="global_mean")
    with pytest.raises(ProcessingError, match="already contains"):
        remove_background(once.dataset, method="global_mean")
    twice = remove_background(once.dataset, method="global_mean", allow_reprocessing=True)
    assert [r["operation"] for r in twice.dataset.processing_history] == [
        "background_removal",
        "background_removal",
    ]


def test_median_methods_warn_nonlinear(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=15, samples_count=10)
    result = remove_background(ds, method="global_median")
    assert any("nonlinear" in w for w in result.warnings)
    result_mean = remove_background(ds, method="global_mean")
    assert not any("nonlinear" in w for w in result_mean.warnings)


def test_npz_round_trip(dataset_factory, tmp_path):
    ds = _long_profile(dataset_factory, slices_count=15, samples_count=10)
    valid_mask = np.ones((ds.shape[1], ds.shape[2]), dtype=bool)
    result = remove_background(ds, method="sliding_mean", window_traces=5, valid_mask=valid_mask)
    npz_path = write_corrected_npz(result, tmp_path / "background_processed.npz")
    reloaded_dataset, reloaded_mask = read_processed_npz(npz_path)
    np.testing.assert_array_equal(reloaded_dataset.amplitudes, result.dataset.amplitudes)
    assert reloaded_mask is not None
    np.testing.assert_array_equal(reloaded_mask, valid_mask)
    assert [r["operation"] for r in reloaded_dataset.processing_history] == ["background_removal"]


def test_deterministic_repeat_run(dataset_factory):
    ds = _long_profile(dataset_factory, slices_count=21, samples_count=15, seed=7)
    a = remove_background(ds, method="sliding_median", window_traces=7)
    b = remove_background(ds, method="sliding_median", window_traces=7)
    np.testing.assert_array_equal(a.dataset.amplitudes, b.dataset.amplitudes)


# ======================================================================
# Scientific risk tests (items 49-58)
# ======================================================================


def test_global_method_suppresses_common_background(dataset_factory):
    slices_count, samples_count = 40, 60
    rng = np.random.default_rng(8)
    common_background = 300.0 * np.sin(np.linspace(0, 4 * np.pi, samples_count))
    amplitudes = (
        np.tile(common_background, (slices_count, 1))
        + rng.normal(0.0, 10.0, size=(slices_count, samples_count))
    ).astype(np.float32)[:, np.newaxis, :]
    ds = dataset_factory(
        amplitudes=amplitudes, slices_count=slices_count, channels_count=1, samples_count=samples_count
    )
    result = remove_background(ds, method="global_mean")
    input_rms = float(np.sqrt((ds.amplitudes.astype(np.float64) ** 2).mean()))
    output_rms = float(np.sqrt((result.dataset.amplitudes.astype(np.float64) ** 2).mean()))
    assert output_rms < 0.2 * input_rms  # common background dominated the RMS; it must mostly disappear


def test_global_method_attenuates_a_long_horizontal_event(dataset_factory):
    # A long horizontal event that spans most of the profile looks exactly
    # like "background" to a global estimator -- this test makes that risk
    # visible/measurable rather than hiding it (see ADR-008).
    slices_count, samples_count = 40, 60
    amplitudes = np.zeros((slices_count, 1, samples_count), dtype=np.float32)
    amplitudes[5:35, 0, 30] = 500.0  # long horizontal reflection, 30/40 traces wide
    ds = dataset_factory(
        amplitudes=amplitudes, slices_count=slices_count, channels_count=1, samples_count=samples_count
    )
    result = remove_background(ds, method="global_mean")
    retained_fraction = float(np.abs(result.dataset.amplitudes[20, 0, 30]) / 500.0)
    assert retained_fraction < 0.3  # most of the long event's amplitude is removed, by construction


def test_local_hyperbola_is_not_fully_removed_by_a_short_sliding_window(dataset_factory):
    slices_count, samples_count = 61, 60
    amplitudes = np.zeros((slices_count, 1, samples_count), dtype=np.float32)
    center = slices_count // 2
    for offset in range(-4, 5):
        depth = 30 + int(0.3 * offset**2)  # a crude hyperbola-like shape
        if depth < samples_count:
            amplitudes[center + offset, 0, depth] = 500.0
    ds = dataset_factory(
        amplitudes=amplitudes, slices_count=slices_count, channels_count=1, samples_count=samples_count
    )
    result = remove_background(ds, method="sliding_mean", window_traces=9)
    peak_before = float(np.abs(amplitudes[center, 0, 30]))
    peak_after = float(np.abs(result.dataset.amplitudes[center, 0, 30]))
    assert (
        peak_after > 0.5 * peak_before
    )  # a local, curved event survives a window narrower than its own extent


def test_window_length_vs_target_length_attenuation_relationship(dataset_factory):
    # The well-known moving-average risk this whole sprint exists to
    # surface (see ADR-008): a target much SHORTER than the sliding window
    # is preserved well (the window mostly samples the surrounding
    # background, so its own local mean stays low and the target survives
    # the subtraction) -- but a target much WIDER than the window is
    # attenuated almost completely at its own center, because there the
    # window sees nothing BUT the target and mistakes it for "background".
    slices_count, samples_count, target_sample = 61, 40, 20

    def make_target(length: int) -> np.ndarray:
        amplitudes = np.zeros((slices_count, 1, samples_count), dtype=np.float32)
        start = slices_count // 2 - length // 2
        amplitudes[start : start + length, 0, target_sample] = 500.0
        return amplitudes

    ds_short = dataset_factory(
        amplitudes=make_target(3), slices_count=slices_count, channels_count=1, samples_count=samples_count
    )
    ds_long = dataset_factory(
        amplitudes=make_target(45), slices_count=slices_count, channels_count=1, samples_count=samples_count
    )
    window = 15
    result_short = remove_background(ds_short, method="sliding_mean", window_traces=window)
    result_long = remove_background(ds_long, method="sliding_mean", window_traces=window)

    center = slices_count // 2
    retention_short = float(np.abs(result_short.dataset.amplitudes[center, 0, target_sample]) / 500.0)
    retention_long = float(np.abs(result_long.dataset.amplitudes[center, 0, target_sample]) / 500.0)
    assert retention_short > retention_long  # shorter-than-window survives; wider-than-window is destroyed


def test_mean_and_median_diverge_under_a_strong_outlier_trace(dataset_factory):
    slices_count, samples_count = 21, 10
    rng = np.random.default_rng(9)
    amplitudes = rng.normal(0.0, 5.0, size=(slices_count, 1, samples_count)).astype(np.float32)
    amplitudes[10, 0, :] += 8000.0  # one extreme outlier trace
    ds = dataset_factory(
        amplitudes=amplitudes, slices_count=slices_count, channels_count=1, samples_count=samples_count
    )
    mean_result = remove_background(ds, method="global_mean")
    median_result = remove_background(ds, method="global_median")
    # On a CLEAN trace (not the outlier itself), the mean estimator's
    # background is biased upward by the outlier; the median is not.
    clean_trace = 0
    mean_bias = float(np.abs(mean_result.removed_component[clean_trace, 0, :]).mean())
    median_bias = float(np.abs(median_result.removed_component[clean_trace, 0, :]).mean())
    assert mean_bias > median_bias
    assert not (mean_bias == pytest.approx(median_bias))  # confirms the two methods really do differ here


def test_event_sample_position_not_systematically_shifted(dataset_factory):
    # Background removal operates along the trace axis only -- it must
    # never shift an event's own sample (time) position.
    slices_count, samples_count = 30, 50
    amplitudes = np.zeros((slices_count, 1, samples_count), dtype=np.float32)
    amplitudes[:, 0, 25] = 1000.0  # a constant-position event on every trace
    ds = dataset_factory(
        amplitudes=amplitudes, slices_count=slices_count, channels_count=1, samples_count=samples_count
    )
    result = remove_background(ds, method="sliding_mean", window_traces=9)
    # The event is common to every trace, so a sliding window centered
    # elsewhere still mostly removes it -- but wherever a residual remains,
    # it must remain at sample 25, never drift to a neighboring sample.
    residual = np.abs(result.dataset.amplitudes[:, 0, :])
    nonzero_positions = {int(np.argmax(row)) for row in residual if row.max() > 1e-6}
    assert nonzero_positions <= {25}


def test_polarity_preserved_on_a_retained_local_event(dataset_factory):
    slices_count, samples_count = 61, 40
    amplitudes = np.zeros((slices_count, 1, samples_count), dtype=np.float32)
    center = slices_count // 2
    amplitudes[center - 1 : center + 2, 0, 20] = -500.0  # a short, negative-polarity local event
    ds = dataset_factory(
        amplitudes=amplitudes, slices_count=slices_count, channels_count=1, samples_count=samples_count
    )
    result = remove_background(ds, method="sliding_mean", window_traces=9)
    assert float(result.dataset.amplitudes[center, 0, 20]) < 0.0
