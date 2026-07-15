"""Time-zero correction: align each channel's picked event to a target sample.

Scope for this sprint (see CLAUDE.md and the Sprint 2 task brief):

* Shifts are always **channel-wide and constant** — every slice of a given
  channel gets the exact same integer sample shift. Free, independent,
  trace-by-trace shifting is explicitly out of scope.
* No sub-sample (fractional) shifting, no phase unwrapping, no neural picker.
* An automatically detected pick is a signal-processing reference, never an
  independently calibrated physical surface time — see
  ``TIME_ZERO_REFERENCE_WARNING``, which is attached to every result.
* The output dataset's ``time_ns`` is rewritten to be time-zero-relative
  (``time_ns[target_sample] == 0.0``, samples before it negative, samples
  after it positive) — see ADR-004. This lets a downstream ns-referenced
  window (``correct_dc_offset(..., window_reference="dataset_time")``)
  select the same physical samples regardless of which ``target_sample``
  was used.

Three ways to decide each channel's shift:

1. ``"manual"`` — the caller supplies a verified sample index per channel.
2. ``"channel_median_peak"`` — pick the ``peak_polarity`` extremum of each
   channel's median trace within a search window.
3. ``"channel_median_cross_correlation"`` — pick the reference channel the
   same way, then align every other channel to it by cross-correlating
   median traces within the search window.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import numpy as np

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.common import (
    TIME_ZERO_REFERENCE_WARNING,
    ProcessingError,
    build_processing_record,
    ns_window_to_samples,
    padding_mask,
    time_zero_relative_time_ns,
    validate_target_sample,
)
from archaeogpr.processing.result import ProcessingResult

_METHODS = ("manual", "channel_median_peak", "channel_median_cross_correlation")
_PEAK_POLARITIES = ("max_abs", "positive_peak", "negative_peak")
_OVERFLOW_POLICIES = ("error", "clip")


def _peak_index(trace: np.ndarray, peak_polarity: str) -> int:
    if peak_polarity == "max_abs":
        return int(np.argmax(np.abs(trace)))
    if peak_polarity == "positive_peak":
        return int(np.argmax(trace))
    if peak_polarity == "negative_peak":
        return int(np.argmin(trace))
    raise ProcessingError(f"peak_polarity must be one of {_PEAK_POLARITIES}, got {peak_polarity!r}")


def _cross_correlation_lag(signal: np.ndarray, reference: np.ndarray, max_lag: int) -> int:
    """Best integer lag so ``np.roll(signal, lag)`` best matches ``reference``.

    Searched over ``[-max_lag, max_lag]`` using only the valid (non-wrapped)
    overlap for each candidate lag — this is a finite-window correlation,
    not a circular one, since ``signal``/``reference`` are short search-window
    segments rather than full traces.
    """
    n = signal.shape[0]
    if n == 0:
        return 0
    # Clamp to n-1 so `n - lag`/`n - m` never goes to zero or negative: Python's
    # arr[:-k] means "drop the last k", not "empty", so an unclamped lag >= n
    # would silently slice the wrong (non-empty) region instead of skipping.
    effective_max_lag = min(max_lag, n - 1)
    best_lag = 0
    best_score = -np.inf
    for lag in range(-effective_max_lag, effective_max_lag + 1):
        if lag >= 0:
            seg_signal, seg_ref = signal[: n - lag], reference[lag:]
        else:
            m = -lag
            seg_signal, seg_ref = signal[m:], reference[: n - m]
        if seg_signal.size == 0 or seg_ref.size == 0:
            continue
        score = float(np.dot(seg_signal, seg_ref))
        if score > best_score:
            best_score, best_lag = score, lag
    return best_lag


def _median_trace(amplitudes: np.ndarray, channel: int, window: tuple[int, int]) -> np.ndarray:
    """Per-trace-mean-removed median trace for one channel within a window.

    The per-trace mean removal is a temporary step used only to stabilize
    peak-picking against DC bias — it is computed on a local float64 copy
    and never written back to any output array or dataset.
    """
    start, end = window
    windowed = amplitudes[:, channel, start:end].astype(np.float64)
    centered = windowed - windowed.mean(axis=1, keepdims=True)
    return np.median(centered, axis=0)


def _resolve_channel_shifts(
    amplitudes: np.ndarray,
    *,
    method: str,
    picks: Mapping[int, int] | None,
    window: tuple[int, int] | None,
    target_sample: int,
    peak_polarity: str,
    reference_channel: int,
    max_shift_samples: int,
) -> tuple[dict[int, int], dict[int, int]]:
    """Resolve each channel's pick and *requested* (not yet overflow-checked) shift.

    Overflow handling (error vs. clip against ``max_shift_samples``) is the
    caller's responsibility — see ``_apply_overflow_policy`` — so that a
    caller can inspect the true requested shift before any policy decision.
    """
    _, channels_count, samples_count = amplitudes.shape
    channel_picks: dict[int, int] = {}
    raw_shifts: dict[int, int] = {}

    if method == "manual":
        if picks is None:
            raise ProcessingError("method='manual' requires the `picks` argument")
        missing = [c for c in range(channels_count) if c not in picks]
        if missing:
            raise ProcessingError(f"picks is missing channel(s): {missing}")
        for channel in range(channels_count):
            sample = int(picks[channel])
            if not (0 <= sample < samples_count):
                raise ProcessingError(f"picks[{channel}]={sample} out of range [0, {samples_count})")
            channel_picks[channel] = sample
            raw_shifts[channel] = target_sample - sample

    elif method in ("channel_median_peak", "channel_median_cross_correlation"):
        if window is None:
            raise ProcessingError(f"method={method!r} requires a search window")
        median_traces = {c: _median_trace(amplitudes, c, window) for c in range(channels_count)}
        window_start = window[0]

        if method == "channel_median_peak":
            for channel in range(channels_count):
                picked = window_start + _peak_index(median_traces[channel], peak_polarity)
                channel_picks[channel] = picked
                raw_shifts[channel] = target_sample - picked
        else:
            ref_picked = window_start + _peak_index(median_traces[reference_channel], peak_polarity)
            channel_picks[reference_channel] = ref_picked
            shift_ref = target_sample - ref_picked
            raw_shifts[reference_channel] = shift_ref
            for channel in range(channels_count):
                if channel == reference_channel:
                    continue
                lag = _cross_correlation_lag(
                    median_traces[channel], median_traces[reference_channel], max_shift_samples
                )
                shift = shift_ref + lag
                raw_shifts[channel] = shift
                channel_picks[channel] = target_sample - shift
    else:
        raise ProcessingError(f"method must be one of {_METHODS}, got {method!r}")

    return channel_picks, raw_shifts


def _apply_overflow_policy(
    raw_shifts: dict[int, int],
    *,
    max_shift_samples: int,
    overflow_policy: str,
) -> tuple[dict[int, int], bool, list[str]]:
    """Resolve overflow per ``overflow_policy``. Returns (final_shifts, has_clipped_shifts, warnings).

    ``"error"`` (the default) raises ``ProcessingError`` — before any data is
    touched — if any channel's requested shift exceeds ``max_shift_samples``,
    so a clipped/misaligned result is never silently written out as if it
    were a normal success. ``"clip"`` clips and returns a result the caller
    must mark ``valid_for_downstream_processing=False``.
    """
    if overflow_policy not in _OVERFLOW_POLICIES:
        raise ProcessingError(f"overflow_policy must be one of {_OVERFLOW_POLICIES}, got {overflow_policy!r}")

    overflowing = {c: s for c, s in raw_shifts.items() if abs(s) > max_shift_samples}
    if not overflowing:
        return dict(raw_shifts), False, []

    if overflow_policy == "error":
        details = "; ".join(
            f"channel {c}: requested shift {s} (|{s}| > {max_shift_samples})"
            for c, s in sorted(overflowing.items())
        )
        raise ProcessingError(
            f"time-zero correction aborted: {len(overflowing)} of {len(raw_shifts)} channel(s) need a "
            f"shift larger than max_shift_samples={max_shift_samples}: {details}. Raise "
            "--max-shift-samples (or the max_shift_samples argument) to accommodate the true shift, or "
            "pass overflow_policy='clip' to explicitly accept a clipped, non-canonical result instead."
        )

    warnings: list[str] = []
    clipped_shifts: dict[int, int] = {}
    for channel, shift in raw_shifts.items():
        clipped = int(np.clip(shift, -max_shift_samples, max_shift_samples))
        clipped_shifts[channel] = clipped
        if clipped != shift:
            warnings.append(
                f"channel {channel}: requested shift {shift} exceeds "
                f"max_shift_samples={max_shift_samples}; clipped to {clipped} "
                "(has_clipped_shifts=true, valid_for_downstream_processing=false)"
            )
    return clipped_shifts, True, warnings


def correct_time_zero(
    dataset: GPRDataset,
    *,
    method: str = "channel_median_peak",
    picks: Mapping[int, int] | None = None,
    search_start_ns: float = 5.0,
    search_end_ns: float = 15.0,
    target_sample: int = 0,
    peak_polarity: str = "max_abs",
    reference_channel: int = 0,
    max_shift_samples: int = 64,
    fill_value: float = 0.0,
    overflow_policy: str = "error",
) -> ProcessingResult:
    """Shift every channel (channel-wide, constant shift) to align a picked event.

    ``dataset`` is never modified; the returned ``ProcessingResult.dataset``
    is a new ``GPRDataset`` with the same shape and dtype. ``method="manual"``
    requires ``picks`` (one sample index per channel, 0..channels-1, all
    required). The two automatic methods search only within
    ``[search_start_ns, search_end_ns)``, never outside it.

    The returned dataset's ``time_ns`` is a **new** array,
    ``(arange(samples) - target_sample) * sampling_time_ns`` — i.e.
    time-zero-relative: ``time_ns[target_sample] == 0.0`` exactly, negative
    before it, positive after it. ``dataset.metadata['sampling']
    ['sampling_time_ns']`` is therefore required for every method, not only
    the automatic ones. The previous axis is not discarded silently — its
    defining start/end are recorded in
    ``diagnostics["time_axis"]``. See ADR-004; this remains a
    signal-processing reference, never a calibrated physical surface time.

    ``overflow_policy`` controls what happens when a channel's *requested*
    shift exceeds ``max_shift_samples``:

    * ``"error"`` (default) — raise ``ProcessingError`` before touching any
      data. A clipped/misaligned dataset is never written out as if it were
      a normal successful result.
    * ``"clip"`` — clip to ``max_shift_samples`` and proceed, but mark the
      result ``diagnostics["has_clipped_shifts"] = True`` and
      ``diagnostics["valid_for_downstream_processing"] = False``, and add an
      explicit warning. Callers/CLIs must treat this as a non-canonical,
      explicitly-opted-into result — never overwrite a canonical output with
      one produced this way without human review.

    Raises ``ProcessingError`` for an invalid method/window/target_sample/
    overflow_policy, or (under ``overflow_policy="error"``) for an
    unaccommodated shift.
    """
    if method not in _METHODS:
        raise ProcessingError(f"method must be one of {_METHODS}, got {method!r}")
    if overflow_policy not in _OVERFLOW_POLICIES:
        raise ProcessingError(f"overflow_policy must be one of {_OVERFLOW_POLICIES}, got {overflow_policy!r}")

    slices_count, channels_count, samples_count = dataset.shape
    validate_target_sample(target_sample, samples_count)
    if not (0 <= reference_channel < channels_count):
        raise ProcessingError(f"reference_channel={reference_channel} out of range [0, {channels_count})")
    if max_shift_samples < 0:
        raise ProcessingError(f"max_shift_samples must be >= 0, got {max_shift_samples}")

    sampling = dataset.metadata.get("sampling") or {}
    sampling_time_ns = sampling.get("sampling_time_ns")
    if sampling_time_ns is None:
        raise ProcessingError(
            "dataset.metadata['sampling']['sampling_time_ns'] is required (for every method) "
            "to produce a time-zero-relative time_ns axis — see ADR-004"
        )

    window: tuple[int, int] | None = None
    if method in ("channel_median_peak", "channel_median_cross_correlation"):
        window = ns_window_to_samples(sampling_time_ns, samples_count, search_start_ns, search_end_ns)

    channel_picks, requested_shifts = _resolve_channel_shifts(
        dataset.amplitudes,
        method=method,
        picks=picks,
        window=window,
        target_sample=target_sample,
        peak_polarity=peak_polarity,
        reference_channel=reference_channel,
        max_shift_samples=max_shift_samples,
    )

    # May raise (overflow_policy="error") before any data is touched.
    channel_shifts, has_clipped_shifts, overflow_warnings = _apply_overflow_policy(
        requested_shifts, max_shift_samples=max_shift_samples, overflow_policy=overflow_policy
    )

    input_amplitudes = dataset.amplitudes  # read-only view; never written to
    output_amplitudes = input_amplitudes.copy()
    padding_counts: dict[int, int] = {}
    valid_mask = np.ones((channels_count, samples_count), dtype=bool)

    for channel in range(channels_count):
        shift = channel_shifts[channel]
        mask = padding_mask(shift, samples_count)
        padding_counts[channel] = int(mask.sum())
        valid_mask[channel, :] = ~mask
        if shift == 0:
            continue
        rolled = np.roll(input_amplitudes[:, channel, :], shift, axis=-1)
        rolled[:, mask] = fill_value
        output_amplitudes[:, channel, :] = rolled

    removed_component = (input_amplitudes.astype(np.float64) - output_amplitudes.astype(np.float64)).astype(
        input_amplitudes.dtype
    )

    valid_counts_per_channel = {c: samples_count - n for c, n in padding_counts.items()}
    total_valid_samples = sum(valid_counts_per_channel.values()) * slices_count
    total_padded_samples = sum(padding_counts.values()) * slices_count

    # Corrected time axis: time_ns[target_sample] == 0.0 exactly, samples before it
    # negative, samples after it positive. The *previous* axis is recorded by its
    # defining (start, end) rather than copied in full -- see ADR-004; this is a
    # signal-processing reference frame, not a physical calibration (see
    # TIME_ZERO_REFERENCE_WARNING).
    previous_time_ns = dataset.time_ns
    corrected_time_ns = time_zero_relative_time_ns(samples_count, target_sample, sampling_time_ns)
    time_axis_diagnostics: dict[str, Any] = {
        "target_sample": target_sample,
        "time_zero_reference_ns": 0.0,
        "sampling_time_ns": sampling_time_ns,
        "negative_time_sample_count": int(target_sample),
        "previous_time_ns_start": float(previous_time_ns[0]),
        "previous_time_ns_end": float(previous_time_ns[-1]),
        "corrected_time_ns_start": float(corrected_time_ns[0]),
        "corrected_time_ns_end": float(corrected_time_ns[-1]),
    }

    shifts_list = list(channel_shifts.values())
    diagnostics: dict[str, Any] = {
        "method": method,
        "sampling_time_ns": sampling_time_ns,
        "peak_polarity": peak_polarity if method != "manual" else None,
        "search_window_ns": [search_start_ns, search_end_ns] if window is not None else None,
        "search_window_samples": list(window) if window is not None else None,
        "target_sample": target_sample,
        "reference_channel": reference_channel if method == "channel_median_cross_correlation" else None,
        "max_shift_samples": max_shift_samples,
        "fill_value": float(fill_value),
        "overflow_policy": overflow_policy,
        "has_clipped_shifts": has_clipped_shifts,
        "valid_for_downstream_processing": not has_clipped_shifts,
        "channel_picks": {str(c): p for c, p in sorted(channel_picks.items())},
        "channel_picks_time_ns": (
            {str(c): p * sampling_time_ns for c, p in sorted(channel_picks.items())}
            if sampling_time_ns is not None
            else None
        ),
        "requested_shifts": {str(c): s for c, s in sorted(requested_shifts.items())},
        "channel_shifts": {str(c): s for c, s in sorted(channel_shifts.items())},
        "padding_sample_counts": {str(c): n for c, n in sorted(padding_counts.items())},
        "valid_sample_counts": {str(c): n for c, n in sorted(valid_counts_per_channel.items())},
        "total_valid_samples": total_valid_samples,
        "total_padded_samples": total_padded_samples,
        "min_shift": int(min(shifts_list)),
        "max_shift": int(max(shifts_list)),
        "median_shift": float(np.median(shifts_list)),
        "time_axis": time_axis_diagnostics,
    }

    all_warnings = (*overflow_warnings, TIME_ZERO_REFERENCE_WARNING)

    record = build_processing_record(
        "time_zero_correction",
        parameters={
            "method": method,
            "picks": {str(c): int(p) for c, p in picks.items()} if picks else None,
            "search_start_ns": search_start_ns,
            "search_end_ns": search_end_ns,
            "target_sample": target_sample,
            "peak_polarity": peak_polarity,
            "reference_channel": reference_channel,
            "max_shift_samples": max_shift_samples,
            "fill_value": float(fill_value),
            "overflow_policy": overflow_policy,
        },
        diagnostics=diagnostics,
        warnings=all_warnings,
    )

    new_dataset = replace(
        dataset,
        amplitudes=output_amplitudes,
        time_ns=corrected_time_ns,
        processing_history=(*dataset.processing_history, record),
    )

    return ProcessingResult(
        dataset=new_dataset,
        removed_component=removed_component,
        diagnostics=diagnostics,
        warnings=all_warnings,
        valid_mask=valid_mask,
    )
