"""Sprint 2 processed-data exports: CSV/JSON summaries and corrected-data NPZ.

Mirrors ``archaeogpr.export.basic``'s style but for processing results
rather than raw-file inspection. This module never picks an output
directory itself — the CLI always passes one explicitly — and by
convention that directory is never ``data/raw/`` or anywhere the raw
``.ogpr`` file lives, keeping raw and processed data physically separate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.result import ProcessingResult


def write_channel_picks_csv(result: ProcessingResult, output_path: str | Path) -> Path:
    """One row per channel: picked/target sample, shift (samples & ns), method, warning."""
    diagnostics = result.diagnostics
    channels = sorted(int(c) for c in diagnostics["channel_picks"])
    method = diagnostics["method"]
    target_sample = diagnostics["target_sample"]
    sampling_time_ns = diagnostics.get("sampling_time_ns")
    picks_time_ns = diagnostics.get("channel_picks_time_ns") or {}

    warning_by_channel: dict[int, str] = {}
    for warning in result.warnings:
        for channel in channels:
            if warning.startswith(f"channel {channel}:"):
                warning_by_channel[channel] = warning

    rows = []
    for channel in channels:
        shift_samples = diagnostics["channel_shifts"][str(channel)]
        rows.append(
            {
                "channel": channel,
                "picked_sample": diagnostics["channel_picks"][str(channel)],
                "picked_time_ns": picks_time_ns.get(str(channel)),
                "target_sample": target_sample,
                "shift_samples": shift_samples,
                "shift_ns": shift_samples * sampling_time_ns if sampling_time_ns is not None else None,
                "method": method,
                "warning": warning_by_channel.get(channel, ""),
            }
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    return output_path


def write_offsets_csv(result: ProcessingResult, output_path: str | Path) -> Path:
    """One row per (slice, channel): offset, method, window_start_ns, window_end_ns."""
    diagnostics = result.diagnostics
    offset = result.removed_component[:, :, 0].astype(np.float64)  # (slices, channels)
    slices_count, channels_count = offset.shape
    slice_idx, channel_idx = np.meshgrid(np.arange(slices_count), np.arange(channels_count), indexing="ij")

    df = pd.DataFrame(
        {
            "slice": slice_idx.reshape(-1),
            "channel": channel_idx.reshape(-1),
            "offset": offset.reshape(-1),
            "method": diagnostics["method"],
            "window_start_ns": diagnostics["window_start_ns"],
            "window_end_ns": diagnostics["window_end_ns"],
        }
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


def write_processing_metadata_json(result: ProcessingResult, output_path: str | Path) -> Path:
    """Dump this result's own processing_history entry (operation/parameters/diagnostics/warnings).

    Assumes ``result`` is exported right after it was produced, before any
    further processing step is chained onto ``result.dataset`` — this writes
    ``result.dataset.processing_history[-1]``, the record this specific
    operation appended, as the single source of truth (no re-derivation).
    """
    record = result.dataset.processing_history[-1]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dict(record), indent=2), encoding="utf-8")
    return output_path


def write_corrected_npz(result: ProcessingResult, output_path: str | Path) -> Path:
    """Save one stage's corrected amplitudes + time_ns + removed_component + metadata as NPZ.

    Includes ``valid_mask`` (shape ``(channels, samples)``) when
    ``result.valid_mask`` is not ``None`` — omitted entirely otherwise,
    never stored as a ``None`` object array.
    """
    dataset = result.dataset
    payload: dict[str, Any] = {
        "amplitudes": dataset.amplitudes,
        "time_ns": dataset.time_ns,
        "removed_component": result.removed_component,
        "has_valid_mask": result.valid_mask is not None,
        "processing_history_json": json.dumps([dict(record) for record in dataset.processing_history]),
        "metadata_json": json.dumps(dict(dataset.metadata)),
    }
    if result.valid_mask is not None:
        payload["valid_mask"] = result.valid_mask
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output_path, **payload)
    return output_path


def write_combined_npz(
    time_zero_result: ProcessingResult,
    dc_offset_result: ProcessingResult,
    output_path: str | Path,
) -> Path:
    """Save the final (time-zero -> DC offset) dataset plus both stages' removed components.

    Includes ``valid_mask`` when present on either result (they are the same
    mask, passed through unchanged by DC offset — see
    ``processing/dc_offset.py``).
    """
    final_dataset = dc_offset_result.dataset
    valid_mask = (
        dc_offset_result.valid_mask
        if dc_offset_result.valid_mask is not None
        else time_zero_result.valid_mask
    )
    payload: dict[str, Any] = {
        "amplitudes": final_dataset.amplitudes,
        "time_ns": final_dataset.time_ns,
        "removed_component_time_zero": time_zero_result.removed_component,
        "removed_component_dc_offset": dc_offset_result.removed_component,
        "has_valid_mask": valid_mask is not None,
        "processing_history_json": json.dumps([dict(record) for record in final_dataset.processing_history]),
        "metadata_json": json.dumps(dict(final_dataset.metadata)),
    }
    if valid_mask is not None:
        payload["valid_mask"] = valid_mask
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output_path, **payload)
    return output_path


def write_valid_sample_summary_json(result: ProcessingResult, output_path: str | Path) -> Path:
    """Save a compact valid/padding + overflow-policy summary, derived from a time-zero result.

    Pulls already-computed fields from ``result.diagnostics`` — no
    recomputation, single source of truth.
    """
    diagnostics = result.diagnostics
    summary: dict[str, Any] = {
        "overflow_policy": diagnostics.get("overflow_policy"),
        "has_clipped_shifts": diagnostics.get("has_clipped_shifts"),
        "valid_for_downstream_processing": diagnostics.get("valid_for_downstream_processing"),
        "max_shift_samples": diagnostics.get("max_shift_samples"),
        "requested_shifts": diagnostics.get("requested_shifts"),
        "channel_shifts": diagnostics.get("channel_shifts"),
        "total_valid_samples": diagnostics.get("total_valid_samples"),
        "total_padded_samples": diagnostics.get("total_padded_samples"),
        "valid_sample_counts_per_channel": diagnostics.get("valid_sample_counts"),
        "padding_sample_counts_per_channel": diagnostics.get("padding_sample_counts"),
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return output_path


def write_relative_time_axis_csv(dataset: GPRDataset, output_path: str | Path) -> Path:
    """Save ``dataset.time_ns`` as one ``sample,time_ns`` row per sample.

    Works on any dataset — before or after ``correct_time_zero()`` — since
    it only ever reads ``dataset.time_ns`` as it currently is. After
    time-zero correction this is time-zero-relative (see ADR-004):
    ``time_ns[target_sample] == 0.0``, negative before it, positive after.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "sample": np.arange(dataset.time_ns.shape[0]),
            "time_ns": dataset.time_ns,
        }
    )
    df.to_csv(output_path, index=False)
    return output_path


def write_processing_history_json(dataset: GPRDataset, output_path: str | Path) -> Path:
    """Save the full ``processing_history`` tuple, in order, as a JSON list."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    history = [dict(record) for record in dataset.processing_history]
    output_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return output_path


def write_sprint2_summary_json(
    raw_dataset: GPRDataset,
    time_zero_result: ProcessingResult,
    dc_offset_result: ProcessingResult,
    output_path: str | Path,
    *,
    source_file: str | Path | None = None,
    raw_file_sha256: str | None = None,
) -> Path:
    """Save a compact combined-pipeline summary (shapes, history order, per-stage key figures)."""
    final_dataset = dc_offset_result.dataset
    summary: dict[str, Any] = {
        "source_file": str(source_file) if source_file is not None else None,
        "raw_file_sha256": raw_file_sha256,
        "input_shape": list(raw_dataset.shape),
        "output_shape": list(final_dataset.shape),
        "processing_history_operations": [record["operation"] for record in final_dataset.processing_history],
        "time_zero": {
            "method": time_zero_result.diagnostics["method"],
            "target_sample": time_zero_result.diagnostics["target_sample"],
            "overflow_policy": time_zero_result.diagnostics.get("overflow_policy"),
            "has_clipped_shifts": time_zero_result.diagnostics.get("has_clipped_shifts"),
            "valid_for_downstream_processing": time_zero_result.diagnostics.get(
                "valid_for_downstream_processing"
            ),
            "channel_shifts": time_zero_result.diagnostics["channel_shifts"],
            "min_shift": time_zero_result.diagnostics["min_shift"],
            "max_shift": time_zero_result.diagnostics["max_shift"],
            "median_shift": time_zero_result.diagnostics["median_shift"],
            "total_valid_samples": time_zero_result.diagnostics.get("total_valid_samples"),
            "total_padded_samples": time_zero_result.diagnostics.get("total_padded_samples"),
            "time_axis": time_zero_result.diagnostics.get("time_axis"),
            "warnings": list(time_zero_result.warnings),
        },
        "dc_offset": {
            "method": dc_offset_result.diagnostics["method"],
            "window_start_ns": dc_offset_result.diagnostics.get("window_start_ns"),
            "window_end_ns": dc_offset_result.diagnostics.get("window_end_ns"),
            "window_reference": dc_offset_result.diagnostics.get("window_reference"),
            "window_start_sample": dc_offset_result.diagnostics.get("window_start_sample"),
            "window_end_sample": dc_offset_result.diagnostics.get("window_end_sample"),
            "offset_statistics": dc_offset_result.diagnostics["offset_statistics"],
            "trace_mean_before": dc_offset_result.diagnostics["trace_mean_before"],
            "trace_mean_after": dc_offset_result.diagnostics["trace_mean_after"],
            "trace_mean_after_valid_only": dc_offset_result.diagnostics.get("trace_mean_after_valid_only"),
            "trace_mean_after_padding_only": dc_offset_result.diagnostics.get(
                "trace_mean_after_padding_only"
            ),
            "padding_value_statistics": dc_offset_result.diagnostics.get("padding_value_statistics"),
            "warnings": list(dc_offset_result.warnings),
        },
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return output_path
