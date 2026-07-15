"""Frequency-band energy integration for Sprint 3.1's decision QC.

Reuses ``compute_amplitude_spectrum()``'s own output (never a new spectrum
algorithm) for the aggregate and per-channel tables. ``per_slice_band_energy``
adds one genuinely new (but still read-only, QC-only) computation this
sprint needs that ``compute_amplitude_spectrum`` doesn't provide: energy in
a band *per individual trace*, to check whether a band's energy is spread
evenly across the profile or concentrated in a handful of traces.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def integrate_band_energy(
    frequencies_mhz: np.ndarray, amplitude_spectrum: np.ndarray, low_mhz: float, high_mhz: float
) -> float:
    """Sum of ``amplitude_spectrum**2`` for frequencies in ``[low_mhz, high_mhz)``."""
    in_band = (frequencies_mhz >= low_mhz) & (frequencies_mhz < high_mhz)
    return float((amplitude_spectrum[in_band].astype(np.float64) ** 2).sum())


def band_energy_table(spectrum: dict[str, Any], bands: list[tuple[str, float, float]]) -> dict[str, float]:
    """``{band_label: energy}`` for a spectrum dict's aggregate ``amplitude_spectrum``."""
    freqs = spectrum["frequencies_mhz"]
    amp = spectrum["amplitude_spectrum"]
    return {label: integrate_band_energy(freqs, amp, low, high) for label, low, high in bands}


def band_energy_table_per_channel(
    spectrum: dict[str, Any], bands: list[tuple[str, float, float]]
) -> dict[int, dict[str, float]]:
    """``{channel: {band_label: energy}}`` using a spectrum dict's ``per_channel_spectrum``."""
    freqs = spectrum["frequencies_mhz"]
    per_channel = spectrum["per_channel_spectrum"]
    return {
        channel: {
            label: integrate_band_energy(freqs, per_channel[channel], low, high) for label, low, high in bands
        }
        for channel in range(per_channel.shape[0])
    }


def retention_ratio(candidate_energy: float, reference_energy: float) -> float:
    """``candidate_energy / reference_energy``, or ``nan`` if the reference is zero."""
    return float(candidate_energy / reference_energy) if reference_energy > 0 else float("nan")


def per_slice_band_energy(
    windowed_amplitudes: np.ndarray, sampling_time_ns: float, low_mhz: float, high_mhz: float
) -> np.ndarray:
    """Energy in ``[low_mhz, high_mhz)`` for each individual trace. Shape ``(slices,)``.

    Vectorized real FFT across all traces at once (``np.fft.rfft(...,
    axis=1)``) -- ``compute_amplitude_spectrum`` only returns spectra
    already aggregated (mean/median/rms) across slices, so this is the one
    new computation Sprint 3.1 needs to ask "is this band's energy spread
    evenly across traces, or concentrated in a few?" (QC only -- this
    function draws no conclusion about *why* itself).
    """
    data = windowed_amplitudes.astype(np.float64)
    n_samples = data.shape[1]
    frequencies_hz = np.fft.rfftfreq(n_samples, d=sampling_time_ns * 1e-9)
    frequencies_mhz = frequencies_hz / 1e6
    in_band = (frequencies_mhz >= low_mhz) & (frequencies_mhz < high_mhz)
    spectrum = np.abs(np.fft.rfft(data, axis=1))
    return (spectrum[:, in_band] ** 2).sum(axis=1)


def rms_difference(a: np.ndarray, b: np.ndarray) -> float:
    """RMS of ``a - b`` over every value in both (same-shape) arrays."""
    diff = a.astype(np.float64) - b.astype(np.float64)
    return float(np.sqrt((diff**2).mean()))
