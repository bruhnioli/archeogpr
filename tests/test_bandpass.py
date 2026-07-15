"""Synthetic tests for archaeogpr.processing.bandpass.correct_bandpass (Sprint 3 / ADR-006).

20 tests covering: passband/stopband retention (both methods), zero-phase
peak-position preservation (with a causal contrast to prove the test
discriminates), Ormsby's zero-phase-by-construction, input=output+removed,
padding exclusion/preservation, valid-mask/shape/immutability, Nyquist and
Ormsby-ordering parameter validation, NaN/Inf guard, processing history, and
NPZ round-trip.
"""

from __future__ import annotations

import numpy as np
import pytest

from archaeogpr.export.processed import write_corrected_npz
from archaeogpr.export.sprint3 import read_processed_npz
from archaeogpr.processing.bandpass import correct_bandpass
from archaeogpr.processing.common import ProcessingError

SAMPLING_TIME_NS = 0.5  # 2000 MHz sampling, 1000 MHz Nyquist
SAMPLES_COUNT = 512


def _sine_mhz(freq_mhz: float, amp: float = 100.0) -> np.ndarray:
    t_s = np.arange(SAMPLES_COUNT, dtype=np.float64) * SAMPLING_TIME_NS * 1e-9
    return amp * np.sin(2 * np.pi * freq_mhz * 1e6 * t_s)


def _ricker(peak_freq_mhz: float, center_sample: int, amp: float = 1000.0) -> np.ndarray:
    n = np.arange(SAMPLES_COUNT, dtype=np.float64)
    t = (n - center_sample) * SAMPLING_TIME_NS * 1e-9
    f = peak_freq_mhz * 1e6
    return amp * (1 - 2 * (np.pi * f * t) ** 2) * np.exp(-((np.pi * f * t) ** 2))


def _retained_std_ratio(input_trace: np.ndarray, output_trace: np.ndarray, interior: slice) -> float:
    return float(output_trace[interior].std() / input_trace[interior].std())


def test_butterworth_passband_sine_is_retained(dataset_factory):
    trace = _sine_mhz(200.0)  # comfortably inside [100, 400] MHz
    ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    result = correct_bandpass(ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4)
    output = result.dataset.amplitudes[0, 0, :].astype(np.float64)
    assert _retained_std_ratio(trace, output, slice(100, 400)) > 0.9


def test_butterworth_stopband_low_sine_is_attenuated(dataset_factory):
    trace = _sine_mhz(20.0)  # well below the 100 MHz low cut
    ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    result = correct_bandpass(ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4)
    output = result.dataset.amplitudes[0, 0, :].astype(np.float64)
    assert _retained_std_ratio(trace, output, slice(100, 400)) < 0.05


def test_butterworth_stopband_high_sine_is_attenuated(dataset_factory):
    trace = _sine_mhz(700.0)  # well above the 400 MHz high cut, below Nyquist (1000 MHz)
    ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    result = correct_bandpass(ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4)
    output = result.dataset.amplitudes[0, 0, :].astype(np.float64)
    assert _retained_std_ratio(trace, output, slice(100, 400)) < 0.05


def test_ormsby_passband_sine_is_retained(dataset_factory):
    trace = _sine_mhz(200.0)  # inside the [120, 350] MHz flat top
    ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    result = correct_bandpass(ds, method="ormsby", frequencies_mhz=(80.0, 120.0, 350.0, 420.0))
    output = result.dataset.amplitudes[0, 0, :].astype(np.float64)
    assert _retained_std_ratio(trace, output, slice(100, 400)) > 0.9


def test_ormsby_stopband_sine_is_attenuated(dataset_factory):
    trace = _sine_mhz(700.0)  # well beyond f4=420 MHz
    ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    result = correct_bandpass(ds, method="ormsby", frequencies_mhz=(80.0, 120.0, 350.0, 420.0))
    output = result.dataset.amplitudes[0, 0, :].astype(np.float64)
    assert _retained_std_ratio(trace, output, slice(100, 400)) < 0.05


def test_zero_phase_butterworth_preserves_pulse_peak_sample(dataset_factory):
    center = 256
    pulse = _ricker(200.0, center)
    ds = dataset_factory(
        amplitudes=pulse.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    result = correct_bandpass(
        ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4, zero_phase=True
    )
    output_peak = int(np.argmax(np.abs(result.dataset.amplitudes[0, 0, :])))
    # Exact tolerance: the main peak sample must not move at all under zero-phase filtering.
    assert output_peak == center
    segment_stats = next(iter(result.diagnostics["peak_shift_and_lag_per_segment"].values()))
    assert segment_stats["median_trace_cross_correlation_lag"] == 0


def test_causal_butterworth_shifts_pulse_peak_sample(dataset_factory):
    # Same pulse/filter as the zero-phase test above, but zero_phase=False (a
    # single causal sosfilt pass) -- this MUST show a real shift, proving the
    # zero-phase test above is actually discriminating and not vacuously true.
    center = 256
    pulse = _ricker(200.0, center)
    ds = dataset_factory(
        amplitudes=pulse.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    result = correct_bandpass(
        ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4, zero_phase=False
    )
    output_peak = int(np.argmax(np.abs(result.dataset.amplitudes[0, 0, :])))
    assert output_peak != center
    segment_stats = next(iter(result.diagnostics["peak_shift_and_lag_per_segment"].values()))
    assert segment_stats["median_trace_cross_correlation_lag"] != 0
    assert any("phase delay" in w for w in result.warnings)


def test_ormsby_preserves_pulse_peak_sample_zero_phase_by_construction(dataset_factory):
    center = 256
    pulse = _ricker(200.0, center)
    ds = dataset_factory(
        amplitudes=pulse.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    result = correct_bandpass(ds, method="ormsby", frequencies_mhz=(80.0, 120.0, 350.0, 420.0))
    output_peak = int(np.argmax(np.abs(result.dataset.amplitudes[0, 0, :])))
    assert output_peak == center
    segment_stats = next(iter(result.diagnostics["peak_shift_and_lag_per_segment"].values()))
    assert segment_stats["median_trace_cross_correlation_lag"] == 0


def test_output_equals_input_minus_removed_component(dataset_factory):
    rng = np.random.default_rng(0)
    amplitudes = rng.normal(0.0, 50.0, size=(3, 2, SAMPLES_COUNT)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_bandpass(ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4)
    reconstructed = result.dataset.amplitudes.astype(np.float64) + result.removed_component.astype(np.float64)
    np.testing.assert_allclose(reconstructed, ds.amplitudes.astype(np.float64), atol=1e-1)


def test_padding_excluded_from_computation(dataset_factory):
    samples_count = 300
    valid_mask = np.ones((1, samples_count), dtype=bool)
    valid_mask[0, 100:110] = False  # padding gap

    rng = np.random.default_rng(1)
    first_segment = (rng.normal(0.0, 5.0, size=100) + _sine_mhz(200.0)[:100] * 0.05).astype(np.float32)

    def run(padding_value: float) -> np.ndarray:
        trace = np.zeros(samples_count, dtype=np.float32)
        trace[:100] = first_segment
        trace[100:110] = padding_value
        trace[110:] = rng.normal(10.0, 5.0, size=samples_count - 110).astype(np.float32)
        ds = dataset_factory(amplitudes=trace.reshape(1, 1, samples_count), sampling_time_ns=SAMPLING_TIME_NS)
        result = correct_bandpass(
            ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4, valid_mask=valid_mask
        )
        return result.dataset.amplitudes[0, 0, :100].copy()

    benign = run(0.0)
    extreme = run(1.0e9)
    np.testing.assert_array_equal(benign, extreme)


def test_padding_preserved_and_valid_mask_returned_as_independent_copy(dataset_factory):
    samples_count = 300
    rng = np.random.default_rng(2)
    amplitudes = np.zeros((2, 1, samples_count), dtype=np.float32)
    amplitudes[:, 0, :200] = rng.normal(0.0, 20.0, size=(2, 200)).astype(np.float32)
    amplitudes[:, 0, 200:] = 0.0  # padding, exactly at a fill_value of 0.0
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    valid_mask = np.ones((1, samples_count), dtype=bool)
    valid_mask[0, 200:] = False

    result = correct_bandpass(
        ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4, valid_mask=valid_mask
    )
    np.testing.assert_array_equal(result.dataset.amplitudes[:, 0, 200:], 0.0)
    np.testing.assert_array_equal(result.removed_component[:, 0, 200:], 0.0)

    assert result.valid_mask is not None
    np.testing.assert_array_equal(result.valid_mask, valid_mask)
    valid_mask[0, 0] = False
    assert result.valid_mask[0, 0], "returned valid_mask must be an independent copy"


def test_output_shape_and_dtype_match_input(dataset_factory):
    amplitudes = np.random.default_rng(3).normal(size=(4, 3, SAMPLES_COUNT)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_bandpass(ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4)
    assert result.dataset.shape == ds.shape
    assert result.removed_component.shape == ds.shape
    assert result.dataset.amplitudes.dtype == np.float32
    assert result.removed_component.dtype == np.float32


def test_input_dataset_is_not_mutated(dataset_factory):
    amplitudes = np.random.default_rng(4).normal(size=(3, 2, SAMPLES_COUNT)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    original_bytes = ds.amplitudes.tobytes()
    correct_bandpass(ds, method="ormsby", frequencies_mhz=(80.0, 120.0, 350.0, 420.0))
    assert ds.amplitudes.tobytes() == original_bytes


def test_error_on_invalid_method(dataset_factory):
    amplitudes = np.zeros((2, 1, SAMPLES_COUNT), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    with pytest.raises(ProcessingError, match="method must be one of"):
        correct_bandpass(ds, method="bogus")


def test_error_on_invalid_butterworth_parameters(dataset_factory):
    amplitudes = np.zeros((2, 1, SAMPLES_COUNT), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    with pytest.raises(ProcessingError, match="requires both lowcut_mhz and highcut_mhz"):
        correct_bandpass(ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=None)
    with pytest.raises(ProcessingError, match="lowcut_mhz < highcut_mhz < nyquist_mhz"):
        correct_bandpass(
            ds, method="butterworth", lowcut_mhz=400.0, highcut_mhz=100.0, order=4
        )  # lowcut > highcut
    with pytest.raises(ProcessingError, match="lowcut_mhz < highcut_mhz < nyquist_mhz"):
        # Nyquist at this sampling rate is 1000 MHz -- 900 < 1200 violates highcut < nyquist.
        correct_bandpass(ds, method="butterworth", lowcut_mhz=900.0, highcut_mhz=1200.0, order=4)
    with pytest.raises(ProcessingError, match="order must be >= 1"):
        correct_bandpass(ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=0)


def test_error_on_invalid_ormsby_parameters(dataset_factory):
    amplitudes = np.zeros((2, 1, SAMPLES_COUNT), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    with pytest.raises(ProcessingError, match="requires frequencies_mhz"):
        correct_bandpass(ds, method="ormsby", frequencies_mhz=None)
    with pytest.raises(ProcessingError, match="f1 < f2 < f3 < f4"):
        correct_bandpass(ds, method="ormsby", frequencies_mhz=(80.0, 350.0, 120.0, 420.0))  # f2/f3 swapped
    with pytest.raises(ProcessingError, match="f1 < f2 < f3 < f4"):
        # Nyquist is 1000 MHz -- f4=1200 violates f4 < nyquist_mhz.
        correct_bandpass(ds, method="ormsby", frequencies_mhz=(80.0, 120.0, 900.0, 1200.0))


def test_nan_input_raises_rather_than_propagating(dataset_factory):
    amplitudes = np.zeros((2, 1, SAMPLES_COUNT), dtype=np.float32)
    amplitudes[0, 0, 200] = np.nan
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    with pytest.raises(ProcessingError, match="NaN/Inf"):
        correct_bandpass(ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4)


def test_processing_history_records_operation_parameters_and_diagnostics(dataset_factory):
    amplitudes = np.zeros((2, 1, SAMPLES_COUNT), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_bandpass(ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4)
    assert ds.processing_history == ()
    record = result.dataset.processing_history[-1]
    assert record["operation"] == "bandpass_correction"
    assert record["parameters"]["method"] == "butterworth"
    assert record["parameters"]["lowcut_mhz"] == 100.0
    assert record["parameters"]["highcut_mhz"] == 400.0
    assert record["diagnostics"]["nyquist_mhz"] == pytest.approx(1000.0)


def test_repeat_processing_guard_and_allow_flag_override(dataset_factory):
    amplitudes = np.random.default_rng(5).normal(size=(2, 1, SAMPLES_COUNT)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    once = correct_bandpass(ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4)

    with pytest.raises(ProcessingError, match="already contains"):
        correct_bandpass(once.dataset, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4)

    twice = correct_bandpass(
        once.dataset,
        method="butterworth",
        lowcut_mhz=100.0,
        highcut_mhz=400.0,
        order=4,
        allow_repeat_processing=True,
    )
    operations = [record["operation"] for record in twice.dataset.processing_history]
    assert operations.count("bandpass_correction") == 2


def test_bandpass_npz_round_trip_preserves_amplitudes_and_history(tmp_path, dataset_factory):
    amplitudes = np.random.default_rng(6).normal(size=(3, 2, SAMPLES_COUNT)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    valid_mask = np.ones((2, SAMPLES_COUNT), dtype=bool)
    valid_mask[:, 450:] = False

    result = correct_bandpass(
        ds, method="ormsby", frequencies_mhz=(80.0, 120.0, 350.0, 420.0), valid_mask=valid_mask
    )
    npz_path = write_corrected_npz(result, tmp_path / "bandpass_processed.npz")

    reloaded_dataset, reloaded_mask = read_processed_npz(npz_path)
    np.testing.assert_array_equal(reloaded_dataset.amplitudes, result.dataset.amplitudes)
    np.testing.assert_array_equal(reloaded_dataset.time_ns, result.dataset.time_ns)
    assert reloaded_mask is not None
    np.testing.assert_array_equal(reloaded_mask, result.valid_mask)
    assert [r["operation"] for r in reloaded_dataset.processing_history] == ["bandpass_correction"]
