"""Integration test for Sprint 3 (dewow + band-pass) against the real sample file.

Skips cleanly (not a failure) if the file is not present under data/raw/.
Rebuilds the canonical Sprint 2 pipeline (time-zero target_sample=16 + DC
offset mean, 20-100ns dataset_time window -- see ADR-004) directly from the
raw file, then runs dewow and both band-pass methods through it. Only
structural/statistical properties are asserted here (shape, dtype,
finiteness, hash, time axis, valid mask, padding, processing history,
spectral energy ratios, peak-position tolerance, QC/NPZ round-trips) --
never a scientific/archaeological interpretation, and no candidate is
marked canonical anywhere in this test.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from archaeogpr.export.processed import write_corrected_npz
from archaeogpr.export.sprint3 import read_processed_npz, write_padding_verification_json
from archaeogpr.io.ogpr_reader import read_ogpr
from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.bandpass import correct_bandpass
from archaeogpr.processing.dc_offset import correct_dc_offset
from archaeogpr.processing.dewow import correct_dewow
from archaeogpr.processing.result import ProcessingResult
from archaeogpr.processing.time_zero import correct_time_zero
from archaeogpr.qc.bandpass import save_bandpass_qc_suite
from archaeogpr.qc.dewow import save_dewow_qc_suite
from archaeogpr.qc.spectrum import compute_amplitude_spectrum

_REAL_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "Swath003_Array02.ogpr"

pytestmark = pytest.mark.skipif(
    not _REAL_FILE.is_file(),
    reason=f"Real sample file not found at {_REAL_FILE}; skipping Sprint 3 integration test.",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sprint2(raw: GPRDataset) -> ProcessingResult:
    """Rebuild the canonical Sprint 2.2 pipeline (ADR-004) directly from the raw file."""
    tz_result = correct_time_zero(
        raw,
        method="channel_median_peak",
        search_start_ns=5.0,
        search_end_ns=15.0,
        target_sample=16,
        peak_polarity="max_abs",
        max_shift_samples=96,
    )
    return correct_dc_offset(
        tz_result.dataset,
        method="mean",
        window_start_ns=20.0,
        window_end_ns=100.0,
        valid_mask=tz_result.valid_mask,
        window_reference="dataset_time",
    )


def test_sprint3_dewow_and_bandpass_on_real_file(tmp_path):
    hash_before = _sha256(_REAL_FILE)
    raw = read_ogpr(_REAL_FILE)
    raw_amplitudes_before = raw.amplitudes.copy()
    assert raw.shape == (175, 11, 1024)
    assert raw.amplitudes.dtype == np.dtype("<f4")

    dc_result = _canonical_sprint2(raw)
    canonical_dataset = dc_result.dataset
    valid_mask = dc_result.valid_mask
    assert valid_mask is not None
    assert canonical_dataset.shape == raw.shape

    # Time-zero-relative axis, derived from the dataset itself (ADR-004), not hardcoded.
    assert canonical_dataset.time_ns[16] == pytest.approx(0.0)
    assert canonical_dataset.time_ns[0] < 0.0

    dewow_result = correct_dewow(
        canonical_dataset, window_ns=8.0, method="running_mean", valid_mask=valid_mask
    )
    bandpass_result = correct_bandpass(
        dewow_result.dataset,
        method="butterworth",
        lowcut_mhz=100.0,
        highcut_mhz=800.0,
        order=4,
        valid_mask=valid_mask,
    )
    ormsby_result = correct_bandpass(
        dewow_result.dataset,
        method="ormsby",
        frequencies_mhz=(80.0, 120.0, 800.0, 1000.0),
        valid_mask=valid_mask,
    )

    # --- shape / dtype / finiteness --------------------------------------------
    for result in (dewow_result, bandpass_result, ormsby_result):
        assert result.dataset.shape == raw.shape
        assert result.dataset.amplitudes.dtype == np.float32
        assert np.isfinite(result.dataset.amplitudes).all()

    # --- time axis preserved end to end -----------------------------------------
    np.testing.assert_array_equal(dewow_result.dataset.time_ns, canonical_dataset.time_ns)
    np.testing.assert_array_equal(bandpass_result.dataset.time_ns, canonical_dataset.time_ns)

    # --- valid mask preserved -----------------------------------------------------
    assert dewow_result.valid_mask is not None
    assert bandpass_result.valid_mask is not None
    np.testing.assert_array_equal(dewow_result.valid_mask, valid_mask)
    np.testing.assert_array_equal(bandpass_result.valid_mask, valid_mask)

    # --- padding exactly zero after every stage -----------------------------------
    padding = ~valid_mask
    for result in (dewow_result, bandpass_result, ormsby_result):
        padding_broadcast = np.broadcast_to(padding[np.newaxis, :, :], result.dataset.amplitudes.shape)
        np.testing.assert_array_equal(result.dataset.amplitudes[padding_broadcast], 0.0)
        np.testing.assert_array_equal(result.removed_component[padding_broadcast], 0.0)

    # --- input immutability: the raw dataset object is never mutated -------------
    np.testing.assert_array_equal(raw.amplitudes, raw_amplitudes_before)

    # --- processing history order -------------------------------------------------
    assert [r["operation"] for r in dewow_result.dataset.processing_history] == [
        "time_zero_correction",
        "dc_offset_correction",
        "dewow_correction",
    ]
    assert [r["operation"] for r in bandpass_result.dataset.processing_history] == [
        "time_zero_correction",
        "dc_offset_correction",
        "dewow_correction",
        "bandpass_correction",
    ]

    # --- dewow reduces low-frequency energy without collapsing the whole spectrum --
    spectrum_before = compute_amplitude_spectrum(
        canonical_dataset, time_start_ns=0.0, time_end_ns=100.0, valid_mask=valid_mask
    )
    spectrum_after_dewow = compute_amplitude_spectrum(
        dewow_result.dataset, time_start_ns=0.0, time_end_ns=100.0, valid_mask=valid_mask
    )

    def _low_freq_energy_ratio(spectrum: dict) -> float:
        freqs = spectrum["frequencies_mhz"]
        amp = spectrum["amplitude_spectrum"]
        total = float((amp**2).sum())
        low = float((amp[freqs <= 100.0] ** 2).sum())
        return low / total if total > 0 else 0.0

    ratio_before = _low_freq_energy_ratio(spectrum_before)
    ratio_after = _low_freq_energy_ratio(spectrum_after_dewow)
    assert ratio_after < ratio_before  # low-frequency "wow" energy share must drop
    assert (
        float((spectrum_after_dewow["amplitude_spectrum"] ** 2).sum()) > 0.0
    )  # spectrum not collapsed to zero

    # --- band-pass retains passband energy while reducing stopband energy ---------
    all_passband_after = [
        e["passband_energy_fraction_after"]
        for e in bandpass_result.diagnostics["band_energy_fraction_per_segment"].values()
    ]
    assert np.mean(all_passband_after) > 0.8  # most energy inside [100, 800] MHz retained
    spectrum_after_bandpass = compute_amplitude_spectrum(
        bandpass_result.dataset, time_start_ns=0.0, time_end_ns=100.0, valid_mask=valid_mask
    )

    def _stopband_energy(spectrum: dict, low_mhz: float, high_mhz: float) -> float:
        freqs = spectrum["frequencies_mhz"]
        amp = spectrum["amplitude_spectrum"]
        return float((amp[(freqs < low_mhz) | (freqs > high_mhz)] ** 2).sum())

    stopband_before = _stopband_energy(spectrum_before, 100.0, 800.0)
    stopband_after = _stopband_energy(spectrum_after_bandpass, 100.0, 800.0)
    assert stopband_after < stopband_before

    # --- median-trace main-event sample position preserved within tolerance -------
    channel = 0
    median_before = np.median(canonical_dataset.amplitudes[:, channel, :].astype(np.float64), axis=0)
    median_after = np.median(bandpass_result.dataset.amplitudes[:, channel, :].astype(np.float64), axis=0)
    peak_before = int(np.argmax(np.abs(median_before)))
    peak_after = int(np.argmax(np.abs(median_after)))
    assert abs(peak_after - peak_before) <= 5  # dewow is not itself proven zero-phase; band-pass is

    # --- output NPZ reopens ---------------------------------------------------------
    npz_path = write_corrected_npz(bandpass_result, tmp_path / "bandpass_processed.npz")
    reloaded_dataset, reloaded_mask = read_processed_npz(npz_path)
    np.testing.assert_array_equal(reloaded_dataset.amplitudes, bandpass_result.dataset.amplitudes)
    assert reloaded_mask is not None
    np.testing.assert_array_equal(reloaded_mask, bandpass_result.valid_mask)

    # --- QC files are valid (non-empty, generated without error) ---------------------
    dewow_qc_paths = save_dewow_qc_suite(canonical_dataset, dewow_result, tmp_path / "dewow_qc")
    for path in dewow_qc_paths.values():
        assert path.stat().st_size > 0
    bandpass_qc_paths = save_bandpass_qc_suite(
        dewow_result.dataset, bandpass_result, tmp_path / "bandpass_qc"
    )
    for path in bandpass_qc_paths.values():
        assert path.stat().st_size > 0
    write_padding_verification_json(bandpass_result, tmp_path / "padding_verification.json")

    # --- no candidate marked canonical anywhere -------------------------------------
    for result in (dewow_result, bandpass_result, ormsby_result):
        assert "canonical" not in result.diagnostics
        assert "canonical" not in result.dataset.metadata

    # --- raw file untouched on disk --------------------------------------------------
    hash_after = _sha256(_REAL_FILE)
    assert hash_after == hash_before
