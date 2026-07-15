"""Survey geometry QC plot: plan-view (x, y) lines for every channel.

Coordinates are plotted exactly as stored in the file. This module never
reprojects, transforms, or otherwise assumes the header's spatial reference
is correct — see ``dataset.metadata["spatial_reference"]``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt
import numpy as np

from archaeogpr.model.dataset import GPRDataset

if TYPE_CHECKING:
    from matplotlib.axes import Axes

CRS_WARNING_TEXT = "Coordinate values shown as stored; CRS not validated."


def plot_survey_geometry(dataset: GPRDataset, ax: Axes | None = None) -> Axes:
    """Plot every channel's (x, y) line with equal-aspect axes and start/end markers.

    Raises ``ValueError`` if ``dataset`` has no geolocation data.
    """
    if not dataset.has_geolocation:
        raise ValueError("Dataset has no geolocation data; cannot plot survey geometry.")
    assert dataset.x is not None and dataset.y is not None  # guaranteed by has_geolocation, narrows for mypy

    if ax is None:
        _, ax = plt.subplots(figsize=(8, 8))

    channels_count = dataset.shape[1]
    cmap = plt.get_cmap("viridis")
    for channel in range(channels_count):
        color = cmap(channel / max(channels_count - 1, 1))
        ax.plot(
            dataset.x[:, channel],
            dataset.y[:, channel],
            color=color,
            linewidth=1.0,
            label=f"Ch {channel:02d}",
        )

    start_x, start_y = float(np.mean(dataset.x[0, :])), float(np.mean(dataset.y[0, :]))
    end_x, end_y = float(np.mean(dataset.x[-1, :])), float(np.mean(dataset.y[-1, :]))
    ax.scatter([start_x], [start_y], marker="o", color="green", s=90, zorder=5, label="Start")
    ax.scatter([end_x], [end_y], marker="s", color="red", s=90, zorder=5, label="End")
    ax.annotate(
        "",
        xy=(end_x, end_y),
        xytext=(start_x, start_y),
        arrowprops={"arrowstyle": "->", "color": "black", "lw": 1.2, "alpha": 0.6},
    )

    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("X (as stored)")
    ax.set_ylabel("Y (as stored)")
    ax.set_title("Survey geometry plan (QC only)")

    srs = dataset.metadata.get("spatial_reference")
    srs_text = f"SRS as stored: {srs}" if srs else "SRS: not present in file"
    ax.text(
        0.01,
        0.01,
        f"{srs_text}\n{CRS_WARNING_TEXT}",
        transform=ax.transAxes,
        fontsize=8,
        va="bottom",
        ha="left",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
    )
    ax.legend(loc="upper right", fontsize=7, ncol=3, framealpha=0.85)
    return ax


def save_survey_geometry(dataset: GPRDataset, output_path: str | Path) -> Path:
    """Render the survey geometry plan and save it as a PNG. Returns the output path."""
    fig, ax = plt.subplots(figsize=(8, 8))
    plot_survey_geometry(dataset, ax=ax)
    fig.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path
