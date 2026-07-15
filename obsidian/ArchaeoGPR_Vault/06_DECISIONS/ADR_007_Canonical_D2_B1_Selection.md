---
type: adr
tags: [decision]
id: ADR-007
status: accepted
date: 2026-07-15
---

# ADR-007 — Canonical D2 Dewow + B1 Band-Pass Selection

## Context
Sprint 3 ([[02_SPRINTS/Sprint_03_Dewow_Bandpass]]) produced four dewow
candidates (D1-D4) and four band-pass candidates (B1-B4), all deliberately
left non-canonical. Sprint 3.1
([[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]]) built decision-
focused QC on D2 (validated in depth, 4/4 measured conditions passed) and
on B1 vs B2 only (a documented engineering trend towards B1,
preservation-favoring, but no final pick). Both sprints ended in
`review_required` — this project never selects a canonical filter
candidate automatically (`CLAUDE.md`).

The user has now supplied an explicit human/geophysicist decision: **D2**
for dewow and **B1** for band-pass. This ADR records that decision as the
canonical Sprint 3 chain and the software change that encodes it
(`src/archaeogpr/sprint3_canonical.py`, `python -m archaeogpr sprint3`) —
it does not re-derive or re-optimize the choice; it fixes it as named,
reviewable parameters.

## Decision
1. **The canonical Sprint 3 chain is: Sprint 2 canonical
   (`target_sample=16`) → D2 dewow → B1 band-pass.**
   - D2: `method="running_mean"`, `requested_window_ns=8.0` →
     `applied_window_ns=8.125` (65 samples), `edge_mode="reflect"`.
   - B1: `method="butterworth"`, `lowcut_mhz=100.0`, `highcut_mhz=900.0`,
     `order=4`, `zero_phase=True`.
2. **D2 selection rationale:** D2 passed all 4 measured conditions in
   Sprint 3.1 — padding unchanged, no phase shift on the direct wave
   (robust median-trace lag = 0), its removed component is a slow,
   laterally continuous baseline rather than a localized coherent event
   (not a discarded reflector), and the 20-100 ns region was not fully
   suppressed (RMS ratio 0.4801). It also sits between D1's shorter,
   more signal-eating window and D3's longer, less-effective window,
   using the same linear `running_mean` method as both — unlike D4's
   nonlinear `running_median`.
3. **B1 selection rationale:** B1 was selected over B2 as the
   **preservation-favoring** candidate — it retains more of the signal's
   own passband energy, substantially more of the 800-900 MHz band
   (~3.3-3.6x B2, per `outputs/sprint03_1/B1_vs_B2_energy_summary.json`),
   and shows higher late-time (20-100 ns) waveform correlation and
   spatial coherence than B2 (spatial coherence W4: B1=0.9247 vs
   B2=0.9077). This is a documented engineering/geophysical trade-off
   towards information preservation over more aggressive noise
   suppression — not a claim that B1 is unconditionally superior to B2
   in every respect.
4. **Preservation-first policy, explicitly scoped:** choosing B1 over B2
   means accepting more retained energy outside the narrower 120-800 MHz
   band in exchange for not risking removal of real signal. This is a
   deliberate policy choice for this dataset, not a universal rule for
   future datasets or acquisition settings.
5. **800-900 MHz energy has no definitive target interpretation.** B1's
   wider passband retains substantially more energy in the 800-900 MHz
   band than B2 would. That retained energy is spatially coherent
   (median adjacent-trace correlation ~0.96 for the corresponding band in
   B2's removed component), but coherence is a QC signal only — it does
   NOT by itself confirm the 800-900 MHz content is a real archaeological
   reflection versus a structured noise source. No anomaly or
   archaeological interpretation is made here or anywhere in this
   project (`CLAUDE.md`).
6. **This canonical selection is scoped to the validated dataset
   (`Swath003_Array02.ogpr`) only.** A different dataset or acquisition
   setting (different antenna, different sampling interval, different
   site conditions) requires its own dewow/band-pass candidate comparison
   (like Sprint 3) and its own human/geophysical decision QC (like
   Sprint 3.1) before its output may be treated as canonical — the D2/B1
   parameter values themselves are not assumed to transfer.
7. **The canonicalization is a thin, reuse-only wrapper.**
   `run_sprint3_canonical()` (`src/archaeogpr/sprint3_canonical.py`) calls
   `correct_dewow()`/`correct_bandpass()` unchanged, with the D2/B1
   parameters as fixed defaults — no new filtering algorithm was
   introduced. The `sprint3` CLI subcommand detects whether the caller
   overrode any parameter away from the D2/B1 defaults and prints
   `canonical selected: false` plus an explicit warning in that case,
   so the same command remains usable for non-canonical experimentation
   without ever falsely claiming canonicality.
8. **Old candidate-comparison outputs are preserved unchanged.**
   `outputs/sprint03/{dewow_candidates,bandpass_candidates,
   combined_candidates,spectrum}/` and `outputs/sprint03_1/` are not
   deleted or overwritten by canonicalization — the new canonical output
   lives in its own folder, `outputs/sprint03/canonical_D2_B1/`.

## Alternatives Considered
- **Re-deriving D2/B1 from a fresh automatic metric optimization:**
  Rejected — automatic canonical selection is prohibited by `CLAUDE.md`;
  the human/geophysicist decision is accepted as given, not re-computed
  or second-guessed by the software.
- **Selecting B2 (the narrower-band alternative) instead of B1:**
  Rejected by the human decision, in favor of the preservation-first
  trade-off documented above — B2 remains a valid, fully-QC'd alternative
  candidate (`outputs/sprint03/bandpass_candidates/B2_butter_120_800/`,
  `outputs/sprint03_1/bandpass_B1_B2_bscan/`) but is not canonical.
- **Marking the D2/B1 decision only in documentation, without a
  dedicated `sprint3_canonical.py` module/CLI subcommand:** Rejected —
  leaving canonicalization as a manual, undocumented parameter
  combination would make the decision hard to reproduce deterministically
  and easy to silently drift from; a first-class, tested code path keeps
  the canonical chain reproducible and distinguishable from the
  candidate-comparison code path.
- **Overwriting `outputs/sprint03/` in place with the canonical result:**
  Rejected — the candidate comparisons remain valuable QC evidence
  supporting this decision and must stay inspectable; the canonical
  output is additive, in its own subfolder.

## Consequences
- Sprint 3 ([[02_SPRINTS/Sprint_03_Dewow_Bandpass]]) and Sprint 3.1
  ([[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]]) both move to
  `done` — the human review both sprints were waiting on is now recorded.
- ISSUE-010 (dewow window selection) and ISSUE-011 (band-pass range
  selection) are resolved as human/geophysical decisions, not code fixes
  — see [[01_PROJECT_STATE/03_Open_Issues]].
- `outputs/sprint03/canonical_D2_B1/` is now the canonical Sprint 3
  processed output; any future Sprint 4 work (background removal, gain,
  etc.) that needs a Sprint-3-processed input should read from this
  folder, not from any of the D1-D4/B1-B4/C1-C6 candidate folders.
- Sprint 4 is still NOT activated by this decision alone — see
  [[01_PROJECT_STATE/02_Next_Development_Sprint]]; it requires the user's
  own explicit request in addition to this canonical selection.
- A future dataset requires its own Sprint-3-style candidate comparison
  and Sprint-3.1-style decision QC before any canonical parameters can be
  assigned to it — D2/B1 are not assumed to generalize.

## Validation
- `run_sprint3_canonical()` reused `correct_dewow()`/`correct_bandpass()`
  unchanged; confirmed byte-identical output against calling those
  functions directly with the same D2/B1 parameters
  (`tests/test_sprint3_canonical.py::
  test_direct_correct_dewow_correct_bandpass_match_canonical_output`).
- D2 genuinely applied `applied_window_ns=8.125`,
  `applied_window_samples=65`, `edge_mode="reflect"` on the real dataset
  — matches the human decision's own expected values exactly.
- B1 genuinely applied `lowcut_mhz=100.0`, `highcut_mhz=900.0`, `order=4`,
  `zero_phase=True` on the real dataset.
- `processing_history` order on the canonical output is exactly
  `["time_zero_correction", "dc_offset_correction", "dewow_correction",
  "bandpass_correction"]`.
- Zero-phase confirmed on the real dataset:
  `max_abs_median_trace_cross_correlation_lag=0`,
  `confirmed_zero_phase=True`.
- Padding stays exactly zero after every stage
  (`all_channels_padding_untouched=true`,
  `all_channels_removed_component_zero_at_padding=true`).
- Input immutability and hash stability confirmed: the raw `.ogpr` file
  hash (`66d840c3...b62a6`) and the Sprint 2 canonical NPZ hash
  (`b2770b5c...af5afe`) are both unchanged before/after the canonical
  run.
- Determinism confirmed: two independent canonical runs on the same
  input produce byte-identical output amplitudes and identical
  `canonical_parameters.json`/`phase_verification.json` content.
- `canonical_parameters.json` includes an explicit
  `"selection_authority": "human/geophysical review"` field and
  references the Sprint 3.1 decision files
  (`D2_DEWOW_DECISION.md`, `BANDPASS_FINAL_DECISION_REQUIRED.md`,
  `B1_vs_B2_energy_summary.json`).
- The `sprint3` CLI subcommand prints `canonical selected: true` only
  when every parameter matches the D2/B1 defaults exactly, and
  `canonical selected: false` plus an explicit warning otherwise —
  confirmed with both the default invocation and an overridden
  invocation (`tests/test_cli_sprint3_canonical.py`).
- The reused candidate-comparison code path
  (`sprint3_candidates.py::run_dewow_candidates`/`run_bandpass_candidates`)
  was confirmed to never write a `"canonical"` key into its own
  `ProcessingResult.diagnostics`/`GPRDataset.metadata` — canonicalization
  is an entirely separate artifact
  (`tests/test_sprint3_canonical.py::
  test_candidate_outputs_never_marked_canonical`).
- 22 new tests (`tests/test_sprint3_canonical.py`,
  `tests/test_cli_sprint3_canonical.py`), existing 232 tests unaffected —
  254/254 passed. `ruff format`/`ruff check`/`mypy src` clean.
- Real canonical CLI run produced exactly the 15 required files in
  `outputs/sprint03/canonical_D2_B1/`; old candidate folders
  (`outputs/sprint03/{dewow_candidates,bandpass_candidates,
  combined_candidates}/`, 202 files) were confirmed untouched.

## Related Files
- `src/archaeogpr/sprint3_canonical.py`
- `src/archaeogpr/cli.py` (`sprint3` subcommand, `_cmd_sprint3`)
- `tests/test_sprint3_canonical.py`, `tests/test_cli_sprint3_canonical.py`
- `outputs/sprint03/canonical_D2_B1/`
- [[ADR_005_Dewow_Window_and_Edge_Policy]]
- [[ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]]
- [[05_PROCESSING/Dewow]], [[05_PROCESSING/Bandpass_Filter]]
- [[02_SPRINTS/Sprint_03_Dewow_Bandpass]],
  [[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]]
