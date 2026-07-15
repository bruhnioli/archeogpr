"""Time-zero correction QC figures: median-trace overlays and pick/shift charts.

B-scan before/after/difference figures for time-zero live in
``archaeogpr.qc.bscan`` (``save_bscan_comparison``) — shared with DC offset
QC rather than duplicated here.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.result import ProcessingResult

if TYPE_CHECKING:
    from matplotlib.axes import Axes


def _channel_median_trace(dataset: GPRDataset, channel: int) -> np.ndarray:
    return np.median(dataset.amplitudes[:, channel, :].astype(np.float64), axis=0)


def plot_channel_median_traces(
    dataset: GPRDataset,
    *,
    picks: Mapping[int, int] | None = None,
    target_sample: int | None = None,
    ax: Axes | None = None,
    title: str | None = None,
) -> Axes:
    """Per-channel median trace (over all slices), with optional pick/target markers."""
    channels_count = dataset.shape[1]
    samples_count = dataset.shape[2]
    if ax is None:
        _, ax = plt.subplots(figsize=(10, 5))

    cmap = plt.get_cmap("viridis")
    x = np.arange(samples_count)
    for channel in range(channels_count):
        color = cmap(channel / max(channels_count - 1, 1))
        trace = _channel_median_trace(dataset, channel)
        ax.plot(x, trace, color=color, linewidth=1.0, label=f"Ch {channel:02d}")
        if picks is not None and channel in picks:
            picked = picks[channel]
            ax.plot([picked], [trace[picked]], marker="o", color=color, markersize=5)

    if target_sample is not None:
        ax.axvline(
            target_sample,
            color="black",
            linestyle="--",
            linewidth=1.2,
            label=f"target_sample={target_sample}",
        )

    ax.set_xlabel("Sample index")
    ax.set_ylabel("Median amplitude (per channel, raw)")
    ax.set_title(title or "Channel median traces")
    ax.legend(loc="upper right", fontsize=7, ncol=3, framealpha=0.85)
    return ax


def plot_channel_median_traces_overlay(
    before: GPRDataset,
    after: GPRDataset,
    *,
    picks: Mapping[int, int] | None = None,
    target_sample: int | None = None,
    ax: Axes | None = None,
    title: str | None = None,
) -> Axes:
    """Before (dashed) vs after (solid) median traces on one shared axes, same color per channel."""
    if before.shape != after.shape:
        raise ValueError(f"before.shape {before.shape} != after.shape {after.shape}")
    channels_count = before.shape[1]
    samples_count = before.shape[2]
    if ax is None:
        _, ax = plt.subplots(figsize=(12, 6))

    cmap = plt.get_cmap("viridis")
    x = np.arange(samples_count)
    for channel in range(channels_count):
        color = cmap(channel / max(channels_count - 1, 1))
        before_trace = _channel_median_trace(before, channel)
        after_trace = _channel_median_trace(after, channel)
        ax.plot(x, before_trace, color=color, linestyle="--", linewidth=1.0, alpha=0.6)
        ax.plot(x, after_trace, color=color, linestyle="-", linewidth=1.3, label=f"Ch {channel:02d}")
        if picks is not None and channel in picks:
            picked = picks[channel]
            ax.plot([picked], [before_trace[picked]], marker="o", color=color, markersize=5)

    if target_sample is not None:
        ax.axvline(
            target_sample, color="black", linestyle=":", linewidth=1.3, label=f"target_sample={target_sample}"
        )

    ax.set_xlabel("Sample index")
    ax.set_ylabel("Median amplitude (per channel, raw)")
    ax.set_title(title or "Channel median traces overlay (dashed = before, solid = after)")
    ax.legend(loc="upper right", fontsize=7, ncol=3, framealpha=0.85)
    return ax


def save_channel_median_traces(
    before: GPRDataset,
    after: GPRDataset,
    result: ProcessingResult,
    output_dir: str | Path,
    stem: str = "channel_median_traces",
) -> dict[str, Path]:
    """Save ``{stem}_before.png``, ``{stem}_after.png``, ``{stem}_overlay.png``."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    picks = {int(c): p for c, p in result.diagnostics["channel_picks"].items()}
    target_sample = result.diagnostics["target_sample"]
    paths: dict[str, Path] = {}

    fig, ax = plt.subplots(figsize=(10, 5))
    plot_channel_median_traces(
        before, picks=picks, target_sample=target_sample, ax=ax, title="Channel median traces — before"
    )
    fig.tight_layout()
    path = output_dir / f"{stem}_before.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths["before"] = path

    fig, ax = plt.subplots(figsize=(10, 5))
    plot_channel_median_traces(
        after, target_sample=target_sample, ax=ax, title="Channel median traces — after"
    )
    fig.tight_layout()
    path = output_dir / f"{stem}_after.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths["after"] = path

    fig, ax = plt.subplots(figsize=(12, 6))
    plot_channel_median_traces_overlay(before, after, picks=picks, target_sample=target_sample, ax=ax)
    fig.tight_layout()
    path = output_dir / f"{stem}_overlay.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths["overlay"] = path

    return paths


def save_picks_and_shifts(result: ProcessingResult, output_path: str | Path) -> Path:
    """Bar charts of picked sample and applied shift, one bar per channel."""
    diagnostics = result.diagnostics
    channels = sorted(int(c) for c in diagnostics["channel_picks"])
    picks = [diagnostics["channel_picks"][str(c)] for c in channels]
    shifts = [diagnostics["channel_shifts"][str(c)] for c in channels]
    target_sample = diagnostics["target_sample"]
    max_shift_samples = diagnostics["max_shift_samples"]
    labels = [f"{c:02d}" for c in channels]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    ax1.bar(labels, picks, color="steelblue")
    ax1.axhline(
        target_sample, color="black", linestyle="--", linewidth=1.2, label=f"target_sample={target_sample}"
    )
    ax1.set_ylabel("Picked sample")
    ax1.set_title(f"Time-zero picks and shifts (method={diagnostics['method']})")
    ax1.legend(fontsize=8)

    colors = ["indianred" if abs(s) >= max_shift_samples else "seagreen" for s in shifts]
    ax2.bar(labels, shifts, color=colors)
    ax2.axhline(0, color="black", linewidth=0.8)
    ax2.set_xlabel("Channel")
    ax2.set_ylabel("Applied shift (samples)")

    fig.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def save_padding_mask_plot(result: ProcessingResult, channel: int, output_path: str | Path) -> Path:
    """Visualize which samples are valid (real shifted data) vs. padding, for one channel.

    Raises ``ValueError`` if ``result.valid_mask`` is ``None`` (the
    operation that produced ``result`` did not report a validity mask).
    """
    if result.valid_mask is None:
        raise ValueError("result.valid_mask is None; this result has no validity mask to plot")
    channels_count, samples_count = result.valid_mask.shape
    if not (0 <= channel < channels_count):
        raise ValueError(f"channel {channel} out of range [0, {channels_count})")

    mask = result.valid_mask[channel]
    n_valid = int(mask.sum())
    n_padding = samples_count - n_valid
    strip = np.where(mask, 0, 1)[np.newaxis, :]  # 0=valid, 1=padding

    fig, ax = plt.subplots(figsize=(10, 2.2))
    ax.imshow(
        strip,
        aspect="auto",
        cmap=ListedColormap(["seagreen", "indianred"]),
        vmin=0,
        vmax=1,
        extent=(0, samples_count, 0, 1),
        origin="upper",
    )
    target_sample = result.diagnostics.get("target_sample")
    if target_sample is not None:
        ax.axvline(target_sample, color="black", linestyle="--", linewidth=1.3)
    ax.set_yticks([])
    ax.set_xlabel("Sample index")
    ax.set_title(f"Channel {channel:02d} valid/padding mask (green=valid, red=padding)")
    ax.text(
        0.01,
        0.5,
        f"valid={n_valid}  padding={n_padding}",
        transform=ax.transAxes,
        fontsize=8,
        va="center",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
    )
    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path
