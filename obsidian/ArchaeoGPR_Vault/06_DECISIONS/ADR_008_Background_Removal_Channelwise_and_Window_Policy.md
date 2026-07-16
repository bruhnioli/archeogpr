---
type: adr
tags: [decision]
id: ADR-008
status: accepted
date: 2026-07-15
---

# ADR-008 — Background Removal: Channel-Wise Computation, Window Policy and No-Canonical-Selection

## Context
Sprint 4A ([[02_SPRINTS/Sprint_04A_Background_Removal]]) implemented four
background-removal methods (`global_mean`, `global_median`,
`sliding_mean`, `sliding_median`) on the canonical Sprint 3 chain
(D2 dewow + B1 band-pass, [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]])
and ran 8 candidates (A1-A8) on the real dataset. This is, by a wide
margin, the most scientifically risky filter this project has
implemented: a moving-average/median estimate along the trace axis
cannot, on its own, distinguish an unwanted common-mode component
(antenna coupling, system ringing, horizontal electronic bias) from a
genuinely long, laterally continuous archaeological reflection (a floor,
a wall foundation, a layer boundary) — both look the same to the
estimator: a slowly-varying-or-constant value across traces at a given
sample position. This ADR records the architectural policy choices this
sprint made to make that risk *visible and measurable* rather than hidden,
and explicitly does **not** select a canonical candidate.

## Decision
1. **Channel-wise, independent computation — channels are never merged
   into one background.** For every channel `c` independently, the
   background at sample `s` is a statistic (mean/median) over that
   channel's own traces only: `background[c, s] = f(amplitudes[:, c, s])`.
   No cross-channel averaging is performed by any of the four methods —
   this keeps antenna-specific coupling/ringing (which can differ per
   channel) from being blended with a neighboring channel's own signal.
2. **Two engineering axes, four methods, no automatic winner.**
   - *Global vs sliding:* `global_mean`/`global_median` estimate one
     background value per sample, shared by the whole profile — maximally
     sensitive to erasing a long horizontal event, because a background
     estimate averaged over the *entire* profile cannot tell a real
     100-trace-long reflection from noise. `sliding_mean`/`sliding_median`
     use a centered, re-estimated-per-trace window — a real event much
     *wider* than the window is still destroyed at its own center (the
     window sees nothing but the target locally and treats it as
     background; verified empirically in `tests/test_background.py` and
     `run_synthetic_risk_experiments()`'s window-length-vs-target-length
     experiment), but an event much *shorter* than the window survives
     well. The practical implication: **the window should be chosen much
     larger than any real feature one wants to preserve** — this is a
     property of the moving-average family itself, not a bug to fix.
   - *Mean vs median:* `median` is more robust to isolated strong-outlier
     traces (verified synthetically: a `global_mean` background estimate
     on a clean trace was measurably biased by 3 strong-outlier traces
     elsewhere in the profile, `global_median` was not) but is a
     nonlinear estimator. **Median is not assumed superior on real data**
     — every median-based candidate's diagnostics carry an explicit
     warning to this effect, and this ADR does not claim otherwise.
   - No combination of these two axes is presented as a canonical
     default; all 8 (2 axes × up to 3 window sizes) are QC candidates
     only.
3. **Trace-spacing is never hardcoded — priority order: geolocation →
   metadata → unavailable.** `compute_trace_spacing()` prefers
   per-channel, outlier-excluded, median-of-medians plan-view geolocation
   distances; falls back to the file's own `metadata.sampling.
   sampling_step_m` only if no geolocation is present; and explicitly
   rejects a `window_m` request (forcing `window_traces` or an explicit
   `trace_spacing_m` override) if neither source is available. On the
   real dataset, the canonical Sprint 3 NPZ carries no geolocation arrays
   (processed NPZs in this project do not currently store them — see
   [[03_ARCHITECTURE/Repository_Map]]), so the real run's source was
   `metadata_sampling_step` (`trace_spacing_m=0.04008848472894169`,
   read from the file's own metadata, not the ~0.0401 m figure quoted
   informally in the spec as context only).
4. **Odd-centered-window policy, always recorded, never silently
   applied.** `window_m / trace_spacing_m` is rounded to the nearest
   integer, then bumped up by one if even (a centered window needs an odd
   trace count). `requested_window_m`, `raw_window_traces_float`, and
   `applied_window_traces`/`applied_window_m` are always recorded
   separately in `diagnostics` — a caller can always see exactly how a
   requested value was converted. An applied window below 3 traces or
   wider than the profile itself is an explicit `ProcessingError`, never
   silently clamped.
5. **Edge policy: `reflect`/`nearest` only, never constant-zero padding.**
   Zero-padding at the profile ends would manufacture an artificial
   amplitude drop exactly where the window starts running out of real
   neighbors — the opposite of what background removal should do at an
   edge. `reflect` (mirrors the profile's own values) and `nearest`
   (repeats the edge trace) were validated with synthetic edge-event
   tests to confirm neither introduces a spurious edge attenuation.
6. **Valid-mask/padding safety exploits this project's own structural
   invariant.** Because `valid_mask` is `(channels, samples)` and — per
   CLAUDE.md — a time-zero shift is channel-wide and constant (never
   per-trace), a given sample position for a channel is either valid for
   *every* trace or for *none*. This means "insufficient valid traces at
   one sample position" (a partial-validity case) structurally cannot
   occur here, simplifying the padding-safety implementation relative to
   dewow/band-pass's per-segment logic. Padding stays byte-identical in
   both the output and the removed component (verified on real data:
   8/8 candidates, `all_channels_padding_untouched=true`).
7. **A new, deliberately non-archaeological "localized event risk" QC
   proxy.** `compute_localized_event_risk()` reports horizontal/vertical
   gradient energy and local curvature of a removed component — never a
   `wall_score`/`target_probability`/classification label. It answers
   "does this removed component look flat and laterally continuous
   (background-like) or local/curved (event-like)", nothing more.
8. **No candidate is ever canonical — enforced at three levels.** (a) no
   function in `sprint4a_candidates.py`/`export/sprint4a.py` ever writes
   a `"canonical": true` value; every `candidate_validation.json` writes
   `"canonical": false` explicitly; (b) `_engineering_category()`'s
   output (`preservation-favoring`/`suppression-favoring`/`balanced`/
   `too_aggressive`/`too_weak`/`inconclusive`) is a transparent, relative
   RMS-retention ranking *within these 8 candidates on this dataset only*
   — documented as non-transferable and never used to auto-eliminate a
   candidate; (c) `BACKGROUND_FINAL_DECISION_REQUIRED.md` opens with
   `Status: review_required` and explicitly states no candidate has been
   selected, contains no `recommended_background_candidate` field, and
   never uses the phrase "best candidate".
9. **Real-data finding: this dataset's removed component is highly
   spatially coherent across all 8 candidates (adjacent-trace correlation
   0.83-1.0), which is exactly the signature that carries real risk to a
   long, laterally continuous reflection regardless of method choice.**
   This is reported transparently via the `Long-horizontal-event
   preservation` proxy column (`max(0, 1 - removed_component_coherence)`,
   near 0 for every candidate here) rather than hidden — see
   `BACKGROUND_FINAL_DECISION_REQUIRED.md`'s explanatory note. This proxy
   is not a direct ground-truth measurement (no known long event exists
   in this real dataset); the direct, known-target version of the same
   risk is the *synthetic* `global_vs_sliding_synthetic_comparison.png`
   experiment.
10. **Dataset-specific QC is required — nothing here transfers
    automatically.** Every number in this ADR and in
    `BACKGROUND_FINAL_DECISION_REQUIRED.md` is specific to
    `Swath003_Array02.ogpr`'s own canonical Sprint 3 chain. A different
    dataset or acquisition setting requires its own 8-candidate run and
    its own human/geophysical decision QC before any window/method choice
    may be treated as informative for it.

## Sprint 4A.1 Correction (2026-07-16)

A self-audit of the original decision QC found three defects that could
mislead a human/geophysical reviewer without changing the underlying
`remove_background()` implementation itself. All three are fixed on PR #1
(`sprint-04a-background-removal`), without introducing a new filter
method and without starting Gain.

1. **Nominal window length is not a physical span.** The original
   `applied_window_m` (`= applied_window_traces * trace_spacing_m`) was
   presented informally as the window's physical extent. It is a
   *nominal length*, not the window's center-to-center span
   (`= (applied_window_traces - 1) * trace_spacing_m`). Both are now
   reported as separate, explicitly named diagnostics fields
   (`applied_window_nominal_length_m`, `applied_window_center_to_center_
   span_m`, `window_half_span_m`); `applied_window_m` is kept only for
   backward compatibility and documented as deprecated/ambiguous. Worked
   example (13 traces, 0.04 m spacing): nominal length 0.52 m,
   center-to-center span 0.48 m, half-span 0.24 m.
2. **Independent per-candidate color scales made visual comparison
   meaningless.** The original decision-panel detail view gave each
   candidate's channel-0 B-scan its own independently computed
   percentile clip -- a candidate that removed nearly everything and one
   that removed nearly nothing could look identically "clean" once each
   is auto-stretched to its own range. `save_common_scale_output_
   comparison()`/`save_common_scale_removed_comparison()` now compute one
   shared symmetric scale per channel row, pooling the canonical input
   and all 8 candidates' outputs (or all 8 removed components) together
   via `compute_shared_clip_limit()` -- no panel is normalized
   independently. `BACKGROUND_DECISION_PANEL.png`/`_DETAIL.png` are kept
   for historical compatibility only and now say so in their own
   captions.
3. **A new, target-isolated synthetic experiment: paired-control
   retention.** The original synthetic risk experiments
   (`run_synthetic_risk_experiments()`) measured a windowed *mixed
   scene* (background + noise + target together) before vs. after
   processing -- informative, but not an isolated measurement of the
   target component alone. `run_paired_control_target_attenuation_
   experiments()` and `compute_paired_control_retention_for_candidates()`
   build a `control` (background + noise only) and a `with_target` run
   from the SAME background+noise realization, process both with the
   identical method/window, and isolate the target-attributable change
   by subtraction (`target_after = processed_with_target -
   processed_control`). Applied to this dataset's own 8 candidates using
   each candidate's own method/window: **every candidate destroys a long
   (55-trace) synthetic target almost completely**
   (`paired_control_long_target_retention` ≈ 0.00006-0.017 across A1-A8)
   even though several candidates show high `overall_rms_retention_
   tendency` (0.62-0.77) -- RMS retention alone would have hidden this.
4. **`1 - removed_component_coherence` is not a preservation fraction.**
   The original `long_horizontal_event_preservation` proxy inverted the
   removed component's own adjacent-trace coherence and presented it as a
   preservation percentage. It is removed from the human-decision table.
   `removed_coherent_event_risk_proxy` now reports the raw coherence
   value directly, with an explicit caveat: a high value means the
   removed component is spatially continuous, which does NOT determine
   whether that continuity reflects unwanted common-mode background or a
   real, laterally continuous reflection, and is not an archaeological
   claim of any kind. The direct, target-isolated version of this same
   risk is now the paired-control long-target retention above, not an
   inverted coherence value.
5. **Engineering interpretation states its own basis and flags
   conflicts.** The RMS-based category label (`preservation-favoring`/
   `suppression-favoring`/`balanced`/`too_aggressive`/`too_weak`) is
   unchanged in mechanism, but is now always reported alongside the
   literal metric it is based on (`overall_rms_retention_tendency`) and
   six other metrics reported separately (`paired_control_short_target_
   retention`, `paired_control_long_target_retention`, `local_event_
   amplitude_retention`, `removed_coherent_event_risk_proxy`,
   `background_suppression`, `waveform_correlation`, `spectral_
   retention`). `_engineering_interpretation_notes()` flags an explicit
   `CONFLICT` when a candidate ranked "preservation-favoring" by RMS
   alone still strongly attenuates the paired-control long target
   (threshold `< 0.3`, documented, not a physical claim) -- on this
   dataset, A1 and A2 both trigger this conflict.

## Sprint 4A.2 Correction (2026-07-16)

A second self-audit (of Sprint 4A.1's own paired-control experiment) found
that the `localized_hyperbola` scenario's synthetic target was, in
practice, indistinguishable from a flat (rectangular) event -- not a
scientific finding, a synthetic-data-generation bug. Fixed on the same PR
(`sprint-04a-background-removal`), without introducing a new filter
method, without changing `remove_background()` itself, and without
starting Gain.

1. **The `localized_hyperbola` target was not actually curved.**
   `_paired_control_profile()`'s hyperbola branch used a *fixed*
   `curvature=0.03` with `target_length_traces=9` (max offset from the
   apex = 4 traces): `depth_shift = round(0.03 * 4**2) = round(0.48) = 0`
   for every trace -- the "hyperbola" was, in every real sense, a flat
   9-trace rectangle. `curvature` is now derived from a requested maximum
   shift and the target's own half-length instead of a fixed constant:
   `curvature = requested_max_shift_samples / max_offset_traces**2`
   (default `requested_max_shift_samples=12.0`, `target_length_traces=15`
   → `max_offset_traces=7` → `curvature≈0.2449`). On the real dataset this
   produces 7 distinct center-sample values across the 15 target traces
   (depth shifts `0,0,1,2,4,6,9,12` by offset), a 12-sample apex-to-arm
   shift, and an apex that is always the shallowest (minimum) center
   sample -- comfortably satisfying every one of the Sprint 4A.2 numeric
   requirements (≥5 target traces, ≥3 distinct center samples, ≥3-5 sample
   apex-to-arm shift).
2. **Retention metrics now use the target's REAL support, not a fixed
   apex-centered window.** The old `_paired_control_retention_metrics()`
   sliced every target shape with the same fixed `target_sample±4` sample
   window -- for a genuinely curved hyperbola, this misses the arms
   entirely (they are shifted up to 12 samples away). `_paired_control_
   profile()` now also returns a real boolean `target_mask` (`(slices,
   samples)`, True exactly where the target's own Hanning-tapered
   contribution is nonzero -- a Hanning taper's own endpoints are exactly
   0.0, so the mask covers every nonzero `target_before` position with no
   false positives), `target_trace_bounds`, `target_sample_bounds`, and
   `target_center_sample_by_trace`. Retention is now computed over this
   real mask for the FULL target support, and separately for the apex
   (the target trace with the minimum/shallowest center sample) and the
   arms (every other target trace): `full_target_peak_retention`,
   `full_target_mean_absolute_retention`, `full_target_energy_retention`,
   `full_target_waveform_correlation`, `apex_retention`, `arm_retention`,
   `edge_trace_retention`, `interior_target_retention`. Rectangular
   targets use this exact same mask-based code path (their "apex"
   degenerates to an arbitrary first target trace, since every rect trace
   shares one center sample -- a documented degenerate case, not a
   separate implementation).
3. **A new validation figure,
   `PAIRED_CONTROL_HYPERBOLA_VALIDATION.png`.** Panels: the known
   `target_before` component; processed `target_after` for `sliding_mean`
   and for `sliding_median` (both against the SAME profile draw, so they
   are directly comparable); the real `target_mask`; the per-trace
   center-sample trajectory (with the apex marked); and apex-vs-arm
   retention bars for both methods. The title states the actual target
   trace count, unique center-sample count, realized max shift, and
   comparison window length -- the figure is itself the evidence that the
   fix produced a genuinely curved target.
4. **A0 (no background removal) -- a decision/QC-layer reference policy,
   not a ninth filter candidate.** `_a0_reference_policy_metrics()`
   returns fixed, definitional values (`overall_rms_retention_tendency`,
   `waveform_correlation`, `spectral_retention`, `local_event_amplitude_
   retention`, `paired_control_short_target_retention`, `paired_control_
   long_target_retention` all `= 1.0`; `background_suppression = 0`;
   `removed_coherent_event_risk_proxy = not_applicable`; `padding_safety
   = unchanged`; `timing_preservation = "0 sample lag"`; `processing_
   applied = False`) -- never measured, never a `ProcessingResult`, never
   written to an NPZ. A0 appears ONLY in `BACKGROUND_FINAL_DECISION_
   REQUIRED.md` (as the first row), `BACKGROUND_METRICS_SUMMARY.png`
   (a gray reference bar in 7 of its 8 panels, separated from A1-A8 by a
   dotted line; excluded from the `removed_coherent_event_risk_proxy`
   panel, since A0 has no real removed component), and `candidate_
   metrics.csv`. It is structurally excluded from `save_common_scale_
   output_comparison()`/`_removed_comparison()` (both iterate
   `candidates_info` only, which A0 never enters) and from `run_
   background_candidates()` (config-driven from `configs/background_
   candidates.yaml`, which defines A1-A8 only). Every "preservation-
   favoring" candidate's `Engineering interpretation` text now also
   states its own comparison against A0's fixed retention of 1.0
   explicitly -- making clear that "preservation-favoring" is a RELATIVE
   ranking among A1-A8 only, never a claim of preserving more of a target
   than doing nothing at all.
5. **The final decision report gains an A0 row and explicit disclaimers.**
   `BACKGROUND_FINAL_DECISION_REQUIRED.md` now opens with: "A0 is the
   no-background-removal reference.", "A0 is not a new filter method.",
   a (data-checked, not hardcoded) statement that all A1-A8 candidates
   strongly attenuate the paired-control long target on this dataset,
   "High overall RMS retention does not imply long-target preservation.",
   "Human reviewer may select \"no background removal\".", "No canonical
   decision is made automatically.", and "Gain has not started." -- in
   addition to the disclaimers already present since Sprint 4A.1.

**This is a correction to the same architectural decision (channel-wise
computation, four methods, no automatic canonical selection), not a new
one -- it does not change which methods exist, does not add a ninth real
filter, and does not resolve the canonical-selection question this ADR
already leaves open.**

## Alternatives Considered
- **Cross-channel background estimation (one shared background across all
  11 channels):** Rejected — explicitly forbidden by the Sprint 4A spec
  and scientifically unjustified here: different channels can have
  different antenna coupling/ringing characteristics, so merging them
  would blend channel-specific noise with channel-specific (possibly
  real) signal.
- **PCA/SVD/eigenimage/robust-PCA, frequency-domain, or polynomial
  trace-background models:** Rejected for this sprint — explicitly out of
  scope (see [[02_SPRINTS/Sprint_04A_Background_Removal]]); these are
  different algorithm families with their own risk profiles that would
  need their own dedicated candidate comparison, not a drop-in
  replacement for the four methods implemented here.
- **Automatically selecting the "best" candidate by an engineering
  score:** Rejected — automatic canonical selection of a background-
  removal candidate is prohibited by CLAUDE.md, and this filter's central
  risk (erasing a real long reflection) is not something any of the
  measured metrics here can rule out on their own; a human/geophysical
  judgment call is required.
- **Zero-padding at profile edges (matching a naive default):** Rejected
  — would manufacture an artificial amplitude drop at the profile ends;
  `reflect`/`nearest` were chosen instead and validated with synthetic
  edge tests.
- **Hardcoding the ~0.0401 m trace spacing quoted informally as
  context:** Rejected — `compute_trace_spacing()` always derives spacing
  from the dataset itself (geolocation or metadata), consistent with
  CLAUDE.md's "never hardcode" principle; the real run's value
  (0.04008848472894169 m) came from the file's own metadata, not a
  literal constant in the code.

## Consequences
- Sprint 4A ([[02_SPRINTS/Sprint_04A_Background_Removal]]) ends in
  `review_required` — this is the expected, correct end state, not an
  incomplete task. The next action is the user's own explicit
  human/geophysical review, not an automatic continuation to Gain.
- `outputs/sprint04a/` now exists as historical QC evidence (8 candidate
  folders + comparison + decision panel/report), alongside — never
  replacing — the canonical Sprint 3 output
  (`outputs/sprint03/canonical_D2_B1/`), which is unmodified.
- Any future Sprint (4B or otherwise) that wants to apply Gain must first
  either (a) receive the user's own explicit canonical background-removal
  selection from this sprint's 8 candidates, or (b) receive the user's
  own explicit instruction to proceed with an un-background-removed
  input — this ADR does not resolve that question, only documents the
  candidates and their trade-offs.
- A future dataset requires its own Sprint-4A-style 8-candidate run and
  its own decision QC before any window/method choice from this ADR may
  be treated as informative for it — none of the numeric values here are
  assumed to transfer.

## Validation
- `remove_background()` verified on real data: `input = output +
  removed_component` holds within float32 round-trip precision
  (`rtol=1e-4, atol=0.05` on amplitudes in the tens of thousands — see
  `tests/test_sprint4a_real_integration.py`); padding stays byte-identical
  in both output and removed component (8/8 candidates); the input
  dataset object is never mutated; `time_ns`/`valid_mask` unchanged;
  processing history is exactly `[time_zero_correction,
  dc_offset_correction, dewow_correction, bandpass_correction,
  background_removal]`.
- Trace-spacing source on the real dataset: `metadata_sampling_step`,
  `trace_spacing_m=0.04008848472894169` — confirmed geolocation is absent
  from the canonical Sprint 3 NPZ, confirmed the fallback path (not the
  geolocation path) was exercised.
- Applied windows on real data: A3/A6 (`window_m=0.5`) → 13 traces
  (0.5212 m); A4/A7 (`window_m=1.0`) → 25 traces (1.002 m); A5/A8
  (`window_m=1.5`) → 37 traces (1.483 m) — all odd, all recorded with
  both requested and applied values.
- Synthetic window-length-vs-target-length experiment confirmed the
  stated risk directly: a target much shorter than the sliding window
  retains most of its energy; a target much wider than the window is
  nearly fully destroyed at its own center — this corrected an initial,
  backwards assumption in `tests/test_background.py` during development
  (see [[02_SPRINTS/Sprint_04A_Background_Removal]] Issues Discovered).
- Synthetic mean-vs-median-under-outliers experiment confirmed
  `global_median`'s background estimate on a clean trace is measurably
  less biased than `global_mean`'s under 3 strong-outlier traces
  elsewhere in the same synthetic profile.
- Real-data removed-component coherence (adjacent-trace correlation,
  W5): A1=1.0, A2=1.0, A3=0.9965, A4=0.9988, A5=0.9995, A6=0.9919,
  A7=0.9971, A8=0.9984 — all high, confirming finding #9 above.
- Engineering categories (RMS-retention ranking, W5, this dataset only):
  A1/A2=preservation-favoring, A3/A6=suppression-favoring,
  A4/A5/A7/A8=balanced.
- `candidate_validation.json` confirmed for all 8 candidates:
  `"canonical": false`, `"gain_applied": false`,
  `"padding_untouched": true`, `"removed_component_zero_at_padding":
  true`, `"no_nan_or_inf": true`, `"shape_matches_input": true`.
- Raw `.ogpr` hash (`66d840c3...b62a6`), Sprint 2 canonical hash
  (`b2770b5c...af5afe`), and Sprint 3 canonical hash
  (`2044dd8f...82fd026`) all unchanged before/after the full 8-candidate
  run.
- 60 new tests (`tests/test_background.py` 44, `tests/test_background_
  qc.py` 11, `tests/test_sprint4a_pipeline.py` 3, `tests/
  test_sprint4a_real_integration.py` 2), existing 254 tests unaffected —
  314/314 passed. `ruff format`/`ruff check`/`mypy src` clean.
- A self-found spec-completeness audit (comparing the literal Sprint 4A
  spec sections 15/16/20 against the first implementation) surfaced and
  fixed three gaps — `removed_input_absolute_energy_ratio`, spatial
  concentration, and three missing `BACKGROUND_FINAL_DECISION_REQUIRED.md`
  table columns; see [[02_SPRINTS/Sprint_04A_Background_Removal]] Issues
  Discovered for the full list and fix.

### Sprint 4A.1 validation (2026-07-16)
- Worked example confirmed exactly: 13 traces, 0.04 m spacing → nominal
  length 0.52 m, center-to-center span 0.48 m, half-span 0.24 m
  (`tests/test_background.py::
  test_nominal_length_and_center_to_center_span_are_distinct_and_correct`).
- Common-scale montages confirmed via a `Figure.savefig` spy: every panel
  in one channel row (input + A1-A8, or A1-A8 removed components) shares
  exactly one `(vmin, vmax)` even when one candidate's amplitude is
  deliberately scaled 50x larger or 1000x smaller than the others —
  proving no panel is normalized independently
  (`tests/test_sprint4a_candidates.py`, 4 tests).
- Paired-control isolation confirmed directly: with `target_amplitude=0`,
  `with_target` equals `control` exactly, and retention metrics are
  guarded to `nan` rather than fabricated; outside the target's own
  traces, `with_target - control` is exactly zero (background+noise
  cancel exactly by construction).
- Window-length/target-length sensitivity confirmed on real paired-control
  data: a target longer than the sliding window retains measurably less
  energy than a target shorter than the window (both `sliding_mean` and
  `sliding_median`); a localized hyperbola-like target is preserved
  measurably better than a long horizontal target within the same method.
- On the real dataset's own 8 candidates: `paired_control_long_target_
  retention` = A1 0.00967, A2 0.0000676, A3 0.0172, A4 0.0134, A5 0.0101,
  A6 0.000131, A7 0.000119, A8 0.0000844 — every candidate destroys the
  synthetic long target almost completely, regardless of
  `overall_rms_retention_tendency` (0.62-0.77 across all 8). A1 and A2
  (both "preservation-favoring" by RMS alone) both trigger the explicit
  `CONFLICT` flag in `Engineering interpretation`.
- `BACKGROUND_FINAL_DECISION_REQUIRED.md` confirmed to no longer contain
  `Long-horizontal-event preservation`, `Localized-event preservation`,
  or `1 - removed_component_coherence`; confirmed to contain all 18
  required columns and the five required disclaimer lines.
- 14 new tests (`tests/test_background.py` +1, new `tests/
  test_sprint4a_candidates.py` +13), existing 314 tests unaffected —
  328/328 passed. `ruff format`/`ruff check`/`mypy src` clean. Real CLI
  re-run confirmed all three hashes (raw `.ogpr`, Sprint 2 canonical,
  Sprint 3 canonical) unchanged.

### Sprint 4A.2 validation (2026-07-16)
- Fixed hyperbola profile confirmed directly: 15 target traces, 7 unique
  center-sample values (`[100, 101, 102, 104, 106, 109, 112]`), realized
  max shift 12 samples, apex trace centered at sample 100 (the shallowest)
  -- comfortably exceeding every numeric threshold in the spec.
- `target_mask` confirmed to exactly match `target_before`'s nonzero
  support: no nonzero value outside the mask, no false positives inside
  it (`tests/test_sprint4a_candidates.py::
  test_target_mask_exactly_matches_nonzero_target_before`).
- `full_target_energy_retention` confirmed to differ from what the retired
  fixed apex-only window would have produced
  (`test_full_target_metric_no_longer_uses_a_fixed_apex_window`); apex and
  arm retention confirmed as separate, genuinely different numbers on the
  real pipeline (`sliding_mean`: apex=0.603, arm=0.701; `sliding_median`:
  apex=0.795, arm=0.869).
- On the real dataset: A1/A2 (`preservation-favoring`) both now carry an
  explicit textual comparison against A0's fixed retention of 1.0 in
  `candidate_metrics.csv`'s `engineering_interpretation` column, in
  addition to the existing `CONFLICT` flag; A0's own row appears first in
  `BACKGROUND_FINAL_DECISION_REQUIRED.md` and in `candidate_metrics.csv`,
  with `background_suppression=0`,
  `overall_rms_retention_tendency=1`, `paired_control_short_target_
  retention=1`, `paired_control_long_target_retention=1`.
- `BACKGROUND_METRICS_SUMMARY.png` confirmed to show A0 as a gray
  reference bar (separated by a dotted line) in 7 of its 8 panels, and
  confirmed ABSENT from the `removed_coherent_event_risk_proxy` panel.
- Confirmed A0 never produces a file whose name contains "A0" anywhere
  under the comparison output tree, and never enters `candidates_info`
  (`test_a0_never_produces_a_processing_result_or_npz_or_bscan_panel`);
  confirmed `archaeogpr.processing.gain` does not exist as an importable
  module (`test_gain_module_does_not_exist_and_report_confirms_gain_not_
  started`).
- 16 new tests in `tests/test_sprint4a_candidates.py`, existing 328 tests
  unaffected -- 344/344 passed. `ruff format`/`ruff check`/`mypy src`
  clean. Real CLI re-run confirmed all three hashes (raw `.ogpr`, Sprint 2
  canonical, Sprint 3 canonical) unchanged.

## Related Files
- `src/archaeogpr/processing/background.py`
- `src/archaeogpr/qc/background.py`
- `src/archaeogpr/export/sprint4a.py`
- `src/archaeogpr/sprint4a_candidates.py` (Sprint 4A.1: common-scale
  montages, paired-control experiment, engineering interpretation,
  corrected final decision report; Sprint 4A.2: fixed hyperbola profile,
  mask-based retention metrics, A0 reference policy)
- `src/archaeogpr/cli.py` (`background`, `sprint4a-candidates` subcommands)
- `configs/background_candidates.yaml`
- `tests/test_sprint4a_candidates.py` (Sprint 4A.1 + 4A.2)
- `tests/test_background.py`, `tests/test_background_qc.py`,
  `tests/test_sprint4a_pipeline.py`, `tests/test_sprint4a_real_integration.py`
- `outputs/sprint04a/`
- [[05_PROCESSING/Background_Removal]]
- [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]
- [[02_SPRINTS/Sprint_04A_Background_Removal]]
