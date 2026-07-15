#!/usr/bin/env python3
"""Sprint 2.2: target-invariance + DC-window validation artifacts.

Recomputes the target_sample=0 and target_sample=16 candidates in-process
(deterministic -- identical to the already-generated
``outputs/sprint02/canonical_target16/`` CLI run for target=16) so this
script has direct array access for building rich comparisons, and writes
everything under ``outputs/sprint02_2_validation/``. Does not modify or
re-generate the canonical CLI output itself. Makes no archaeological
interpretation and does not choose a target_sample -- target_sample=16 was
already recorded as the engineering recommendation elsewhere (see ADR-004);
this script only verifies the target-invariance property numerically.

Usage:
    python scripts/generate_sprint2_2_validation.py
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

from archaeogpr.io.ogpr_reader import read_ogpr
from archaeogpr.processing.dc_offset import correct_dc_offset
from archaeogpr.processing.result import ProcessingResult
from archaeogpr.processing.time_zero import correct_time_zero

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = REPO_ROOT / "data" / "raw" / "Swath003_Array02.ogpr"
VALIDATION_DIR = REPO_ROOT / "outputs" / "sprint02_2_validation"
TARGET_INVARIANCE_DIR = VALIDATION_DIR / "target_invariance"
DC_WINDOW_DIR = VALIDATION_DIR / "dc_window"

DC_WINDOW_START_NS = 20.0
DC_WINDOW_END_NS = 100.0
_TIME_ZERO_KWARGS: dict[str, Any] = {
    "method": "channel_median_peak",
    "search_start_ns": 5.0,
    "search_end_ns": 15.0,
    "peak_polarity": "max_abs",
    "max_shift_samples": 96,
    "overflow_policy": "error",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_candidate(raw, target_sample: int) -> tuple[ProcessingResult, ProcessingResult, ProcessingResult]:
    tz = correct_time_zero(raw, target_sample=target_sample, **_TIME_ZERO_KWARGS)
    dc_mean = correct_dc_offset(
        tz.dataset,
        method="mean",
        window_start_ns=DC_WINDOW_START_NS,
        window_end_ns=DC_WINDOW_END_NS,
        valid_mask=tz.valid_mask,
        window_reference="dataset_time",
    )
    dc_median = correct_dc_offset(
        tz.dataset,
        method="median",
        window_start_ns=DC_WINDOW_START_NS,
        window_end_ns=DC_WINDOW_END_NS,
        valid_mask=tz.valid_mask,
        window_reference="dataset_time",
    )
    return tz, dc_mean, dc_median


def _offsets_df(dc_result: ProcessingResult, target_sample: int) -> pd.DataFrame:
    offset = dc_result.removed_component[:, :, 0].astype(np.float64)
    slices_count, channels_count = offset.shape
    slice_idx, channel_idx = np.meshgrid(np.arange(slices_count), np.arange(channels_count), indexing="ij")
    return pd.DataFrame(
        {
            "slice": slice_idx.reshape(-1),
            "channel": channel_idx.reshape(-1),
            "offset": offset.reshape(-1),
            "target_sample": target_sample,
        }
    )


def main() -> None:
    raw_hash_before = _sha256(RAW_FILE)
    raw = read_ogpr(RAW_FILE)
    channels_count = raw.shape[1]

    tz0, dc0_mean, dc0_median = _run_candidate(raw, 0)
    tz16, dc16_mean, dc16_median = _run_candidate(raw, 16)

    TARGET_INVARIANCE_DIR.mkdir(parents=True, exist_ok=True)
    DC_WINDOW_DIR.mkdir(parents=True, exist_ok=True)

    # --- offsets CSVs + difference -------------------------------------------------
    df0 = _offsets_df(dc0_mean, 0)
    df16 = _offsets_df(dc16_mean, 16)
    df0.to_csv(TARGET_INVARIANCE_DIR / "offsets_target00.csv", index=False)
    df16.to_csv(TARGET_INVARIANCE_DIR / "offsets_target16.csv", index=False)

    merged = df0.merge(df16, on=["slice", "channel"], suffixes=("_target00", "_target16"))
    merged["abs_difference"] = (merged["offset_target00"] - merged["offset_target16"]).abs()
    merged[["slice", "channel", "offset_target00", "offset_target16", "abs_difference"]].to_csv(
        TARGET_INVARIANCE_DIR / "offset_difference.csv", index=False
    )
    max_offset_diff = float(merged["abs_difference"].max())
    offsets_allclose = bool(
        np.allclose(merged["offset_target00"], merged["offset_target16"], rtol=1e-6, atol=1e-3)
    )

    # --- offset_comparison.png ------------------------------------------------------
    channel_mean0 = df0.groupby("channel")["offset"].mean()
    channel_mean16 = df16.groupby("channel")["offset"].mean()
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(channels_count)
    width = 0.35
    ax.bar(x - width / 2, channel_mean0.values, width, label="target_sample=0")
    ax.bar(x + width / 2, channel_mean16.values, width, label="target_sample=16")
    ax.set_xlabel("Channel")
    ax.set_ylabel("DC offset (mean, canonical 20-100 ns window)")
    ax.set_title(f"DC offset per channel: target=0 vs target=16 (max abs diff={max_offset_diff:.2e})")
    ax.set_xticks(x)
    ax.legend()
    fig.tight_layout()
    fig.savefig(TARGET_INVARIANCE_DIR / "offset_comparison.png", dpi=140)
    plt.close(fig)

    # --- relative_time_axis_comparison.png ------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(np.arange(tz0.dataset.time_ns.shape[0]), tz0.dataset.time_ns, label="target_sample=0")
    ax.plot(np.arange(tz16.dataset.time_ns.shape[0]), tz16.dataset.time_ns, label="target_sample=16")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Sample index")
    ax.set_ylabel("time_ns (corrected, time-zero-relative)")
    ax.set_title("Corrected relative time axis: target=0 vs target=16")
    ax.legend()
    fig.tight_layout()
    fig.savefig(TARGET_INVARIANCE_DIR / "relative_time_axis_comparison.png", dpi=140)
    plt.close(fig)

    # --- common relative-time region -------------------------------------------------
    time0 = tz0.dataset.time_ns
    time16 = tz16.dataset.time_ns
    common_end = min(float(time0[-1]), float(time16[-1]))
    mask0 = (time0 >= 0) & (time0 <= common_end)
    mask16 = (time16 >= 0) & (time16 <= common_end)
    common0 = dc0_mean.dataset.amplitudes[:, :, mask0].astype(np.float64)
    common16 = dc16_mean.dataset.amplitudes[:, :, mask16].astype(np.float64)
    common_diff = np.abs(common0 - common16)
    max_common_diff = float(common_diff.max())

    fig, ax = plt.subplots(figsize=(10, 5))
    im = ax.imshow(common_diff[:, 0, :].T, aspect="auto", cmap="viridis", origin="upper")
    fig.colorbar(im, ax=ax, label="abs amplitude difference")
    ax.set_xlabel("Slice index")
    ax.set_ylabel("Common-region sample index")
    ax.set_title(
        f"Channel 00: |target=0 - target=16| in common relative-time region (max={max_common_diff:.2e})"
    )
    fig.tight_layout()
    fig.savefig(TARGET_INVARIANCE_DIR / "common_time_data_difference.png", dpi=140)
    plt.close(fig)

    # --- raw window mapping per channel ----------------------------------------------
    per_channel: list[dict[str, Any]] = []
    for channel in range(channels_count):
        shift0 = tz0.diagnostics["channel_shifts"][str(channel)]
        shift16 = tz16.diagnostics["channel_shifts"][str(channel)]
        raw_start0 = dc0_mean.diagnostics["window_start_sample"] - shift0
        raw_end0 = dc0_mean.diagnostics["window_end_sample"] - shift0
        raw_start16 = dc16_mean.diagnostics["window_start_sample"] - shift16
        raw_end16 = dc16_mean.diagnostics["window_end_sample"] - shift16
        per_channel.append(
            {
                "channel": channel,
                "raw_window_start_sample_target00": raw_start0,
                "raw_window_end_sample_target00": raw_end0,
                "raw_window_start_sample_target16": raw_start16,
                "raw_window_end_sample_target16": raw_end16,
                "raw_window_matches": raw_start0 == raw_start16 and raw_end0 == raw_end16,
                "selected_valid_sample_count_target00": dc0_mean.diagnostics[
                    "valid_samples_per_channel_in_window"
                ][str(channel)],
                "selected_valid_sample_count_target16": dc16_mean.diagnostics[
                    "valid_samples_per_channel_in_window"
                ][str(channel)],
            }
        )

    summary: dict[str, Any] = {
        "note": (
            "Measured/derived quantities only. target_sample=16 was already recorded "
            "as the engineering recommendation elsewhere (ADR-004) -- this file verifies "
            "target-invariance, it does not select a target_sample."
        ),
        "raw_file_sha256": raw_hash_before,
        "dc_window_ns": [DC_WINDOW_START_NS, DC_WINDOW_END_NS],
        "window_reference": "dataset_time",
        "per_channel_raw_window_mapping": per_channel,
        "all_channels_raw_window_matches": all(bool(r["raw_window_matches"]) for r in per_channel),
        "max_offset_abs_difference": max_offset_diff,
        "offsets_allclose_rtol_1e-6_atol_1e-3": offsets_allclose,
        "common_relative_time_region_sample_count": int(mask0.sum()),
        "max_common_time_amplitude_abs_difference": max_common_diff,
        "target16_minus_target0_padding_count_per_channel": {
            str(channel): int((~tz16.valid_mask[channel]).sum()) - int((~tz0.valid_mask[channel]).sum())
            for channel in range(channels_count)
        },
    }
    (TARGET_INVARIANCE_DIR / "target_invariance_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    # ================= dc_window/ ====================================================

    fig, ax = plt.subplots(figsize=(12, 6))
    cmap = plt.get_cmap("viridis")
    for channel in range(channels_count):
        color = cmap(channel / max(channels_count - 1, 1))
        median_trace = np.median(tz16.dataset.amplitudes[:, channel, :].astype(np.float64), axis=0)
        ax.plot(tz16.dataset.time_ns, median_trace, color=color, linewidth=1.0, label=f"Ch {channel:02d}")
    ax.axvspan(DC_WINDOW_START_NS, DC_WINDOW_END_NS, color="orange", alpha=0.2, label="DC window [20,100) ns")
    ax.axvline(0, color="black", linestyle="--", linewidth=1.2, label="target_sample=16 (t=0)")
    ax.set_xlabel("time_ns (corrected, target_sample=16)")
    ax.set_ylabel("Median amplitude (per channel, time-zero corrected)")
    ax.set_title("Channel median traces with the canonical DC window shaded")
    ax.legend(fontsize=7, ncol=3)
    fig.tight_layout()
    fig.savefig(DC_WINDOW_DIR / "channel_median_traces_with_window.png", dpi=140)
    plt.close(fig)

    mean_offsets = np.array(
        [dc16_mean.removed_component[0, channel, 0] for channel in range(channels_count)], dtype=np.float64
    )
    median_offsets = np.array(
        [dc16_median.removed_component[0, channel, 0] for channel in range(channels_count)], dtype=np.float64
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(channels_count)
    width = 0.35
    ax.bar(x - width / 2, mean_offsets, width, label="mean")
    ax.bar(x + width / 2, median_offsets, width, label="median")
    ax.set_xlabel("Channel")
    ax.set_ylabel("DC offset")
    ax.set_title("Mean vs median DC offset per channel (canonical window, target_sample=16, QC only)")
    ax.set_xticks(x)
    ax.legend()
    fig.tight_layout()
    fig.savefig(DC_WINDOW_DIR / "mean_vs_median_offsets.png", dpi=140)
    plt.close(fig)

    rows = []
    for channel in range(channels_count):
        rows.append(
            {
                "channel": channel,
                "selected_valid_sample_count_target00": dc0_mean.diagnostics[
                    "valid_samples_per_channel_in_window"
                ][str(channel)],
                "selected_valid_sample_count_target16": dc16_mean.diagnostics[
                    "valid_samples_per_channel_in_window"
                ][str(channel)],
            }
        )
    pd.DataFrame(rows).to_csv(DC_WINDOW_DIR / "selected_sample_count.csv", index=False)

    dc_window_summary: dict[str, Any] = {
        "window_start_ns": DC_WINDOW_START_NS,
        "window_end_ns": DC_WINDOW_END_NS,
        "window_reference": "dataset_time",
        "window_sample_indices_target00": [
            dc0_mean.diagnostics["window_start_sample"],
            dc0_mean.diagnostics["window_end_sample"],
        ],
        "window_sample_indices_target16": [
            dc16_mean.diagnostics["window_start_sample"],
            dc16_mean.diagnostics["window_end_sample"],
        ],
        "mean_offsets_target16": mean_offsets.tolist(),
        "median_offsets_target16": median_offsets.tolist(),
        "max_abs_mean_vs_median_difference": float(np.abs(mean_offsets - median_offsets).max()),
    }
    (DC_WINDOW_DIR / "dc_window_summary.json").write_text(
        json.dumps(dc_window_summary, indent=2), encoding="utf-8"
    )

    raw_hash_after = _sha256(RAW_FILE)

    print(
        json.dumps(
            {
                "raw_hash_unchanged": raw_hash_before == raw_hash_after,
                "all_channels_raw_window_matches": summary["all_channels_raw_window_matches"],
                "offsets_allclose": offsets_allclose,
                "max_offset_abs_difference": max_offset_diff,
                "max_common_time_amplitude_abs_difference": max_common_diff,
                "target16_minus_target0_padding_delta": summary[
                    "target16_minus_target0_padding_count_per_channel"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
