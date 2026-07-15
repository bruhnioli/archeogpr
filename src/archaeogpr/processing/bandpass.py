"""Band-pass filtering: keep a frequency band, reject everything else.

Two independent methods, both intended to be zero-phase (see ADR-006):

* ``"butterworth"`` -- ``scipy.signal.butter(..., output="sos")`` +
  ``scipy.signal.sosfiltfilt`` (two-pass, so the *effective* magnitude
  response is the design's response squared -- standard, expected, and
  documented in diagnostics). ``zero_phase=False`` uses a single
  ``sosfilt`` pass instead, which does introduce a phase delay -- kept only
  so the zero-phase property can be demonstrated by contrast in tests.
* ``"ormsby"`` -- a real, symmetric trapezoidal transfer function applied
  by direct FFT multiply; a real transfer function is zero-phase by
  construction, so there is no ``zero_phase`` toggle for this method.

Both operate per (slice, channel) trace, independently within each
contiguous run of valid (non-padding) samples -- exactly like
``processing/dewow.py``. Padding is never read and never written; see
CLAUDE.md and ADR-006.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
from scipy.signal import butter, sosfilt, sosfiltfilt

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.common import ProcessingError, build_processing_record, contiguous_true_runs
from archaeogpr.processing.result import ProcessingResult

_METHODS = ("butterworth", "ormsby")
_OPERATION_NAME = "bandpass_correction"

#: Ormsby's internal reflect-pad, sized relative to the segment (bounded so
#: it neither vanishes for tiny segments nor balloons for huge ones) --
#: avoids circular convolution wrapping the trapezoid's implicit
#: time-domain ringing around the segment's own edges.
_ORMSBY_MIN_PAD = 32
_ORMSBY_MAX_PAD = 512

#: Butterworth's own internal edge extension passed explicitly to
#: sosfiltfilt (rather than relying on scipy's own default, which this
#: project cannot cheaply introspect for diagnostics) -- a conventional,
#: order-proportional choice.
_BUTTERWORTH_PADLEN_PER_ORDER = 3


def _nyquist_mhz(sampling_time_ns: float) -> float:
    sampling_frequency_hz = 1.0 / (sampling_time_ns * 1e-9)
    return sampling_frequency_hz / 2.0 / 1e6


def build_butterworth_sos(
    lowcut_mhz: float, highcut_mhz: float, order: int, sampling_time_ns: float
) -> np.ndarray:
    """Design the SOS bandpass filter used by ``method="butterworth"``."""
    sampling_frequency_hz = 1.0 / (sampling_time_ns * 1e-9)
    return butter(
        order, [lowcut_mhz * 1e6, highcut_mhz * 1e6], btype="bandpass", fs=sampling_frequency_hz, output="sos"
    )


def build_ormsby_transfer_function(
    frequencies_hz: np.ndarray, corners_mhz: tuple[float, float, float, float]
) -> np.ndarray:
    """Real trapezoidal transfer function evaluated at ``frequencies_hz`` (real, so zero-phase)."""
    f1, f2, f3, f4 = (c * 1e6 for c in corners_mhz)
    h = np.zeros_like(frequencies_hz, dtype=np.float64)
    rising = (frequencies_hz >= f1) & (frequencies_hz < f2)
    h[rising] = (frequencies_hz[rising] - f1) / (f2 - f1)
    flat = (frequencies_hz >= f2) & (frequencies_hz <= f3)
    h[flat] = 1.0
    falling = (frequencies_hz > f3) & (frequencies_hz <= f4)
    h[falling] = (f4 - frequencies_hz[falling]) / (f4 - f3)
    return h


def _validate_butterworth(
    lowcut_mhz: float | None, highcut_mhz: float | None, order: int, nyquist_mhz: float
) -> None:
    if lowcut_mhz is None or highcut_mhz is None:
        raise ProcessingError("method='butterworth' requires both lowcut_mhz and highcut_mhz")
    if not (0 < lowcut_mhz < highcut_mhz < nyquist_mhz):
        raise ProcessingError(
            f"butterworth requires 0 < lowcut_mhz < highcut_mhz < nyquist_mhz "
            f"({nyquist_mhz:g} MHz), got lowcut_mhz={lowcut_mhz}, highcut_mhz={highcut_mhz}"
        )
    if order < 1:
        raise ProcessingError(f"order must be >= 1, got {order}")


def _validate_ormsby(
    frequencies_mhz: tuple[float, ...] | None, nyquist_mhz: float
) -> tuple[float, float, float, float]:
    if frequencies_mhz is None or len(frequencies_mhz) != 4:
        raise ProcessingError("method='ormsby' requires frequencies_mhz=(f1, f2, f3, f4)")
    f1, f2, f3, f4 = frequencies_mhz
    if not (0 <= f1 < f2 < f3 < f4 < nyquist_mhz):
        raise ProcessingError(
            f"ormsby requires 0 <= f1 < f2 < f3 < f4 < nyquist_mhz ({nyquist_mhz:g} MHz), "
            f"got frequencies_mhz={frequencies_mhz}"
        )
    return f1, f2, f3, f4


def _apply_butterworth(
    segment: np.ndarray, sos: np.ndarray, order: int, zero_phase: bool
) -> tuple[np.ndarray, int]:
    length = segment.shape[-1]
    padlen = min(_BUTTERWORTH_PADLEN_PER_ORDER * order, length - 1)
    if zero_phase:
        if padlen < 1 or length <= padlen:
            raise ProcessingError(
                f"segment length {length} is too short for zero-phase Butterworth order={order} "
                f"(needs more than {padlen} samples)"
            )
        try:
            filtered = sosfiltfilt(sos, segment, axis=-1, padlen=padlen)
        except ValueError as exc:
            raise ProcessingError(f"sosfiltfilt failed on a segment of length {length}: {exc}") from exc
        return filtered, padlen
    return sosfilt(sos, segment, axis=-1), 0


def _apply_ormsby(
    segment: np.ndarray, corners_mhz: tuple[float, float, float, float], sampling_time_ns: float
) -> tuple[np.ndarray, int]:
    length = segment.shape[-1]
    pad_samples = min(max(length // 4, _ORMSBY_MIN_PAD), _ORMSBY_MAX_PAD, length - 1)
    padded = np.pad(segment, ((0, 0), (pad_samples, pad_samples)), mode="reflect")
    n_padded = padded.shape[-1]
    frequencies_hz = np.fft.rfftfreq(n_padded, d=sampling_time_ns * 1e-9)
    transfer = build_ormsby_transfer_function(frequencies_hz, corners_mhz)
    spectrum = np.fft.rfft(padded, axis=-1)
    filtered_padded = np.fft.irfft(spectrum * transfer[np.newaxis, :], n=n_padded, axis=-1)
    return filtered_padded[:, pad_samples : pad_samples + length], pad_samples


def _peak_shift_and_lag(
    input_segment: np.ndarray, output_segment: np.ndarray, max_lag: int = 32
) -> dict[str, Any]:
    """Per-trace peak-sample shift, plus a median-trace cross-correlation lag."""
    input_peaks = np.argmax(np.abs(input_segment), axis=-1)
    output_peaks = np.argmax(np.abs(output_segment), axis=-1)
    shifts = output_peaks - input_peaks

    median_before = np.median(input_segment, axis=0)
    median_after = np.median(output_segment, axis=0)
    a = median_before - median_before.mean()
    b = median_after - median_after.mean()
    n = a.shape[0]
    effective_max_lag = min(max_lag, n - 1)
    correlation = np.correlate(b, a, mode="full")
    center = n - 1
    window = correlation[center - effective_max_lag : center + effective_max_lag + 1]
    lag = int(np.argmax(window)) - effective_max_lag

    return {
        "peak_sample_shift_min": int(shifts.min()),
        "peak_sample_shift_max": int(shifts.max()),
        "peak_sample_shift_mean": float(shifts.mean()),
        "median_trace_cross_correlation_lag": lag,
    }


def _band_energy_ratio(
    input_segment: np.ndarray,
    output_segment: np.ndarray,
    sampling_time_ns: float,
    band_hz: tuple[float, float],
) -> dict[str, float]:
    """Fraction of each segment's energy inside ``band_hz``, before and after filtering."""
    length = input_segment.shape[-1]
    frequencies_hz = np.fft.rfftfreq(length, d=sampling_time_ns * 1e-9)
    in_band = (frequencies_hz >= band_hz[0]) & (frequencies_hz <= band_hz[1])

    def _band_fraction(segment: np.ndarray) -> float:
        power = np.abs(np.fft.rfft(segment, axis=-1)) ** 2
        total = power.sum()
        return float(power[:, in_band].sum() / total) if total > 0 else 0.0

    return {
        "passband_energy_fraction_before": _band_fraction(input_segment),
        "passband_energy_fraction_after": _band_fraction(output_segment),
    }


def correct_bandpass(
    dataset: GPRDataset,
    *,
    method: str = "butterworth",
    lowcut_mhz: float | None = None,
    highcut_mhz: float | None = None,
    order: int = 4,
    zero_phase: bool = True,
    frequencies_mhz: tuple[float, float, float, float] | None = None,
    valid_mask: np.ndarray | None = None,
    allow_repeat_processing: bool = False,
) -> ProcessingResult:
    """Band-pass filter every trace, independently within each valid segment.

    ``method="butterworth"`` requires ``lowcut_mhz``/``highcut_mhz``
    (``0 < lowcut_mhz < highcut_mhz < Nyquist``) and uses zero-phase
    ``sosfiltfilt`` by default (``zero_phase=False`` for a single causal
    pass instead). ``method="ormsby"`` requires
    ``frequencies_mhz=(f1,f2,f3,f4)`` (``0 <= f1 < f2 < f3 < f4 <
    Nyquist``) and applies a real (hence zero-phase) trapezoidal transfer
    function via FFT, with internal reflect-padding to avoid circular
    convolution. ``dataset`` is never modified; padding is excluded from
    the filter and left byte-for-byte unchanged. Raises ``ProcessingError``
    for invalid parameters, a segment too short to filter, a
    `bandpass_correction` already in ``dataset.processing_history`` (unless
    ``allow_repeat_processing=True``), or NaN/Inf in the result.
    """
    if method not in _METHODS:
        raise ProcessingError(f"method must be one of {_METHODS}, got {method!r}")

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
        raise ProcessingError(
            "dataset.metadata['sampling']['sampling_time_ns'] is required for bandpass filtering"
        )
    nyquist_mhz = _nyquist_mhz(sampling_time_ns)

    sos = None
    ormsby_corners: tuple[float, float, float, float] | None = None
    if method == "butterworth":
        if frequencies_mhz is not None:
            raise ProcessingError("frequencies_mhz is only used for method='ormsby'")
        _validate_butterworth(lowcut_mhz, highcut_mhz, order, nyquist_mhz)
        assert lowcut_mhz is not None and highcut_mhz is not None
        sos = build_butterworth_sos(lowcut_mhz, highcut_mhz, order, sampling_time_ns)
    else:
        if lowcut_mhz is not None or highcut_mhz is not None:
            raise ProcessingError("lowcut_mhz/highcut_mhz are only used for method='butterworth'")
        ormsby_corners = _validate_ormsby(frequencies_mhz, nyquist_mhz)

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

    segment_lengths: list[int] = []
    internal_padding_by_channel: dict[str, list[int]] = {}
    peak_shift_stats_by_channel: dict[str, Any] = {}
    energy_by_channel: dict[str, Any] = {}
    for channel in range(channels_count):
        runs = contiguous_true_runs(full_valid_mask[channel])
        internal_padding_by_channel[str(channel)] = []
        for start, end in runs:
            length = end - start
            segment_lengths.append(length)
            segment = input_amplitudes[:, channel, start:end].astype(np.float64)

            if method == "butterworth":
                assert sos is not None
                filtered, internal_padding = _apply_butterworth(segment, sos, order, zero_phase)
            else:
                assert ormsby_corners is not None
                filtered, internal_padding = _apply_ormsby(segment, ormsby_corners, sampling_time_ns)

            output_f64[:, channel, start:end] = filtered
            removed_f64[:, channel, start:end] = segment - filtered
            internal_padding_by_channel[str(channel)].append(internal_padding)
            peak_shift_stats_by_channel[f"{channel}:{start}-{end}"] = _peak_shift_and_lag(segment, filtered)
            if method == "butterworth":
                assert lowcut_mhz is not None and highcut_mhz is not None
                band_hz = (lowcut_mhz * 1e6, highcut_mhz * 1e6)
            else:
                assert ormsby_corners is not None
                band_hz = (ormsby_corners[1] * 1e6, ormsby_corners[2] * 1e6)
            energy_by_channel[f"{channel}:{start}-{end}"] = _band_energy_ratio(
                segment, filtered, sampling_time_ns, band_hz
            )
    # Positions outside every valid run are left exactly as copied from
    # input_amplitudes above -- never written to, so padding is preserved
    # byte-for-byte.

    if not np.isfinite(output_f64).all():
        raise ProcessingError("bandpass filtering produced NaN/Inf output")
    output_amplitudes = output_f64.astype(input_amplitudes.dtype)
    removed_component = removed_f64.astype(input_amplitudes.dtype)

    trace_mean_before = input_amplitudes.astype(np.float64).mean(axis=2)
    trace_mean_after = output_amplitudes.astype(np.float64).mean(axis=2)

    diagnostics: dict[str, Any] = {
        "method": method,
        "sampling_time_ns": sampling_time_ns,
        "sampling_frequency_mhz": nyquist_mhz * 2,
        "nyquist_mhz": nyquist_mhz,
        "valid_mask_provided": valid_mask is not None,
        "valid_segment_min_length": int(min(segment_lengths)) if segment_lengths else None,
        "valid_segment_max_length": int(max(segment_lengths)) if segment_lengths else None,
        "internal_padding_samples_per_channel": internal_padding_by_channel,
        "peak_shift_and_lag_per_segment": peak_shift_stats_by_channel,
        "band_energy_fraction_per_segment": energy_by_channel,
        "input_statistics": {
            "min": float(input_amplitudes.astype(np.float64).min()),
            "max": float(input_amplitudes.astype(np.float64).max()),
            "mean": float(input_amplitudes.astype(np.float64).mean()),
        },
        "output_statistics": {
            "min": float(output_f64.min()),
            "max": float(output_f64.max()),
            "mean": float(output_f64.mean()),
        },
        "removed_component_statistics": {
            "min": float(removed_f64.min()),
            "max": float(removed_f64.max()),
            "mean": float(removed_f64.mean()),
        },
        "trace_mean_before": {"min": float(trace_mean_before.min()), "max": float(trace_mean_before.max())},
        "trace_mean_after": {"min": float(trace_mean_after.min()), "max": float(trace_mean_after.max())},
    }
    if method == "butterworth":
        diagnostics.update(
            {"lowcut_mhz": lowcut_mhz, "highcut_mhz": highcut_mhz, "order": order, "zero_phase": zero_phase}
        )
    else:
        assert ormsby_corners is not None
        diagnostics.update(
            {
                "frequencies_mhz": list(ormsby_corners),
                "zero_phase": True,
            }
        )

    warnings: list[str] = []
    if method == "butterworth" and not zero_phase:
        warnings.append(
            "zero_phase=False uses a single causal sosfilt pass -- this introduces a real phase "
            "delay/lag, unlike the zero_phase=True (sosfiltfilt) default"
        )

    parameters: dict[str, Any] = {"method": method, "valid_mask_provided": valid_mask is not None}
    if method == "butterworth":
        parameters.update(
            {"lowcut_mhz": lowcut_mhz, "highcut_mhz": highcut_mhz, "order": order, "zero_phase": zero_phase}
        )
    else:
        assert ormsby_corners is not None
        parameters["frequencies_mhz"] = list(ormsby_corners)

    record = build_processing_record(
        _OPERATION_NAME, parameters=parameters, diagnostics=diagnostics, warnings=tuple(warnings)
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
