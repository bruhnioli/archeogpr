"""DC offset correction QC figures: offset distribution and trace-mean comparisons.

B-scan before/after/difference figures for DC offset live in
``archaeogpr.qc.bscan`` (``save_bscan_comparison``) — shared with time-zero
QC rather than duplicated here. The per-(slice, channel) offset array itself
is not stored separately: it is recovered from
``result.removed_component[:, :, 0]`` (every sample along the trace axis is
the same repeated offset value, by construction — see
``processing/dc_offset.py``), so there is exactly one source of truth for it.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt
import numpy as np

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.result import ProcessingResult


def _offset_array(result: ProcessingResult) -> np.ndarray:
    """(slices, channels) offset, recovered from the constant-per-trace removed_component."""
    return result.removed_component[:, :, 0].astype(np.float64)


def save_offset_histogram(result: ProcessingResult, output_path: str | Path) -> Path:
    """Histogram of the per-trace offset values removed across the whole dataset."""
    offset = _offset_array(result).reshape(-1)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(offset, bins=40, color="steelblue", edgecolor="black", linewidth=0.3)
    ax.axvline(0.0, color="black", linewidth=0.8)
    ax.set_xlabel("Offset removed (amplitude units)")
    ax.set_ylabel("Trace count")
    ax.set_title(f"DC offset distribution across traces (method={result.diagnostics['method']})")
    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def save_trace_means_before_after(before: GPRDataset, after: GPRDataset, output_path: str | Path) -> Path:
    """Overlaid histograms of full-trace mean amplitude, before vs after correction."""
    if before.shape != after.shape:
        raise ValueError(f"before.shape {before.shape} != after.shape {after.shape}")

    means_before = before.amplitudes.astype(np.float64).mean(axis=2).reshape(-1)
    means_after = after.amplitudes.astype(np.float64).mean(axis=2).reshape(-1)
    bins = np.histogram_bin_edges(np.concatenate([means_before, means_after]), bins=40).tolist()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(means_before, bins=bins, alpha=0.6, label="Before", color="indianred")
    ax.hist(means_after, bins=bins, alpha=0.6, label="After", color="seagreen")
    ax.axvline(0.0, color="black", linewidth=0.8)
    ax.set_xlabel("Trace mean amplitude")
    ax.set_ylabel("Trace count")
    ax.set_title("Trace mean amplitude: before vs after DC offset correction")
    ax.legend()
    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def save_channel_offset_statistics(result: ProcessingResult, output_path: str | Path) -> Path:
    """Per-channel boxplot of the removed offset (median, IQR, range) across all slices."""
    offset = _offset_array(result)
    channels_count = offset.shape[1]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.boxplot([offset[:, c] for c in range(channels_count)], showfliers=True)
    ax.set_xticks(range(1, channels_count + 1))
    ax.set_xticklabels([f"{c:02d}" for c in range(channels_count)])
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_xlabel("Channel")
    ax.set_ylabel("Offset removed (amplitude units)")
    ax.set_title("Per-channel DC offset distribution")
    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path
