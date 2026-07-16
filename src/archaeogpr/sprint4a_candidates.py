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
from dataclasses import dataclass
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
from archaeogpr.qc.bscan import compute_shared_clip_limit
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
    """Run the window-length/global-vs-sliding/mean-vs-median synthetic experiments and save their outputs.

    Sprint 4A.1 note: the retention metrics computed here measure the
    windowed *mixed scene* (background + noise + target together) before
    vs. after processing -- they are NOT isolated target-only retention,
    because the "before" reference here still contains the shared
    background/noise component. Fields are named ``mixed_scene_*``
    accordingly. For an isolated, paired-control measurement of the
    target component alone (background+noise held identical between a
    "control" and "with-target" run), see
    :func:`run_paired_control_target_attenuation_experiments`.
    """
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
                    # Sprint 4A.1: renamed from "amplitude_retention"/"energy_retention"/
                    # "waveform_correlation" -- these measure the mixed background+noise+
                    # target scene, not an isolated target-only component. Do not confuse
                    # with the paired-control "target_*" metrics below.
                    "mixed_scene_amplitude_retention": amplitude_retention,
                    "mixed_scene_energy_retention": energy_retention,
                    "mixed_scene_waveform_correlation": correlation,
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
            subset["window_traces"],
            subset["mixed_scene_energy_retention"],
            marker="o",
            color=cmap(i),
            label=target_label,
        )
    ax.set_xlabel("Sliding-mean window (traces)")
    ax.set_ylabel("Mixed-scene energy retention (synthetic, QC only, not target-isolated)")
    ax.set_title(
        "Window length vs. target-length attenuation (synthetic, mixed-scene metric)\n"
        "See paired_control_window_length_vs_target_attenuation.png for the target-isolated version"
    )
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
        long_event_rows.append({"method": label, "long_event_mixed_scene_energy_retention": energy_retention})

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(
        [r["method"] for r in long_event_rows],
        [r["long_event_mixed_scene_energy_retention"] for r in long_event_rows],
        color=["tab:blue", "tab:orange"],
    )
    ax.set_ylabel("Long horizontal-event mixed-scene energy retention (synthetic)")
    ax.set_title(
        "Global vs. sliding background removal on a long horizontal event (mixed-scene metric)\n"
        "See paired_control_target_attenuation.csv for the target-isolated, global-mean/median version"
    )
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
        "long_event_mixed_scene_energy_retention": {
            r["method"]: r["long_event_mixed_scene_energy_retention"] for r in long_event_rows
        },
        "mean_vs_median_clean_trace_bias": {"global_mean": mean_bias, "global_median": median_bias},
    }


# ======================================================================
# Paired-control synthetic target attenuation (Sprint 4A.1 correction) --
# isolates the target-only component by differencing a "control" run
# (background + noise only) against a "with-target" run built from the
# SAME background+noise realization, both processed with the same
# method/parameters. This is distinct from run_synthetic_risk_experiments()
# above, whose "mixed_scene_*" metrics measure the windowed scene as a
# whole (background+noise+target together) rather than the target alone.
# ======================================================================


@dataclass(frozen=True)
class PairedControlProfile:
    """Everything needed to isolate and evaluate one synthetic target's own retention.

    ``target_mask`` is a ``(slices_count, samples_count)`` boolean array,
    True exactly where the target's own amplitude contribution is nonzero
    (a Hanning taper's own endpoints are exactly 0.0, so they are excluded
    -- ``target_before`` is exactly zero everywhere ``target_mask`` is
    False, and ``target_mask`` covers every nonzero ``target_before``
    position). ``target_center_sample_by_trace`` holds each target trace's
    own center/peak sample, and ``-1`` for every trace outside the target
    -- this identifies the hyperbola's apex (its minimum value among
    target traces, per Sprint 4A.2: "apex is the shallowest sample") versus
    its arms (every other target trace). ``shape_diagnostics`` records how
    a hyperbola's curvature was derived and what it actually produced
    (Sprint 4A.2 -- see ``_paired_control_profile``).
    """

    control: np.ndarray
    with_target: np.ndarray
    target_mask: np.ndarray
    target_trace_bounds: tuple[int, int]
    target_sample_bounds: tuple[int, int]
    target_center_sample_by_trace: np.ndarray
    shape_diagnostics: dict[str, Any]


#: Sprint 4A.2 default: the hyperbola's outermost trace is shifted this many
#: samples away from the apex. A *fixed* curvature constant combined with a
#: short target can round every depth_shift to 0 (the Sprint 4A.1 bug this
#: constant fixes) -- deriving curvature from this value and the target's
#: own half-length instead guarantees a real, measurable curve regardless
#: of target_length_traces.
_HYPERBOLA_DEFAULT_MAX_SHIFT_SAMPLES = 12.0


def _paired_control_profile(
    rng: np.random.Generator,
    slices_count: int,
    samples_count: int,
    *,
    target_length_traces: int,
    target_shape: str = "rect",
    target_sample: int = 100,
    background_amplitude: float = 200.0,
    target_amplitude: float = 600.0,
    noise_scale: float = 15.0,
    requested_max_shift_samples: float = _HYPERBOLA_DEFAULT_MAX_SHIFT_SAMPLES,
) -> PairedControlProfile:
    """Build a paired (control, with_target) pair sharing one background+noise realization.

    ``target_shape`` is ``"rect"`` (a flat-topped, sample-axis-tapered
    block, the same depth across every target trace -- a "long horizontal
    reflection" style event) or ``"hyperbola"`` (sample center genuinely
    varies with trace index, curving away from an apex -- a localized,
    curved event; Sprint 4A.2). For ``"hyperbola"``, ``curvature`` is
    derived as ``requested_max_shift_samples / max_offset_traces**2``
    (``max_offset_traces`` = the trace distance from the apex to the
    target's own edge) rather than a fixed constant, guaranteeing the
    outermost trace is shifted by (approximately) ``requested_max_shift_
    samples`` regardless of ``target_length_traces`` -- a fixed curvature
    with a short target can round every ``depth_shift`` to 0, producing a
    practically flat "hyperbola" (the Sprint 4A.1 bug this fixes). Raises
    ``ValueError`` rather than silently clipping if the target would
    exceed the profile's own trace or sample bounds.
    """
    background = background_amplitude * np.sin(np.linspace(0.0, 4 * np.pi, samples_count))
    noise = rng.normal(scale=noise_scale, size=(slices_count, samples_count))
    control = np.tile(background, (slices_count, 1)) + noise
    with_target = control.copy()
    target_mask = np.zeros((slices_count, samples_count), dtype=bool)
    center_sample_by_trace = np.full(slices_count, -1, dtype=int)

    target_start = max(0, slices_count // 2 - target_length_traces // 2)
    target_end = min(slices_count, target_start + target_length_traces)
    if target_end <= target_start:
        raise ValueError(f"target_length_traces={target_length_traces} produced an empty target range")

    shape_diagnostics: dict[str, Any] = {"target_shape": target_shape}
    sample_lo_bound = samples_count
    sample_hi_bound = 0

    def _apply_taper(trace_index: int, center: int) -> None:
        nonlocal sample_lo_bound, sample_hi_bound
        lo, hi = center - 4, center + 5
        if lo < 0 or hi > samples_count:
            raise ValueError(
                f"target at trace {trace_index} (center sample={center}) exceeds sample bounds "
                f"[0, {samples_count}) -- move target_sample away from the profile edge or reduce "
                "requested_max_shift_samples"
            )
        taper = np.hanning(9)
        with_target[trace_index, lo:hi] += target_amplitude * taper
        target_mask[trace_index, lo + np.flatnonzero(taper != 0)] = True
        center_sample_by_trace[trace_index] = center
        sample_lo_bound = min(sample_lo_bound, lo)
        sample_hi_bound = max(sample_hi_bound, hi)

    if target_shape == "rect":
        for trace_index in range(target_start, target_end):
            _apply_taper(trace_index, target_sample)
    elif target_shape == "hyperbola":
        apex_trace = (target_start + target_end - 1) // 2
        max_offset_traces = max(apex_trace - target_start, target_end - 1 - apex_trace)
        if max_offset_traces < 1:
            raise ValueError(
                f"target_length_traces={target_length_traces} is too short for a hyperbola -- "
                "need traces on both sides of the apex"
            )
        curvature = requested_max_shift_samples / max_offset_traces**2
        for trace_index in range(target_start, target_end):
            offset = trace_index - apex_trace
            depth_shift = int(round(curvature * offset**2))
            _apply_taper(trace_index, target_sample + depth_shift)

        unique_centers = sorted({int(c) for c in center_sample_by_trace[target_start:target_end] if c >= 0})
        shape_diagnostics.update(
            {
                "apex_trace_index": apex_trace,
                "max_offset_traces": max_offset_traces,
                "requested_max_shift_samples": requested_max_shift_samples,
                "computed_curvature": curvature,
                "realized_max_shift_samples": (
                    (max(unique_centers) - target_sample) if unique_centers else 0
                ),
                "unique_center_sample_count": len(unique_centers),
                "unique_center_samples": unique_centers,
            }
        )
    else:
        raise ValueError(f"target_shape must be 'rect' or 'hyperbola', got {target_shape!r}")

    return PairedControlProfile(
        control=control,
        with_target=with_target,
        target_mask=target_mask,
        target_trace_bounds=(target_start, target_end),
        target_sample_bounds=(sample_lo_bound, sample_hi_bound),
        target_center_sample_by_trace=center_sample_by_trace,
        shape_diagnostics=shape_diagnostics,
    )


def _mask_subset_retention(
    target_before: np.ndarray,
    target_after: np.ndarray,
    target_mask: np.ndarray,
    row_selector: np.ndarray,
) -> dict[str, float]:
    """Retention ratios computed ONLY over ``target_mask`` positions within the selected trace rows.

    ``target_before``/``target_after`` are boolean-indexed by the SAME
    combined mask, so element-wise correspondence between the two is
    preserved (numpy iterates a boolean mask in a fixed, consistent order
    for same-shaped arrays).
    """
    row_mask = np.zeros(target_mask.shape[0], dtype=bool)
    row_mask[row_selector] = True
    combined_mask = target_mask & row_mask[:, np.newaxis]
    before = target_before[combined_mask]
    after = target_after[combined_mask]
    before_abs_mean = float(np.abs(before).mean()) if before.size else 0.0
    after_abs_mean = float(np.abs(after).mean()) if after.size else 0.0
    before_energy = float((before**2).sum())
    after_energy = float((after**2).sum())
    before_peak = float(np.abs(before).max()) if before.size else 0.0
    after_peak = float(np.abs(after).max()) if after.size else 0.0
    correlation = (
        float(np.corrcoef(before, after)[0, 1])
        if before.size >= 2 and before.std() > 0 and after.std() > 0
        else float("nan")
    )
    return {
        "mean_absolute_retention": (after_abs_mean / before_abs_mean)
        if before_abs_mean > 0
        else float("nan"),
        "energy_retention": (after_energy / before_energy) if before_energy > 0 else float("nan"),
        "peak_retention": (after_peak / before_peak) if before_peak > 0 else float("nan"),
        "waveform_correlation": correlation,
    }


def _paired_control_retention_metrics(
    profile: PairedControlProfile,
    method: str,
    window_kwargs: dict[str, Any],
    edge_mode: str,
    *,
    sampling_time_ns: float = 0.5,
) -> dict[str, float]:
    """Isolate the target-only before/after component and measure its retention over its REAL support.

    ``target_before = with_target - control`` is the exact, known target
    component (by construction, since both share the same background+noise).
    ``target_after`` is the SAME subtraction applied to the two independently
    processed outputs -- this isolates what background removal did to the
    target-attributable signal specifically, cancelling out whatever it did
    to the shared background/noise. Sprint 4A.2: every metric here uses
    ``profile.target_mask`` -- the target's actual per-trace support -- not
    a fixed sample window; for a hyperbola, a fixed window centered on the
    apex would silently miss the curved arms entirely.
    """
    control_dataset = _wrap_synthetic(profile.control, sampling_time_ns)
    with_target_dataset = _wrap_synthetic(profile.with_target, sampling_time_ns)
    kwargs: dict[str, Any] = {"method": method, "edge_mode": edge_mode, **window_kwargs}
    if method in ("global_mean", "global_median"):
        kwargs = {"method": method}

    processed_control = remove_background(control_dataset, **kwargs)
    processed_with_target = remove_background(with_target_dataset, **kwargs)

    target_before = profile.with_target - profile.control
    target_after = processed_with_target.dataset.amplitudes[:, 0, :].astype(
        np.float64
    ) - processed_control.dataset.amplitudes[:, 0, :].astype(np.float64)

    target_start, target_end = profile.target_trace_bounds
    all_target_traces = np.arange(target_start, target_end)
    full = _mask_subset_retention(target_before, target_after, profile.target_mask, all_target_traces)

    centers = profile.target_center_sample_by_trace[all_target_traces]
    apex_trace = int(all_target_traces[np.argmin(centers)])  # apex = shallowest (minimum) sample
    apex = _mask_subset_retention(target_before, target_after, profile.target_mask, np.array([apex_trace]))
    arm_traces = all_target_traces[all_target_traces != apex_trace]
    arm = (
        _mask_subset_retention(target_before, target_after, profile.target_mask, arm_traces)
        if arm_traces.size
        else full
    )

    edge_traces = np.array(sorted({target_start, target_end - 1}))
    edge = _mask_subset_retention(target_before, target_after, profile.target_mask, edge_traces)
    n = len(all_target_traces)
    margin = min(2, max(0, n // 2 - 1))
    interior_traces = all_target_traces[margin : n - margin] if n > 2 * margin else all_target_traces
    interior = _mask_subset_retention(target_before, target_after, profile.target_mask, interior_traces)

    return {
        "full_target_peak_retention": full["peak_retention"],
        "full_target_mean_absolute_retention": full["mean_absolute_retention"],
        "full_target_energy_retention": full["energy_retention"],
        "full_target_waveform_correlation": full["waveform_correlation"],
        "apex_retention": apex["mean_absolute_retention"],
        "arm_retention": arm["mean_absolute_retention"],
        "edge_trace_retention": edge["mean_absolute_retention"],
        "interior_target_retention": interior["mean_absolute_retention"],
    }


#: Fixed sliding window (traces) used to classify the "shorter/about/longer
#: than window" paired-control scenarios below -- an explicit constant, not
#: re-derived per candidate, since these are synthetic risk-test scenarios
#: rather than the real 8 candidates (which each keep their own window).
_PAIRED_CONTROL_COMPARISON_WINDOW_TRACES = 15
_PAIRED_CONTROL_SLICES_COUNT = 61
_PAIRED_CONTROL_SAMPLES_COUNT = 200
_PAIRED_CONTROL_TARGET_SAMPLE = 100


def _save_paired_control_hyperbola_validation_panel(
    profile: PairedControlProfile,
    window_traces: int,
    output_path: Path,
    *,
    sampling_time_ns: float = 0.5,
) -> Path:
    """Sprint 4A.2: visual evidence that the localized-hyperbola target is genuinely curved.

    Panels: the known ``target_before`` component; processed ``target_after``
    for ``sliding_mean`` and for ``sliding_median`` (both against the SAME
    ``profile``, so the two are directly comparable); the real boolean
    ``target_mask``; the per-trace center-sample trajectory (proving the
    center genuinely varies, with the apex marked); and apex-vs-arm retention
    bars for both methods. The title states the actual target trace count,
    unique center-sample count, realized max shift, and comparison window
    length, so the figure is self-documenting evidence against the Sprint
    4A.1 bug (a fixed curvature that rounded every depth_shift to 0).
    """
    control_dataset = _wrap_synthetic(profile.control, sampling_time_ns)
    with_target_dataset = _wrap_synthetic(profile.with_target, sampling_time_ns)
    target_before = profile.with_target - profile.control
    target_start, target_end = profile.target_trace_bounds

    processed_after: dict[str, np.ndarray] = {}
    retention: dict[str, dict[str, float]] = {}
    for method in ("sliding_mean", "sliding_median"):
        window_kwargs: dict[str, Any] = {"window_traces": window_traces}
        processed_control = remove_background(
            control_dataset, method=method, edge_mode="reflect", **window_kwargs
        )
        processed_with_target = remove_background(
            with_target_dataset, method=method, edge_mode="reflect", **window_kwargs
        )
        processed_after[method] = processed_with_target.dataset.amplitudes[:, 0, :].astype(
            np.float64
        ) - processed_control.dataset.amplitudes[:, 0, :].astype(np.float64)
        retention[method] = _paired_control_retention_metrics(profile, method, window_kwargs, "reflect")

    diagnostics = profile.shape_diagnostics
    unique_center_count = diagnostics.get("unique_center_sample_count", 0)
    realized_max_shift = diagnostics.get("realized_max_shift_samples", 0)

    sample_lo_bound, sample_hi_bound = profile.target_sample_bounds
    pad = 5
    sample_lo = max(0, sample_lo_bound - pad)
    sample_hi = min(profile.control.shape[1], sample_hi_bound + pad)
    extent = (target_start, target_end, sample_hi, sample_lo)
    clip = float(np.abs(target_before[target_start:target_end, sample_lo:sample_hi]).max()) or 1.0

    fig = plt.figure(figsize=(14, 9))
    grid = fig.add_gridspec(3, 2)

    ax_before = fig.add_subplot(grid[0, 0])
    ax_before.imshow(
        target_before[target_start:target_end, sample_lo:sample_hi].T,
        aspect="auto",
        cmap="seismic",
        vmin=-clip,
        vmax=clip,
        extent=extent,
        origin="upper",
    )
    ax_before.set_title("target_before (known target component)")
    ax_before.set_xlabel("Trace index")
    ax_before.set_ylabel("Sample")

    for grid_pos, method in zip((grid[0, 1], grid[1, 0]), ("sliding_mean", "sliding_median"), strict=True):
        ax = fig.add_subplot(grid_pos)
        ax.imshow(
            processed_after[method][target_start:target_end, sample_lo:sample_hi].T,
            aspect="auto",
            cmap="seismic",
            vmin=-clip,
            vmax=clip,
            extent=extent,
            origin="upper",
        )
        ax.set_title(f"target_after, processed ({method})")
        ax.set_xlabel("Trace index")
        ax.set_ylabel("Sample")

    ax_mask = fig.add_subplot(grid[1, 1])
    ax_mask.imshow(
        profile.target_mask[target_start:target_end, sample_lo:sample_hi].T,
        aspect="auto",
        cmap="gray_r",
        vmin=0,
        vmax=1,
        extent=extent,
        origin="upper",
    )
    ax_mask.set_title("target_mask (real target support)")
    ax_mask.set_xlabel("Trace index")
    ax_mask.set_ylabel("Sample")

    ax_trajectory = fig.add_subplot(grid[2, 0])
    trace_indices = np.arange(target_start, target_end)
    centers = profile.target_center_sample_by_trace[target_start:target_end]
    apex_trace = int(trace_indices[np.argmin(centers)])
    ax_trajectory.plot(trace_indices, centers, marker="o", color="tab:blue")
    ax_trajectory.axvline(apex_trace, color="black", linestyle="--", linewidth=0.8, label="apex")
    ax_trajectory.invert_yaxis()
    ax_trajectory.set_xlabel("Trace index")
    ax_trajectory.set_ylabel("Center sample")
    ax_trajectory.set_title("Center-sample trajectory (apex = shallowest sample)")
    ax_trajectory.legend(fontsize=8)

    ax_bars = fig.add_subplot(grid[2, 1])
    bar_labels = ["apex_retention", "arm_retention"]
    x = np.arange(len(bar_labels))
    width = 0.35
    for offset, method in zip((-width / 2, width / 2), ("sliding_mean", "sliding_median"), strict=True):
        values = [retention[method][key] for key in bar_labels]
        ax_bars.bar(x + offset, values, width=width, label=method)
    ax_bars.set_xticks(list(x))
    ax_bars.set_xticklabels(bar_labels)
    ax_bars.axhline(0.0, color="black", linewidth=0.6)
    ax_bars.set_ylabel("Mean-absolute retention (target-isolated)")
    ax_bars.set_title("Apex vs. arm retention")
    ax_bars.legend(fontsize=8)

    fig.suptitle(
        f"Paired-control localized hyperbola validation -- {target_end - target_start} target traces, "
        f"{unique_center_count} unique center samples, max shift {realized_max_shift} samples, "
        f"comparison window {window_traces} traces"
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def run_paired_control_target_attenuation_experiments(output_dir: Path) -> dict[str, Any]:
    """Paired-control (background+noise held identical) target-retention experiments.

    Covers, per the Sprint 4A.1 correction: target shorter/about-equal/longer
    than a fixed sliding window, for both ``sliding_mean`` and
    ``sliding_median``; a long-horizontal target for both ``global_mean`` and
    ``global_median`` (global methods have no window concept, so only the
    long-horizontal scenario applies to them); and a window-length sweep
    (mirroring ``run_synthetic_risk_experiments``'s sweep, but
    target-isolated) for both sliding methods. Writes
    ``paired_control_target_attenuation.csv`` and
    ``paired_control_window_length_vs_target_attenuation.png``.

    Sprint 4A.2 adds a dedicated ``localized_hyperbola`` scenario, evaluated
    separately from the rect-shaped scenario matrix above: ONE shared
    hyperbola profile (one control/with_target draw) is scored by both
    sliding methods, so the two methods' rows -- and the ``PAIRED_CONTROL_
    HYPERBOLA_VALIDATION.png`` panel built from the same profile -- are
    directly comparable rather than independently-drawn. See
    ``_paired_control_profile`` for the curvature fix (Sprint 4A.1's fixed
    ``curvature=0.03`` rounded every depth_shift to 0 for a short target,
    making the "hyperbola" practically flat).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260716)
    slices_count = _PAIRED_CONTROL_SLICES_COUNT
    samples_count = _PAIRED_CONTROL_SAMPLES_COUNT
    target_sample = _PAIRED_CONTROL_TARGET_SAMPLE
    comparison_window_traces = _PAIRED_CONTROL_COMPARISON_WINDOW_TRACES

    scenarios = [
        ("shorter_than_window", "rect", 5),
        ("approximately_equal_to_window", "rect", 15),
        ("longer_than_window", "rect", 45),
    ]

    rows: list[dict[str, Any]] = []
    for method in ("sliding_mean", "sliding_median"):
        for scenario_label, shape, target_length in scenarios:
            profile = _paired_control_profile(
                rng,
                slices_count,
                samples_count,
                target_length_traces=target_length,
                target_shape=shape,
                target_sample=target_sample,
            )
            metrics = _paired_control_retention_metrics(
                profile,
                method,
                {"window_traces": comparison_window_traces},
                "reflect",
            )
            rows.append(
                {
                    "method": method,
                    "scenario": scenario_label,
                    "target_length_traces": target_length,
                    "window_traces": comparison_window_traces,
                    **metrics,
                }
            )

    # Sprint 4A.2: localized hyperbola, one shared profile scored by both sliding methods.
    hyperbola_target_length_traces = 15
    hyperbola_profile = _paired_control_profile(
        rng,
        slices_count,
        samples_count,
        target_length_traces=hyperbola_target_length_traces,
        target_shape="hyperbola",
        target_sample=target_sample,
        requested_max_shift_samples=_HYPERBOLA_DEFAULT_MAX_SHIFT_SAMPLES,
    )
    hyperbola_diagnostic_columns = {
        f"hyperbola_{key}": value
        for key, value in hyperbola_profile.shape_diagnostics.items()
        if key != "target_shape"
    }
    for method in ("sliding_mean", "sliding_median"):
        metrics = _paired_control_retention_metrics(
            hyperbola_profile,
            method,
            {"window_traces": comparison_window_traces},
            "reflect",
        )
        rows.append(
            {
                "method": method,
                "scenario": "localized_hyperbola",
                "target_length_traces": hyperbola_target_length_traces,
                "window_traces": comparison_window_traces,
                **metrics,
                **hyperbola_diagnostic_columns,
            }
        )

    hyperbola_validation_png = _save_paired_control_hyperbola_validation_panel(
        hyperbola_profile,
        comparison_window_traces,
        output_dir / "PAIRED_CONTROL_HYPERBOLA_VALIDATION.png",
    )

    # Long-horizontal scenario: run for every method, including global (no window).
    long_horizontal_length = 55
    for method in ("sliding_mean", "sliding_median", "global_mean", "global_median"):
        profile = _paired_control_profile(
            rng,
            slices_count,
            samples_count,
            target_length_traces=long_horizontal_length,
            target_shape="rect",
            target_sample=target_sample,
        )
        window_kwargs = (
            {"window_traces": comparison_window_traces}
            if method in ("sliding_mean", "sliding_median")
            else {}
        )
        metrics = _paired_control_retention_metrics(profile, method, window_kwargs, "reflect")
        rows.append(
            {
                "method": method,
                "scenario": "long_horizontal",
                "target_length_traces": long_horizontal_length,
                "window_traces": comparison_window_traces if window_kwargs else None,
                **metrics,
            }
        )

    attenuation_df = pd.DataFrame(rows)
    csv_path = output_dir / "paired_control_target_attenuation.csv"
    attenuation_df.to_csv(csv_path, index=False)

    # Window-length sweep, paired-control (sliding methods only -- global has no window).
    window_options = [5, 9, 15, 25, 37, 51]
    sweep_target_lengths = {"shorter_than_window": 5, "about_window": 15, "longer_than_window": 45}
    sweep_rows: list[dict[str, Any]] = []
    for method in ("sliding_mean", "sliding_median"):
        for target_label, target_length in sweep_target_lengths.items():
            profile = _paired_control_profile(
                rng,
                slices_count,
                samples_count,
                target_length_traces=target_length,
                target_shape="rect",
                target_sample=target_sample,
            )
            for window_traces in window_options:
                if window_traces >= slices_count:
                    continue
                metrics = _paired_control_retention_metrics(
                    profile,
                    method,
                    {"window_traces": window_traces},
                    "reflect",
                )
                sweep_rows.append(
                    {
                        "method": method,
                        "target_length_category": target_label,
                        "target_length_traces": target_length,
                        "window_traces": window_traces,
                        **metrics,
                    }
                )
    sweep_df = pd.DataFrame(sweep_rows)

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), sharey=True)
    cmap = plt.get_cmap("tab10")
    for ax, method in zip(axes, ("sliding_mean", "sliding_median"), strict=True):
        for i, target_label in enumerate(sweep_target_lengths):
            subset = sweep_df[
                (sweep_df["method"] == method) & (sweep_df["target_length_category"] == target_label)
            ]
            ax.plot(
                subset["window_traces"],
                subset["full_target_energy_retention"],
                marker="o",
                color=cmap(i),
                label=target_label,
            )
        ax.set_xlabel("Sliding window (traces)")
        ax.set_title(method)
        ax.axhline(0.0, color="black", linewidth=0.6)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("Paired-control target energy retention (target-isolated, full target-mask support)")
    fig.suptitle("Window length vs. paired-control target-energy retention (synthetic, target-isolated)")
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    plot_path = output_dir / "paired_control_window_length_vs_target_attenuation.png"
    fig.savefig(plot_path, dpi=140)
    plt.close(fig)

    return {
        "paired_control_target_attenuation_csv": csv_path,
        "paired_control_window_length_vs_target_attenuation_png": plot_path,
        "paired_control_hyperbola_validation_png": hyperbola_validation_png,
        "rows": rows,
    }


#: Short/long synthetic target lengths used when scoring each REAL candidate's
#: own method/window against the paired-control profiles (distinct from the
#: scenario matrix above, which explores window-length sensitivity in the
#: abstract). Both share one background+noise realization across every
#: candidate, so retention differences are attributable to the candidate's
#: own method/window choice, not independent random noise draws.
_PAIRED_CONTROL_CANDIDATE_SHORT_TARGET_TRACES = 5
_PAIRED_CONTROL_CANDIDATE_LONG_TARGET_TRACES = 55


def compute_paired_control_retention_for_candidates(
    candidates_info: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Apply each real candidate's own method/window to shared short- and long-target scenarios.

    Returns ``{candidate_id: {"paired_control_short_target_retention": ...,
    "paired_control_long_target_retention": ...}}``. This is the per-real-
    candidate counterpart of ``run_paired_control_target_attenuation_
    experiments`` -- it answers "how would THIS candidate's own method and
    window treat a short vs. a long synthetic target", using
    ``full_target_energy_retention`` from :func:`_paired_control_retention_metrics`.
    Global methods use no window (``window_kwargs={}``); their retention
    reflects the global-mean/median estimator itself, not a window choice.
    """
    rng = np.random.default_rng(20260717)
    slices_count = _PAIRED_CONTROL_SLICES_COUNT
    samples_count = _PAIRED_CONTROL_SAMPLES_COUNT
    target_sample = _PAIRED_CONTROL_TARGET_SAMPLE

    short_profile = _paired_control_profile(
        rng,
        slices_count,
        samples_count,
        target_length_traces=_PAIRED_CONTROL_CANDIDATE_SHORT_TARGET_TRACES,
        target_shape="rect",
        target_sample=target_sample,
    )
    long_profile = _paired_control_profile(
        rng,
        slices_count,
        samples_count,
        target_length_traces=_PAIRED_CONTROL_CANDIDATE_LONG_TARGET_TRACES,
        target_shape="rect",
        target_sample=target_sample,
    )

    per_candidate: dict[str, dict[str, float]] = {}
    for info in candidates_info:
        diag = info["result"].diagnostics
        method = diag["method"]
        edge_mode = diag["edge_mode"] if diag["edge_mode"] != "not_applicable" else "reflect"
        window_kwargs = (
            {"window_traces": diag["applied_window_traces"]} if diag["applied_window_traces"] else {}
        )

        short_metrics = _paired_control_retention_metrics(short_profile, method, window_kwargs, edge_mode)
        long_metrics = _paired_control_retention_metrics(long_profile, method, window_kwargs, edge_mode)
        per_candidate[info["id"]] = {
            "paired_control_short_target_retention": short_metrics["full_target_energy_retention"],
            "paired_control_long_target_retention": long_metrics["full_target_energy_retention"],
        }
    return per_candidate


#: Documented QC-flag threshold (not a physical claim) -- a candidate ranked
#: "preservation-favoring" by overall RMS retention alone whose paired-
#: control long-target retention falls below this is flagged as a conflict
#: rather than silently trusted.
_PAIRED_CONTROL_LONG_TARGET_CONFLICT_THRESHOLD = 0.3


#: Sprint 4A.2: A0 is a decision/QC-layer REFERENCE POLICY, not a filter
#: candidate. It never runs through ``remove_background()``, never produces
#: a ``ProcessingResult``/NPZ, and never appears in a B-scan montage (no
#: real dataset or removed_component exists for it). It exists only in the
#: final decision table, the metrics summary panel, and ``candidate_metrics.
#: csv`` -- so a human reviewer always sees "do nothing" as an explicit,
#: literal option, never silently defaulted-past.
_A0_ID = "A0"
_A0_LABEL = "no_background_removal"


def _a0_reference_policy_metrics() -> dict[str, Any]:
    """The fixed, hand-authored A0 metric values (never measured -- see module note above).

    Retention of an unprocessed signal against itself is exactly 1.0 by
    definition; suppression of nothing removed is exactly 0; a filter that
    was never applied has no timing shift, no removed component, and
    cannot have corrupted padding. These are definitional constants, not
    measurements, and must never be written into a ``ProcessingResult`` or
    NPZ.
    """
    return {
        "overall_rms_retention_tendency": 1.0,
        "paired_control_short_target_retention": 1.0,
        "paired_control_long_target_retention": 1.0,
        "local_event_amplitude_retention": 1.0,
        "removed_coherent_event_risk_proxy": "not_applicable",
        "background_suppression": 0.0,
        "waveform_correlation": 1.0,
        "spectral_retention": 1.0,
        "padding_safety": "unchanged",
        "timing_preservation": "0 sample lag",
        "removed_component": "not_applicable",
        "processing_applied": False,
        "type": "reference_policy",
        "label": _A0_LABEL,
    }


def _engineering_interpretation_notes(
    candidates_info: list[dict[str, Any]],
    categories: dict[str, str],
    paired_control_by_id: dict[str, dict[str, float]],
    window_label: str = "W5",
) -> dict[str, str]:
    """Per-candidate interpretation text: category + the metric it is based on + any conflict flag.

    ``categories`` (see ``_engineering_category``) is driven ONLY by
    ``overall_rms_retention_tendency`` -- this makes that basis explicit in
    the text itself, and cross-checks it against ``paired_control_long_
    target_retention``: if a candidate is ranked "preservation-favoring" by
    RMS alone yet still strongly attenuates a long synthetic target, that
    disagreement is reported directly rather than presenting RMS retention
    as equivalent to archaeological-target preservation.

    Sprint 4A.2: "preservation-favoring" candidates additionally get an
    explicit textual comparison against A0 (no background removal, whose
    own overall_rms_retention_tendency and paired-control retentions are
    fixed at 1.0 by definition) -- this makes clear that the label is only
    a RELATIVE ranking among A1-A8, never a claim of preserving more than
    doing nothing at all.
    """
    a0 = _a0_reference_policy_metrics()
    notes: dict[str, str] = {}
    for info in candidates_info:
        candidate_id = info["id"]
        rms = info["signal_preservation"][window_label]["rms_retention"]
        category = categories[candidate_id]
        long_retention = paired_control_by_id.get(candidate_id, {}).get(
            "paired_control_long_target_retention", float("nan")
        )
        base = f"{category} (basis: overall_rms_retention_tendency={rms:.3g} only)"
        if (
            category == "preservation-favoring"
            and np.isfinite(long_retention)
            and long_retention < _PAIRED_CONTROL_LONG_TARGET_CONFLICT_THRESHOLD
        ):
            notes[candidate_id] = (
                f"{base}; CONFLICTS with paired_control_long_target_retention={long_retention:.3g} -- "
                "high overall RMS retention does NOT mean long synthetic targets survive this candidate; "
                f"compare against {_A0_ID} ({_A0_LABEL}): its own overall_rms_retention_tendency="
                f"{a0['overall_rms_retention_tendency']:.3g} and paired_control_long_target_retention="
                f"{a0['paired_control_long_target_retention']:.3g} are both >= this candidate's -- "
                "'preservation-favoring' is only a ranking among A1-A8, not evidence of preserving "
                "more than doing nothing"
            )
        elif category == "preservation-favoring":
            notes[candidate_id] = (
                f"{base}; compare against {_A0_ID} ({_A0_LABEL}): its own overall_rms_retention_tendency="
                f"{a0['overall_rms_retention_tendency']:.3g} is still >= this candidate's "
                f"({rms:.3g}) -- 'preservation-favoring' is only a ranking among A1-A8, not evidence of "
                "preserving more than doing nothing"
            )
        else:
            notes[candidate_id] = base
    return notes


# ======================================================================
# Cross-candidate comparison
# ======================================================================


def save_common_scale_output_comparison(
    dataset: GPRDataset,
    candidates_info: list[dict[str, Any]],
    output_path: Path,
    *,
    channels: tuple[int, ...] = CANDIDATE_CHANNELS,
    comparison_window_ns: tuple[float, float] = COMPARISON_WINDOW_NS,
    clip_percentile: float = 99.0,
) -> Path:
    """Cross-candidate output B-scan montage: input + A1-A8, one shared scale per channel row.

    Sprint 4A.1 correction (see ADR-008): the original decision-panel detail
    view gave each candidate's B-scan its own independently computed
    percentile scale, which makes visual candidate comparison meaningless --
    a candidate that removed almost everything and one that removed almost
    nothing can look identically "clean" once each is stretched to its own
    range. Here every panel in one channel's row (the canonical Sprint 3
    input plus all 8 candidate outputs) shares exactly one symmetric scale,
    computed once from that channel's input and every candidate's output
    pooled together via :func:`compute_shared_clip_limit` -- no panel is
    normalized independently.
    """
    start_ns, end_ns = comparison_window_ns
    sample_mask = (dataset.time_ns >= start_ns) & (dataset.time_ns < end_ns)
    n_cols = 1 + len(candidates_info)
    fig, axes = plt.subplots(
        len(channels), n_cols, figsize=(2.4 * n_cols, 4.0 * len(channels)), squeeze=False
    )

    for row, channel in enumerate(channels):
        input_windowed = dataset.amplitudes[:, channel, sample_mask].astype(np.float64)
        candidate_windowed = [
            info["result"].dataset.amplitudes[:, channel, sample_mask].astype(np.float64)
            for info in candidates_info
        ]
        shared_limit = compute_shared_clip_limit(
            input_windowed, *candidate_windowed, clip_percentile=clip_percentile
        )
        extent = (0.0, float(input_windowed.shape[0]), end_ns, start_ns)

        ax = axes[row][0]
        ax.imshow(
            input_windowed.T,
            aspect="auto",
            cmap="seismic",
            vmin=-shared_limit,
            vmax=shared_limit,
            extent=extent,
            origin="upper",
        )
        ax.set_title("input" if row > 0 else f"input\n(±{shared_limit:.3g})", fontsize=8)
        ax.set_ylabel(f"Ch{channel:02d}\ntime_ns", fontsize=8)
        if row == len(channels) - 1:
            ax.set_xlabel("Slice")

        for col, (info, windowed) in enumerate(
            zip(candidates_info, candidate_windowed, strict=True), start=1
        ):
            ax = axes[row][col]
            ax.imshow(
                windowed.T,
                aspect="auto",
                cmap="seismic",
                vmin=-shared_limit,
                vmax=shared_limit,
                extent=extent,
                origin="upper",
            )
            ax.set_title(info["id"] if row > 0 else f"{info['id']}\n(shared)", fontsize=8)
            ax.set_yticklabels([])
            if row == len(channels) - 1:
                ax.set_xlabel("Slice")

    fig.suptitle(
        f"Background-removal output comparison, {start_ns:g}-{end_ns:g} ns -- input + A1-A8,\n"
        "one shared symmetric amplitude scale per channel row (Sprint 4A.1 correction, ADR-008)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def save_common_scale_removed_comparison(
    dataset: GPRDataset,
    candidates_info: list[dict[str, Any]],
    output_path: Path,
    *,
    channels: tuple[int, ...] = CANDIDATE_CHANNELS,
    comparison_window_ns: tuple[float, float] = COMPARISON_WINDOW_NS,
    clip_percentile: float = 99.0,
) -> Path:
    """Cross-candidate removed-component B-scan montage: A1-A8, one shared scale per channel row.

    Same common-scale correction as :func:`save_common_scale_output_comparison`,
    applied to ``result.removed_component`` instead of the output -- lets a
    reviewer see directly whether a candidate's removed component looks like
    a flat, laterally continuous baseline or a localized/curved event,
    without one candidate's own independent color stretch hiding the
    comparison.
    """
    start_ns, end_ns = comparison_window_ns
    sample_mask = (dataset.time_ns >= start_ns) & (dataset.time_ns < end_ns)
    n_cols = len(candidates_info)
    fig, axes = plt.subplots(
        len(channels), n_cols, figsize=(2.4 * n_cols, 4.0 * len(channels)), squeeze=False
    )

    for row, channel in enumerate(channels):
        removed_windowed = [
            info["result"].removed_component[:, channel, sample_mask].astype(np.float64)
            for info in candidates_info
        ]
        shared_limit = compute_shared_clip_limit(*removed_windowed, clip_percentile=clip_percentile)
        extent = (0.0, float(removed_windowed[0].shape[0]), end_ns, start_ns)

        for col, (info, windowed) in enumerate(zip(candidates_info, removed_windowed, strict=True)):
            ax = axes[row][col]
            ax.imshow(
                windowed.T,
                aspect="auto",
                cmap="seismic",
                vmin=-shared_limit,
                vmax=shared_limit,
                extent=extent,
                origin="upper",
            )
            ax.set_title(info["id"] if row > 0 else f"{info['id']}\n(shared)", fontsize=8)
            if col == 0:
                ax.set_ylabel(f"Ch{channel:02d}\ntime_ns", fontsize=8)
            else:
                ax.set_yticklabels([])
            if row == len(channels) - 1:
                ax.set_xlabel("Slice")

    fig.suptitle(
        f"Removed-component comparison, {start_ns:g}-{end_ns:g} ns -- A1-A8,\n"
        "one shared symmetric amplitude scale per channel row (Sprint 4A.1 correction, ADR-008)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


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

    # --- channelNN_median_trace_all_candidates_20_100ns.png: median-trace overlay --
    # (Sprint 4A.1: renamed from "..._all_candidates_20_100ns.png" -- this is a
    # median-trace line overlay, not a B-scan; see save_common_scale_output_comparison
    # for the actual cross-candidate B-scan montage.)
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
        path = comparison_dir / f"channel{channel:02d}_median_trace_all_candidates_20_100ns.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        paths[f"channel{channel:02d}_median_trace_all_candidates_20_100ns"] = path

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

    # --- Sprint 4A.1: paired-control (target-isolated) synthetic experiments ---
    paired_control_synthetic = run_paired_control_target_attenuation_experiments(comparison_dir)
    paths.update(
        {
            "paired_control_target_attenuation_csv": Path(
                paired_control_synthetic["paired_control_target_attenuation_csv"]
            ),
            "paired_control_window_length_vs_target_attenuation": Path(
                paired_control_synthetic["paired_control_window_length_vs_target_attenuation_png"]
            ),
        }
    )

    # --- candidate_metrics*.csv ---------------------------------------------
    # A0 (no background removal) is a hand-authored reference-policy row, never
    # derived from a ProcessingResult -- it appears ONLY here, in the decision
    # table, and in the metrics summary panel (Sprint 4A.2; see ADR-008).
    a0 = _a0_reference_policy_metrics()
    overall_rows = [
        {
            "id": _A0_ID,
            "label": a0["label"],
            "type": a0["type"],
            "method": _A0_LABEL,
            "processing_applied": a0["processing_applied"],
            "applied_window_traces": None,
            "applied_window_m": None,
            "applied_window_nominal_length_m": None,
            "applied_window_center_to_center_span_m": None,
            "window_half_span_m": None,
            "overall_rms_retention_tendency": a0["overall_rms_retention_tendency"],
            "spectral_energy_retention_w5": a0["spectral_retention"],
            "waveform_correlation_median_w5": a0["waveform_correlation"],
            "local_event_amplitude_retention_w5": a0["local_event_amplitude_retention"],
            "median_trace_cross_correlation_lag_w5": None,
            "timing_preservation": a0["timing_preservation"],
            "removed_input_rms_ratio_w5": a0["background_suppression"],
            "removed_input_energy_ratio_w5": a0["background_suppression"],
            "removed_coherent_event_risk_proxy_w5": a0["removed_coherent_event_risk_proxy"],
            "removed_component": a0["removed_component"],
            "padding_safety": a0["padding_safety"],
            "paired_control_short_target_retention": a0["paired_control_short_target_retention"],
            "paired_control_long_target_retention": a0["paired_control_long_target_retention"],
            "engineering_category": "not_applicable (reference_policy, not ranked against A1-A8)",
            "engineering_interpretation": (
                f"{_A0_LABEL}: no filter applied; not a candidate; retention=1.0 and suppression=0 "
                "by definition, not measurement"
            ),
        }
    ]
    by_channel_rows = []
    by_window_rows = []
    categories = _engineering_category(candidates_info)
    paired_control_by_id = compute_paired_control_retention_for_candidates(candidates_info)
    interpretation_notes = _engineering_interpretation_notes(
        candidates_info, categories, paired_control_by_id
    )
    for info in candidates_info:
        diag = info["result"].diagnostics
        paired = paired_control_by_id[info["id"]]
        overall_rows.append(
            {
                "id": info["id"],
                "label": info["label"],
                "type": "candidate",
                "method": info["method"],
                "processing_applied": True,
                "applied_window_traces": diag["applied_window_traces"],
                "applied_window_m": diag["applied_window_m"],
                "applied_window_nominal_length_m": diag["applied_window_nominal_length_m"],
                "applied_window_center_to_center_span_m": diag["applied_window_center_to_center_span_m"],
                "window_half_span_m": diag["window_half_span_m"],
                "overall_rms_retention_tendency": info["signal_preservation"][w5]["rms_retention"],
                "spectral_energy_retention_w5": info["signal_preservation"][w5]["spectral_energy_retention"],
                "waveform_correlation_median_w5": info["signal_preservation"][w5][
                    "waveform_correlation_median"
                ],
                "local_event_amplitude_retention_w5": info["signal_preservation"][w5][
                    "local_event_amplitude_retention"
                ],
                "median_trace_cross_correlation_lag_w5": info["signal_preservation"][w5][
                    "median_trace_cross_correlation_lag"
                ],
                "removed_input_rms_ratio_w5": info["removed_metrics"][w5]["removed_input_rms_ratio"],
                "removed_input_energy_ratio_w5": info["removed_metrics"][w5]["removed_input_energy_ratio"],
                "removed_coherent_event_risk_proxy_w5": info["removed_metrics"][w5][
                    "adjacent_trace_correlation_median"
                ],
                "paired_control_short_target_retention": paired["paired_control_short_target_retention"],
                "paired_control_long_target_retention": paired["paired_control_long_target_retention"],
                "engineering_category": categories[info["id"]],
                "engineering_interpretation": interpretation_notes[info["id"]],
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
    review_path.write_text(
        _background_review_markdown(candidates_info, paired_control_by_id, interpretation_notes),
        encoding="utf-8",
    )
    paths["review"] = review_path

    return paths


def _background_review_markdown(
    candidates_info: list[dict[str, Any]],
    paired_control_by_id: dict[str, dict[str, float]],
    interpretation_notes: dict[str, str],
) -> str:
    w5 = "W5"
    header_row = (
        "| ID | Label | Method | Applied window (traces) | Overall RMS retention tendency | "
        "Paired-control long-target retention | Removed coherent-event risk proxy | Interpretation |"
    )
    rows = "\n".join(
        f"| {info['id']} | {info['label']} | {info['method']} | "
        f"{info['result'].diagnostics['applied_window_traces']} | "
        f"{info['signal_preservation'][w5]['rms_retention']:.4g} | "
        f"{paired_control_by_id[info['id']]['paired_control_long_target_retention']:.4g} | "
        f"{info['removed_metrics'][w5]['adjacent_trace_correlation_median']:.4g} | "
        f"{interpretation_notes[info['id']]} |"
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

`Overall RMS retention tendency` is a transparent, relative ranking by
measured RMS retention across these 8 candidates on this dataset only (see
``sprint4a_candidates.py::_engineering_category``) -- it is NOT
archaeological-target preservation, is not a canonical selection, and does
not transfer to a different dataset. `Removed coherent-event risk proxy`
is the removed component's own adjacent-trace coherence, reported
directly -- a high value means the removed component is spatially
continuous, not that it is (or is not) a real reflection. `Interpretation`
states the single metric the category is based on and flags any conflict
against the paired-control long-target retention (see
`paired_control_target_attenuation.csv`).

See `../../BACKGROUND_OUTPUT_COMPARISON_CH00_CH05_CH10.png`,
`../../BACKGROUND_REMOVED_COMPARISON_CH00_CH05_CH10.png`,
`../../BACKGROUND_METRICS_SUMMARY.png`, and
`../../BACKGROUND_FINAL_DECISION_REQUIRED.md` for the full, common-scale
decision package. `BACKGROUND_DECISION_PANEL.png`/`_DETAIL.png` are kept
for historical compatibility only.
"""


# ======================================================================
# Decision panel and final human-decision report
# ======================================================================


def save_background_metrics_summary_panel(
    candidates_info: list[dict[str, Any]],
    paired_control_by_id: dict[str, dict[str, float]],
    output_path: Path,
    *,
    window_label: str = "W5",
) -> Path:
    """Metrics-only summary panel (bar charts, no B-scans) -- Sprint 4A.1 correction, ADR-008.

    Deliberately separate from the B-scan montages
    (:func:`save_common_scale_output_comparison`/
    :func:`save_common_scale_removed_comparison`) so numeric evidence and
    visual evidence can be reviewed independently. Shows every metric that
    feeds a candidate's engineering interpretation: ``overall_rms_
    retention_tendency``, paired-control short/long synthetic-target
    retention, local-event amplitude retention, the removed coherent-event
    risk proxy, background suppression, waveform correlation, and spectral
    retention. None of these, individually or together, select a canonical
    candidate.

    Sprint 4A.2: an ``A0`` (no background removal) reference bar is added to
    every panel except ``removed_coherent_event_risk_proxy`` (A0 has no real
    removed component, so that panel stays A1-A8 only), separated from the
    real candidates by a dotted line -- A0 never appears in the B-scan
    montages (no real dataset exists for it), so this panel and the final
    decision table are the only places it can be visually compared at all.
    """
    ids = [info["id"] for info in candidates_info]
    ids_with_a0 = ids + [_A0_ID]
    cmap = plt.get_cmap("tab10")
    a0_color = "gray"
    w5 = window_label
    a0 = _a0_reference_policy_metrics()

    panels = [
        (
            "overall_rms_retention_tendency",
            [info["signal_preservation"][w5]["rms_retention"] for info in candidates_info]
            + [a0["overall_rms_retention_tendency"]],
        ),
        (
            "paired_control_short_target_retention",
            [paired_control_by_id[i]["paired_control_short_target_retention"] for i in ids]
            + [a0["paired_control_short_target_retention"]],
        ),
        (
            "paired_control_long_target_retention",
            [paired_control_by_id[i]["paired_control_long_target_retention"] for i in ids]
            + [a0["paired_control_long_target_retention"]],
        ),
        (
            "local_event_amplitude_retention",
            [info["signal_preservation"][w5]["local_event_amplitude_retention"] for info in candidates_info]
            + [a0["local_event_amplitude_retention"]],
        ),
        (
            "removed_coherent_event_risk_proxy",
            [info["removed_metrics"][w5]["adjacent_trace_correlation_median"] for info in candidates_info],
        ),
        (
            "background_suppression",
            [info["removed_metrics"][w5]["removed_input_rms_ratio"] for info in candidates_info]
            + [a0["background_suppression"]],
        ),
        (
            "waveform_correlation",
            [info["signal_preservation"][w5]["waveform_correlation_median"] for info in candidates_info]
            + [a0["waveform_correlation"]],
        ),
        (
            "spectral_retention",
            [info["signal_preservation"][w5]["spectral_energy_retention"] for info in candidates_info]
            + [a0["spectral_retention"]],
        ),
    ]

    fig, axes = plt.subplots(2, 4, figsize=(20, 9))
    for ax, (label, values) in zip(axes.ravel(), panels, strict=True):
        has_a0 = label != "removed_coherent_event_risk_proxy"
        panel_ids = ids_with_a0 if has_a0 else ids
        colors = [cmap(i) for i in range(len(ids))] + ([a0_color] if has_a0 else [])
        ax.bar(panel_ids, values, color=colors)
        ax.set_title(label, fontsize=9)
        if has_a0:
            ax.axvline(len(ids) - 0.5, color="black", linestyle=":", linewidth=0.6)
        ax.axhline(0.0, color="black", linewidth=0.6)
        ax.tick_params(axis="x", labelsize=8)
    fig.suptitle(
        "Sprint 4A.2 background-removal metrics summary (W5 = 20-100 ns, post-direct-wave)\n"
        f"{_A0_ID} = {_A0_LABEL} (reference policy, not a filter candidate) -- no candidate, "
        "including A0, is selected as canonical\n"
        "Overall RMS retention is NOT archaeological-target preservation; the removed "
        "coherent-event risk proxy is NOT a signal/noise classifier (A0 has no removed component)",
        fontsize=10.5,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.88))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def save_decision_panel(
    dataset: GPRDataset,
    candidates_info: list[dict[str, Any]],
    output_path: Path,
    detail_output_path: Path,
) -> tuple[Path, Path]:
    """Save the two-page Sprint 4A decision panel (summary + detail B-scans).

    Kept for historical compatibility. Sprint 4A.1 correction: each panel
    here still uses its own historical (non-shared) scale -- for a
    common-scale, apples-to-apples visual comparison, see
    ``BACKGROUND_OUTPUT_COMPARISON_CH00_CH05_CH10.png``,
    ``BACKGROUND_REMOVED_COMPARISON_CH00_CH05_CH10.png``, and
    ``BACKGROUND_METRICS_SUMMARY.png`` instead.
    """
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
        "No candidate selected as canonical -- human/geophysical review required.\n"
        "Sprint 4A.1 correction: see BACKGROUND_OUTPUT_COMPARISON_CH00_CH05_CH10.png, "
        "BACKGROUND_REMOVED_COMPARISON_CH00_CH05_CH10.png, and BACKGROUND_METRICS_SUMMARY.png "
        "for the common-scale comparison used for human review.",
        fontsize=11,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.91))
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
        f"Channel {CANDIDATE_CHANNELS[0]:02d}, {start_ns:g}-{end_ns:g} ns -- all candidates (detail)\n"
        "Each panel here uses its OWN independent percentile scale (historical; kept for\n"
        "compatibility) -- NOT suitable for cross-candidate comparison. See\n"
        "BACKGROUND_OUTPUT_COMPARISON_CH00_CH05_CH10.png for the common-scale version.",
        fontsize=10,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.87))
    detail_output_path = Path(detail_output_path)
    detail_output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(detail_output_path, dpi=150)
    plt.close(fig)

    return output_path, detail_output_path


def write_background_final_decision_required(
    candidates_info: list[dict[str, Any]],
    categories: dict[str, str],
    paired_control_by_id: dict[str, dict[str, float]],
    interpretation_notes: dict[str, str],
    output_path: Path,
) -> Path:
    """Write ``BACKGROUND_FINAL_DECISION_REQUIRED.md`` -- criteria table, no canonical pick.

    Sprint 4A.1 correction (see ADR-008): the previous version of this
    table (a) presented ``applied_window_m`` as a physical span rather than
    a nominal length, (b) derived a ``long_horizontal_event_preservation``
    "preservation fraction" from ``1 - removed_component_coherence``, which
    invites reading the coherence proxy as a direct preservation
    measurement, and (c) labeled a purely RMS-retention-based ranking
    "engineering category" without stating that basis or checking it
    against any target-preservation evidence. All three are fixed here:
    nominal length and center-to-center span are reported as separate
    columns; the removed-component coherence is reported directly as a
    risk *proxy*, never as a preservation fraction; and the RMS-based
    ranking is reported as ``overall_rms_retention_tendency`` with an
    explicit rationale string (``interpretation_notes``) that flags any
    conflict against the paired-control long-target retention.

    Sprint 4A.2 (see ADR-008 addendum): adds an ``A0`` row -- the
    no-background-removal reference policy, fixed values from
    :func:`_a0_reference_policy_metrics`, never a measured
    ``ProcessingResult`` -- ahead of A1-A8, so a human reviewer sees "do
    nothing" as an explicit, literal, always-available option rather than
    one silently excluded from the comparison.
    """
    w5 = "W5"
    header = [
        "Candidate",
        "Method",
        "Requested window",
        "Applied trace count",
        "Nominal window length",
        "Center-to-center spatial span",
        "Background suppression",
        "Overall RMS retention",
        "Waveform correlation",
        "Spectral retention",
        "Local-event amplitude retention",
        "Paired-control short-target retention",
        "Paired-control long-target retention",
        "Removed coherent-event risk proxy",
        "Padding safety",
        "Timing preservation",
        "Engineering interpretation",
        "Main risk",
    ]
    a0 = _a0_reference_policy_metrics()
    rows = [
        "| "
        + " | ".join(
            [
                _A0_ID,
                _A0_LABEL,
                "n/a (no filter applied)",
                "n/a",
                "n/a",
                "n/a",
                f"{a0['background_suppression']:.4g}",
                f"{a0['overall_rms_retention_tendency']:.4g}",
                f"{a0['waveform_correlation']:.4g}",
                f"{a0['spectral_retention']:.4g}",
                f"{a0['local_event_amplitude_retention']:.4g}",
                f"{a0['paired_control_short_target_retention']:.4g}",
                f"{a0['paired_control_long_target_retention']:.4g}",
                str(a0["removed_coherent_event_risk_proxy"]),
                str(a0["padding_safety"]),
                str(a0["timing_preservation"]),
                (
                    "reference_policy (no_background_removal); NOT ranked by "
                    "overall_rms_retention_tendency and NOT compared against the too_weak/"
                    "too_aggressive/preservation-favoring/balanced/suppression-favoring scale "
                    "used for A1-A8"
                ),
                (
                    "raw common-mode background, drift, and system noise are NOT suppressed; "
                    "downstream analysis must tolerate the full unprocessed signal"
                ),
            ]
        )
        + " |"
    ]
    for info in candidates_info:
        candidate_id = info["id"]
        diag = info["result"].diagnostics
        sp = info["signal_preservation"][w5]
        rm = info["removed_metrics"][w5]
        paired = paired_control_by_id[candidate_id]
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
            if categories[candidate_id] == "too_weak"
            else "may remove real, laterally continuous reflections"
            if categories[candidate_id] in ("too_aggressive", "suppression-favoring")
            else "moderate risk to long horizontal reflections; review removed-component panels"
        )
        rows.append(
            "| "
            + " | ".join(
                [
                    candidate_id,
                    info["method"],
                    requested,
                    str(diag["applied_window_traces"]) if diag["applied_window_traces"] else "n/a",
                    (
                        f"{diag['applied_window_nominal_length_m']:.4g} m"
                        if diag["applied_window_nominal_length_m"] is not None
                        else "n/a"
                    ),
                    (
                        f"{diag['applied_window_center_to_center_span_m']:.4g} m"
                        if diag["applied_window_center_to_center_span_m"] is not None
                        else "n/a"
                    ),
                    f"{rm['removed_input_rms_ratio']:.4g}",
                    f"{sp['rms_retention']:.4g}",
                    f"{sp['waveform_correlation_median']:.4g}",
                    f"{sp['spectral_energy_retention']:.4g}",
                    f"{sp['local_event_amplitude_retention']:.4g}",
                    f"{paired['paired_control_short_target_retention']:.4g}",
                    f"{paired['paired_control_long_target_retention']:.4g}",
                    f"{rm['adjacent_trace_correlation_median']:.4g}",
                    "ok",
                    str(sp["median_trace_cross_correlation_lag"]),
                    interpretation_notes[candidate_id],
                    main_risk,
                ]
            )
            + " |"
        )

    long_retentions = [
        paired_control_by_id[info["id"]]["paired_control_long_target_retention"] for info in candidates_info
    ]
    all_candidates_strongly_attenuate_long_target = bool(long_retentions) and all(
        np.isfinite(r) and r < _PAIRED_CONTROL_LONG_TARGET_CONFLICT_THRESHOLD for r in long_retentions
    )
    long_target_disclaimer = (
        "**All A1-A8 candidates strongly attenuate the paired-control long target "
        f"(paired_control_long_target_retention < {_PAIRED_CONTROL_LONG_TARGET_CONFLICT_THRESHOLD:g} "
        "for every candidate on this dataset).**"
        if all_candidates_strongly_attenuate_long_target
        else "**Paired-control long-target retention varies across A1-A8 on this dataset -- see the table.**"
    )

    content = f"""# BACKGROUND_FINAL_DECISION_REQUIRED

**Status: review_required**
**No background-removal candidate has been selected as canonical.**
**A0 is the no-background-removal reference.**
**A0 is not a new filter method.**
{long_target_disclaimer}
**High overall RMS retention does not imply long-target preservation.**
**Human reviewer may select "no background removal".**
**No canonical decision is made automatically.**
**Gain has not started.**
**Overall RMS retention is not equivalent to archaeological-target preservation.**
**Removed-component coherence (the "removed coherent-event risk proxy") is
not a direct signal/noise classifier.**
**Human review requires the common-scale B-scans, not this table alone -- A0
has no B-scan of its own (no processing was applied), so its row here and in
`BACKGROUND_METRICS_SUMMARY.png` is the only place it can be compared.**

| {" | ".join(header)} |
|{"---|" * len(header)}
{chr(10).join(rows)}

## How to read this table

- **Nominal window length** vs. **center-to-center spatial span** are
  DIFFERENT things: nominal length = applied trace count * trace spacing
  (kept for backward compatibility as `applied_window_m` in the JSON
  exports, but that name is ambiguous and deprecated); center-to-center
  span = (applied trace count - 1) * trace spacing -- the actual physical
  distance between the window's first and last trace. See ADR-008
  (Sprint 4A.1 correction).
- **Overall RMS retention** is a single aggregate number (this candidate's
  W5 output RMS divided by the input's) -- it says nothing about whether
  any *specific* real or synthetic target survives; a candidate can retain
  most of the profile's RMS energy while still nearly erasing a target
  whose length approaches or exceeds the sliding window. See the two
  paired-control columns for a target-isolated measurement instead.
- **Paired-control short/long-target retention** come from
  `paired_control_target_attenuation.csv` -- each candidate's own method
  and window applied to a SYNTHETIC scenario where a short (5-trace) or
  long (55-trace) target is added to an otherwise identical background+
  noise realization, then isolated by subtraction (`target_after =
  processed_with_target - processed_control`). This is the direct,
  target-isolated measurement that `overall_rms_retention_tendency` is
  NOT.
- **Removed coherent-event risk proxy** is the removed component's own
  adjacent-trace correlation, reported directly (never as `1 -
  coherence`, and never as a "preservation fraction"). A HIGH value means
  the removed component is spatially continuous -- it does NOT determine
  whether that continuity reflects unwanted common-mode background or a
  real, laterally continuous reflection, and it is not an archaeological
  claim of any kind.
- **Engineering interpretation** states which single metric
  (`overall_rms_retention_tendency`) the category label is based on, and
  flags an explicit CONFLICT when a candidate ranked "preservation-favoring"
  by that metric alone still strongly attenuates the paired-control long
  target -- this project does not present one metric as decisive when
  metrics disagree, and none of these labels select a canonical candidate
  or transfer to a different dataset. Every "preservation-favoring"
  candidate's interpretation text also states its comparison against A0
  (see below) explicitly, so that ranking is never read as evidence of
  preserving more than doing nothing.
- **A0 (no_background_removal)** is a decision/QC-layer REFERENCE POLICY,
  not a filter candidate and not a `ProcessingResult` -- it never ran
  through `remove_background()`, has no dataset/removed_component/NPZ of
  its own, and is excluded from the `engineering_category` ranking scale
  entirely (that scale only ranks A1-A8 against each other). Its fixed
  values (background suppression 0; every retention metric 1.0) are
  definitional, not measured: an unprocessed signal is unconditionally
  identical to itself. Because A1-A8 all attenuate the paired-control long
  target far below A0's own retention of 1.0, "preservation-favoring"
  among A1-A8 is a RELATIVE ranking only -- it is never a claim that any
  processed candidate preserves more of a long target than doing nothing.

## What this report does NOT do

It does not select a canonical background-removal candidate -- including
A0. It does not apply gain. It does not make any archaeological
interpretation of removed or retained content. It does not equate overall
RMS retention with archaeological-target preservation. It does not present
removed-component coherence as a signal/noise classifier. It does not
treat A0 as a new filter method -- A0 is the absence of one. A human
reviewer remains free to select "no background removal" (A0) if the
common-scale evidence does not justify any of A1-A8; this report makes no
canonical decision automatically, for A0 or any other row. Human/
geophysical review of `BACKGROUND_OUTPUT_COMPARISON_CH00_CH05_CH10.png`,
`BACKGROUND_REMOVED_COMPARISON_CH00_CH05_CH10.png`, and
`BACKGROUND_METRICS_SUMMARY.png` (all common-scale across every candidate;
A0 appears only in the metrics summary panel and this table, since it has
no B-scan of its own) is required before any candidate here is used for
anything beyond QC comparison; `BACKGROUND_DECISION_PANEL.png`/`_DETAIL.png`
are kept for historical compatibility only and use independent,
non-comparable scales.
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
    paired_control_by_id = compute_paired_control_retention_for_candidates(candidates_info)
    interpretation_notes = _engineering_interpretation_notes(
        candidates_info, categories, paired_control_by_id
    )

    decision_panel_path, decision_panel_detail_path = save_decision_panel(
        dataset,
        candidates_info,
        output_dir / "BACKGROUND_DECISION_PANEL.png",
        output_dir / "BACKGROUND_DECISION_PANEL_DETAIL.png",
    )
    # Sprint 4A.1 correction: the three files below are the common-scale
    # comparison actually intended for human review -- BACKGROUND_DECISION_
    # PANEL.png/_DETAIL.png above are kept only for historical compatibility
    # (see their own docstrings/captions).
    output_comparison_path = save_common_scale_output_comparison(
        dataset, candidates_info, output_dir / "BACKGROUND_OUTPUT_COMPARISON_CH00_CH05_CH10.png"
    )
    removed_comparison_path = save_common_scale_removed_comparison(
        dataset, candidates_info, output_dir / "BACKGROUND_REMOVED_COMPARISON_CH00_CH05_CH10.png"
    )
    metrics_summary_path = save_background_metrics_summary_panel(
        candidates_info, paired_control_by_id, output_dir / "BACKGROUND_METRICS_SUMMARY.png"
    )
    final_decision_path = write_background_final_decision_required(
        candidates_info,
        categories,
        paired_control_by_id,
        interpretation_notes,
        output_dir / "BACKGROUND_FINAL_DECISION_REQUIRED.md",
    )

    return {
        "dataset": dataset,
        "valid_mask": valid_mask,
        "candidates": candidates_info,
        "comparison_paths": comparison_paths,
        "engineering_categories": categories,
        "paired_control_by_id": paired_control_by_id,
        "engineering_interpretation_notes": interpretation_notes,
        "decision_panel_path": decision_panel_path,
        "decision_panel_detail_path": decision_panel_detail_path,
        "output_comparison_path": output_comparison_path,
        "removed_comparison_path": removed_comparison_path,
        "metrics_summary_path": metrics_summary_path,
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
    "compute_paired_control_retention_for_candidates",
    "run_all_sprint4a_candidates",
    "run_background_candidates",
    "run_paired_control_target_attenuation_experiments",
    "run_synthetic_risk_experiments",
    "save_background_metrics_summary_panel",
    "save_common_scale_output_comparison",
    "save_common_scale_removed_comparison",
    "save_decision_panel",
    "sha256_file",
    "write_background_final_decision_required",
]
