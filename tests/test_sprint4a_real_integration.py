"""Integration test for Sprint 4A (background removal) against the real canonical Sprint 3 NPZ.

Skips cleanly (not a failure) if that file is not present under
outputs/sprint03/canonical_D2_B1/. Mirrors test_sprint3_real_integration.py's
pattern (hash-before/after, shape/dtype/finiteness, time-axis/valid-mask/
padding preservation, input immutability, processing-history order) but is
gated on the canonical Sprint 3 NPZ rather than the raw .ogpr file, per
Sprint 4A's own input requirement (spec section 4). Also runs the full
8-candidate real orchestration (``run_all_sprint4a_candidates``) with the
project's own ``configs/background_candidates.yaml`` and checks the
real-data acceptance criteria (spec section 23). Never marks anything
canonical, never applies gain.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from archaeogpr.export.sprint3 import read_processed_npz
from archaeogpr.export.sprint4a import (
    write_removed_component_metrics_json,
    write_signal_preservation_metrics_json,
)
from archaeogpr.processing.background import remove_background
from archaeogpr.qc.background import (
    compute_removed_component_metrics,
    compute_signal_preservation_metrics,
    save_background_qc_suite,
)
from archaeogpr.sprint4a_candidates import CANDIDATE_CHANNELS, run_all_sprint4a_candidates

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CANONICAL_SPRINT3_NPZ = _PROJECT_ROOT / "outputs" / "sprint03" / "canonical_D2_B1" / "sprint03_processed.npz"
_RAW_FILE = _PROJECT_ROOT / "data" / "raw" / "Swath003_Array02.ogpr"
_SPRINT2_CANONICAL_NPZ = (
    _PROJECT_ROOT / "outputs" / "sprint02" / "canonical_target16" / "sprint02_processed.npz"
)
_BACKGROUND_CONFIG = _PROJECT_ROOT / "configs" / "background_candidates.yaml"

pytestmark = pytest.mark.skipif(
    not _CANONICAL_SPRINT3_NPZ.is_file(),
    reason=(
        f"Canonical Sprint 3 NPZ not found at {_CANONICAL_SPRINT3_NPZ}; skipping Sprint 4A integration test."
    ),
)

_EXPECTED_SPRINT3_HISTORY = (
    "time_zero_correction",
    "dc_offset_correction",
    "dewow_correction",
    "bandpass_correction",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_background_removal_on_real_canonical_sprint3_input(tmp_path):
    hash_before = _sha256(_CANONICAL_SPRINT3_NPZ)
    dataset, valid_mask = read_processed_npz(_CANONICAL_SPRINT3_NPZ)
    assert valid_mask is not None

    # --- input must carry exactly the canonical Sprint 3 processing history ----
    assert tuple(r["operation"] for r in dataset.processing_history) == _EXPECTED_SPRINT3_HISTORY

    amplitudes_before = dataset.amplitudes.copy()

    global_result = remove_background(dataset, method="global_mean", valid_mask=valid_mask)
    sliding_result = remove_background(
        dataset, method="sliding_median", window_m=1.0, valid_mask=valid_mask, edge_mode="reflect"
    )

    # --- shape / dtype / finiteness ------------------------------------------
    for result in (global_result, sliding_result):
        assert result.dataset.shape == dataset.shape
        assert result.dataset.amplitudes.dtype == np.float32
        assert np.isfinite(result.dataset.amplitudes).all()
        assert np.isfinite(result.removed_component).all()

    # --- time axis / valid mask preserved bit-for-bit -------------------------
    for result in (global_result, sliding_result):
        np.testing.assert_array_equal(result.dataset.time_ns, dataset.time_ns)
        assert result.valid_mask is not None
        np.testing.assert_array_equal(result.valid_mask, valid_mask)

    # --- padding exactly zero in both output and removed component -----------
    padding = ~valid_mask
    for result in (global_result, sliding_result):
        padding_broadcast = np.broadcast_to(padding[np.newaxis, :, :], result.dataset.amplitudes.shape)
        np.testing.assert_array_equal(result.dataset.amplitudes[padding_broadcast], 0.0)
        np.testing.assert_array_equal(result.removed_component[padding_broadcast], 0.0)

    # --- input = output + removed_component (the mandatory invariant, spec 5) --
    for result in (global_result, sliding_result):
        reconstructed = result.dataset.amplitudes.astype(np.float64) + result.removed_component.astype(
            np.float64
        )
        # float32 round-trip precision (subtract then add back), not an exact identity --
        # amplitudes here run into the tens of thousands, so a purely absolute tolerance
        # would be too tight; rtol accounts for float32's ~7-significant-digit precision.
        np.testing.assert_allclose(reconstructed, dataset.amplitudes.astype(np.float64), rtol=1e-4, atol=0.05)

    # --- input dataset immutability -------------------------------------------
    np.testing.assert_array_equal(dataset.amplitudes, amplitudes_before)

    # --- processing history: exactly one background_removal appended ---------
    assert tuple(r["operation"] for r in global_result.dataset.processing_history) == (
        *_EXPECTED_SPRINT3_HISTORY,
        "background_removal",
    )

    # --- signal-preservation / removed-component metrics compute + serialize --
    signal_metrics = compute_signal_preservation_metrics(
        dataset, global_result, valid_mask, channels=CANDIDATE_CHANNELS
    )
    removed_metrics = compute_removed_component_metrics(
        dataset, global_result, valid_mask, channels=CANDIDATE_CHANNELS
    )
    signal_path = write_signal_preservation_metrics_json(
        signal_metrics, tmp_path / "signal_preservation_metrics.json"
    )
    removed_path = write_removed_component_metrics_json(
        removed_metrics, tmp_path / "removed_component_metrics.json"
    )
    assert signal_path.stat().st_size > 0
    assert removed_path.stat().st_size > 0
    for window_metrics in (*signal_metrics.values(), *removed_metrics.values()):
        assert "canonical" not in window_metrics

    # --- QC plotting suite produces non-empty files ---------------------------
    qc_paths = save_background_qc_suite(dataset, global_result, tmp_path / "qc")
    for path in qc_paths.values():
        assert path.is_file()
        assert path.stat().st_size > 0

    # --- canonical Sprint 3 NPZ untouched on disk ------------------------------
    hash_after = _sha256(_CANONICAL_SPRINT3_NPZ)
    assert hash_after == hash_before


def test_run_all_sprint4a_candidates_on_real_data(tmp_path):
    raw_hash_before = _sha256(_RAW_FILE) if _RAW_FILE.is_file() else None
    sprint2_hash_before = _sha256(_SPRINT2_CANONICAL_NPZ) if _SPRINT2_CANONICAL_NPZ.is_file() else None
    sprint3_hash_before = _sha256(_CANONICAL_SPRINT3_NPZ)

    result = run_all_sprint4a_candidates(
        _CANONICAL_SPRINT3_NPZ,
        tmp_path / "sprint04a",
        background_config_path=_BACKGROUND_CONFIG,
        sprint2_canonical_npz_path=_SPRINT2_CANONICAL_NPZ if _SPRINT2_CANONICAL_NPZ.is_file() else None,
    )

    # --- all 8 candidates produced, none canonical, no gain --------------------
    assert [info["id"] for info in result["candidates"]] == [f"A{i}" for i in range(1, 9)]
    assert result["input_hash_unchanged"] is True

    for info in result["candidates"]:
        candidate_dir = info["output_dir"]
        validation_text = (candidate_dir / "candidate_validation.json").read_text(encoding="utf-8")
        assert '"canonical": false' in validation_text
        assert '"gain_applied": false' in validation_text
        assert '"padding_untouched": true' in validation_text
        assert '"removed_component_zero_at_padding": true' in validation_text
        assert '"no_nan_or_inf": true' in validation_text
        assert '"shape_matches_input": true' in validation_text

        reloaded_dataset, reloaded_mask = read_processed_npz(candidate_dir / "background_processed.npz")
        assert reloaded_mask is not None
        assert reloaded_dataset.shape == (175, 11, 1024)
        history_ops = tuple(r["operation"] for r in reloaded_dataset.processing_history)
        assert history_ops == (*_EXPECTED_SPRINT3_HISTORY, "background_removal")

    # --- measurable differences between candidates (never presented as "all the same") --
    output_means = {
        info["id"]: float(info["result"].dataset.amplitudes.astype(np.float64).mean())
        for info in result["candidates"]
    }
    assert len(set(output_means.values())) > 1

    # --- decision panel / final decision report exist and are non-canonical ----
    assert result["decision_panel_path"].is_file()
    assert result["decision_panel_path"].stat().st_size > 0
    assert result["decision_panel_detail_path"].is_file()
    final_decision_text = result["final_decision_path"].read_text(encoding="utf-8")
    assert "Status: review_required" in final_decision_text
    assert "No background-removal candidate has been selected as canonical." in final_decision_text
    assert "Gain has not started." in final_decision_text
    assert "best candidate" not in final_decision_text.lower()

    # --- comparison outputs exist ------------------------------------------------
    for key in (
        "candidate_metrics_csv",
        "candidate_metrics_by_channel_csv",
        "candidate_metrics_by_time_window_csv",
        "synthetic_target_attenuation_csv",
        "trace_spacing_summary",
        "review",
    ):
        path = result["comparison_paths"][key]
        assert path.is_file()
        assert path.stat().st_size > 0

    # --- Sprint 4A.2/Closure: A0 recorded in candidate_metrics.csv, never as an
    # NPZ or a candidate output directory anywhere in this real run ------------
    candidate_metrics_csv = result["comparison_paths"]["candidate_metrics_csv"]
    csv_text = candidate_metrics_csv.read_text(encoding="utf-8")
    assert csv_text.splitlines()[1].startswith("A0,")
    assert list((tmp_path / "sprint04a").rglob("*A0*.npz")) == []
    assert not any("A0" in p.name for p in (tmp_path / "sprint04a").rglob("*") if p.is_dir())

    # --- engineering categories restricted to the allowed vocabulary ------------
    allowed_categories = {
        "preservation-favoring",
        "suppression-favoring",
        "balanced",
        "too_aggressive",
        "too_weak",
        "inconclusive",
    }
    assert set(result["engineering_categories"].values()) <= allowed_categories

    # --- nothing on disk (raw / sprint2 / sprint3 canonical) was ever mutated ----
    if raw_hash_before is not None:
        assert _sha256(_RAW_FILE) == raw_hash_before
    if sprint2_hash_before is not None:
        assert _sha256(_SPRINT2_CANONICAL_NPZ) == sprint2_hash_before
    assert _sha256(_CANONICAL_SPRINT3_NPZ) == sprint3_hash_before


def test_sprint4a_closure_canonical_chain_has_no_background_removal():
    """Sprint 4A Closure (ADR-009): canonical policy = A0, so the canonical NPZ's own history is untouched."""
    dataset, _valid_mask = read_processed_npz(_CANONICAL_SPRINT3_NPZ)
    history_ops = tuple(r["operation"] for r in dataset.processing_history)
    assert history_ops == _EXPECTED_SPRINT3_HISTORY
    assert "background_removal" not in history_ops
