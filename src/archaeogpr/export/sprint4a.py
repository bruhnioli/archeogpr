"""Sprint 4A exports: background-removal-specific JSON reports.

The generic NPZ/processing-metadata/processing-history/padding-verification
writers (``export/processed.py``, ``export/sprint3.py``) are reused
unchanged for background removal -- they operate on any ``ProcessingResult``/
``GPRDataset`` and need no background-specific variant. This module adds
only what Sprint 4A's spec asks for that nothing else already writes:
signal-preservation metrics, removed-component metrics, the trace-spacing/
window report, and a machine-readable per-candidate validation summary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from archaeogpr.processing.result import ProcessingResult


def write_signal_preservation_metrics_json(
    metrics_by_window: dict[str, dict[str, Any]], output_path: str | Path
) -> Path:
    """Save :func:`archaeogpr.qc.background.compute_signal_preservation_metrics`'s output."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metrics_by_window, indent=2), encoding="utf-8")
    return output_path


def write_removed_component_metrics_json(
    metrics_by_window: dict[str, dict[str, Any]], output_path: str | Path
) -> Path:
    """Save :func:`archaeogpr.qc.background.compute_removed_component_metrics`'s output."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metrics_by_window, indent=2), encoding="utf-8")
    return output_path


def write_trace_spacing_and_window_json(result: ProcessingResult, output_path: str | Path) -> Path:
    """Save this candidate's own trace-spacing/window diagnostics (from ``result.diagnostics``).

    Reports both the legacy, ambiguous ``applied_window_m`` (kept only for
    backward compatibility -- see its own ``applied_window_m_deprecated_
    note``) and the explicit, unambiguous fields introduced in Sprint 4A.1:
    ``applied_window_nominal_length_m`` (identical value, clearly named),
    ``applied_window_center_to_center_span_m`` (the window's actual
    first-to-last-trace physical distance), and ``window_half_span_m``.
    """
    diag = result.diagnostics
    report = {
        "method": diag["method"],
        "edge_mode": diag["edge_mode"],
        "requested_window_m": diag["requested_window_m"],
        "requested_window_traces": diag["requested_window_traces"],
        "raw_window_traces_float": diag["raw_window_traces_float"],
        "applied_window_traces": diag["applied_window_traces"],
        "applied_window_m": diag["applied_window_m"],
        "applied_window_m_deprecated_note": diag["applied_window_m_deprecated_note"],
        "applied_window_nominal_length_m": diag["applied_window_nominal_length_m"],
        "applied_window_center_to_center_span_m": diag["applied_window_center_to_center_span_m"],
        "window_half_span_m": diag["window_half_span_m"],
        "rounding_policy": diag["rounding_policy"],
        "trace_spacing": diag["trace_spacing"],
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output_path


def write_candidate_validation_json(
    *,
    candidate_id: str,
    before_shape: tuple[int, int, int],
    result: ProcessingResult,
    raw_file_sha256: str,
    sprint2_canonical_sha256: str,
    sprint3_canonical_sha256: str,
    output_path: str | Path,
) -> Path:
    """Save the real-data acceptance-criteria checklist for one candidate (Sprint 4A spec section 23).

    Every check here is computed directly from ``result``/the given hashes
    -- nothing is assumed true and written unchecked. The three input
    hashes are recorded as-of this run's single upfront read; the
    before/after immutability *comparison* itself is a one-time check the
    top-level orchestrator makes once for the whole run (re-hashing after
    all candidates finish), not repeated per candidate -- see
    ``sprint4a_candidates.py::run_all_sprint4a_candidates``.
    """
    dataset = result.dataset
    valid_mask = result.valid_mask
    padding_ok = True
    removed_padding_ok = True
    if valid_mask is not None:
        padding = ~valid_mask
        padding_broadcast = np.broadcast_to(padding[np.newaxis, :, :], dataset.amplitudes.shape)
        padding_ok = bool(np.all(dataset.amplitudes[padding_broadcast] == 0.0))
        removed_padding_ok = bool(np.all(result.removed_component[padding_broadcast] == 0.0))

    report = {
        "candidate_id": candidate_id,
        "shape_matches_input": tuple(dataset.shape) == tuple(before_shape),
        "dtype_is_float32": dataset.amplitudes.dtype == np.float32,
        "no_nan_or_inf": bool(np.isfinite(dataset.amplitudes).all()),
        "padding_untouched": padding_ok,
        "removed_component_zero_at_padding": removed_padding_ok,
        "raw_ogpr_sha256": raw_file_sha256,
        "sprint2_canonical_sha256": sprint2_canonical_sha256,
        "sprint3_canonical_sha256": sprint3_canonical_sha256,
        "processing_history": [record["operation"] for record in dataset.processing_history],
        "canonical": False,
        "gain_applied": False,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output_path
