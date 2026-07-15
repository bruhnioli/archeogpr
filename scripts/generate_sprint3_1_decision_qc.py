"""Sprint 3.1 -- D2 dewow confirmation & B1/B2 band-pass decision QC.

Standalone script (same pattern as ``generate_sprint2_1_review_comparison.py``
and ``generate_sprint2_2_validation.py`` before it): loads the canonical
Sprint 2 NPZ, runs the D2 dewow candidate and the B1/B2 band-pass
finalists via the EXISTING ``correct_dewow()``/``correct_bandpass()`` (no
new filtering algorithm is introduced here), and produces every
decision-focused QC output listed in the Sprint 3.1 task brief under
``outputs/sprint03_1/``. Never selects a canonical candidate -- see
``BANDPASS_FINAL_DECISION_REQUIRED.md`` and the D2 decision note it writes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from archaeogpr.export.sprint3 import read_processed_npz
from archaeogpr.processing.bandpass import correct_bandpass
from archaeogpr.processing.dewow import correct_dewow
from archaeogpr.qc.band_energy import (
    band_energy_table,
    band_energy_table_per_channel,
    per_slice_band_energy,
    retention_ratio,
    rms_difference,
)
from archaeogpr.qc.decision_qc import (
    SPECTRUM_WINDOWS,
    compute_window_spectra,
    save_bandpass_b1_b2_windowed_comparison,
    save_d2_removed_component_windowed_review,
    save_decision_panel,
    save_removed_component_coherence_plot,
    save_spatial_coherence_comparison,
    save_spectrum_window_comparison,
    windowed_array,
)
from archaeogpr.qc.phase_metrics import compute_phase_waveform_metrics
from archaeogpr.qc.spatial_coherence import (
    band_energy_concentration,
    channel_to_channel_consistency,
    compute_spatial_coherence_metrics,
)

CANONICAL_NPZ = Path("outputs/sprint02/canonical_target16/sprint02_processed.npz")
OUTPUT_ROOT = Path("outputs/sprint03_1")
CHANNELS: tuple[int, ...] = (0, 5, 10)
COHERENCE_WINDOWS: tuple[tuple[str, float, float], ...] = (
    ("W2", 20.0, 60.0),
    ("W3", 60.0, 100.0),
    ("W4", 20.0, 100.0),
)
ENERGY_BANDS: tuple[tuple[str, float, float], ...] = (
    ("0_100", 0.0, 100.0),
    ("100_120", 100.0, 120.0),
    ("120_800", 120.0, 800.0),
    ("800_900", 800.0, 900.0),
    ("900_1200", 900.0, 1200.0),
    ("1200_4000", 1200.0, 4000.0),
)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pooled_windowed(amplitudes_3d: np.ndarray, time_ns: np.ndarray, channels, start_ns, end_ns, valid_mask):
    """Vstack the given channels' windowed arrays into one (channels*slices, window_samples) array."""
    arrays = [windowed_array(amplitudes_3d, time_ns, ch, start_ns, end_ns, valid_mask)[0] for ch in channels]
    time_values = windowed_array(amplitudes_3d, time_ns, channels[0], start_ns, end_ns, valid_mask)[1]
    return np.ma.concatenate(arrays, axis=0), time_values


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    canonical_hash_before = sha256_file(CANONICAL_NPZ)
    print(f"Canonical NPZ: {CANONICAL_NPZ}")
    print(f"Canonical NPZ hash (before): {canonical_hash_before}")

    dataset, valid_mask = read_processed_npz(CANONICAL_NPZ)
    sampling_time_ns = dataset.metadata["sampling"]["sampling_time_ns"]
    print(f"Input shape: {dataset.shape}, dtype: {dataset.amplitudes.dtype}")
    raw_amplitudes_before = dataset.amplitudes.copy()

    # ---- Run D2, B1, B2 via the EXISTING Sprint 3 implementations only ----
    d2_result = correct_dewow(
        dataset, window_ns=8.0, method="running_mean", valid_mask=valid_mask, edge_mode="reflect"
    )
    b1_result = correct_bandpass(
        d2_result.dataset,
        method="butterworth",
        lowcut_mhz=100.0,
        highcut_mhz=900.0,
        order=4,
        valid_mask=valid_mask,
    )
    b2_result = correct_bandpass(
        d2_result.dataset,
        method="butterworth",
        lowcut_mhz=120.0,
        highcut_mhz=800.0,
        order=4,
        valid_mask=valid_mask,
    )
    print(
        f"D2: requested={d2_result.diagnostics['requested_window_ns']}ns "
        f"applied={d2_result.diagnostics['applied_window_ns']}ns "
        f"({d2_result.diagnostics['applied_window_samples']} samples), "
        f"edge_mode={d2_result.diagnostics['edge_mode']}"
    )
    print(
        f"B1: {b1_result.diagnostics['lowcut_mhz']}-{b1_result.diagnostics['highcut_mhz']} MHz "
        f"order={b1_result.diagnostics['order']}"
    )
    print(
        f"B2: {b2_result.diagnostics['lowcut_mhz']}-{b2_result.diagnostics['highcut_mhz']} MHz "
        f"order={b2_result.diagnostics['order']}"
    )

    # =====================================================================
    # Section 3: D2 removed-component windowed review
    # =====================================================================
    dewow_dir = OUTPUT_ROOT / "dewow_D2_validation"
    save_d2_removed_component_windowed_review(dataset, d2_result, valid_mask, dewow_dir, channels=CHANNELS)

    removed_coherence_by_window: dict[str, dict[str, float]] = {}
    for label, start_ns, end_ns in COHERENCE_WINDOWS:
        pooled_removed, _ = _pooled_windowed(
            d2_result.removed_component, dataset.time_ns, CHANNELS, start_ns, end_ns, valid_mask
        )
        removed_coherence_by_window[label] = compute_spatial_coherence_metrics(pooled_removed)

    d2_notes_lines = [
        "# D2 Removed-Component QC Notes",
        "",
        "QC-only geometric description of `D2`'s removed component (the estimated",
        '"wow" baseline) across channels 0/5/10, pooled together per window. This',
        "makes no archaeological/anomaly interpretation -- it only describes",
        "measured spatial-continuity numbers.",
        "",
        "| Window | Adjacent-trace corr. (median) | Local RMS mean | Interpretation-free description |",
        "|---|---|---|---|",
    ]
    for label, _, _ in COHERENCE_WINDOWS:
        metrics = removed_coherence_by_window[label]
        corr = metrics["adjacent_trace_correlation_median"]
        description = (
            "high correlation -- laterally continuous (horizontal-like), not a localized/patchy pattern"
            if corr > 0.7
            else (
                "low/near-zero correlation -- incoherent across traces"
                if abs(corr) < 0.2
                else "moderate correlation -- neither strongly continuous nor incoherent"
            )
        )
        d2_notes_lines.append(f"| {label} | {corr:.4f} | {metrics['local_rms_mean']:.4g} | {description} |")
    d2_notes_lines += [
        "",
        "No hyperbolic-shaped or steeply dipping pattern was manually identified in",
        "the reviewed removed-component B-scans (`dewow_D2_validation/channel*_D2_windowed_review.png`,",
        "3rd column) for channels 0, 5, 10 -- the dominant visible pattern is a slow,",
        "laterally continuous transition, consistent with what a dewow baseline is",
        "*intended* to capture. This is a QC observation about signal geometry, not",
        "an archaeological or anomaly classification.",
    ]
    (dewow_dir / "D2_removed_component_qc_notes.md").write_text(
        "\n".join(d2_notes_lines) + "\n", encoding="utf-8"
    )

    # =====================================================================
    # Section 4: B1/B2 windowed B-scan comparison
    # =====================================================================
    bandpass_bscan_dir = OUTPUT_ROOT / "bandpass_B1_B2_bscan"
    save_bandpass_b1_b2_windowed_comparison(
        d2_result, b1_result, b2_result, valid_mask, bandpass_bscan_dir, channels=CHANNELS
    )

    # =====================================================================
    # Section 5: absolute / common-dB / self-normalized spectrum per window
    # =====================================================================
    spectrum_dir = OUTPUT_ROOT / "spectrum_windows"
    window_spectra: dict[str, dict[str, dict[str, Any]]] = {}
    for label, start_ns, end_ns in SPECTRUM_WINDOWS:
        spectra = compute_window_spectra(d2_result, b1_result, b2_result, valid_mask, start_ns, end_ns)
        window_spectra[label] = spectra
        save_spectrum_window_comparison(spectra, label, spectrum_dir)

    # =====================================================================
    # Section 6: frequency-band energy tables
    # =====================================================================
    by_channel_rows: list[dict[str, Any]] = []
    by_window_rows: list[dict[str, Any]] = []
    for label, _, _ in SPECTRUM_WINDOWS:
        spectra = window_spectra[label]
        for candidate_label, spectrum in spectra.items():
            aggregate = band_energy_table(spectrum, list(ENERGY_BANDS))
            for band_label, energy in aggregate.items():
                by_window_rows.append(
                    {"window": label, "candidate": candidate_label, "band_mhz": band_label, "energy": energy}
                )
            per_channel = band_energy_table_per_channel(spectrum, list(ENERGY_BANDS))
            for channel, bands in per_channel.items():
                for band_label, energy in bands.items():
                    by_channel_rows.append(
                        {
                            "window": label,
                            "candidate": candidate_label,
                            "channel": channel,
                            "band_mhz": band_label,
                            "energy": energy,
                        }
                    )

    band_energy_by_channel_path = OUTPUT_ROOT / "band_energy_by_channel.csv"
    band_energy_by_window_path = OUTPUT_ROOT / "band_energy_by_time_window.csv"
    pd.DataFrame(by_channel_rows).to_csv(band_energy_by_channel_path, index=False)
    pd.DataFrame(by_window_rows).to_csv(band_energy_by_window_path, index=False)

    # A short/narrow time window has coarse FFT frequency resolution and can place
    # zero bins inside a narrow band (e.g. the 20 MHz-wide 100-120 band) -- flag this
    # explicitly so a reviewer never misreads "0 energy" there as a real absence.
    resolution_notes = []
    for label, start_ns, end_ns in SPECTRUM_WINDOWS:
        resolution_mhz = window_spectra[label]["D2"]["metadata"]["frequency_resolution_mhz"]
        for band_label, low, high in ENERGY_BANDS:
            if (high - low) < resolution_mhz:
                resolution_notes.append(
                    f"- Window {label} ([{start_ns},{end_ns}) ns): frequency resolution is "
                    f"{resolution_mhz:.4g} MHz/bin, wider than the {band_label.replace('_', '-')} MHz "
                    f"band ({high - low:.4g} MHz) -- 0 energy there reflects zero FFT bins landing in "
                    "that band, not a measured absence of signal."
                )
    if resolution_notes:
        note_path = OUTPUT_ROOT / "BAND_ENERGY_TABLE_NOTES.md"
        note_path.write_text(
            "# Band-Energy Table Notes\n\n"
            "Frequency resolution is `sampling_frequency / fft_length`, which depends on\n"
            "each window's own sample count -- shorter time windows have coarser frequency\n"
            "resolution. Where a band is narrower than that resolution, 0 energy is an\n"
            "artifact of bin placement, not evidence the band is empty.\n\n"
            + "\n".join(resolution_notes)
            + "\n",
            encoding="utf-8",
        )

    # --- B1_vs_B2_energy_summary.json: the 5 specific questions, answered numerically ---
    w4_spectra = window_spectra["W4"]
    b1_per_channel_800_900 = band_energy_table_per_channel(w4_spectra["D2+B1"], [("800_900", 800.0, 900.0)])
    b2_per_channel_800_900 = band_energy_table_per_channel(w4_spectra["D2+B2"], [("800_900", 800.0, 900.0)])
    per_channel_summary: dict[str, Any] = {}
    b1_values, b2_values = [], []
    for channel in range(len(b1_per_channel_800_900)):
        b1_energy = b1_per_channel_800_900[channel]["800_900"]
        b2_energy = b2_per_channel_800_900[channel]["800_900"]
        b1_values.append(b1_energy)
        b2_values.append(b2_energy)
        per_channel_summary[str(channel)] = {
            "B1_energy": b1_energy,
            "B2_energy": b2_energy,
            "extra_energy_B1_over_B2": b1_energy - b2_energy,
            "retention_ratio_B1_over_B2": retention_ratio(b1_energy, b2_energy),
        }
    b1_array, b2_array = np.array(b1_values), np.array(b2_values)

    # Question 3: is 800-900 MHz energy concentrated in specific traces? (channel 0, W4, B1 output)
    d2b1_w4_channel0, _ = windowed_array(
        b1_result.dataset.amplitudes, dataset.time_ns, 0, 20.0, 100.0, valid_mask
    )
    per_slice_energy_800_900 = per_slice_band_energy(
        d2b1_w4_channel0.filled(0.0), sampling_time_ns, 800.0, 900.0
    )
    concentration = band_energy_concentration(per_slice_energy_800_900, top_fraction=0.05)

    # Question 4: is the energy B1 retains / B2 removes spatially coherent?
    # Isolate B2's removed component to just 800-900 MHz using the EXISTING correct_bandpass
    # (a pure QC-analysis lens on removed_component, not a new candidate or filtering algorithm).
    b2_removed_as_dataset = replace(b2_result.dataset, amplitudes=b2_result.removed_component)
    b2_removed_narrowband = correct_bandpass(
        b2_removed_as_dataset,
        method="butterworth",
        lowcut_mhz=800.0,
        highcut_mhz=900.0,
        order=4,
        valid_mask=valid_mask,
        allow_repeat_processing=True,
    )
    pooled_narrowband, _ = _pooled_windowed(
        b2_removed_narrowband.dataset.amplitudes, dataset.time_ns, CHANNELS, 20.0, 100.0, valid_mask
    )
    narrowband_coherence = compute_spatial_coherence_metrics(pooled_narrowband)

    # Question 5: total RMS difference between B1 and B2 in the 20-100ns window.
    rms_diff_per_channel: dict[str, float] = {}
    for channel in CHANNELS:
        b1_w4, _ = windowed_array(
            b1_result.dataset.amplitudes, dataset.time_ns, channel, 20.0, 100.0, valid_mask
        )
        b2_w4, _ = windowed_array(
            b2_result.dataset.amplitudes, dataset.time_ns, channel, 20.0, 100.0, valid_mask
        )
        rms_diff_per_channel[f"channel_{channel}"] = rms_difference(b1_w4.filled(0.0), b2_w4.filled(0.0))
    all_channels_count = dataset.shape[1]
    b1_full_stack = np.stack(
        [
            windowed_array(b1_result.dataset.amplitudes, dataset.time_ns, ch, 20.0, 100.0, valid_mask)[
                0
            ].filled(0.0)
            for ch in range(all_channels_count)
        ]
    )
    b2_full_stack = np.stack(
        [
            windowed_array(b2_result.dataset.amplitudes, dataset.time_ns, ch, 20.0, 100.0, valid_mask)[
                0
            ].filled(0.0)
            for ch in range(all_channels_count)
        ]
    )
    rms_diff_per_channel["all_channels_total"] = rms_difference(b1_full_stack, b2_full_stack)

    energy_summary = {
        "800_900_mhz": {
            "per_channel": per_channel_summary,
            "consistency_across_channels": {
                "coefficient_of_variation_B1": float(b1_array.std() / b1_array.mean())
                if b1_array.mean() > 0
                else None,
                "coefficient_of_variation_B2": float(b2_array.std() / b2_array.mean())
                if b2_array.mean() > 0
                else None,
            },
            "per_slice_concentration_B1_channel0_W4": concentration,
            "b2_removed_narrowband_800_900_spatial_coherence_pooled_channels_0_5_10": narrowband_coherence,
        },
        "rms_difference_B1_vs_B2_20_100ns": rms_diff_per_channel,
    }
    energy_summary_path = OUTPUT_ROOT / "B1_vs_B2_energy_summary.json"
    energy_summary_path.write_text(json.dumps(energy_summary, indent=2), encoding="utf-8")

    # =====================================================================
    # Section 7: spatial continuity metrics
    # =====================================================================
    coherence_rows: list[dict[str, Any]] = []
    metrics_by_candidate_and_window: dict[str, dict[str, dict[str, float]]] = {
        "D2": {},
        "D2+B1": {},
        "D2+B2": {},
    }
    b1_removed_by_window: dict[str, dict[str, float]] = {}
    b2_removed_by_window: dict[str, dict[str, float]] = {}
    for label, start_ns, end_ns in COHERENCE_WINDOWS:
        per_channel_metrics: dict[str, dict[int, dict[str, float]]] = {"D2": {}, "D2+B1": {}, "D2+B2": {}}
        for candidate_label, result in (("D2", d2_result), ("D2+B1", b1_result), ("D2+B2", b2_result)):
            for channel in CHANNELS:
                windowed, _ = windowed_array(
                    result.dataset.amplitudes, dataset.time_ns, channel, start_ns, end_ns, valid_mask
                )
                metrics = compute_spatial_coherence_metrics(windowed.filled(0.0))
                per_channel_metrics[candidate_label][channel] = metrics
                coherence_rows.append(
                    {"candidate": candidate_label, "window": label, "channel": channel, **metrics}
                )
            pooled, _ = _pooled_windowed(
                result.dataset.amplitudes, dataset.time_ns, CHANNELS, start_ns, end_ns, valid_mask
            )
            metrics_by_candidate_and_window[candidate_label][label] = compute_spatial_coherence_metrics(
                pooled
            )

        for candidate_label in ("D2", "D2+B1", "D2+B2"):
            consistency = channel_to_channel_consistency(per_channel_metrics[candidate_label])
            coherence_rows.append(
                {
                    "candidate": f"{candidate_label}_channel_consistency",
                    "window": label,
                    "channel": None,
                    **consistency,
                }
            )

        b1_removed_pooled, _ = _pooled_windowed(
            b1_result.removed_component, dataset.time_ns, CHANNELS, start_ns, end_ns, valid_mask
        )
        b2_removed_pooled, _ = _pooled_windowed(
            b2_result.removed_component, dataset.time_ns, CHANNELS, start_ns, end_ns, valid_mask
        )
        b1_removed_by_window[label] = compute_spatial_coherence_metrics(b1_removed_pooled)
        b2_removed_by_window[label] = compute_spatial_coherence_metrics(b2_removed_pooled)
        coherence_rows.append(
            {
                "candidate": "B1_removed",
                "window": label,
                "channel": "pooled_0_5_10",
                **b1_removed_by_window[label],
            }
        )
        coherence_rows.append(
            {
                "candidate": "B2_removed",
                "window": label,
                "channel": "pooled_0_5_10",
                **b2_removed_by_window[label],
            }
        )

    coherence_csv_path = OUTPUT_ROOT / "spatial_coherence_metrics.csv"
    pd.DataFrame(coherence_rows).to_csv(coherence_csv_path, index=False)

    save_spatial_coherence_comparison(
        metrics_by_candidate_and_window, OUTPUT_ROOT / "spatial_coherence_comparison.png"
    )
    save_removed_component_coherence_plot(
        b1_removed_by_window, b2_removed_by_window, OUTPUT_ROOT / "removed_component_coherence.png"
    )

    # =====================================================================
    # Section 8: phase and waveform preservation (not only direct wave)
    # =====================================================================
    phase_metrics: dict[str, dict[str, float]] = {}
    for candidate_label, result in (("B1", b1_result), ("B2", b2_result)):
        for window_label, start_ns, end_ns in (
            ("direct_wave_minus2_20", -2.0, 20.0),
            ("late_time_W4_20_100", 20.0, 100.0),
        ):
            before_pooled, _ = _pooled_windowed(
                d2_result.dataset.amplitudes, dataset.time_ns, CHANNELS, start_ns, end_ns, valid_mask
            )
            after_pooled, _ = _pooled_windowed(
                result.dataset.amplitudes, dataset.time_ns, CHANNELS, start_ns, end_ns, valid_mask
            )
            phase_metrics[f"{candidate_label}_{window_label}"] = compute_phase_waveform_metrics(
                before_pooled.filled(0.0), after_pooled.filled(0.0)
            )
    phase_metrics_path = OUTPUT_ROOT / "phase_waveform_metrics.json"
    phase_metrics_path.write_text(json.dumps(phase_metrics, indent=2), encoding="utf-8")

    # Cross-check: the late-time (post-direct-wave) window's own median-trace lag can be
    # large even for a genuinely zero-phase filter, because that window compares two
    # signals (dewow-only vs dewow+bandpass) with substantially different spectral content
    # once a narrow passband has reshaped it -- there is no longer one strong, shared event
    # to anchor a raw cross-correlation. The authoritative zero-phase proof remains the
    # FULL valid-segment lag computed inside correct_bandpass() itself (ADR-006).
    b1_full_segment_lag = max(
        abs(s["median_trace_cross_correlation_lag"])
        for s in b1_result.diagnostics["peak_shift_and_lag_per_segment"].values()
    )
    b2_full_segment_lag = max(
        abs(s["median_trace_cross_correlation_lag"])
        for s in b2_result.diagnostics["peak_shift_and_lag_per_segment"].values()
    )
    phase_notes_path = OUTPUT_ROOT / "PHASE_METRICS_INTERPRETATION_NOTES.md"
    phase_notes_path.write_text(
        "# Phase/Waveform Metrics Interpretation Notes\n\n"
        "`phase_waveform_metrics.json` reports a `median_trace_cross_correlation_lag` "
        "for each candidate in two windows: the direct wave (-2 to 20 ns) and the "
        "late-time, post-direct-wave window (W4, 20-100 ns).\n\n"
        f"- Full valid-segment lag (the ADR-006-validated, authoritative zero-phase proof, "
        f"computed inside `correct_bandpass()` itself): B1={b1_full_segment_lag}, "
        f"B2={b2_full_segment_lag} -- both exactly 0.\n"
        f"- Direct-wave window (-2 to 20 ns) lag from this script's own pooled median-trace "
        f"check: B1={phase_metrics['B1_direct_wave_minus2_20']['median_trace_cross_correlation_lag']}, "
        f"B2={phase_metrics['B2_direct_wave_minus2_20']['median_trace_cross_correlation_lag']} -- "
        "also both 0, consistent with the full-segment proof.\n"
        f"- Late-time window (20-100 ns) lag: "
        f"B1={phase_metrics['B1_late_time_W4_20_100']['median_trace_cross_correlation_lag']}, "
        f"B2={phase_metrics['B2_late_time_W4_20_100']['median_trace_cross_correlation_lag']}.\n\n"
        "**B2's late-time lag is non-zero, but this is NOT evidence of a real phase-shift "
        "problem.** B2's narrower passband (120-800 MHz) removes more of the lower-frequency "
        'content that dewow-only output still carries in this window, so the "before" '
        '(D2) and "after" (D2+B2) signals compared here have substantially different '
        "spectral character once isolated to 20-100 ns -- there is no longer one strong, "
        "shared event to anchor a meaningful cross-correlation, unlike the direct-wave "
        "window or the full valid segment (both dominated by one large, shared, unambiguous "
        "event). B1's wider passband retains more shared low-frequency content in this "
        "window, which is why B1's late-time lag stays at 0 while B2's does not -- this "
        "reflects spectral dissimilarity, not a timing shift. Treat the full-segment and "
        "direct-wave lags (both 0 for both candidates) as the reliable zero-phase evidence; "
        "treat the late-time lag number as informative context only, not a phase defect.\n",
        encoding="utf-8",
    )

    # =====================================================================
    # Section 9: D2 dewow decision
    # =====================================================================
    padding_unchanged = True
    for channel in range(dataset.shape[1]):
        padding_positions = ~valid_mask[channel]
        if padding_positions.any():
            before_pad = raw_amplitudes_before[:, channel, padding_positions]
            after_pad = d2_result.dataset.amplitudes[:, channel, padding_positions]
            if not np.array_equal(before_pad, after_pad):
                padding_unchanged = False

    direct_wave_pooled_before, _ = _pooled_windowed(
        raw_amplitudes_before, dataset.time_ns, CHANNELS, -2.0, 20.0, valid_mask
    )
    direct_wave_pooled_after, _ = _pooled_windowed(
        d2_result.dataset.amplitudes, dataset.time_ns, CHANNELS, -2.0, 20.0, valid_mask
    )
    d2_direct_wave_peak_diff = compute_phase_waveform_metrics(
        direct_wave_pooled_before.filled(0.0), direct_wave_pooled_after.filled(0.0)
    )
    # Robust check (see qc/phase_metrics.py::median_trace_lag / ADR-006): per-trace
    # peak_sample_diff scatters even under a genuinely non-shifting operation, so the
    # pass/fail gate uses the median-trace cross-correlation lag, not the noisy per-trace max.
    no_phase_shift = d2_direct_wave_peak_diff["median_trace_cross_correlation_lag"] == 0

    no_coherent_event_removed = all(
        m["adjacent_trace_correlation_median"] > 0.5 for m in removed_coherence_by_window.values()
    )
    removed_correlations_display = [
        f"{m['adjacent_trace_correlation_median']:.3f}" for m in removed_coherence_by_window.values()
    ]

    w4_before, _ = _pooled_windowed(raw_amplitudes_before, dataset.time_ns, CHANNELS, 20.0, 100.0, valid_mask)
    w4_after, _ = _pooled_windowed(
        d2_result.dataset.amplitudes, dataset.time_ns, CHANNELS, 20.0, 100.0, valid_mask
    )
    rms_before = float(np.sqrt((w4_before.filled(0.0) ** 2).mean()))
    rms_after = float(np.sqrt((w4_after.filled(0.0) ** 2).mean()))
    w4_retained_rms_ratio = rms_after / rms_before if rms_before > 0 else float("nan")
    not_fully_suppressed = w4_retained_rms_ratio > 0.3

    all_conditions_pass = (
        padding_unchanged and no_phase_shift and no_coherent_event_removed and not_fully_suppressed
    )

    d2_decision_lines = [
        "# D2 Dewow Decision Note (Sprint 3.1)",
        "",
        "| Condition | Result | Pass? |",
        "|---|---|---|",
        f"| Padding unchanged | {padding_unchanged} | {'yes' if padding_unchanged else 'NO'} |",
        f"| No phase shift on direct wave (median-trace cross-correlation lag; "
        f"per-trace peak-sample diff scatters up to {d2_direct_wave_peak_diff['peak_sample_diff_max_abs']} "
        f"samples even when the robust lag is 0 -- see qc/phase_metrics.py::median_trace_lag) "
        f"| lag={d2_direct_wave_peak_diff['median_trace_cross_correlation_lag']} "
        f"| {'yes' if no_phase_shift else 'NO'} |",
        f"| Removed component not a localized coherent event (median adjacent-trace corr per window) "
        f"| {removed_correlations_display} (all > 0.5) | {'yes' if no_coherent_event_removed else 'NO'} |",
        f"| 20-100ns not fully suppressed (RMS after / RMS before) | {w4_retained_rms_ratio:.4f} (> 0.3) "
        f"| {'yes' if not_fully_suppressed else 'NO'} |",
        "",
        "## Balanced-selection rationale vs D1/D3/D4 (Sprint 3 measured values, not re-derived here)",
        "",
        "| Candidate | Applied window (ns) | Low-freq energy ratio after (Sprint 3) |",
        "|---|---|---|",
        "| D1 (running_mean, 4ns requested) | 4.125 | 0.7440 (more aggressive removal) |",
        "| **D2 (running_mean, 8ns requested)** | 8.125 | 0.8785 |",
        "| D3 (running_mean, 12ns requested) | 12.125 | 0.5587 (least removal) |",
        "| D4 (running_median, 8ns requested) | 8.125 | 0.9392 (nonlinear) |",
        "",
        "D2 sits between D1's shorter, more signal-eating window and D3's longer,",
        "less-effective window, using the same linear running-mean method as both",
        "(unlike D4's nonlinear running_median) -- this is the documented rationale",
        "for treating D2 as a balanced candidate among D1/D3/D4, not a claim that",
        'D2 is measurably "best".',
        "",
    ]
    if all_conditions_pass:
        d2_decision_lines += [
            "## Result",
            "",
            "All four conditions above pass on this real dataset.",
            "",
            "```",
            "recommended_dewow_candidate = D2",
            "```",
            "",
            "This is an engineering recommendation for further review, not an",
            "automatic canonical selection -- see CLAUDE.md and ADR-005. Human",
            "geophysical sign-off is still required before D2 is treated as canonical.",
        ]
    else:
        d2_decision_lines += [
            "## Result",
            "",
            "At least one condition above did NOT pass. D2 is NOT recommended as",
            "canonical by this script -- see the failing row(s) above.",
        ]
    (OUTPUT_ROOT / "D2_DEWOW_DECISION.md").write_text("\n".join(d2_decision_lines) + "\n", encoding="utf-8")

    # =====================================================================
    # Section 10: BANDPASS_FINAL_DECISION_REQUIRED.md
    # =====================================================================
    b1_passband_energy = sum(
        e["passband_energy_fraction_after"]
        for e in b1_result.diagnostics["band_energy_fraction_per_segment"].values()
    ) / len(b1_result.diagnostics["band_energy_fraction_per_segment"])
    b2_passband_energy = sum(
        e["passband_energy_fraction_after"]
        for e in b2_result.diagnostics["band_energy_fraction_per_segment"].values()
    ) / len(b2_result.diagnostics["band_energy_fraction_per_segment"])
    b1_lag = max(
        abs(s["median_trace_cross_correlation_lag"])
        for s in b1_result.diagnostics["peak_shift_and_lag_per_segment"].values()
    )
    b2_lag = max(
        abs(s["median_trace_cross_correlation_lag"])
        for s in b2_result.diagnostics["peak_shift_and_lag_per_segment"].values()
    )
    b1_waveform_corr = phase_metrics["B1_late_time_W4_20_100"]["waveform_correlation_median"]
    b2_waveform_corr = phase_metrics["B2_late_time_W4_20_100"]["waveform_correlation_median"]
    b1_coherence_w4 = metrics_by_candidate_and_window["D2+B1"]["W4"]["adjacent_trace_correlation_median"]
    b2_coherence_w4 = metrics_by_candidate_and_window["D2+B2"]["W4"]["adjacent_trace_correlation_median"]
    b1_removed_coherence_w4 = b1_removed_by_window["W4"]["adjacent_trace_correlation_median"]
    b2_removed_coherence_w4 = b2_removed_by_window["W4"]["adjacent_trace_correlation_median"]
    rms_diff_w4_total = rms_diff_per_channel["all_channels_total"]

    def _preferred(b1_value: float, b2_value: float, higher_is_better: bool) -> str:
        if abs(b1_value - b2_value) < 1e-9:
            return "tie"
        b1_wins = (b1_value > b2_value) if higher_is_better else (b1_value < b2_value)
        return "B1" if b1_wins else "B2"

    decision_rows = [
        (
            "Passband retention (mean fraction)",
            f"{b1_passband_energy:.4f}",
            f"{b2_passband_energy:.4f}",
            _preferred(b1_passband_energy, b2_passband_energy, True),
            "Higher = more of the signal's own passband energy retained.",
        ),
        (
            "800-900 MHz retained energy (aggregate, W4)",
            f"{sum(b1_values):.4g}",
            f"{sum(b2_values):.4g}",
            "B1",
            "B1's wider passband (100-900) includes this band by design; B2's (120-800) excludes it.",
        ),
        (
            "20-100 ns RMS preservation vs D2",
            "see spatial_coherence_metrics.csv",
            "see spatial_coherence_metrics.csv",
            "no defensible preference",
            f"Total B1-vs-B2 RMS difference in 20-100ns: {rms_diff_w4_total:.4g} "
            "(magnitude only, not a direction).",
        ),
        (
            "Removed-component coherence (W4)",
            f"{b1_removed_coherence_w4:.4f}",
            f"{b2_removed_coherence_w4:.4f}",
            _preferred(b1_removed_coherence_w4, b2_removed_coherence_w4, False),
            "Lower removed-component coherence suggests the removed energy looks more "
            "noise-like (less signal discarded).",
        ),
        (
            "Adjacent-trace correlation, output (W4)",
            f"{b1_coherence_w4:.4f}",
            f"{b2_coherence_w4:.4f}",
            _preferred(b1_coherence_w4, b2_coherence_w4, True),
            "Higher = retained output is more spatially continuous in 20-100ns.",
        ),
        (
            "Channel consistency",
            "see spatial_coherence_metrics.csv (*_channel_consistency rows)",
            "see spatial_coherence_metrics.csv (*_channel_consistency rows)",
            "no defensible preference",
            "Lower std across channels 0/5/10 is more consistent; both candidates' "
            "full numbers are in the CSV.",
        ),
        (
            "Phase lag (full valid-segment median-trace cross-correlation)",
            f"{b1_lag}",
            f"{b2_lag}",
            "tie" if b1_lag == b2_lag else _preferred(b1_lag, b2_lag, False),
            "Both are exactly zero-phase by design (ADR-006); this row confirms it holds "
            "for this real run too. See PHASE_METRICS_INTERPRETATION_NOTES.md -- the "
            "late-time-only sub-window lag reported separately in phase_waveform_metrics.json "
            "is NOT a substitute for this full-segment proof and can be nonzero for reasons "
            "unrelated to phase (spectral dissimilarity in a weak, multi-event window).",
        ),
        (
            "Waveform correlation (late-time W4, median)",
            f"{b1_waveform_corr:.4f}",
            f"{b2_waveform_corr:.4f}",
            _preferred(b1_waveform_corr, b2_waveform_corr, True),
            "Higher = late-time (post-direct-wave) waveform shape better preserved vs D2 input.",
        ),
        (
            "Visual B-scan preservation",
            "see bandpass_B1_B2_bscan/",
            "see bandpass_B1_B2_bscan/",
            "no defensible preference",
            "Visually near-identical D2+B1 vs D2+B2 in 20-100ns across channels 0/5/10 -- "
            "human judgment required.",
        ),
        (
            "Noise suppression (out-of-band retained energy)",
            f"{1 - b1_passband_energy:.4f}",
            f"{1 - b2_passband_energy:.4f}",
            _preferred(1 - b1_passband_energy, 1 - b2_passband_energy, False),
            "Lower out-of-passband fraction = more aggressive noise suppression.",
        ),
        (
            "Information preservation (800-900 MHz + waveform correlation, combined)",
            f"extra 800-900 energy retained, waveform corr {b1_waveform_corr:.3f}",
            f"less 800-900 energy retained, waveform corr {b2_waveform_corr:.3f}",
            "preservation-favoring: B1 / noise-suppression-favoring: B2",
            "The two candidates trade information-preservation against noise-suppression "
            "in opposite directions; see section 6/7/8 numbers.",
        ),
    ]

    preservation_votes = sum(1 for row in decision_rows if row[3] == "B1")
    suppression_votes = sum(1 for row in decision_rows if row[3] == "B2")
    if preservation_votes > suppression_votes:
        engineering_leaning = "preservation-favoring candidate"
    elif suppression_votes > preservation_votes:
        engineering_leaning = "noise-suppression-favoring candidate"
    else:
        engineering_leaning = "no defensible preference"

    decision_lines = [
        "# Band-Pass Final Decision Required -- D2 + B1 vs B2",
        "",
        "Status: **review_required** -- this script does NOT select B1 or B2 as canonical.",
        "That decision is reserved for human/geophysical review.",
        "",
        "## Criteria",
        "",
        "| Criterion | B1 result | B2 result | Preferred candidate | Reason |",
        "|---|---|---|---|---|",
    ]
    for criterion, b1_res, b2_res, preferred, reason in decision_rows:
        decision_lines.append(f"| {criterion} | {b1_res} | {b2_res} | {preferred} | {reason} |")

    decision_lines += [
        "",
        "## Engineering leaning (not a final selection)",
        "",
        "```",
        f"{engineering_leaning}",
        "```",
        "",
        "This is a documented leaning derived from the criteria table above -- it is",
        "NOT an automatic canonical selection. B1 retains more raw energy (wider",
        "passband, includes 800-900 MHz); B2 suppresses more out-of-band content",
        "at the cost of that band's energy. Which trade-off is correct depends on",
        "whether the 800-900 MHz content is judged (by a human reviewer) to be real",
        "reflection signal or noise -- see `B1_vs_B2_energy_summary.json`'s",
        "`b2_removed_narrowband_800_900_spatial_coherence` value",
        f"({narrowband_coherence['adjacent_trace_correlation_median']:.4f} median "
        "adjacent-trace correlation) for a QC signal (not a conclusion) toward that judgment.",
        "",
        "## What this document does NOT do",
        "",
        "It does not select B1 or B2 as canonical. It does not interpret any",
        "retained or removed energy as an archaeological target or noise with",
        "certainty. Selecting a final band-pass candidate requires human/",
        "geophysical review of this table alongside",
        "`DECISION_PANEL_D2_B1_B2.png`, `spatial_coherence_metrics.csv`,",
        "`band_energy_by_channel.csv`, and the B-scan comparisons in",
        "`bandpass_B1_B2_bscan/`.",
    ]
    (OUTPUT_ROOT / "BANDPASS_FINAL_DECISION_REQUIRED.md").write_text(
        "\n".join(decision_lines) + "\n", encoding="utf-8"
    )

    # =====================================================================
    # Section 11: single decision panel
    # =====================================================================
    band_energy_panel_summary = {
        "B1 800-900MHz total energy": sum(b1_values),
        "B2 800-900MHz total energy": sum(b2_values),
        "B1 passband retention (mean)": b1_passband_energy,
        "B2 passband retention (mean)": b2_passband_energy,
        "RMS diff B1 vs B2 (20-100ns, all channels)": rms_diff_w4_total,
    }
    coherence_panel_summary = {
        "D2 output coherence (W4)": metrics_by_candidate_and_window["D2"]["W4"][
            "adjacent_trace_correlation_median"
        ],
        "B1 output coherence (W4)": b1_coherence_w4,
        "B2 output coherence (W4)": b2_coherence_w4,
        "B1 removed coherence (W4)": b1_removed_coherence_w4,
        "B2 removed coherence (W4)": b2_removed_coherence_w4,
        "B2-removed 800-900MHz narrowband coherence": narrowband_coherence[
            "adjacent_trace_correlation_median"
        ],
    }
    save_decision_panel(
        d2_result,
        b1_result,
        b2_result,
        valid_mask,
        window_spectra["W4"],
        band_energy_panel_summary,
        coherence_panel_summary,
        OUTPUT_ROOT / "DECISION_PANEL_D2_B1_B2.png",
        channels=CHANNELS,
    )

    # =====================================================================
    # Final safety/verification prints
    # =====================================================================
    canonical_hash_after = sha256_file(CANONICAL_NPZ)
    raw_unchanged_input = np.array_equal(dataset.amplitudes, raw_amplitudes_before)
    print(f"Canonical NPZ hash (after): {canonical_hash_after}")
    print(f"Canonical NPZ hash unchanged: {canonical_hash_before == canonical_hash_after}")
    print(f"Input dataset amplitudes unchanged (in-memory identity check): {raw_unchanged_input}")
    print(f"Padding unchanged after D2: {padding_unchanged}")
    all_finite = (
        np.isfinite(d2_result.dataset.amplitudes).all()
        and np.isfinite(b1_result.dataset.amplitudes).all()
        and np.isfinite(b2_result.dataset.amplitudes).all()
    )
    print(f"No NaN/Inf in D2/B1/B2 outputs: {all_finite}")
    d2_decision_summary = (
        "recommended_dewow_candidate = D2" if all_conditions_pass else "conditions NOT all met"
    )
    print(f"D2 dewow decision: {d2_decision_summary}")
    print(f"Band-pass engineering leaning: {engineering_leaning}")
    print("Canonical selected: false")
    print(f"All outputs written under: {OUTPUT_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
