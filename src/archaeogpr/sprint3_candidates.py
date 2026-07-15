"""Sprint 3 candidate orchestration: dewow, spectrum, band-pass, and combined
candidates, each with its own QC suite plus a cross-candidate comparison.

This module never marks any candidate canonical -- see CLAUDE.md and
ADR-005/ADR-006. It only reads the Sprint 2 canonical NPZ and writes new
files under ``outputs/sprint03/``; it never modifies the canonical NPZ or
the raw ``.ogpr`` file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import sosfreqz

from archaeogpr.export.processed import write_corrected_npz, write_processing_metadata_json
from archaeogpr.export.sprint3 import (
    load_candidates_config,
    read_processed_npz,
    write_padding_verification_json,
)
from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.bandpass import (
    build_butterworth_sos,
    build_ormsby_transfer_function,
    correct_bandpass,
)
from archaeogpr.processing.dc_offset import correct_dc_offset
from archaeogpr.processing.dewow import correct_dewow
from archaeogpr.processing.result import ProcessingResult
from archaeogpr.qc.bandpass import save_bandpass_qc_suite
from archaeogpr.qc.dewow import save_dewow_qc_suite
from archaeogpr.qc.spectrum import compute_amplitude_spectrum

DC_METRIC_WINDOW_NS = (20.0, 100.0)
SPECTRUM_WINDOW_NS = (0.0, 100.0)
LOW_FREQ_CUTOFFS_MHZ = (50.0, 100.0, 150.0)
HIGH_FREQ_CUTOFFS_MHZ = (800.0, 1000.0, 1200.0)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dc_metric_snapshot(dataset: GPRDataset, valid_mask: np.ndarray | None) -> dict[str, dict[str, float]]:
    """Per-channel mean/median offset within the ISSUE-009 20-100 ns window -- QC only.

    Does not apply or keep either DC correction; both are computed and
    discarded, purely to report the metric.
    """
    mean_result = correct_dc_offset(
        dataset,
        method="mean",
        window_start_ns=DC_METRIC_WINDOW_NS[0],
        window_end_ns=DC_METRIC_WINDOW_NS[1],
        valid_mask=valid_mask,
        window_reference="dataset_time",
    )
    median_result = correct_dc_offset(
        dataset,
        method="median",
        window_start_ns=DC_METRIC_WINDOW_NS[0],
        window_end_ns=DC_METRIC_WINDOW_NS[1],
        valid_mask=valid_mask,
        window_reference="dataset_time",
    )
    channels_count = dataset.shape[1]
    per_channel: dict[str, dict[str, float]] = {}
    for channel in range(channels_count):
        mean_offset = float(mean_result.removed_component[:, channel, 0].astype(np.float64).mean())
        median_offset = float(median_result.removed_component[:, channel, 0].astype(np.float64).mean())
        per_channel[str(channel)] = {
            "mean_offset": mean_offset,
            "median_offset": median_offset,
            "mean_minus_median": mean_offset - median_offset,
        }
    return per_channel


def _band_energy(spectrum: dict[str, Any], low_mhz: float, high_mhz: float) -> float:
    freqs = spectrum["frequencies_mhz"]
    mask = (freqs >= low_mhz) & (freqs <= high_mhz)
    return float((spectrum["amplitude_spectrum"][mask] ** 2).sum())


def spectrum_metrics(spectrum: dict[str, Any]) -> dict[str, float]:
    """QC-only spectral summary metrics -- not a physical antenna-band claim."""
    freqs = spectrum["frequencies_mhz"]
    amp = spectrum["amplitude_spectrum"]
    nonzero = freqs > 0
    dominant_frequency_mhz = (
        float(freqs[nonzero][np.argmax(amp[nonzero])]) if nonzero.any() else float(freqs[0])
    )
    total_energy = float((amp**2).sum())
    centroid = float((freqs * amp**2).sum() / total_energy) if total_energy > 0 else 0.0

    peak = amp.max()
    above_half_power = amp >= (peak / np.sqrt(2)) if peak > 0 else np.zeros_like(amp, dtype=bool)
    band_freqs = freqs[above_half_power]
    minus_3db_low = float(band_freqs.min()) if band_freqs.size else float("nan")
    minus_3db_high = float(band_freqs.max()) if band_freqs.size else float("nan")

    cumulative_energy = np.cumsum(amp**2)
    cumulative_energy = (
        cumulative_energy / cumulative_energy[-1] if cumulative_energy[-1] > 0 else cumulative_energy
    )
    percentiles = {}
    for p in (5, 50, 95):
        idx = int(np.searchsorted(cumulative_energy, p / 100.0))
        idx = min(idx, len(freqs) - 1)
        percentiles[f"energy_percentile_{p}_mhz"] = float(freqs[idx])

    metrics: dict[str, float] = {
        "dominant_frequency_mhz": dominant_frequency_mhz,
        "spectral_centroid_mhz": centroid,
        "minus_3db_band_low_mhz": minus_3db_low,
        "minus_3db_band_high_mhz": minus_3db_high,
        **percentiles,
    }
    for cutoff in LOW_FREQ_CUTOFFS_MHZ:
        metrics[f"energy_below_{int(cutoff)}mhz"] = _band_energy(spectrum, 0.0, cutoff)
    for cutoff in HIGH_FREQ_CUTOFFS_MHZ:
        metrics[f"energy_above_{int(cutoff)}mhz"] = _band_energy(spectrum, cutoff, float(freqs[-1]))
    metrics["low_frequency_energy_ratio"] = (
        metrics[f"energy_below_{int(LOW_FREQ_CUTOFFS_MHZ[1])}mhz"] / total_energy if total_energy > 0 else 0.0
    )
    metrics["high_frequency_energy_ratio"] = (
        metrics[f"energy_above_{int(HIGH_FREQ_CUTOFFS_MHZ[1])}mhz"] / total_energy
        if total_energy > 0
        else 0.0
    )
    return metrics


# ======================================================================
# Dewow candidates
# ======================================================================


def run_dewow_candidates(
    dataset: GPRDataset, valid_mask: np.ndarray | None, output_root: Path, config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Run every dewow candidate in ``config``, writing its full QC suite.

    Returns a list of per-candidate info dicts.
    """
    edge_mode = config["edge_mode"]
    candidates_info: list[dict[str, Any]] = []
    for candidate in config["candidates"]:
        candidate_dir = output_root / f"{candidate['id']}_{candidate['label']}"
        candidate_dir.mkdir(parents=True, exist_ok=True)

        result = correct_dewow(
            dataset,
            window_ns=candidate["window_ns"],
            method=candidate["method"],
            valid_mask=valid_mask,
            edge_mode=edge_mode,
        )

        write_corrected_npz(result, candidate_dir / "dewow_processed.npz")
        write_processing_metadata_json(result, candidate_dir / "processing_metadata.json")
        write_padding_verification_json(result, candidate_dir / "padding_verification.json")
        qc_paths = save_dewow_qc_suite(dataset, result, candidate_dir)

        dc_metrics_after = _dc_metric_snapshot(result.dataset, valid_mask)
        spectrum_after = compute_amplitude_spectrum(
            result.dataset,
            time_start_ns=SPECTRUM_WINDOW_NS[0],
            time_end_ns=SPECTRUM_WINDOW_NS[1],
            valid_mask=valid_mask,
        )

        candidates_info.append(
            {
                "id": candidate["id"],
                "label": candidate["label"],
                "method": candidate["method"],
                "requested_window_ns": candidate["window_ns"],
                "result": result,
                "qc_paths": qc_paths,
                "dc_metrics_after": dc_metrics_after,
                "spectrum_after": spectrum_after,
                "spectrum_metrics_after": spectrum_metrics(spectrum_after),
                "output_dir": candidate_dir,
            }
        )
    return candidates_info


def build_dewow_comparison(
    dataset: GPRDataset,
    valid_mask: np.ndarray | None,
    candidates_info: list[dict[str, Any]],
    comparison_dir: Path,
    *,
    channel: int = 0,
) -> dict[str, Path]:
    """Build the dewow candidate comparison folder. Makes no canonical selection."""
    comparison_dir.mkdir(parents=True, exist_ok=True)
    channels_count = dataset.shape[1]
    paths: dict[str, Path] = {}

    dc_metrics_raw = _dc_metric_snapshot(dataset, valid_mask)
    spectrum_raw = compute_amplitude_spectrum(
        dataset, time_start_ns=SPECTRUM_WINDOW_NS[0], time_end_ns=SPECTRUM_WINDOW_NS[1], valid_mask=valid_mask
    )
    spectrum_metrics_raw = spectrum_metrics(spectrum_raw)

    # --- channel00_all_dewow_candidates.png: median trace overlay, all candidates ---
    fig, ax = plt.subplots(figsize=(12, 6))
    raw_median = np.median(dataset.amplitudes[:, channel, :].astype(np.float64), axis=0)
    ax.plot(dataset.time_ns, raw_median, color="black", linewidth=1.4, linestyle=":", label="raw (canonical)")
    cmap = plt.get_cmap("tab10")
    for i, info in enumerate(candidates_info):
        after = info["result"].dataset
        median_trace = np.median(after.amplitudes[:, channel, :].astype(np.float64), axis=0)
        ax.plot(
            after.time_ns, median_trace, color=cmap(i), linewidth=1.2, label=f"{info['id']} ({info['label']})"
        )
    ax.set_xlabel("time_ns")
    ax.set_ylabel("Median amplitude")
    ax.set_title(f"Channel {channel:02d} median trace -- all dewow candidates (QC only)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = comparison_dir / "channel00_all_dewow_candidates.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths["channel00_all_dewow_candidates"] = path

    # --- all_channel_medians_candidates.png: one panel per candidate, all channels ---
    n = len(candidates_info)
    ncols = 2
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 4 * nrows), squeeze=False)
    channel_cmap = plt.get_cmap("viridis")
    for i, info in enumerate(candidates_info):
        ax = axes[i // ncols][i % ncols]
        after = info["result"].dataset
        for ch in range(channels_count):
            color = channel_cmap(ch / max(channels_count - 1, 1))
            median_trace = np.median(after.amplitudes[:, ch, :].astype(np.float64), axis=0)
            ax.plot(after.time_ns, median_trace, color=color, linewidth=0.9)
        ax.set_title(f"{info['id']} ({info['label']})")
        ax.set_xlabel("time_ns")
    for j in range(n, nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")
    fig.suptitle("All-channel median traces per dewow candidate (QC only)")
    fig.tight_layout()
    path = comparison_dir / "all_channel_medians_candidates.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    paths["all_channel_medians_candidates"] = path

    # --- low_frequency_energy_comparison.png ---
    labels = ["raw"] + [info["id"] for info in candidates_info]
    energies = [spectrum_metrics_raw["energy_below_100mhz"]] + [
        info["spectrum_metrics_after"]["energy_below_100mhz"] for info in candidates_info
    ]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(labels, energies, color=["gray"] + [cmap(i) for i in range(n)])
    ax.set_ylabel("Energy below 100 MHz (QC metric, arbitrary units)")
    ax.set_title("Low-frequency energy: raw vs each dewow candidate (QC only)")
    fig.tight_layout()
    path = comparison_dir / "low_frequency_energy_comparison.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths["low_frequency_energy_comparison"] = path

    # --- mean_vs_median_dc_metric_comparison.png: heatmap of mean-minus-median per channel ---
    conditions = ["raw"] + [info["id"] for info in candidates_info]
    all_metrics = [dc_metrics_raw] + [info["dc_metrics_after"] for info in candidates_info]
    heatmap = np.array(
        [
            [all_metrics[c][str(ch)]["mean_minus_median"] for ch in range(channels_count)]
            for c in range(len(conditions))
        ]
    )
    fig, ax = plt.subplots(figsize=(10, 4))
    limit = float(np.abs(heatmap).max()) or 1.0
    im = ax.imshow(heatmap, aspect="auto", cmap="coolwarm", vmin=-limit, vmax=limit)
    ax.set_yticks(range(len(conditions)))
    ax.set_yticklabels(conditions)
    ax.set_xticks(range(channels_count))
    ax.set_xlabel("Channel")
    ax.set_title(
        "DC mean-minus-median (20-100 ns window) per channel -- raw vs dewow candidates (ISSUE-009 QC)"
    )
    fig.colorbar(im, ax=ax, label="mean - median")
    fig.tight_layout()
    path = comparison_dir / "mean_vs_median_dc_metric_comparison.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths["mean_vs_median_dc_metric_comparison"] = path

    # --- dewow_candidate_metrics.csv ---
    rows = []
    for info in candidates_info:
        result: ProcessingResult = info["result"]
        diag = result.diagnostics
        mean_minus_median_values = [
            info["dc_metrics_after"][str(ch)]["mean_minus_median"] for ch in range(channels_count)
        ]
        rows.append(
            {
                "id": info["id"],
                "label": info["label"],
                "method": info["method"],
                "requested_window_ns": diag["requested_window_ns"],
                "applied_window_ns": diag["applied_window_ns"],
                "applied_window_samples": diag["applied_window_samples"],
                "edge_mode": diag["edge_mode"],
                "removed_component_mean": diag["removed_component_statistics"]["mean"],
                "removed_component_std": diag["removed_component_statistics"]["std"],
                "output_mean": diag["output_statistics"]["mean"],
                "output_std": diag["output_statistics"]["std"],
                "low_frequency_energy_below_100mhz": info["spectrum_metrics_after"]["energy_below_100mhz"],
                "low_frequency_energy_ratio": info["spectrum_metrics_after"]["low_frequency_energy_ratio"],
                "dominant_frequency_mhz": info["spectrum_metrics_after"]["dominant_frequency_mhz"],
                "mean_minus_median_avg_abs": float(np.mean(np.abs(mean_minus_median_values))),
                "mean_minus_median_max_abs": float(np.max(np.abs(mean_minus_median_values))),
            }
        )
    metrics_df = pd.DataFrame(rows)
    csv_path = comparison_dir / "dewow_candidate_metrics.csv"
    metrics_df.to_csv(csv_path, index=False)
    paths["dewow_candidate_metrics_csv"] = csv_path

    review_path = comparison_dir / "DEWOW_REVIEW_REQUIRED.md"
    review_path.write_text(_dewow_review_markdown(candidates_info, spectrum_metrics_raw), encoding="utf-8")
    paths["review"] = review_path
    return paths


def _dewow_review_markdown(
    candidates_info: list[dict[str, Any]], spectrum_metrics_raw: dict[str, float]
) -> str:
    rows = "\n".join(
        f"| {info['id']} | {info['label']} | {info['method']} | "
        f"{info['result'].diagnostics['requested_window_ns']:g} | "
        f"{info['result'].diagnostics['applied_window_ns']:.4g} | "
        f"{info['spectrum_metrics_after']['low_frequency_energy_ratio']:.4f} | "
        f"{info['spectrum_metrics_after']['dominant_frequency_mhz']:.1f} |"
        for info in candidates_info
    )
    return f"""# Dewow Candidate Review Required

Status: **review_required** -- no dewow candidate has been selected as canonical.
This document presents measured/derived quantities only.

## Candidates

| ID | Label | Method | Req window (ns) | Applied (ns) | Low-freq ratio (after) | Dom freq (MHz, after) |
|---|---|---|---|---|---|---|
{rows}

Raw canonical low-frequency energy ratio (0-100 ns window, before any dewow): \
{spectrum_metrics_raw["low_frequency_energy_ratio"]:.4f}

## Risks (measured/derived, not a selection)

- **Short window (D1, 4 ns) risk:** a narrow moving-average window follows the
  trace's own short-timescale fluctuations more closely, so it can remove real,
  fast reflection content along with the intended slow "wow" drift -- the
  shorter the window, the more it behaves like a broadband high-pass filter
  rather than a baseline-drift remover.
- **Long window (D3, 12 ns) risk:** a wide moving-average window responds only
  to very slow drift, so genuine low-frequency wow occurring on a timescale
  shorter than the window may not be fully removed -- see each candidate's own
  `low_frequency_spectrum_before_after.png` for the actual measured effect.
- **Median dewow (D4) is a nonlinear filter.** Unlike running_mean, it does not
  correspond to a simple linear high-pass response, and its behavior on
  transients/pulses differs qualitatively from the mean-based candidates. It
  is offered here for robust QC comparison only, not as an assumed equivalent
  alternative to the mean-based candidates.
- Candidates are **not automatically selected**. See
  `dewow_candidate_metrics.csv`, `channel00_all_dewow_candidates.png`,
  `all_channel_medians_candidates.png`, `low_frequency_energy_comparison.png`,
  and `mean_vs_median_dc_metric_comparison.png` for the full comparison.
  Selecting a candidate requires human/geophysical review.
"""


# ======================================================================
# Spectrum analysis
# ======================================================================


def run_spectrum_analysis(
    dataset: GPRDataset,
    valid_mask: np.ndarray | None,
    dewow_candidates_info: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Path]:
    """Raw canonical spectrum + all dewow candidates' spectra, with metrics. QC only."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    raw_spectrum = compute_amplitude_spectrum(
        dataset, time_start_ns=SPECTRUM_WINDOW_NS[0], time_end_ns=SPECTRUM_WINDOW_NS[1], valid_mask=valid_mask
    )
    raw_metrics = spectrum_metrics(raw_spectrum)

    csv_path = output_dir / "raw_canonical_spectrum.csv"
    pd.DataFrame(
        {
            "frequency_mhz": raw_spectrum["frequencies_mhz"],
            "amplitude": raw_spectrum["amplitude_spectrum"],
            "amplitude_db": raw_spectrum["amplitude_spectrum_db"],
            "amplitude_normalized": raw_spectrum["amplitude_spectrum_normalized"],
        }
    ).to_csv(csv_path, index=False)
    paths["raw_canonical_spectrum_csv"] = csv_path

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(raw_spectrum["frequencies_mhz"], raw_spectrum["amplitude_spectrum_db"])
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Amplitude (dB, relative to peak)")
    ax.set_title("Raw canonical amplitude spectrum (QC only, not a physical antenna-band claim)")
    fig.tight_layout()
    png_path = output_dir / "raw_canonical_spectrum.png"
    fig.savefig(png_path, dpi=140)
    plt.close(fig)
    paths["raw_canonical_spectrum_png"] = png_path

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        raw_spectrum["frequencies_mhz"], raw_spectrum["amplitude_spectrum_db"], color="black", label="raw"
    )
    cmap = plt.get_cmap("tab10")
    for i, info in enumerate(dewow_candidates_info):
        ax.plot(
            info["spectrum_after"]["frequencies_mhz"],
            info["spectrum_after"]["amplitude_spectrum_db"],
            color=cmap(i),
            label=f"{info['id']} ({info['label']})",
        )
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Amplitude (dB, relative to each spectrum's own peak)")
    ax.set_title("Amplitude spectrum -- raw vs each dewow candidate (QC only)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    candidate_spectra_path = output_dir / "dewow_candidate_spectra.png"
    fig.savefig(candidate_spectra_path, dpi=140)
    plt.close(fig)
    paths["dewow_candidate_spectra"] = candidate_spectra_path

    rows = [{"source": "raw_canonical", **raw_metrics}]
    for info in dewow_candidates_info:
        rows.append({"source": info["id"], **info["spectrum_metrics_after"]})
    metrics_csv_path = output_dir / "spectrum_metrics.csv"
    pd.DataFrame(rows).to_csv(metrics_csv_path, index=False)
    paths["spectrum_metrics_csv"] = metrics_csv_path

    metadata_path = output_dir / "spectrum_metadata.json"
    metadata_path.write_text(json.dumps(raw_spectrum["metadata"], indent=2), encoding="utf-8")
    paths["spectrum_metadata_json"] = metadata_path

    notes_path = output_dir / "SPECTRUM_INTERPRETATION_NOTES.md"
    notes_path.write_text(
        f"""# Spectrum Interpretation Notes

These are QC metrics only -- **none of the values below are treated as "the
real antenna band"** or any other physical claim. See CLAUDE.md and
ADR-005/006.

- Sampling frequency: {raw_spectrum["metadata"]["sampling_frequency_mhz"]:.4g} MHz
- Nyquist: {raw_spectrum["metadata"]["nyquist_mhz"]:.4g} MHz
- FFT length: {raw_spectrum["metadata"]["fft_length"]} samples
- Frequency resolution: {raw_spectrum["metadata"]["frequency_resolution_mhz"]:.4g} MHz
- Time window analyzed: [{SPECTRUM_WINDOW_NS[0]}, {SPECTRUM_WINDOW_NS[1]}) ns
- Raw canonical dominant frequency (excluding 0 MHz): {raw_metrics["dominant_frequency_mhz"]:.1f} MHz
- Raw canonical spectral centroid: {raw_metrics["spectral_centroid_mhz"]:.1f} MHz
- Raw canonical -3 dB band: [{raw_metrics["minus_3db_band_low_mhz"]:.1f}, \
{raw_metrics["minus_3db_band_high_mhz"]:.1f}] MHz

The header's nominal frequency (600 MHz) is a metadata value from the
acquisition equipment, not independently re-derived here as a spectral
measurement -- see `spectrum_metrics.csv` for the full per-source metric
table (raw canonical + every dewow candidate) and draw your own comparison;
this file does not recommend a band-pass range.
""",
        encoding="utf-8",
    )
    paths["spectrum_interpretation_notes"] = notes_path
    return paths


# ======================================================================
# Band-pass candidates
# ======================================================================


def run_bandpass_candidates(
    dewow_base_result: ProcessingResult,
    valid_mask: np.ndarray | None,
    output_root: Path,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Run every band-pass candidate on ``dewow_base_result.dataset``. Returns per-candidate info dicts."""
    base_dataset = dewow_base_result.dataset
    candidates_info: list[dict[str, Any]] = []
    for candidate in config["candidates"]:
        candidate_dir = output_root / f"{candidate['id']}_{candidate['label']}"
        candidate_dir.mkdir(parents=True, exist_ok=True)

        kwargs: dict[str, Any] = {"method": candidate["method"], "valid_mask": valid_mask}
        if candidate["method"] == "butterworth":
            kwargs.update(
                lowcut_mhz=candidate["lowcut_mhz"],
                highcut_mhz=candidate["highcut_mhz"],
                order=candidate["order"],
            )
        else:
            kwargs["frequencies_mhz"] = tuple(candidate["frequencies_mhz"])
        result = correct_bandpass(base_dataset, **kwargs)

        write_corrected_npz(result, candidate_dir / "bandpass_processed.npz")
        write_processing_metadata_json(result, candidate_dir / "processing_metadata.json")
        write_padding_verification_json(result, candidate_dir / "padding_verification.json")
        qc_paths = save_bandpass_qc_suite(base_dataset, result, candidate_dir)

        spectrum_before = compute_amplitude_spectrum(
            base_dataset,
            time_start_ns=SPECTRUM_WINDOW_NS[0],
            time_end_ns=SPECTRUM_WINDOW_NS[1],
            valid_mask=valid_mask,
        )
        spectrum_after = compute_amplitude_spectrum(
            result.dataset,
            time_start_ns=SPECTRUM_WINDOW_NS[0],
            time_end_ns=SPECTRUM_WINDOW_NS[1],
            valid_mask=valid_mask,
        )

        candidates_info.append(
            {
                "id": candidate["id"],
                "label": candidate["label"],
                "method": candidate["method"],
                "result": result,
                "qc_paths": qc_paths,
                "spectrum_before": spectrum_before,
                "spectrum_after": spectrum_after,
                "spectrum_metrics_before": spectrum_metrics(spectrum_before),
                "spectrum_metrics_after": spectrum_metrics(spectrum_after),
                "output_dir": candidate_dir,
            }
        )
    return candidates_info


def build_bandpass_comparison(
    base_dataset: GPRDataset,
    candidates_info: list[dict[str, Any]],
    comparison_dir: Path,
    *,
    channel: int = 0,
) -> dict[str, Path]:
    """Build the band-pass candidate comparison folder. Makes no canonical selection."""
    comparison_dir.mkdir(parents=True, exist_ok=True)
    channels_count = base_dataset.shape[1]
    paths: dict[str, Path] = {}
    cmap = plt.get_cmap("tab10")

    fig, ax = plt.subplots(figsize=(12, 6))
    base_median = np.median(base_dataset.amplitudes[:, channel, :].astype(np.float64), axis=0)
    ax.plot(
        base_dataset.time_ns,
        base_median,
        color="black",
        linestyle=":",
        linewidth=1.4,
        label="dewow base (D2)",
    )
    for i, info in enumerate(candidates_info):
        after = info["result"].dataset
        median_trace = np.median(after.amplitudes[:, channel, :].astype(np.float64), axis=0)
        ax.plot(
            after.time_ns, median_trace, color=cmap(i), linewidth=1.2, label=f"{info['id']} ({info['label']})"
        )
    ax.set_xlabel("time_ns")
    ax.set_ylabel("Median amplitude")
    ax.set_title(f"Channel {channel:02d} median trace -- all band-pass candidates (QC only)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = comparison_dir / "channel00_all_bandpass_candidates.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths["channel00_all_bandpass_candidates"] = path

    n = len(candidates_info)
    ncols = 2
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 4 * nrows), squeeze=False)
    channel_cmap = plt.get_cmap("viridis")
    for i, info in enumerate(candidates_info):
        ax = axes[i // ncols][i % ncols]
        after = info["result"].dataset
        for ch in range(channels_count):
            color = channel_cmap(ch / max(channels_count - 1, 1))
            median_trace = np.median(after.amplitudes[:, ch, :].astype(np.float64), axis=0)
            ax.plot(after.time_ns, median_trace, color=color, linewidth=0.9)
        ax.set_title(f"{info['id']} ({info['label']})")
        ax.set_xlabel("time_ns")
    for j in range(n, nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")
    fig.suptitle("All-channel median traces per band-pass candidate (QC only)")
    fig.tight_layout()
    path = comparison_dir / "all_channel_medians_bandpass_candidates.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    paths["all_channel_medians_bandpass_candidates"] = path

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        candidates_info[0]["spectrum_before"]["frequencies_mhz"],
        candidates_info[0]["spectrum_before"]["amplitude_spectrum_db"],
        color="black",
        label="dewow base (D2)",
    )
    for i, info in enumerate(candidates_info):
        ax.plot(
            info["spectrum_after"]["frequencies_mhz"],
            info["spectrum_after"]["amplitude_spectrum_db"],
            color=cmap(i),
            label=f"{info['id']} ({info['label']})",
        )
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Amplitude (dB, relative to each spectrum's own peak)")
    ax.set_title("Amplitude spectrum -- all band-pass candidates (QC only)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = comparison_dir / "spectra_all_candidates.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths["spectra_all_candidates"] = path

    fig, ax = plt.subplots(figsize=(10, 5))
    for i, info in enumerate(candidates_info):
        diag = info["result"].diagnostics
        sampling_time_ns = diag["sampling_time_ns"]
        sampling_frequency_hz = 1.0 / (sampling_time_ns * 1e-9)
        freqs_hz = np.linspace(0, sampling_frequency_hz / 2, 4096)
        if diag["method"] == "butterworth":
            sos = build_butterworth_sos(
                diag["lowcut_mhz"], diag["highcut_mhz"], diag["order"], sampling_time_ns
            )
            _, h = sosfreqz(sos, worN=freqs_hz, fs=sampling_frequency_hz)
            magnitude = np.abs(h)
        else:
            magnitude = build_ormsby_transfer_function(freqs_hz, tuple(diag["frequencies_mhz"]))
        ax.plot(freqs_hz / 1e6, magnitude, color=cmap(i), label=f"{info['id']} ({info['label']})")
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("|H(f)|")
    ax.set_title("Transfer functions -- all band-pass candidates")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = comparison_dir / "transfer_functions_all_candidates.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths["transfer_functions_all_candidates"] = path

    fig, ax = plt.subplots(figsize=(12, 6))
    for i, info in enumerate(candidates_info):
        removed_median = np.median(info["result"].removed_component[:, channel, :].astype(np.float64), axis=0)
        ax.plot(base_dataset.time_ns, removed_median, color=cmap(i), label=f"{info['id']} ({info['label']})")
    ax.set_xlabel("time_ns")
    ax.set_ylabel("Median removed amplitude")
    ax.set_title(f"Channel {channel:02d} removed component (median trace) -- all band-pass candidates")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = comparison_dir / "removed_components_all_candidates.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths["removed_components_all_candidates"] = path

    phase_rows = []
    for info in candidates_info:
        for segment_key, stats in info["result"].diagnostics["peak_shift_and_lag_per_segment"].items():
            channel_str, span = segment_key.split(":")
            start_str, end_str = span.split("-")
            phase_rows.append(
                {
                    "id": info["id"],
                    "label": info["label"],
                    "method": info["method"],
                    "channel": int(channel_str),
                    "segment_start": int(start_str),
                    "segment_end": int(end_str),
                    **stats,
                }
            )
    phase_csv_path = comparison_dir / "phase_lag_comparison.csv"
    pd.DataFrame(phase_rows).to_csv(phase_csv_path, index=False)
    paths["phase_lag_comparison_csv"] = phase_csv_path

    spectral_rows = []
    for info in candidates_info:
        spectral_rows.append(
            {"id": info["id"], "label": info["label"], "stage": "before", **info["spectrum_metrics_before"]}
        )
        spectral_rows.append(
            {"id": info["id"], "label": info["label"], "stage": "after", **info["spectrum_metrics_after"]}
        )
    spectral_csv_path = comparison_dir / "spectral_metrics_comparison.csv"
    pd.DataFrame(spectral_rows).to_csv(spectral_csv_path, index=False)
    paths["spectral_metrics_comparison_csv"] = spectral_csv_path

    rows = []
    for info in candidates_info:
        diag = info["result"].diagnostics
        all_lags = [
            s["median_trace_cross_correlation_lag"] for s in diag["peak_shift_and_lag_per_segment"].values()
        ]
        all_passband_after = [
            e["passband_energy_fraction_after"] for e in diag["band_energy_fraction_per_segment"].values()
        ]
        all_passband_before = [
            e["passband_energy_fraction_before"] for e in diag["band_energy_fraction_per_segment"].values()
        ]
        rows.append(
            {
                "id": info["id"],
                "label": info["label"],
                "method": info["method"],
                "lowcut_mhz": diag.get("lowcut_mhz"),
                "highcut_mhz": diag.get("highcut_mhz"),
                "order": diag.get("order"),
                "frequencies_mhz": diag.get("frequencies_mhz"),
                "sampling_frequency_mhz": diag["sampling_frequency_mhz"],
                "nyquist_mhz": diag["nyquist_mhz"],
                "max_abs_median_trace_lag": int(np.max(np.abs(all_lags))) if all_lags else None,
                "passband_energy_fraction_before_mean": (
                    float(np.mean(all_passband_before)) if all_passband_before else None
                ),
                "passband_energy_fraction_after_mean": (
                    float(np.mean(all_passband_after)) if all_passband_after else None
                ),
                "dominant_frequency_mhz_before": info["spectrum_metrics_before"]["dominant_frequency_mhz"],
                "dominant_frequency_mhz_after": info["spectrum_metrics_after"]["dominant_frequency_mhz"],
                "spectral_centroid_mhz_before": info["spectrum_metrics_before"]["spectral_centroid_mhz"],
                "spectral_centroid_mhz_after": info["spectrum_metrics_after"]["spectral_centroid_mhz"],
            }
        )
    metrics_csv_path = comparison_dir / "bandpass_candidate_metrics.csv"
    pd.DataFrame(rows).to_csv(metrics_csv_path, index=False)
    paths["bandpass_candidate_metrics_csv"] = metrics_csv_path

    review_path = comparison_dir / "BANDPASS_REVIEW_REQUIRED.md"
    review_path.write_text(_bandpass_review_markdown(candidates_info), encoding="utf-8")
    paths["review"] = review_path
    return paths


def _bandpass_review_markdown(candidates_info: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        f"| {info['id']} | {info['label']} | {info['method']} | "
        f"{info['result'].diagnostics.get('lowcut_mhz', '-')} | "
        f"{info['result'].diagnostics.get('highcut_mhz', '-')} | "
        f"{info['result'].diagnostics.get('frequencies_mhz', '-')} |"
        for info in candidates_info
    )
    return f"""# Band-pass Candidate Review Required

Status: **review_required** -- no band-pass candidate has been selected as canonical.
All candidates were run on the same dewow base (D2, running_mean, 8 ns
requested) purely as a controlled comparison baseline -- this does not mean
D2 is canonical either.

## Candidates

| ID | Label | Method | Lowcut (MHz) | Highcut (MHz) | Ormsby corners (MHz) |
|---|---|---|---|---|---|
{rows}

## Risks (measured/derived, not a selection)

- **Narrow band risk:** a tighter passband (e.g. B2's 120-800 MHz vs B1's
  100-900 MHz) rejects more of the signal's own energy along with noise --
  see each candidate's `bandpass_candidate_metrics.csv` passband-energy
  columns for the actual measured retained fraction. A narrow band can
  discard real reflection energy near its edges, not only noise.
- **Wide band risk:** a broader passband retains more out-of-band noise,
  which can obscure genuine reflections in later interpretation stages.
- **Butterworth vs Ormsby:** Butterworth's roll-off is smooth and
  order-dependent (steeper with higher order, but with more numerical
  sensitivity for short valid segments); Ormsby's roll-off is a fixed linear
  ramp between its four corner frequencies -- neither is shown here to be
  superior, only different in transition shape (see each candidate's own
  `transfer_function.png` and this folder's `transfer_functions_all_candidates.png`).
- **The header's 600 MHz nominal frequency is not, by itself, sufficient to
  choose a band-pass range.** It is a single metadata value from the
  acquisition equipment, not an independently measured spectral center --
  see `outputs/sprint03/spectrum/SPECTRUM_INTERPRETATION_NOTES.md`.
- Candidates are **not automatically selected**. Selecting one requires
  human/geophysical review of `phase_lag_comparison.csv`,
  `spectral_metrics_comparison.csv`, and `bandpass_candidate_metrics.csv`
  alongside the visual comparisons in this folder.
"""


# ======================================================================
# Combined dewow + band-pass candidates
# ======================================================================


def run_combined_candidates(
    dewow_candidates_info: list[dict[str, Any]],
    valid_mask: np.ndarray | None,
    output_root: Path,
    bandpass_config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Run each controlled dewow+bandpass pair from ``bandpass_config['combined_candidates']``."""
    dewow_by_id = {info["id"]: info for info in dewow_candidates_info}
    bandpass_by_id = {c["id"]: c for c in bandpass_config["candidates"]}
    candidates_info: list[dict[str, Any]] = []

    for combo in bandpass_config["combined_candidates"]:
        dewow_info = dewow_by_id[combo["dewow"]]
        bandpass_params = bandpass_by_id[combo["bandpass"]]
        candidate_dir = output_root / f"{combo['id']}_{combo['label']}"
        candidate_dir.mkdir(parents=True, exist_ok=True)

        kwargs: dict[str, Any] = {"method": bandpass_params["method"], "valid_mask": valid_mask}
        if bandpass_params["method"] == "butterworth":
            kwargs.update(
                lowcut_mhz=bandpass_params["lowcut_mhz"],
                highcut_mhz=bandpass_params["highcut_mhz"],
                order=bandpass_params["order"],
            )
        else:
            kwargs["frequencies_mhz"] = tuple(bandpass_params["frequencies_mhz"])
        bp_result = correct_bandpass(dewow_info["result"].dataset, **kwargs)

        write_corrected_npz(bp_result, candidate_dir / "combined_processed.npz")
        write_processing_metadata_json(bp_result, candidate_dir / "processing_metadata.json")
        write_padding_verification_json(bp_result, candidate_dir / "padding_verification.json")
        qc_paths = save_bandpass_qc_suite(dewow_info["result"].dataset, bp_result, candidate_dir)

        spectrum_after = compute_amplitude_spectrum(
            bp_result.dataset,
            time_start_ns=SPECTRUM_WINDOW_NS[0],
            time_end_ns=SPECTRUM_WINDOW_NS[1],
            valid_mask=valid_mask,
        )

        candidates_info.append(
            {
                "id": combo["id"],
                "label": combo["label"],
                "dewow_id": combo["dewow"],
                "bandpass_id": combo["bandpass"],
                "result": bp_result,
                "qc_paths": qc_paths,
                "spectrum_after": spectrum_after,
                "spectrum_metrics_after": spectrum_metrics(spectrum_after),
                "output_dir": candidate_dir,
            }
        )
    return candidates_info


def build_combined_comparison(
    raw_dataset: GPRDataset,
    candidates_info: list[dict[str, Any]],
    comparison_dir: Path,
    *,
    channel: int = 0,
) -> dict[str, Path]:
    """Build the combined dewow+bandpass candidate comparison folder. Makes no canonical selection."""
    comparison_dir.mkdir(parents=True, exist_ok=True)
    channels_count = raw_dataset.shape[1]
    paths: dict[str, Path] = {}
    cmap = plt.get_cmap("tab10")

    fig, ax = plt.subplots(figsize=(12, 6))
    raw_median = np.median(raw_dataset.amplitudes[:, channel, :].astype(np.float64), axis=0)
    ax.plot(
        raw_dataset.time_ns, raw_median, color="black", linestyle=":", linewidth=1.4, label="raw (canonical)"
    )
    for i, info in enumerate(candidates_info):
        after = info["result"].dataset
        median_trace = np.median(after.amplitudes[:, channel, :].astype(np.float64), axis=0)
        ax.plot(
            after.time_ns,
            median_trace,
            color=cmap(i),
            linewidth=1.2,
            label=f"{info['id']} ({info['dewow_id']}+{info['bandpass_id']})",
        )
    ax.set_xlabel("time_ns")
    ax.set_ylabel("Median amplitude")
    ax.set_title(f"Channel {channel:02d} median trace -- all combined candidates (QC only)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = comparison_dir / "channel00_all_combined_candidates.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths["channel00_all_combined_candidates"] = path

    n = len(candidates_info)
    ncols = 3
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 4 * nrows), squeeze=False)
    channel_cmap = plt.get_cmap("viridis")
    for i, info in enumerate(candidates_info):
        ax = axes[i // ncols][i % ncols]
        after = info["result"].dataset
        for ch in range(channels_count):
            color = channel_cmap(ch / max(channels_count - 1, 1))
            median_trace = np.median(after.amplitudes[:, ch, :].astype(np.float64), axis=0)
            ax.plot(after.time_ns, median_trace, color=color, linewidth=0.9)
        ax.set_title(f"{info['id']} ({info['dewow_id']}+{info['bandpass_id']})")
        ax.set_xlabel("time_ns")
    for j in range(n, nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")
    fig.suptitle("All-channel median traces per combined candidate (QC only)")
    fig.tight_layout()
    path = comparison_dir / "all_channel_medians_combined.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    paths["all_channel_medians_combined"] = path

    fig, ax = plt.subplots(figsize=(10, 5))
    for i, info in enumerate(candidates_info):
        ax.plot(
            info["spectrum_after"]["frequencies_mhz"],
            info["spectrum_after"]["amplitude_spectrum_db"],
            color=cmap(i),
            label=f"{info['id']} ({info['dewow_id']}+{info['bandpass_id']})",
        )
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Amplitude (dB, relative to each spectrum's own peak)")
    ax.set_title("Amplitude spectrum -- all combined candidates (QC only)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = comparison_dir / "combined_spectra.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths["combined_spectra"] = path

    rows = []
    for info in candidates_info:
        diag = info["result"].diagnostics
        all_lags = [
            s["median_trace_cross_correlation_lag"] for s in diag["peak_shift_and_lag_per_segment"].values()
        ]
        rows.append(
            {
                "id": info["id"],
                "dewow_id": info["dewow_id"],
                "bandpass_id": info["bandpass_id"],
                "bandpass_method": diag["method"],
                "max_abs_median_trace_lag": int(np.max(np.abs(all_lags))) if all_lags else None,
                "dominant_frequency_mhz": info["spectrum_metrics_after"]["dominant_frequency_mhz"],
                "spectral_centroid_mhz": info["spectrum_metrics_after"]["spectral_centroid_mhz"],
                "low_frequency_energy_ratio": info["spectrum_metrics_after"]["low_frequency_energy_ratio"],
                "high_frequency_energy_ratio": info["spectrum_metrics_after"]["high_frequency_energy_ratio"],
            }
        )
    metrics_csv_path = comparison_dir / "combined_candidate_metrics.csv"
    pd.DataFrame(rows).to_csv(metrics_csv_path, index=False)
    paths["combined_candidate_metrics_csv"] = metrics_csv_path

    review_path = comparison_dir / "COMBINED_REVIEW_REQUIRED.md"
    combo_rows = "\n".join(
        f"| {info['id']} | {info['dewow_id']} | {info['bandpass_id']} |" for info in candidates_info
    )
    review_path.write_text(
        f"""# Combined Candidate Review Required

Status: **review_required** -- no combined candidate has been selected as canonical.

## Candidates

| ID | Dewow | Band-pass |
|---|---|---|
{combo_rows}

C1-C3 vary the dewow window (D1/D2/D3) with band-pass held fixed (B2), to
isolate the dewow window's own effect. C4-C6 vary the band-pass candidate
(B1/B3/B4) with dewow held fixed (D2), to isolate the band-pass choice's own
effect. This is a controlled comparison design, not an exhaustive 4x4 sweep,
and using D2/B2 as the fixed baseline in these pairings does **not** mean
either is canonical.

See `combined_candidate_metrics.csv` and the comparison plots in this folder.
Selecting a combined candidate requires human/geophysical review.
""",
        encoding="utf-8",
    )
    paths["review"] = review_path
    return paths


# ======================================================================
# Top-level orchestrator
# ======================================================================


def _padding_ok(candidate_dir: Path) -> bool:
    report = json.loads((candidate_dir / "padding_verification.json").read_text(encoding="utf-8"))
    return bool(report["all_channels_padding_untouched"]) and bool(
        report["all_channels_removed_component_zero_at_padding"]
    )


def _max_abs_lag(info: dict[str, Any]) -> int | None:
    lags = [
        s["median_trace_cross_correlation_lag"]
        for s in info["result"].diagnostics["peak_shift_and_lag_per_segment"].values()
    ]
    return int(np.max(np.abs(lags))) if lags else None


def _write_sprint3_review(
    output_dir: Path,
    dewow_info: list[dict[str, Any]],
    bandpass_info: list[dict[str, Any]],
    combined_info: list[dict[str, Any]],
    dewow_base_id: str,
) -> Path:
    """Top-level ``outputs/sprint03/SPRINT3_REVIEW_REQUIRED.md`` -- links every candidate
    and comparison folder, states padding/phase verification, and makes no selection.
    """
    dewow_rows = "\n".join(
        f"| {info['id']} | {info['label']} | {info['method']} | "
        f"{info['result'].diagnostics['applied_window_ns']:.4g} | "
        f"{'yes' if _padding_ok(info['output_dir']) else 'NO'} | "
        f"{info['spectrum_metrics_after']['dominant_frequency_mhz']:.1f} | "
        f"{info['spectrum_metrics_after']['low_frequency_energy_ratio']:.4f} |"
        for info in dewow_info
    )
    bandpass_rows = "\n".join(
        f"| {info['id']} | {info['label']} | {info['method']} | "
        f"{'yes' if _padding_ok(info['output_dir']) else 'NO'} | "
        f"{_max_abs_lag(info)} | "
        f"{info['spectrum_metrics_after']['dominant_frequency_mhz']:.1f} |"
        for info in bandpass_info
    )
    combined_rows = "\n".join(
        f"| {info['id']} | {info['dewow_id']}+{info['bandpass_id']} | "
        f"{'yes' if _padding_ok(info['output_dir']) else 'NO'} | "
        f"{_max_abs_lag(info)} | "
        f"{info['spectrum_metrics_after']['dominant_frequency_mhz']:.1f} |"
        for info in combined_info
    )
    all_padding_ok = all(
        _padding_ok(info["output_dir"]) for info in (*dewow_info, *bandpass_info, *combined_info)
    )
    all_lags = [lag for info in (*bandpass_info, *combined_info) if (lag := _max_abs_lag(info)) is not None]
    zero_phase_ok = all(lag == 0 for lag in all_lags)

    text = f"""# Sprint 3 Review Required

Status: **review_required**. Dewow and band-pass candidates, their QC suites,
and cross-candidate comparisons have all been generated. **No dewow or
band-pass candidate has been selected as canonical.** Selecting one requires
human/geophysical review of the evidence below -- see CLAUDE.md,
ADR-005 (dewow window/edge policy), and ADR-006 (zero-phase band-pass and
masked-segment policy).

## Padding and phase verification (aggregate, machine-checked)

- All candidates' padding untouched and removed-component-zero-at-padding: **{all_padding_ok}**
- All band-pass/combined candidates' zero-phase (median-trace cross-correlation lag == 0): **{zero_phase_ok}**
  (individual per-trace `peak_sample_shift` values scatter around 0 by chance/noise -- this is expected
  and distinct from the robust median-trace lag; see each candidate's `phase_lag_comparison.csv`.)

## Dewow candidates -- `dewow_candidates/`

| ID | Label | Method | Applied (ns) | Padding OK | Dom freq after (MHz) | Low-freq ratio after |
|---|---|---|---|---|---|---|
{dewow_rows}

See `dewow_candidates/comparison/DEWOW_REVIEW_REQUIRED.md` and
`dewow_candidates/comparison/dewow_candidate_metrics.csv` for the full risk
discussion and metrics.

## Spectrum analysis -- `spectrum/`

Raw canonical spectrum and per-dewow-candidate spectra with QC metrics
(dominant frequency, spectral centroid, -3dB band, energy percentile bands).
See `spectrum/SPECTRUM_INTERPRETATION_NOTES.md` -- these are QC metrics only,
never a physical antenna-band claim.

## Band-pass candidates -- `bandpass_candidates/` (run on dewow base {dewow_base_id})

Using {dewow_base_id} as the common dewow baseline for band-pass comparison
does **not** mean {dewow_base_id} is canonical -- it is a controlled-comparison
choice only.

| ID | Label | Method | Padding OK | Max abs median-trace lag | Dominant freq after (MHz) |
|---|---|---|---|---|---|
{bandpass_rows}

See `bandpass_candidates/comparison/BANDPASS_REVIEW_REQUIRED.md` and
`bandpass_candidates/comparison/bandpass_candidate_metrics.csv`.

## Combined dewow+band-pass candidates -- `combined_candidates/`

Controlled pairs only (dewow window varied with band-pass fixed at B2 for
C1-C3; band-pass varied with dewow fixed at D2 for C4-C6), not an exhaustive
sweep.

| ID | Dewow+Bandpass | Padding OK | Max abs median-trace lag | Dominant freq after (MHz) |
|---|---|---|---|---|
{combined_rows}

See `combined_candidates/comparison/COMBINED_REVIEW_REQUIRED.md` and
`combined_candidates/comparison/combined_candidate_metrics.csv`.

## Images needing human review

- `dewow_candidates/comparison/channel00_all_dewow_candidates.png`
- `dewow_candidates/comparison/all_channel_medians_candidates.png`
- `dewow_candidates/comparison/low_frequency_energy_comparison.png`
- `dewow_candidates/comparison/mean_vs_median_dc_metric_comparison.png`
- `spectrum/raw_canonical_spectrum.png`
- `spectrum/dewow_candidate_spectra.png`
- `bandpass_candidates/comparison/channel00_all_bandpass_candidates.png`
- `bandpass_candidates/comparison/spectra_all_candidates.png`
- `bandpass_candidates/comparison/transfer_functions_all_candidates.png`
- `combined_candidates/comparison/channel00_all_combined_candidates.png`
- `combined_candidates/comparison/combined_spectra.png`

## What this sprint does NOT claim

No candidate here is canonical. No frequency band is claimed to be "the real
antenna band." No candidate is claimed to show archaeological targets better
than another. No anomaly or archaeological interpretation has been made.
Selecting a final dewow window and band-pass range is a human/geophysicist
decision for a future sprint.
"""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "SPRINT3_REVIEW_REQUIRED.md"
    path.write_text(text, encoding="utf-8")
    return path


def run_all_sprint3_candidates(
    npz_path: str | Path,
    output_dir: str | Path,
    *,
    dewow_config_path: str | Path = "configs/dewow_candidates.yaml",
    bandpass_config_path: str | Path = "configs/bandpass_candidates.yaml",
) -> dict[str, Any]:
    """Run every Sprint 3 candidate (dewow, spectrum, band-pass, combined) end to end.

    Reads the Sprint 2 canonical NPZ at ``npz_path`` (never modified), writes
    every candidate's QC suite plus comparison folders under ``output_dir``,
    and finishes with ``output_dir/SPRINT3_REVIEW_REQUIRED.md``. Never selects
    or marks any candidate canonical -- see CLAUDE.md and ADR-005/ADR-006.
    """
    output_dir = Path(output_dir)
    dataset, valid_mask = read_processed_npz(npz_path)

    dewow_config = load_candidates_config(dewow_config_path)
    bandpass_config = load_candidates_config(bandpass_config_path)

    dewow_root = output_dir / "dewow_candidates"
    dewow_info = run_dewow_candidates(dataset, valid_mask, dewow_root, dewow_config)
    dewow_comparison_paths = build_dewow_comparison(
        dataset, valid_mask, dewow_info, dewow_root / "comparison"
    )

    spectrum_paths = run_spectrum_analysis(dataset, valid_mask, dewow_info, output_dir / "spectrum")

    dewow_base_id = bandpass_config["dewow_base_candidate"]
    dewow_base_result = next(info["result"] for info in dewow_info if info["id"] == dewow_base_id)

    bandpass_root = output_dir / "bandpass_candidates"
    bandpass_info = run_bandpass_candidates(dewow_base_result, valid_mask, bandpass_root, bandpass_config)
    bandpass_comparison_paths = build_bandpass_comparison(
        dewow_base_result.dataset, bandpass_info, bandpass_root / "comparison"
    )

    combined_root = output_dir / "combined_candidates"
    combined_info = run_combined_candidates(dewow_info, valid_mask, combined_root, bandpass_config)
    combined_comparison_paths = build_combined_comparison(
        dataset, combined_info, combined_root / "comparison"
    )

    review_path = _write_sprint3_review(output_dir, dewow_info, bandpass_info, combined_info, dewow_base_id)

    return {
        "dataset": dataset,
        "valid_mask": valid_mask,
        "dewow_candidates": dewow_info,
        "dewow_comparison_paths": dewow_comparison_paths,
        "spectrum_paths": spectrum_paths,
        "dewow_base_id": dewow_base_id,
        "bandpass_candidates": bandpass_info,
        "bandpass_comparison_paths": bandpass_comparison_paths,
        "combined_candidates": combined_info,
        "combined_comparison_paths": combined_comparison_paths,
        "review_path": review_path,
    }
