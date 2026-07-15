"""Sprint 3.1 decision-focused QC plotting.

Windowed D2 dewow validation grids, windowed B1/B2 band-pass comparison
grids, per-window spectrum comparisons (absolute / common-dB-reference /
self-normalized), and the single composite decision panel. Every function
here only *reads* already-computed ``ProcessingResult``/``GPRDataset``
data -- nothing here runs a new filter or spectrum algorithm; it all reuses
``correct_dewow``/``correct_bandpass`` (called by the caller) and
``compute_amplitude_spectrum``/``to_db`` (called here, exactly as
documented for QC use elsewhere in Sprint 3).

Padding is never silently included in a color scale or shown as if it were
real data: every B-scan panel masks invalid (padding) samples with
``numpy.ma`` and a colormap ``set_bad`` color, so padding renders as a
distinct flat gray rather than participating in the ``vmin``/``vmax``
computed from real amplitudes.
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
from archaeogpr.qc.bscan import compute_shared_clip_limit
from archaeogpr.qc.spectrum import compute_amplitude_spectrum, to_db

#: (label, start_ns, end_ns) -- ``end_ns is None`` means "full trace, no time filter".
BSCAN_WINDOWS: tuple[tuple[str, float | None, float | None], ...] = (
    ("W_minus2_20", -2.0, 20.0),
    ("W_20_60", 20.0, 60.0),
    ("W_60_100", 60.0, 100.0),
    ("W_20_100", 20.0, 100.0),
    ("full", None, None),
)

#: Sprint 3.1's own W1-W4 naming (see the task brief section 5).
SPECTRUM_WINDOWS: tuple[tuple[str, float, float], ...] = (
    ("W1", -2.0, 20.0),
    ("W2", 20.0, 60.0),
    ("W3", 60.0, 100.0),
    ("W4", 20.0, 100.0),
)


def _masked_cmap(name: str = "seismic"):
    cmap = plt.get_cmap(name).copy()
    cmap.set_bad(color="0.75")  # explicit flat gray for padding -- never left to show real color-scale data
    return cmap


def windowed_array(
    amplitudes_3d: np.ndarray,
    time_ns: np.ndarray,
    channel: int,
    start_ns: float | None,
    end_ns: float | None,
    valid_mask: np.ndarray | None,
) -> tuple[np.ma.MaskedArray, np.ndarray]:
    """One channel's ``(slices, window_samples)`` slice, time axis, and padding mask applied.

    ``start_ns``/``end_ns`` both ``None`` selects the full trace. Returns a
    ``numpy.ma.MaskedArray`` with invalid (padding) positions masked, and
    the corresponding ``time_ns`` sub-array.
    """
    samples_count = amplitudes_3d.shape[2]
    if start_ns is None:
        sample_mask = np.ones(samples_count, dtype=bool)
    else:
        assert end_ns is not None
        sample_mask = dataset_time_window_mask(time_ns, start_ns, end_ns)
    time_values = time_ns[sample_mask]
    data = amplitudes_3d[:, channel, sample_mask].astype(np.float64)
    if valid_mask is not None:
        valid_1d = valid_mask[channel, sample_mask]
        invalid_2d = np.broadcast_to(~valid_1d, data.shape)
        masked = np.ma.masked_where(invalid_2d, data)
    else:
        masked = np.ma.array(data)
    return masked, time_values


def _imshow_panel(
    ax, masked_data: np.ma.MaskedArray, time_values: np.ndarray, vlimit: float, cmap, title: str
):
    extent = (0.0, float(masked_data.shape[0]), float(time_values[-1]), float(time_values[0]))
    im = ax.imshow(
        masked_data.T,
        aspect="auto",
        cmap=cmap,
        vmin=-vlimit,
        vmax=vlimit,
        extent=extent,
        origin="upper",
        interpolation="nearest",
    )
    ax.set_xlabel("Slice index")
    ax.set_ylabel("time_ns")
    ax.set_title(title, fontsize=9)
    return im


def _shared_limit(*masked_arrays: np.ma.MaskedArray, clip_percentile: float = 99.0) -> float:
    filled = [np.asarray(m.filled(0.0)) for m in masked_arrays]
    return compute_shared_clip_limit(*filled, clip_percentile=clip_percentile)


# ======================================================================
# Section 3: D2 removed-component windowed review
# ======================================================================


def save_d2_removed_component_windowed_review(
    raw_dataset: GPRDataset,
    d2_result: Any,
    valid_mask: np.ndarray | None,
    output_dir: str | Path,
    *,
    channels: tuple[int, ...] = (0, 5, 10),
    clip_percentile: float = 99.0,
) -> dict[str, Path]:
    """One grid PNG per channel: rows = time windows, columns = input/D2 output/removed/difference.

    Each row (window) gets its own shared, symmetric amplitude scale across
    its 4 panels; different windows are not forced onto one shared scale
    (the direct-wave window is orders of magnitude larger than the late-time
    windows). Returns ``{"channel00": path, ...}``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cmap = _masked_cmap()
    paths: dict[str, Path] = {}

    for channel in channels:
        nrows = len(BSCAN_WINDOWS)
        fig, axes = plt.subplots(nrows, 4, figsize=(18, 3.6 * nrows))
        for row, (label, start_ns, end_ns) in enumerate(BSCAN_WINDOWS):
            input_masked, t = windowed_array(
                raw_dataset.amplitudes, raw_dataset.time_ns, channel, start_ns, end_ns, valid_mask
            )
            output_masked, _ = windowed_array(
                d2_result.dataset.amplitudes, raw_dataset.time_ns, channel, start_ns, end_ns, valid_mask
            )
            removed_masked, _ = windowed_array(
                d2_result.removed_component, raw_dataset.time_ns, channel, start_ns, end_ns, valid_mask
            )
            diff_masked = np.ma.masked_array(
                input_masked.filled(0.0) - output_masked.filled(0.0),
                mask=np.ma.getmaskarray(input_masked) | np.ma.getmaskarray(output_masked),
            )

            limit = _shared_limit(
                input_masked, output_masked, removed_masked, diff_masked, clip_percentile=clip_percentile
            )
            _imshow_panel(axes[row][0], input_masked, t, limit, cmap, f"{label}: input")
            _imshow_panel(axes[row][1], output_masked, t, limit, cmap, f"{label}: D2 output")
            _imshow_panel(axes[row][2], removed_masked, t, limit, cmap, f"{label}: removed component")
            _imshow_panel(axes[row][3], diff_masked, t, limit, cmap, f"{label}: input - output")

        fig.suptitle(
            f"Channel {channel:02d} -- D2 dewow windowed validation (QC only; "
            "gray = masked padding; each row has its own shared scale)"
        )
        fig.tight_layout()
        path = output_dir / f"channel{channel:02d}_D2_windowed_review.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        paths[f"channel{channel:02d}"] = path

    return paths


# ======================================================================
# Section 4: B1/B2 band-pass windowed comparison
# ======================================================================


def save_bandpass_b1_b2_windowed_comparison(
    d2_result: Any,
    b1_result: Any,
    b2_result: Any,
    valid_mask: np.ndarray | None,
    output_dir: str | Path,
    *,
    channels: tuple[int, ...] = (0, 5, 10),
    clip_percentile: float = 99.0,
) -> dict[str, Path]:
    """One grid PNG per channel: rows = windows, columns = D2/D2+B1/D2+B2/B1 removed/B2 removed/B1-B2 diff.

    Columns 1-3 (D2, D2+B1, D2+B2) share one amplitude scale per row;
    columns 4-5 (B1/B2 removed component) share a separate scale per row;
    column 6 (B1-B2 difference) uses its own scale per row -- matching the
    task brief's explicit "ortak ... scale" grouping.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cmap = _masked_cmap()
    paths: dict[str, Path] = {}
    time_ns = d2_result.dataset.time_ns

    for channel in channels:
        nrows = len(BSCAN_WINDOWS)
        fig, axes = plt.subplots(nrows, 6, figsize=(26, 3.6 * nrows))
        for row, (label, start_ns, end_ns) in enumerate(BSCAN_WINDOWS):
            d2_masked, t = windowed_array(
                d2_result.dataset.amplitudes, time_ns, channel, start_ns, end_ns, valid_mask
            )
            b1_masked, _ = windowed_array(
                b1_result.dataset.amplitudes, time_ns, channel, start_ns, end_ns, valid_mask
            )
            b2_masked, _ = windowed_array(
                b2_result.dataset.amplitudes, time_ns, channel, start_ns, end_ns, valid_mask
            )
            b1_removed_masked, _ = windowed_array(
                b1_result.removed_component, time_ns, channel, start_ns, end_ns, valid_mask
            )
            b2_removed_masked, _ = windowed_array(
                b2_result.removed_component, time_ns, channel, start_ns, end_ns, valid_mask
            )
            diff_masked = np.ma.masked_array(
                b1_masked.filled(0.0) - b2_masked.filled(0.0),
                mask=np.ma.getmaskarray(b1_masked) | np.ma.getmaskarray(b2_masked),
            )

            limit_inputs = _shared_limit(d2_masked, b1_masked, b2_masked, clip_percentile=clip_percentile)
            limit_removed = _shared_limit(
                b1_removed_masked, b2_removed_masked, clip_percentile=clip_percentile
            )
            limit_diff = _shared_limit(diff_masked, clip_percentile=clip_percentile)

            _imshow_panel(axes[row][0], d2_masked, t, limit_inputs, cmap, f"{label}: D2 input")
            _imshow_panel(axes[row][1], b1_masked, t, limit_inputs, cmap, f"{label}: D2+B1")
            _imshow_panel(axes[row][2], b2_masked, t, limit_inputs, cmap, f"{label}: D2+B2")
            _imshow_panel(axes[row][3], b1_removed_masked, t, limit_removed, cmap, f"{label}: B1 removed")
            _imshow_panel(axes[row][4], b2_removed_masked, t, limit_removed, cmap, f"{label}: B2 removed")
            _imshow_panel(axes[row][5], diff_masked, t, limit_diff, cmap, f"{label}: B1 - B2")

        fig.suptitle(
            f"Channel {channel:02d} -- B1 vs B2 windowed comparison (QC only; gray = masked padding; "
            "cols 1-3 share one scale, cols 4-5 share a separate scale, col 6 its own)"
        )
        fig.tight_layout()
        path = output_dir / f"channel{channel:02d}_B1_B2_windowed_comparison.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        paths[f"channel{channel:02d}"] = path

    return paths


# ======================================================================
# Section 5: per-window spectrum comparison (absolute / common dB / self-normalized)
# ======================================================================


def _spectrum_for(dataset: GPRDataset, valid_mask, start_ns: float, end_ns: float) -> dict[str, Any]:
    return compute_amplitude_spectrum(
        dataset, time_start_ns=start_ns, time_end_ns=end_ns, valid_mask=valid_mask
    )


def compute_window_spectra(
    d2_result: Any, b1_result: Any, b2_result: Any, valid_mask, start_ns: float, end_ns: float
) -> dict[str, dict[str, Any]]:
    """Spectra for D2/D2+B1/D2+B2/B1-removed/B2-removed, all within one ``[start_ns, end_ns)`` window."""
    b1_removed_ds = replace(b1_result.dataset, amplitudes=b1_result.removed_component)
    b2_removed_ds = replace(b2_result.dataset, amplitudes=b2_result.removed_component)
    return {
        "D2": _spectrum_for(d2_result.dataset, valid_mask, start_ns, end_ns),
        "D2+B1": _spectrum_for(b1_result.dataset, valid_mask, start_ns, end_ns),
        "D2+B2": _spectrum_for(b2_result.dataset, valid_mask, start_ns, end_ns),
        "B1 removed": _spectrum_for(b1_removed_ds, valid_mask, start_ns, end_ns),
        "B2 removed": _spectrum_for(b2_removed_ds, valid_mask, start_ns, end_ns),
    }


def save_spectrum_window_comparison(
    spectra: dict[str, dict[str, Any]], window_label: str, output_dir: str | Path
) -> Path:
    """One PNG, 3 subplots: absolute amplitude, common-dB-vs-D2, and each candidate's own-peak-normalized.

    The dB subplot's reference is fixed to D2's own global peak in this
    window -- every curve in that subplot (including D2 itself) is
    expressed relative to that ONE shared reference, so the subplot is
    directly comparable across candidates. The normalized subplot is
    explicitly titled as each candidate's own peak = 1.0 -- it must never
    be read as a claim that absolute energy is conserved across candidates.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    d2_reference = float(spectra["D2"]["amplitude_spectrum"].max())

    fig, axes = plt.subplots(1, 3, figsize=(21, 5.5))
    cmap = plt.get_cmap("tab10")
    for i, (candidate_label, spectrum) in enumerate(spectra.items()):
        color = cmap(i)
        freqs = spectrum["frequencies_mhz"]
        axes[0].plot(freqs, spectrum["amplitude_spectrum"], color=color, label=candidate_label)
        axes[1].plot(
            freqs,
            to_db(spectrum["amplitude_spectrum"], reference=d2_reference),
            color=color,
            label=candidate_label,
        )
        axes[2].plot(freqs, spectrum["amplitude_spectrum_normalized"], color=color, label=candidate_label)

    axes[0].set_title(f"{window_label}: absolute amplitude spectrum")
    axes[0].set_xlabel("Frequency (MHz)")
    axes[0].set_ylabel("Absolute amplitude (arbitrary units, not gained)")
    axes[0].legend(fontsize=8)

    axes[1].set_title(f"{window_label}: dB, common reference = D2's own peak in this window")
    axes[1].set_xlabel("Frequency (MHz)")
    axes[1].set_ylabel(f"dB re: D2 peak ({d2_reference:.4g})")
    axes[1].legend(fontsize=8)

    axes[2].set_title(f"{window_label}: self-normalized (each candidate's OWN peak = 1.0)")
    axes[2].set_xlabel("Frequency (MHz)")
    axes[2].set_ylabel("Normalized amplitude (no absolute-energy comparison implied)")
    axes[2].legend(fontsize=8)

    fig.suptitle(
        "QC only -- self-normalized view (right) must not be read as absolute energy "
        "conservation across candidates"
    )
    fig.tight_layout()
    path = output_dir / f"{window_label}_spectrum_comparison.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


# ======================================================================
# Decision panel
# ======================================================================


def save_decision_panel(
    d2_result: Any,
    b1_result: Any,
    b2_result: Any,
    valid_mask,
    w4_spectra: dict[str, dict[str, Any]],
    band_energy_summary: dict[str, Any],
    spatial_coherence_summary: dict[str, Any],
    output_path: str | Path,
    *,
    channels: tuple[int, ...] = (0, 5, 10),
    clip_percentile: float = 99.0,
) -> Path:
    """Single high-resolution decision panel: 20-100 ns only (direct wave excluded by construction).

    Deliberately restricted to the 20-100 ns window so the direct wave
    (which lives before 20 ns) cannot dominate this panel's amplitude scale.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmap = _masked_cmap()
    time_ns = d2_result.dataset.time_ns
    start_ns, end_ns = 20.0, 100.0

    fig = plt.figure(figsize=(22, 24), constrained_layout=True)
    grid = fig.add_gridspec(len(channels) + 3, 3, height_ratios=[3] * len(channels) + [3, 1.4, 1.4])

    for row, channel in enumerate(channels):
        d2_masked, t = windowed_array(
            d2_result.dataset.amplitudes, time_ns, channel, start_ns, end_ns, valid_mask
        )
        b1_masked, _ = windowed_array(
            b1_result.dataset.amplitudes, time_ns, channel, start_ns, end_ns, valid_mask
        )
        b2_masked, _ = windowed_array(
            b2_result.dataset.amplitudes, time_ns, channel, start_ns, end_ns, valid_mask
        )
        limit = _shared_limit(d2_masked, b1_masked, b2_masked, clip_percentile=clip_percentile)
        ax0 = fig.add_subplot(grid[row, 0])
        ax1 = fig.add_subplot(grid[row, 1])
        ax2 = fig.add_subplot(grid[row, 2])
        _imshow_panel(ax0, d2_masked, t, limit, cmap, f"Ch{channel:02d} D2 (20-100ns)")
        _imshow_panel(ax1, b1_masked, t, limit, cmap, f"Ch{channel:02d} D2+B1 (20-100ns)")
        _imshow_panel(ax2, b2_masked, t, limit, cmap, f"Ch{channel:02d} D2+B2 (20-100ns)")

    removed_row = len(channels)
    channel0 = channels[0]
    b1_removed_masked, t = windowed_array(
        b1_result.removed_component, time_ns, channel0, start_ns, end_ns, valid_mask
    )
    b2_removed_masked, _ = windowed_array(
        b2_result.removed_component, time_ns, channel0, start_ns, end_ns, valid_mask
    )
    removed_limit = _shared_limit(b1_removed_masked, b2_removed_masked, clip_percentile=clip_percentile)
    ax_b1r = fig.add_subplot(grid[removed_row, 0])
    ax_b2r = fig.add_subplot(grid[removed_row, 1])
    _imshow_panel(
        ax_b1r, b1_removed_masked, t, removed_limit, cmap, f"Ch{channel0:02d} B1 removed (20-100ns)"
    )
    _imshow_panel(
        ax_b2r, b2_removed_masked, t, removed_limit, cmap, f"Ch{channel0:02d} B2 removed (20-100ns)"
    )

    ax_abs = fig.add_subplot(grid[removed_row, 2])
    for label, spectrum in w4_spectra.items():
        ax_abs.plot(spectrum["frequencies_mhz"], spectrum["amplitude_spectrum"], label=label)
    ax_abs.set_title("W4 (20-100ns) absolute amplitude spectrum")
    ax_abs.set_xlabel("Frequency (MHz)")
    ax_abs.legend(fontsize=7)

    ax_db = fig.add_subplot(grid[removed_row + 1, 0:2])
    d2_reference = float(w4_spectra["D2"]["amplitude_spectrum"].max())
    for label, spectrum in w4_spectra.items():
        ax_db.plot(
            spectrum["frequencies_mhz"],
            to_db(spectrum["amplitude_spectrum"], reference=d2_reference),
            label=label,
        )
    ax_db.set_title("W4 (20-100ns) dB, common reference = D2's own peak")
    ax_db.set_xlabel("Frequency (MHz)")
    ax_db.legend(fontsize=7)

    ax_table = fig.add_subplot(grid[removed_row + 1, 2])
    ax_table.axis("off")
    rows = [[k, f"{v:.4g}" if isinstance(v, float) else str(v)] for k, v in band_energy_summary.items()]
    ax_table.table(cellText=rows, colLabels=["band-energy metric", "value"], loc="center", cellLoc="left")
    ax_table.set_title("Band-energy retention summary (QC only)", fontsize=9)

    ax_coherence = fig.add_subplot(grid[removed_row + 2, :])
    ax_coherence.axis("off")
    rows = [[k, f"{v:.4g}" if isinstance(v, float) else str(v)] for k, v in spatial_coherence_summary.items()]
    ax_coherence.table(
        cellText=rows, colLabels=["spatial-coherence metric", "value"], loc="center", cellLoc="left"
    )
    ax_coherence.set_title(
        "Spatial-coherence summary (QC only -- not an automatic target interpretation)", fontsize=9
    )

    fig.suptitle(
        "Decision panel: D2 dewow + B1 vs B2 band-pass, 20-100ns only (direct wave excluded) -- "
        "QC evidence only, no candidate is marked canonical here",
        fontsize=13,
    )
    fig.savefig(output_path, dpi=130)
    plt.close(fig)
    return output_path


# ======================================================================
# Section 7: spatial-coherence comparison plots
# ======================================================================


def save_spatial_coherence_comparison(
    metrics_by_candidate_and_window: dict[str, dict[str, dict[str, float]]], output_path: str | Path
) -> Path:
    """Grouped bar chart of ``adjacent_trace_correlation_median`` per candidate, per window.

    ``metrics_by_candidate_and_window`` is ``{candidate_label: {window_label: metrics_dict}}``,
    where each ``metrics_dict`` is a :func:`archaeogpr.qc.spatial_coherence.compute_spatial_coherence_metrics`
    result. QC only -- a higher value is not itself claimed to mean "real target".
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidates = list(metrics_by_candidate_and_window.keys())
    windows = list(next(iter(metrics_by_candidate_and_window.values())).keys())

    fig, ax = plt.subplots(figsize=(10, 5.5))
    width = 0.8 / max(len(candidates), 1)
    x = np.arange(len(windows))
    cmap = plt.get_cmap("tab10")
    for i, candidate in enumerate(candidates):
        values = [
            metrics_by_candidate_and_window[candidate][window]["adjacent_trace_correlation_median"]
            for window in windows
        ]
        ax.bar(x + i * width, values, width=width, label=candidate, color=cmap(i))
    ax.set_xticks(x + width * (len(candidates) - 1) / 2)
    ax.set_xticklabels(windows)
    ax.set_ylabel("Adjacent-trace correlation (median)")
    ax.set_title("Spatial coherence comparison -- D2 vs B1 vs B2 (QC only, not a target claim)")
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def save_removed_component_coherence_plot(
    b1_removed_metrics_by_window: dict[str, dict[str, float]],
    b2_removed_metrics_by_window: dict[str, dict[str, float]],
    output_path: str | Path,
) -> Path:
    """Grouped bar chart comparing B1 vs B2 *removed-component* spatial coherence, per window."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    windows = list(b1_removed_metrics_by_window.keys())
    x = np.arange(len(windows))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5.5))
    b1_values = [b1_removed_metrics_by_window[w]["adjacent_trace_correlation_median"] for w in windows]
    b2_values = [b2_removed_metrics_by_window[w]["adjacent_trace_correlation_median"] for w in windows]
    ax.bar(x - width / 2, b1_values, width=width, label="B1 removed", color="tab:red")
    ax.bar(x + width / 2, b2_values, width=width, label="B2 removed", color="tab:purple")
    ax.set_xticks(x)
    ax.set_xticklabels(windows)
    ax.set_ylabel("Adjacent-trace correlation (median)")
    ax.set_title(
        "Removed-component spatial coherence -- B1 vs B2 (QC only; high = spatially continuous, "
        "low = noise-like; not an automatic target interpretation)"
    )
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path
