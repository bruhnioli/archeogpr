"""Amplitude spectrum computation for GPR traces -- a read-only QC/analysis tool.

Lives in ``qc/`` rather than ``processing/`` because it never produces a new
``GPRDataset`` -- it only reads ``dataset.amplitudes``/``time_ns`` and
reports numbers/arrays back. Nothing here interprets a spectral feature as
"the real antenna band" or any other physical/archaeological claim -- these
are QC metrics only (see CLAUDE.md and ADR-004/005/006's shared epistemic
stance).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt
import numpy as np

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.common import ProcessingError

_DETREND_OPTIONS = ("constant", None)
_TAPER_OPTIONS = ("hann", None)
_AGGREGATION_OPTIONS = ("mean", "median", "rms")

#: Floor used before taking 20*log10(...) so a zero/near-zero bin never
#: produces -inf or a RuntimeWarning -- a fixed, tiny amplitude floor, not a
#: physically meaningful noise floor.
_DB_SAFETY_FLOOR = 1e-12


def to_db(spectrum: np.ndarray, *, reference: float | None = None) -> np.ndarray:
    """``20*log10(spectrum / reference)``, floored so it's always finite.

    ``reference`` defaults to ``spectrum.max()`` (or ``1.0`` if that is 0).
    """
    spectrum = np.asarray(spectrum, dtype=np.float64)
    if reference is None:
        reference = float(spectrum.max()) or 1.0
    ratio = np.maximum(spectrum, _DB_SAFETY_FLOOR) / reference
    return 20.0 * np.log10(np.maximum(ratio, _DB_SAFETY_FLOOR))


def _aggregate(spectra: np.ndarray, aggregation: str) -> np.ndarray:
    """Reduce ``spectra`` (shape ``(n_traces, n_freq)``) to ``(n_freq,)``."""
    if aggregation == "mean":
        return spectra.mean(axis=0)
    if aggregation == "median":
        return np.median(spectra, axis=0)
    if aggregation == "rms":
        return np.sqrt((spectra**2).mean(axis=0))
    raise ProcessingError(f"aggregation must be one of {_AGGREGATION_OPTIONS}, got {aggregation!r}")


def compute_amplitude_spectrum(
    dataset: GPRDataset,
    *,
    time_start_ns: float = 0.0,
    time_end_ns: float = 100.0,
    valid_mask: np.ndarray | None = None,
    detrend: str | None = "constant",
    taper: str | None = "hann",
    aggregation: str = "median",
) -> dict[str, Any]:
    """Amplitude (not power) spectrum of ``dataset`` within ``[time_start_ns, time_end_ns)``.

    The time window is resolved against ``dataset.time_ns`` itself (so it
    behaves correctly whether or not the dataset has been through
    time-zero correction -- see ADR-004's ``dataset_time`` convention).
    When ``valid_mask`` (shape ``(channels, samples)``) is given, only
    samples valid in *every* channel, inside the window, are used -- this
    guarantees every selected trace has the same sample count, which a
    single shared frequency axis requires. Padding is never read.

    Returns a dict with ``frequencies_mhz``, ``amplitude_spectrum``
    (aggregated across all slices and channels), ``amplitude_spectrum_db``,
    ``amplitude_spectrum_normalized``, ``per_channel_spectrum`` (shape
    ``(channels, n_freq)``, aggregated across slices only), and
    ``metadata`` (sampling frequency, Nyquist, FFT length, frequency
    resolution, time window, taper, detrend, aggregation, valid sample
    count actually used). Raises ``ProcessingError`` for an invalid
    detrend/taper/aggregation, a window selecting zero common samples, or
    a window with fewer than 2 samples (FFT is not meaningful below that).
    """
    if detrend not in _DETREND_OPTIONS:
        raise ProcessingError(f"detrend must be one of {_DETREND_OPTIONS}, got {detrend!r}")
    if taper not in _TAPER_OPTIONS:
        raise ProcessingError(f"taper must be one of {_TAPER_OPTIONS}, got {taper!r}")
    if aggregation not in _AGGREGATION_OPTIONS:
        raise ProcessingError(f"aggregation must be one of {_AGGREGATION_OPTIONS}, got {aggregation!r}")
    if time_end_ns <= time_start_ns:
        raise ProcessingError(
            f"time_end_ns ({time_end_ns}) must be greater than time_start_ns ({time_start_ns})"
        )

    sampling = dataset.metadata.get("sampling") or {}
    sampling_time_ns = sampling.get("sampling_time_ns")
    if sampling_time_ns is None:
        raise ProcessingError(
            "dataset.metadata['sampling']['sampling_time_ns'] is required for spectrum analysis"
        )

    slices_count, channels_count, samples_count = dataset.shape
    window_mask = (dataset.time_ns >= time_start_ns) & (dataset.time_ns < time_end_ns)
    if not window_mask.any():
        raise ProcessingError(
            f"window [{time_start_ns}, {time_end_ns}) ns selects zero samples from this dataset's "
            f"time_ns range [{float(dataset.time_ns.min())}, {float(dataset.time_ns.max())}] ns"
        )

    if valid_mask is not None:
        if valid_mask.shape != (channels_count, samples_count):
            raise ProcessingError(
                f"valid_mask shape {valid_mask.shape} does not match "
                f"(channels, samples)={(channels_count, samples_count)}"
            )
        common_valid_across_channels = np.all(np.asarray(valid_mask, dtype=bool), axis=0)
    else:
        common_valid_across_channels = np.ones(samples_count, dtype=bool)

    common_mask = window_mask & common_valid_across_channels
    n_samples = int(common_mask.sum())
    if n_samples < 2:
        raise ProcessingError(
            f"window [{time_start_ns}, {time_end_ns}) ns intersected with valid_mask selects only "
            f"{n_samples} sample(s) common to every channel -- at least 2 are required for an FFT"
        )

    selected = dataset.amplitudes[:, :, common_mask].astype(np.float64)  # (slices, channels, n_samples)

    if detrend == "constant":
        selected = selected - selected.mean(axis=2, keepdims=True)
    if taper == "hann":
        selected = selected * np.hanning(n_samples)

    complex_spectrum = np.fft.rfft(selected, axis=2)  # (slices, channels, n_freq)
    amplitude = np.abs(complex_spectrum)

    sampling_time_s = sampling_time_ns * 1e-9
    frequencies_hz = np.fft.rfftfreq(n_samples, d=sampling_time_s)
    frequencies_mhz = frequencies_hz / 1e6
    sampling_frequency_hz = 1.0 / sampling_time_s
    nyquist_hz = sampling_frequency_hz / 2.0
    frequency_resolution_hz = sampling_frequency_hz / n_samples

    per_channel_spectrum = np.stack(
        [_aggregate(amplitude[:, channel, :], aggregation) for channel in range(channels_count)]
    )
    overall_spectrum = _aggregate(amplitude.reshape(-1, amplitude.shape[-1]), aggregation)
    overall_max = float(overall_spectrum.max())
    normalized = overall_spectrum / overall_max if overall_max > 0 else overall_spectrum.copy()

    metadata: dict[str, Any] = {
        "sampling_frequency_hz": sampling_frequency_hz,
        "sampling_frequency_mhz": sampling_frequency_hz / 1e6,
        "nyquist_hz": nyquist_hz,
        "nyquist_mhz": nyquist_hz / 1e6,
        "fft_length": n_samples,
        "frequency_resolution_hz": frequency_resolution_hz,
        "frequency_resolution_mhz": frequency_resolution_hz / 1e6,
        "time_start_ns": time_start_ns,
        "time_end_ns": time_end_ns,
        "valid_mask_provided": valid_mask is not None,
        "common_valid_sample_count": n_samples,
        "taper": taper,
        "detrend": detrend,
        "aggregation": aggregation,
    }

    return {
        "frequencies_mhz": frequencies_mhz,
        "amplitude_spectrum": overall_spectrum,
        "amplitude_spectrum_db": to_db(overall_spectrum),
        "amplitude_spectrum_normalized": normalized,
        "per_channel_spectrum": per_channel_spectrum,
        "metadata": metadata,
    }


def save_spectrum_comparison(
    before: GPRDataset,
    after: GPRDataset,
    output_path: str | Path,
    *,
    valid_mask: np.ndarray | None = None,
    time_start_ns: float = 0.0,
    time_end_ns: float = 100.0,
    freq_max_mhz: float | None = None,
    title: str | None = None,
) -> Path:
    """Save a before/after amplitude spectrum comparison (dB scale) as one PNG.

    ``freq_max_mhz`` zooms the x-axis (e.g. to inspect low-frequency
    content specifically); ``None`` shows the full range up to Nyquist.
    QC only -- no claim that either spectrum's shape reflects "the real"
    antenna band (see CLAUDE.md, ADR-004/005/006).
    """
    before_spectrum = compute_amplitude_spectrum(
        before, time_start_ns=time_start_ns, time_end_ns=time_end_ns, valid_mask=valid_mask
    )
    after_spectrum = compute_amplitude_spectrum(
        after, time_start_ns=time_start_ns, time_end_ns=time_end_ns, valid_mask=valid_mask
    )

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(before_spectrum["frequencies_mhz"], before_spectrum["amplitude_spectrum_db"], label="before")
    ax.plot(after_spectrum["frequencies_mhz"], after_spectrum["amplitude_spectrum_db"], label="after")
    if freq_max_mhz is not None:
        ax.set_xlim(0, freq_max_mhz)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Amplitude (dB, relative to each spectrum's own peak)")
    ax.set_title(title or "Amplitude spectrum -- before vs after (QC only)")
    ax.legend()
    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path
