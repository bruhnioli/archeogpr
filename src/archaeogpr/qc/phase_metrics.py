"""Phase/waveform-preservation QC metrics beyond the pass/stop-band lag check.

Sprint 3's zero-phase verification (see ADR-006) already proves the
*median-trace* cross-correlation lag is exactly 0. Sprint 3.1 asks a
narrower, complementary question: does a band-pass candidate preserve
phase/waveform shape on *individual* late-time (post-direct-wave) events,
not only on the dominant direct-wave pulse? Everything here is read-only
QC on a pair of already-windowed ``(slices, window_samples)`` arrays
(typically "before band-pass" vs "after band-pass", both derived from the
same D2 dewow output) -- no new filtering algorithm.
"""

from __future__ import annotations

import numpy as np


def main_peak_sample_difference(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Per-trace ``argmax(|after|) - argmax(|before|)``, in samples. Shape ``(slices,)``."""
    before_peak = np.argmax(np.abs(before.astype(np.float64)), axis=1)
    after_peak = np.argmax(np.abs(after.astype(np.float64)), axis=1)
    return after_peak.astype(np.int64) - before_peak.astype(np.int64)


def _nearest_zero_crossing(trace: np.ndarray, near_sample: int) -> int:
    """Index of the sign change nearest ``near_sample``; falls back to ``near_sample`` if none exists."""
    signs = np.sign(trace)
    signs[signs == 0] = 1.0
    crossings = np.flatnonzero(np.diff(signs) != 0)
    if crossings.size == 0:
        return near_sample
    return int(crossings[np.argmin(np.abs(crossings - near_sample))])


def zero_crossing_sample_difference(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Per-trace shift (samples) of the zero crossing nearest ``before``'s own main peak.

    Both ``before`` and ``after``'s nearest zero crossing are located
    relative to ``before``'s own peak sample, so the comparison isolates
    whether band-pass filtering moved the crossing -- not a coincidental
    difference from each array picking its own, possibly different, peak.
    """
    before_f64 = before.astype(np.float64)
    after_f64 = after.astype(np.float64)
    before_peaks = np.argmax(np.abs(before_f64), axis=1)
    diffs = np.zeros(before_f64.shape[0], dtype=np.int64)
    for i in range(before_f64.shape[0]):
        before_zc = _nearest_zero_crossing(before_f64[i], int(before_peaks[i]))
        after_zc = _nearest_zero_crossing(after_f64[i], int(before_peaks[i]))
        diffs[i] = after_zc - before_zc
    return diffs


def local_waveform_correlation(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Per-trace Pearson correlation of ``before`` vs ``after`` within the window. Shape ``(slices,)``."""
    before_f64 = before.astype(np.float64)
    after_f64 = after.astype(np.float64)
    correlations = np.full(before_f64.shape[0], np.nan)
    for i in range(before_f64.shape[0]):
        a, b = before_f64[i], after_f64[i]
        if a.std() > 0 and b.std() > 0:
            correlations[i] = np.corrcoef(a, b)[0, 1]
    return correlations


def polarity_preserved(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Per-trace bool: does the sign of the dominant sample match before vs after?"""
    before_f64 = before.astype(np.float64)
    after_f64 = after.astype(np.float64)
    n = before_f64.shape[0]
    before_peaks = np.argmax(np.abs(before_f64), axis=1)
    after_peaks = np.argmax(np.abs(after_f64), axis=1)
    before_sign = np.sign(before_f64[np.arange(n), before_peaks])
    after_sign = np.sign(after_f64[np.arange(n), after_peaks])
    return before_sign == after_sign


def median_trace_lag(before: np.ndarray, after: np.ndarray, max_lag: int = 64) -> dict[str, float]:
    """Robust systematic-shift check: cross-correlation lag between the two MEDIAN traces.

    Individual per-trace peak-sample differences (see
    :func:`main_peak_sample_difference`) scatter around 0 even under a truly
    zero-phase operation, whenever two nearby samples have similar amplitude
    and noise flips which one is technically the argmax (this is exactly why
    Sprint 3's own band-pass zero-phase verification -- ADR-006 -- treats
    per-trace scatter as expected and uses the median-trace lag as the robust
    signal instead). This function applies that same, already-established
    methodology to a dewow (or any other) before/after pair.

    Caveat (Sprint 3.1 finding): this metric assumes ``before``/``after``
    share broadly similar spectral content over the window given -- true
    when comparing a single filter's own input/output over a segment
    dominated by one strong, shared event (e.g. the direct wave; see
    ``processing/bandpass.py``'s own full-segment diagnostics, which remain
    the authoritative zero-phase proof). When restricted to a weak,
    multi-event, post-direct-wave window where a narrow-band filter has
    substantially reshaped the spectrum (little shared low-frequency
    content left to anchor a cross-correlation), this function can report a
    large apparent "lag" that reflects spectral dissimilarity, not a real
    time shift -- always cross-check against the full-segment lag before
    concluding a real phase problem exists.
    """
    median_before = np.median(before.astype(np.float64), axis=0)
    median_after = np.median(after.astype(np.float64), axis=0)
    peak_sample_diff = int(np.argmax(np.abs(median_after)) - np.argmax(np.abs(median_before)))

    a = median_before - median_before.mean()
    b = median_after - median_after.mean()
    n = a.shape[0]
    effective_max_lag = min(max_lag, n - 1)
    correlation = np.correlate(b, a, mode="full")
    center = n - 1
    window = correlation[center - effective_max_lag : center + effective_max_lag + 1]
    lag = int(np.argmax(window)) - effective_max_lag

    return {"median_trace_peak_sample_diff": peak_sample_diff, "median_trace_cross_correlation_lag": lag}


def compute_phase_waveform_metrics(before: np.ndarray, after: np.ndarray) -> dict[str, float]:
    """Combined summary dict: peak-sample diff, zero-crossing diff, waveform correlation, polarity.

    ``before``/``after`` must share shape ``(slices, window_samples)``.
    Correlation is reported as a distribution (min/p5/median/p95/max) per
    the Sprint 3.1 request for a "local event correlation distribution"
    across the window, not just a single aggregate number.
    """
    peak_diff = main_peak_sample_difference(before, after)
    zc_diff = zero_crossing_sample_difference(before, after)
    correlation = local_waveform_correlation(before, after)
    polarity = polarity_preserved(before, after)
    finite_correlation = correlation[np.isfinite(correlation)]
    median_lag = median_trace_lag(before, after)

    return {
        **median_lag,
        "peak_sample_diff_mean": float(peak_diff.mean()),
        "peak_sample_diff_median": float(np.median(peak_diff)),
        "peak_sample_diff_max_abs": int(np.max(np.abs(peak_diff))) if peak_diff.size else 0,
        "zero_crossing_diff_mean": float(zc_diff.mean()),
        "zero_crossing_diff_median": float(np.median(zc_diff)),
        "zero_crossing_diff_max_abs": int(np.max(np.abs(zc_diff))) if zc_diff.size else 0,
        "waveform_correlation_min": (
            float(finite_correlation.min()) if finite_correlation.size else float("nan")
        ),
        "waveform_correlation_p5": (
            float(np.percentile(finite_correlation, 5)) if finite_correlation.size else float("nan")
        ),
        "waveform_correlation_median": (
            float(np.median(finite_correlation)) if finite_correlation.size else float("nan")
        ),
        "waveform_correlation_p95": (
            float(np.percentile(finite_correlation, 95)) if finite_correlation.size else float("nan")
        ),
        "waveform_correlation_max": (
            float(finite_correlation.max()) if finite_correlation.size else float("nan")
        ),
        "polarity_preserved_fraction": float(polarity.mean()) if polarity.size else float("nan"),
    }
