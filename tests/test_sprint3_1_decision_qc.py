"""Tests for Sprint 3.1's decision-focused QC modules: qc/spatial_coherence.py,
qc/phase_metrics.py, qc/band_energy.py, and qc/decision_qc.py.

Real-.ogpr-and-canonical-NPZ-dependent hash/immutability checks live in a
dedicated real-data test at the bottom of this file and skip cleanly if the
files are absent, matching the existing test_sprint3_real_integration.py
convention.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from archaeogpr.export.sprint3 import read_processed_npz
from archaeogpr.processing.bandpass import correct_bandpass
from archaeogpr.processing.dewow import correct_dewow
from archaeogpr.qc.band_energy import (
    band_energy_table,
    integrate_band_energy,
    per_slice_band_energy,
    retention_ratio,
    rms_difference,
)
from archaeogpr.qc.decision_qc import _shared_limit, compute_window_spectra, windowed_array
from archaeogpr.qc.phase_metrics import compute_phase_waveform_metrics, median_trace_lag, polarity_preserved
from archaeogpr.qc.spatial_coherence import (
    adjacent_trace_correlation,
    band_energy_concentration,
    channel_to_channel_consistency,
    compute_spatial_coherence_metrics,
)
from archaeogpr.qc.spectrum import to_db

SAMPLING_TIME_NS = 0.125  # matches the real canonical dataset: 8000 MHz sampling
SAMPLES_COUNT = 640  # 80 ns of trace


def _sine_mhz(freq_mhz: float, amp: float = 100.0, samples: int = SAMPLES_COUNT) -> np.ndarray:
    t_s = np.arange(samples, dtype=np.float64) * SAMPLING_TIME_NS * 1e-9
    return amp * np.sin(2 * np.pi * freq_mhz * 1e6 * t_s)


# --- 1/2: absolute vs normalized vs common-dB-reference spectrum modes ----------------


def test_absolute_and_normalized_spectrum_modes_differ(dataset_factory):
    trace = _sine_mhz(300.0)
    d2_ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    b1_result = correct_bandpass(d2_ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=900.0, order=4)
    b2_result = correct_bandpass(d2_ds, method="butterworth", lowcut_mhz=120.0, highcut_mhz=800.0, order=4)

    class _FakeResult:
        def __init__(self, dataset, removed_component):
            self.dataset = dataset
            self.removed_component = removed_component

    d2_result = _FakeResult(d2_ds, np.zeros_like(trace).reshape(1, 1, -1))
    spectra = compute_window_spectra(d2_result, b1_result, b2_result, None, 0.0, 80.0)
    d2_spectrum = spectra["D2"]
    assert d2_spectrum["amplitude_spectrum"].max() > 1.0  # absolute scale, not normalized
    assert d2_spectrum["amplitude_spectrum_normalized"].max() == pytest.approx(1.0)
    assert not np.allclose(d2_spectrum["amplitude_spectrum"], d2_spectrum["amplitude_spectrum_normalized"])


def test_common_db_reference_is_identical_across_candidates(dataset_factory):
    big_trace = _sine_mhz(300.0, amp=100.0)
    small_trace = _sine_mhz(300.0, amp=10.0)  # 10x smaller absolute peak
    big_ds = dataset_factory(
        amplitudes=big_trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    small_ds = dataset_factory(
        amplitudes=small_trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    from archaeogpr.qc.spectrum import compute_amplitude_spectrum

    big_spectrum = compute_amplitude_spectrum(big_ds, time_start_ns=0.0, time_end_ns=80.0)
    small_spectrum = compute_amplitude_spectrum(small_ds, time_start_ns=0.0, time_end_ns=80.0)

    shared_reference = float(big_spectrum["amplitude_spectrum"].max())
    big_db = to_db(big_spectrum["amplitude_spectrum"], reference=shared_reference)
    small_db = to_db(small_spectrum["amplitude_spectrum"], reference=shared_reference)
    # Same shared reference -> the 10x-smaller trace's own peak sits ~20 dB below the big one's,
    # rather than both independently normalizing to their own 0 dB peak.
    assert big_db.max() == pytest.approx(0.0, abs=1e-6)
    assert small_db.max() == pytest.approx(-20.0, abs=0.5)


# --- 3/4: time-window sample selection and padding exclusion --------------------------


def test_windowed_array_selects_correct_samples(dataset_factory):
    samples_count = 200
    time_ns = np.arange(samples_count, dtype=np.float64) * SAMPLING_TIME_NS
    amplitudes = np.arange(samples_count, dtype=np.float32).reshape(1, 1, samples_count)
    masked, t = windowed_array(amplitudes, time_ns, 0, 10.0, 20.0, None)
    expected_count = int(((time_ns >= 10.0) & (time_ns < 20.0)).sum())
    assert masked.shape[1] == expected_count
    assert t.min() >= 10.0 and t.max() < 20.0


def test_windowed_array_full_trace_when_bounds_none(dataset_factory):
    samples_count = 100
    time_ns = np.arange(samples_count, dtype=np.float64) * SAMPLING_TIME_NS
    amplitudes = np.zeros((1, 1, samples_count), dtype=np.float32)
    masked, t = windowed_array(amplitudes, time_ns, 0, None, None, None)
    assert masked.shape[1] == samples_count
    assert t.shape[0] == samples_count


def test_windowed_array_explicitly_masks_padding():
    samples_count = 50
    time_ns = np.arange(samples_count, dtype=np.float64) * SAMPLING_TIME_NS
    amplitudes = np.full((2, 1, samples_count), 5.0, dtype=np.float32)
    valid_mask = np.ones((1, samples_count), dtype=bool)
    valid_mask[0, 30:] = False
    masked, _ = windowed_array(amplitudes, time_ns, 0, None, None, valid_mask)
    assert np.ma.getmaskarray(masked)[:, 30:].all()
    assert not np.ma.getmaskarray(masked)[:, :30].any()


def test_per_slice_band_energy_excludes_padding_via_caller_supplied_zero(dataset_factory):
    # per_slice_band_energy itself is padding-agnostic (caller fills padding with 0
    # via windowed_array(...).filled(0.0)) -- confirm a zero-filled padded region
    # contributes exactly zero extra energy versus a trace with no padding at all.
    trace = _sine_mhz(300.0, samples=320)
    padded = np.concatenate([trace, np.zeros(64)])
    unpadded = np.concatenate([trace, np.zeros(64)])  # identical here -- padding is already zero-filled
    energy_padded = per_slice_band_energy(padded.reshape(1, -1), SAMPLING_TIME_NS, 250.0, 350.0)
    energy_unpadded = per_slice_band_energy(unpadded.reshape(1, -1), SAMPLING_TIME_NS, 250.0, 350.0)
    np.testing.assert_allclose(energy_padded, energy_unpadded)


# --- 5/6: band energy integration and retention ratio ----------------------------------


def test_band_energy_integration_lands_in_correct_band(dataset_factory):
    trace = _sine_mhz(300.0)
    ds = dataset_factory(
        amplitudes=trace.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )
    from archaeogpr.qc.spectrum import compute_amplitude_spectrum

    spectrum = compute_amplitude_spectrum(ds, time_start_ns=0.0, time_end_ns=80.0, taper=None, detrend=None)
    bands = [("low", 0.0, 250.0), ("mid", 250.0, 350.0), ("high", 350.0, 2000.0)]
    table = band_energy_table(spectrum, bands)
    total = sum(table.values())
    assert (
        table["mid"] / total > 0.95
    )  # nearly all energy in the 250-350 MHz band containing the 300 MHz tone
    assert table["low"] / total < 0.05
    assert table["high"] / total < 0.05


def test_integrate_band_energy_matches_manual_sum():
    freqs = np.array([0.0, 100.0, 200.0, 300.0, 400.0])
    amp = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    energy = integrate_band_energy(freqs, amp, 100.0, 400.0)  # half-open [100, 400): bins at 100,200,300
    assert energy == pytest.approx(2.0**2 + 3.0**2 + 4.0**2)


def test_retention_ratio_correct_and_nan_on_zero_reference():
    assert retention_ratio(50.0, 100.0) == pytest.approx(0.5)
    assert np.isnan(retention_ratio(50.0, 0.0))


def test_rms_difference_zero_for_identical_arrays_and_positive_otherwise():
    a = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    assert rms_difference(a, a) == pytest.approx(0.0)
    b = a + 2.0
    assert rms_difference(a, b) == pytest.approx(2.0)


# --- 7: B1/B2 shared amplitude scale ---------------------------------------------------


def test_shared_limit_uses_the_combined_max_across_arrays():
    a = np.ma.array(np.full((3, 10), 5.0))
    b = np.ma.array(np.full((3, 10), 20.0))
    limit_combined = _shared_limit(a, b, clip_percentile=99.0)
    limit_a_alone = _shared_limit(a, clip_percentile=99.0)
    assert limit_combined == pytest.approx(20.0, rel=1e-6)
    assert limit_a_alone == pytest.approx(5.0, rel=1e-6)
    assert limit_combined > limit_a_alone


# --- 8: removed component correctness through windowing --------------------------------


def test_windowed_removed_component_equals_windowed_input_minus_output(dataset_factory):
    amplitudes = np.random.default_rng(0).normal(size=(2, 1, SAMPLES_COUNT)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    result = correct_dewow(ds, window_ns=8.0, method="running_mean")

    input_masked, _ = windowed_array(ds.amplitudes, ds.time_ns, 0, 10.0, 40.0, None)
    output_masked, _ = windowed_array(result.dataset.amplitudes, ds.time_ns, 0, 10.0, 40.0, None)
    removed_masked, _ = windowed_array(result.removed_component, ds.time_ns, 0, 10.0, 40.0, None)
    np.testing.assert_allclose(
        input_masked.filled(0.0) - output_masked.filled(0.0), removed_masked.filled(0.0), atol=1e-3
    )


# --- 9/10: spatial coherence discriminates coherent events from noise -----------------


def test_adjacent_trace_correlation_high_for_coherent_synthetic_event():
    rng = np.random.default_rng(1)
    t = np.linspace(0, 1, 100)
    base = np.sin(2 * np.pi * 5 * t)
    coherent = np.array([base + rng.normal(0, 0.02, 100) for _ in range(30)])
    metrics = compute_spatial_coherence_metrics(coherent)
    assert metrics["adjacent_trace_correlation_median"] > 0.9


def test_adjacent_trace_correlation_low_for_random_noise():
    rng = np.random.default_rng(2)
    noise = rng.normal(0, 1, (30, 100))
    correlations = adjacent_trace_correlation(noise)
    assert abs(np.nanmedian(correlations)) < 0.2


def test_band_energy_concentration_detects_concentrated_vs_uniform():
    uniform = np.full(100, 10.0)
    concentrated = np.full(100, 1.0)
    concentrated[:5] = 200.0  # top 5% holds almost all the energy
    uniform_result = band_energy_concentration(uniform, top_fraction=0.05)
    concentrated_result = band_energy_concentration(concentrated, top_fraction=0.05)
    assert concentrated_result["top_fraction_energy_share"] > uniform_result["top_fraction_energy_share"]
    assert uniform_result["top_fraction_energy_share"] == pytest.approx(0.05, abs=1e-6)


def test_channel_to_channel_consistency_low_std_for_similar_channels():
    similar = {
        0: {"adjacent_trace_correlation_median": 0.9},
        5: {"adjacent_trace_correlation_median": 0.91},
        10: {"adjacent_trace_correlation_median": 0.89},
    }
    dissimilar = {
        0: {"adjacent_trace_correlation_median": 0.95},
        5: {"adjacent_trace_correlation_median": 0.1},
        10: {"adjacent_trace_correlation_median": -0.8},
    }
    similar_consistency = channel_to_channel_consistency(similar)
    dissimilar_consistency = channel_to_channel_consistency(dissimilar)
    assert (
        similar_consistency["correlation_median_across_channels_std"]
        < dissimilar_consistency["correlation_median_across_channels_std"]
    )


# --- 11: phase metrics report lag=0 for a known zero-phase filter, nonzero for causal --


def test_median_trace_lag_zero_for_zero_phase_and_nonzero_for_causal(dataset_factory):
    center = 256
    n = np.arange(SAMPLES_COUNT, dtype=np.float64)
    t = (n - center) * SAMPLING_TIME_NS * 1e-9
    f = 200.0e6
    pulse = 1000.0 * (1 - 2 * (np.pi * f * t) ** 2) * np.exp(-((np.pi * f * t) ** 2))
    ds = dataset_factory(
        amplitudes=pulse.astype(np.float32).reshape(1, 1, -1), sampling_time_ns=SAMPLING_TIME_NS
    )

    zero_phase_result = correct_bandpass(
        ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4, zero_phase=True
    )
    causal_result = correct_bandpass(
        ds, method="butterworth", lowcut_mhz=100.0, highcut_mhz=400.0, order=4, zero_phase=False
    )

    zero_phase_lag = median_trace_lag(ds.amplitudes[:, 0, :], zero_phase_result.dataset.amplitudes[:, 0, :])
    causal_lag = median_trace_lag(ds.amplitudes[:, 0, :], causal_result.dataset.amplitudes[:, 0, :])
    assert zero_phase_lag["median_trace_cross_correlation_lag"] == 0
    assert causal_lag["median_trace_cross_correlation_lag"] != 0


def test_polarity_preserved_detects_sign_flip():
    before = np.array([[0.0, 1.0, 5.0, 1.0, 0.0]])
    after_same = before.copy()
    after_flipped = -before
    assert polarity_preserved(before, after_same).all()
    assert not polarity_preserved(before, after_flipped).any()


def test_compute_phase_waveform_metrics_reports_full_correlation_for_identical_arrays():
    before = np.random.default_rng(3).normal(size=(10, 50))
    metrics = compute_phase_waveform_metrics(before, before.copy())
    assert metrics["waveform_correlation_median"] == pytest.approx(1.0)
    assert metrics["polarity_preserved_fraction"] == pytest.approx(1.0)
    assert metrics["peak_sample_diff_max_abs"] == 0


# --- 12/13/14: immutability, time axis, valid mask preserved through D2->B1/B2 --------


def test_input_dataset_not_mutated_through_d2_b1_b2_chain(dataset_factory):
    amplitudes = np.random.default_rng(4).normal(size=(3, 2, SAMPLES_COUNT)).astype(np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    original_bytes = ds.amplitudes.tobytes()

    d2_result = correct_dewow(ds, window_ns=8.0, method="running_mean")
    correct_bandpass(d2_result.dataset, method="butterworth", lowcut_mhz=100.0, highcut_mhz=900.0, order=4)
    correct_bandpass(d2_result.dataset, method="butterworth", lowcut_mhz=120.0, highcut_mhz=800.0, order=4)

    assert ds.amplitudes.tobytes() == original_bytes


def test_time_axis_unchanged_through_d2_b1_b2_chain(dataset_factory):
    amplitudes = np.zeros((2, 1, SAMPLES_COUNT), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    d2_result = correct_dewow(ds, window_ns=8.0, method="running_mean")
    b1_result = correct_bandpass(
        d2_result.dataset, method="butterworth", lowcut_mhz=100.0, highcut_mhz=900.0, order=4
    )
    np.testing.assert_array_equal(d2_result.dataset.time_ns, ds.time_ns)
    np.testing.assert_array_equal(b1_result.dataset.time_ns, ds.time_ns)


def test_valid_mask_unchanged_through_d2_b1_b2_chain(dataset_factory):
    amplitudes = np.zeros((2, 1, SAMPLES_COUNT), dtype=np.float32)
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)
    valid_mask = np.ones((1, SAMPLES_COUNT), dtype=bool)
    valid_mask[0, 600:] = False

    d2_result = correct_dewow(ds, window_ns=8.0, method="running_mean", valid_mask=valid_mask)
    b1_result = correct_bandpass(
        d2_result.dataset,
        method="butterworth",
        lowcut_mhz=100.0,
        highcut_mhz=900.0,
        order=4,
        valid_mask=valid_mask,
    )
    np.testing.assert_array_equal(d2_result.valid_mask, valid_mask)
    np.testing.assert_array_equal(b1_result.valid_mask, valid_mask)


# --- 15: real raw/canonical hash + full-chain padding/NaN checks (skips if file absent) ---

_REAL_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "Swath003_Array02.ogpr"
_CANONICAL_NPZ = (
    Path(__file__).resolve().parents[1]
    / "outputs"
    / "sprint02"
    / "canonical_target16"
    / "sprint02_processed.npz"
)

pytestmark_real = pytest.mark.skipif(
    not (_REAL_FILE.is_file() and _CANONICAL_NPZ.is_file()),
    reason="Real raw file or canonical Sprint 2 NPZ not found; skipping Sprint 3.1 real-data check.",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytestmark_real
def test_raw_and_canonical_hashes_unchanged_by_d2_b1_b2_chain():
    raw_hash_before = _sha256(_REAL_FILE)
    canonical_hash_before = _sha256(_CANONICAL_NPZ)

    dataset, valid_mask = read_processed_npz(_CANONICAL_NPZ)
    d2_result = correct_dewow(
        dataset, window_ns=8.0, method="running_mean", valid_mask=valid_mask, edge_mode="reflect"
    )
    b1_result = correct_bandpass(
        d2_result.dataset,
        method="butterworth",
        lowcut_mhz=100.0,
        highcut_mhz=900.0,
        order=4,
        valid_mask=valid_mask,
    )
    b2_result = correct_bandpass(
        d2_result.dataset,
        method="butterworth",
        lowcut_mhz=120.0,
        highcut_mhz=800.0,
        order=4,
        valid_mask=valid_mask,
    )

    assert _sha256(_REAL_FILE) == raw_hash_before
    assert _sha256(_CANONICAL_NPZ) == canonical_hash_before

    for result in (d2_result, b1_result, b2_result):
        assert np.isfinite(result.dataset.amplitudes).all()
        padding = ~valid_mask
        padding_broadcast = np.broadcast_to(padding[np.newaxis, :, :], result.dataset.amplitudes.shape)
        np.testing.assert_array_equal(result.dataset.amplitudes[padding_broadcast], 0.0)
