"""GUI-side PNG export: renders exactly what the B-scan view is currently
showing (channel, colormap, display levels) via matplotlib, plus an
optional JSON sidecar recording the display policy used.

This is a *display* export, not a processing export -- it never reads or
writes ``dataset.processing_history``, never mutates ``dataset.amplitudes``,
and is entirely separate from ``archaeogpr.export`` (the existing headless
CLI export package for processed data). Uses matplotlib only to rasterize a
static image (``Agg`` backend, no window, no interaction with the running
PySide6 event loop) -- the interactive GUI itself never uses matplotlib.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt

from archaeogpr import __version__ as ARCHAEOGPR_VERSION
from archaeogpr.gui.models.display_settings import DisplaySettings
from archaeogpr.model.dataset import GPRDataset


def export_bscan_png(
    dataset: GPRDataset,
    channel: int,
    levels: tuple[float, float],
    colormap: str,
    output_path: str | Path,
    *,
    source_filename: str | None = None,
    selected_trace: int | None = None,
) -> Path:
    """Render channel ``channel``'s B-scan at the given ``levels``/``colormap`` to a PNG.

    ``levels``/``colormap`` are exactly what the GUI is currently
    displaying (see ``BScanView.compute_full_range_levels()``/
    ``DisplaySettings.colormap``) -- this function does not recompute or
    otherwise alter them. Never modifies ``dataset``.
    """
    channel_data = dataset.amplitudes[:, channel, :]  # (trace, sample), read-only view
    trace_count = channel_data.shape[0]
    t0, t1 = float(dataset.time_ns[0]), float(dataset.time_ns[-1])
    vmin, vmax = levels

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.imshow(
        channel_data.T,
        aspect="auto",
        cmap=colormap,
        vmin=vmin,
        vmax=vmax,
        extent=(0.0, float(trace_count), t1, t0),
        origin="upper",
        interpolation="nearest",
    )
    if selected_trace is not None:
        ax.axvline(selected_trace + 0.5, color="#ffe100", linewidth=1.0)
    ax.set_xlabel("Trace index")
    ax.set_ylabel("Time (ns)")
    title = f"Channel {channel:02d} B-scan"
    if source_filename:
        title = f"{source_filename} — {title}"
    ax.set_title(f"{title} (levels [{vmin:.4g}, {vmax:.4g}], display-only, source amplitudes unchanged)")
    fig.colorbar(ax.images[0], ax=ax, label="Amplitude (raw, ungained)")
    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def _level_mode(settings: DisplaySettings) -> str:
    if settings.manual_levels_enabled and settings.manual_levels_are_valid():
        return "manual"
    return "symmetric" if settings.symmetric_levels else "asymmetric"


def write_display_sidecar(
    png_path: str | Path,
    dataset: GPRDataset,
    channel: int,
    settings: DisplaySettings,
    levels: tuple[float, float],
    *,
    source_filename: str | None = None,
) -> Path:
    """Write ``<png_stem>.display.json`` next to ``png_path`` (see ``ADR-013``).

    Records the display policy that produced the PNG -- never the
    amplitude data itself -- so the export is reproducible and unambiguous
    about being a display, not a processing, artifact.
    """
    png_path = Path(png_path)
    sidecar_path = png_path.with_suffix("").with_suffix(".display.json")
    payload: dict[str, Any] = {
        "source_filename": source_filename,
        "channel": channel,
        "display_settings": asdict(settings),
        "level_mode": _level_mode(settings),
        "display_min": levels[0],
        "display_max": levels[1],
        "export_timestamp": datetime.now(UTC).isoformat(),
        "software_version": ARCHAEOGPR_VERSION,
        "note": "Display-only export; source amplitudes unchanged.",
    }
    sidecar_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return sidecar_path
