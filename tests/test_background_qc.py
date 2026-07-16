"""Tests for archaeogpr.qc.background (Sprint 4A QC metrics and plotting).

Covers: signal-preservation metrics structure/correctness, removed-component
metrics structure/correctness (including band-energy integration and the
QC-only localized-event-risk proxy distinguishing flat/coherent removed
components from curved/local ones), and that every QC plotting function
produces non-empty, openable files.
"""

from __future__ import annotations

import matplotlib.image as mpimg
import numpy as np

from archaeogpr.processing.background import remove_background
from archaeogpr.qc.background import (
    TIME_WINDOWS_NS,
    compute_localized_event_risk,
    compute_removed_component_metrics,
    compute_signal_preservation_metrics,
    save_background_qc_suite,
    save_before_after_removed_panel,
    save_removed_component_spectrum,
)

SAMPLING_TIME_NS = 0.125


def _profile_with_common_background(dataset_factory, *, slices_count=40, samples_count=850, seed=0):
    rng = np.random.default_rng(seed)
    background = 300.0 * np.sin(np.linspace(0.0, 4 * np.pi, samples_count))
    amplitudes = (
        np.tile(background, (slices_count, 1)) + rng.normal(0.0, 15.0, size=(slices_count, samples_count))
    ).astype(np.float32)
    full = np.stack([amplitudes for _ in range(11)], axis=1)  # 11 channels, matching real dataset shape
    return dataset_factory(
        amplitudes=full,
        slices_count=slices_count,
        channels_count=11,
        samples_count=samples_count,
        sampling_time_ns=SAMPLING_TIME_NS,
    )


def test_signal_preservation_metrics_cover_every_time_window(dataset_factory):
    ds = _profile_with_common_background(dataset_factory)
    valid_mask = np.ones((ds.shape[1], ds.shape[2]), dtype=bool)
    result = remove_background(ds, method="global_mean", valid_mask=valid_mask)
    metrics = compute_signal_preservation_metrics(ds, result, valid_mask, channels=(0, 5, 10))
    assert set(metrics.keys()) == {label for label, _s, _e in TIME_WINDOWS_NS}
    for window_metrics in metrics.values():
        for key in (
            "median_trace_cross_correlation_lag",
            "rms_retention",
            "absolute_energy_retention",
            "spectral_energy_retention",
            "adjacent_trace_correlation_before",
            "adjacent_trace_correlation_after",
            # Sprint 4A spec section 16: median-trace correlation, local-event
            # amplitude retention, and channel consistency before/after.
            "median_trace_correlation",
            "local_event_amplitude_retention",
            "channel_consistency_before_correlation_median_across_channels_mean",
            "channel_consistency_after_correlation_median_across_channels_mean",
        ):
            assert key in window_metrics


def test_signal_preservation_rms_retention_below_one_after_removing_dominant_background(dataset_factory):
    # The common background dominates the signal's own RMS by construction
    # (amplitude 300 vs noise std 15); removing it must measurably reduce
    # RMS relative to the original in every window.
    ds = _profile_with_common_background(dataset_factory)
    valid_mask = np.ones((ds.shape[1], ds.shape[2]), dtype=bool)
    result = remove_background(ds, method="global_mean", valid_mask=valid_mask)
    metrics = compute_signal_preservation_metrics(ds, result, valid_mask, channels=(0, 5, 10))
    for window_metrics in metrics.values():
        assert window_metrics["rms_retention"] < 1.0


def test_removed_component_metrics_structure_and_band_energy(dataset_factory):
    ds = _profile_with_common_background(dataset_factory)
    valid_mask = np.ones((ds.shape[1], ds.shape[2]), dtype=bool)
    result = remove_background(ds, method="global_mean", valid_mask=valid_mask)
    metrics = compute_removed_component_metrics(ds, result, valid_mask, channels=(0, 5, 10))
    assert set(metrics.keys()) == {label for label, _s, _e in TIME_WINDOWS_NS}
    for window_metrics in metrics.values():
        assert "removed_input_rms_ratio" in window_metrics
        assert "removed_input_energy_ratio" in window_metrics
        # Sprint 4A spec section 15.1/15.2: absolute-energy ratio (distinct
        # from the squared-energy ratio above) and spatial concentration.
        assert "removed_input_absolute_energy_ratio" in window_metrics
        assert "spatial_concentration_coefficient_of_variation" in window_metrics
        assert "spatial_concentration_top_fraction_energy_share" in window_metrics
        assert "adjacent_trace_correlation_median" in window_metrics
        assert "band_energy_mhz" in window_metrics
        assert isinstance(window_metrics["band_energy_mhz"], dict)
        assert all(v >= 0.0 for v in window_metrics["band_energy_mhz"].values())


def test_removed_component_coherence_high_for_shared_background(dataset_factory):
    # A global_mean's removed component is (by construction) the SAME
    # profile-wide curve broadcast to every trace -- adjacent traces must
    # therefore be highly correlated (a coherent, non-noise-like removed
    # component).
    ds = _profile_with_common_background(dataset_factory)
    valid_mask = np.ones((ds.shape[1], ds.shape[2]), dtype=bool)
    result = remove_background(ds, method="global_mean", valid_mask=valid_mask)
    metrics = compute_removed_component_metrics(ds, result, valid_mask, channels=(0, 5, 10))
    assert metrics["W5"]["adjacent_trace_correlation_median"] > 0.9


def test_localized_event_risk_low_for_flat_background(dataset_factory):
    slices_count, samples_count = 30, 50
    flat = np.tile(100.0 * np.sin(np.linspace(0, 2 * np.pi, samples_count)), (slices_count, 1))
    flat_risk = compute_localized_event_risk(flat)
    assert flat_risk["horizontal_gradient_energy"] < 1.0
    assert flat_risk["local_curvature_energy"] < 1.0


def test_localized_event_risk_higher_for_a_curved_local_event(dataset_factory):
    slices_count, samples_count = 30, 50
    curved = np.zeros((slices_count, samples_count))
    for i in range(slices_count):
        depth = 20 + int(0.05 * (i - 15) ** 2)
        if depth < samples_count:
            curved[i, depth] = 500.0
    curved_risk = compute_localized_event_risk(curved)
    flat = np.tile(100.0 * np.sin(np.linspace(0, 2 * np.pi, samples_count)), (slices_count, 1))
    flat_risk = compute_localized_event_risk(flat)
    assert curved_risk["horizontal_gradient_energy"] > flat_risk["horizontal_gradient_energy"]
    assert curved_risk["local_curvature_energy"] > flat_risk["local_curvature_energy"]


def test_localized_event_risk_handles_degenerate_shapes():
    tiny = np.zeros((1, 1))
    risk = compute_localized_event_risk(tiny)
    assert all(not np.isfinite(v) for v in risk.values())


def test_save_background_qc_suite_produces_all_required_non_empty_files(dataset_factory, tmp_path):
    ds = _profile_with_common_background(dataset_factory, slices_count=25)
    valid_mask = np.ones((ds.shape[1], ds.shape[2]), dtype=bool)
    result = remove_background(ds, method="sliding_mean", window_traces=5, valid_mask=valid_mask)
    paths = save_background_qc_suite(ds, result, tmp_path, secondary_channels=(5, 10))

    expected_keys = {
        "channel_before",
        "channel_after",
        "channel_difference",
        "channel_removed",
        "channel05_before_after_removed",
        "channel10_before_after_removed",
        "all_channels_after",
        "median_trace_before_after",
        "removed_component_median_trace",
        "removed_component_spectrum",
    }
    assert expected_keys <= set(paths.keys())
    for path in paths.values():
        assert path.is_file()
        assert path.stat().st_size > 0
        img = mpimg.imread(path)
        assert np.isfinite(img).all()


def test_save_before_after_removed_panel_is_non_empty(dataset_factory, tmp_path):
    ds = _profile_with_common_background(dataset_factory, slices_count=25)
    result = remove_background(ds, method="global_median")
    path = save_before_after_removed_panel(ds, result, 5, tmp_path / "panel.png")
    assert path.is_file()
    assert path.stat().st_size > 0


def test_save_removed_component_spectrum_is_non_empty(dataset_factory, tmp_path):
    ds = _profile_with_common_background(dataset_factory, slices_count=25)
    valid_mask = np.ones((ds.shape[1], ds.shape[2]), dtype=bool)
    result = remove_background(ds, method="global_mean", valid_mask=valid_mask)
    path = save_removed_component_spectrum(result, tmp_path / "spectrum.png", valid_mask=valid_mask)
    assert path.is_file()
    assert path.stat().st_size > 0


def test_signal_preservation_and_removed_metrics_never_include_canonical_flag(dataset_factory):
    # Sprint 4A must never mark anything canonical -- confirm the QC metric
    # dicts themselves carry no such key (canonicality lives only in the
    # orchestration layer's own review/decision documents, never here).
    ds = _profile_with_common_background(dataset_factory, slices_count=20)
    valid_mask = np.ones((ds.shape[1], ds.shape[2]), dtype=bool)
    result = remove_background(ds, method="global_mean", valid_mask=valid_mask)
    signal_metrics = compute_signal_preservation_metrics(ds, result, valid_mask, channels=(0, 5, 10))
    removed_metrics = compute_removed_component_metrics(ds, result, valid_mask, channels=(0, 5, 10))
    for window_metrics in (*signal_metrics.values(), *removed_metrics.values()):
        assert "canonical" not in window_metrics
