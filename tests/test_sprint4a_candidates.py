"""Unit tests for the Sprint 4A.1 background-decision-QC correction.

Covers, per the Sprint 4A.1 spec: common-scale B-scan montages (no
per-candidate independent normalization), the paired-control synthetic
target-attenuation experiment (target isolation, window-length/target-
length sensitivity, mean-vs-median divergence), and the corrected final
decision report (no "1 - coherence" preservation framing, no canonical
selection, no Gain).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from matplotlib.figure import Figure

from archaeogpr.processing.background import remove_background
from archaeogpr.qc.background import compute_removed_component_metrics, compute_signal_preservation_metrics
from archaeogpr.sprint4a_candidates import (
    _engineering_category,
    _engineering_interpretation_notes,
    _paired_control_profile,
    _paired_control_retention_metrics,
    compute_paired_control_retention_for_candidates,
    run_paired_control_target_attenuation_experiments,
    save_common_scale_output_comparison,
    save_common_scale_removed_comparison,
    write_background_final_decision_required,
)

SAMPLING_TIME_NS = 0.5


def _build_candidates_info(dataset_factory, *, methods=("global_mean", "global_median")):
    """A small, real (non-mocked) set of candidates -- built the same way run_background_candidates does."""
    slices_count, channels_count, samples_count = 30, 11, 300
    rng = np.random.default_rng(0)
    background = 200.0 * np.sin(np.linspace(0.0, 4 * np.pi, samples_count))
    amplitudes = np.zeros((slices_count, channels_count, samples_count), dtype=np.float32)
    for channel in range(channels_count):
        amplitudes[:, channel, :] = background + rng.normal(0.0, 10.0, size=(slices_count, samples_count))
    ds = dataset_factory(
        amplitudes=amplitudes,
        slices_count=slices_count,
        channels_count=channels_count,
        samples_count=samples_count,
        sampling_time_ns=SAMPLING_TIME_NS,
    )
    valid_mask = np.ones((channels_count, samples_count), dtype=bool)

    candidates_info = []
    for i, method in enumerate(methods):
        kwargs: dict = {"method": method, "valid_mask": valid_mask}
        if method in ("sliding_mean", "sliding_median"):
            kwargs["window_traces"] = 9
            kwargs["edge_mode"] = "reflect"
        result = remove_background(ds, **kwargs)
        signal_preservation = compute_signal_preservation_metrics(ds, result, valid_mask, channels=(0, 5, 10))
        removed_metrics = compute_removed_component_metrics(ds, result, valid_mask, channels=(0, 5, 10))
        candidates_info.append(
            {
                "id": f"A{i + 1}",
                "label": method,
                "method": method,
                "result": result,
                "signal_preservation": signal_preservation,
                "removed_metrics": removed_metrics,
            }
        )
    return ds, candidates_info


def _capture_saved_figure(monkeypatch) -> list[Figure]:
    """Spy on Figure.savefig so a test can inspect axes/images before the production code closes it."""
    captured: list[Figure] = []
    original_savefig = Figure.savefig

    def spy(self, *args, **kwargs):
        captured.append(self)
        return original_savefig(self, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", spy)
    return captured


# ======================================================================
# Common-scale B-scan montages (items 2-5)
# ======================================================================


def test_output_comparison_shares_one_vlimit_per_channel_row(dataset_factory, tmp_path, monkeypatch):
    ds, candidates_info = _build_candidates_info(
        dataset_factory, methods=("global_mean", "global_median", "sliding_mean")
    )
    # Deliberately scale one candidate's output far outside the others' range --
    # if normalization were still per-candidate, this panel would show a
    # different vlim than its neighbors. ``dataset.amplitudes`` is read-only
    # by design (CLAUDE.md), so build a scaled copy via dataclasses.replace.
    scaled_result = candidates_info[-1]["result"]
    scaled_dataset = replace(scaled_result.dataset, amplitudes=scaled_result.dataset.amplitudes * 50.0)
    candidates_info[-1]["result"] = replace(scaled_result, dataset=scaled_dataset)

    captured = _capture_saved_figure(monkeypatch)
    save_common_scale_output_comparison(
        ds, candidates_info, tmp_path / "output_comparison.png", channels=(0,)
    )
    fig = captured[-1]
    clims = [ax.images[0].get_clim() for ax in fig.axes if ax.images]
    assert len(clims) == 1 + len(candidates_info)  # input + every candidate
    assert len(set(clims)) == 1  # every panel in this one channel row shares the SAME (vmin, vmax)


def test_removed_comparison_shares_one_vlimit_per_channel_row(dataset_factory, tmp_path, monkeypatch):
    ds, candidates_info = _build_candidates_info(dataset_factory, methods=("global_mean", "global_median"))
    captured = _capture_saved_figure(monkeypatch)
    save_common_scale_removed_comparison(
        ds, candidates_info, tmp_path / "removed_comparison.png", channels=(0,)
    )
    fig = captured[-1]
    clims = [ax.images[0].get_clim() for ax in fig.axes if ax.images]
    assert len(clims) == len(candidates_info)
    assert len(set(clims)) == 1


def test_output_comparison_produces_exactly_channels_0_5_10_by_default(
    dataset_factory, tmp_path, monkeypatch
):
    ds, candidates_info = _build_candidates_info(dataset_factory, methods=("global_mean", "global_median"))
    captured = _capture_saved_figure(monkeypatch)
    output_path = save_common_scale_output_comparison(ds, candidates_info, tmp_path / "output_comparison.png")
    assert output_path.is_file()
    fig = captured[-1]
    n_cols = 1 + len(candidates_info)
    n_rows_with_images = sum(1 for ax in fig.axes if ax.images) // n_cols
    assert n_rows_with_images == 3  # channels (0, 5, 10)


def test_output_comparison_never_normalizes_a_candidate_independently(dataset_factory, tmp_path, monkeypatch):
    """A candidate whose output is 1000x smaller must NOT get its own independent, auto-scaled panel."""
    ds, candidates_info = _build_candidates_info(
        dataset_factory, methods=("global_mean", "global_median", "sliding_mean")
    )
    small_result = candidates_info[0]["result"]
    small_dataset = replace(small_result.dataset, amplitudes=small_result.dataset.amplitudes * 0.001)
    candidates_info[0]["result"] = replace(small_result, dataset=small_dataset)

    captured = _capture_saved_figure(monkeypatch)
    save_common_scale_output_comparison(ds, candidates_info, tmp_path / "output.png", channels=(0,))
    fig = captured[-1]
    clims = [ax.images[0].get_clim() for ax in fig.axes if ax.images]
    # If A1's tiny-amplitude output were independently normalized, its panel
    # would have a correspondingly tiny (vmin, vmax) -- it must not.
    assert len(set(clims)) == 1


# ======================================================================
# Paired-control target-isolation fundamentals (items 6-7)
# ======================================================================


def test_paired_control_background_and_noise_cancel_outside_target(dataset_factory):
    rng = np.random.default_rng(1)
    control, with_target, target_start, target_end = _paired_control_profile(
        rng, slices_count=41, samples_count=100, target_length_traces=9, target_shape="rect", target_sample=50
    )
    diff = with_target - control
    outside_rows = np.ones(41, dtype=bool)
    outside_rows[target_start:target_end] = False
    # Background + noise are identical between control/with_target by
    # construction -- outside the target's own traces, the difference must
    # be EXACTLY zero (not merely small).
    assert np.all(diff[outside_rows, :] == 0.0)
    assert np.any(diff[target_start:target_end, :] != 0.0)  # the target itself was actually added


def test_paired_control_retention_isolates_only_the_added_target(dataset_factory):
    rng = np.random.default_rng(2)
    # With target_amplitude=0.0, "with_target" is control plus nothing.
    control, with_target, target_start, target_end = _paired_control_profile(
        rng,
        slices_count=41,
        samples_count=100,
        target_length_traces=9,
        target_shape="rect",
        target_sample=50,
        target_amplitude=0.0,
    )
    np.testing.assert_array_equal(with_target, control)
    metrics = _paired_control_retention_metrics(
        control, with_target, "sliding_mean", {"window_traces": 9}, "reflect", target_start, target_end, 50
    )
    # Zero target energy before processing -- retention is guarded to nan,
    # never a crash or a fabricated ratio.
    assert np.isnan(metrics["target_energy_retention"])
    assert np.isnan(metrics["target_mean_absolute_amplitude_retention"])


# ======================================================================
# Window-length / target-length sensitivity (items 8-10)
# ======================================================================


def test_long_target_attenuated_more_than_short_target_in_same_window(tmp_path):
    result = run_paired_control_target_attenuation_experiments(tmp_path)
    rows = result["rows"]
    for method in ("sliding_mean", "sliding_median"):
        short = next(r for r in rows if r["method"] == method and r["scenario"] == "shorter_than_window")
        long_ = next(r for r in rows if r["method"] == method and r["scenario"] == "longer_than_window")
        assert long_["target_energy_retention"] < short["target_energy_retention"]


def test_localized_hyperbola_preserved_better_than_long_horizontal_within_method(tmp_path):
    result = run_paired_control_target_attenuation_experiments(tmp_path)
    rows = result["rows"]
    for method in ("sliding_mean", "sliding_median"):
        hyperbola = next(r for r in rows if r["method"] == method and r["scenario"] == "localized_hyperbola")
        long_horizontal = next(
            r for r in rows if r["method"] == method and r["scenario"] == "longer_than_window"
        )
        assert hyperbola["target_energy_retention"] > long_horizontal["target_energy_retention"]


def test_mean_and_median_paired_control_results_can_diverge(tmp_path):
    result = run_paired_control_target_attenuation_experiments(tmp_path)
    rows = result["rows"]
    mean_row = next(
        r for r in rows if r["method"] == "sliding_mean" and r["scenario"] == "shorter_than_window"
    )
    median_row = next(
        r for r in rows if r["method"] == "sliding_median" and r["scenario"] == "shorter_than_window"
    )
    assert mean_row["target_energy_retention"] != pytest.approx(median_row["target_energy_retention"])


# ======================================================================
# Final decision report correctness (items 11-13)
# ======================================================================


def test_final_decision_report_never_reports_inverted_coherence_as_preservation(dataset_factory, tmp_path):
    _ds, candidates_info = _build_candidates_info(dataset_factory, methods=("global_mean", "global_median"))
    categories = _engineering_category(candidates_info)
    paired_control_by_id = compute_paired_control_retention_for_candidates(candidates_info)
    interpretation_notes = _engineering_interpretation_notes(
        candidates_info, categories, paired_control_by_id
    )

    output_path = write_background_final_decision_required(
        candidates_info, categories, paired_control_by_id, interpretation_notes, tmp_path / "decision.md"
    )
    text = output_path.read_text(encoding="utf-8")

    # The removed Sprint 4A framing must never reappear.
    assert "Long-horizontal-event preservation" not in text
    assert "Localized-event preservation" not in text
    assert "1 - removed_component_coherence" not in text

    # The coherence value reported in the table must be the RAW coherence,
    # not its complement.
    w5 = "W5"
    for info in candidates_info:
        raw_coherence = info["removed_metrics"][w5]["adjacent_trace_correlation_median"]
        assert f"{raw_coherence:.4g}" in text


def test_final_decision_report_never_selects_a_canonical_candidate(dataset_factory, tmp_path):
    _ds, candidates_info = _build_candidates_info(dataset_factory, methods=("global_mean", "global_median"))
    categories = _engineering_category(candidates_info)
    paired_control_by_id = compute_paired_control_retention_for_candidates(candidates_info)
    interpretation_notes = _engineering_interpretation_notes(
        candidates_info, categories, paired_control_by_id
    )

    output_path = write_background_final_decision_required(
        candidates_info, categories, paired_control_by_id, interpretation_notes, tmp_path / "decision.md"
    )
    text = output_path.read_text(encoding="utf-8")
    assert "No background-removal candidate has been selected as canonical." in text
    assert "recommended_background_candidate" not in text
    assert "best candidate" not in text.lower()


def test_final_decision_report_states_gain_not_started(dataset_factory, tmp_path):
    _ds, candidates_info = _build_candidates_info(dataset_factory, methods=("global_mean", "global_median"))
    categories = _engineering_category(candidates_info)
    paired_control_by_id = compute_paired_control_retention_for_candidates(candidates_info)
    interpretation_notes = _engineering_interpretation_notes(
        candidates_info, categories, paired_control_by_id
    )

    output_path = write_background_final_decision_required(
        candidates_info, categories, paired_control_by_id, interpretation_notes, tmp_path / "decision.md"
    )
    text = output_path.read_text(encoding="utf-8")
    assert "Gain has not been started." in text


# ======================================================================
# Engineering interpretation conflict flag
# ======================================================================


def test_interpretation_notes_states_the_metric_basis_and_flags_conflicts(dataset_factory):
    _ds, candidates_info = _build_candidates_info(
        dataset_factory, methods=("global_mean", "global_median", "sliding_mean")
    )
    categories = _engineering_category(candidates_info)
    paired_control_by_id = compute_paired_control_retention_for_candidates(candidates_info)
    notes = _engineering_interpretation_notes(candidates_info, categories, paired_control_by_id)

    for info in candidates_info:
        note = notes[info["id"]]
        assert "overall_rms_retention_tendency" in note
        category = categories[info["id"]]
        long_retention = paired_control_by_id[info["id"]]["paired_control_long_target_retention"]
        if category == "preservation-favoring" and long_retention < 0.3:
            assert "CONFLICT" in note
        else:
            assert "CONFLICT" not in note
