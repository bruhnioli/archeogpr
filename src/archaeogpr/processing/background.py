"""Background removal: reduce a component shared across traces along one channel.

For every channel independently, at every *valid* (non-padding) sample
position::

    background(sample) = TraceAxisStatistic(amplitudes[:, channel, sample])
    corrected(slice, sample) = amplitudes[slice, channel, sample] - background(sample)

where ``TraceAxisStatistic`` is one of four supported methods:

- ``global_mean`` / ``global_median`` -- one background value per sample,
  shared by every trace in the profile.
- ``sliding_mean`` / ``sliding_median`` -- a centered window of neighboring
  traces (along-track position), re-estimated at every trace.

Averaging only ever happens along the slice (trace) axis -- never across
samples (time) or channels; see ``_global_background``/``_sliding_background``.
This is, by a wide margin, the most scientifically risky filter this
project has implemented: a genuinely long, laterally continuous
archaeological reflection (a floor, a wall foundation, a layer boundary) is
removed exactly as effectively as unwanted common-mode noise -- background
removal cannot distinguish the two on its own. See CLAUDE.md and
ADR-008. No candidate produced here is ever canonical; that selection is
reserved for human/geophysical review (Sprint 4A).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.common import ProcessingError, build_processing_record
from archaeogpr.processing.result import ProcessingResult

_GLOBAL_METHODS = ("global_mean", "global_median")
_SLIDING_METHODS = ("sliding_mean", "sliding_median")
_METHODS = _GLOBAL_METHODS + _SLIDING_METHODS
_EDGE_MODES = ("reflect", "nearest")
_OPERATION_NAME = "background_removal"
_MIN_APPLIED_WINDOW_TRACES = 3

#: numpy.pad mode for each supported edge_mode -- same convention as
#: processing/dewow.py: "reflect" mirrors the profile's own values without
#: repeating the edge trace, "nearest" repeats the edge trace outward.
_NUMPY_PAD_MODE: dict[str, Literal["reflect", "edge"]] = {"reflect": "reflect", "nearest": "edge"}

#: Warn (not error) if pooled along-track interval spacing varies by more
#: than this fraction of its own mean -- an engineering QC threshold
#: documented in ADR-008, not a physical claim about survey quality.
TRACE_SPACING_CV_WARNING_THRESHOLD = 0.05

#: An along-track interval more than this multiple of its own channel's
#: median is treated as a bad geolocation fix (a jump/outlier), not a real
#: local spacing change, and excluded before taking that channel's median.
_TRACE_SPACING_OUTLIER_MULTIPLE = 5.0


def compute_trace_spacing(dataset: GPRDataset) -> dict[str, Any]:
    """Along-track trace spacing, for ``window_m``<->trace-count conversion.

    Priority order:

    1. **Plan-view geolocation**, computed independently per channel: each
       channel's own consecutive-slice (x, y) distances, with zero,
       non-finite, and outlier intervals excluded (see
       ``_TRACE_SPACING_OUTLIER_MULTIPLE``), then that channel's median.
       The reported ``trace_spacing_m`` is the median of those per-channel
       medians -- a single channel's local geolocation noise cannot by
       itself swing the result.
    2. **The file's own metadata** ``sampling.sampling_step_m``, used only
       if there is no usable geolocation (e.g. this project's processed
       NPZs do not currently carry geolocation arrays).

    Returns ``trace_spacing_m=None`` (``trace_spacing_source="unavailable"``)
    if neither is available -- callers must reject a ``window_m`` request
    in that case rather than guessing one.

    Every distance here is a *local*, consecutive-slice difference -- this
    is never an absolute-map-accuracy claim and is computed identically
    whether or not the header's CRS has been independently validated (see
    CLAUDE.md, ADR-001 ISSUE-001).
    """
    if dataset.x is not None and dataset.y is not None:
        slices_count, channels_count = dataset.x.shape
        if slices_count >= 2:
            per_channel_median: dict[str, float] = {}
            pooled_intervals: list[float] = []
            for channel in range(channels_count):
                dx = np.diff(dataset.x[:, channel].astype(np.float64))
                dy = np.diff(dataset.y[:, channel].astype(np.float64))
                distances = np.hypot(dx, dy)
                finite = distances[np.isfinite(distances) & (distances > 0)]
                if finite.size == 0:
                    continue
                channel_median = float(np.median(finite))
                if channel_median > 0:
                    not_outlier = finite[finite <= _TRACE_SPACING_OUTLIER_MULTIPLE * channel_median]
                    if not_outlier.size:
                        finite = not_outlier
                        channel_median = float(np.median(finite))
                per_channel_median[str(channel)] = channel_median
                pooled_intervals.extend(float(v) for v in finite)

            if per_channel_median:
                pooled = np.array(pooled_intervals, dtype=np.float64)
                mean = float(pooled.mean())
                std = float(pooled.std())
                cv = (std / mean) if mean > 0 else float("nan")
                spacing_warnings: list[str] = []
                if np.isfinite(cv) and cv > TRACE_SPACING_CV_WARNING_THRESHOLD:
                    spacing_warnings.append(
                        f"along-track trace-spacing coefficient of variation ({cv:.4g}) exceeds "
                        f"{TRACE_SPACING_CV_WARNING_THRESHOLD:.0%} -- window_m<->trace conversions "
                        "assume a roughly uniform spacing; treat applied_window_m as approximate"
                    )
                return {
                    "trace_spacing_source": "geolocation",
                    "trace_spacing_m": float(np.median(list(per_channel_median.values()))),
                    "per_channel_trace_spacing_median": per_channel_median,
                    "trace_spacing_mean": mean,
                    "trace_spacing_std": std,
                    "trace_spacing_cv": cv,
                    "number_of_valid_intervals": int(pooled.size),
                    "warnings": spacing_warnings,
                }

    sampling = dataset.metadata.get("sampling") or {}
    sampling_step_m = sampling.get("sampling_step_m")
    if sampling_step_m is not None:
        return {
            "trace_spacing_source": "metadata_sampling_step",
            "trace_spacing_m": float(sampling_step_m),
            "per_channel_trace_spacing_median": None,
            "trace_spacing_mean": None,
            "trace_spacing_std": None,
            "trace_spacing_cv": None,
            "number_of_valid_intervals": None,
            "warnings": [
                "trace spacing came from metadata sampling.sampling_step_m, not measured "
                "plan-view geolocation -- treat as a nominal survey-design value, not a "
                "per-channel measurement"
            ],
        }

    return {
        "trace_spacing_source": "unavailable",
        "trace_spacing_m": None,
        "per_channel_trace_spacing_median": None,
        "trace_spacing_mean": None,
        "trace_spacing_std": None,
        "trace_spacing_cv": None,
        "number_of_valid_intervals": None,
        "warnings": [
            "no plan-view geolocation and no metadata sampling.sampling_step_m -- window_m "
            "cannot be converted to a trace count; pass trace_spacing_m explicitly or use "
            "window_traces instead"
        ],
    }


def _global_background(column: np.ndarray, method: str) -> np.ndarray:
    """``column`` shape ``(slices, n_valid_samples)`` -> shape ``(n_valid_samples,)``."""
    if method == "global_mean":
        return column.mean(axis=0)
    return np.median(column, axis=0)


def _sliding_background(
    column: np.ndarray, window_traces: int, method: str, pad_mode: Literal["reflect", "edge"]
) -> np.ndarray:
    """``column`` shape ``(slices, n_valid_samples)`` -> same shape out.

    Pads only along the slice (trace) axis, using this channel's own valid
    values -- never reaching into another channel or a padding sample.
    """
    half_window = window_traces // 2
    padded = np.pad(column, ((half_window, half_window), (0, 0)), mode=pad_mode)
    windows = sliding_window_view(padded, window_traces, axis=0)  # (slices, n_valid_samples, window_traces)
    if method == "sliding_mean":
        return windows.mean(axis=-1)
    return np.median(windows, axis=-1)


def remove_background(
    dataset: GPRDataset,
    *,
    method: str,
    valid_mask: np.ndarray | None = None,
    window_traces: int | None = None,
    window_m: float | None = None,
    edge_mode: str = "reflect",
    trace_spacing_m: float | None = None,
    allow_reprocessing: bool = False,
) -> ProcessingResult:
    """Subtract a per-channel, trace-axis background estimate from every trace.

    ``dataset`` is never modified. ``method`` selects the estimator:
    ``"global_mean"``/``"global_median"`` (whole-profile, ``window_traces``/
    ``window_m`` must both be omitted) or ``"sliding_mean"``/
    ``"sliding_median"`` (centered along-track window; give exactly one of
    ``window_traces`` or ``window_m``). ``window_m`` is converted to an odd
    trace count via :func:`compute_trace_spacing` unless ``trace_spacing_m``
    is given explicitly (in which case that value is used as-is, and
    ``compute_trace_spacing`` is not called). ``valid_mask`` (shape
    ``(channels, samples)``) excludes padding from both the background
    estimate and the subtraction; pass ``None`` to treat every sample as
    valid. Raises ``ProcessingError`` for an invalid method/edge_mode, a
    window specified for a global method, zero or two of
    ``window_traces``/``window_m`` given for a sliding method, a
    ``window_m`` request with no available trace spacing, an applied
    window under 3 traces or wider than the profile itself, a
    ``background_removal`` already present in ``dataset.processing_history``
    (unless ``allow_reprocessing=True``), or NaN/Inf output.

    ``diagnostics["applied_window_m"]`` is kept only for backward
    compatibility and is ambiguous -- it equals ``applied_window_traces *
    trace_spacing_m`` (a "nominal length"), which is NOT the window's
    physical center-to-center span. Prefer the explicit, unambiguous
    fields instead: ``applied_window_nominal_length_m`` (same value,
    clearly named), ``applied_window_center_to_center_span_m`` (``=
    (applied_window_traces - 1) * trace_spacing_m``, the actual distance
    between the window's first and last trace), and ``window_half_span_m``
    (``= center_to_center_span_m / 2``). See ADR-008 (Sprint 4A.1
    correction) -- ``applied_window_m`` must not be presented as a
    physical span in human-decision reports.
    """
    if method not in _METHODS:
        raise ProcessingError(f"method must be one of {_METHODS}, got {method!r}")
    if edge_mode not in _EDGE_MODES:
        raise ProcessingError(f"edge_mode must be one of {_EDGE_MODES}, got {edge_mode!r}")

    existing_ops = [record["operation"] for record in dataset.processing_history]
    if _OPERATION_NAME in existing_ops and not allow_reprocessing:
        raise ProcessingError(
            f"dataset.processing_history already contains {_OPERATION_NAME!r} "
            f"({existing_ops.count(_OPERATION_NAME)} time(s)); pass allow_reprocessing=True "
            "to apply it again deliberately"
        )

    slices_count, channels_count, samples_count = dataset.shape
    is_global = method in _GLOBAL_METHODS

    if is_global:
        if window_traces is not None or window_m is not None:
            raise ProcessingError(f"method={method!r} is global -- window_traces/window_m must not be given")
    elif window_traces is not None and window_m is not None:
        raise ProcessingError("give exactly one of window_traces or window_m, not both")
    elif window_traces is None and window_m is None:
        raise ProcessingError(f"method={method!r} requires exactly one of window_traces or window_m")

    spacing_info: dict[str, Any] | None = None
    requested_window_m: float | None = None
    raw_window_traces_float: float | None = None
    applied_window_traces: int | None = None
    applied_window_m: float | None = None
    applied_window_nominal_length_m: float | None = None
    applied_window_center_to_center_span_m: float | None = None
    window_half_span_m: float | None = None
    rounding_policy: str | None = None

    if not is_global:
        rounding_policy = (
            "round(raw_window_traces_float) to the nearest integer, then bump up by 1 if the "
            f"result is even (a centered window needs an odd trace count); {_MIN_APPLIED_WINDOW_TRACES} "
            "traces is the enforced minimum, raised as an explicit error rather than silently applied"
        )
        if window_m is not None:
            if trace_spacing_m is not None:
                spacing_info = {
                    "trace_spacing_source": "explicit_override",
                    "trace_spacing_m": float(trace_spacing_m),
                    "per_channel_trace_spacing_median": None,
                    "trace_spacing_mean": None,
                    "trace_spacing_std": None,
                    "trace_spacing_cv": None,
                    "number_of_valid_intervals": None,
                    "warnings": [],
                }
            else:
                spacing_info = compute_trace_spacing(dataset)
            if spacing_info["trace_spacing_m"] is None:
                raise ProcessingError(
                    "window_m was given but no trace spacing is available (no geolocation, no "
                    "metadata sampling_step_m) -- pass trace_spacing_m explicitly or use "
                    "window_traces instead"
                )
            requested_window_m = window_m
            raw_window_traces_float = window_m / spacing_info["trace_spacing_m"]
        else:
            assert window_traces is not None  # guaranteed by the window_traces/window_m check above
            raw_window_traces_float = float(window_traces)
            # trace spacing is still reported (for QC/CSV completeness) even
            # though this path doesn't need it for the conversion itself.
            spacing_info = (
                {
                    "trace_spacing_source": "explicit_override",
                    "trace_spacing_m": float(trace_spacing_m),
                    "per_channel_trace_spacing_median": None,
                    "trace_spacing_mean": None,
                    "trace_spacing_std": None,
                    "trace_spacing_cv": None,
                    "number_of_valid_intervals": None,
                    "warnings": [],
                }
                if trace_spacing_m is not None
                else compute_trace_spacing(dataset)
            )

        rounded = int(round(raw_window_traces_float))
        applied_window_traces = rounded if rounded % 2 == 1 else rounded + 1
        if applied_window_traces < _MIN_APPLIED_WINDOW_TRACES:
            source_desc = f"window_m={window_m}" if window_m is not None else f"window_traces={window_traces}"
            raise ProcessingError(
                f"applied window ({applied_window_traces} traces, from {source_desc}) is below "
                f"the minimum of {_MIN_APPLIED_WINDOW_TRACES} traces"
            )
        if applied_window_traces > slices_count:
            raise ProcessingError(
                f"applied window ({applied_window_traces} traces) is wider than the profile "
                f"({slices_count} traces) -- reduce window_m/window_traces"
            )
        if spacing_info.get("trace_spacing_m") is not None:
            trace_spacing_m_value = spacing_info["trace_spacing_m"]
            # "applied_window_m" (below) is ambiguous and kept only for
            # backward compatibility -- it is numerically identical to
            # "nominal length" (trace count * spacing), which is NOT the
            # same thing as the window's physical center-to-center span
            # (Sprint 4A.1 correction; see ADR-008). Report both explicitly.
            applied_window_m = applied_window_traces * trace_spacing_m_value
            applied_window_nominal_length_m = applied_window_traces * trace_spacing_m_value
            applied_window_center_to_center_span_m = (applied_window_traces - 1) * trace_spacing_m_value
            window_half_span_m = ((applied_window_traces - 1) / 2) * trace_spacing_m_value
    else:
        # Global methods have no window, but trace spacing is still useful
        # QC context (e.g. trace_spacing_and_window.json is written per
        # candidate, including global ones) -- compute it defensively, but
        # never let it block a global candidate.
        spacing_info = (
            {
                "trace_spacing_source": "explicit_override",
                "trace_spacing_m": float(trace_spacing_m),
                "per_channel_trace_spacing_median": None,
                "trace_spacing_mean": None,
                "trace_spacing_std": None,
                "trace_spacing_cv": None,
                "number_of_valid_intervals": None,
                "warnings": [],
            }
            if trace_spacing_m is not None
            else compute_trace_spacing(dataset)
        )

    if valid_mask is not None:
        if valid_mask.shape != (channels_count, samples_count):
            raise ProcessingError(
                f"valid_mask shape {valid_mask.shape} does not match "
                f"(channels, samples)={(channels_count, samples_count)}"
            )
        full_valid_mask = np.asarray(valid_mask, dtype=bool)
    else:
        full_valid_mask = np.ones((channels_count, samples_count), dtype=bool)

    input_amplitudes = dataset.amplitudes  # read-only view; never written to
    output_f64 = input_amplitudes.astype(np.float64).copy()
    removed_f64 = np.zeros((slices_count, channels_count, samples_count), dtype=np.float64)
    pad_mode = _NUMPY_PAD_MODE[edge_mode] if not is_global else None

    per_channel_valid_count: dict[str, int] = {}
    for channel in range(channels_count):
        valid_samples = full_valid_mask[channel]
        per_channel_valid_count[str(channel)] = int(valid_samples.sum())
        if not valid_samples.any():
            continue
        column = input_amplitudes[:, channel, valid_samples].astype(np.float64)  # (slices, n_valid)
        if is_global:
            background = _global_background(column, method)  # (n_valid,)
            output_f64[:, channel, valid_samples] = column - background[np.newaxis, :]
            removed_f64[:, channel, valid_samples] = np.broadcast_to(background[np.newaxis, :], column.shape)
        else:
            assert applied_window_traces is not None and pad_mode is not None
            background = _sliding_background(column, applied_window_traces, method, pad_mode)
            output_f64[:, channel, valid_samples] = column - background
            removed_f64[:, channel, valid_samples] = background
    # Sample positions where a channel has zero valid traces (fully padded)
    # are left exactly as copied from input_amplitudes above -- never
    # written to, so padding (typically time-zero's fill_value) is
    # preserved byte-for-byte, the same padding-safety contract used by
    # dewow.py/bandpass.py. Because this project's valid_mask is constant
    # across slices within a channel (a time-zero shift is channel-wide,
    # never per-trace -- see CLAUDE.md), a sample position is either valid
    # for every trace or for none, so "insufficient valid traces at one
    # sample position" cannot occur here as a partial case.

    if not np.isfinite(output_f64).all():
        raise ProcessingError("background removal produced NaN/Inf output")

    output_amplitudes = output_f64.astype(input_amplitudes.dtype)
    removed_component = removed_f64.astype(input_amplitudes.dtype)

    valid_broadcast = np.broadcast_to(full_valid_mask[np.newaxis, :, :], output_f64.shape)
    valid_values_after = output_f64[valid_broadcast]
    padding_values_after = output_f64[~valid_broadcast]

    diagnostics: dict[str, Any] = {
        "method": method,
        "edge_mode": edge_mode if not is_global else "not_applicable",
        "valid_mask_provided": valid_mask is not None,
        "per_channel_valid_sample_count": per_channel_valid_count,
        "requested_window_m": requested_window_m,
        "requested_window_traces": (int(window_traces) if window_traces is not None else None),
        "raw_window_traces_float": raw_window_traces_float,
        "applied_window_traces": applied_window_traces if not is_global else None,
        "applied_window_m": applied_window_m,
        "applied_window_m_deprecated_note": (
            "'applied_window_m' is ambiguous and kept only for backward compatibility -- it is "
            "numerically identical to 'applied_window_nominal_length_m' (trace count * trace "
            "spacing), which is NOT the window's physical center-to-center span. Use "
            "'applied_window_nominal_length_m'/'applied_window_center_to_center_span_m'/"
            "'window_half_span_m' explicitly instead; do not present 'applied_window_m' as a "
            "physical span in new human-decision reports (see ADR-008, Sprint 4A.1)."
        ),
        "applied_window_nominal_length_m": applied_window_nominal_length_m,
        "applied_window_center_to_center_span_m": applied_window_center_to_center_span_m,
        "window_half_span_m": window_half_span_m,
        "rounding_policy": rounding_policy if rounding_policy is not None else "not_applicable",
        "trace_spacing": spacing_info,
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
        "output_valid_only_mean": float(valid_values_after.mean()) if valid_values_after.size else None,
        "output_padding_only_mean": (
            float(padding_values_after.mean()) if padding_values_after.size else None
        ),
    }

    warnings: list[str] = []
    if spacing_info is not None:
        warnings.extend(spacing_info["warnings"])
    if (
        not is_global
        and raw_window_traces_float is not None
        and applied_window_traces is not None
        and int(round(raw_window_traces_float)) != applied_window_traces
    ):
        warnings.append(
            f"requested window rounds to {int(round(raw_window_traces_float))} traces, which is "
            f"even; applied window was bumped up to {applied_window_traces} traces to keep it "
            "centered"
        )
    if method in ("global_median", "sliding_median"):
        warnings.append(
            "median is a nonlinear background estimator -- it is not assumed superior to the "
            "mean variant on this dataset; both are reported as QC candidates only, not a "
            "canonical choice"
        )

    record = build_processing_record(
        _OPERATION_NAME,
        parameters={
            "method": method,
            "edge_mode": edge_mode,
            "window_traces": window_traces,
            "window_m": window_m,
            "trace_spacing_m": trace_spacing_m,
            "valid_mask_provided": valid_mask is not None,
            "allow_reprocessing": allow_reprocessing,
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
