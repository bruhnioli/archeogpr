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

import contextlib
import json
import os
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt
import numpy as np

from archaeogpr import __version__ as ARCHAEOGPR_VERSION
from archaeogpr.cscan.models import CScanGeometryView, CScanResult
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


def export_cscan_png(
    result: CScanResult,
    geometry_view: CScanGeometryView,
    levels: tuple[float, float],
    colormap: str,
    output_path: str | Path,
    *,
    x_grid: np.ndarray | None = None,
    y_grid: np.ndarray | None = None,
    show_invalid_points: bool = True,
    source_filename: str | None = None,
) -> Path:
    """Render a ``CScanResult`` at the given ``levels``/``colormap`` to a PNG, atomically.

    Sprint 3D-1 (see ADR-017): re-renders from data (never a live screen
    grab), on the same matplotlib ``Agg`` backend as :func:`export_bscan_png`
    -- but written **atomically** (temp file + ``os.replace``), unlike that
    older function, since a C-scan export is explicitly required to never
    leave a half-written file behind. ``x_grid``/``y_grid`` (shape
    ``(trace_count, channel_count)``) are required for
    ``ACTUAL_XY_POINT_MAP`` and ignored for ``DERIVED_PARAMETER_GRID``
    (which renders ``result.values`` directly as an image, transposed
    exactly like ``CScanView._render_derived_grid``). Never modifies
    ``result``.
    """
    vmin, vmax = levels
    fig, ax = plt.subplots(figsize=(9, 7))
    values = result.values

    if geometry_view is CScanGeometryView.ACTUAL_XY_POINT_MAP:
        if x_grid is None or y_grid is None:
            raise ValueError("x_grid/y_grid are required for ACTUAL_XY_POINT_MAP export")
        point_valid = result.valid_mask & np.isfinite(x_grid) & np.isfinite(y_grid)
        scatter = ax.scatter(
            x_grid[point_valid],
            y_grid[point_valid],
            c=values[point_valid],
            cmap=colormap,
            vmin=vmin,
            vmax=vmax,
        )
        if show_invalid_points:
            invalid_mask = (~result.valid_mask) & np.isfinite(x_grid) & np.isfinite(y_grid)
            if invalid_mask.any():
                ax.scatter(x_grid[invalid_mask], y_grid[invalid_mask], marker="x", c="#cc3333")
        ax.set_aspect("equal", adjustable="datalim")
        fig.colorbar(scatter, ax=ax, label="C-scan value")
        title = "Actual X/Y point map — no interpolation"
    else:
        display_values = np.where(result.valid_mask, values, np.nan)
        image = ax.imshow(
            display_values.T,
            aspect="auto",
            cmap=colormap,
            vmin=vmin,
            vmax=vmax,
            origin="lower",
            interpolation="nearest",
        )
        ax.set_xlabel("Along-track (trace index)")
        ax.set_ylabel("Cross-track (channel index)")
        fig.colorbar(image, ax=ax, label="C-scan value")
        title = "Derived s/c parameter grid"

    if source_filename:
        title = f"{source_filename} — {title}"
    ax.set_title(f"{title} ({result.aggregation.value}, center {result.requested_center_time_ns:.3f} ns)")
    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(output_path.parent), prefix=f".{output_path.name}.", suffix=".tmp"
    )
    os.close(fd)
    try:
        fig.savefig(tmp_name, dpi=150, format="png")
        os.replace(tmp_name, output_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp_name)
        raise
    finally:
        plt.close(fig)
    return output_path
