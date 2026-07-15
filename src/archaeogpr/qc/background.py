"""Background-removal QC figures and metrics.

Reuses existing generic B-scan/spectrum plotting (``qc/bscan.py``,
``qc/spectrum.py``, ``qc/time_zero.py``) and Sprint 3.1's spatial-coherence /
band-energy / phase-metrics analysis (``qc/spatial_coherence.py``,
``qc/band_energy.py``, ``qc/phase_metrics.py``) -- no new filtering
algorithm and no new spatial-coherence/phase math here, only orchestration
specific to background removal's before/after/removed comparison and its
particular scientific risk (see ``processing/background.py``, ADR-008):
that a genuinely long, laterally continuous reflection can be removed just
as effectively as unwanted common-mode noise.

Every metric here is explicitly QC-only. Nothing in this module produces or
implies an archaeological classification, probability, or label (see
CLAUDE.md) -- only numbers describing shape, energy, and continuity that a
human/geophysical reviewer can use to judge a candidate.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt
import numpy as np

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.common import dataset_time_window_mask
from archaeogpr.processing.result import ProcessingResult
from archaeogpr.qc.band_energy import band_energy_table, retention_ratio
from archaeogpr.qc.bscan import (
    compute_shared_clip_limit,
    plot_bscan,
    save_all_channels_bscan,
    save_bscan_comparison,
    save_channel_bscan,
)
from archaeogpr.qc.phase_metrics import compute_phase_waveform_metrics
from archaeogpr.qc.spatial_coherence import (
    band_energy_concentration,
    channel_to_channel_consistency,
    compute_spatial_coherence_metrics,
)
from archaeogpr.qc.spectrum import compute_amplitude_spectrum, to_db
from archaeogpr.qc.time_zero import plot_channel_median_traces, plot_channel_median_traces_overlay

#: QC-only frequency bands for removed-component energy distribution --
#: never presented as a physical antenna-band claim (see CLAUDE.md,
#: ADR-006's shared epistemic stance).
FREQUENCY_BANDS_MHZ: tuple[tuple[str, float, float], ...] = (
    ("0-100", 0.0, 100.0),
    ("100-300", 100.0, 300.0),
    ("300-600", 300.0, 600.0),
    ("600-900", 600.0, 900.0),
    ("900-1200", 900.0, 1200.0),
)

#: Sprint 4A's own time windows (spec section 14/16). ``-2.0`` is this
#: dataset's own time-zero-relative axis start (Sprint 2.2/ADR-004,
#: target_sample=16) -- a QC-window boundary choice, not a hardcoded binary
#: offset.
TIME_WINDOWS_NS: tuple[tuple[str, float, float], ...] = (
    ("W1", -2.0, 20.0),
    ("W2", 20.0, 40.0),
    ("W3", 40.0, 60.0),
    ("W4", 60.0, 100.0),
    ("W5", 20.0, 100.0),
)


def _windowed_channel(
    amplitudes_3d: np.ndarray,
    time_ns: np.ndarray,
    channel: int,
    start_ns: float,
    end_ns: float,
    valid_mask: np.ndarray | None,
) -> np.ndarray:
    """One channel's ``(slices, window_samples)`` slice within ``[start_ns, end_ns)``, padding zero-filled.

    Padding is zero-filled rather than excluded (the same convention Sprint
    3.1's decision QC used -- see ``qc/decision_qc.py::windowed_array``)
    because this project's ``valid_mask`` is channel-wide constant, so a
    window straddling the (small) leading-padding region only affects that
    channel's own few padded samples, already exactly zero.
    """
    sample_mask = dataset_time_window_mask(time_ns, start_ns, end_ns)
    data = amplitudes_3d[:, channel, sample_mask].astype(np.float64)
    if valid_mask is not None:
        valid_1d = valid_mask[channel, sample_mask]
        data = data * valid_1d[np.newaxis, :]
    return data


def _pooled_windowed(
    amplitudes_3d: np.ndarray,
    time_ns: np.ndarray,
    channels: tuple[int, ...],
    start_ns: float,
    end_ns: float,
    valid_mask: np.ndarray | None,
) -> np.ndarray:
    """Vstack ``channels``' windowed arrays into one ``(len(channels)*slices, window_samples)`` array."""
    return np.concatenate(
        [_windowed_channel(amplitudes_3d, time_ns, ch, start_ns, end_ns, valid_mask) for ch in channels],
        axis=0,
    )


# ======================================================================
# Plotting
# ======================================================================


def save_before_after_removed_panel(
    before: GPRDataset,
    result: ProcessingResult,
    channel: int,
    output_path: str | Path,
    *,
    clip_percentile: float = 99.0,
    cmap: str = "seismic",
) -> Path:
    """One PNG, 3 side-by-side panels: before / after / removed, sharing one symmetric clip scale."""
    after = result.dataset
    removed_dataset = replace(after, amplitudes=result.removed_component)
    shared_limit = compute_shared_clip_limit(
        before.amplitudes[:, channel, :],
        after.amplitudes[:, channel, :],
        result.removed_component[:, channel, :],
        clip_percentile=clip_percentile,
    )

    fig, axes = plt.subplots(1, 3, figsize=(21, 5))
    for ax, dataset, label in (
        (axes[0], before, "before"),
        (axes[1], after, "after"),
        (axes[2], removed_dataset, "removed"),
    ):
        plot_bscan(
            dataset,
            channel,
            vlimit=shared_limit,
            cmap=cmap,
            ax=ax,
            title=f"Channel {channel:02d} -- {label} (±{shared_limit:.4g} clip)",
        )
    fig.colorbar(axes[-1].images[0], ax=axes, label="Amplitude (raw, ungained)", fraction=0.02)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def save_removed_component_spectrum(
    result: ProcessingResult,
    output_path: str | Path,
    *,
    valid_mask: np.ndarray | None = None,
    time_start_ns: float = 0.0,
    time_end_ns: float = 100.0,
    freq_max_mhz: float | None = None,
    title: str | None = None,
) -> Path:
    """Single-curve amplitude spectrum (dB) of ``result.removed_component`` itself."""
    removed_dataset = replace(result.dataset, amplitudes=result.removed_component)
    spectrum = compute_amplitude_spectrum(
        removed_dataset, time_start_ns=time_start_ns, time_end_ns=time_end_ns, valid_mask=valid_mask
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(spectrum["frequencies_mhz"], to_db(spectrum["amplitude_spectrum"]))
    if freq_max_mhz is not None:
        ax.set_xlim(0, freq_max_mhz)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Amplitude (dB, relative to this spectrum's own peak)")
    ax.set_title(title or "Removed-component amplitude spectrum (QC only)")
    fig.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def save_background_qc_suite(
    before: GPRDataset,
    result: ProcessingResult,
    output_dir: str | Path,
    *,
    channel: int = 0,
    secondary_channels: tuple[int, ...] = (5, 10),
    clip_percentile: float = 99.0,
    cmap: str = "seismic",
) -> dict[str, Path]:
    """Save every required per-candidate background-removal QC figure.

    Returns a dict of the paths written. ``channel`` gets the full
    before/after/removed/difference treatment; each of ``secondary_channels``
    gets one combined before/after/removed panel (fewer files, still visual
    coverage of channels 5 and 10 -- see Sprint 4A spec section 13).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    after = result.dataset
    stem = f"channel{channel:02d}"
    paths: dict[str, Path] = {}

    comparison_paths = save_bscan_comparison(
        before, after, channel, output_dir, stem, clip_percentile=clip_percentile, cmap=cmap
    )
    paths["channel_before"] = comparison_paths["before"]
    paths["channel_after"] = comparison_paths["after"]
    paths["channel_difference"] = comparison_paths["difference"]

    removed_dataset = replace(after, amplitudes=result.removed_component)
    paths["channel_removed"] = save_channel_bscan(
        removed_dataset,
        channel,
        output_dir / f"{stem}_removed.png",
        clip_percentile=clip_percentile,
        cmap=cmap,
    )

    for secondary_channel in secondary_channels:
        paths[f"channel{secondary_channel:02d}_before_after_removed"] = save_before_after_removed_panel(
            before,
            result,
            secondary_channel,
            output_dir / f"channel{secondary_channel:02d}_before_after_removed.png",
            clip_percentile=clip_percentile,
            cmap=cmap,
        )

    paths["all_channels_after"] = save_all_channels_bscan(
        after, output_dir / "all_channels_after.png", clip_percentile=clip_percentile, cmap=cmap
    )

    fig, ax = plt.subplots(figsize=(12, 6))
    plot_channel_median_traces_overlay(
        before, after, ax=ax, title="Median trace -- before vs after background removal"
    )
    fig.tight_layout()
    median_path = output_dir / "median_trace_before_after.png"
    fig.savefig(median_path, dpi=140)
    plt.close(fig)
    paths["median_trace_before_after"] = median_path

    fig, ax = plt.subplots(figsize=(10, 5))
    plot_channel_median_traces(removed_dataset, ax=ax, title="Removed component -- channel median traces")
    fig.tight_layout()
    removed_median_path = output_dir / "removed_component_median_trace.png"
    fig.savefig(removed_median_path, dpi=140)
    plt.close(fig)
    paths["removed_component_median_trace"] = removed_median_path

    paths["removed_component_spectrum"] = save_removed_component_spectrum(
        result, output_dir / "removed_component_spectrum.png", valid_mask=result.valid_mask
    )

    return paths


# ======================================================================
# Metrics: signal preservation (output vs canonical Sprint 3 input)
# ======================================================================


def compute_signal_preservation_metrics(
    before: GPRDataset,
    result: ProcessingResult,
    valid_mask: np.ndarray | None,
    *,
    channels: tuple[int, ...] = (0, 5, 10),
    time_windows: tuple[tuple[str, float, float], ...] = TIME_WINDOWS_NS,
) -> dict[str, dict[str, Any]]:
    """Per-time-window signal-preservation metrics, pooling ``channels`` together.

    Combines Sprint 3.1's phase/waveform metrics (``compute_phase_waveform_
    metrics``, applied here to a background-removal before/after pair
    instead of a dewow/band-pass one) with RMS/energy/spectral retention
    ratios, a median-trace correlation, a local-event amplitude-retention
    proxy, and channel-to-channel consistency before/after (Sprint 4A spec
    section 16). Background removal is not a time-shift filter -- a median
    lag near 0 and small peak/zero-crossing displacements are the expected
    result, not proof by themselves (see the same late-time-window caveat
    documented in Sprint 3.1 / ``qc/phase_metrics.py``).
    """
    after = result.dataset
    sampling_time_ns = before.metadata["sampling"]["sampling_time_ns"]
    by_window: dict[str, dict[str, Any]] = {}
    for label, start_ns, end_ns in time_windows:
        before_pooled = _pooled_windowed(
            before.amplitudes, before.time_ns, channels, start_ns, end_ns, valid_mask
        )
        after_pooled = _pooled_windowed(
            after.amplitudes, after.time_ns, channels, start_ns, end_ns, valid_mask
        )

        waveform_metrics = compute_phase_waveform_metrics(before_pooled, after_pooled)

        before_rms = float(np.sqrt((before_pooled**2).mean()))
        after_rms = float(np.sqrt((after_pooled**2).mean()))
        rms_retention = (after_rms / before_rms) if before_rms > 0 else float("nan")

        before_energy = float((before_pooled**2).sum())
        after_energy = float((after_pooled**2).sum())
        absolute_energy_retention = (after_energy / before_energy) if before_energy > 0 else float("nan")

        before_spectrum = compute_amplitude_spectrum(
            before, time_start_ns=start_ns, time_end_ns=end_ns, valid_mask=valid_mask
        )
        after_spectrum = compute_amplitude_spectrum(
            after, time_start_ns=start_ns, time_end_ns=end_ns, valid_mask=valid_mask
        )
        before_spectral_energy = float((before_spectrum["amplitude_spectrum"] ** 2).sum())
        after_spectral_energy = float((after_spectrum["amplitude_spectrum"] ** 2).sum())
        spectral_energy_retention = retention_ratio(after_spectral_energy, before_spectral_energy)

        adjacent_before = compute_spatial_coherence_metrics(before_pooled)
        adjacent_after = compute_spatial_coherence_metrics(after_pooled)

        median_before_trace = np.median(before_pooled, axis=0)
        median_after_trace = np.median(after_pooled, axis=0)
        median_trace_correlation = (
            float(np.corrcoef(median_before_trace, median_after_trace)[0, 1])
            if median_before_trace.std() > 0 and median_after_trace.std() > 0
            else float("nan")
        )

        # Local-event amplitude retention: a QC-only proxy, not a target pick --
        # each pooled trace's own dominant (before) sample stands in for "a
        # local event on this trace", and we ask how much of that specific
        # sample's amplitude survives in the same before/after pair, mirroring
        # the same peak-location methodology already used for peak_sample_diff.
        before_peak_idx = np.argmax(np.abs(before_pooled), axis=1)
        before_peak_amp = np.abs(np.take_along_axis(before_pooled, before_peak_idx[:, np.newaxis], axis=1))
        after_peak_amp = np.abs(np.take_along_axis(after_pooled, before_peak_idx[:, np.newaxis], axis=1))
        nonzero = before_peak_amp[:, 0] > 0
        local_event_amplitude_retention = (
            float(np.median(after_peak_amp[nonzero, 0] / before_peak_amp[nonzero, 0]))
            if nonzero.any()
            else float("nan")
        )

        channel_before_coherence = {
            ch: compute_spatial_coherence_metrics(
                _windowed_channel(before.amplitudes, before.time_ns, ch, start_ns, end_ns, valid_mask)
            )
            for ch in channels
        }
        channel_after_coherence = {
            ch: compute_spatial_coherence_metrics(
                _windowed_channel(after.amplitudes, after.time_ns, ch, start_ns, end_ns, valid_mask)
            )
            for ch in channels
        }
        consistency_before = channel_to_channel_consistency(channel_before_coherence)
        consistency_after = channel_to_channel_consistency(channel_after_coherence)

        by_window[label] = {
            **waveform_metrics,
            "rms_retention": rms_retention,
            "absolute_energy_retention": absolute_energy_retention,
            "spectral_energy_retention": spectral_energy_retention,
            "adjacent_trace_correlation_before": adjacent_before["adjacent_trace_correlation_median"],
            "adjacent_trace_correlation_after": adjacent_after["adjacent_trace_correlation_median"],
            "median_trace_correlation": median_trace_correlation,
            "local_event_amplitude_retention": local_event_amplitude_retention,
            **{f"channel_consistency_before_{k}": v for k, v in consistency_before.items()},
            **{f"channel_consistency_after_{k}": v for k, v in consistency_after.items()},
        }
    _ = sampling_time_ns  # reserved for future frequency-aware preservation checks
    return by_window


# ======================================================================
# Metrics: removed-component QC (energy, spatial continuity, time/frequency,
# and a QC-only localized/curved-event risk proxy)
# ======================================================================


def compute_localized_event_risk(removed_windowed: np.ndarray) -> dict[str, float]:
    """QC-only proxy for whether ``removed_windowed`` looks flat/laterally-continuous or local/curved.

    This is deliberately NOT an archaeological classifier: it never returns
    a target probability, a "wall"/"tomb" label, or any object identity --
    only a few interpretable numbers about the *shape* of the array itself
    (gradient energy along the trace axis vs the time axis, and along-trace
    curvature). A flat, laterally continuous background has low horizontal
    gradient and low curvature; a localized or curved (e.g. hyperbolic)
    event raises both. Read alongside spatial-coherence metrics, never
    alone (see CLAUDE.md, ADR-008).
    """
    data = removed_windowed.astype(np.float64)
    if data.shape[0] < 2 or data.shape[1] < 2:
        return {
            "horizontal_gradient_energy": float("nan"),
            "vertical_gradient_energy": float("nan"),
            "gradient_anisotropy_ratio": float("nan"),
            "local_curvature_energy": float("nan"),
        }
    horizontal_gradient = np.diff(data, axis=0)  # along the trace/slice axis
    vertical_gradient = np.diff(data, axis=1)  # along the sample/time axis
    horizontal_energy = float((horizontal_gradient**2).mean())
    vertical_energy = float((vertical_gradient**2).mean())
    anisotropy = (horizontal_energy / vertical_energy) if vertical_energy > 0 else float("nan")
    if data.shape[0] >= 3:
        curvature_energy = float((np.diff(data, n=2, axis=0) ** 2).mean())
    else:
        curvature_energy = float("nan")
    return {
        "horizontal_gradient_energy": horizontal_energy,
        "vertical_gradient_energy": vertical_energy,
        "gradient_anisotropy_ratio": anisotropy,
        "local_curvature_energy": curvature_energy,
    }


def compute_removed_component_metrics(
    before: GPRDataset,
    result: ProcessingResult,
    valid_mask: np.ndarray | None,
    *,
    channels: tuple[int, ...] = (0, 5, 10),
    time_windows: tuple[tuple[str, float, float], ...] = TIME_WINDOWS_NS,
    frequency_bands_mhz: tuple[tuple[str, float, float], ...] = FREQUENCY_BANDS_MHZ,
) -> dict[str, dict[str, Any]]:
    """Per-time-window metrics describing ``result.removed_component`` itself.

    Combines energy/amplitude ratios (RMS, squared-energy, and absolute-
    energy ratios), Sprint 3.1's spatial-coherence metrics plus a spatial-
    concentration score, frequency-band energy (reusing
    ``compute_amplitude_spectrum``), and :func:`compute_localized_event_risk`.
    QC only.
    """
    removed_dataset = replace(result.dataset, amplitudes=result.removed_component)
    by_window: dict[str, dict[str, Any]] = {}
    for label, start_ns, end_ns in time_windows:
        input_pooled = _pooled_windowed(
            before.amplitudes, before.time_ns, channels, start_ns, end_ns, valid_mask
        )
        removed_pooled = _pooled_windowed(
            result.removed_component, result.dataset.time_ns, channels, start_ns, end_ns, valid_mask
        )

        input_rms = float(np.sqrt((input_pooled**2).mean()))
        removed_rms = float(np.sqrt((removed_pooled**2).mean()))
        removed_input_rms_ratio = (removed_rms / input_rms) if input_rms > 0 else float("nan")

        input_energy = float((input_pooled**2).sum())
        removed_energy = float((removed_pooled**2).sum())
        removed_input_energy_ratio = retention_ratio(removed_energy, input_energy)

        input_absolute_energy = float(np.abs(input_pooled).sum())
        removed_absolute_energy = float(np.abs(removed_pooled).sum())
        removed_input_absolute_energy_ratio = retention_ratio(removed_absolute_energy, input_absolute_energy)

        coherence = compute_spatial_coherence_metrics(removed_pooled)
        per_slice_removed_energy = (removed_pooled.astype(np.float64) ** 2).sum(axis=1)
        concentration = band_energy_concentration(per_slice_removed_energy)
        per_channel_coherence = {
            channel: compute_spatial_coherence_metrics(
                _windowed_channel(
                    result.removed_component, result.dataset.time_ns, channel, start_ns, end_ns, valid_mask
                )
            )
            for channel in channels
        }
        consistency = channel_to_channel_consistency(per_channel_coherence)

        removed_spectrum = compute_amplitude_spectrum(
            removed_dataset, time_start_ns=start_ns, time_end_ns=end_ns, valid_mask=valid_mask
        )
        band_energy = band_energy_table(removed_spectrum, list(frequency_bands_mhz))

        risk = compute_localized_event_risk(removed_pooled)

        by_window[label] = {
            "removed_peak_amplitude": float(np.max(np.abs(removed_pooled))) if removed_pooled.size else 0.0,
            "removed_median_abs_amplitude": float(np.median(np.abs(removed_pooled)))
            if removed_pooled.size
            else 0.0,
            "removed_input_rms_ratio": removed_input_rms_ratio,
            "removed_input_energy_ratio": removed_input_energy_ratio,
            "removed_input_absolute_energy_ratio": removed_input_absolute_energy_ratio,
            **coherence,
            **consistency,
            "spatial_concentration_coefficient_of_variation": concentration["coefficient_of_variation"],
            "spatial_concentration_top_fraction_energy_share": concentration["top_fraction_energy_share"],
            "band_energy_mhz": band_energy,
            **risk,
        }
    return by_window
