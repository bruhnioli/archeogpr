"""B-scan QC figures.

Every plotting function here only *reads* ``dataset.amplitudes``; percentile
clipping only affects the color-mapping range (``imshow(vmin=..., vmax=...)``),
never the underlying array, so the raw radar volume is never copied, clipped,
or otherwise modified.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt
import numpy as np

from archaeogpr.model.dataset import GPRDataset

if TYPE_CHECKING:
    from matplotlib.axes import Axes


def _x_axis_values(dataset: GPRDataset, channel: int, x_axis: str) -> np.ndarray:
    slices_count = dataset.shape[0]
    if x_axis == "slice":
        return np.arange(slices_count, dtype=np.float64)
    if x_axis == "distance_m":
        if dataset.x is None or dataset.y is None:
            raise ValueError("x_axis='distance_m' requires geolocation data; this dataset has none.")
        x, y = dataset.x[:, channel], dataset.y[:, channel]
        distance = np.zeros(slices_count, dtype=np.float64)
        if slices_count > 1:
            distance[1:] = np.cumsum(np.hypot(np.diff(x), np.diff(y)))
        return distance
    raise ValueError(f"x_axis must be 'slice' or 'distance_m', got {x_axis!r}")


def _y_axis_values(dataset: GPRDataset, y_axis: str) -> np.ndarray:
    if y_axis == "time_ns":
        return dataset.time_ns
    if y_axis == "sample":
        return np.arange(dataset.shape[2], dtype=np.float64)
    raise ValueError(f"y_axis must be 'sample' or 'time_ns', got {y_axis!r}")


def compute_shared_clip_limit(*channel_data_arrays: np.ndarray, clip_percentile: float = 99.0) -> float:
    """Symmetric clip limit shared across one or more (slices, samples) arrays.

    Used to give a before/after pair of B-scans (Sprint 2 QC) the same color
    scale, rather than each plot independently clipping to its own range.
    """
    if not (0 < clip_percentile <= 100):
        raise ValueError(f"clip_percentile must be in (0, 100], got {clip_percentile}")
    limit = 0.0
    for arr in channel_data_arrays:
        limit = max(limit, float(np.percentile(np.abs(arr), clip_percentile)))
    return limit if limit > 0 else 1.0


def plot_bscan(
    dataset: GPRDataset,
    channel: int = 0,
    *,
    clip_percentile: float = 99.0,
    vlimit: float | None = None,
    cmap: str = "seismic",
    x_axis: str = "slice",
    y_axis: str = "sample",
    ax: Axes | None = None,
    title: str | None = None,
) -> Axes:
    """Plot one channel's B-scan onto ``ax`` (a new axes is created if omitted).

    ``clip_percentile`` sets a symmetric, zero-centered color range at
    ``+/- percentile(|amplitude|, clip_percentile)`` — it never clips or
    otherwise modifies ``dataset.amplitudes`` itself. Pass ``vlimit``
    (e.g. from :func:`compute_shared_clip_limit`) to use an externally
    supplied limit instead — for comparing a before/after pair on one scale.
    """
    channels_count = dataset.shape[1]
    if not (0 <= channel < channels_count):
        raise ValueError(f"channel {channel} out of range [0, {channels_count})")

    channel_data = dataset.amplitudes[:, channel, :]  # (slices, samples) read-only view
    if vlimit is not None:
        limit = vlimit
    else:
        if not (0 < clip_percentile <= 100):
            raise ValueError(f"clip_percentile must be in (0, 100], got {clip_percentile}")
        limit = float(np.percentile(np.abs(channel_data), clip_percentile))
        if limit <= 0:
            limit = 1.0  # degenerate all-zero channel: avoid a zero-width color range

    x_values = _x_axis_values(dataset, channel, x_axis)
    y_values = _y_axis_values(dataset, y_axis)

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 5))

    extent = (float(x_values[0]), float(x_values[-1]), float(y_values[-1]), float(y_values[0]))
    ax.imshow(
        channel_data.T,
        aspect="auto",
        cmap=cmap,
        vmin=-limit,
        vmax=limit,
        extent=extent,
        origin="upper",
        interpolation="nearest",
    )
    ax.set_xlabel("Slice index" if x_axis == "slice" else "Along-track distance (m)")
    ax.set_ylabel("Sample index" if y_axis == "sample" else "Time (ns)")
    default_title = (
        f"Channel {channel:02d} B-scan (±{limit:.4g} clip)"
        if vlimit is not None
        else f"Channel {channel:02d} B-scan (±{clip_percentile:g}th pct clip)"
    )
    ax.set_title(title or default_title)
    return ax


def save_channel_bscan(
    dataset: GPRDataset,
    channel: int,
    output_path: str | Path,
    *,
    clip_percentile: float = 99.0,
    cmap: str = "seismic",
    x_axis: str = "slice",
    y_axis: str = "sample",
) -> Path:
    """Render one channel's B-scan and save it as a PNG. Returns the output path."""
    fig, ax = plt.subplots(figsize=(12, 5))
    plot_bscan(
        dataset,
        channel,
        clip_percentile=clip_percentile,
        cmap=cmap,
        x_axis=x_axis,
        y_axis=y_axis,
        ax=ax,
    )
    fig.colorbar(ax.images[0], ax=ax, label="Amplitude (raw, ungained)")
    fig.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def save_all_channels_bscan(
    dataset: GPRDataset,
    output_path: str | Path,
    *,
    clip_percentile: float = 99.0,
    cmap: str = "seismic",
    x_axis: str = "slice",
    y_axis: str = "sample",
    ncols: int = 4,
) -> Path:
    """Render every channel's B-scan as small subplot panels in one QC figure."""
    channels_count = dataset.shape[1]
    ncols = max(1, min(ncols, channels_count))
    nrows = math.ceil(channels_count / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3 * nrows), squeeze=False)

    for i in range(nrows * ncols):
        ax = axes[i // ncols][i % ncols]
        if i < channels_count:
            plot_bscan(
                dataset,
                i,
                clip_percentile=clip_percentile,
                cmap=cmap,
                x_axis=x_axis,
                y_axis=y_axis,
                ax=ax,
                title=f"Ch {i:02d}",
            )
        else:
            ax.axis("off")

    fig.suptitle("All-channel B-scan comparison (QC only, not for quantitative use)")
    fig.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=130)
    plt.close(fig)
    return output_path


def plot_bscan_difference(
    before: GPRDataset,
    after: GPRDataset,
    channel: int = 0,
    *,
    clip_percentile: float = 99.0,
    cmap: str = "seismic",
    x_axis: str = "slice",
    y_axis: str = "sample",
    ax: Axes | None = None,
    title: str | None = None,
) -> Axes:
    """Plot ``before - after`` for one channel, with its own (separate) symmetric clip.

    ``before``/``after`` must have the same shape. This never modifies
    either dataset; the difference is computed into a fresh float64 array.
    """
    if before.shape != after.shape:
        raise ValueError(f"before.shape {before.shape} != after.shape {after.shape}")
    channels_count = before.shape[1]
    if not (0 <= channel < channels_count):
        raise ValueError(f"channel {channel} out of range [0, {channels_count})")

    diff = before.amplitudes[:, channel, :].astype(np.float64) - after.amplitudes[:, channel, :].astype(
        np.float64
    )
    limit = compute_shared_clip_limit(diff, clip_percentile=clip_percentile)

    x_values = _x_axis_values(before, channel, x_axis)
    y_values = _y_axis_values(before, y_axis)

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 5))

    extent = (float(x_values[0]), float(x_values[-1]), float(y_values[-1]), float(y_values[0]))
    ax.imshow(
        diff.T,
        aspect="auto",
        cmap=cmap,
        vmin=-limit,
        vmax=limit,
        extent=extent,
        origin="upper",
        interpolation="nearest",
    )
    ax.set_xlabel("Slice index" if x_axis == "slice" else "Along-track distance (m)")
    ax.set_ylabel("Sample index" if y_axis == "sample" else "Time (ns)")
    ax.set_title(title or f"Channel {channel:02d} difference (before − after, ±{limit:.4g} clip)")
    return ax


def save_bscan_comparison(
    before: GPRDataset,
    after: GPRDataset,
    channel: int,
    output_dir: str | Path,
    stem: str,
    *,
    clip_percentile: float = 99.0,
    cmap: str = "seismic",
    x_axis: str = "slice",
    y_axis: str = "sample",
) -> dict[str, Path]:
    """Save ``{stem}_before.png``, ``{stem}_after.png`` (shared clip), ``{stem}_difference.png``.

    Returns a dict with keys ``"before"``, ``"after"``, ``"difference"``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    shared_limit = compute_shared_clip_limit(
        before.amplitudes[:, channel, :],
        after.amplitudes[:, channel, :],
        clip_percentile=clip_percentile,
    )

    paths: dict[str, Path] = {}
    for label, dataset in (("before", before), ("after", after)):
        fig, ax = plt.subplots(figsize=(12, 5))
        plot_bscan(
            dataset,
            channel,
            vlimit=shared_limit,
            cmap=cmap,
            x_axis=x_axis,
            y_axis=y_axis,
            ax=ax,
            title=f"Channel {channel:02d} — {label} (±{shared_limit:.4g} clip)",
        )
        fig.colorbar(ax.images[0], ax=ax, label="Amplitude (raw, ungained)")
        fig.tight_layout()
        path = output_dir / f"{stem}_{label}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths[label] = path

    fig, ax = plt.subplots(figsize=(12, 5))
    plot_bscan_difference(
        before,
        after,
        channel,
        clip_percentile=clip_percentile,
        cmap=cmap,
        x_axis=x_axis,
        y_axis=y_axis,
        ax=ax,
    )
    fig.colorbar(ax.images[0], ax=ax, label="Amplitude difference")
    fig.tight_layout()
    diff_path = output_dir / f"{stem}_difference.png"
    fig.savefig(diff_path, dpi=150)
    plt.close(fig)
    paths["difference"] = diff_path

    return paths


def save_stage_differences(
    stage_datasets: list[tuple[str, GPRDataset]],
    channel: int,
    output_path: str | Path,
    *,
    clip_percentile: float = 99.0,
    cmap: str = "seismic",
    x_axis: str = "slice",
    y_axis: str = "sample",
) -> Path:
    """One panel per consecutive pair in ``stage_datasets``, each showing that stage's difference.

    E.g. ``[("raw", raw), ("time-zero", tz_ds), ("dc-offset", final_ds)]`` produces
    two panels: raw→time-zero and time-zero→dc-offset.
    """
    if len(stage_datasets) < 2:
        raise ValueError("stage_datasets needs at least 2 (name, dataset) entries")

    n_panels = len(stage_datasets) - 1
    fig, axes = plt.subplots(1, n_panels, figsize=(8 * n_panels, 5), squeeze=False)
    for i in range(n_panels):
        name_before, dataset_before = stage_datasets[i]
        name_after, dataset_after = stage_datasets[i + 1]
        plot_bscan_difference(
            dataset_before,
            dataset_after,
            channel,
            clip_percentile=clip_percentile,
            cmap=cmap,
            x_axis=x_axis,
            y_axis=y_axis,
            ax=axes[0][i],
            title=f"{name_before} → {name_after}",
        )

    fig.suptitle(f"Channel {channel:02d} stage differences")
    fig.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path
