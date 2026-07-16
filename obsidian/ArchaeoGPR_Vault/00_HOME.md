---
type: home
tags: [project-state]
---

# ArchaeoGPR Knowledge Base

Bu vault, `archaeogpr` Python projesinin (OpenGPR `.ogpr` dosyalarını okuyan,
doğrulayan ve QC çıktıları üreten araç seti) geliştirme bağlamını,
mimari kararlarını ve doğrulama sonuçlarını tutar.

## Current Status
- Current sprint: Sprint 4A ([[02_SPRINTS/Sprint_04A_Background_Removal]]) — **review_required**. Four background-removal methods implemented, 8 candidates (A1-A8) run on the real canonical Sprint 3 chain (D2+B1). **Sprint 4A.1 correction (2026-07-16, PR #1):** decision-QC fixed (window terminology, common-scale B-scan montages, removed the misleading `1 - coherence` "preservation" framing) and a new paired-control synthetic experiment found that every candidate destroys a long synthetic target almost completely regardless of RMS retention. **Sprint 4A.2 correction (2026-07-16, same PR #1):** fixed a bug in that SAME paired-control experiment (the `localized_hyperbola` scenario was, in practice, a flat event) and added **A0** (no background removal) as an explicit, fixed-value reference row in the decision table/metrics panel/CSV — never a ninth filter candidate. **No candidate (including A0) selected as canonical, Gain not started.** See [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].
- Project status: Sprint 3 ([[02_SPRINTS/Sprint_03_Dewow_Bandpass]]) and Sprint 3.1 ([[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]]) are both **done** — D2 dewow + B1 band-pass canonical (see [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]). Sprint 4A's 8 background-removal candidates (`outputs/sprint04a/`) are historical QC evidence only — hiçbiri canonical değil.
- Last updated: 2026-07-16
- Latest validated dataset: Swath003_Array02 ([[04_DATASETS/Swath003_Array02]])
- Test status: 342/342 pytest passed (328 önceki + 16 yeni Sprint 4A.2 testi; gerçek dosya entegrasyon testi dahil — skip edilmedi, çünkü `data/raw/Swath003_Array02.ogpr` mevcut)

## Navigation
- [[01_PROJECT_STATE/00_Claude_Context]]
- [[01_PROJECT_STATE/01_Current_Project_State]]
- [[01_PROJECT_STATE/02_Next_Development_Sprint]]
- [[01_PROJECT_STATE/03_Open_Issues]]
- [[01_PROJECT_STATE/04_Risks_and_Limitations]]
- [[01_PROJECT_STATE/05_Project_Roadmap]]
- [[03_ARCHITECTURE/Architecture_Overview]]
- [[04_DATASETS/Dataset_Index]]
- [[05_PROCESSING/Processing_Index]]
- [[06_DECISIONS/Decision_Index]]
- [[07_VALIDATION/Validation_Index]]
- [[08_SESSION_LOGS/Session_Index]]
- [[09_REFERENCES/Reference_Index]]

## Current Priorities
1. **Human review of corrected hyperbola QC, A0 baseline, and common-scale real-data montages** (bkz. [[01_PROJECT_STATE/02_Next_Development_Sprint]]) — `BACKGROUND_OUTPUT_COMPARISON_CH00_CH05_CH10.png`, `BACKGROUND_REMOVED_COMPARISON_CH00_CH05_CH10.png`, `BACKGROUND_METRICS_SUMMARY.png`, `PAIRED_CONTROL_HYPERBOLA_VALIDATION.png`, `BACKGROUND_FINAL_DECISION_REQUIRED.md` — 8 background-removal adayından birini veya A0'ı ("hiç background removal yapmama") canonical seçmek. Bu karardan sonra da Gain otomatik olarak BAŞLAMAZ.
2. EPSG:32632 CRS uyuşmazlığını saha ekibiyle doğrulamak (bkz. [[01_PROJECT_STATE/04_Risks_and_Limitations]]).
3. Mean vs median DC offset belirsizliğini (bazı kanallarda işaret değişimi) jeofizik ekibiyle değerlendirmek (bkz. [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-009).

## Critical Warnings
- Raw OGPR files are read-only.
- CRS metadata is not yet validated.
- Depth depends on propagation velocity.
- Automatic time-zero picks are signal-processing references, not calibrated physical surface times — this remains true even for the now-recommended `target_sample=16`.
- D2 dewow + B1 band-pass are canonical **only for `Swath003_Array02.ogpr`** — a different dataset requires its own candidate comparison and its own human/geophysical decision QC before any parameters may be treated as canonical for it.
- The 800-900 MHz energy B1 retains has no definitive archaeological target interpretation — see [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]].
- **Background removal (Sprint 4A) is the most scientifically risky filter implemented so far** — it cannot distinguish a real, long laterally-continuous reflection from common-mode noise. **No candidate is canonical.** See [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].
- Processing algorithms beyond time-zero, DC offset, dewow, band-pass, and background removal (as non-canonical candidates) are not implemented yet — Gain has not been started.

## Latest Outputs
- Sprint 1 (inspect): `outputs/inspect/Swath003_Array02_metadata.json`, `_header.json`, `_geolocation.csv`, `_channel00_bscan.png`, `_survey_geometry.png`
- Sprint 2.2 (canonical, `target_sample=16`): `outputs/sprint02/canonical_target16/sprint02_processed.npz`, `CANONICAL_PROCESSING_NOTE.md`, `relative_time_axis.csv`
- Sprint 2.2 (validation): `outputs/sprint02_2_validation/{target_invariance,dc_window}/`, `VALIDATION_RESULT.md`
- Sprint 3 (aday karşılaştırmaları, tarihsel QC kanıtı — hiçbiri canonical değil): `outputs/sprint03/{dewow_candidates,spectrum,bandpass_candidates,combined_candidates}/`, `SPRINT3_REVIEW_REQUIRED.md`
- Sprint 3.1 (D2 doğrulama + B1/B2 karar QC'si, tarihsel QC kanıtı — hiçbiri canonical değil): `outputs/sprint03_1/`, `DECISION_PANEL_D2_B1_B2.png`, `BANDPASS_FINAL_DECISION_REQUIRED.md`
- **Sprint 3 Canonicalization (canonical, D2+B1):** `outputs/sprint03/canonical_D2_B1/sprint03_processed.npz`, `CANONICAL_PROCESSING_NOTE.md`, `canonical_parameters.json` — bkz. [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]
- Sprint 4A (8 background-removal adayı, tarihsel QC kanıtı — **hiçbiri canonical değil**): `outputs/sprint04a/{background_candidates/{A1_global_mean,...,A8_sliding_median_150m},comparison}/`, `BACKGROUND_FINAL_DECISION_REQUIRED.md` — bkz. [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]]
- **Sprint 4A.1 düzeltmesi (asıl karar dosyaları):** `outputs/sprint04a/BACKGROUND_OUTPUT_COMPARISON_CH00_CH05_CH10.png`, `BACKGROUND_REMOVED_COMPARISON_CH00_CH05_CH10.png`, `BACKGROUND_METRICS_SUMMARY.png` (ortak-scale) — `BACKGROUND_DECISION_PANEL.png`/`_DETAIL.png` tarihsel uyumluluk için korunuyor
- **Sprint 4A.2 düzeltmesi (düzeltilmiş hiperbol QC + A0 referansı):** `outputs/sprint04a/background_candidates/comparison/PAIRED_CONTROL_HYPERBOLA_VALIDATION.png` (yeni), `candidate_metrics.csv` (A0 satırı dahil, 9 satır), `BACKGROUND_METRICS_SUMMARY.png`/`BACKGROUND_FINAL_DECISION_REQUIRED.md` (A0 referans değerleriyle güncellendi) — A0 hiçbir zaman bir B-scan montajında görünmez
- Older, superseded (preserved, not deleted): `outputs/sprint02/combined/` (Sprint 2), `outputs/sprint02_review/` (Sprint 2.1)
