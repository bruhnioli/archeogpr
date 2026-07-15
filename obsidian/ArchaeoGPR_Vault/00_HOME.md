---
type: home
tags: [project-state]
---

# ArchaeoGPR Knowledge Base

Bu vault, `archaeogpr` Python projesinin (OpenGPR `.ogpr` dosyalarını okuyan,
doğrulayan ve QC çıktıları üreten araç seti) geliştirme bağlamını,
mimari kararlarını ve doğrulama sonuçlarını tutar.

## Current Status
- Current sprint: none active — Sprint 3 ([[02_SPRINTS/Sprint_03_Dewow_Bandpass]]) and Sprint 3.1 ([[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]]) are both **done**. D2 dewow + B1 band-pass were selected as canonical by human/geophysical review — see [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]. Sprint 4 is not yet defined.
- Project status: canonical Sprint 3 chain (Sprint 2 canonical → D2 → B1) implemented, tested, and run for real (`outputs/sprint03/canonical_D2_B1/`, 15 files). All previous Sprint 3/3.1 candidate-comparison outputs (D1-D4, B1-B4, C1-C6, `outputs/sprint03_1/`) remain unchanged and preserved as the QC evidence supporting this decision.
- Last updated: 2026-07-15
- Latest validated dataset: Swath003_Array02 ([[04_DATASETS/Swath003_Array02]])
- Test status: 254/254 pytest passed (232 önceki + 22 yeni canonicalization testi; gerçek dosya entegrasyon testi dahil — skip edilmedi, çünkü `data/raw/Swath003_Array02.ogpr` mevcut)

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
1. Sprint 4'ü tanımlamak/başlatmak için kullanıcının kendi açık isteğini almak (bkz. [[01_PROJECT_STATE/02_Next_Development_Sprint]]) — D2/B1'in canonical seçilmiş olması, tek başına, Sprint 4'ü otomatik olarak açmaz.
2. EPSG:32632 CRS uyuşmazlığını saha ekibiyle doğrulamak (bkz. [[01_PROJECT_STATE/04_Risks_and_Limitations]]).
3. Mean vs median DC offset belirsizliğini (bazı kanallarda işaret değişimi) jeofizik ekibiyle değerlendirmek (bkz. [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-009).

## Critical Warnings
- Raw OGPR files are read-only.
- CRS metadata is not yet validated.
- Depth depends on propagation velocity.
- Automatic time-zero picks are signal-processing references, not calibrated physical surface times — this remains true even for the now-recommended `target_sample=16`.
- D2 dewow + B1 band-pass are canonical **only for `Swath003_Array02.ogpr`** — a different dataset requires its own candidate comparison and its own human/geophysical decision QC before any parameters may be treated as canonical for it.
- The 800-900 MHz energy B1 retains has no definitive archaeological target interpretation — see [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]].
- Processing algorithms beyond time-zero, DC offset, dewow, and band-pass are not implemented yet.

## Latest Outputs
- Sprint 1 (inspect): `outputs/inspect/Swath003_Array02_metadata.json`, `_header.json`, `_geolocation.csv`, `_channel00_bscan.png`, `_survey_geometry.png`
- Sprint 2.2 (canonical, `target_sample=16`): `outputs/sprint02/canonical_target16/sprint02_processed.npz`, `CANONICAL_PROCESSING_NOTE.md`, `relative_time_axis.csv`
- Sprint 2.2 (validation): `outputs/sprint02_2_validation/{target_invariance,dc_window}/`, `VALIDATION_RESULT.md`
- Sprint 3 (aday karşılaştırmaları, tarihsel QC kanıtı — hiçbiri canonical değil): `outputs/sprint03/{dewow_candidates,spectrum,bandpass_candidates,combined_candidates}/`, `SPRINT3_REVIEW_REQUIRED.md`
- Sprint 3.1 (D2 doğrulama + B1/B2 karar QC'si, tarihsel QC kanıtı — hiçbiri canonical değil): `outputs/sprint03_1/`, `DECISION_PANEL_D2_B1_B2.png`, `BANDPASS_FINAL_DECISION_REQUIRED.md`
- **Sprint 3 Canonicalization (canonical, D2+B1):** `outputs/sprint03/canonical_D2_B1/sprint03_processed.npz`, `CANONICAL_PROCESSING_NOTE.md`, `canonical_parameters.json` — bkz. [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]
- Older, superseded (preserved, not deleted): `outputs/sprint02/combined/` (Sprint 2), `outputs/sprint02_review/` (Sprint 2.1)
