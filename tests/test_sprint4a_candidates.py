"""Unit tests for the Sprint 4A.1/4A.2 background-decision-QC corrections.

Covers, per the Sprint 4A.1 spec: common-scale B-scan montages (no
per-candidate independent normalization), the paired-control synthetic
target-attenuation experiment (target isolation, window-length/target-
length sensitivity, mean-vs-median divergence), and the corrected final
decision report (no "1 - coherence" preservation framing, no canonical
selection, no Gain).

Sprint 4A.2 additionally covers: the fixed (genuinely curved) localized-
hyperbola synthetic target, mask-based (not fixed-window) retention
metrics with separate apex/arm reporting, and the A0 (no background
removal) reference-policy row -- present in the decision table, the
metrics summary panel, and ``candidate_metrics.csv`` only, never as a
``ProcessingResult``/NPZ or in a B-scan montage.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from matplotlib.figure import Figure

from archaeogpr.processing.background import remove_background
from archaeogpr.qc.background import compute_removed_component_metrics, compute_signal_preservation_metrics
from archaeogpr.sprint4a_candidates import (
    _A0_ID,
    _A0_LABEL,
    _a0_reference_policy_metrics,
    _engineering_category,
    _engineering_interpretation_notes,
    _paired_control_profile,
    _paired_control_retention_metrics,
    _wrap_synthetic,
    build_background_comparison,
    compute_paired_control_retention_for_candidates,
    run_paired_control_target_attenuation_experiments,
    save_background_metrics_summary_panel,
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
    profile = _paired_control_profile(
        rng, slices_count=41, samples_count=100, target_length_traces=9, target_shape="rect", target_sample=50
    )
    diff = profile.with_target - profile.control
    target_start, target_end = profile.target_trace_bounds
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
    profile = _paired_control_profile(
        rng,
        slices_count=41,
        samples_count=100,
        target_length_traces=9,
        target_shape="rect",
        target_sample=50,
        target_amplitude=0.0,
    )
    np.testing.assert_array_equal(profile.with_target, profile.control)
    metrics = _paired_control_retention_metrics(profile, "sliding_mean", {"window_traces": 9}, "reflect")
    # Zero target energy before processing -- retention is guarded to nan,
    # never a crash or a fabricated ratio.
    assert np.isnan(metrics["full_target_energy_retention"])
    assert np.isnan(metrics["full_target_mean_absolute_retention"])


# ======================================================================
# Window-length / target-length sensitivity (items 8-10)
# ======================================================================


def test_long_target_attenuated_more_than_short_target_in_same_window(tmp_path):
    result = run_paired_control_target_attenuation_experiments(tmp_path)
    rows = result["rows"]
    for method in ("sliding_mean", "sliding_median"):
        short = next(r for r in rows if r["method"] == method and r["scenario"] == "shorter_than_window")
        long_ = next(r for r in rows if r["method"] == method and r["scenario"] == "longer_than_window")
        assert long_["full_target_energy_retention"] < short["full_target_energy_retention"]


def test_localized_hyperbola_preserved_better_than_long_horizontal_within_method(tmp_path):
    result = run_paired_control_target_attenuation_experiments(tmp_path)
    rows = result["rows"]
    for method in ("sliding_mean", "sliding_median"):
        hyperbola = next(r for r in rows if r["method"] == method and r["scenario"] == "localized_hyperbola")
        long_horizontal = next(
            r for r in rows if r["method"] == method and r["scenario"] == "longer_than_window"
        )
        assert hyperbola["full_target_energy_retention"] > long_horizontal["full_target_energy_retention"]


def test_mean_and_median_paired_control_results_can_diverge(tmp_path):
    result = run_paired_control_target_attenuation_experiments(tmp_path)
    rows = result["rows"]
    mean_row = next(
        r for r in rows if r["method"] == "sliding_mean" and r["scenario"] == "shorter_than_window"
    )
    median_row = next(
        r for r in rows if r["method"] == "sliding_median" and r["scenario"] == "shorter_than_window"
    )
    assert mean_row["full_target_energy_retention"] != pytest.approx(
        median_row["full_target_energy_retention"]
    )


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
    assert "Gain has not started." in text  # Sprint 4A.2's exact required disclaimer wording


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


# ======================================================================
# Sprint 4A.2: fixed (genuinely curved) localized-hyperbola target
# ======================================================================


def _build_hyperbola_profile(seed: int, *, target_length_traces: int = 15, max_shift: float = 12.0):
    rng = np.random.default_rng(seed)
    return _paired_control_profile(
        rng,
        slices_count=61,
        samples_count=200,
        target_length_traces=target_length_traces,
        target_shape="hyperbola",
        target_sample=100,
        requested_max_shift_samples=max_shift,
    )


def test_hyperbola_profile_satisfies_sprint4a2_geometry_requirements():
    profile = _build_hyperbola_profile(3)
    target_start, target_end = profile.target_trace_bounds
    assert target_end - target_start >= 5  # at least 5 traces carry the target

    centers = profile.target_center_sample_by_trace[target_start:target_end]
    assert np.all(centers >= 0)  # every target trace has a real center sample
    unique_centers = {int(c) for c in centers}
    assert len(unique_centers) >= 3  # the sample center genuinely varies across traces

    apex_center = int(centers.min())
    apex_trace_offset = int(np.argmin(centers))
    assert centers[apex_trace_offset] == apex_center  # apex is the shallowest (minimum) sample
    max_arm_shift = int(centers.max() - apex_center)
    assert max_arm_shift >= 3  # arms differ from the apex by at least 3-5 samples


def test_hyperbola_never_exceeds_trace_or_sample_bounds():
    profile = _build_hyperbola_profile(8)
    target_start, target_end = profile.target_trace_bounds
    assert 0 <= target_start < target_end <= profile.control.shape[0]
    sample_lo, sample_hi = profile.target_sample_bounds
    assert 0 <= sample_lo < sample_hi <= profile.control.shape[1]


def test_hyperbola_raises_rather_than_silently_exceeding_sample_bounds():
    rng = np.random.default_rng(4)
    # target_sample=195 plus a 12-sample shift plus the taper's own half-width
    # would push the arm's window past samples_count=200 -- this must raise,
    # never silently clip (CLAUDE.md: no silent clipping of an out-of-bounds
    # shift/parameter).
    with pytest.raises(ValueError):
        _paired_control_profile(
            rng,
            slices_count=61,
            samples_count=200,
            target_length_traces=15,
            target_shape="hyperbola",
            target_sample=195,
            requested_max_shift_samples=12.0,
        )


def test_target_mask_exactly_matches_nonzero_target_before():
    profile = _build_hyperbola_profile(7)
    target_before = profile.with_target - profile.control
    nonzero = target_before != 0.0
    # No false negatives: every nonzero target contribution lies inside the mask.
    assert np.all(profile.target_mask[nonzero])
    # No false positives: outside the mask, the target's own contribution is
    # EXACTLY zero (not merely small) -- this is what makes target_before -
    # target_mask a reliable ground truth for retention metrics.
    assert np.all(target_before[~profile.target_mask] == 0.0)


def test_full_target_metric_no_longer_uses_a_fixed_apex_window():
    """The old Sprint 4A.1 fixed apex_sample+-4 window must not silently reappear as the full metric."""
    profile = _build_hyperbola_profile(42)
    metrics = _paired_control_retention_metrics(profile, "sliding_mean", {"window_traces": 15}, "reflect")

    control_dataset = _wrap_synthetic(profile.control)
    with_target_dataset = _wrap_synthetic(profile.with_target)
    processed_control = remove_background(
        control_dataset, method="sliding_mean", edge_mode="reflect", window_traces=15
    )
    processed_with_target = remove_background(
        with_target_dataset, method="sliding_mean", edge_mode="reflect", window_traces=15
    )
    target_before = profile.with_target - profile.control
    target_after = processed_with_target.dataset.amplitudes[:, 0, :].astype(
        np.float64
    ) - processed_control.dataset.amplitudes[:, 0, :].astype(np.float64)

    target_start, target_end = profile.target_trace_bounds
    lo, hi = 100 - 4, 100 + 5  # the retired Sprint 4A.1 fixed apex-centered window
    fixed_before = target_before[target_start:target_end, lo:hi]
    fixed_after = target_after[target_start:target_end, lo:hi]
    fixed_window_energy_retention = float((fixed_after**2).sum() / (fixed_before**2).sum())

    # The hyperbola's arms sit up to 12 samples away from the apex -- well
    # outside this fixed window -- so a full-target metric that genuinely
    # includes the arms must differ from the fixed-window-only value.
    assert metrics["full_target_energy_retention"] != pytest.approx(fixed_window_energy_retention)


def test_apex_and_arm_retention_are_separate_metrics(tmp_path):
    result = run_paired_control_target_attenuation_experiments(tmp_path)
    hyperbola_rows = [r for r in result["rows"] if r["scenario"] == "localized_hyperbola"]
    assert len(hyperbola_rows) == 2  # sliding_mean, sliding_median
    for row in hyperbola_rows:
        assert "apex_retention" in row
        assert "arm_retention" in row
        # Genuinely distinct measurements, not two names for the same number.
        assert row["apex_retention"] != pytest.approx(row["arm_retention"])


def test_rect_target_uses_the_same_mask_based_retention_infrastructure():
    """Rectangular targets must share the mask-based path, not a separate hyperbola-only one."""
    rng = np.random.default_rng(6)
    profile = _paired_control_profile(
        rng, slices_count=41, samples_count=100, target_length_traces=9, target_shape="rect", target_sample=50
    )
    target_start, target_end = profile.target_trace_bounds
    centers = profile.target_center_sample_by_trace[target_start:target_end]
    assert np.all(centers == centers[0])  # degenerate case: every rect trace shares one center

    metrics = _paired_control_retention_metrics(profile, "sliding_mean", {"window_traces": 9}, "reflect")
    for key in (
        "full_target_peak_retention",
        "full_target_mean_absolute_retention",
        "full_target_energy_retention",
        "full_target_waveform_correlation",
        "apex_retention",
        "arm_retention",
        "edge_trace_retention",
        "interior_target_retention",
    ):
        assert key in metrics
        assert np.isfinite(metrics[key])


# ======================================================================
# Sprint 4A.2: A0 (no background removal) reference policy
# ======================================================================


def test_a0_reference_policy_metrics_are_fixed_at_one_and_zero():
    a0 = _a0_reference_policy_metrics()
    assert a0["overall_rms_retention_tendency"] == 1.0
    assert a0["waveform_correlation"] == 1.0
    assert a0["spectral_retention"] == 1.0
    assert a0["local_event_amplitude_retention"] == 1.0
    assert a0["paired_control_short_target_retention"] == 1.0
    assert a0["paired_control_long_target_retention"] == 1.0
    assert a0["background_suppression"] == 0.0
    assert a0["removed_coherent_event_risk_proxy"] == "not_applicable"
    assert a0["padding_safety"] == "unchanged"
    assert a0["processing_applied"] is False
    assert a0["type"] == "reference_policy"
    assert a0["label"] == _A0_LABEL == "no_background_removal"


def test_a0_row_present_in_final_decision_table(dataset_factory, tmp_path):
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
    assert f"| {_A0_ID} | {_A0_LABEL} |" in text
    assert "A0 is the no-background-removal reference." in text
    assert "A0 is not a new filter method." in text
    assert 'Human reviewer may select "no background removal".' in text
    assert "No canonical decision is made automatically." in text
    assert "Gain has not started." in text


def test_a0_never_produces_a_processing_result_or_npz_or_bscan_panel(dataset_factory, tmp_path, monkeypatch):
    ds, candidates_info = _build_candidates_info(dataset_factory, methods=("global_mean", "global_median"))
    n_before = len(candidates_info)

    # A0 must never enter the B-scan montages -- it has no real dataset.
    captured = _capture_saved_figure(monkeypatch)
    save_common_scale_output_comparison(ds, candidates_info, tmp_path / "output.png", channels=(0,))
    fig = captured[-1]
    titles = [ax.get_title() for ax in fig.axes]
    assert not any(_A0_ID in title for title in titles)

    build_background_comparison(ds, None, candidates_info, tmp_path / "comparison")
    # build_background_comparison must never mutate candidates_info in place
    # to smuggle A0 in as a fake ProcessingResult.
    assert len(candidates_info) == n_before
    assert all(info["id"] != _A0_ID for info in candidates_info)
    # No NPZ or per-candidate directory anywhere in the tree is attributable to A0.
    assert list(tmp_path.rglob(f"*{_A0_ID}*.npz")) == []
    assert not any(_A0_ID in p.name for p in tmp_path.rglob("*") if p.is_dir())

    csv_text = (tmp_path / "comparison" / "candidate_metrics.csv").read_text(encoding="utf-8")
    assert csv_text.splitlines()[1].startswith(f"{_A0_ID},")


def test_a0_appears_in_metrics_summary_panel_but_not_removed_coherence(
    dataset_factory, tmp_path, monkeypatch
):
    _ds, candidates_info = _build_candidates_info(dataset_factory, methods=("global_mean", "global_median"))
    paired_control_by_id = compute_paired_control_retention_for_candidates(candidates_info)

    captured = _capture_saved_figure(monkeypatch)
    save_background_metrics_summary_panel(candidates_info, paired_control_by_id, tmp_path / "summary.png")
    fig = captured[-1]
    titles_to_xticklabels = {
        ax.get_title(): [label.get_text() for label in ax.get_xticklabels()] for ax in fig.axes
    }
    for title, xticklabels in titles_to_xticklabels.items():
        if title == "removed_coherent_event_risk_proxy":
            assert _A0_ID not in xticklabels  # A0 has no real removed component
        else:
            assert _A0_ID in xticklabels


def test_no_candidate_including_a0_is_ever_marked_canonical(dataset_factory, tmp_path):
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
    text_normalized = " ".join(text.split())  # tolerate the source's own line-wrapping
    assert "No background-removal candidate has been selected as canonical." in text
    assert "does not select a canonical background-removal candidate -- including A0" in text_normalized
    assert "recommended_background_candidate" not in text
    assert "best candidate" not in text.lower()


def test_gain_module_does_not_exist_and_report_confirms_gain_not_started(dataset_factory, tmp_path):
    with pytest.raises(ModuleNotFoundError):
        import archaeogpr.processing.gain  # noqa: F401

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
    assert "Gain has not started." in text


def test_preservation_favoring_candidates_are_compared_against_a0(dataset_factory):
    """Every 'preservation-favoring' candidate's note must name A0, conflict or not (spec item 5)."""
    _ds, candidates_info = _build_candidates_info(
        dataset_factory, methods=("global_mean", "global_median", "sliding_mean")
    )
    categories = _engineering_category(candidates_info)
    paired_control_by_id = compute_paired_control_retention_for_candidates(candidates_info)
    notes = _engineering_interpretation_notes(candidates_info, categories, paired_control_by_id)

    for candidate_id, category in categories.items():
        if category == "preservation-favoring":
            assert _A0_ID in notes[candidate_id]
            assert _A0_LABEL in notes[candidate_id]


# ======================================================================
# Sprint 4A Closure (2026-07-16): human decision recorded in ADR-009
# ======================================================================


def test_adr_009_records_the_a0_canonical_decision():
    """ADR-009 (vault) records the human decision: canonical background-removal policy = A0."""
    adr_path = (
        Path(__file__).resolve().parents[1]
        / "obsidian"
        / "ArchaeoGPR_Vault"
        / "06_DECISIONS"
        / "ADR_009_Canonical_No_Background_Removal_Policy.md"
    )
    assert adr_path.is_file()
    text = adr_path.read_text(encoding="utf-8")
    assert "Canonical background-removal policy: A0" in text
    assert "no_background_removal" in text
    assert "None of A1-A8 is selected canonical." in text
    assert "No new canonical NPZ is produced" in text
    assert "Gain has not started" in text
