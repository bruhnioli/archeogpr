"""Spatial-continuity QC metrics for a windowed (slices, samples) array.

Sprint 3.1: pure, read-only analysis functions used to judge whether a
band's retained/removed energy behaves like a spatially continuous
reflection (adjacent traces agree) or incoherent noise (adjacent traces
don't) -- a QC signal only, never an automatic archaeological/anomaly
interpretation (see CLAUDE.md).

Nothing here mutates its input; every function takes a plain ``(slices,
window_samples)`` array (already time-windowed and, where relevant,
restricted to valid/non-padding samples by the caller) and returns plain
numpy arrays or a dict of scalar summary statistics.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def adjacent_trace_correlation(windowed_amplitudes: np.ndarray) -> np.ndarray:
    """Pearson correlation between trace ``i`` and trace ``i+1``, for every ``i``.

    ``windowed_amplitudes`` has shape ``(slices, window_samples)``. Returns
    shape ``(slices - 1,)``; a pair where either trace is exactly constant
    (zero variance -- e.g. an all-padding row) yields ``nan`` rather than a
    divide-by-zero warning.
    """
    data = windowed_amplitudes.astype(np.float64)
    slices_count = data.shape[0]
    correlations = np.full(max(slices_count - 1, 0), np.nan)
    for i in range(slices_count - 1):
        a, b = data[i], data[i + 1]
        if a.std() > 0 and b.std() > 0:
            correlations[i] = np.corrcoef(a, b)[0, 1]
    return correlations


def local_rms_amplitude(windowed_amplitudes: np.ndarray) -> np.ndarray:
    """Per-trace RMS amplitude within the window. Shape ``(slices,)``."""
    data = windowed_amplitudes.astype(np.float64)
    return np.sqrt((data**2).mean(axis=1))


def trace_to_trace_difference_energy(windowed_amplitudes: np.ndarray) -> np.ndarray:
    """Sum of squared difference between adjacent traces. Shape ``(slices - 1,)``."""
    data = windowed_amplitudes.astype(np.float64)
    return (np.diff(data, axis=0) ** 2).sum(axis=1)


def compute_spatial_coherence_metrics(windowed_amplitudes: np.ndarray) -> dict[str, float]:
    """Summary dict combining every per-array spatial-coherence metric above.

    QC-only: a high ``adjacent_trace_correlation`` suggests the array's
    content is spatially continuous (consistent with a real reflection);
    a value near zero suggests incoherent, trace-independent content
    (consistent with noise). This function draws no such conclusion
    itself -- it only reports the numbers.
    """
    correlations = adjacent_trace_correlation(windowed_amplitudes)
    rms = local_rms_amplitude(windowed_amplitudes)
    diff_energy = trace_to_trace_difference_energy(windowed_amplitudes)
    finite_correlations = correlations[np.isfinite(correlations)]
    return {
        "adjacent_trace_correlation_median": (
            float(np.median(finite_correlations)) if finite_correlations.size else float("nan")
        ),
        "adjacent_trace_correlation_mean": (
            float(finite_correlations.mean()) if finite_correlations.size else float("nan")
        ),
        "adjacent_trace_correlation_min": (
            float(finite_correlations.min()) if finite_correlations.size else float("nan")
        ),
        "adjacent_trace_correlation_max": (
            float(finite_correlations.max()) if finite_correlations.size else float("nan")
        ),
        "local_rms_mean": float(rms.mean()),
        "local_rms_std": float(rms.std()),
        "trace_to_trace_difference_energy_mean": float(diff_energy.mean()),
        "trace_to_trace_difference_energy_std": float(diff_energy.std()),
    }


def channel_to_channel_consistency(per_channel_metrics: dict[int, dict[str, float]]) -> dict[str, float]:
    """Spread of ``adjacent_trace_correlation_median`` across a set of channels.

    ``per_channel_metrics`` maps channel index to that channel's own
    :func:`compute_spatial_coherence_metrics` output. A small
    ``correlation_median_std`` means the channels agree with each other
    (consistent spatial behavior); a large one means they don't.
    """
    values = np.array(
        [m["adjacent_trace_correlation_median"] for m in per_channel_metrics.values()], dtype=np.float64
    )
    finite = values[np.isfinite(values)]
    return {
        "correlation_median_across_channels_mean": float(finite.mean()) if finite.size else float("nan"),
        "correlation_median_across_channels_std": float(finite.std()) if finite.size else float("nan"),
        "correlation_median_across_channels_min": float(finite.min()) if finite.size else float("nan"),
        "correlation_median_across_channels_max": float(finite.max()) if finite.size else float("nan"),
    }


def removed_component_spatial_coherence(removed_component_windowed: np.ndarray) -> dict[str, float]:
    """Same metrics as :func:`compute_spatial_coherence_metrics`, applied to a removed component.

    Not a separate algorithm -- this is exactly
    ``compute_spatial_coherence_metrics`` under a name that makes the
    caller's intent (judging the *removed* energy, not the retained output)
    explicit at call sites.
    """
    return compute_spatial_coherence_metrics(removed_component_windowed)


def band_energy_concentration(per_slice_energy: np.ndarray, top_fraction: float = 0.05) -> dict[str, Any]:
    """How concentrated ``per_slice_energy`` (shape ``(slices,)``) is across traces.

    Returns the coefficient of variation (std/mean) and the share of total
    energy held by the top ``top_fraction`` of slices -- a high top-share
    relative to ``top_fraction`` itself indicates the energy is
    concentrated in a few traces rather than spread evenly.
    """
    energy = np.asarray(per_slice_energy, dtype=np.float64)
    total = float(energy.sum())
    mean = float(energy.mean())
    std = float(energy.std())
    top_k = max(1, int(round(top_fraction * energy.size)))
    top_share = float(np.sort(energy)[-top_k:].sum() / total) if total > 0 else float("nan")
    return {
        "coefficient_of_variation": (std / mean) if mean > 0 else float("nan"),
        "top_fraction": top_fraction,
        "top_fraction_slice_count": top_k,
        "top_fraction_energy_share": top_share,
        "even_distribution_share": top_fraction,
    }
