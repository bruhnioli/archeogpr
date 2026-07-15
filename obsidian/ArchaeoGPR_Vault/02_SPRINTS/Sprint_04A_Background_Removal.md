---
type: sprint
tags: [sprint, review]
sprint: 4A
status: review_required
started: 2026-07-15
completed:
---

# Sprint 4A — Background Removal Candidate Development, Signal-Preservation Validation and Geophysical QC

> **İnsan/jeofizik incelemesi bekleniyor.** Bu sprint hiçbir background-
> removal adayını canonical seçmedi ve gain'i başlatmadı. Sonraki adım:
> [[01_PROJECT_STATE/02_Next_Development_Sprint]]'teki `Next action`.

## Goal
Yeni bir arka-plan-çıkarma (background removal) mühendislik kararı
otomatik olarak VERİLMEDİ. Bu sprint, canonical Sprint 3 çıktısı
(`outputs/sprint03/canonical_D2_B1/sprint03_processed.npz`, D2 dewow + B1
band-pass) üzerinde dört farklı background-removal yöntemini (global mean,
global median, sliding mean, sliding median) bilimsel olarak
implemente etmek, çıkarılan bileşeni (removed component) ayrıntılı olarak
incelemek ve karar-odaklı QC çıktıları üretmek amacındadır. **Bu sprintte
hiçbir aday otomatik olarak canonical seçilmedi.**

## Scope
- `src/archaeogpr/processing/background.py` — `remove_background()`:
  `global_mean`, `global_median`, `sliding_mean`, `sliding_median`;
  kanal-bazlı bağımsız hesaplama (kanallar hiçbir zaman birleştirilmez);
  metre→trace penceresi dönüşümü asla sessizce yuvarlanmaz.
- `compute_trace_spacing()` — geolocation → metadata `sampling_step_m` →
  `unavailable` öncelik sırası; asla sabit gömülü ~0.0401 m değeri.
- 8 aday (A1-A8), gerçek canonical Sprint 3 verisi üzerinde çalıştırıldı:
  A1=global_mean, A2=global_median, A3-A5=sliding_mean (0.5/1.0/1.5 m),
  A6-A8=sliding_median (0.5/1.0/1.5 m).
- Sinyal-koruma metrikleri (`compute_signal_preservation_metrics`):
  waveform/median-trace correlation, RMS/absolute-energy/spectral-energy
  retention, peak-sample/zero-crossing displacement, polarity preservation,
  adjacent-trace correlation before/after, local-event amplitude
  retention, channel consistency before/after — hepsi 5 zaman penceresi
  (W1-W5) × kanal 0/5/10 için.
- Çıkarılan-bileşen metrikleri (`compute_removed_component_metrics`):
  RMS/energy/absolute-energy ratio, spatial coherence, spatial
  concentration, frekans-bandı enerjisi, ve YENİ bir QC-only "localized
  event risk" proxy'si (`compute_localized_event_risk` — asla
  arkeolojik sınıflandırma yapmaz, "wall"/"target" etiketi DÖNDÜRMEZ).
- 5 synthetic bilimsel-risk deneyi (spec 17): window-length vs
  target-length attenuation, global vs sliding uzun-olay testi, mean vs
  median outlier testi, edge (reflect/nearest) testi — hepsi
  `tests/test_background.py` + `sprint4a_candidates.py::
  run_synthetic_risk_experiments()`'te insan-incelenebilir çıktı olarak.
- Karar paneli (`BACKGROUND_DECISION_PANEL.png` +
  `_DETAIL.png`) ve nihai insan-kararı raporu
  (`BACKGROUND_FINAL_DECISION_REQUIRED.md`) — **hiçbir "en iyi aday"
  ifadesi yok, `recommended_background_candidate` alanı YOK.**
- CLI: `background` (tekil, manuel parametre) ve `sprint4a-candidates`
  (8 aday orkestrasyonu) alt komutları.

## Out of Scope
Gain, AGC, SEC/exponential/time-power gain, F-K filtering, migration,
velocity analysis, CMP analysis, hyperbola fitting, Hilbert envelope,
instantaneous attributes, time/depth slices, interpolation/gridding,
anomaly detection, arkeolojik sınıflandırma, otomatik wall/tomb/object
tespiti, Blender/QGIS/ReflexW/SEG-Y export, GUI, otomatik canonical aday
seçimi, PCA/SVD/eigenimage/robust-PCA background removal, frekans-domeni
background removal, polynomial trace-background modeli, neural-network
tabanlı yöntem, morphological image filtering, otomatik adaptif yöntem
seçimi, ham veri modifikasyonu.

## Input Data
`outputs/sprint03/canonical_D2_B1/sprint03_processed.npz` — SHA-256
`2044dd8f67957ee11590911bfbcaa410d2de29bd8ebfcae3b6aa06b5182fd026`, shape
`(175, 11, 1024)`, float32, işleme geçmişi tam olarak
`[time_zero_correction, dc_offset_correction, dewow_correction,
bandpass_correction]` (D2 dewow: `running_mean`, 65 örnek/8.125ns
uygulanan, `edge_mode=reflect`; B1 band-pass: Butterworth 100-900MHz,
order=4, zero-phase). Bkz. [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]].

## Tasks
- [x] Git branch (`sprint-04a-background-removal`) doğrulandı, `main`'e
  dokunulmadı.
- [x] `processing/background.py` — 4 yöntem, trace-spacing hesaplama,
  odd-centered-window politikası, `reflect`/`nearest` edge, valid-mask/
  padding güvenliği (10 kural), reprocessing guard.
- [x] `qc/background.py` — plotting suite (10 dosya/aday) + sinyal-koruma
  ve removed-component metrikleri + localized-event-risk proxy'si.
- [x] `export/sprint4a.py` — JSON yazıcıları + `candidate_validation.json`.
- [x] `configs/background_candidates.yaml` — A1-A8.
- [x] `sprint4a_candidates.py` — 8-aday orkestrasyonu, synthetic risk
  deneyleri, karşılaştırma klasörü, karar paneli, nihai karar raporu.
- [x] CLI: `background`, `sprint4a-candidates` alt komutları.
- [x] 60 yeni test (`test_background.py` 44, `test_background_qc.py` 11,
  `test_sprint4a_pipeline.py` 3, `test_sprint4a_real_integration.py` 2).
- [x] Kod incelemesi sırasında bulunan spec-tamlık boşlukları düzeltildi
  (bkz. Issues Discovered) — `removed_input_absolute_energy_ratio`,
  spatial concentration, median-trace correlation, local-event amplitude
  retention, channel consistency before/after, ve
  `BACKGROUND_FINAL_DECISION_REQUIRED.md`'nin 3 eksik kolonu.
- [x] Gerçek CLI çalıştırıldı: `outputs/sprint04a/` (8 aday × 18 dosya +
  karşılaştırma klasörü + üst düzey karar paneli/rapor).
- [x] Programatik + görsel QC denetimi.
- [x] ADR-008 + Obsidian vault senkronizasyonu (bu not dahil).

## Acceptance Criteria
Girdi/ham dosya/Sprint 2/Sprint 3 canonical hash'leri değişmedi · girdi
mutasyona uğramadı · `input = output + removed_component` (float32
hassasiyeti dahilinde) her adayda doğrulandı · `time_ns`/`valid_mask`
değişmedi · padding hem çıktıda hem removed component'te tam sıfır kaldı ·
8 aday arasında ölçülebilir farklar var (aynı değiller) · **hiçbir aday
canonical seçilmedi** · gain başlatılmadı · 314/314 test geçti (254 önceki
+ 60 yeni) · ruff/mypy temiz · vault validator PASS · tüm QC PNG/JSON/CSV
açılabilir/parse edilebilir · NPZ'ler `allow_pickle=False` ile yeniden
açılabiliyor. Hepsi **PASS**.

## Implementation Notes
- **Kanal-bazlı bağımsız hesaplama:** her kanalın background'ı kendi
  trace-axis istatistiğinden hesaplanır; kanallar hiçbir zaman
  birleştirilmez (`_global_background`/`_sliding_background`,
  `axis=0` = slice/trace ekseni, `sliding_window_view` ile — dewow.py'nin
  `axis=1` = sample ekseni kullanımından KASITLI olarak farklı).
- **Trace-spacing önceliği asla sabit gömülü değil:** öncelik sırası
  geolocation → metadata `sampling.sampling_step_m` → `unavailable`.
  Canonical Sprint 3 NPZ'de geolocation dizileri taşınmadığı için gerçek
  çalıştırmada kaynak `metadata_sampling_step`
  (`trace_spacing_m=0.04008848472894169`) oldu — bu, dosyanın kendi
  metadata'sından okundu, hiçbir yerde ~0.0401 sabit gömülü değil.
- **Odd-centered-window politikası:** `window_m/trace_spacing_m` en yakın
  tek sayıya yuvarlanır (çift ise +1); 3 traceden az bir pencere açık
  hatadır, profilden geniş bir pencere de açık hatadır — hiçbiri sessizce
  düzeltilmez.
- **Valid-mask yapısal basitleştirme:** bu projede `valid_mask` `(channels,
  samples)` şekilli ve bir kanal içinde her zaman slice-bazında sabittir
  (time-zero shift'i kanal-bazlı ve sabit — CLAUDE.md); bu nedenle "bir
  örnek konumunda yetersiz valid trace" kısmi bir durum olarak hiç
  OLUŞAMAZ — her örnek konumu bir kanal için ya tüm trace'lerde valid ya
  hiçbirinde valid'dir.
- **Kod incelemesi sırasında öz-eleştirel olarak bulunan spec-tamlık
  boşlukları** (bkz. Issues Discovered) — gerçek bir uygulama hatası değil,
  spec'in 15/16/20 numaralı bölümlerinin literal gereksinimleriyle ilk
  taslak arasındaki fark. Düzeltme sonrası tüm testler yeniden geçti
  (16/16 Sprint 4A testi + 314/314 toplam).

## Validation Results
- 314/314 test geçti (254 önceki hiç bozulmadı + 60 yeni: 44
  `test_background.py`, 11 `test_background_qc.py`, 3
  `test_sprint4a_pipeline.py`, 2 `test_sprint4a_real_integration.py`).
- `ruff format .`: 65 dosya (temiz). `ruff check .`: `All checks passed!`.
  `mypy src/archaeogpr`: `Success: no issues found in 39 source files`.
- Gerçek veri: 8/8 aday NPZ'si doğrulandı (shape `(175,11,1024)`, float32,
  NaN/Inf yok, padding tam sıfır hem çıktıda hem removed component'te,
  işleme geçmişi tam olarak `[..., background_removal]`).
- Ham dosya hash'i (`66d840c3...b62a6`), Sprint 2 canonical hash'i
  (`b2770b5c...af5afe`) ve Sprint 3 canonical hash'i
  (`2044dd8f...82fd026`) hepsi komut öncesi/sonrası değişmedi.
- Tam detay: [[07_VALIDATION/Test_Results]], [[07_VALIDATION/QC_Output_Validation]].

## Generated Outputs
`outputs/sprint04a/` (repository'de, vault dışı): `BACKGROUND_DECISION_
PANEL.png`, `BACKGROUND_DECISION_PANEL_DETAIL.png`,
`BACKGROUND_FINAL_DECISION_REQUIRED.md`,
`background_candidates/{A1_global_mean,...,A8_sliding_median_150m}/` (her
biri 18 dosya: NPZ, 6 JSON, 10 PNG, `candidate_validation.json`),
`background_candidates/comparison/` (19 dosya: karşılaştırma PNG'leri,
synthetic risk deneyi çıktıları, 3 CSV, `trace_spacing_summary.json`,
`BACKGROUND_REVIEW_REQUIRED.md`).

## Issues Discovered
Geliştirme sırasında kendi kendime bulunan ve düzeltilen boşluklar (kod
hiçbir zaman canonical/paylaşılan bir dala commit edilmeden düzeltildi):
1. **`run_background_candidates()`'in sliding yöntemler için yalnızca
   `window_m` anahtarını kabul etmesi** — `window_traces` veren bir
   config satırı `KeyError` verirdi. Düzeltme: `if/elif/else` ile her iki
   anahtar da desteklendi, ikisi de yoksa açık `ProcessingError`.
2. **`write_candidate_validation_json`'ın yanıltıcı bir
   `sprint3_canonical_sha256_after` parametresi taşıması** — dosya yalnızca
   bir kez okunduğu için bu, per-candidate sahte bir yeniden-doğrulama
   izlenimi veriyordu. Düzeltme: parametre kaldırıldı; gerçek tek-seferlik
   before/after hash karşılaştırması `run_all_sprint4a_candidates()`'e
   taşındı.
3. **Spec bölüm 15/16/20'nin literal gereksinimleriyle karşılaştırmalı
   denetim** (bkz. ADR-008) üç eksiği ortaya çıkardı:
   `removed_input_absolute_energy_ratio` (sum|x| tabanlı, sum(x²) tabanlı
   `removed_input_energy_ratio`'dan ayrı) ve spatial-concentration
   metriği `compute_removed_component_metrics`'te yoktu;
   `median_trace_correlation`, `local_event_amplitude_retention`, ve
   `channel_consistency_before/after` `compute_signal_preservation_
   metrics`'te yoktu; `BACKGROUND_FINAL_DECISION_REQUIRED.md`'nin
   tablosunda 3 zorunlu kolon (`Long-horizontal-event preservation`,
   `Localized-event preservation`, `Removed/input energy`) eksikti.
   Hepsi eklendi, testler güncellendi, gerçek CLI yeniden çalıştırıldı —
   tüm hash'ler değişmeden kaldı (aynı girdi, deterministik yeniden
   hesaplama).

## Decisions
Bu sprintte hiçbir background-removal adayı canonical seçilmedi (kural
gereği — bkz. CLAUDE.md, ADR-008). ADR-008 kanal-bazlı politika,
window-length riski, mean-vs-median farkı, ve trace-spacing önceliğini
mimari karar olarak kayda geçirir; bir aday SEÇMEZ.

## Completion Summary
Dört background-removal yöntemi bilimsel olarak implemente edildi, 8 aday
gerçek canonical Sprint 3 verisi üzerinde çalıştırıldı, sinyal-koruma ve
çıkarılan-bileşen metrikleri her aday için hesaplandı, 5 synthetic risk
deneyi çalıştırıldı, ve tam bir karar paketi (panel + rapor) üretildi.
Hiçbir aday canonical seçilmedi, gain başlatılmadı. Status: `review_required`.

## Next Sprint Recommendation
Bir kod görevi DEĞİL: **kullanıcının kendi açık isteğiyle** bu sprintin
8 adayından birini (veya hiçbirini) canonical seçmesi — bkz.
[[01_PROJECT_STATE/02_Next_Development_Sprint]]. Bu karardan sonra da
Gain otomatik olarak BAŞLAMAZ.

## Related Notes
[[Sprint_Index]], [[Sprint_03_Dewow_Bandpass]],
[[Sprint_03_1_Dewow_Bandpass_Decision_QC]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
[[05_PROCESSING/Background_Removal]],
[[01_PROJECT_STATE/02_Next_Development_Sprint]]
