"""Dewow: remove a slow, low-frequency "wow"/baseline drift from every trace.

For every (slice, channel) trace independently, within each contiguous run
of valid (non-padding) samples::

    baseline(t) = MovingWindow[trace(t)]   # mean or median, centered
    corrected(t) = trace(t) - baseline(t)   for t in that valid run

Padding is never read (it does not influence the moving window) and never
written (it stays exactly at whatever value it already had -- typically
time-zero's ``fill_value``). See CLAUDE.md: "Every filter must expose the
removed or difference component for QC" -- ``removed_component`` here is
exactly the estimated baseline, zero at padding since nothing was removed
there.

Window handling (see ADR-005): a caller-requested ``window_ns`` is
converted to samples via ``round(window_ns / sampling_time_ns)``. A centered
moving window needs an odd sample count, so an even result is bumped up by
one (never silently rounded down, which would make the window narrower and
more signal-eating than requested). Both the requested and applied windows
are reported in ``diagnostics`` -- the applied value is never substituted
silently.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.common import ProcessingError, build_processing_record, contiguous_true_runs
from archaeogpr.processing.result import ProcessingResult

_METHODS = ("running_mean", "running_median")
_EDGE_MODES = ("reflect", "nearest")
_OPERATION_NAME = "dewow_correction"
_MIN_APPLIED_WINDOW_SAMPLES = 3

#: numpy.pad mode for each supported edge_mode. "reflect" mirrors the segment
#: without repeating its edge sample (numpy's own "reflect"); "nearest"
#: repeats the edge sample outward (numpy's "edge") -- i.e. holds the
#: nearest real value constant past the boundary.
_NUMPY_PAD_MODE: dict[str, Literal["reflect", "edge"]] = {"reflect": "reflect", "nearest": "edge"}


def _moving_window_baseline(
    segment: np.ndarray, window_samples: int, method: str, pad_mode: Literal["reflect", "edge"]
) -> np.ndarray:
    """Centered moving mean/median of ``segment`` (shape ``(slices, length)``), same shape out.

    Pads only within this segment's own values (never reaching into padding
    or neighboring segments) so the window is always well-defined at the
    segment's own edges.
    """
    half_window = window_samples // 2
    padded = np.pad(segment, ((0, 0), (half_window, half_window)), mode=pad_mode)
    windows = sliding_window_view(padded, window_samples, axis=1)  # (slices, length, window_samples)
    if method == "running_mean":
        return windows.mean(axis=-1)
    return np.median(windows, axis=-1)


def correct_dewow(
    dataset: GPRDataset,
    *,
    window_ns: float = 8.0,
    method: str = "running_mean",
    valid_mask: np.ndarray | None = None,
    edge_mode: str = "reflect",
    allow_repeat_processing: bool = False,
) -> ProcessingResult:
    """Subtract a per-trace, per-valid-segment moving-window baseline (the "wow").

    ``dataset`` is never modified. ``valid_mask`` (shape ``(channels,
    samples)``, e.g. from ``correct_time_zero``'s ``ProcessingResult.
    valid_mask``) excludes padding from both the window computation and the
    subtraction; pass ``None`` to treat every sample as valid. Within a
    channel, each contiguous run of valid samples is dewowed independently
    (a window never reaches across a padding gap). Raises ``ProcessingError``
    for an invalid method/edge_mode, an applied window under 3 samples, a
    window wider than some valid run, a `dewow_correction` already present in
    ``dataset.processing_history`` (unless ``allow_repeat_processing=True``),
    or if the result contains NaN/Inf.
    """
    if method not in _METHODS:
        raise ProcessingError(f"method must be one of {_METHODS}, got {method!r}")
    if edge_mode not in _EDGE_MODES:
        raise ProcessingError(f"edge_mode must be one of {_EDGE_MODES}, got {edge_mode!r}")

    existing_ops = [record["operation"] for record in dataset.processing_history]
    if _OPERATION_NAME in existing_ops and not allow_repeat_processing:
        raise ProcessingError(
            f"dataset.processing_history already contains {_OPERATION_NAME!r} "
            f"({existing_ops.count(_OPERATION_NAME)} time(s)); pass allow_repeat_processing=True "
            "to apply it again deliberately"
        )

    slices_count, channels_count, samples_count = dataset.shape

    sampling = dataset.metadata.get("sampling") or {}
    sampling_time_ns = sampling.get("sampling_time_ns")
    if sampling_time_ns is None:
        raise ProcessingError("dataset.metadata['sampling']['sampling_time_ns'] is required for dewow")

    if valid_mask is not None:
        if valid_mask.shape != (channels_count, samples_count):
            raise ProcessingError(
                f"valid_mask shape {valid_mask.shape} does not match "
                f"(channels, samples)={(channels_count, samples_count)}"
            )
        full_valid_mask = np.asarray(valid_mask, dtype=bool)
    else:
        full_valid_mask = np.ones((channels_count, samples_count), dtype=bool)

    requested_window_samples = int(round(window_ns / sampling_time_ns))
    applied_window_samples = (
        requested_window_samples if requested_window_samples % 2 == 1 else requested_window_samples + 1
    )
    if applied_window_samples < _MIN_APPLIED_WINDOW_SAMPLES:
        raise ProcessingError(
            f"applied window ({applied_window_samples} samples, from window_ns={window_ns}, "
            f"sampling_time_ns={sampling_time_ns}) is below the minimum of "
            f"{_MIN_APPLIED_WINDOW_SAMPLES} samples"
        )
    applied_window_ns = applied_window_samples * sampling_time_ns

    input_amplitudes = dataset.amplitudes  # read-only view; never written to
    output_f64 = input_amplitudes.astype(np.float64).copy()
    removed_f64 = np.zeros((slices_count, channels_count, samples_count), dtype=np.float64)
    pad_mode = _NUMPY_PAD_MODE[edge_mode]

    segment_lengths: list[int] = []
    edge_effect_regions: dict[str, list[dict[str, int]]] = {}
    for channel in range(channels_count):
        runs = contiguous_true_runs(full_valid_mask[channel])
        edge_effect_regions[str(channel)] = []
        for start, end in runs:
            length = end - start
            segment_lengths.append(length)
            if applied_window_samples > length:
                raise ProcessingError(
                    f"channel {channel}: applied window ({applied_window_samples} samples) is wider "
                    f"than a valid segment [{start}, {end}) of length {length} -- reduce window_ns "
                    "or exclude this channel"
                )
            segment = input_amplitudes[:, channel, start:end].astype(np.float64)
            baseline = _moving_window_baseline(segment, applied_window_samples, method, pad_mode)
            output_f64[:, channel, start:end] = segment - baseline
            removed_f64[:, channel, start:end] = baseline
            half_window = applied_window_samples // 2
            edge_effect_regions[str(channel)].append(
                {
                    "segment_start": start,
                    "segment_end": end,
                    "leading_edge_effect_end": min(start + half_window, end),
                    "trailing_edge_effect_start": max(end - half_window, start),
                }
            )
    # Positions outside every valid run are left exactly as copied from
    # input_amplitudes above -- never written to, so padding (typically
    # time-zero's fill_value) is preserved byte-for-byte.

    if not np.isfinite(output_f64).all():
        raise ProcessingError("dewow correction produced NaN/Inf output")
    output_amplitudes = output_f64.astype(input_amplitudes.dtype)
    removed_component = removed_f64.astype(input_amplitudes.dtype)

    trace_mean_before = input_amplitudes.astype(np.float64).mean(axis=2)
    trace_mean_after = output_amplitudes.astype(np.float64).mean(axis=2)

    valid_broadcast = np.broadcast_to(full_valid_mask[np.newaxis, :, :], output_f64.shape)
    valid_values_after = output_f64[valid_broadcast]
    padding_values_after = output_f64[~valid_broadcast]

    diagnostics: dict[str, Any] = {
        "method": method,
        "edge_mode": edge_mode,
        "requested_window_ns": window_ns,
        "requested_window_samples": requested_window_samples,
        "applied_window_ns": applied_window_ns,
        "applied_window_samples": applied_window_samples,
        "half_window_samples": applied_window_samples // 2,
        "sampling_time_ns": sampling_time_ns,
        "valid_mask_provided": valid_mask is not None,
        "valid_segment_min_length": int(min(segment_lengths)) if segment_lengths else None,
        "valid_segment_max_length": int(max(segment_lengths)) if segment_lengths else None,
        "valid_segment_count_per_channel": {
            str(c): len(contiguous_true_runs(full_valid_mask[c])) for c in range(channels_count)
        },
        "edge_effect_regions": edge_effect_regions,
        "total_valid_samples": int(full_valid_mask.sum()) * slices_count,
        "total_padded_samples": int((~full_valid_mask).sum()) * slices_count,
        "removed_component_statistics": {
            "min": float(removed_f64.min()),
            "max": float(removed_f64.max()),
            "mean": float(removed_f64.mean()),
            "std": float(removed_f64.std()),
        },
        "output_statistics": {
            "min": float(output_f64.min()),
            "max": float(output_f64.max()),
            "mean": float(output_f64.mean()),
            "std": float(output_f64.std()),
        },
        "trace_mean_before": {
            "min": float(trace_mean_before.min()),
            "max": float(trace_mean_before.max()),
            "mean": float(trace_mean_before.mean()),
        },
        "trace_mean_after": {
            "min": float(trace_mean_after.min()),
            "max": float(trace_mean_after.max()),
            "mean": float(trace_mean_after.mean()),
        },
        "trace_mean_after_valid_only": float(valid_values_after.mean()) if valid_values_after.size else None,
        "trace_mean_after_padding_only": (
            float(padding_values_after.mean()) if padding_values_after.size else None
        ),
    }

    warnings: list[str] = []
    if requested_window_samples != applied_window_samples:
        warnings.append(
            f"requested window ({window_ns} ns = {requested_window_samples} samples) is even; "
            f"applied window was bumped up to {applied_window_samples} samples "
            f"({applied_window_ns:.4g} ns) to keep it centered"
        )
    if method == "running_median":
        warnings.append(
            "running_median is a nonlinear filter -- unlike running_mean it does not correspond "
            "to a simple linear high-pass response; use for robust QC comparison, not as the "
            "assumed canonical method"
        )

    record = build_processing_record(
        _OPERATION_NAME,
        parameters={
            "window_ns": window_ns,
            "method": method,
            "edge_mode": edge_mode,
            "valid_mask_provided": valid_mask is not None,
            "allow_repeat_processing": allow_repeat_processing,
        },
        diagnostics=diagnostics,
        warnings=tuple(warnings),
    )

    new_dataset = replace(
        dataset,
        amplitudes=output_amplitudes,
        processing_history=(*dataset.processing_history, record),
    )

    return ProcessingResult(
        dataset=new_dataset,
        removed_component=removed_component,
        diagnostics=diagnostics,
        warnings=tuple(warnings),
        valid_mask=(full_valid_mask.copy() if valid_mask is not None else None),
    )
