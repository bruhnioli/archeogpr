"""Dewow QC figures: before/after/removed B-scans, median traces, spectra.

Reuses the existing generic B-scan and median-trace plotting helpers
(``qc/bscan.py``, ``qc/time_zero.py``) by wrapping ``removed_component`` in
a throwaway ``GPRDataset`` with the same axes as the real one -- no new
B-scan-plotting logic needed, and it stays visually consistent with every
other stage's QC in this project.
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt
import numpy as np

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.result import ProcessingResult
from archaeogpr.qc.bscan import save_all_channels_bscan, save_bscan_comparison, save_channel_bscan
from archaeogpr.qc.spectrum import save_spectrum_comparison
from archaeogpr.qc.time_zero import plot_channel_median_traces, plot_channel_median_traces_overlay


def save_median_trace_comparison(
    before: GPRDataset, after: GPRDataset, output_path: str | Path, *, title: str | None = None
) -> Path:
    """Before (dashed) vs after (solid) channel median traces, one shared axes."""
    fig, ax = plt.subplots(figsize=(12, 6))
    plot_channel_median_traces_overlay(before, after, ax=ax, title=title)
    fig.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def save_removed_component_median_trace(
    result: ProcessingResult, output_path: str | Path, *, title: str | None = None
) -> Path:
    """Channel median trace of ``result.removed_component`` itself (the estimated baseline)."""
    removed_dataset = replace(result.dataset, amplitudes=result.removed_component)
    fig, ax = plt.subplots(figsize=(10, 5))
    plot_channel_median_traces(
        removed_dataset, ax=ax, title=title or "Removed component -- channel median traces"
    )
    fig.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def save_trace_mean_histogram(before: GPRDataset, after: GPRDataset, output_path: str | Path) -> Path:
    """Histogram of per-(slice, channel) trace means, before vs after, overlaid."""
    means_before = before.amplitudes.astype(np.float64).mean(axis=2).reshape(-1)
    means_after = after.amplitudes.astype(np.float64).mean(axis=2).reshape(-1)

    fig, ax = plt.subplots(figsize=(10, 5))
    bins = 40
    ax.hist(means_before.tolist(), bins=bins, alpha=0.6, label="before")
    ax.hist(means_after.tolist(), bins=bins, alpha=0.6, label="after")
    ax.set_xlabel("Trace mean")
    ax.set_ylabel("Count (traces)")
    ax.set_title("Trace mean distribution -- before vs after dewow")
    ax.legend()
    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def save_dewow_qc_suite(
    before: GPRDataset,
    result: ProcessingResult,
    output_dir: str | Path,
    *,
    channel: int = 0,
    clip_percentile: float = 99.0,
    cmap: str = "seismic",
) -> dict[str, Path]:
    """Save every required per-candidate dewow QC figure. Returns a dict of the paths written."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    after = result.dataset
    stem = f"channel{channel:02d}"
    paths: dict[str, Path] = {}

    comparison_paths = save_bscan_comparison(
        before, after, channel, output_dir, stem, clip_percentile=clip_percentile, cmap=cmap
    )
    paths["channel_before"] = comparison_paths["before"]  # already f"{stem}_before.png"
    paths["channel_after"] = comparison_paths["after"]  # already f"{stem}_after.png"
    difference_path = output_dir / f"{stem}_before_after_difference.png"
    shutil.copyfile(
        comparison_paths["difference"], difference_path
    )  # alias; f"{stem}_difference.png" kept too
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
    paths["removed_component_median_trace"] = save_removed_component_median_trace(
        result, output_dir / "removed_component_median_trace.png"
    )
    paths["trace_mean_histogram_before_after"] = save_trace_mean_histogram(
        before, after, output_dir / "trace_mean_histogram_before_after.png"
    )
    paths["low_frequency_spectrum_before_after"] = save_spectrum_comparison(
        before,
        after,
        output_dir / "low_frequency_spectrum_before_after.png",
        valid_mask=result.valid_mask,
        freq_max_mhz=200.0,
        title="Low-frequency amplitude spectrum -- before vs after dewow (QC only)",
    )
    return paths
