"""Sprint 3 canonicalization: the human/geophysicist-selected D2 + B1 chain.

Unlike ``sprint3_candidates.py`` (which never marks anything canonical),
this module runs the ONE chain the human/geophysical review
(``outputs/sprint03_1/BANDPASS_FINAL_DECISION_REQUIRED.md``,
``outputs/sprint03_1/D2_DEWOW_DECISION.md``) selected:

    Sprint 2 canonical (target_sample=16) -> D2 dewow -> B1 band-pass

and writes it as the canonical Sprint 3 output. It reuses
``correct_dewow()``/``correct_bandpass()`` unchanged -- no new filtering
algorithm. Nothing here re-decides D2 or B1; both are accepted as fixed,
named parameters recording the human decision, not re-derived or
re-optimized.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from archaeogpr import __version__ as ARCHAEOGPR_VERSION
from archaeogpr.export.processed import (
    write_corrected_npz,
    write_processing_history_json,
    write_processing_metadata_json,
)
from archaeogpr.export.sprint3 import read_processed_npz, write_padding_verification_json
from archaeogpr.processing.bandpass import correct_bandpass
from archaeogpr.processing.dewow import correct_dewow
from archaeogpr.processing.result import ProcessingResult
from archaeogpr.qc.bandpass import save_transfer_function_plot
from archaeogpr.qc.bscan import save_all_channels_bscan, save_channel_bscan
from archaeogpr.qc.spectrum import save_spectrum_comparison

#: The human/geophysicist-selected canonical parameters (see
#: outputs/sprint03_1/{D2_DEWOW_DECISION,BANDPASS_FINAL_DECISION_REQUIRED}.md).
#: Defaults only -- callers (CLI, tests) may override, but the *decision*
#: these encode is not re-derived here.
CANONICAL_DEWOW_CANDIDATE_ID = "D2"
CANONICAL_DEWOW_METHOD = "running_mean"
CANONICAL_DEWOW_WINDOW_NS = 8.0
CANONICAL_DEWOW_EDGE_MODE = "reflect"

CANONICAL_BANDPASS_CANDIDATE_ID = "B1"
CANONICAL_BANDPASS_METHOD = "butterworth"
CANONICAL_LOWCUT_MHZ = 100.0
CANONICAL_HIGHCUT_MHZ = 900.0
CANONICAL_ORDER = 4
CANONICAL_ZERO_PHASE = True

SELECTION_AUTHORITY = "human/geophysical review"
SELECTION_REFERENCES = (
    "outputs/sprint03_1/D2_DEWOW_DECISION.md",
    "outputs/sprint03_1/BANDPASS_FINAL_DECISION_REQUIRED.md",
    "outputs/sprint03_1/B1_vs_B2_energy_summary.json",
)
DATASET_SCOPE_STATEMENT = (
    "These parameters are canonical for Swath003_Array02.ogpr (this validated dataset) only. "
    "A different dataset or acquisition setting requires its own QC/candidate comparison and its "
    "own human/geophysical review before being treated as canonical -- see ADR-007."
)


def run_sprint3_canonical(
    npz_path: str | Path,
    output_dir: str | Path,
    *,
    dewow_method: str = CANONICAL_DEWOW_METHOD,
    dewow_window_ns: float = CANONICAL_DEWOW_WINDOW_NS,
    dewow_edge_mode: str = CANONICAL_DEWOW_EDGE_MODE,
    bandpass_method: str = CANONICAL_BANDPASS_METHOD,
    lowcut_mhz: float = CANONICAL_LOWCUT_MHZ,
    highcut_mhz: float = CANONICAL_HIGHCUT_MHZ,
    order: int = CANONICAL_ORDER,
    zero_phase: bool = CANONICAL_ZERO_PHASE,
    channel: int = 0,
    clip_percentile: float = 99.0,
    cmap: str = "seismic",
) -> dict[str, Any]:
    """Run the canonical Sprint 2 -> D2 -> B1 chain and write every required output file.

    Returns a dict with ``dataset`` (Sprint 2 canonical input), ``valid_mask``,
    ``dewow_result``, ``bandpass_result`` (the two ``ProcessingResult``s),
    and ``generated`` (a ``{name: Path}`` dict of every file written).
    """
    npz_path = Path(npz_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset, valid_mask = read_processed_npz(npz_path)

    dewow_result: ProcessingResult = correct_dewow(
        dataset,
        window_ns=dewow_window_ns,
        method=dewow_method,
        valid_mask=valid_mask,
        edge_mode=dewow_edge_mode,
    )
    bandpass_result: ProcessingResult = correct_bandpass(
        dewow_result.dataset,
        method=bandpass_method,
        lowcut_mhz=lowcut_mhz,
        highcut_mhz=highcut_mhz,
        order=order,
        zero_phase=zero_phase,
        valid_mask=valid_mask,
    )
    final_dataset = bandpass_result.dataset

    generated: dict[str, Path] = {}

    generated["npz"] = write_corrected_npz(bandpass_result, output_dir / "sprint03_processed.npz")
    generated["processing_history_json"] = write_processing_history_json(
        final_dataset, output_dir / "processing_history.json"
    )
    generated["processing_metadata_json"] = write_processing_metadata_json(
        bandpass_result, output_dir / "processing_metadata.json"
    )
    generated["padding_verification_json"] = write_padding_verification_json(
        bandpass_result, output_dir / "padding_verification.json"
    )

    canonical_parameters: dict[str, Any] = {
        "canonical": True,
        "selection_authority": SELECTION_AUTHORITY,
        "selection_references": list(SELECTION_REFERENCES),
        "chain": [
            "time_zero_correction",
            "dc_offset_correction",
            "dewow_correction",
            "bandpass_correction",
        ],
        "dewow": {
            "candidate_id": CANONICAL_DEWOW_CANDIDATE_ID,
            "method": dewow_method,
            "requested_window_ns": dewow_window_ns,
            "applied_window_ns": dewow_result.diagnostics["applied_window_ns"],
            "applied_window_samples": dewow_result.diagnostics["applied_window_samples"],
            "edge_mode": dewow_edge_mode,
        },
        "bandpass": {
            "candidate_id": CANONICAL_BANDPASS_CANDIDATE_ID,
            "method": bandpass_method,
            "lowcut_mhz": lowcut_mhz,
            "highcut_mhz": highcut_mhz,
            "order": order,
            "zero_phase": zero_phase,
        },
        "dataset_scope": DATASET_SCOPE_STATEMENT,
        "archaeogpr_version": ARCHAEOGPR_VERSION,
    }
    canonical_parameters_path = output_dir / "canonical_parameters.json"
    canonical_parameters_path.write_text(json.dumps(canonical_parameters, indent=2), encoding="utf-8")
    generated["canonical_parameters_json"] = canonical_parameters_path

    all_lags = [
        segment["median_trace_cross_correlation_lag"]
        for segment in bandpass_result.diagnostics["peak_shift_and_lag_per_segment"].values()
    ]
    phase_verification = {
        "method": bandpass_method,
        "zero_phase_requested": zero_phase,
        "per_segment_median_trace_cross_correlation_lag": {
            key: value["median_trace_cross_correlation_lag"]
            for key, value in bandpass_result.diagnostics["peak_shift_and_lag_per_segment"].items()
        },
        "max_abs_median_trace_cross_correlation_lag": (
            int(max(abs(lag) for lag in all_lags)) if all_lags else None
        ),
        "confirmed_zero_phase": all(lag == 0 for lag in all_lags),
    }
    phase_verification_path = output_dir / "phase_verification.json"
    phase_verification_path.write_text(json.dumps(phase_verification, indent=2), encoding="utf-8")
    generated["phase_verification_json"] = phase_verification_path

    stem = f"channel{channel:02d}"
    generated["channel00_raw"] = save_channel_bscan(
        dataset, channel, output_dir / f"{stem}_raw.png", clip_percentile=clip_percentile, cmap=cmap
    )
    generated["channel00_after_dewow"] = save_channel_bscan(
        dewow_result.dataset,
        channel,
        output_dir / f"{stem}_after_dewow.png",
        clip_percentile=clip_percentile,
        cmap=cmap,
    )
    generated["channel00_final"] = save_channel_bscan(
        final_dataset, channel, output_dir / f"{stem}_final.png", clip_percentile=clip_percentile, cmap=cmap
    )

    removed_dewow_dataset = replace(dataset, amplitudes=dewow_result.removed_component)
    generated["channel00_removed_dewow"] = save_channel_bscan(
        removed_dewow_dataset,
        channel,
        output_dir / f"{stem}_removed_dewow.png",
        clip_percentile=clip_percentile,
        cmap=cmap,
    )

    removed_bandpass_dataset = replace(dewow_result.dataset, amplitudes=bandpass_result.removed_component)
    generated["channel00_removed_bandpass"] = save_channel_bscan(
        removed_bandpass_dataset,
        channel,
        output_dir / f"{stem}_removed_bandpass.png",
        clip_percentile=clip_percentile,
        cmap=cmap,
    )

    generated["all_channels_final"] = save_all_channels_bscan(
        final_dataset, output_dir / "all_channels_final.png", clip_percentile=clip_percentile, cmap=cmap
    )

    generated["spectrum_before_after"] = save_spectrum_comparison(
        dataset,
        final_dataset,
        output_dir / "spectrum_before_after.png",
        valid_mask=valid_mask,
        title="Canonical Sprint 3 (D2 + B1) -- amplitude spectrum before vs after (QC only)",
    )

    sampling_time_ns = dataset.metadata["sampling"]["sampling_time_ns"]
    generated["transfer_function"] = save_transfer_function_plot(
        output_dir / "transfer_function.png",
        method=bandpass_method,
        sampling_time_ns=sampling_time_ns,
        lowcut_mhz=lowcut_mhz,
        highcut_mhz=highcut_mhz,
        order=order,
    )

    return {
        "dataset": dataset,
        "valid_mask": valid_mask,
        "dewow_result": dewow_result,
        "bandpass_result": bandpass_result,
        "canonical_parameters": canonical_parameters,
        "phase_verification": phase_verification,
        "generated": generated,
    }


def write_canonical_processing_note(
    result: dict[str, Any],
    raw_file_sha256: str,
    canonical_npz_sha256_before: str,
    output_path: str | Path,
) -> Path:
    """Write ``CANONICAL_PROCESSING_NOTE.md`` documenting the human decision and its scope."""
    dewow_result = result["dewow_result"]
    bandpass_result = result["bandpass_result"]
    phase_verification = result["phase_verification"]

    b1_800_900_note = (
        "B1's wider passband (100-900 MHz) retains substantially more energy in the "
        "800-900 MHz band than B2's narrower 120-800 MHz passband would (see "
        "outputs/sprint03_1/B1_vs_B2_energy_summary.json). This retained energy is "
        "spatially coherent (median adjacent-trace correlation ~0.96 for the "
        "corresponding band in B2's removed component), but that coherence is a QC "
        "signal only -- it is NOT an archaeological target interpretation and does not "
        "by itself confirm the 800-900 MHz content is a real reflection versus a "
        "structured noise source."
    )

    lines = [
        "# Canonical Sprint 3 Processing Note",
        "",
        "## Selection",
        "",
        "The dewow candidate **D2** and the band-pass candidate **B1** were selected "
        "as canonical by **human/geophysical review**, not by this software. This "
        "project never automatically selects a canonical dewow or band-pass "
        "candidate -- see CLAUDE.md, ADR-005, ADR-006.",
        "",
        "Decision references: `outputs/sprint03_1/D2_DEWOW_DECISION.md`, "
        "`outputs/sprint03_1/BANDPASS_FINAL_DECISION_REQUIRED.md`, "
        "`outputs/sprint03_1/B1_vs_B2_energy_summary.json`.",
        "",
        "## D2 selection rationale",
        "",
        "D2 (`running_mean`, requested 8.0 ns -> applied "
        f"{dewow_result.diagnostics['applied_window_ns']:.4g} ns / "
        f"{dewow_result.diagnostics['applied_window_samples']} samples, "
        f"edge_mode=`{dewow_result.diagnostics['edge_mode']}`) passed all 4 measured "
        "conditions in Sprint 3.1: padding unchanged, no phase shift on the direct "
        "wave (robust median-trace lag = 0), its removed component is not a localized "
        "coherent event (a slow, laterally continuous baseline, not a discarded "
        "reflector), and the 20-100 ns region was not fully suppressed. It also sits "
        "between D1's shorter, more signal-eating window and D3's longer, less-"
        "effective window, using the same linear running-mean method as both (unlike "
        "D4's nonlinear running_median).",
        "",
        "## B1 selection rationale",
        "",
        f"B1 (Butterworth, {bandpass_result.diagnostics['lowcut_mhz']}-"
        f"{bandpass_result.diagnostics['highcut_mhz']} MHz, order="
        f"{bandpass_result.diagnostics['order']}, zero_phase="
        f"{bandpass_result.diagnostics['zero_phase']}) was selected as the "
        "**preservation-favoring** candidate over B2 (120-800 MHz): B1 retains more of "
        "the signal's own passband energy, more of the 800-900 MHz band, and shows "
        "higher late-time waveform correlation and spatial coherence in the 20-100 ns "
        "window than B2. This is a documented engineering/geophysical trade-off "
        "towards information preservation over more aggressive noise suppression, not "
        "a claim that B1 is unconditionally superior -- see "
        "`BANDPASS_FINAL_DECISION_REQUIRED.md` for the full multi-criterion comparison.",
        "",
        "## 800-900 MHz energy -- not a target interpretation",
        "",
        b1_800_900_note,
        "",
        "## Dataset-specific scope",
        "",
        DATASET_SCOPE_STATEMENT,
        "",
        "## Verification",
        "",
        f"- Zero-phase confirmed: `confirmed_zero_phase={phase_verification['confirmed_zero_phase']}`, "
        f"max abs median-trace cross-correlation lag = "
        f"{phase_verification['max_abs_median_trace_cross_correlation_lag']}.",
        f"- Raw file SHA-256: `{raw_file_sha256}`",
        f"- Sprint 2 canonical NPZ SHA-256 (input, unchanged by this run): `{canonical_npz_sha256_before}`",
        f"- Software version: `{ARCHAEOGPR_VERSION}`",
        "- Date: 2026-07-15",
        "",
        "## What this note does NOT do",
        "",
        "It does not claim these parameters are canonical for any dataset other than "
        "the one validated here (`Swath003_Array02.ogpr`). It does not interpret any "
        "retained or removed frequency content as an archaeological target. A new "
        "dataset or acquisition setting requires its own dewow/band-pass candidate "
        "comparison and its own human/geophysical review before being treated as "
        "canonical.",
        "",
    ]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
