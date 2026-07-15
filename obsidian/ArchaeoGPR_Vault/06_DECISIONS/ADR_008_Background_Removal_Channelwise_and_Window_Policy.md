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

## Related Files
- `src/archaeogpr/processing/background.py`
- `src/archaeogpr/qc/background.py`
- `src/archaeogpr/export/sprint4a.py`
- `src/archaeogpr/sprint4a_candidates.py`
- `src/archaeogpr/cli.py` (`background`, `sprint4a-candidates` subcommands)
- `configs/background_candidates.yaml`
- `tests/test_background.py`, `tests/test_background_qc.py`,
  `tests/test_sprint4a_pipeline.py`, `tests/test_sprint4a_real_integration.py`
- `outputs/sprint04a/`
- [[05_PROCESSING/Background_Removal]]
- [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]
- [[02_SPRINTS/Sprint_04A_Background_Removal]]
