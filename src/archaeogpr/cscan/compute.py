"""Compute a single C-scan value grid from one time sample or time window.

See the module docstring in ``archaeogpr.cscan.models`` for the scientific
scope of "C-scan" here. Nothing in this module imports Qt, pyqtgraph, the
``gui`` package, or ``archaeogpr.geometry`` — it operates purely on
``GPRDataset.amplitudes``/``time_ns`` and an optional
``ProcessingResult``-shaped ``valid_mask``.
"""

from __future__ import annotations

import numpy as np

from archaeogpr.cscan.models import (
    CScanAggregation,
    CScanError,
    CScanRequest,
    CScanResult,
    CScanStatistics,
)
from archaeogpr.model.dataset import GPRDataset

__all__ = ["compute_cscan"]


def _validate_time_axis(time_ns: np.ndarray) -> None:
    if time_ns.ndim != 1 or time_ns.size < 2:
        raise CScanError(f"time_ns must be a 1-D array with at least 2 samples, got shape {time_ns.shape}")
    if not np.all(np.isfinite(time_ns)):
        raise CScanError("time_ns contains non-finite values; cannot select a time sample/window")
    if not np.all(np.diff(time_ns) > 0):
        raise CScanError(
            "time_ns is not strictly increasing; a C-scan time selection requires a "
            "monotonic time axis (this check is independent of any geometry readiness gate)"
        )


def _select_single_sample(
    time_ns: np.ndarray, center_time_ns: float
) -> tuple[int, int, int, tuple[str, ...]]:
    """Return ``(selected_index, start_index, stop_index, warnings)`` for SINGLE_SAMPLE.

    ``start_index``/``stop_index`` are the one-element half-open range
    ``(selected_index, selected_index + 1)``. A center time outside
    ``time_ns``'s own range is not an error — the nearest edge sample is
    still well-defined — but is reported with a warning.
    """
    selected_index = int(np.argmin(np.abs(time_ns - center_time_ns)))
    warnings: tuple[str, ...] = ()
    if center_time_ns < time_ns[0] or center_time_ns > time_ns[-1]:
        warnings = (
            f"Requested center time {center_time_ns:.3f} ns is outside the dataset's time range "
            f"[{time_ns[0]:.3f}, {time_ns[-1]:.3f}] ns; using the nearest edge sample "
            f"(time_ns[{selected_index}] = {time_ns[selected_index]:.3f} ns).",
        )
    return selected_index, selected_index, selected_index + 1, warnings


def _select_window(
    time_ns: np.ndarray, center_time_ns: float, window_width_ns: float
) -> tuple[int, int, tuple[str, ...]]:
    """Return ``(start_index, stop_index, warnings)`` for a half-open ``[start, stop)`` window.

    Raises ``CScanError`` only if the requested ``[center - width/2, center +
    width/2)`` window falls entirely outside ``time_ns``'s range. A window
    that partially overlaps is silently clamped to what actually exists, and
    reported via a warning naming the actual time range used — it is never
    treated as an error, and never produces a wrong result by pretending the
    full requested width was used.
    """
    requested_start_ns = center_time_ns - window_width_ns / 2.0
    requested_stop_ns = center_time_ns + window_width_ns / 2.0
    axis_min, axis_max = float(time_ns[0]), float(time_ns[-1])

    if requested_stop_ns <= axis_min or requested_start_ns > axis_max:
        raise CScanError(
            f"window [{requested_start_ns:.3f}, {requested_stop_ns:.3f}) ns is entirely outside "
            f"the dataset's time range [{axis_min:.3f}, {axis_max:.3f}] ns"
        )

    mask = (time_ns >= requested_start_ns) & (time_ns < requested_stop_ns)
    if not mask.any():
        # The requested range straddles a gap wider than the sample spacing
        # (only possible with a non-uniform time_ns) with no sample inside it.
        raise CScanError(
            f"window [{requested_start_ns:.3f}, {requested_stop_ns:.3f}) ns selects zero samples"
        )
    positions = np.flatnonzero(mask)
    start_index = int(positions[0])
    stop_index = int(positions[-1]) + 1

    warnings: tuple[str, ...] = ()
    actual_start_ns = float(time_ns[start_index])
    clamped_low = requested_start_ns < axis_min
    clamped_high = requested_stop_ns > axis_max
    if clamped_low or clamped_high:
        actual_stop_report_ns = (
            float(time_ns[stop_index]) if stop_index < time_ns.size else float(time_ns[-1])
        )
        warnings = (
            f"Requested window [{requested_start_ns:.3f}, {requested_stop_ns:.3f}) ns was clamped "
            f"to the dataset's available time range; actual window used: "
            f"[{actual_start_ns:.3f}, {actual_stop_report_ns:.3f}) ns "
            f"(samples [{start_index}, {stop_index})).",
        )
    return start_index, stop_index, warnings


def _aggregate(window: np.ndarray, aggregation: CScanAggregation, finite: np.ndarray) -> np.ndarray:
    """``window``/``finite`` shape ``(trace_count, channel_count, window_len)``.

    ``finite`` marks which window samples are usable (valid_mask AND
    finite-amplitude). Returns ``(trace_count, channel_count)``, with
    ``np.nan`` at any cell with zero usable samples in the window.
    """
    safe = np.where(finite, window, 0.0).astype(np.float64)
    usable_count = finite.sum(axis=2)
    with np.errstate(invalid="ignore", divide="ignore"):
        if aggregation is CScanAggregation.RMS:
            mean_sq = safe.astype(np.float64) ** 2
            values = np.sqrt(mean_sq.sum(axis=2) / usable_count)
        elif aggregation is CScanAggregation.MEAN_ABSOLUTE:
            values = np.abs(safe).sum(axis=2) / usable_count
        elif aggregation is CScanAggregation.MAXIMUM_ABSOLUTE:
            abs_safe = np.where(finite, np.abs(window), -np.inf)
            values = abs_safe.max(axis=2)
        else:
            raise CScanError(f"unsupported window aggregation {aggregation!r}")
    values = np.where(usable_count > 0, values, np.nan)
    return values


def compute_cscan(
    dataset: GPRDataset,
    request: CScanRequest,
    *,
    valid_mask: np.ndarray | None = None,
) -> CScanResult:
    """Compute one ``(trace_count, channel_count)`` C-scan value grid.

    ``valid_mask`` (shape ``(channel_count, sample_count)``, e.g. from
    ``DatasetSession.current_valid_mask``/``preview_valid_mask``) is
    optional; when omitted every sample is treated as valid. A cell is
    invalid in the result — ``np.nan`` in ``values``, ``False`` in
    ``valid_mask`` — if every sample it would use is masked invalid or
    non-finite (``SINGLE_SAMPLE``: that one sample; a window aggregation:
    every sample in the window). ``dataset`` is never modified.

    Raises ``CScanError`` for an invalid request/mask, a non-monotonic
    ``time_ns``, or a window that falls entirely outside the dataset's time
    range.
    """
    amplitudes = dataset.amplitudes
    time_ns = dataset.time_ns
    trace_count, channel_count, sample_count = amplitudes.shape
    _validate_time_axis(time_ns)

    if valid_mask is not None:
        if valid_mask.shape != (channel_count, sample_count):
            raise CScanError(
                f"valid_mask shape {valid_mask.shape} does not match "
                f"(channel_count, sample_count)={(channel_count, sample_count)}"
            )
        full_valid_mask = np.asarray(valid_mask, dtype=bool)
    else:
        full_valid_mask = np.ones((channel_count, sample_count), dtype=bool)

    warnings: tuple[str, ...] = ()
    if request.aggregation is CScanAggregation.SINGLE_SAMPLE:
        selected_index, start_index, stop_index, warnings = _select_single_sample(
            time_ns, request.center_time_ns
        )
    else:
        assert request.window_width_ns is not None  # enforced by CScanRequest.__post_init__
        selected_index = None
        start_index, stop_index, warnings = _select_window(
            time_ns, request.center_time_ns, request.window_width_ns
        )

    window_amplitudes = amplitudes[:, :, start_index:stop_index]
    window_valid = full_valid_mask[:, start_index:stop_index]
    window_finite = np.isfinite(window_amplitudes) & window_valid[np.newaxis, :, :]

    if request.aggregation is CScanAggregation.SINGLE_SAMPLE:
        sample_finite = window_finite[:, :, 0]  # (trace_count, channel_count)
        values = np.where(sample_finite, window_amplitudes[:, :, 0], np.nan).astype(np.float64)
        cell_valid = sample_finite
    else:
        values = _aggregate(window_amplitudes, request.aggregation, window_finite)
        cell_valid = np.isfinite(values)

    if not np.array_equal(cell_valid, np.isfinite(values)):
        # Defensive invariant check: NaN in values must exactly match invalid cells.
        raise CScanError("internal error: values/valid_mask disagreement after aggregation")

    finite_values = values[cell_valid]
    statistics = CScanStatistics(
        valid_count=int(cell_valid.sum()),
        invalid_count=int((~cell_valid).sum()),
        min_value=float(finite_values.min()) if finite_values.size else None,
        max_value=float(finite_values.max()) if finite_values.size else None,
        mean_value=float(finite_values.mean()) if finite_values.size else None,
    )
    if statistics.valid_count == 0:
        warnings = (
            *warnings,
            "Every cell in this C-scan is invalid (no usable sample in the selected "
            "time selection for any trace/channel).",
        )

    actual_start_time_ns = float(time_ns[start_index])
    actual_stop_time_ns = (
        float(time_ns[stop_index]) if stop_index < sample_count else float(time_ns[stop_index - 1])
    )

    return CScanResult(
        values=values,
        valid_mask=cell_valid,
        aggregation=request.aggregation,
        requested_center_time_ns=request.center_time_ns,
        requested_window_width_ns=request.window_width_ns,
        selected_sample_index=selected_index,
        sample_start_index=start_index,
        sample_stop_index=stop_index,
        actual_start_time_ns=actual_start_time_ns,
        actual_stop_time_ns=actual_stop_time_ns,
        source_kind=request.source_kind,
        source_revision=request.source_revision,
        geometry_revision=request.geometry_revision,
        warnings=warnings,
        statistics=statistics,
        metadata={
            "trace_count": trace_count,
            "channel_count": channel_count,
            "window_sample_count": stop_index - start_index,
            "valid_mask_provided": valid_mask is not None,
            "input_dtype": str(amplitudes.dtype),
        },
    )
