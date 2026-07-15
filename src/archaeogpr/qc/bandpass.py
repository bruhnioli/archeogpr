"""Band-pass QC figures: before/after/removed B-scans, spectra, transfer function, impulse response.

Reuses the same generic B-scan/median-trace helpers as ``qc/dewow.py`` (and
its ``save_median_trace_comparison``) for the shared parts of the QC suite;
adds transfer-function and impulse-response plots specific to band-pass
filters.
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import sosfilt, sosfiltfilt, sosfreqz

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.bandpass import build_butterworth_sos, build_ormsby_transfer_function
from archaeogpr.processing.result import ProcessingResult
from archaeogpr.qc.bscan import save_all_channels_bscan, save_bscan_comparison, save_channel_bscan
from archaeogpr.qc.dewow import save_median_trace_comparison
from archaeogpr.qc.spectrum import save_spectrum_comparison


def save_transfer_function_plot(
    output_path: str | Path,
    *,
    method: str,
    sampling_time_ns: float,
    lowcut_mhz: float | None = None,
    highcut_mhz: float | None = None,
    order: int | None = None,
    frequencies_mhz: tuple[float, float, float, float] | None = None,
    n_points: int = 4096,
) -> Path:
    """Plot ``|H(f)|`` for the exact filter design used by ``correct_bandpass``."""
    sampling_frequency_hz = 1.0 / (sampling_time_ns * 1e-9)
    fig, ax = plt.subplots(figsize=(10, 5))
    if method == "butterworth":
        assert lowcut_mhz is not None and highcut_mhz is not None and order is not None
        sos = build_butterworth_sos(lowcut_mhz, highcut_mhz, order, sampling_time_ns)
        w_hz, h = sosfreqz(sos, worN=n_points, fs=sampling_frequency_hz)
        ax.plot(w_hz / 1e6, np.abs(h), label="single-pass |H(f)|")
        ax.plot(
            w_hz / 1e6, np.abs(h) ** 2, label="zero-phase (sosfiltfilt) effective |H(f)|^2", linestyle="--"
        )
        title = f"Butterworth order={order} transfer function ([{lowcut_mhz}, {highcut_mhz}] MHz)"
    else:
        assert frequencies_mhz is not None
        frequencies_hz = np.linspace(0, sampling_frequency_hz / 2, n_points)
        h = build_ormsby_transfer_function(frequencies_hz, frequencies_mhz)
        ax.plot(frequencies_hz / 1e6, h, label="|H(f)| (real, zero-phase by construction)")
        title = f"Ormsby transfer function (corners={frequencies_mhz} MHz)"
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("|H(f)|")
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def save_impulse_response_plot(
    output_path: str | Path,
    *,
    method: str,
    sampling_time_ns: float,
    lowcut_mhz: float | None = None,
    highcut_mhz: float | None = None,
    order: int | None = None,
    zero_phase: bool = True,
    frequencies_mhz: tuple[float, float, float, float] | None = None,
    length: int = 201,
) -> Path:
    """Plot the time-domain impulse response actually used by ``correct_bandpass``."""
    impulse = np.zeros(length, dtype=np.float64)
    impulse[length // 2] = 1.0
    time_ns = (np.arange(length) - length // 2) * sampling_time_ns

    if method == "butterworth":
        assert lowcut_mhz is not None and highcut_mhz is not None and order is not None
        sos = build_butterworth_sos(lowcut_mhz, highcut_mhz, order, sampling_time_ns)
        response = sosfiltfilt(sos, impulse) if zero_phase else sosfilt(sos, impulse)
        title = f"Butterworth order={order} impulse response ({'zero-phase' if zero_phase else 'causal'})"
    else:
        assert frequencies_mhz is not None
        sampling_frequency_hz = 1.0 / (sampling_time_ns * 1e-9)
        frequencies_hz = np.fft.rfftfreq(length, d=sampling_time_ns * 1e-9)
        transfer = build_ormsby_transfer_function(frequencies_hz, frequencies_mhz)
        response = np.fft.fftshift(np.fft.irfft(np.fft.rfft(impulse) * transfer, n=length))
        title = (
            f"Ormsby impulse response (corners={frequencies_mhz} MHz, "
            f"fs={sampling_frequency_hz / 1e6:.4g} MHz)"
        )

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(time_ns, response)
    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Time (ns, centered on the impulse)")
    ax.set_ylabel("Amplitude")
    ax.set_title(title)
    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def save_bandpass_qc_suite(
    before: GPRDataset,
    result: ProcessingResult,
    output_dir: str | Path,
    *,
    channel: int = 0,
    clip_percentile: float = 99.0,
    cmap: str = "seismic",
) -> dict[str, Path]:
    """Save every required per-candidate band-pass QC figure. Returns a dict of the paths written."""
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
    difference_path = output_dir / f"{stem}_before_after_difference.png"
    shutil.copyfile(comparison_paths["difference"], difference_path)
    paths["channel_before_after_difference"] = difference_path

    removed_dataset = replace(after, amplitudes=result.removed_component)
    paths["channel_removed"] = save_channel_bscan(
        removed_dataset,
        channel,
        output_dir / f"{stem}_removed.png",
        clip_percentile=clip_percentile,
        cmap=cmap,
    )
    paths["all_channels_after"] = save_all_channels_bscan(
        after, output_dir / "all_channels_after.png", clip_percentile=clip_percentile, cmap=cmap
    )
    paths["median_trace_before_after"] = save_median_trace_comparison(
        before, after, output_dir / "median_trace_before_after.png"
    )
    paths["spectrum_before_after"] = save_spectrum_comparison(
        before,
        after,
        output_dir / "spectrum_before_after.png",
        valid_mask=result.valid_mask,
        freq_max_mhz=None,
        title="Amplitude spectrum -- before vs after band-pass (QC only)",
    )

    diagnostics = result.diagnostics
    sampling_time_ns = diagnostics["sampling_time_ns"]
    common_kwargs: dict[str, Any] = {"method": diagnostics["method"], "sampling_time_ns": sampling_time_ns}
    if diagnostics["method"] == "butterworth":
        common_kwargs.update(
            lowcut_mhz=diagnostics["lowcut_mhz"],
            highcut_mhz=diagnostics["highcut_mhz"],
            order=diagnostics["order"],
        )
    else:
        common_kwargs["frequencies_mhz"] = tuple(diagnostics["frequencies_mhz"])

    paths["transfer_function"] = save_transfer_function_plot(
        output_dir / "transfer_function.png", **common_kwargs
    )
    paths["impulse_response"] = save_impulse_response_plot(
        output_dir / "impulse_response.png",
        zero_phase=diagnostics.get("zero_phase", True),
        **common_kwargs,
    )
    return paths
