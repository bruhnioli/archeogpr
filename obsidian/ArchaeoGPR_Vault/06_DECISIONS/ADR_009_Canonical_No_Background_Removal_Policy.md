---
type: adr
tags: [decision]
id: ADR-009
status: accepted
date: 2026-07-16
---

# ADR-009 — Canonical No-Background-Removal Policy (A0)

## Context

Sprint 4A ([[02_SPRINTS/Sprint_04A_Background_Removal]]) implemented four
background-removal methods and ran 8 candidates (A1-A8) on the canonical
Sprint 3 chain (D2 dewow + B1 band-pass,
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]). Sprint 4A.1 added
common-scale B-scan montages and a paired-control synthetic target-
retention experiment; Sprint 4A.2 fixed a bug in that same experiment
(the `localized_hyperbola` scenario was, in practice, a flat event) and
added **A0** (no background removal) as an explicit, fixed-value
reference row in the decision table, metrics summary panel, and
`candidate_metrics.csv` — never a ninth filter candidate. ADR-008 records
the architectural policy (channel-wise computation, four methods, no
automatic canonical selection) that made this evidence possible, but
deliberately left the canonical-selection question open for human/
geophysical review. This ADR records that human decision and closes
Sprint 4A.

## Decision

**Canonical background-removal policy: A0 (`no_background_removal`).**

1. None of A1-A8 is selected canonical.
2. Background removal is **not applied** to the canonical Sprint 3
   (D2+B1) output.
3. The canonical processing chain remains exactly:
   `time_zero_correction → dc_offset_correction → dewow_correction (D2)
   → bandpass_correction (B1)`.
4. No new canonical NPZ is produced for background removal. The
   canonical Sprint 3 NPZ (`outputs/sprint03/canonical_D2_B1/
   sprint03_processed.npz`) remains the canonical artifact, unmodified.
5. A0 produces no `ProcessingResult`, no `removed_component`, and no
   NPZ — by design (Sprint 4A.2), it is a decision-layer reference
   policy, not a filter, and this decision does not change that.
6. A1-A8 remain in the repository as experimental, opt-in tools (the
   `background`/`sprint4a-candidates` CLI subcommands and
   `configs/background_candidates.yaml`) — not deleted, not removed from
   the codebase, simply not selected as canonical. A future sprint may
   re-evaluate them against a different dataset or a different candidate
   set without needing to reintroduce anything.
7. Gain has not started, and this decision does not authorize starting
   it. Selecting "no background removal" is not equivalent to "ready for
   Gain" — that remains a separate, future decision requiring its own
   explicit human instruction.

## Rationale (human/geophysical review findings)

1. On the common-scale output B-scans
   (`BACKGROUND_OUTPUT_COMPARISON_CH00_CH05_CH10.png`), A1/A2 (global
   mean/median) are the candidates visually closest to the input.
   However, their own paired-control long-target retention is
   `paired_control_long_target_retention` ≈ **0.009675** (A1) and
   **0.00006764** (A2) — both candidates that look "safest" on the
   common-scale montage in fact destroy a long synthetic target almost
   completely. Visual closeness to the input is not evidence of target
   preservation.
2. The removed-component B-scans of A3-A8
   (`BACKGROUND_REMOVED_COMPARISON_CH00_CH05_CH10.png`) do not show a
   purely horizontal, common-mode response — they contain sloped/local/
   reflection-like structure as well. A sliding window removing more
   than flat common-mode content is itself evidence against treating any
   sliding candidate as a safe, surgical common-mode-only filter.
3. Across all 8 candidates, `paired_control_long_target_retention` is
   far below the documented conflict threshold of 0.3 — the real values
   range from **0.0000676** (A2) to **0.0172** (A3). Every candidate,
   across both engineering axes (global/sliding, mean/median) and all
   three tested window sizes, destroys a long synthetic target almost
   completely.
4. `removed_coherent_event_risk_proxy` is **≈0.99–1.00** for every
   candidate (A1=1.0, A2=0.99999999..., A3=0.9965, A4=0.9988, A5=0.9995,
   A6=0.9919, A7=0.9971, A8=0.9984) — the removed component is highly
   spatially continuous in every case. This does not by itself prove the
   removed content is a real reflection rather than noise, but it means
   the risk signal cannot be used to clear any candidate either: high
   coherence is consistent with both "background successfully isolated"
   and "a real continuous reflection was removed," and this dataset gives
   no way to distinguish the two from the removed component alone.
5. Background removal (any of the four methods) cannot distinguish an
   unwanted common-mode component from a genuinely long, laterally
   continuous archaeological event — a floor, a wall foundation, a layer
   boundary, or any reflection running parallel to the survey profile.
   This is the filter family's own structural limitation (see ADR-008
   Context), not something a different window size or a different
   candidate among A1-A8 could resolve.
6. Background removal is an irreversible operation on the canonical
   chain (the removed content cannot be recovered from the output
   alone). Given points 1-5 above, a preservation-first policy excludes
   it from the canonical chain for this dataset: **the risk of silently
   erasing a real long/horizontal archaeological event outweighs the
   benefit of suppressing a common-mode component that current evidence
   cannot cleanly separate from that risk.**
7. A0 is not a filter — it is the policy of not applying one. Recording
   it explicitly (rather than leaving "no background removal" as an
   unstated default) makes the decision visible, dated, and reviewable,
   consistent with this project's decision-QC discipline (ADR-007,
   ADR-008).

## Alternatives Considered

- **Selecting A1 or A2 as canonical** (highest `overall_rms_retention_
  tendency`, 0.772/0.774, and the closest visual match to the input):
  Rejected. Their own paired-control long-target retention is the LOWEST
  of all 8 candidates (0.009675/0.00006764) — the metric that looks most
  reassuring (RMS retention) is exactly the one Sprint 4A.1 demonstrated
  is not equivalent to archaeological-target preservation. Selecting
  either would contradict the project's own documented finding.
- **Selecting a sliding-window candidate (A3-A8)**: Rejected. Their
  removed-component B-scans show non-horizontal, reflection-like
  structure in addition to common-mode content, and their own paired-
  control long-target retention (0.0000844-0.0172) is no better than
  A1/A2's.
- **Selecting the "least bad" candidate by paired-control long-target
  retention alone** (e.g. A3 at 0.0172, the highest of the 8): Rejected —
  0.0172 retention is still a near-total loss of a long target; treating
  "least destructive among 8 destructive candidates" as "acceptable" would
  misrepresent the actual risk.
- **Deferring the decision, running additional candidates or window
  sizes**: Rejected. The paired-control evidence spans both engineering
  axes (global/sliding, mean/median) and three window sizes (0.5/1.0/1.5
  m) — the limitation is structural to the background-removal method
  family on this dataset, not a parameter-tuning problem an additional
  candidate would resolve (see ADR-008 Context and Decision item 2).
- **Applying Gain directly to the un-background-removed canonical
  chain as part of this same decision**: Rejected — out of scope for
  this ADR. Gain requires its own explicit human instruction and has not
  been requested; this decision only closes the background-removal
  question.

## Consequences

- Sprint 4A ([[02_SPRINTS/Sprint_04A_Background_Removal]]) is now
  **done**. Its success criterion was never "select a filter" — it was
  producing enough evidence for a human/geophysical decision, including
  the possibility of choosing none. That decision has now been made.
- [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-012 is **closed**: canonical
  background-removal policy = A0.
- `outputs/sprint04a/` (8 candidate folders + comparison + decision
  panel/report) remains in the repository as historical QC evidence —
  it is not deleted and not superseded by a new canonical output, because
  no new canonical output for background removal exists.
- The canonical processing chain for `Swath003_Array02.ogpr` is
  unchanged from Sprint 3 canonicalization: `outputs/sprint03/
  canonical_D2_B1/sprint03_processed.npz` remains the single canonical
  artifact for this dataset.
- A1-A8 (`src/archaeogpr/processing/background.py::remove_background()`,
  the `background`/`sprint4a-candidates` CLI subcommands,
  `configs/background_candidates.yaml`) remain fully functional,
  experimental, opt-in tools. Nothing about this decision requires or
  implies removing them from the codebase.
- Any future sprint that wants to apply Gain to this dataset now has an
  unambiguous input to start from (the canonical Sprint 3 D2+B1 chain,
  with no background removal) — but Gain itself still requires its own
  explicit human instruction; this ADR does not start it.

## Dataset-Specific Scope

This decision (canonical policy = A0) applies **only** to
`Swath003_Array02.ogpr`'s Sprint 3 D2+B1 canonical chain. A different
dataset, or a different acquisition setting for the same site, requires
its own Sprint-4A-style 8-candidate comparison and its own human/
geophysical decision QC before any of the numeric evidence in this ADR
or in ADR-008 may be treated as informative for it — none of these
values are assumed to transfer.

## Validation

- `pytest` → all tests pass (see [[07_VALIDATION/Test_Results]] for the
  exact count after this closure round).
- Canonical Sprint 3 NPZ hash unchanged before/after this closure round:
  `2044dd8f...82fd026`. Raw `.ogpr` hash unchanged: `66d840c3...b62a6`.
  Sprint 2 canonical NPZ hash unchanged: `b2770b5c...af5afe`.
- No NPZ or `ProcessingResult` exists for A0 (verified in Sprint 4A.2,
  re-confirmed here — see [[02_SPRINTS/Sprint_04A_Background_Removal]]).
- Canonical Sprint 3 NPZ's `processing_history` contains exactly
  `[time_zero_correction, dc_offset_correction, dewow_correction,
  bandpass_correction]` — no `background_removal` entry.
- `archaeogpr.processing.gain` does not exist as an importable module —
  Gain has not started.
- Real-data figures used above (`overall_rms_retention_tendency`,
  `paired_control_long_target_retention`,
  `removed_coherent_event_risk_proxy_w5`) are read directly from
  `outputs/sprint04a/background_candidates/comparison/
  candidate_metrics.csv`, generated by the same `sprint4a-candidates`
  CLI run used throughout Sprint 4A/4A.1/4A.2.

## Related Files

- [[02_SPRINTS/Sprint_04A_Background_Removal]] (status: done)
- [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]]
  (architectural policy this decision closes)
- [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]] (the canonical chain
  this decision leaves unchanged)
- [[01_PROJECT_STATE/03_Open_Issues]] (ISSUE-012, closed by this ADR)
- [[05_PROCESSING/Background_Removal]]
- `src/archaeogpr/sprint4a_candidates.py`
- `outputs/sprint04a/BACKGROUND_FINAL_DECISION_REQUIRED.md`
- `outputs/sprint04a/background_candidates/comparison/candidate_metrics.csv`
- `outputs/sprint03/canonical_D2_B1/` (unchanged canonical chain)
