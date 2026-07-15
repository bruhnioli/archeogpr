"""Tests for Sprint 3 canonicalization (``sprint3_canonical.py``): the ONE
human/geophysicist-selected D2 dewow + B1 band-pass chain, run against the
real Sprint 2 canonical NPZ.

Unlike ``test_sprint3_real_integration.py`` / ``test_sprint3_1_decision_qc.py``
(which never mark anything canonical), this file specifically verifies the
canonicalization behavior: that D2+B1 are applied with their exact decided
parameters, in the exact decided order, deterministically, without mutating
any input, and that the resulting metadata correctly records who made the
selection -- while confirming the underlying candidate-comparison code path
(``sprint3_candidates.py``) still never marks anything canonical.

Skips cleanly (not a failure) if the real Sprint 2 canonical NPZ or the raw
sample file are not present.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from archaeogpr.export.sprint3 import read_processed_npz
from archaeogpr.processing.bandpass import correct_bandpass
from archaeogpr.processing.dewow import correct_dewow
from archaeogpr.sprint3_candidates import run_bandpass_candidates, run_dewow_candidates
from archaeogpr.sprint3_canonical import (
    CANONICAL_BANDPASS_CANDIDATE_ID,
    CANONICAL_BANDPASS_METHOD,
    CANONICAL_DEWOW_CANDIDATE_ID,
    CANONICAL_DEWOW_EDGE_MODE,
    CANONICAL_DEWOW_METHOD,
    CANONICAL_DEWOW_WINDOW_NS,
    CANONICAL_HIGHCUT_MHZ,
    CANONICAL_LOWCUT_MHZ,
    CANONICAL_ORDER,
    CANONICAL_ZERO_PHASE,
    SELECTION_AUTHORITY,
    SELECTION_REFERENCES,
    run_sprint3_canonical,
    write_canonical_processing_note,
)

_CANONICAL_NPZ = (
    Path(__file__).resolve().parents[1]
    / "outputs"
    / "sprint02"
    / "canonical_target16"
    / "sprint02_processed.npz"
)
_RAW_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "Swath003_Array02.ogpr"

pytestmark = pytest.mark.skipif(
    not _CANONICAL_NPZ.is_file(),
    reason=f"Real Sprint 2 canonical NPZ not found at {_CANONICAL_NPZ}; skipping canonicalization tests.",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_canonical_constants_encode_the_human_decision():
    """Sprint 3.1's D2/B1 decision, not re-derived -- see D2_DEWOW_DECISION.md,

    BANDPASS_FINAL_DECISION_REQUIRED.md.
    """
    assert CANONICAL_DEWOW_CANDIDATE_ID == "D2"
    assert CANONICAL_DEWOW_METHOD == "running_mean"
    assert CANONICAL_DEWOW_WINDOW_NS == 8.0
    assert CANONICAL_DEWOW_EDGE_MODE == "reflect"
    assert CANONICAL_BANDPASS_CANDIDATE_ID == "B1"
    assert CANONICAL_BANDPASS_METHOD == "butterworth"
    assert CANONICAL_LOWCUT_MHZ == 100.0
    assert CANONICAL_HIGHCUT_MHZ == 900.0
    assert CANONICAL_ORDER == 4
    assert CANONICAL_ZERO_PHASE is True
    assert SELECTION_AUTHORITY == "human/geophysical review"
    assert len(SELECTION_REFERENCES) == 3


def test_run_sprint3_canonical_processing_history_order(tmp_path):
    result = run_sprint3_canonical(_CANONICAL_NPZ, tmp_path / "canonical")
    final_dataset = result["bandpass_result"].dataset
    assert [r["operation"] for r in final_dataset.processing_history] == [
        "time_zero_correction",
        "dc_offset_correction",
        "dewow_correction",
        "bandpass_correction",
    ]
    # B1 is built directly from D2's own output dataset -- not the raw Sprint 2 input.
    dewow_history_len = len(result["dewow_result"].dataset.processing_history)
    assert dewow_history_len == 3
    assert len(final_dataset.processing_history) == 4


def test_run_sprint3_canonical_D2_applied_exact_window(tmp_path):
    result = run_sprint3_canonical(_CANONICAL_NPZ, tmp_path / "canonical")
    diagnostics = result["dewow_result"].diagnostics
    assert diagnostics["applied_window_ns"] == pytest.approx(8.125, abs=1e-6)
    assert diagnostics["applied_window_samples"] == 65
    assert diagnostics["edge_mode"] == "reflect"


def test_run_sprint3_canonical_B1_applied_exact_parameters(tmp_path):
    result = run_sprint3_canonical(_CANONICAL_NPZ, tmp_path / "canonical")
    diagnostics = result["bandpass_result"].diagnostics
    assert diagnostics["method"] == "butterworth"
    assert diagnostics["lowcut_mhz"] == 100.0
    assert diagnostics["highcut_mhz"] == 900.0
    assert diagnostics["order"] == 4
    assert diagnostics["zero_phase"] is True


def test_run_sprint3_canonical_phase_lag_zero(tmp_path):
    result = run_sprint3_canonical(_CANONICAL_NPZ, tmp_path / "canonical")
    phase_verification = result["phase_verification"]
    assert phase_verification["confirmed_zero_phase"] is True
    assert phase_verification["max_abs_median_trace_cross_correlation_lag"] == 0


def test_run_sprint3_canonical_time_axis_and_valid_mask_preserved(tmp_path):
    result = run_sprint3_canonical(_CANONICAL_NPZ, tmp_path / "canonical")
    dataset = result["dataset"]
    valid_mask = result["valid_mask"]
    dewow_result = result["dewow_result"]
    bandpass_result = result["bandpass_result"]

    np.testing.assert_array_equal(dewow_result.dataset.time_ns, dataset.time_ns)
    np.testing.assert_array_equal(bandpass_result.dataset.time_ns, dataset.time_ns)

    assert valid_mask is not None
    assert dewow_result.valid_mask is not None
    assert bandpass_result.valid_mask is not None
    np.testing.assert_array_equal(dewow_result.valid_mask, valid_mask)
    np.testing.assert_array_equal(bandpass_result.valid_mask, valid_mask)


def test_run_sprint3_canonical_padding_stays_exactly_zero(tmp_path):
    result = run_sprint3_canonical(_CANONICAL_NPZ, tmp_path / "canonical")
    valid_mask = result["valid_mask"]
    padding = ~valid_mask
    for step_result in (result["dewow_result"], result["bandpass_result"]):
        padding_broadcast = np.broadcast_to(padding[np.newaxis, :, :], step_result.dataset.amplitudes.shape)
        np.testing.assert_array_equal(step_result.dataset.amplitudes[padding_broadcast], 0.0)
        np.testing.assert_array_equal(step_result.removed_component[padding_broadcast], 0.0)


def test_run_sprint3_canonical_no_nan_or_inf(tmp_path):
    result = run_sprint3_canonical(_CANONICAL_NPZ, tmp_path / "canonical")
    final_dataset = result["bandpass_result"].dataset
    assert np.isfinite(final_dataset.amplitudes).all()


def test_run_sprint3_canonical_input_immutable_and_hash_unchanged(tmp_path):
    hash_before = _sha256(_CANONICAL_NPZ)
    reference_dataset, reference_mask = read_processed_npz(_CANONICAL_NPZ)

    result = run_sprint3_canonical(_CANONICAL_NPZ, tmp_path / "canonical")

    hash_after = _sha256(_CANONICAL_NPZ)
    assert hash_after == hash_before

    np.testing.assert_array_equal(result["dataset"].amplitudes, reference_dataset.amplitudes)
    np.testing.assert_array_equal(result["valid_mask"], reference_mask)


def test_run_sprint3_canonical_deterministic(tmp_path):
    result_a = run_sprint3_canonical(_CANONICAL_NPZ, tmp_path / "run_a")
    result_b = run_sprint3_canonical(_CANONICAL_NPZ, tmp_path / "run_b")

    np.testing.assert_array_equal(
        result_a["bandpass_result"].dataset.amplitudes, result_b["bandpass_result"].dataset.amplitudes
    )
    assert result_a["canonical_parameters"] == result_b["canonical_parameters"]
    assert result_a["phase_verification"] == result_b["phase_verification"]


def test_canonical_parameters_json_has_selection_authority_and_scope(tmp_path):
    output_dir = tmp_path / "canonical"
    result = run_sprint3_canonical(_CANONICAL_NPZ, output_dir)
    canonical_parameters_path = result["generated"]["canonical_parameters_json"]
    payload = json.loads(canonical_parameters_path.read_text(encoding="utf-8"))

    assert payload["canonical"] is True
    assert payload["selection_authority"] == "human/geophysical review"
    assert len(payload["selection_references"]) == 3
    assert payload["chain"] == [
        "time_zero_correction",
        "dc_offset_correction",
        "dewow_correction",
        "bandpass_correction",
    ]
    assert payload["dewow"]["candidate_id"] == "D2"
    assert payload["bandpass"]["candidate_id"] == "B1"
    assert "Swath003_Array02.ogpr" in payload["dataset_scope"]


def test_output_npz_reopens_without_pickle(tmp_path):
    output_dir = tmp_path / "canonical"
    result = run_sprint3_canonical(_CANONICAL_NPZ, output_dir)
    npz_path = result["generated"]["npz"]

    reloaded_dataset, reloaded_mask = read_processed_npz(npz_path)
    final_dataset = result["bandpass_result"].dataset
    np.testing.assert_array_equal(reloaded_dataset.amplitudes, final_dataset.amplitudes)
    assert reloaded_mask is not None
    np.testing.assert_array_equal(reloaded_mask, result["valid_mask"])


def test_write_canonical_processing_note_contains_required_elements(tmp_path):
    result = run_sprint3_canonical(_CANONICAL_NPZ, tmp_path / "canonical")
    note_path = write_canonical_processing_note(
        result, "deadbeef" * 8, "cafebabe" * 8, tmp_path / "CANONICAL_PROCESSING_NOTE.md"
    )
    text = note_path.read_text(encoding="utf-8")

    assert "human/geophysical review" in text
    assert "D2" in text and "B1" in text
    assert "preservation-favoring" in text
    assert "800-900 MHz" in text
    assert "canonical for Swath003_Array02.ogpr" in text
    assert "deadbeef" * 8 in text
    assert "cafebabe" * 8 in text
    assert "does NOT do" in text
    assert "confirmed_zero_phase=True" in text


def test_candidate_outputs_never_marked_canonical(tmp_path):
    """The reused ``sprint3_candidates.py`` orchestration must stay canonical-free.

    Canonicalization is an entirely separate artifact (``canonical_parameters.json``,
    written only by ``run_sprint3_canonical``) -- it must never leak into the
    ``ProcessingResult``/``GPRDataset`` objects that the candidate-comparison
    code path (used by the ``sprint3-candidates`` CLI command) also produces.
    """
    dataset, valid_mask = read_processed_npz(_CANONICAL_NPZ)

    one_dewow_candidate_config = {
        "edge_mode": "reflect",
        "candidates": [{"id": "D2", "label": "running_mean_8ns", "method": "running_mean", "window_ns": 8.0}],
    }
    dewow_candidates_info = run_dewow_candidates(
        dataset, valid_mask, tmp_path / "dewow", one_dewow_candidate_config
    )
    assert len(dewow_candidates_info) == 1
    dewow_result = dewow_candidates_info[0]["result"]
    assert "canonical" not in dewow_result.diagnostics
    assert "canonical" not in dewow_result.dataset.metadata

    one_bandpass_candidate_config = {
        "candidates": [
            {
                "id": "B1",
                "label": "butterworth_100_900",
                "method": "butterworth",
                "lowcut_mhz": 100.0,
                "highcut_mhz": 900.0,
                "order": 4,
            }
        ]
    }
    bandpass_candidates_info = run_bandpass_candidates(
        dewow_result, valid_mask, tmp_path / "bandpass", one_bandpass_candidate_config
    )
    assert len(bandpass_candidates_info) == 1
    bandpass_result = bandpass_candidates_info[0]["result"]
    assert "canonical" not in bandpass_result.diagnostics
    assert "canonical" not in bandpass_result.dataset.metadata


def test_direct_correct_dewow_correct_bandpass_match_canonical_output(tmp_path):
    """`run_sprint3_canonical` must be a thin wrapper -- no new filtering algorithm.

    Calling ``correct_dewow``/``correct_bandpass`` directly with the same D2/B1
    parameters must reproduce byte-identical amplitudes to what
    ``run_sprint3_canonical`` produced -- confirming it reuses those functions
    unchanged rather than reimplementing anything.
    """
    dataset, valid_mask = read_processed_npz(_CANONICAL_NPZ)
    dewow_result = correct_dewow(
        dataset,
        window_ns=CANONICAL_DEWOW_WINDOW_NS,
        method=CANONICAL_DEWOW_METHOD,
        valid_mask=valid_mask,
        edge_mode=CANONICAL_DEWOW_EDGE_MODE,
    )
    bandpass_result = correct_bandpass(
        dewow_result.dataset,
        method=CANONICAL_BANDPASS_METHOD,
        lowcut_mhz=CANONICAL_LOWCUT_MHZ,
        highcut_mhz=CANONICAL_HIGHCUT_MHZ,
        order=CANONICAL_ORDER,
        zero_phase=CANONICAL_ZERO_PHASE,
        valid_mask=valid_mask,
    )

    canonical_result = run_sprint3_canonical(_CANONICAL_NPZ, tmp_path / "canonical")
    np.testing.assert_array_equal(
        bandpass_result.dataset.amplitudes, canonical_result["bandpass_result"].dataset.amplitudes
    )
