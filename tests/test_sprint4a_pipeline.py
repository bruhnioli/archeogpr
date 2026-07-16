"""Synthetic end-to-end pipeline tests for Sprint 4A.

Extends the established Sprint 2/3 synthetic-chain pattern
(``test_sprint3_pipeline.py::test_full_synthetic_pipeline_...``) one more
stage: time-zero -> DC offset -> dewow -> band-pass -> background removal,
via a written-and-reloaded NPZ at each step (proving the reprocessing guard
and NPZ round-trip work through this stage too). Also runs the full
``run_all_sprint4a_candidates`` orchestration end to end against a small
synthetic "Sprint-3-canonical-style" NPZ, confirming every required file is
produced and nothing is ever marked canonical.
"""

from __future__ import annotations

import numpy as np
import pytest

from archaeogpr.export.processed import write_combined_npz, write_corrected_npz
from archaeogpr.export.sprint3 import read_processed_npz
from archaeogpr.processing.background import remove_background
from archaeogpr.processing.bandpass import correct_bandpass
from archaeogpr.processing.common import ProcessingError
from archaeogpr.processing.dc_offset import correct_dc_offset
from archaeogpr.processing.dewow import correct_dewow
from archaeogpr.processing.time_zero import correct_time_zero
from archaeogpr.sprint4a_candidates import run_all_sprint4a_candidates

SAMPLING_TIME_NS = 0.5


def test_full_synthetic_pipeline_through_background_removal(dataset_factory, tmp_path):
    amplitudes = np.zeros((30, 2, 400), dtype=np.float32)
    amplitudes[:, 0, 20] = 500.0
    amplitudes[:, 1, 22] = 500.0
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    tz_result = correct_time_zero(ds, method="manual", picks={0: 20, 1: 22}, target_sample=16)
    dc_result = correct_dc_offset(tz_result.dataset, method="mean", valid_mask=tz_result.valid_mask)
    npz_path = write_combined_npz(tz_result, dc_result, tmp_path / "sprint02_processed.npz")

    reloaded_dataset, reloaded_mask = read_processed_npz(npz_path)
    dewow_result = correct_dewow(
        reloaded_dataset, window_ns=9.0, method="running_mean", valid_mask=reloaded_mask
    )
    bandpass_result = correct_bandpass(
        dewow_result.dataset,
        method="butterworth",
        lowcut_mhz=50.0,
        highcut_mhz=800.0,
        order=4,
        valid_mask=reloaded_mask,
    )
    bandpass_npz_path = write_corrected_npz(bandpass_result, tmp_path / "sprint03_processed.npz")

    reloaded_sprint3_dataset, reloaded_sprint3_mask = read_processed_npz(bandpass_npz_path)
    background_result = remove_background(
        reloaded_sprint3_dataset, method="global_mean", valid_mask=reloaded_sprint3_mask
    )

    final = background_result.dataset
    assert final.shape == ds.shape
    assert final.amplitudes.dtype == np.float32
    assert [r["operation"] for r in final.processing_history] == [
        "time_zero_correction",
        "dc_offset_correction",
        "dewow_correction",
        "bandpass_correction",
        "background_removal",
    ]
    assert np.isfinite(final.amplitudes).all()

    background_npz_path = write_corrected_npz(background_result, tmp_path / "sprint04a_processed.npz")
    reloaded_final_dataset, _ = read_processed_npz(background_npz_path)
    with pytest.raises(ProcessingError, match="already contains"):
        remove_background(reloaded_final_dataset, method="global_mean", valid_mask=reloaded_sprint3_mask)


def _synthetic_sprint3_canonical_npz(dataset_factory, tmp_path):
    """A small NPZ shaped like ``outputs/sprint03/canonical_D2_B1/sprint03_processed.npz``."""
    amplitudes = np.zeros((30, 11, 400), dtype=np.float32)
    for channel in range(11):
        amplitudes[:, channel, 20 + channel] = 500.0
    ds = dataset_factory(
        amplitudes=amplitudes,
        slices_count=30,
        channels_count=11,
        samples_count=400,
        sampling_time_ns=SAMPLING_TIME_NS,
    )
    picks = {c: 20 + c for c in range(11)}
    tz_result = correct_time_zero(ds, method="manual", picks=picks, target_sample=16)
    dc_result = correct_dc_offset(tz_result.dataset, method="mean", valid_mask=tz_result.valid_mask)
    dewow_result = correct_dewow(
        dc_result.dataset, window_ns=9.0, method="running_mean", valid_mask=tz_result.valid_mask
    )
    bandpass_result = correct_bandpass(
        dewow_result.dataset,
        method="butterworth",
        lowcut_mhz=50.0,
        highcut_mhz=800.0,
        order=4,
        valid_mask=tz_result.valid_mask,
    )
    return write_corrected_npz(bandpass_result, tmp_path / "sprint03_processed.npz")


def test_run_all_sprint4a_candidates_synthetic_end_to_end(dataset_factory, tmp_path):
    npz_path = _synthetic_sprint3_canonical_npz(dataset_factory, tmp_path)
    background_config = tmp_path / "background_candidates.yaml"
    background_config.write_text(
        "edge_mode: reflect\n"
        "candidates:\n"
        "  - id: A1\n    label: global_mean\n    method: global_mean\n"
        "  - id: A2\n    label: global_median\n    method: global_median\n"
        "  - id: A3\n    label: sliding_mean_5tr\n    method: sliding_mean\n    window_traces: 5\n"
        "  - id: A4\n    label: sliding_median_5tr\n    method: sliding_median\n    window_traces: 5\n",
        encoding="utf-8",
    )

    result = run_all_sprint4a_candidates(
        npz_path,
        tmp_path / "sprint04a",
        background_config_path=background_config,
        sprint2_canonical_npz_path=None,
    )

    assert [info["id"] for info in result["candidates"]] == ["A1", "A2", "A3", "A4"]
    assert result["input_hash_unchanged"] is True
    assert result["sprint2_canonical_sha256"] == "not_verified_this_run"
    assert result["decision_panel_path"].is_file()
    assert result["decision_panel_path"].stat().st_size > 0
    assert result["decision_panel_detail_path"].is_file()
    assert result["final_decision_path"].is_file()

    final_decision_text = result["final_decision_path"].read_text(encoding="utf-8")
    assert "No background-removal candidate has been selected as canonical" in final_decision_text
    assert "Gain has not started" in final_decision_text
    # Sprint 4A.1 correction's exact required column set (spec section 8).
    for column in (
        "Candidate",
        "Method",
        "Requested window",
        "Applied trace count",
        "Nominal window length",
        "Center-to-center spatial span",
        "Background suppression",
        "Overall RMS retention",
        "Waveform correlation",
        "Spectral retention",
        "Local-event amplitude retention",
        "Paired-control short-target retention",
        "Paired-control long-target retention",
        "Removed coherent-event risk proxy",
        "Padding safety",
        "Timing preservation",
        "Engineering interpretation",
        "Main risk",
    ):
        assert column in final_decision_text
    # Required disclaimer lines (Sprint 4A.1 spec section 8).
    assert (
        "Overall RMS retention is not equivalent to archaeological-target preservation" in final_decision_text
    )
    assert "not a direct signal/noise classifier" in final_decision_text
    assert "common-scale B-scans" in final_decision_text
    # The old, removed "preservation fraction" framing must never reappear.
    assert "Long-horizontal-event preservation" not in final_decision_text
    assert "Localized-event preservation" not in final_decision_text

    for info in result["candidates"]:
        candidate_dir = info["output_dir"]
        for required_file in (
            "background_processed.npz",
            "processing_metadata.json",
            "processing_history.json",
            "padding_verification.json",
            "signal_preservation_metrics.json",
            "removed_component_metrics.json",
            "trace_spacing_and_window.json",
            "candidate_validation.json",
        ):
            path = candidate_dir / required_file
            assert path.is_file(), f"missing {required_file} for {info['id']}"
            assert path.stat().st_size > 0

        reloaded_dataset, _ = read_processed_npz(candidate_dir / "background_processed.npz")
        assert reloaded_dataset.shape == (30, 11, 400)
        assert [r["operation"] for r in reloaded_dataset.processing_history][-1] == "background_removal"


def test_run_all_sprint4a_candidates_never_marks_anything_canonical(dataset_factory, tmp_path):
    npz_path = _synthetic_sprint3_canonical_npz(dataset_factory, tmp_path)
    background_config = tmp_path / "background_candidates_small.yaml"
    background_config.write_text(
        "edge_mode: reflect\ncandidates:\n  - id: A1\n    label: global_mean\n    method: global_mean\n",
        encoding="utf-8",
    )
    result = run_all_sprint4a_candidates(
        npz_path,
        tmp_path / "sprint04a_small",
        background_config_path=background_config,
        sprint2_canonical_npz_path=None,
    )
    for info in result["candidates"]:
        assert "canonical" not in info["result"].diagnostics
        assert "canonical" not in info["result"].dataset.metadata
        validation = (info["output_dir"] / "candidate_validation.json").read_text(encoding="utf-8")
        assert '"canonical": false' in validation
        assert '"gain_applied": false' in validation
