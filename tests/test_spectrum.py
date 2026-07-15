"""Tests for archaeogpr.qc.spectrum.compute_amplitude_spectrum (Sprint 3).

Covers: real frequency axis from the actual sampling interval, correct
Hz/MHz and Nyquist, padding exclusion via a shared common-valid mask,
dataset_time window selection, optional constant detrend, Hann taper
(spectral leakage contrast), mean/median/RMS aggregation, amplitude (never
power) linearity, log-safe dB conversion, normalized spectrum, required
metadata fields, and every documented error path.
"""

from __future__ import annotations

import numpy as np
import pytest

from archaeogpr.processing.common import ProcessingError
from archaeogpr.qc.spectrum import compute_amplitude_spectrum, to_db

SAMPLING_TIME_NS = 0.25  # 4000 MHz sampling, 2000 MHz Nyquist
SAMPLES_COUNT = 400


def _sine_mhz(freq_mhz: float, amp: float = 10.0, samples: int = SAMPLES_COUNT) -> np.ndarray:
    t_s = np.arange(samples, dtype=np.float64) * SAMPLING_TIME_NS * 1e-9
    return amp * np.sin(2 * np.pi * freq_mhz * 1e6 * t_s)


def test_dominant_frequency_is_detected_correctly(dataset_factory):
    trace = _sine_mhz(300.0)  # exactly bin-aligned: resolution = 4000/400 = 10 MHz
    ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    spectrum = compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=100.0)
    peak_freq = spectrum["frequencies_mhz"][np.argmax(spectrum["amplitude_spectrum"])]
    assert peak_freq == pytest.approx(300.0)


def test_frequency_axis_and_nyquist_match_actual_sampling_interval(dataset_factory):
    trace = np.zeros(SAMPLES_COUNT, dtype=np.float32)
    ds = dataset_factory(amplitudes=trace.reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS)
    spectrum = compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=100.0)
    meta = spectrum["metadata"]
    assert meta["sampling_frequency_mhz"] == pytest.approx(4000.0)
    assert meta["nyquist_mhz"] == pytest.approx(2000.0)
    assert spectrum["frequencies_mhz"].max() == pytest.approx(2000.0, rel=1e-3)


def test_nyquist_is_exactly_half_sampling_frequency(dataset_factory):
    trace = np.zeros(SAMPLES_COUNT, dtype=np.float32)
    ds = dataset_factory(amplitudes=trace.reshape(1, 1, -1), sampling_time_ns=0.125)  # 8000 MHz sampling
    spectrum = compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=100.0)
    meta = spectrum["metadata"]
    assert meta["nyquist_mhz"] == pytest.approx(meta["sampling_frequency_mhz"] / 2.0)


def test_frequency_resolution_equals_sampling_frequency_over_fft_length(dataset_factory):
    trace = np.zeros(SAMPLES_COUNT, dtype=np.float32)
    ds = dataset_factory(amplitudes=trace.reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS)
    spectrum = compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=100.0)
    meta = spectrum["metadata"]
    assert meta["frequency_resolution_mhz"] == pytest.approx(
        meta["sampling_frequency_mhz"] / meta["fft_length"]
    )


def test_padding_excluded_from_fft(dataset_factory):
    # Two channels; channel 1's padding holds an extreme value that must
    # never reach the FFT once the common (all-channels-valid) mask excludes it.
    trace0 = _sine_mhz(300.0)
    trace1 = trace0.copy()
    trace1[350:] = 1.0e9  # channel 1 padding, extreme
    amplitudes = np.stack([trace0, trace1]).astype(np.float32).reshape(1, 2, SAMPLES_COUNT)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    valid_mask = np.ones((2, SAMPLES_COUNT), dtype=bool)
    valid_mask[1, 350:] = False

    with_mask = compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=100.0, valid_mask=valid_mask)
    assert with_mask["metadata"]["common_valid_sample_count"] == 350
    # A spectrum computed on trace0 alone, truncated to the same 350 valid samples, must match exactly.
    truncated_ds = dataset_factory(
        amplitudes=trace0[:350].astype(np.float32).reshape(1, 1, 350), sampling_time_ns=SAMPLING_TIME_NS
    )
    truncated_spectrum = compute_amplitude_spectrum(truncated_ds, time_start_ns=0.0, time_end_ns=100.0)
    np.testing.assert_allclose(
        with_mask["per_channel_spectrum"][0], truncated_spectrum["amplitude_spectrum"], atol=1e-6
    )


def test_window_selected_via_dataset_time_ns(dataset_factory):
    # time_ns relative to a target_sample=16-like shift, as after time-zero correction.
    time_ns = (np.arange(SAMPLES_COUNT, dtype=np.float64) - 16) * SAMPLING_TIME_NS
    trace = _sine_mhz(300.0)
    ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1),
        sampling_time_ns=SAMPLING_TIME_NS,
        time_ns=time_ns,
    )
    spectrum = compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=100.0)
    # [0, 100) ns at dt=0.25 ns, offset by -16 samples -> exactly 400 samples selected here would
    # overflow; the window must select only the in-range samples actually satisfying time_ns < 100.
    expected_count = int(((time_ns >= 0.0) & (time_ns < 100.0)).sum())
    assert spectrum["metadata"]["common_valid_sample_count"] == expected_count


def test_all_selected_traces_share_sample_count_via_common_valid_mask(dataset_factory):
    amplitudes = np.zeros((2, 3, SAMPLES_COUNT), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    valid_mask = np.ones((3, SAMPLES_COUNT), dtype=bool)
    valid_mask[0, 90:] = False  # channel 0 ends early
    valid_mask[1, 95:] = False  # channel 1 ends slightly later
    # channel 2 fully valid
    spectrum = compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=100.0, valid_mask=valid_mask)
    assert spectrum["metadata"]["common_valid_sample_count"] == 90  # the strictest intersection


def test_constant_detrend_removes_dc_component(dataset_factory):
    trace = _sine_mhz(300.0, amp=1.0) + 1000.0  # huge DC bias dwarfing the AC signal
    ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    spectrum = compute_amplitude_spectrum(
        ds, time_start_ns=0.0, time_end_ns=100.0, detrend="constant", taper=None
    )
    assert spectrum["amplitude_spectrum"][0] == pytest.approx(0.0, abs=1e-6)


def test_detrend_none_leaves_a_large_dc_component(dataset_factory):
    trace = _sine_mhz(300.0, amp=1.0) + 1000.0
    ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    spectrum = compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=100.0, detrend=None, taper=None)
    assert spectrum["amplitude_spectrum"][0] > 1000.0


def test_hann_taper_spreads_energy_relative_to_no_taper(dataset_factory):
    # A bin-aligned pure sinusoid with no taper puts ~100% of energy in one
    # bin; a Hann taper deliberately spreads (leaks) some of it to neighbors.
    trace = _sine_mhz(250.0)  # bin-aligned: 250 / 10 MHz resolution = bin 25
    ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )

    def concentration(taper: str | None) -> float:
        spectrum = compute_amplitude_spectrum(
            ds, time_start_ns=0.0, time_end_ns=100.0, taper=taper, detrend=None
        )
        amp = spectrum["amplitude_spectrum"]
        return float(amp.max() / amp.sum())

    no_taper_concentration = concentration(None)
    hann_concentration = concentration("hann")
    assert no_taper_concentration > 0.99
    assert hann_concentration < no_taper_concentration - 0.1


def test_aggregation_mean_is_pulled_by_an_outlier_slice_median_is_not(dataset_factory):
    base = _sine_mhz(300.0, amp=1.0)
    amplitudes = np.zeros((5, 1, SAMPLES_COUNT), dtype=np.float32)
    for i in range(5):
        amplitudes[i, 0, :] = base * (100.0 if i == 0 else 1.0)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    mean_spec = compute_amplitude_spectrum(
        ds, time_start_ns=0.0, time_end_ns=100.0, aggregation="mean", taper=None, detrend=None
    )
    median_spec = compute_amplitude_spectrum(
        ds, time_start_ns=0.0, time_end_ns=100.0, aggregation="median", taper=None, detrend=None
    )
    assert mean_spec["amplitude_spectrum"].max() > 10 * median_spec["amplitude_spectrum"].max()


def test_aggregation_rms_is_pulled_even_more_than_mean_by_an_outlier(dataset_factory):
    # Power-mean inequality: for non-negative, non-constant values, the
    # quadratic mean (RMS) is strictly >= the arithmetic mean, which is in
    # turn pulled above the median by a single large outlier -- so the
    # correct ordering here is median < mean < RMS, not RMS "in between".
    base = _sine_mhz(300.0, amp=1.0)
    amplitudes = np.zeros((5, 1, SAMPLES_COUNT), dtype=np.float32)
    for i in range(5):
        amplitudes[i, 0, :] = base * (100.0 if i == 0 else 1.0)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    rms_spec = compute_amplitude_spectrum(
        ds, time_start_ns=0.0, time_end_ns=100.0, aggregation="rms", taper=None, detrend=None
    )
    median_spec = compute_amplitude_spectrum(
        ds, time_start_ns=0.0, time_end_ns=100.0, aggregation="median", taper=None, detrend=None
    )
    mean_spec = compute_amplitude_spectrum(
        ds, time_start_ns=0.0, time_end_ns=100.0, aggregation="mean", taper=None, detrend=None
    )
    median_peak = median_spec["amplitude_spectrum"].max()
    mean_peak = mean_spec["amplitude_spectrum"].max()
    rms_peak = rms_spec["amplitude_spectrum"].max()
    assert median_peak < mean_peak < rms_peak


def test_amplitude_spectrum_scales_linearly_not_quadratically(dataset_factory):
    # Amplitude (not power) spectrum: doubling the input amplitude must
    # exactly double the spectrum peak, not quadruple it.
    base = _sine_mhz(250.0, amp=1.0)
    ds1 = dataset_factory(
        amplitudes=(base * 10.0).astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    ds2 = dataset_factory(
        amplitudes=(base * 20.0).astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    s1 = compute_amplitude_spectrum(ds1, time_start_ns=0.0, time_end_ns=100.0, taper=None, detrend=None)
    s2 = compute_amplitude_spectrum(ds2, time_start_ns=0.0, time_end_ns=100.0, taper=None, detrend=None)
    ratio = s2["amplitude_spectrum"].max() / s1["amplitude_spectrum"].max()
    assert ratio == pytest.approx(2.0, rel=1e-6)


def test_db_conversion_is_finite_even_for_all_zero_input():
    spectrum = np.zeros(50)
    db = to_db(spectrum)
    assert np.isfinite(db).all()


def test_db_spectrum_from_all_zero_trace_is_finite(dataset_factory):
    ds = dataset_factory(
        amplitudes=np.zeros((1, 1, SAMPLES_COUNT), dtype=np.float32), sampling_time_ns=SAMPLING_TIME_NS
    )
    spectrum = compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=100.0)
    assert np.isfinite(spectrum["amplitude_spectrum_db"]).all()


def test_normalized_spectrum_peaks_at_exactly_one(dataset_factory):
    trace = _sine_mhz(300.0)
    ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    spectrum = compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=100.0)
    assert spectrum["amplitude_spectrum_normalized"].max() == pytest.approx(1.0)


def test_metadata_contains_all_required_fields(dataset_factory):
    trace = np.zeros(SAMPLES_COUNT, dtype=np.float32)
    ds = dataset_factory(amplitudes=trace.reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS)
    spectrum = compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=100.0)
    required = {
        "sampling_frequency_hz",
        "sampling_frequency_mhz",
        "nyquist_hz",
        "nyquist_mhz",
        "fft_length",
        "frequency_resolution_hz",
        "frequency_resolution_mhz",
        "time_start_ns",
        "time_end_ns",
        "valid_mask_provided",
        "common_valid_sample_count",
        "taper",
        "detrend",
        "aggregation",
    }
    assert required.issubset(spectrum["metadata"].keys())


def test_error_on_invalid_detrend(dataset_factory):
    ds = dataset_factory(
        amplitudes=np.zeros((1, 1, SAMPLES_COUNT), dtype=np.float32), sampling_time_ns=SAMPLING_TIME_NS
    )
    with pytest.raises(ProcessingError, match="detrend must be one of"):
        compute_amplitude_spectrum(ds, detrend="linear")


def test_error_on_invalid_taper(dataset_factory):
    ds = dataset_factory(
        amplitudes=np.zeros((1, 1, SAMPLES_COUNT), dtype=np.float32), sampling_time_ns=SAMPLING_TIME_NS
    )
    with pytest.raises(ProcessingError, match="taper must be one of"):
        compute_amplitude_spectrum(ds, taper="blackman")


def test_error_on_invalid_aggregation(dataset_factory):
    ds = dataset_factory(
        amplitudes=np.zeros((1, 1, SAMPLES_COUNT), dtype=np.float32), sampling_time_ns=SAMPLING_TIME_NS
    )
    with pytest.raises(ProcessingError, match="aggregation must be one of"):
        compute_amplitude_spectrum(ds, aggregation="max")


def test_error_on_invalid_time_window_order(dataset_factory):
    ds = dataset_factory(
        amplitudes=np.zeros((1, 1, SAMPLES_COUNT), dtype=np.float32), sampling_time_ns=SAMPLING_TIME_NS
    )
    with pytest.raises(ProcessingError, match="must be greater than"):
        compute_amplitude_spectrum(ds, time_start_ns=50.0, time_end_ns=10.0)


def test_error_on_window_selecting_zero_samples(dataset_factory):
    ds = dataset_factory(
        amplitudes=np.zeros((1, 1, SAMPLES_COUNT), dtype=np.float32), sampling_time_ns=SAMPLING_TIME_NS
    )
    with pytest.raises(ProcessingError, match="selects zero samples"):
        compute_amplitude_spectrum(ds, time_start_ns=10_000.0, time_end_ns=20_000.0)


def test_error_on_fewer_than_two_common_valid_samples(dataset_factory):
    ds = dataset_factory(
        amplitudes=np.zeros((1, 1, SAMPLES_COUNT), dtype=np.float32), sampling_time_ns=SAMPLING_TIME_NS
    )
    valid_mask = np.zeros((1, SAMPLES_COUNT), dtype=bool)
    valid_mask[0, 5] = True  # only one valid sample anywhere
    with pytest.raises(ProcessingError, match="at least 2 are required"):
        compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=100.0, valid_mask=valid_mask)


def test_error_on_valid_mask_shape_mismatch(dataset_factory):
    ds = dataset_factory(
        amplitudes=np.zeros((1, 2, SAMPLES_COUNT), dtype=np.float32), sampling_time_ns=SAMPLING_TIME_NS
    )
    wrong_shape_mask = np.ones((3, SAMPLES_COUNT), dtype=bool)  # 3 channels, dataset only has 2
    with pytest.raises(ProcessingError, match="does not match"):
        compute_amplitude_spectrum(ds, valid_mask=wrong_shape_mask)
