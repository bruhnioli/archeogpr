"""DC offset correction: remove a constant per-trace amplitude bias.

For every (slice, channel) trace independently::

    offset[i, j]      = location(trace[i, j, window AND valid])   # mean or median
    corrected[i, j, t] = trace[i, j, t] - offset[i, j]   for t in valid
    corrected[i, j, t] = trace[i, j, t]                   for t not in valid (untouched)

A single global offset is never applied to the whole volume — every trace
gets its own value. See CLAUDE.md: "Every filter must expose the removed or
difference component for QC" — ``removed_component`` here is exactly the
per-trace offset broadcast back to the full trace length (zero at any
padding/invalid position, since nothing was removed there).

``valid_mask`` (from a prior ``correct_time_zero`` call) tells this function
which samples are real shifted radar data versus padding fill — see
``ProcessingResult.valid_mask``. When given, padding positions are excluded
from BOTH the offset computation and the subtraction itself, so they are
left byte-for-byte identical to the input (no fabricated ``-offset`` band).
When omitted (the default), behavior is unchanged from before this existed:
every sample in the window is treated as valid, preserving standalone
(no time-zero) DC offset correction exactly as it worked previously.

``window_reference`` (Sprint 2.2, see ADR-004) controls how
``window_start_ns``/``window_end_ns`` are turned into a sample selection:

* ``"dataset_time"`` (default) — selects samples where
  ``dataset.time_ns`` itself falls in ``[window_start_ns, window_end_ns)``.
  After ``correct_time_zero()`` has rewritten ``time_ns`` to be
  time-zero-relative, this makes the window **target-sample-invariant**:
  the same ns window resolves to the same underlying raw samples no matter
  what ``target_sample`` was used, because it tracks the zero-event rather
  than the array's start. This is why a canonical, physically-meaningful DC
  window must never be defined against "the whole valid trace" or "sample
  0" — both drift with ``target_sample``; only a window anchored to the
  zero-event itself is stable.
* ``"sample_index"`` — the pre-Sprint-2.2 behavior: samples are selected by
  ``round(ns / sampling_time_ns)`` from sample 0, ignoring whatever
  ``dataset.time_ns`` says. Kept for standalone use on datasets that were
  never time-zero-corrected, or when literal absolute-sample windowing is
  actually what's wanted.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.common import (
    ProcessingError,
    build_processing_record,
    dataset_time_window_mask,
    ns_window_to_samples,
)
from archaeogpr.processing.result import ProcessingResult

_METHODS = ("mean", "median")
_WINDOW_REFERENCES = ("dataset_time", "sample_index")


def _stats(values: np.ndarray) -> dict[str, float]:
    return {
        "min": float(values.min()),
        "max": float(values.max()),
        "mean": float(values.mean()),
        "median": float(np.median(values)),
        "std": float(values.std()),
    }


def correct_dc_offset(
    dataset: GPRDataset,
    *,
    method: str = "mean",
    window_start_ns: float | None = None,
    window_end_ns: float | None = None,
    valid_mask: np.ndarray | None = None,
    window_reference: str = "dataset_time",
) -> ProcessingResult:
    """Subtract a per-(slice, channel) constant offset computed over an optional window.

    ``window_start_ns``/``window_end_ns`` must both be given or both omitted
    (omitted means "use the full trace"). ``window_reference`` (default
    ``"dataset_time"``) picks how they're resolved to samples — see the
    module docstring; this is the setting that makes the window
    target-sample-invariant after ``correct_time_zero()``. ``valid_mask``
    (shape ``(channels, samples)``, e.g. from ``correct_time_zero``'s
    ``ProcessingResult.valid_mask``) excludes padding from both the offset
    computation and the subtraction; pass ``None`` (the default) for
    standalone use with no time-zero-aware masking. ``dataset`` is never
    modified. Computation is done in float64 for precision; the output is
    cast back to the input's dtype. Raises ``ProcessingError`` for an
    invalid method/window/mask/window_reference, if the window selects zero
    samples at all, if a trace has zero valid samples in the selected
    window, or if the result contains NaN/Inf.
    """
    if method not in _METHODS:
        raise ProcessingError(f"method must be one of {_METHODS}, got {method!r}")
    if window_reference not in _WINDOW_REFERENCES:
        raise ProcessingError(
            f"window_reference must be one of {_WINDOW_REFERENCES}, got {window_reference!r}"
        )

    slices_count, channels_count, samples_count = dataset.shape

    if valid_mask is not None:
        if valid_mask.shape != (channels_count, samples_count):
            raise ProcessingError(
                f"valid_mask shape {valid_mask.shape} does not match "
                f"(channels, samples)={(channels_count, samples_count)}"
            )
        full_valid_mask = np.asarray(valid_mask, dtype=bool)
    else:
        full_valid_mask = np.ones((channels_count, samples_count), dtype=bool)

    sampling = dataset.metadata.get("sampling") or {}
    sampling_time_ns = sampling.get("sampling_time_ns")

    window_given = window_start_ns is not None or window_end_ns is not None
    if window_given and (window_start_ns is None or window_end_ns is None):
        raise ProcessingError("window_start_ns and window_end_ns must both be given, or both omitted")

    if not window_given:
        window_mask = np.ones(samples_count, dtype=bool)
    elif window_reference == "dataset_time":
        assert window_start_ns is not None and window_end_ns is not None  # narrowed by window_given above
        window_mask = dataset_time_window_mask(dataset.time_ns, window_start_ns, window_end_ns)
    else:  # "sample_index" -- pre-Sprint-2.2 literal absolute-sample behavior
        if sampling_time_ns is None:
            raise ProcessingError(
                "a window with window_reference='sample_index' was given but "
                "dataset.metadata['sampling']['sampling_time_ns'] is missing"
            )
        start_sample, end_sample = ns_window_to_samples(
            sampling_time_ns, samples_count, window_start_ns, window_end_ns
        )
        window_mask = np.zeros(samples_count, dtype=bool)
        window_mask[start_sample:end_sample] = True

    window_positions = np.flatnonzero(window_mask)
    window_start_sample = int(window_positions[0])
    window_end_sample = int(window_positions[-1]) + 1
    window_len = int(window_mask.sum())

    input_amplitudes = dataset.amplitudes  # read-only view; never written to
    windowed = input_amplitudes[:, :, window_mask].astype(np.float64)
    window_valid_mask = full_valid_mask[:, window_mask]

    offset = np.zeros((slices_count, channels_count), dtype=np.float64)
    valid_counts_in_window: dict[int, int] = {}
    for channel in range(channels_count):
        positions = window_valid_mask[channel]
        n_valid = int(positions.sum())
        valid_counts_in_window[channel] = n_valid
        if n_valid == 0:
            raise ProcessingError(
                f"channel {channel}: no valid samples in the selected window "
                f"[sample {window_start_sample}, {window_end_sample}) — every sample there is padding, "
                "so no DC offset can be computed for this trace"
            )
        channel_values = windowed[:, channel, :][:, positions]  # (slices, n_valid)
        offset[:, channel] = (
            channel_values.mean(axis=1) if method == "mean" else np.median(channel_values, axis=1)
        )

    if not np.isfinite(offset).all():
        raise ProcessingError("computed DC offsets contain NaN/Inf; refusing to apply them")

    output_f64 = input_amplitudes.astype(np.float64).copy()
    removed_f64 = np.zeros((slices_count, channels_count, samples_count), dtype=np.float64)
    for channel in range(channels_count):
        positions = full_valid_mask[channel]
        output_f64[:, channel, positions] -= offset[:, channel][:, np.newaxis]
        removed_f64[:, channel, positions] = offset[:, channel][:, np.newaxis]
    # Positions where full_valid_mask is False are left exactly as they were
    # copied from input_amplitudes above — never written to, so padding
    # (typically fill_value from time-zero) is preserved byte-for-byte.

    if not np.isfinite(output_f64).all():
        raise ProcessingError("DC offset correction produced NaN/Inf output")
    output_amplitudes = output_f64.astype(input_amplitudes.dtype)
    removed_component = removed_f64.astype(input_amplitudes.dtype)

    trace_mean_before = input_amplitudes.astype(np.float64).mean(axis=2)
    trace_mean_after = output_amplitudes.astype(np.float64).mean(axis=2)

    warnings: list[str] = []
    if method == "mean" and not window_given and valid_mask is None:
        warnings.append(
            "Offset computed as the full-trace mean with no window; a strong direct/air "
            "wave can bias this estimate away from the true DC bias. Consider a "
            "pre-trigger window (--window-start-ns/--window-end-ns) or method='median'."
        )

    valid_broadcast = np.broadcast_to(full_valid_mask[np.newaxis, :, :], output_f64.shape)
    valid_values_after = output_f64[valid_broadcast]
    padding_values_after = output_f64[~valid_broadcast]
    trace_mean_after_valid_only = float(valid_values_after.mean()) if valid_values_after.size else None
    trace_mean_after_padding_only = float(padding_values_after.mean()) if padding_values_after.size else None
    padding_value_stats = (
        {
            "unique_count": int(np.unique(padding_values_after).size),
            "min": float(padding_values_after.min()),
            "max": float(padding_values_after.max()),
        }
        if padding_values_after.size
        else None
    )

    diagnostics: dict[str, Any] = {
        "method": method,
        "window_start_ns": window_start_ns,
        "window_end_ns": window_end_ns,
        "window_reference": window_reference,
        "window_start_sample": window_start_sample,
        "window_end_sample": window_end_sample,
        "offset_shape": [slices_count, channels_count],
        "offset_statistics": _stats(offset),
        "trace_mean_before": _stats(trace_mean_before),
        "trace_mean_after": _stats(trace_mean_after),
        "valid_mask_provided": valid_mask is not None,
        "mask_policy": (
            "offset computed from window AND valid_mask; subtraction applied only at valid "
            "positions; padding left byte-for-byte unchanged"
            if valid_mask is not None
            else "no valid_mask provided; every sample in the window is treated as valid "
            "(standalone/backward-compatible behavior)"
        ),
        "valid_samples_per_trace_min": int(min(valid_counts_in_window.values())),
        "valid_samples_per_trace_max": int(max(valid_counts_in_window.values())),
        "valid_samples_per_channel_in_window": {str(c): n for c, n in sorted(valid_counts_in_window.items())},
        "excluded_padding_count": int(sum(window_len - n for n in valid_counts_in_window.values())),
        "trace_mean_after_valid_only": trace_mean_after_valid_only,
        "trace_mean_after_padding_only": trace_mean_after_padding_only,
        "padding_value_statistics": padding_value_stats,
    }

    record = build_processing_record(
        "dc_offset_correction",
        parameters={
            "method": method,
            "window_start_ns": window_start_ns,
            "window_end_ns": window_end_ns,
            "window_reference": window_reference,
            "valid_mask_provided": valid_mask is not None,
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
