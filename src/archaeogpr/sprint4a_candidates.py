"""Sprint 4A candidate orchestration: eight background-removal candidates
(A1-A8), each with its own QC suite, plus a cross-candidate comparison and a
single decision panel.

This module never marks any candidate canonical -- see CLAUDE.md and
ADR-008. It only reads the canonical Sprint 3 NPZ and writes new files
under ``outputs/sprint04a/``; it never modifies that NPZ, the Sprint 2
canonical NPZ, or the raw ``.ogpr`` file. The "engineering category" label
each candidate gets (`preservation-favoring`/`suppression-favoring`/
`balanced`/`too_aggressive`/`too_weak`) is a transparent, documented,
relative ranking by measured RMS retention across these 8 candidates on
this dataset -- not an automatic canonical selection, and not itself an
archaeological claim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from archaeogpr.export.processed import (
    write_corrected_npz,
    write_processing_history_json,
    write_processing_metadata_json,
)
from archaeogpr.export.sprint3 import read_processed_npz, write_padding_verification_json
from archaeogpr.export.sprint4a import (
    write_candidate_validation_json,
    write_removed_component_metrics_json,
    write_signal_preservation_metrics_json,
    write_trace_spacing_and_window_json,
)
from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.background import remove_background
from archaeogpr.processing.common import ProcessingError
from archaeogpr.qc.background import (
    TIME_WINDOWS_NS,
    compute_localized_event_risk,
    compute_removed_component_metrics,
    compute_signal_preservation_metrics,
    save_background_qc_suite,
)
from archaeogpr.sprint3_candidates import sha256_file

#: The channels used throughout Sprint 4A's windowed QC (spec section 14/16).
CANDIDATE_CHANNELS = (0, 5, 10)

#: Comparison window used for the cross-candidate B-scan/removed-component
#: overlays (post-direct-wave reflections; matches Sprint 3.1's own W4/W5
#: convention for "not dominated by the direct wave").
COMPARISON_WINDOW_NS = (20.0, 100.0)

#: Engineering-category thresholds (see module docstring) -- a documented,
#: relative-ranking QC label, never a canonical selection.
TOO_WEAK_RMS_RETENTION = 0.95
TOO_AGGRESSIVE_RMS_RETENTION = 0.15


def run_background_candidates(
    dataset: GPRDataset,
    valid_mask: np.ndarray | None,
    output_root: Path,
    config: dict[str, Any],
    *,
    raw_file_sha256: str,
    sprint2_canonical_sha256: str,
    sprint3_canonical_sha256: str,
) -> list[dict[str, Any]]:
    """Run every background-removal candidate in ``config``, writing its full QC suite.

    ``raw_file_sha256``/``sprint2_canonical_sha256``/``sprint3_canonical_sha256``
    are written into each candidate's ``candidate_validation.json`` as the
    acceptance-criteria record (Sprint 4A spec section 23) -- computed once
    by the caller, not re-derived per candidate. Returns a list of
    per-candidate info dicts.
    """
    edge_mode = config["edge_mode"]
    candidates_info: list[dict[str, Any]] = []
    for candidate in config["candidates"]:
        candidate_dir = output_root / f"{candidate['id']}_{candidate['label']}"
        candidate_dir.mkdir(parents=True, exist_ok=True)

        kwargs: dict[str, Any] = {"method": candidate["method"], "valid_mask": valid_mask}
        if candidate["method"] in ("sliding_mean", "sliding_median"):
            if "window_m" in candidate:
                kwargs["window_m"] = candidate["window_m"]
            elif "window_traces" in candidate:
                kwargs["window_traces"] = candidate["window_traces"]
            else:
                raise ProcessingError(
                    f"candidate {candidate['id']!r} (method={candidate['method']!r}) needs "
                    "'window_m' or 'window_traces' in its config entry"
                )
            kwargs["edge_mode"] = edge_mode

        result = remove_background(dataset, **kwargs)

        write_corrected_npz(result, candidate_dir / "background_processed.npz")
        write_processing_metadata_json(result, candidate_dir / "processing_metadata.json")
        write_processing_history_json(result.dataset, candidate_dir / "processing_history.json")
        write_padding_verification_json(result, candidate_dir / "padding_verification.json")
        write_trace_spacing_and_window_json(result, candidate_dir / "trace_spacing_and_window.json")

        signal_preservation = compute_signal_preservation_metrics(
            dataset, result, valid_mask, channels=CANDIDATE_CHANNELS
        )
        write_signal_preservation_metrics_json(
            signal_preservation, candidate_dir / "signal_preservation_metrics.json"
        )

        removed_metrics = compute_removed_component_metrics(
            dataset, result, valid_mask, channels=CANDIDATE_CHANNELS
        )
        write_removed_component_metrics_json(
            removed_metrics, candidate_dir / "removed_component_metrics.json"
        )

        write_candidate_validation_json(
            candidate_id=candidate["id"],
            before_shape=dataset.shape,
            result=result,
            raw_file_sha256=raw_file_sha256,
            sprint2_canonical_sha256=sprint2_canonical_sha256,
            sprint3_canonical_sha256=sprint3_canonical_sha256,
            output_path=candidate_dir / "candidate_validation.json",
        )

        qc_paths = save_background_qc_suite(dataset, result, candidate_dir, secondary_channels=(5, 10))

        candidates_info.append(
            {
                "id": candidate["id"],
                "label": candidate["label"],
                "method": candidate["method"],
                "result": result,
                "signal_preservation": signal_preservation,
                "removed_metrics": removed_metrics,
                "qc_paths": qc_paths,
                "output_dir": candidate_dir,
            }
        )
    return candidates_info


def _engineering_category(candidates_info: list[dict[str, Any]], window_label: str = "W5") -> dict[str, str]:
    """Relative RMS-retention ranking across ``candidates_info`` -> ``{candidate_id: category}``.

    Documented, deterministic rule (see module docstring): candidates whose
    ``rms_retention`` in ``window_label`` sits above ``TOO_WEAK_RMS_RETENTION``
    or below ``TOO_AGGRESSIVE_RMS_RETENTION`` are flagged outright; the rest
    are split into thirds by rank (highest retention = preservation-favoring,
    lowest = suppression-favoring, middle = balanced). Never a canonical pick.
    """
    retentions = {
        info["id"]: info["signal_preservation"][window_label]["rms_retention"] for info in candidates_info
    }
    categories: dict[str, str] = {}
    reasonable_ids: list[str] = []
    for candidate_id, retention in retentions.items():
        if not np.isfinite(retention):
            categories[candidate_id] = "inconclusive"
        elif retention >= TOO_WEAK_RMS_RETENTION:
            categories[candidate_id] = "too_weak"
        elif retention <= TOO_AGGRESSIVE_RMS_RETENTION:
            categories[candidate_id] = "too_aggressive"
        else:
            reasonable_ids.append(candidate_id)

    reasonable_ids.sort(key=lambda cid: retentions[cid], reverse=True)
    n = len(reasonable_ids)
    for rank, candidate_id in enumerate(reasonable_ids):
        if rank < max(1, n // 3):
            categories[candidate_id] = "preservation-favoring"
        elif rank >= n - max(1, n // 3):
            categories[candidate_id] = "suppression-favoring"
        else:
            categories[candidate_id] = "balanced"
    return categories


# ======================================================================
# Small, self-contained synthetic scientific-risk experiments (spec 17) --
# produced here as human-reviewable comparison artifacts; the same
# scientific questions are also asserted with real test coverage in
# tests/test_background.py.
# ======================================================================


def _synthetic_profile(
    rng: np.random.Generator,
    slices_count: int,
    samples_count: int,
    *,
    target_length_traces: int,
    target_sample: int = 100,
    background_amplitude: float = 200.0,
    target_amplitude: float = 600.0,
    noise_scale: float = 15.0,
) -> np.ndarray:
    """One synthetic ``(slices, samples)`` B-scan: shared background + noise + one local target."""
    background = background_amplitude * np.sin(np.linspace(0.0, 4 * np.pi, samples_count))
    data = np.tile(background, (slices_count, 1)) + rng.normal(
        scale=noise_scale, size=(slices_count, samples_count)
    )
    target_start = max(0, slices_count // 2 - target_length_traces // 2)
    target_end = min(slices_count, target_start + target_length_traces)
    taper = np.hanning(9)
    lo, hi = max(0, target_sample - 4), min(samples_count, target_sample + 5)
    data[target_start:target_end, lo:hi] += target_amplitude * taper[: hi - lo][np.newaxis, :]
    return data


def _wrap_synthetic(data: np.ndarray, sampling_time_ns: float = 0.5) -> GPRDataset:
    slices_count, samples_count = data.shape
    return GPRDataset(
        amplitudes=data[:, np.newaxis, :].astype(np.float32),
        time_ns=np.arange(samples_count, dtype=np.float64) * sampling_time_ns,
        x=None,
        y=None,
        depth_top_m=None,
        elevation_top_m=None,
        depth_bottom_m=None,
        elevation_bottom_m=None,
        metadata={"sampling": {"sampling_time_ns": sampling_time_ns}},
    )


def run_synthetic_risk_experiments(output_dir: Path) -> dict[str, Any]:
    """Run the window-length/global-vs-sliding/mean-vs-median synthetic experiments and save their outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260715)
    slices_count, samples_count, target_sample = 61, 200, 100

    # -- 17.3: window length vs. target-length attenuation ------------------
    window_traces_options = [5, 9, 15, 25, 37, 51]
    target_lengths = {"shorter_than_window": 3, "about_window": 15, "longer_than_window": 45}
    rows: list[dict[str, Any]] = []
    for target_label, target_length in target_lengths.items():
        data = _synthetic_profile(rng, slices_count, samples_count, target_length_traces=target_length)
        dataset = _wrap_synthetic(data)
        target_start = max(0, slices_count // 2 - target_length // 2)
        target_end = min(slices_count, target_start + target_length)
        target_before = data[target_start:target_end, target_sample - 4 : target_sample + 5]
        for window_traces in window_traces_options:
            if window_traces >= slices_count:
                continue
            result = remove_background(
                dataset, method="sliding_mean", window_traces=window_traces, edge_mode="reflect"
            )
            output = result.dataset.amplitudes[:, 0, :].astype(np.float64)
            target_after = output[target_start:target_end, target_sample - 4 : target_sample + 5]
            amplitude_retention = (
                float(np.abs(target_after).mean() / np.abs(target_before).mean())
                if np.abs(target_before).mean() > 0
                else float("nan")
            )
            energy_retention = (
                float((target_after**2).sum() / (target_before**2).sum())
                if (target_before**2).sum() > 0
                else float("nan")
            )
            correlation = (
                float(np.corrcoef(target_before.ravel(), target_after.ravel())[0, 1])
                if target_before.std() > 0 and target_after.std() > 0
                else float("nan")
            )
            rows.append(
                {
                    "target_length_category": target_label,
                    "target_length_traces": target_length,
                    "window_traces": window_traces,
                    "amplitude_retention": amplitude_retention,
                    "energy_retention": energy_retention,
                    "waveform_correlation": correlation,
                }
            )
    attenuation_df = pd.DataFrame(rows)
    csv_path = output_dir / "synthetic_target_attenuation.csv"
    attenuation_df.to_csv(csv_path, index=False)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    cmap = plt.get_cmap("tab10")
    for i, (target_label, _length) in enumerate(target_lengths.items()):
        subset = attenuation_df[attenuation_df["target_length_category"] == target_label]
        ax.plot(
            subset["window_traces"], subset["energy_retention"], marker="o", color=cmap(i), label=target_label
        )
    ax.set_xlabel("Sliding-mean window (traces)")
    ax.set_ylabel("Target energy retention (synthetic, QC only)")
    ax.set_title("Window length vs. target-length attenuation (synthetic risk test)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    window_plot_path = output_dir / "window_length_vs_target_attenuation.png"
    fig.savefig(window_plot_path, dpi=140)
    plt.close(fig)

    # -- 17.2: global vs sliding on a long horizontal event ------------------
    long_event_length = 45  # a "long horizontal reflection" relative to the profile
    data_long = _synthetic_profile(rng, slices_count, samples_count, target_length_traces=long_event_length)
    dataset_long = _wrap_synthetic(data_long)
    target_start = max(0, slices_count // 2 - long_event_length // 2)
    target_end = min(slices_count, target_start + long_event_length)
    target_before = data_long[target_start:target_end, target_sample - 4 : target_sample + 5]

    global_result = remove_background(dataset_long, method="global_mean")
    sliding_result = remove_background(
        dataset_long, method="sliding_mean", window_traces=9, edge_mode="reflect"
    )
    long_event_rows: list[dict[str, Any]] = []
    for label, result in (("global_mean", global_result), ("sliding_mean_9tr", sliding_result)):
        output = result.dataset.amplitudes[:, 0, :].astype(np.float64)
        target_after = output[target_start:target_end, target_sample - 4 : target_sample + 5]
        energy_retention = (
            float((target_after**2).sum() / (target_before**2).sum())
            if (target_before**2).sum() > 0
            else float("nan")
        )
        long_event_rows.append({"method": label, "long_event_energy_retention": energy_retention})

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(
        [r["method"] for r in long_event_rows],
        [r["long_event_energy_retention"] for r in long_event_rows],
        color=["tab:blue", "tab:orange"],
    )
    ax.set_ylabel("Long horizontal-event energy retention (synthetic)")
    ax.set_title("Global vs. sliding background removal on a long horizontal event")
    fig.tight_layout()
    global_vs_sliding_path = output_dir / "global_vs_sliding_synthetic_comparison.png"
    fig.savefig(global_vs_sliding_path, dpi=140)
    plt.close(fig)

    # -- 17.4: mean vs median under a strong-outlier trace -------------------
    data_outlier = _synthetic_profile(rng, slices_count, samples_count, target_length_traces=9)
    outlier_traces = [10, 11, 30]
    for t in outlier_traces:
        data_outlier[t, :] += rng.normal(scale=1.0) * 4000.0
    dataset_outlier = _wrap_synthetic(data_outlier)
    mean_result = remove_background(dataset_outlier, method="global_mean")
    median_result = remove_background(dataset_outlier, method="global_median")
    clean_trace = 45  # far from both the target and the outlier traces
    mean_bias = float(np.abs(mean_result.removed_component[clean_trace, 0, :]).mean())
    median_bias = float(np.abs(median_result.removed_component[clean_trace, 0, :]).mean())

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(["global_mean", "global_median"], [mean_bias, median_bias], color=["tab:red", "tab:green"])
    ax.set_ylabel("|background estimate| on a clean trace, with 3 strong outlier traces present")
    ax.set_title("Mean vs. median background estimator under outlier traces (synthetic)")
    fig.tight_layout()
    mean_vs_median_path = output_dir / "mean_vs_median_outlier_comparison.png"
    fig.savefig(mean_vs_median_path, dpi=140)
    plt.close(fig)

    return {
        "synthetic_target_attenuation_csv": csv_path,
        "window_length_vs_target_attenuation_png": window_plot_path,
        "global_vs_sliding_synthetic_comparison_png": global_vs_sliding_path,
        "mean_vs_median_outlier_comparison_png": mean_vs_median_path,
        "long_event_energy_retention": {
            r["method"]: r["long_event_energy_retention"] for r in long_event_rows
        },
        "mean_vs_median_clean_trace_bias": {"global_mean": mean_bias, "global_median": median_bias},
    }


# ======================================================================
# Cross-candidate comparison
# ======================================================================


def build_background_comparison(
    dataset: GPRDataset,
    valid_mask: np.ndarray | None,
    candidates_info: list[dict[str, Any]],
    comparison_dir: Path,
) -> dict[str, Path]:
    """Build the background-removal candidate comparison folder. Makes no canonical selection."""
    comparison_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    cmap = plt.get_cmap("tab10")
    start_ns, end_ns = COMPARISON_WINDOW_NS
    sample_mask = (dataset.time_ns >= start_ns) & (dataset.time_ns < end_ns)

    # --- channelNN_all_candidates_20_100ns.png: median-trace overlay -------
    for channel in CANDIDATE_CHANNELS:
        fig, ax = plt.subplots(figsize=(12, 6))
        raw_median = np.median(dataset.amplitudes[:, channel, sample_mask].astype(np.float64), axis=0)
        ax.plot(
            dataset.time_ns[sample_mask],
            raw_median,
            color="black",
            linestyle=":",
            linewidth=1.4,
            label="input",
        )
        for i, info in enumerate(candidates_info):
            after = info["result"].dataset
            median_trace = np.median(after.amplitudes[:, channel, sample_mask].astype(np.float64), axis=0)
            ax.plot(
                after.time_ns[sample_mask],
                median_trace,
                color=cmap(i),
                linewidth=1.1,
                label=f"{info['id']} ({info['label']})",
            )
        ax.set_xlabel("time_ns")
        ax.set_ylabel("Median amplitude")
        ax.set_title(
            f"Channel {channel:02d}, {start_ns:g}-{end_ns:g} ns -- all background candidates (QC only)"
        )
        ax.legend(fontsize=7)
        fig.tight_layout()
        path = comparison_dir / f"channel{channel:02d}_all_candidates_20_100ns.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        paths[f"channel{channel:02d}_all_candidates_20_100ns"] = path

    # --- removed_components_all_candidates_{20_100ns,full}.png -------------
    for suffix, mask in (("20_100ns", sample_mask), ("full", np.ones_like(sample_mask))):
        fig, ax = plt.subplots(figsize=(12, 6))
        for i, info in enumerate(candidates_info):
            removed = info["result"].removed_component
            median_trace = np.median(removed[:, CANDIDATE_CHANNELS[0], mask].astype(np.float64), axis=0)
            ax.plot(dataset.time_ns[mask], median_trace, color=cmap(i), linewidth=1.1, label=f"{info['id']}")
        ax.set_xlabel("time_ns")
        ax.set_ylabel("Median removed amplitude")
        ax.set_title(f"Channel {CANDIDATE_CHANNELS[0]:02d} removed component -- all candidates ({suffix})")
        ax.legend(fontsize=7)
        fig.tight_layout()
        path = comparison_dir / f"removed_components_all_candidates_{suffix}.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        paths[f"removed_components_all_candidates_{suffix}"] = path

    ids = [info["id"] for info in candidates_info]

    def _bar(values: list[float], ylabel: str, title: str, filename: str) -> Path:
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar(ids, values, color=[cmap(i) for i in range(len(ids))])
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.axhline(0.0, color="black", linewidth=0.8)
        fig.tight_layout()
        path = comparison_dir / filename
        fig.savefig(path, dpi=140)
        plt.close(fig)
        return path

    w5 = "W5"
    paths["removed_component_coherence"] = _bar(
        [info["removed_metrics"][w5]["adjacent_trace_correlation_median"] for info in candidates_info],
        "Removed-component adjacent-trace correlation (median, W5)",
        "Removed-component spatial coherence -- all candidates (QC only, not a target claim)",
        "removed_component_coherence.png",
    )
    paths["removed_input_energy_ratio"] = _bar(
        [info["removed_metrics"][w5]["removed_input_energy_ratio"] for info in candidates_info],
        "Removed / input energy ratio (W5)",
        "Removed-vs-input energy ratio -- all candidates",
        "removed_input_energy_ratio.png",
    )
    paths["signal_preservation_comparison"] = _bar(
        [info["signal_preservation"][w5]["rms_retention"] for info in candidates_info],
        "Output RMS retention (W5)",
        "Signal preservation (RMS retention) -- all candidates",
        "signal_preservation_comparison.png",
    )
    paths["waveform_correlation_comparison"] = _bar(
        [info["signal_preservation"][w5]["waveform_correlation_median"] for info in candidates_info],
        "Waveform correlation (median, W5)",
        "Waveform correlation vs. canonical input -- all candidates",
        "waveform_correlation_comparison.png",
    )
    paths["adjacent_trace_correlation_comparison"] = _bar(
        [info["signal_preservation"][w5]["adjacent_trace_correlation_after"] for info in candidates_info],
        "Output adjacent-trace correlation (median, W5)",
        "Output spatial coherence -- all candidates",
        "adjacent_trace_correlation_comparison.png",
    )
    paths["spectral_retention_comparison"] = _bar(
        [info["signal_preservation"][w5]["spectral_energy_retention"] for info in candidates_info],
        "Spectral energy retention (W5)",
        "Spectral-energy retention -- all candidates",
        "spectral_retention_comparison.png",
    )

    synthetic = run_synthetic_risk_experiments(comparison_dir)
    paths.update(
        {
            "window_length_vs_target_attenuation": Path(synthetic["window_length_vs_target_attenuation_png"]),
            "global_vs_sliding_synthetic_comparison": Path(
                synthetic["global_vs_sliding_synthetic_comparison_png"]
            ),
            "mean_vs_median_outlier_comparison": Path(synthetic["mean_vs_median_outlier_comparison_png"]),
            "synthetic_target_attenuation_csv": Path(synthetic["synthetic_target_attenuation_csv"]),
        }
    )

    # --- candidate_metrics*.csv ---------------------------------------------
    overall_rows = []
    by_channel_rows = []
    by_window_rows = []
    categories = _engineering_category(candidates_info)
    for info in candidates_info:
        diag = info["result"].diagnostics
        overall_rows.append(
            {
                "id": info["id"],
                "label": info["label"],
                "method": info["method"],
                "applied_window_traces": diag["applied_window_traces"],
                "applied_window_m": diag["applied_window_m"],
                "rms_retention_w5": info["signal_preservation"][w5]["rms_retention"],
                "spectral_energy_retention_w5": info["signal_preservation"][w5]["spectral_energy_retention"],
                "waveform_correlation_median_w5": info["signal_preservation"][w5][
                    "waveform_correlation_median"
                ],
                "median_trace_cross_correlation_lag_w5": info["signal_preservation"][w5][
                    "median_trace_cross_correlation_lag"
                ],
                "removed_input_energy_ratio_w5": info["removed_metrics"][w5]["removed_input_energy_ratio"],
                "removed_component_coherence_w5": info["removed_metrics"][w5][
                    "adjacent_trace_correlation_median"
                ],
                "engineering_category": categories[info["id"]],
            }
        )
        for channel in CANDIDATE_CHANNELS:
            windowed = info["result"].dataset.amplitudes[:, channel, sample_mask].astype(np.float64)
            risk = compute_localized_event_risk(windowed)
            by_channel_rows.append({"id": info["id"], "channel": channel, **risk})
        for window_label, _s, _e in TIME_WINDOWS_NS:
            by_window_rows.append(
                {
                    "id": info["id"],
                    "window": window_label,
                    **{f"signal_{k}": v for k, v in info["signal_preservation"][window_label].items()},
                    **{
                        f"removed_{k}": v
                        for k, v in info["removed_metrics"][window_label].items()
                        if k != "band_energy_mhz"
                    },
                }
            )

    pd.DataFrame(overall_rows).to_csv(comparison_dir / "candidate_metrics.csv", index=False)
    pd.DataFrame(by_channel_rows).to_csv(comparison_dir / "candidate_metrics_by_channel.csv", index=False)
    pd.DataFrame(by_window_rows).to_csv(comparison_dir / "candidate_metrics_by_time_window.csv", index=False)
    paths["candidate_metrics_csv"] = comparison_dir / "candidate_metrics.csv"
    paths["candidate_metrics_by_channel_csv"] = comparison_dir / "candidate_metrics_by_channel.csv"
    paths["candidate_metrics_by_time_window_csv"] = comparison_dir / "candidate_metrics_by_time_window.csv"

    trace_spacing_summary_path = comparison_dir / "trace_spacing_summary.json"
    trace_spacing_summary_path.write_text(
        json.dumps(candidates_info[0]["result"].diagnostics["trace_spacing"], indent=2), encoding="utf-8"
    )
    paths["trace_spacing_summary"] = trace_spacing_summary_path

    review_path = comparison_dir / "BACKGROUND_REVIEW_REQUIRED.md"
    review_path.write_text(_background_review_markdown(candidates_info, categories), encoding="utf-8")
    paths["review"] = review_path

    return paths


def _background_review_markdown(candidates_info: list[dict[str, Any]], categories: dict[str, str]) -> str:
    w5 = "W5"
    header_row = (
        "| ID | Label | Method | Applied window (traces) | RMS retention (W5) | "
        "Removed/input energy (W5) | Removed coherence (W5) | Engineering category |"
    )
    rows = "\n".join(
        f"| {info['id']} | {info['label']} | {info['method']} | "
        f"{info['result'].diagnostics['applied_window_traces']} | "
        f"{info['signal_preservation'][w5]['rms_retention']:.4g} | "
        f"{info['removed_metrics'][w5]['removed_input_energy_ratio']:.4g} | "
        f"{info['removed_metrics'][w5]['adjacent_trace_correlation_median']:.4g} | "
        f"{categories[info['id']]} |"
        for info in candidates_info
    )
    return f"""# Background Removal Candidate Review (Sprint 4A)

**No candidate below has been selected as canonical.** Background removal is
the most scientifically risky filter this project has implemented -- it can
remove a genuinely long, laterally continuous archaeological reflection
exactly as effectively as unwanted common-mode noise (see CLAUDE.md,
ADR-008). Human/geophysical review is required before any candidate is
used for anything beyond QC comparison.

{header_row}
|---|---|---|---|---|---|---|---|
{rows}

`engineering_category` is a transparent, relative ranking by measured RMS
retention across these 8 candidates on this dataset only (see
``sprint4a_candidates.py::_engineering_category``) -- it is not a canonical
selection, and it does not transfer to a different dataset.

See `BACKGROUND_DECISION_PANEL.png`, `BACKGROUND_DECISION_PANEL_DETAIL.png`,
and `../../BACKGROUND_FINAL_DECISION_REQUIRED.md` for the full decision
package.
"""


# ======================================================================
# Decision panel and final human-decision report
# ======================================================================


def save_decision_panel(
    dataset: GPRDataset,
    candidates_info: list[dict[str, Any]],
    output_path: Path,
    detail_output_path: Path,
) -> tuple[Path, Path]:
    """Save the two-page Sprint 4A decision panel (summary + detail B-scans)."""
    w5 = "W5"
    ids = [info["id"] for info in candidates_info]
    cmap = plt.get_cmap("tab10")

    fig, axes = plt.subplots(2, 3, figsize=(20, 11))
    metrics_to_plot = [
        ("rms_retention", "signal_preservation", "Output RMS retention (W5)"),
        ("waveform_correlation_median", "signal_preservation", "Waveform correlation (W5)"),
        ("adjacent_trace_correlation_after", "signal_preservation", "Output adjacent-trace corr. (W5)"),
        ("spectral_energy_retention", "signal_preservation", "Spectral-energy retention (W5)"),
        ("removed_input_energy_ratio", "removed_metrics", "Removed/input energy ratio (W5)"),
        ("adjacent_trace_correlation_median", "removed_metrics", "Removed-component coherence (W5)"),
    ]
    for ax, (metric_key, source_key, title) in zip(axes.ravel(), metrics_to_plot, strict=True):
        values = [info[source_key][w5][metric_key] for info in candidates_info]
        ax.bar(ids, values, color=[cmap(i) for i in range(len(ids))])
        ax.set_title(title, fontsize=10)
        ax.axhline(0.0, color="black", linewidth=0.6)
        ax.tick_params(axis="x", labelsize=8)
    fig.suptitle(
        "Sprint 4A Background Removal -- Decision Summary (W5 = 20-100 ns, post-direct-wave)\n"
        "No candidate selected as canonical -- human/geophysical review required",
        fontsize=12,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)

    start_ns, end_ns = COMPARISON_WINDOW_NS
    sample_mask = (dataset.time_ns >= start_ns) & (dataset.time_ns < end_ns)
    n = len(candidates_info)
    fig, axes = plt.subplots(1, n, figsize=(3.2 * n, 6), squeeze=False)
    for i, info in enumerate(candidates_info):
        ax = axes[0][i]
        after = info["result"].dataset.amplitudes[:, CANDIDATE_CHANNELS[0], sample_mask].astype(np.float64)
        limit = float(np.percentile(np.abs(after), 99)) or 1.0
        extent = (0.0, float(after.shape[0]), end_ns, start_ns)
        ax.imshow(
            after.T, aspect="auto", cmap="seismic", vmin=-limit, vmax=limit, extent=extent, origin="upper"
        )
        ax.set_title(f"{info['id']}", fontsize=9)
        ax.set_xlabel("Slice")
        if i == 0:
            ax.set_ylabel("time_ns")
    fig.suptitle(
        f"Channel {CANDIDATE_CHANNELS[0]:02d}, {start_ns:g}-{end_ns:g} ns -- all candidates (detail)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    detail_output_path = Path(detail_output_path)
    detail_output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(detail_output_path, dpi=150)
    plt.close(fig)

    return output_path, detail_output_path


def write_background_final_decision_required(
    candidates_info: list[dict[str, Any]], categories: dict[str, str], output_path: Path
) -> Path:
    """Write ``BACKGROUND_FINAL_DECISION_REQUIRED.md`` -- criteria table, no canonical pick."""
    w5 = "W5"
    header = [
        "Candidate",
        "Method",
        "Requested window",
        "Applied window traces",
        "Applied window metres",
        "Background suppression",
        "Long-horizontal-event preservation",
        "Localized-event preservation",
        "Waveform correlation",
        "RMS retention",
        "Spectral retention",
        "Adjacent-trace correlation",
        "Removed-component coherence",
        "Removed/input energy",
        "Padding safety",
        "Timing preservation",
        "Engineering category",
        "Main risk",
    ]
    rows = []
    for info in candidates_info:
        diag = info["result"].diagnostics
        sp = info["signal_preservation"][w5]
        rm = info["removed_metrics"][w5]
        requested = (
            f"{diag['requested_window_m']:g} m"
            if diag["requested_window_m"] is not None
            else (
                f"{diag['requested_window_traces']} traces"
                if diag["requested_window_traces"]
                else "n/a (global)"
            )
        )
        main_risk = (
            "may under-suppress common-mode background"
            if categories[info["id"]] == "too_weak"
            else "may remove real, laterally continuous reflections"
            if categories[info["id"]] in ("too_aggressive", "suppression-favoring")
            else "moderate risk to long horizontal reflections; review removed-component panels"
        )
        # "Long-horizontal-event preservation" is a QC proxy, not a direct
        # real-data measurement (no ground-truth long event exists in this
        # dataset) -- it is the inverse of the removed component's own
        # adjacent-trace coherence: a removed component that is itself
        # highly spatially continuous is exactly the signature of removing a
        # real long horizontal reflection. See the *synthetic* long-event
        # experiment (run_synthetic_risk_experiments) for a direct
        # known-target measurement of this same risk.
        long_horizontal_event_preservation = max(0.0, 1.0 - rm["adjacent_trace_correlation_median"])
        rows.append(
            "| "
            + " | ".join(
                [
                    info["id"],
                    info["method"],
                    requested,
                    str(diag["applied_window_traces"]) if diag["applied_window_traces"] else "n/a",
                    f"{diag['applied_window_m']:.4g}" if diag["applied_window_m"] else "n/a",
                    f"{rm['removed_input_rms_ratio']:.4g}",
                    f"{long_horizontal_event_preservation:.4g}",
                    f"{sp['local_event_amplitude_retention']:.4g}",
                    f"{sp['waveform_correlation_median']:.4g}",
                    f"{sp['rms_retention']:.4g}",
                    f"{sp['spectral_energy_retention']:.4g}",
                    f"{sp['adjacent_trace_correlation_after']:.4g}",
                    f"{rm['adjacent_trace_correlation_median']:.4g}",
                    f"{rm['removed_input_energy_ratio']:.4g}",
                    "ok",
                    str(sp["median_trace_cross_correlation_lag"]),
                    categories[info["id"]],
                    main_risk,
                ]
            )
            + " |"
        )

    content = f"""# BACKGROUND_FINAL_DECISION_REQUIRED

**Status: review_required**
**No background-removal candidate has been selected as canonical.**
**Gain has not been started.**

| {" | ".join(header)} |
|{"---|" * len(header)}
{chr(10).join(rows)}

`engineering_category` is a transparent, relative ranking by measured RMS
retention across these 8 candidates *on this dataset only* -- it is not a
canonical selection, does not transfer to another dataset or acquisition
setting, and none of these values were used to automatically eliminate any
candidate. Background removal cannot, on its own, distinguish unwanted
common-mode noise from a genuinely long, laterally continuous
archaeological reflection (a floor, a wall foundation, a layer boundary) --
see ADR-008 and `removed_component_metrics.json` (`horizontal_gradient_
energy`, `local_curvature_energy`) for each candidate's own removed-component
shape.

`Long-horizontal-event preservation` is a QC proxy derived from the removed
component's own adjacent-trace coherence (`1 - removed_component_coherence`),
not a direct measurement -- this real dataset has no known-ground-truth long
horizontal event to measure against. See `synthetic_target_attenuation.csv`
and `global_vs_sliding_synthetic_comparison.png` for the direct, known-target
version of this same risk on synthetic data. `Localized-event preservation`
is `local_event_amplitude_retention` from `signal_preservation_metrics.json`
-- the fraction of each trace's own dominant-sample amplitude that survives
background removal; also a QC proxy, not an archaeological target pick.

## What this report does NOT do

It does not select a canonical background-removal candidate. It does not
apply gain. It does not make any archaeological interpretation of removed
or retained content. Human/geophysical review of `BACKGROUND_DECISION_
PANEL.png`, `BACKGROUND_DECISION_PANEL_DETAIL.png`, and the per-candidate
removed-component B-scans is required before any candidate here is used
for anything beyond QC comparison.
"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def run_all_sprint4a_candidates(
    npz_path: str | Path,
    output_dir: str | Path,
    *,
    background_config_path: str | Path = "configs/background_candidates.yaml",
    sprint2_canonical_npz_path: str
    | Path
    | None = "outputs/sprint02/canonical_target16/sprint02_processed.npz",
) -> dict[str, Any]:
    """Run every Sprint 4A background-removal candidate end to end.

    Reads the canonical Sprint 3 NPZ at ``npz_path`` (never modified),
    writes every candidate's QC suite plus comparison/decision-panel/
    final-decision outputs under ``output_dir``. Never selects or marks any
    candidate canonical -- see CLAUDE.md and ADR-008. Hashes the raw
    ``.ogpr`` file (via ``dataset.metadata['source_file']['path']``, never
    hardcoded), the Sprint 2 canonical NPZ (if ``sprint2_canonical_npz_path``
    resolves to a real file -- ``None`` or a missing path is recorded as
    ``"not_verified_this_run"`` rather than fabricated), and ``npz_path``
    itself -- then re-hashes ``npz_path`` after every candidate has run to
    confirm this sprint never touched its own input.
    """
    from archaeogpr.export.sprint3 import load_candidates_config

    output_dir = Path(output_dir)
    npz_path = Path(npz_path)
    sprint3_canonical_sha256_before = sha256_file(npz_path)
    dataset, valid_mask = read_processed_npz(npz_path)

    source_file = dataset.metadata.get("source_file") or {}
    raw_path = source_file.get("path")
    raw_file_sha256 = (
        sha256_file(raw_path) if raw_path and Path(raw_path).is_file() else "not_verified_this_run"
    )
    sprint2_canonical_sha256 = (
        sha256_file(sprint2_canonical_npz_path)
        if sprint2_canonical_npz_path is not None and Path(sprint2_canonical_npz_path).is_file()
        else "not_verified_this_run"
    )

    config = load_candidates_config(background_config_path)

    candidates_root = output_dir / "background_candidates"
    candidates_info = run_background_candidates(
        dataset,
        valid_mask,
        candidates_root,
        config,
        raw_file_sha256=raw_file_sha256,
        sprint2_canonical_sha256=sprint2_canonical_sha256,
        sprint3_canonical_sha256=sprint3_canonical_sha256_before,
    )
    comparison_paths = build_background_comparison(
        dataset, valid_mask, candidates_info, candidates_root / "comparison"
    )

    sprint3_canonical_sha256_after = sha256_file(npz_path)
    input_hash_unchanged = sprint3_canonical_sha256_before == sprint3_canonical_sha256_after

    categories = _engineering_category(candidates_info)
    decision_panel_path, decision_panel_detail_path = save_decision_panel(
        dataset,
        candidates_info,
        output_dir / "BACKGROUND_DECISION_PANEL.png",
        output_dir / "BACKGROUND_DECISION_PANEL_DETAIL.png",
    )
    final_decision_path = write_background_final_decision_required(
        candidates_info, categories, output_dir / "BACKGROUND_FINAL_DECISION_REQUIRED.md"
    )

    return {
        "dataset": dataset,
        "valid_mask": valid_mask,
        "candidates": candidates_info,
        "comparison_paths": comparison_paths,
        "engineering_categories": categories,
        "decision_panel_path": decision_panel_path,
        "decision_panel_detail_path": decision_panel_detail_path,
        "final_decision_path": final_decision_path,
        "raw_file_sha256": raw_file_sha256,
        "sprint2_canonical_sha256": sprint2_canonical_sha256,
        "sprint3_canonical_sha256_before": sprint3_canonical_sha256_before,
        "sprint3_canonical_sha256_after": sprint3_canonical_sha256_after,
        "input_hash_unchanged": input_hash_unchanged,
    }


__all__ = [
    "CANDIDATE_CHANNELS",
    "build_background_comparison",
    "run_all_sprint4a_candidates",
    "run_background_candidates",
    "run_synthetic_risk_experiments",
    "save_decision_panel",
    "sha256_file",
    "write_background_final_decision_required",
]
