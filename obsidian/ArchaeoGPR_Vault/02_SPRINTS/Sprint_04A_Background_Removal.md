---
type: sprint
tags: [sprint, review]
sprint: 4A
status: done
started: 2026-07-15
completed: 2026-07-16
---

# Sprint 4A — Background Removal Candidate Development, Signal-Preservation Validation and Geophysical QC

> **✅ Sprint tamamlandı (2026-07-16) — İnsan/jeofizik kararı: A0 (hiç
> background removal uygulanmama).** Bu sprintin başarı kriteri bir
> filtre SEÇMEK değildi — 8 adayı (A1-A8) ve bunların risklerini insan/
> jeofizik incelemesi için ölçülebilir kılmaktı. İnceleme sonucunda
> kullanıcı background removal'ın canonical zincire dahil EDİLMEMESİNE
> karar verdi. Canonical işlem zinciri Sprint 3 D2+B1 çıktısında kalıyor;
> hiçbir yeni canonical NPZ üretilmedi; Gain başlatılmadı. Detay:
> [[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]],
> [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-012 (kapatıldı).
>
> Aşağıdaki "Sprint 4A.1"/"Sprint 4A.2" bölümleri, bu nihai karara
> ulaşmak için üretilen kanıtın tarihsel QC kaydı olarak KORUNUYOR
> (değiştirilmedi) — bu düzeltmeler kendileri artık review_required
> DEĞİL, kapanmış bir sprintin parçası.
>
> **Sprint 4A.1 düzeltmesi (2026-07-16, PR #1 üzerinde):** karar QC'sindeki
> üç kusur düzeltildi — (1) pencere uzunluğu terminolojisi (`applied_
> window_m` fiziksel bir açıklık DEĞİLDİ, nominal length'ti); (2) karar
> B-scan'leri her aday için ayrı percentile scale kullanıyordu (görsel
> karşılaştırma anlamsızdı); (3) `long_horizontal_event_preservation = 1 -
> removed_component_coherence` bir "preservation fraction" gibi
> sunuluyordu (yanıltıcı). Yeni bir **paired-control sentetik hedef-
> retention deneyi** eklendi ve **kritik bir bulgu ortaya çıkardı**: A1/A2
> (yüksek `overall_rms_retention_tendency` ile "preservation-favoring"
> etiketlenmiş) gerçekte uzun sentetik hedefleri neredeyse tamamen yok
> ediyor (`paired_control_long_target_retention` ≈ 0.0097 / 0.0000676) —
> bu çelişki artık `Engineering interpretation` kolonunda açıkça
> `CONFLICT` olarak işaretleniyor. Detay: aşağıdaki "Sprint 4A.1" bölümü,
> [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].
>
> **Sprint 4A.2 düzeltmesi (2026-07-16, aynı PR #1):**
> `localized_hyperbola` sentetik hedefi, sabit `curvature=0.03` +
> `target_length_traces=9` yüzünden pratikte DÜZ bir olaydı (`depth_shift`
> her trace'te 0'a yuvarlanıyordu) — gerçek bir jeofizik bulgu değil, bir
> sentetik-veri-üretim hatasıydı. Artık `curvature` istenen bir maksimum
> kaymadan türetiliyor, gerçek bir boole `target_mask` döndürülüyor, ve
> retention metrikleri sabit bir apex-penceresi yerine bu gerçek maskeyi
> kullanıyor (apex/arm ayrı raporlanıyor). Yeni **A0 ("hiç background
> removal yapmama")** — bir dokuzuncu filtre değil, karar/QC katmanında
> sabit değerli bir referans politikası (`overall_rms_retention_
> tendency=1`, `background_suppression=0`, hiçbir NPZ/ProcessingResult
> yok) — nihai karar tablosuna, metrics summary paneline ve
> `candidate_metrics.csv`'ye eklendi (B-scan montajlarına DEĞİL). "No
> background removal" insan reviewer için geçerli bir karar olarak açıkça
> belgelendi. Detay: aşağıdaki "Sprint 4A.2" bölümü,
> [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].

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
- [x] **Sprint 4A.1 (PR #1 üzerinde):** pencere terminolojisi düzeltmesi,
  ortak-scale B-scan montajları (3 yeni dosya), paired-control sentetik
  hedef-retention deneyi (YENİ), engineering category yeniden adlandırma
  + çelişki bayrağı, `1 - coherence` "preservation" çerçevesinin
  kaldırılması, nihai karar tablosunun 18 kolonla yeniden yazılması, 14
  yeni test, gerçek CLI yeniden çalıştırma (tüm hash'ler değişmedi).

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
- **Sprint 4A.1 sonrası: 328/328 test geçti** (314 önceki hiç bozulmadı +
  14 yeni: 1 `test_background.py`, 13 yeni `tests/
  test_sprint4a_candidates.py`).
- `ruff format .`: 66 dosya (temiz). `ruff check .`: `All checks passed!`.
  `mypy src/archaeogpr`: `Success: no issues found in 39 source files`.
- Gerçek veri: 8/8 aday NPZ'si doğrulandı (shape `(175,11,1024)`, float32,
  NaN/Inf yok, padding tam sıfır hem çıktıda hem removed component'te,
  işleme geçmişi tam olarak `[..., background_removal]`).
- Ham dosya hash'i (`66d840c3...b62a6`), Sprint 2 canonical hash'i
  (`b2770b5c...af5afe`) ve Sprint 3 canonical hash'i
  (`2044dd8f...82fd026`) hepsi Sprint 4A.1 çalıştırması öncesi/sonrası da
  değişmedi (deterministik yeniden hesaplama, aynı girdi).
- Tam detay: [[07_VALIDATION/Test_Results]], [[07_VALIDATION/QC_Output_Validation]].

## Generated Outputs
`outputs/sprint04a/` (repository'de, vault dışı): `BACKGROUND_DECISION_
PANEL.png`/`_DETAIL.png` (tarihsel uyumluluk), **`BACKGROUND_OUTPUT_
COMPARISON_CH00_CH05_CH10.png`, `BACKGROUND_REMOVED_COMPARISON_CH00_
CH05_CH10.png`, `BACKGROUND_METRICS_SUMMARY.png` (Sprint 4A.1, insan
incelemesi için asıl dosyalar)**, `BACKGROUND_FINAL_DECISION_REQUIRED.md`
(18 kolon), `background_candidates/{A1_global_mean,...,
A8_sliding_median_150m}/` (her biri 18 dosya: NPZ, 6 JSON, 10 PNG,
`candidate_validation.json`), `background_candidates/comparison/` (22
dosya: karşılaştırma PNG'leri, synthetic + **paired-control (YENİ)** risk
deneyi çıktıları, 4 CSV, `trace_spacing_summary.json`,
`BACKGROUND_REVIEW_REQUIRED.md`; eski dosya adlarına ait 3 stale dosya
Sprint 4A.1'de temizlendi).

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

## Sprint 4A.1 — Background Decision QC Correction (2026-07-16)
PR #1 üzerinde, çekirdek background-removal implementasyonunu (4 yöntem,
8 aday) değiştirmeden, insan/jeofizik kararını etkileyen QC/raporlama
kusurlarını düzeltir. Yeni bir filtre yöntemi geliştirilmedi, Gain'e
başlanmadı, `main`'e doğrudan commit atılmadı.

**Düzeltilen kusurlar:**
1. **Pencere terminolojisi:** `applied_window_m` (= `applied_window_
   traces * trace_spacing_m`, bir "nominal length") fiziksel bir merkez-
   merkez açıklık gibi sunuluyordu. Artık ayrı, açık alanlar var:
   `applied_window_nominal_length_m`, `applied_window_center_to_center_
   span_m` (`= (applied_window_traces - 1) * trace_spacing_m`),
   `window_half_span_m`. Örnek (13 trace, dx=0.04m): nominal=0.52m,
   center-to-center span=0.48m, half-span=0.24m. `applied_window_m`
   backward-compat için korundu ama açıkça deprecated/ambiguous olarak
   belgelendi ve yeni insan-karar raporlarında kullanılmıyor.
2. **Karar B-scan'leri:** eski detail panel her aday için bağımsız
   percentile scale kullanıyordu — görsel karşılaştırma anlamsızdı. Yeni
   üç dosya: `BACKGROUND_OUTPUT_COMPARISON_CH00_CH05_CH10.png` (input +
   A1-A8, kanal-bazlı TEK ortak simetrik scale), `BACKGROUND_REMOVED_
   COMPARISON_CH00_CH05_CH10.png` (A1-A8 removed component, aynı ortak-
   scale kuralı), `BACKGROUND_METRICS_SUMMARY.png` (sadece metrik bar
   chart paneli). Eski `BACKGROUND_DECISION_PANEL.png`/`_DETAIL.png`
   tarihsel uyumluluk için korundu ama artık açıkça bu üç dosyaya
   yönlendiriyor. `channelNN_all_candidates_20_100ns.png` da
   `channelNN_median_trace_all_candidates_20_100ns.png` olarak yeniden
   adlandırıldı (bir medyan-iz overlay'i, B-scan değil).
3. **Paired-control sentetik hedef-retention deneyi (YENİ):** eski
   sentetik retention hesabı hedef+background+noise'u birlikte ölçüyordu
   (yeniden adlandırıldı: `mixed_scene_*`). Yeni yöntem: AYNI background+
   noise realizasyonuyla bir `control` ve bir `with_target` profili
   kurulur, her ikisi de aynı yöntem/pencereyle işlenir, ve
   `target_after = processed_with_target - processed_control` ile SADECE
   hedefe ait bileşen izole edilir. 5 senaryo (kısa/pencereye
   yakın/uzun/hiperbol-benzeri lokalize/uzun-yatay) × sliding_mean/
   sliding_median + global_mean/global_median (yalnızca uzun-yatay).
   **Kritik bulgu:** bu veri setinde TÜM 8 aday, uzun bir sentetik hedefi
   neredeyse tamamen yok ediyor (`paired_control_long_target_retention`
   ≈ 0.00006-0.017, A1-A8 arası) — RMS-bazlı "preservation-favoring"
   etiketi bu riski GİZLİYORDU.
4. **Engineering category yeniden adlandırıldı:** RMS-bazlı sıralama artık
   `overall_rms_retention_tendency` olarak açıkça raporlanıyor (yalnızca
   bu metriğe dayandığı belirtilerek); `paired_control_short_target_
   retention`, `paired_control_long_target_retention`,
   `local_event_amplitude_retention`, `removed_coherent_event_risk_proxy`,
   `background_suppression`, `waveform_correlation`, `spectral_retention`
   ayrı metrikler olarak raporlanıyor. Yeni `Engineering interpretation`
   metni, `overall_rms_retention_tendency`'nin "preservation-favoring"
   dediği ama `paired_control_long_target_retention`'ın düşük çıktığı
   (< 0.3) her adayda açık bir `CONFLICT` uyarısı basıyor — A1 ve A2 için
   gerçek veride bu çelişki tetiklendi.
5. **`1 - coherence` "preservation" çerçevesi kaldırıldı:**
   `long_horizontal_event_preservation = max(0, 1 -
   removed_component_coherence)` insan-karar tablosundan kaldırıldı.
   Yerine `removed_coherent_event_risk_proxy` = ham `removed_component_
   coherence` DOĞRUDAN raporlanıyor, açık bir uyarıyla: yüksek değer
   removed component'in mekânsal sürekli olduğunu gösterir, bunun
   unwanted background mı gerçek yansıma mı olduğunu BELİRLEMEZ, bir
   preservation yüzdesi DEĞİLDİR, arkeolojik bir iddia DEĞİLDİR.

**Nihai karar tablosu** (`BACKGROUND_FINAL_DECISION_REQUIRED.md`) artık 18
kolon: Candidate, Method, Requested window, Applied trace count, Nominal
window length, Center-to-center spatial span, Background suppression,
Overall RMS retention, Waveform correlation, Spectral retention,
Local-event amplitude retention, Paired-control short-target retention,
Paired-control long-target retention, Removed coherent-event risk proxy,
Padding safety, Timing preservation, Engineering interpretation, Main risk.
Açık uyarı satırları: no candidate canonical, gain not started, "overall
RMS retention is not equivalent to archaeological-target preservation",
"removed-component coherence ... is not a direct signal/noise classifier",
"human review requires common-scale B-scans".

**Testler:** 14 yeni test eklendi (`test_background.py`'de 1 — nominal
length vs center-to-center span aritmetiği; yeni `tests/
test_sprint4a_candidates.py`'de 13 — ortak-scale montaj testleri,
paired-control izolasyon/pencere-uzunluğu/hiperbol/mean-vs-median
testleri, nihai rapor doğruluğu, çelişki-bayrağı testi). Mevcut 314 test
hiç bozulmadı — toplam **328/328 passed**.

**Gerçek CLI yeniden çalıştırıldı** (`outputs/sprint04a/`) — tüm hash'ler
(ham `.ogpr`, Sprint 2 canonical, Sprint 3 canonical) değişmeden kaldı,
aynı deterministik girdi/çıktı.

## Sprint 4A.2 — Hyperbola QC Fix and No-Background Baseline (2026-07-16)
PR #1 üzerinde, aynı branch'te (`sprint-04a-background-removal`). Çekirdek
`remove_background()` implementasyonunu değiştirmeden, Sprint 4A.1'in
KENDİ paired-control deneyindeki bir sentetik-veri hatasını ve nihai karar
tablosundaki bir eksik referans noktasını (background removal
YAPMAMAYI) düzeltir. Yeni bir filtre yöntemi geliştirilmedi, Gain'e
başlanmadı, `main`'e doğrudan commit atılmadı.

**Düzeltilen kusurlar:**
1. **`localized_hyperbola` pratikte düz bir olaydı.** `_paired_control_
   profile()`'ın hiperbol dalı sabit `curvature=0.03` kullanıyordu;
   `target_length_traces=9` (apex'ten maksimum uzaklık = 4 trace) ile
   `depth_shift = round(0.03 * 4**2) = round(0.48) = 0` — her trace'te
   sıfır. Düzeltme: `curvature` artık istenen bir maksimum kaymadan
   türetiliyor: `curvature = requested_max_shift_samples /
   max_offset_traces**2` (varsayılan `requested_max_shift_samples=12.0`,
   `target_length_traces=15` → `max_offset_traces=7` →
   `curvature≈0.2449`). Gerçek veride bu, 15 hedef trace boyunca 7 farklı
   sample-center değeri (`[100,101,102,104,106,109,112]`), 12 örnek
   apex-kol kayması, ve apex'in her zaman en sığ (minimum) sample olması
   üretiyor — istenen tüm sayısal eşikleri (≥5 trace, ≥3 farklı merkez,
   ≥3-5 örnek apex-kol farkı) rahatça karşılıyor.
2. **Retention metrikleri artık gerçek hedef desteğini kullanıyor, sabit
   bir apex-penceresi DEĞİL.** `_paired_control_profile()` artık gerçek
   bir boole `target_mask` (`(slices, samples)`, Hanning-taper'ın
   sıfır-olmayan katkısının bulunduğu her yer — taper'ın kendi uç
   noktaları tam sıfır olduğu için mask, `target_before`'un her
   sıfır-olmayan değerini kapsıyor, hiçbir yanlış-pozitif yok),
   `target_trace_bounds`, `target_sample_bounds`, ve `target_center_
   sample_by_trace` döndürüyor. Retention artık bu gerçek mask üzerinden,
   TÜM hedef desteği için, ve ayrıca apex (en sığ sample'a sahip hedef
   trace'i) ile kollar (diğer tüm hedef trace'leri) için ayrı ayrı
   hesaplanıyor: `full_target_peak_retention`, `full_target_mean_
   absolute_retention`, `full_target_energy_retention`, `full_target_
   waveform_correlation`, `apex_retention`, `arm_retention`, `edge_trace_
   retention`, `interior_target_retention`. Dikdörtgen hedefler AYNI
   mask-tabanlı kod yolunu kullanıyor (apex'i, her trace aynı merkez
   sample'ı paylaştığı için gelişigüzel ilk hedef trace'e indirgeniyor —
   belgeleniyor, ayrı bir uygulama DEĞİL).
3. **Yeni doğrulama görseli:** `PAIRED_CONTROL_HYPERBOLA_VALIDATION.png`
   (`background_candidates/comparison/`). Paneller: bilinen `target_
   before`; `sliding_mean` ve `sliding_median` için işlenmiş `target_
   after` (AYNI profil çekiminden, doğrudan karşılaştırılabilir); gerçek
   `target_mask`; trace-bazlı merkez-sample yörüngesi (apex işaretli); her
   iki yöntem için apex-vs-kol retention çubukları. Başlık gerçek hedef
   trace sayısını, benzersiz merkez-sample sayısını, gerçekleşen maksimum
   kaymayı, ve karşılaştırma penceresi trace sayısını belirtiyor.
4. **A0 ("hiç background removal yapmama") — dokuzuncu bir filtre değil,
   karar/QC katmanında sabit değerli bir referans politikası.**
   `_a0_reference_policy_metrics()` sabit, tanımsal değerler döndürüyor
   (`overall_rms_retention_tendency=1`, `waveform_correlation=1`,
   `spectral_retention=1`, `local_event_amplitude_retention=1`,
   `paired_control_short_target_retention=1`, `paired_control_long_
   target_retention=1`, `background_suppression=0`, `removed_coherent_
   event_risk_proxy=not_applicable`, `padding_safety=unchanged`,
   `timing_preservation="0 sample lag"`, `processing_applied=False`) —
   hiçbir zaman ölçülmüyor, hiçbir zaman bir `ProcessingResult`/NPZ
   üretmiyor. A0 SADECE `BACKGROUND_FINAL_DECISION_REQUIRED.md`'de (ilk
   satır), `BACKGROUND_METRICS_SUMMARY.png`'de (8 panelin 7'sinde gri bir
   referans çubuğu, `removed_coherent_event_risk_proxy` panelinden hariç
   — A0'ın gerçek bir removed component'i yok), ve `candidate_metrics.
   csv`'de görünüyor; B-scan montajlarına asla girmiyor (`save_common_
   scale_output_comparison()`/`_removed_comparison()` yalnızca
   `candidates_info`'yu işliyor, A0 oraya hiç girmiyor). "Preservation-
   favoring" etiketli her adayın `Engineering interpretation` metni artık
   A0'ın sabit 1.0 retention'ına karşı açık bir karşılaştırma da içeriyor
   — bu etiketin SADECE A1-A8 arasında GÖRECELİ bir sıralama olduğunu,
   hiçbir zaman "hiçbir şey yapmamaktan daha fazla koruma" iddiası
   olmadığını netleştiriyor.
5. **Nihai karar raporuna A0 satırı ve yeni açık uyarılar eklendi.**
   `BACKGROUND_FINAL_DECISION_REQUIRED.md` artık şunları da içeriyor:
   "A0 is the no-background-removal reference.", "A0 is not a new filter
   method.", (veri-bazlı, sabit-kodlanmamış) tüm A1-A8'in paired-control
   uzun hedefi güçlü şekilde zayıflattığı ifadesi, "High overall RMS
   retention does not imply long-target preservation.", "Human reviewer
   may select \"no background removal\".", "No canonical decision is made
   automatically.", "Gain has not started." — Sprint 4A.1'den beri var
   olan uyarılara ek olarak.

**Testler:** 16 yeni test eklendi (`tests/test_sprint4a_candidates.py`'de,
mevcut testler yeni API'ye güncellendi) — hiperbol geometrisi/sınır
kontrolü, mask doğruluğu, sabit-pencere metriğinin artık kullanılmadığının
doğrulanması, apex/arm'ın ayrı metrik olduğu, A0'ın sabit değerleri, A0'ın
NPZ/B-scan üretmediği, hiçbir adayın (A0 dahil) canonical seçilmediği,
Gain modülünün var olmadığı. Mevcut 328 test hiç bozulmadı — toplam
**342/342 passed** (bazı testler Sprint 4A.1'in eski `Gain has not been
started.` metnini kontrol ediyordu, bu Sprint 4A.2'nin tam gerekli
metnine — `Gain has not started.` — güncellendi).

**Gerçek CLI yeniden çalıştırıldı** (`outputs/sprint04a/`) — tüm hash'ler
(ham `.ogpr`, Sprint 2 canonical, Sprint 3 canonical) değişmeden kaldı.

## Sprint 4A Closure — Human Decision (2026-07-16)

**Sprint başarılı şekilde tamamlandı.** Bu sprintin başarı kriteri bir
filtre seçmek DEĞİLDİ — 8 background-removal adayını (A1-A8) gerçek
veride ölçülebilir, insan/jeofizik incelemesine uygun kanıtla üretmekti.
**İnsan incelemesi sonucunda background removal uygulanmaması seçildi**
(canonical policy: **A0**, `no_background_removal`) — bkz.
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]] (karar
gerekçesi, alternatifler, dataset-specific kapsam, tüm sayısal kanıt).

**[[01_PROJECT_STATE/03_Open_Issues]] ISSUE-012 şu karar ile KAPATILDI:
canonical background policy = A0.**

Karar sonucu:
- A1-A8'den hiçbiri canonical seçilmedi.
- Canonical Sprint 3 verisine (D2+B1) background removal
  UYGULANMAYACAK.
- Canonical işlem zinciri değişmeden kalıyor:
  `time_zero_correction → dc_offset_correction → dewow_correction (D2)
  → bandpass_correction (B1)`.
- Yeni bir canonical NPZ üretilmedi.
- A0 için `ProcessingResult`, `removed_component` veya NPZ üretilmedi
  (Sprint 4A.2'de kasıtlı olarak tasarlanmış davranış — bu karar bunu
  değiştirmiyor).
- A1-A8, repository'de deneysel/opt-in araçlar olarak kalıyor
  (`background`/`sprint4a-candidates` CLI alt komutları,
  `configs/background_candidates.yaml`) — silinmedi, kaldırılmadı.
- Gain başlatılmadı; bu karar Gain'i otomatik olarak BAŞLATMAZ.

Sprint 4A.1 ve Sprint 4A.2 düzeltmeleri (yukarıdaki bölümler) bu nihai
karara ulaşmak için üretilen kanıtın **tarihsel QC kaydı** olarak
DEĞİŞTİRİLMEDEN korunuyor.

## Decisions
Bu sprintte 8 background-removal adayından (A1-A8) hiçbiri canonical
seçilmedi — ancak sprint kapanışında (2026-07-16) kullanıcı **A0**'ı
(hiç background removal uygulanmama) canonical POLİTİKA olarak seçti.
Bkz. [[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]].
ADR-008 kanal-bazlı politika, window-length riski, mean-vs-median farkı,
ve trace-spacing önceliğini mimari karar olarak kayda geçirir; bir aday
SEÇMEZ. Sprint 4A.1, ADR-008'e nominal-length-vs-span, paired-control
target retention, common-scale görsel karşılaştırma, ve
removed-coherence'ın preservation olmadığı notlarını ekler. Sprint 4A.2,
hiperbol QC düzeltmesi ve A0 referans politikasını ekler. ADR-009, bu
kanıtı kullanarak nihai insan kararını (A0 canonical) kayda geçirir.

## Completion Summary
Dört background-removal yöntemi bilimsel olarak implemente edildi, 8 aday
gerçek canonical Sprint 3 verisi üzerinde çalıştırıldı, sinyal-koruma ve
çıkarılan-bileşen metrikleri her aday için hesaplandı, 5 synthetic risk
deneyi çalıştırıldı, hiperbol QC hatası düzeltildi, A0 referans
politikası eklendi, ve tam bir karar paketi (panel + rapor) üretildi.
**İnsan/jeofizik incelemesi sonucunda hiçbir aday (A1-A8) canonical
seçilmedi; canonical policy = A0 (background removal uygulanmadı); gain
başlatılmadı. Status: `done`.**

## Next Sprint Recommendation
Bir kod görevi DEĞİL: Sprint 4B (Gain veya başka bir kapsam) henüz
TANIMLANMADI ve kullanıcının kendi açık isteği olmadan BAŞLATILMAYACAK —
bkz. [[01_PROJECT_STATE/02_Next_Development_Sprint]]. "Canonical policy =
A0" kararı, tek başına, Gain'i veya başka bir sonraki sprinti otomatik
olarak BAŞLATMAZ.

## Related Notes
[[Sprint_Index]], [[Sprint_03_Dewow_Bandpass]],
[[Sprint_03_1_Dewow_Bandpass_Decision_QC]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]],
[[05_PROCESSING/Background_Removal]],
[[01_PROJECT_STATE/02_Next_Development_Sprint]],
[[01_PROJECT_STATE/03_Open_Issues]]
