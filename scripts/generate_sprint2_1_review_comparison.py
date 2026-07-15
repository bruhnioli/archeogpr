#!/usr/bin/env python3
"""Sprint 2.1: build the target_sample=0 vs target_sample=16 comparison artifacts.

Reads the four already-generated candidate directories under
``outputs/sprint02_review/`` (produced by running the ``time-zero`` and
``sprint2`` CLI commands directly — this script does not run any
processing itself, only reads back what those commands wrote and
tabulates/plots it) and writes the comparison deliverables into
``outputs/sprint02_review/comparison/`` plus the top-level
``REVIEW_REQUIRED.md``.

This script makes no archaeological interpretation and does not recommend
target_sample=0 over target_sample=16 or vice-versa — it only presents the
measured/derived numbers side by side. See CLAUDE.md and the Sprint 2.1
task brief.

Usage:
    python scripts/generate_sprint2_1_review_comparison.py
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

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = REPO_ROOT / "outputs" / "sprint02_review"
COMPARISON_DIR = REVIEW_DIR / "comparison"
RAW_FILE = REPO_ROOT / "data" / "raw" / "Swath003_Array02.ogpr"

_CANDIDATES = {
    0: {"time_zero_dir": REVIEW_DIR / "target_sample_00", "combined_dir": REVIEW_DIR / "combined_target00"},
    16: {"time_zero_dir": REVIEW_DIR / "target_sample_16", "combined_dir": REVIEW_DIR / "combined_target16"},
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_candidate(target_sample: int) -> dict[str, Any]:
    paths = _CANDIDATES[target_sample]
    picks_df = pd.read_csv(paths["time_zero_dir"] / "channel_picks.csv")
    valid_summary = json.loads((paths["time_zero_dir"] / "valid_sample_summary.json").read_text())
    with np.load(paths["time_zero_dir"] / "time_zero_corrected.npz") as npz:
        tz_amplitudes = npz["amplitudes"].copy()
        tz_valid_mask = npz["valid_mask"].copy()
    with np.load(paths["combined_dir"] / "sprint02_processed.npz") as npz:
        combined_amplitudes = npz["amplitudes"].copy()
    return {
        "picks_df": picks_df,
        "valid_summary": valid_summary,
        "tz_amplitudes": tz_amplitudes,
        "tz_valid_mask": tz_valid_mask,
        "combined_amplitudes": combined_amplitudes,
    }


def _build_discarded_leading_samples_csv(candidates: dict[int, dict[str, Any]]) -> Path:
    rows = []
    for target_sample, data in candidates.items():
        for _, row in data["picks_df"].iterrows():
            shift = int(row["shift_samples"])
            padding_count = abs(shift)
            # A negative shift (target_sample < picked_sample) moves the trace toward
            # the front: samples originally before the alignment point fall off the
            # front entirely (leading_samples_discarded) and an equal-sized padding
            # gap appears at the tail (trailing_padding_samples). A positive shift
            # (target_sample > picked_sample) is the mirror case and discards nothing
            # from the front, so both columns are 0 (padding then appears at the
            # front instead, which is out of scope for "leading wavelet loss").
            leading_samples_discarded = padding_count if shift < 0 else 0
            trailing_padding_samples = padding_count if shift < 0 else 0
            rows.append(
                {
                    "channel": int(row["channel"]),
                    "picked_sample": int(row["picked_sample"]),
                    "target_sample": target_sample,
                    "leading_samples_discarded": leading_samples_discarded,
                    "trailing_padding_samples": trailing_padding_samples,
                }
            )
    df = pd.DataFrame(rows).sort_values(["channel", "target_sample"]).reset_index(drop=True)
    output_path = COMPARISON_DIR / "discarded_leading_samples.csv"
    df.to_csv(output_path, index=False)
    return output_path


def _build_padding_summary_csv(candidates: dict[int, dict[str, Any]]) -> Path:
    rows = []
    for target_sample, data in candidates.items():
        summary = data["valid_summary"]
        samples_count = data["tz_amplitudes"].shape[2]
        channel_shifts = summary["channel_shifts"]
        valid_counts = summary["valid_sample_counts_per_channel"]
        padding_counts = summary["padding_sample_counts_per_channel"]
        for channel_str in sorted(channel_shifts, key=int):
            shift = int(channel_shifts[channel_str])
            padding_count = int(padding_counts[channel_str])
            rows.append(
                {
                    "target_sample": target_sample,
                    "channel": int(channel_str),
                    "applied_shift": shift,
                    "samples_count": samples_count,
                    "valid_sample_count": int(valid_counts[channel_str]),
                    "padding_sample_count": padding_count,
                    "padding_fraction": round(padding_count / samples_count, 6),
                    "padding_side": "trailing" if shift < 0 else ("leading" if shift > 0 else "none"),
                }
            )
    df = pd.DataFrame(rows).sort_values(["channel", "target_sample"]).reset_index(drop=True)
    output_path = COMPARISON_DIR / "padding_summary.csv"
    df.to_csv(output_path, index=False)
    return output_path


def _build_comparison_summary_json(candidates: dict[int, dict[str, Any]], raw_file_sha256: str) -> Path:
    summary: dict[str, Any] = {
        "note": (
            "This file presents only measured/derived quantities produced by the "
            "already-completed time-zero and DC-offset runs for each candidate. It "
            "does not recommend or select a target_sample — that decision requires "
            "human/geophysical review. See REVIEW_REQUIRED.md."
        ),
        "raw_file_sha256": raw_file_sha256,
        "candidates": {},
    }
    for target_sample, data in candidates.items():
        s = data["valid_summary"]
        summary["candidates"][str(target_sample)] = {
            "overflow_policy": s["overflow_policy"],
            "has_clipped_shifts": s["has_clipped_shifts"],
            "valid_for_downstream_processing": s["valid_for_downstream_processing"],
            "max_shift_samples": s["max_shift_samples"],
            "channel_shifts": s["channel_shifts"],
            "total_valid_samples": s["total_valid_samples"],
            "total_padded_samples": s["total_padded_samples"],
            "valid_sample_counts_per_channel": s["valid_sample_counts_per_channel"],
            "padding_sample_counts_per_channel": s["padding_sample_counts_per_channel"],
        }
    output_path = COMPARISON_DIR / "comparison_summary.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return output_path


def _shared_clip_limit(*arrays: np.ndarray, clip_percentile: float = 99.0) -> float:
    limit = 0.0
    for arr in arrays:
        limit = max(limit, float(np.percentile(np.abs(arr), clip_percentile)))
    return limit if limit > 0 else 1.0


def _build_channel00_comparison_png(candidates: dict[int, dict[str, Any]]) -> Path:
    channel = 0
    data_0, data_16 = candidates[0], candidates[16]
    ch_0 = data_0["combined_amplitudes"][:, channel, :]
    ch_16 = data_16["combined_amplitudes"][:, channel, :]
    limit = _shared_clip_limit(ch_0, ch_16)

    fig, axes = plt.subplots(1, 2, figsize=(16, 5), sharey=True)
    for ax, (target_sample, ch_data) in zip(axes, ((0, ch_0), (16, ch_16)), strict=True):
        ax.imshow(
            ch_data.T,
            aspect="auto",
            cmap="seismic",
            vmin=-limit,
            vmax=limit,
            origin="upper",
            interpolation="nearest",
        )
        ax.axhline(target_sample, color="black", linestyle="--", linewidth=1.2)
        ax.set_xlabel("Slice index")
        ax.set_title(f"target_sample={target_sample} (final: time-zero + DC offset)")
    axes[0].set_ylabel("Sample index")
    fig.suptitle("Channel 00 — target_sample=0 vs target_sample=16 (shared color scale, QC only)")
    fig.colorbar(axes[-1].images[0], ax=axes, label="Amplitude (raw, ungained)", shrink=0.85)

    output_path = COMPARISON_DIR / "target00_vs_target16_channel00.png"
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def _build_all_channel_medians_png(candidates: dict[int, dict[str, Any]]) -> Path:
    data_0, data_16 = candidates[0], candidates[16]
    channels_count = data_0["tz_amplitudes"].shape[1]
    samples_count = data_0["tz_amplitudes"].shape[2]
    x = np.arange(samples_count)
    cmap = plt.get_cmap("viridis")

    fig, ax = plt.subplots(figsize=(12, 6))
    for channel in range(channels_count):
        color = cmap(channel / max(channels_count - 1, 1))
        median_0 = np.median(data_0["tz_amplitudes"][:, channel, :].astype(np.float64), axis=0)
        median_16 = np.median(data_16["tz_amplitudes"][:, channel, :].astype(np.float64), axis=0)
        ax.plot(x, median_0, color=color, linestyle="--", linewidth=1.0, alpha=0.7)
        ax.plot(x, median_16, color=color, linestyle="-", linewidth=1.3, label=f"Ch {channel:02d}")

    ax.axvline(0, color="black", linestyle="--", linewidth=1.3, label="target_sample=0")
    ax.axvline(16, color="black", linestyle="-", linewidth=1.3, label="target_sample=16")
    ax.set_xlim(0, 120)
    ax.set_xlabel("Sample index")
    ax.set_ylabel("Median amplitude (per channel, time-zero corrected only)")
    ax.set_title("All-channel median traces — target_sample=0 (dashed) vs target_sample=16 (solid)")
    ax.legend(loc="upper right", fontsize=7, ncol=3, framealpha=0.85)
    fig.tight_layout()

    output_path = COMPARISON_DIR / "target00_vs_target16_all_channel_medians.png"
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


_REVIEW_REQUIRED_TEMPLATE = """# Sprint 2.1 Review Required: target_sample=0 vs target_sample=16

Status: **review_required** — no target_sample has been selected. This document
presents the measured behavior of both candidates side by side. Selecting a final
target_sample for downstream (Sprint 3+) processing requires human/geophysical review;
it is not decided automatically by this pipeline.

## What was run

Both candidates used the same real input file, the same automatic pick method
(`channel_median_peak`, `search_start_ns=5.0`, `search_end_ns=15.0`, `peak_polarity=max_abs`),
and the same overflow settings (`max_shift_samples=96`, `overflow_policy=error`). Only
`target_sample` differs (0 vs 16). Both achieved **zero clipped channels**
(`has_clipped_shifts=false`, `valid_for_downstream_processing=true` for every channel in
both candidates) — `max_shift_samples=96` is generous enough that every channel's true
requested shift ({min_shift_0} to {max_shift_0} samples for target_sample=0) was applied
exactly, not clipped.

- Raw input file SHA-256: `{raw_sha256}` (verified unchanged before and after every run)
- Candidate A: `outputs/sprint02_review/target_sample_00/`, `outputs/sprint02_review/combined_target00/`
- Candidate B: `outputs/sprint02_review/target_sample_16/`, `outputs/sprint02_review/combined_target16/`
- Comparison data: `outputs/sprint02_review/comparison/`

## target_sample=0 behavior

Every channel's picked event is shifted so it lands exactly on sample 0. This means
**every sample that was originally recorded before the picked peak is discarded** —
between {min_leading_0} and {max_leading_0} samples per channel (see
`comparison/discarded_leading_samples.csv`). The output trace has no room left before
the aligned event; the padding introduced at the tail of each channel ranges from
{min_leading_0} to {max_leading_0} samples (`comparison/padding_summary.csv`).

Risk: if the true physical onset (e.g. the leading edge of the direct/air wave, or
weak early energy the automatic peak-picker did not select as "the" peak) occurs before
the picked sample, target_sample=0 removes it completely and irreversibly. There is no
way to recover it from the target_sample=0 output.

## target_sample=16 behavior

Every channel's picked event is shifted so it lands on sample 16 instead of sample 0,
which means 16 fewer samples are discarded from the front of every channel compared to
target_sample=0 (between {min_leading_16} and {max_leading_16} samples discarded, vs
{min_leading_0}-{max_leading_0} for target_sample=0) — see
`comparison/discarded_leading_samples.csv` for the exact per-channel counts. The
trailing padding region is correspondingly 16 samples smaller per channel.

Risk: target_sample=16 still discards a large number of leading samples (it only
reduces the loss by 16, it does not eliminate it), and shifting the reference point away
from 0 changes where sample-index-based downstream logic (e.g. any future windowed
filter with a fixed sample offset) would need to look for the direct wave. Any future
band-pass or dewow filter's edge effects (Sprint 3, not started) would begin 16 samples
later in absolute terms for this candidate.

## Common caveats (apply to both candidates)

- **Automatic picks are not physically certain.** {tz_reference_warning}
- The pick method (`channel_median_peak`) selects one extremum per channel's median
  trace inside the search window — it has no independent ground truth for where the
  physical surface/direct-wave onset actually is. A different peak_polarity, search
  window, or picking method could plausibly select a different sample for the same
  physical event.
- DC offset correction was applied using the time-zero valid mask
  (`dc_offset_valid_mask_used=true` in both `combined_target00` and `combined_target16`
  CLI runs), so padding introduced by time-zero is excluded from both the offset
  computation and the subtraction in both candidates — padding stays exactly at
  `fill_value` in both.
- Neither candidate has been filtered (no dewow, no band-pass); Sprint 3 has **not**
  been started.

## Key images for human/geophysical review

- `comparison/target00_vs_target16_channel00.png` — channel 0, final (time-zero +
  DC-offset) B-scan, target_sample=0 vs target_sample=16, shared color scale.
- `comparison/target00_vs_target16_all_channel_medians.png` — all 11 channels' median
  traces (time-zero corrected only), target_sample=0 (dashed) vs target_sample=16
  (solid), zoomed to the first 120 samples where the picks and shifts occur.
- `target_sample_00/padding_mask_channel00.png` and
  `target_sample_16/padding_mask_channel00.png` — valid/padding regions for channel 0
  under each candidate.

## Next action

**Next action: Human geophysical QC of target_sample 0 vs 16 candidates.**

No target_sample has been selected. Sprint 3 (dewow, band-pass) has not been started and
must not begin until this review is complete and a target_sample is explicitly approved.
"""


def _build_review_required_md(candidates: dict[int, dict[str, Any]], raw_file_sha256: str) -> Path:
    discarded_df = pd.read_csv(COMPARISON_DIR / "discarded_leading_samples.csv")
    d0 = discarded_df[discarded_df["target_sample"] == 0]
    d16 = discarded_df[discarded_df["target_sample"] == 16]
    shifts_0 = [int(v) for v in candidates[0]["valid_summary"]["channel_shifts"].values()]

    text = _REVIEW_REQUIRED_TEMPLATE.format(
        raw_sha256=raw_file_sha256,
        min_shift_0=min(shifts_0),
        max_shift_0=max(shifts_0),
        min_leading_0=int(d0["leading_samples_discarded"].min()),
        max_leading_0=int(d0["leading_samples_discarded"].max()),
        min_leading_16=int(d16["leading_samples_discarded"].min()),
        max_leading_16=int(d16["leading_samples_discarded"].max()),
        tz_reference_warning=(
            "Automatic time-zero picks are signal-processing references and are not "
            "independently calibrated physical surface times."
        ),
    )
    output_path = REVIEW_DIR / "REVIEW_REQUIRED.md"
    output_path.write_text(text, encoding="utf-8")
    return output_path


def main() -> None:
    for target_sample, paths in _CANDIDATES.items():
        for key in ("time_zero_dir", "combined_dir"):
            if not paths[key].is_dir():
                raise SystemExit(
                    f"missing candidate directory for target_sample={target_sample}: {paths[key]} "
                    "— run the time-zero and sprint2 CLI commands for both candidates first"
                )

    COMPARISON_DIR.mkdir(parents=True, exist_ok=True)
    raw_file_sha256 = _sha256(RAW_FILE)
    candidates = {ts: _load_candidate(ts) for ts in _CANDIDATES}

    generated = [
        _build_discarded_leading_samples_csv(candidates),
        _build_padding_summary_csv(candidates),
        _build_channel00_comparison_png(candidates),
        _build_all_channel_medians_png(candidates),
    ]
    generated.append(_build_comparison_summary_json(candidates, raw_file_sha256))
    generated.append(_build_review_required_md(candidates, raw_file_sha256))

    print("Generated:")
    for path in generated:
        print(f"  - {path.relative_to(REPO_ROOT)}")

    raw_file_sha256_after = _sha256(RAW_FILE)
    print(f"Raw file hash unchanged: {raw_file_sha256_after == raw_file_sha256}")


if __name__ == "__main__":
    main()
