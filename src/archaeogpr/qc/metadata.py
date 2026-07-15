"""Pure functions that derive QC metadata from a :class:`GPRDataset`.

None of these functions modify their inputs. Depth/elevation figures are
always derived from the file's *metadata* propagation velocity — that
assumption is never validated against ground truth, and every function that
depends on it says so via ``derive_metadata()['warnings']`` /
``['depth_estimate']['basis']`` when velocity metadata is unavailable.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from archaeogpr.model.dataset import GPRDataset


def compute_time_window_ns(samples_count: int, sampling_time_ns: float) -> float:
    """Total two-way time window covered by one trace: samples * sampling interval."""
    return float(samples_count) * float(sampling_time_ns)


def compute_depth_per_sample_m(velocity_m_per_ns: float, sampling_time_ns: float) -> float:
    """One-way depth per sample given a metadata propagation velocity assumption."""
    return float(velocity_m_per_ns) * float(sampling_time_ns) / 2.0


def compute_max_depth_m(velocity_m_per_ns: float, sampling_time_ns: float, samples_count: int) -> float:
    """One-way depth reached by the last sample, under the same velocity assumption."""
    return compute_depth_per_sample_m(velocity_m_per_ns, sampling_time_ns) * samples_count


def compute_slice_centers(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Per-slice (x, y) center, averaged across channels. Shape (slices, 2)."""
    return np.stack([np.mean(x, axis=1), np.mean(y, axis=1)], axis=1)


def compute_profile_length_m(x: np.ndarray | None, y: np.ndarray | None) -> float | None:
    """Along-track length of the survey line, summing consecutive slice-center distances."""
    if x is None or y is None:
        return None
    centers = compute_slice_centers(x, y)
    if centers.shape[0] < 2:
        return 0.0
    deltas = np.diff(centers, axis=0)
    return float(np.sum(np.hypot(deltas[:, 0], deltas[:, 1])))


def compute_along_track_spacing_m(x: np.ndarray | None, y: np.ndarray | None) -> float | None:
    """Median distance between consecutive slice centers."""
    if x is None or y is None:
        return None
    centers = compute_slice_centers(x, y)
    if centers.shape[0] < 2:
        return None
    deltas = np.diff(centers, axis=0)
    return float(np.median(np.hypot(deltas[:, 0], deltas[:, 1])))


def compute_cross_channel_spacing_m(x: np.ndarray | None, y: np.ndarray | None) -> float | None:
    """Median distance between adjacent channels within a slice, over all slices."""
    if x is None or y is None or x.shape[1] < 2:
        return None
    dx = np.diff(x, axis=1)
    dy = np.diff(y, axis=1)
    return float(np.median(np.hypot(dx, dy)))


def compute_swath_width_m(x: np.ndarray | None, y: np.ndarray | None) -> float | None:
    """Median distance between the first and last channel, over all slices."""
    if x is None or y is None or x.shape[1] < 2:
        return None
    dx = x[:, -1] - x[:, 0]
    dy = y[:, -1] - y[:, 0]
    return float(np.median(np.hypot(dx, dy)))


def compute_amplitude_statistics(amplitudes: np.ndarray) -> dict[str, float]:
    """min/max/mean/std and the 1st/50th/99th percentiles over all amplitude samples."""
    flat = amplitudes.reshape(-1)
    p1, p50, p99 = np.percentile(flat, [1, 50, 99])
    return {
        "min": float(flat.min()),
        "max": float(flat.max()),
        "mean": float(flat.mean()),
        "std": float(flat.std()),
        "p1": float(p1),
        "p50": float(p50),
        "p99": float(p99),
    }


def compute_geometry_statistics(dataset: GPRDataset) -> dict[str, Any]:
    """Profile/spacing/extent statistics; all None if the dataset has no geolocation."""
    x, y = dataset.x, dataset.y
    stats: dict[str, Any] = {
        "profile_length_m": compute_profile_length_m(x, y),
        "along_track_spacing_m": compute_along_track_spacing_m(x, y),
        "cross_channel_spacing_m": compute_cross_channel_spacing_m(x, y),
        "swath_width_m": compute_swath_width_m(x, y),
        "x_min": float(np.min(x)) if x is not None else None,
        "x_max": float(np.max(x)) if x is not None else None,
        "y_min": float(np.min(y)) if y is not None else None,
        "y_max": float(np.max(y)) if y is not None else None,
        "elevation_min_m": None,
        "elevation_max_m": None,
    }
    elevation_arrays = [a for a in (dataset.elevation_top_m, dataset.elevation_bottom_m) if a is not None]
    if elevation_arrays:
        stats["elevation_min_m"] = float(min(np.min(a) for a in elevation_arrays))
        stats["elevation_max_m"] = float(max(np.max(a) for a in elevation_arrays))
    return stats


def derive_metadata(dataset: GPRDataset) -> dict[str, Any]:
    """Combine every derived QC figure into one JSON-serializable dict.

    This does not modify ``dataset`` or its metadata; callers merge the
    result into an export (see ``archaeogpr.export.basic``) as needed.
    """
    _, _, samples_count = dataset.shape
    sampling = dataset.metadata.get("sampling") or {}
    radar = dataset.metadata.get("radar") or {}
    sampling_time_ns = sampling.get("sampling_time_ns")
    velocity_m_per_ns = radar.get("propagation_velocity_m_per_ns")

    warnings_list: list[str] = []

    time_window_ns = (
        compute_time_window_ns(samples_count, sampling_time_ns) if sampling_time_ns is not None else None
    )

    depth_per_sample_m = None
    max_depth_m = None
    basis = None
    if velocity_m_per_ns is not None and sampling_time_ns is not None:
        depth_per_sample_m = compute_depth_per_sample_m(velocity_m_per_ns, sampling_time_ns)
        max_depth_m = compute_max_depth_m(velocity_m_per_ns, sampling_time_ns, samples_count)
        basis = (
            f"Derived from the file's metadata propagation velocity assumption "
            f"({velocity_m_per_ns:.6g} m/ns); not ground-truthed against a known target."
        )
    else:
        warnings_list.append(
            "Depth/elevation figures could not be estimated: propagation velocity metadata is missing."
        )

    return {
        "time_window_ns": time_window_ns,
        "depth_estimate": {
            "depth_per_sample_m": depth_per_sample_m,
            "max_depth_m": max_depth_m,
            "basis": basis,
        },
        "geometry": compute_geometry_statistics(dataset),
        "amplitude_statistics": compute_amplitude_statistics(dataset.amplitudes),
        "warnings": warnings_list,
    }
