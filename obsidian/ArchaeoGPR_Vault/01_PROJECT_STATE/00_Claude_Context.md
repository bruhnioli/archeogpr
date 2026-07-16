---
type: project-state
tags: [project-state]
---

> Bu dosya hızlı bağlam özetidir. Kodun gerçek davranışı için repository ve testler kaynak kabul edilir.

# Claude Context — archaeogpr

## Proje amacı
IDS GeoRadar OpenGPR (`.ogpr`) dosyalarını okuyan, doğrulayan ve ileride
arkeolojik GPR görselleştirmesi için kullanılacak modüler bir Python
yazılımı. Nihai hedef arkeolojik GPR görselleştirme; şu ana kadar veri
altyapısı + iki temel sinyal işleme modülü (time-zero, DC offset) kuruldu.

## Repository yolu ve temel mimari
- Kök: `archaeogpr/` (proje bu klasörde; henüz bir git repository değil)
- `src/archaeogpr/io/` — `ogpr_reader.py` (`read_ogpr`, `read_ogpr_header`), `exceptions.py`
- `src/archaeogpr/model/` — `dataset.py` (`GPRDataset`), `_frozen.py` (paylaşılan `FrozenDict`/freeze yardımcıları)
- `src/archaeogpr/processing/` — `common.py` (`contiguous_true_runs` dahil), `result.py` (`ProcessingResult`), `time_zero.py`, `dc_offset.py`, `dewow.py`, `bandpass.py`
- `src/archaeogpr/qc/` — `metadata.py`, `bscan.py`, `geometry.py`, `time_zero.py`, `dc_offset.py`, `spectrum.py`, `dewow.py`, `bandpass.py`
- `src/archaeogpr/export/` — `basic.py`, `processed.py` (Sprint 2 CSV/JSON/NPZ), `sprint3.py` (`read_processed_npz`, `load_candidates_config`, `write_padding_verification_json`), `sprint4a.py` (Sprint 4A JSON yazıcıları)
- `src/archaeogpr/sprint3_candidates.py` — Sprint 3 aday orkestrasyonu (dewow/spektrum/band-pass/kombine + karşılaştırma + `SPRINT3_REVIEW_REQUIRED.md`)
- `src/archaeogpr/sprint3_canonical.py` — canonical D2+B1 zinciri (`run_sprint3_canonical()`, `write_canonical_processing_note()`) — insan/jeofizik kararı, yeni filtre algoritması YOK
- `src/archaeogpr/processing/background.py` — (Sprint 4A) `remove_background()` (global_mean/global_median/sliding_mean/sliding_median), `compute_trace_spacing()`
- `src/archaeogpr/qc/background.py` — (Sprint 4A) sinyal-koruma + removed-component metrikleri, `compute_localized_event_risk()`, plotting suite
- `src/archaeogpr/sprint4a_candidates.py` — (Sprint 4A) 8-aday orkestrasyonu, synthetic risk deneyleri, karar paneli, `BACKGROUND_FINAL_DECISION_REQUIRED.md` yazıcısı — **hiçbir aday canonical seçmez**
- `src/archaeogpr/cli.py`, `__main__.py` — `python -m archaeogpr inspect|header|time-zero|dc-offset|sprint2|dewow|bandpass|sprint3-candidates|sprint3|background|sprint4a-candidates`
- `configs/{dewow,bandpass}_candidates.yaml` — Sprint 3 aday tanımları
- `configs/background_candidates.yaml` — Sprint 4A aday tanımları (A1-A8)
- `tests/` — sentetik fixture tabanlı unit testler + gerçek dosya entegrasyon testleri
- `obsidian/ArchaeoGPR_Vault/` — bu vault
- Detaylı harita: [[03_ARCHITECTURE/Repository_Map]]

## Aktif sprint
**Sprint 4A** ([[02_SPRINTS/Sprint_04A_Background_Removal]]) —
**review_required**. Dört background-removal yöntemi (global_mean/
global_median/sliding_mean/sliding_median) implemente edildi, 8 aday
(A1-A8) canonical Sprint 3 çıktısı (D2+B1) üzerinde gerçek veride
çalıştırıldı. **Hiçbir aday canonical seçilmedi, Gain başlatılmadı** —
bkz. [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].
**Sprint 4A.2 (2026-07-16, PR #1):** `localized_hyperbola` sentetik
hedefinin pratikte düz olduğu bulundu/düzeltildi (gerçek eğrilik, mask-
tabanlı apex/arm retention), ve karar katmanına A0 ("hiç background
removal yapmama") referans politikası eklendi — status hâlâ
`review_required`.
Sprint 3 ([[02_SPRINTS/Sprint_03_Dewow_Bandpass]]) ve Sprint 3.1
([[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]]) her ikisi de
**done** — D2 dewow + B1 band-pass canonical (bkz.
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]). Sprint 2/2.1/2.2
durumları da `done` (bkz. [[02_SPRINTS/Sprint_02_TimeZero_DCOffset]],
[[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]],
[[02_SPRINTS/Sprint_02_2_TimeAxis_DCWindow_Validation]]).

## Mevcut çalışan özellikler
- Sprint 1: `.ogpr` okuyucu, `GPRDataset`, türetilmiş metadata, temel QC
  görselleri/exportlar, `inspect`/`header` CLI.
- Sprint 2: `correct_time_zero()` (manual / channel_median_peak /
  channel_median_cross_correlation), `correct_dc_offset()` (mean / median),
  `ProcessingResult` (dataset + removed_component + diagnostics + warnings),
  before/after/difference B-scan QC, `time-zero`/`dc-offset`/`sprint2` CLI
  alt komutları.
- Sprint 3: `correct_dewow()` (running_mean/running_median, segment-bazlı),
  `correct_bandpass()` (zero-phase Butterworth + Ormsby, segment-bazlı),
  `compute_amplitude_spectrum()` (genlik spektrumu QC), `read_processed_
  npz()` (güvenli NPZ yükleyici), aday orkestrasyonu
  (`sprint3_candidates.py`), `dewow`/`bandpass`/`sprint3-candidates` CLI
  alt komutları. Karşılaştırma aşamasında hiçbir aday canonical
  seçilmedi (bkz. aşağıdaki canonicalization maddesi için nihai karar).
- Sprint 3.1: `qc/{spatial_coherence,phase_metrics,band_energy,
  decision_qc}.py` (yeni QC/analiz katmanı, yeni filtre YOK) +
  `scripts/generate_sprint3_1_decision_qc.py`. D2 dewow'un removed
  component'i ayrıntılı doğrulandı; yalnızca B1/B2 band-pass adayları
  karar-odaklı QC ile karşılaştırıldı.
- **Sprint 3 Canonicalization (2026-07-15):** `sprint3_canonical.py`
  (`run_sprint3_canonical()`, `correct_dewow()`/`correct_bandpass()`'i
  D2/B1 sabit parametreleriyle çağırır — yeni bir filtre algoritması
  YOK), `sprint3` CLI alt komutu. İnsan/jeofizik kararı: **D2 dewow + B1
  band-pass canonical**. Bkz.
  [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
  `outputs/sprint03/canonical_D2_B1/`.
- **Sprint 4A (2026-07-15, review_required):** `processing/background.py`
  (`remove_background()` — global_mean/global_median/sliding_mean/
  sliding_median, kanal-bazlı bağımsız, hiçbir zaman kanalları
  birleştirmez), `qc/background.py` (sinyal-koruma + removed-component
  metrikleri + `compute_localized_event_risk()` QC-only proxy'si),
  `sprint4a_candidates.py` (8 aday orkestrasyonu, synthetic risk
  deneyleri, karar paneli). `background`/`sprint4a-candidates` CLI alt
  komutları. **Hiçbir aday canonical seçilmedi, Gain başlatılmadı.** Bkz.
  [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
  `outputs/sprint04a/`.
- **Sprint 4A.1 (2026-07-16, PR #1):** karar QC düzeltmesi — pencere
  terminolojisi (`applied_window_nominal_length_m` vs `_center_to_
  center_span_m`), ortak-scale B-scan montajları
  (`save_common_scale_output_comparison()`/`_removed_comparison()`),
  YENİ paired-control sentetik hedef-retention deneyi
  (`run_paired_control_target_attenuation_experiments()`), `1 -
  coherence` "preservation" çerçevesinin kaldırılması. **Kritik bulgu:**
  A1/A2 yüksek RMS retention ile "preservation-favoring" ama
  `paired_control_long_target_retention` ≈ 0 — artık `Engineering
  interpretation`'da açık `CONFLICT` olarak işaretleniyor. Çekirdek
  background-removal implementasyonu DEĞİŞMEDİ, Gain başlatılmadı.
- **Sprint 4A.2 (2026-07-16, aynı PR #1):** `_paired_control_profile()`'ın
  `localized_hyperbola` dalı sabit `curvature=0.03` ile pratikte düz bir
  olay üretiyordu (`depth_shift` her trace'te 0'a yuvarlanıyordu) —
  düzeltildi: `curvature` artık bir istenen maksimum kaymadan türetiliyor,
  gerçek bir boole `target_mask` döndürülüyor. `_paired_control_retention_
  metrics()` artık sabit bir apex-penceresi yerine bu gerçek maskeyi
  kullanıyor, apex/arm'ı ayrı raporluyor (`full_target_*`, `apex_
  retention`, `arm_retention`). Yeni `PAIRED_CONTROL_HYPERBOLA_
  VALIDATION.png`. Yeni **A0** (`_a0_reference_policy_metrics()`) —
  dokuzuncu bir filtre DEĞİL, karar/QC katmanında sabit değerli bir
  referans politikası (`overall_rms_retention_tendency=1`, `background_
  suppression=0`, hiçbir NPZ/ProcessingResult yok) — nihai karar
  tablosuna, metrics summary paneline ve `candidate_metrics.csv`'ye
  eklendi. Çekirdek background-removal implementasyonu DEĞİŞMEDİ, Gain
  başlatılmadı.

## Son doğrulanan test sonucu
`pytest` → **342 passed, 0 failed, 0 skipped** (2026-07-16; 328 önceki +
16 yeni Sprint 4A.2 testi — bkz. `tests/test_sprint4a_candidates.py`).
Gerçek dosya entegrasyon testleri çalıştı (skip edilmedi). Detay:
[[07_VALIDATION/Test_Results]].

## Aktif dataset
`Swath003_Array02.ogpr` — shape `(175, 11, 1024)`, float32, 600 MHz,
horizontal polarization, geolocation mevcut, SRS EPSG:32632 (doğrulanmamış).
Sprint 2 sonrası işlenmiş türevleri de mevcut (`outputs/sprint02/`).
Detay: [[04_DATASETS/Swath003_Array02]].

## Kritik teknik kararlar
- Radar eksen sırası sabit: `(slice, channel, sample)`.
- Ham veri modeli tamamen immutable (`model/_frozen.py`: `FrozenDict` + read-only ndarray).
- Time-zero shift **kanal-bazlı ve sabittir**; iz-bazlı (trace-by-trace)
  otomatik kaydırma bu sprintte kesinlikle uygulanmadı.
- Otomatik time-zero pick'i **fiziksel yüzey zamanı değildir** — her
  sonuçta `TIME_ZERO_REFERENCE_WARNING` bulunur. Detay:
  [[06_DECISIONS/ADR_002_TimeZero_Reference_and_Shift_Policy]].
- DC offset her (slice, channel) trace'ini bağımsız düzeltir; tek global ofset yok.
- `removed_component := input - output` (her iki işlemde de tam eşitlik).
- Sample Geolocations blok kaydının iç yapısı header'da tanımlı DEĞİL; gerçek dosyadan doğrulanarak çıkarıldı.
- **(Sprint 2.1)** `overflow_policy: Literal["error","clip"]`, varsayılan
  `"error"` — `max_shift_samples` aşılırsa veriye dokunulmadan hata verilir;
  kırpma yalnızca açık opt-in. Bkz.
  [[06_DECISIONS/ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]].
- **(Sprint 2.1)** `ProcessingResult.valid_mask` (şekil `(channels,
  samples)`, bool, salt-okunur) — time-zero'nun padding bölgesini işaretler;
  `correct_dc_offset(..., valid_mask=...)` ofset hesaplamasını VE çıkarmayı
  bu maskeyle sınırlar, padding `fill_value`'da byte-bazında değişmeden
  kalır.
- **(Sprint 2.2)** `correct_time_zero()`'nun çıktı `time_ns`'i artık
  time-zero-relative: `time_ns[target_sample] == 0.0`. `correct_dc_offset(
  ..., window_reference="dataset_time")` (varsayılan), pencereyi bu eksene
  göre çözer — bu, aynı ns penceresinin farklı `target_sample`
  değerlerinde AYNI ham örnekleri seçmesini sağlar (target-invariance,
  gerçek veride fark=0.0 olarak doğrulandı). Canonical politika:
  `method="mean", window=[20,100) ns` — CLI varsayılanı, fonksiyona sabit
  gömülü değil.
- **(Sprint 3)** `contiguous_true_runs()` (`processing/common.py`),
  hem dewow hem band-pass tarafından paylaşılır — bir kayan
  pencere/filtre asla bir padding boşluğunu aşmaz, her ardışık geçerli
  segment bağımsız işlenir.
- **(Sprint 3)** Dewow pencere dönüşümü hiçbir zaman sessizce
  yuvarlanmaz: istenen ve uygulanan pencere (çift→tek yuvarlama dahil)
  her zaman ayrı ayrı `diagnostics`'e kaydedilir. Bkz.
  [[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]].
- **(Sprint 3)** Band-pass iki bağımsız yöntem sunar (Butterworth
  zero-phase `sosfiltfilt`, Ormsby gerçek yamuk transfer fonksiyonu),
  ikisi de sıfır-faz — pik-kayması + medyan-iz çapraz-korelasyon
  gecikmesiyle hem sentetik hem gerçek veride doğrulandı (gecikme=0).
  Bkz. [[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]].
- **(Sprint 3)** Dewow (D1-D4) ve band-pass (B1-B4) için aday parametre
  karşılaştırmaları üretildi (`outputs/sprint03/`); kodun kendisi hiçbirini
  otomatik olarak canonical seçmedi.
- **(Sprint 3 Canonicalization, 2026-07-15)** Kullanıcı D2 (dewow) + B1
  (band-pass)'i insan/jeofizik kararı olarak canonical seçti — kod
  tarafından otomatik seçilmedi, sabit/adlandırılmış parametreler olarak
  kodlandı (`sprint3_canonical.py`, yeni bir filtre algoritması YOK).
  Yalnızca `Swath003_Array02.ogpr` için canonical. Bkz.
  [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]].
- **(Sprint 4A, 2026-07-15)** Background removal, en bilimsel açıdan
  riskli filtre — gerçek uzun/yatay bir yansımayı ortak-mod gürültüden
  ayırt edemez. Kanal-bazlı bağımsız hesaplama (kanallar hiçbir zaman
  birleştirilmez); trace-spacing hiçbir zaman sabit gömülü değil
  (geolocation → metadata → unavailable önceliği); pencere dönüşümü
  her zaman tek sayıya yuvarlanır ve ayrı ayrı kaydedilir; edge modu
  `reflect`/`nearest` (asla sıfır-padding). 8 aday çalıştırıldı, **hiçbiri
  canonical seçilmedi**. Bkz.
  [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].

## Bilinen riskler
- EPSG:32632 coğrafi olarak Orta Avrupa/İtalya'yı kapsar; gerçek saha bağlamı (Marmara Ereğlisi, Türkiye) ile uyuşmuyor olabilir.
- Derinlik değerleri sadece metadata hız varsayımına (0.1 m/ns) dayanıyor.
- **(Sprint 2.1'de çözüldü)** Gerçek dosyada eski varsayılan
  `max_shift_samples=64` + `target_sample=0` ile 9/11 kanal sessizce
  kırpılıyordu (bkz. [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-006,
  resolved). Yeni varsayılan (`overflow_policy="error"`) bunu artık
  sessizce yapmıyor.
- **(Sprint 2.2'de mühendislik önerisiyle çözüldü)** `target_sample=0` vs
  `16` — `target_sample=16` ölçülen trade-off'lara dayanarak öneri olarak
  kaydedildi ve canonical çıktı üretildi; bu fiziksel bir kalibrasyon
  iddiası DEĞİLDİR (bkz. [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-008).
- **(Açık)** Mean vs median DC offset, gerçek veride bazı kanallarda işaret
  değiştiriyor (bkz. ISSUE-009) — jeofizik ekibiyle doğrulanmamış.
- **(Sprint 3 canonicalization'da çözüldü)** Hangi dewow penceresinin
  (D1-D4) ve hangi band-pass aralığının (B1-B4) canonical olacağı artık
  kullanıcının insan/jeofizik kararıyla çözüldü: D2 + B1 (bkz. ISSUE-010
  resolved, ISSUE-011 resolved,
  [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]). Bu seçim yalnızca
  `Swath003_Array02.ogpr` için geçerlidir.
- **(Sprint 3.1'de bulundu, belgelendi)** B2'nin geç-zaman (20-100ns)
  penceresindeki ham medyan-iz gecikmesi (40 örnek) gerçek bir faz kayması
  DEĞİLDİR — spektral farklılıktan kaynaklanan bir ölçüm sınırlamasıdır;
  yetkili kanıt tam-segment lag'i (=0, her iki aday için). Bkz.
  `outputs/sprint03_1/PHASE_METRICS_INTERPRETATION_NOTES.md`.
- **(Sprint 4A'da açık, karar bekleyen konu)** 8 background-removal
  adayından hangisinin (varsa) canonical seçileceği henüz karar
  verilmedi — bu proje bu seçimi otomatik yapmaz. Bu veri setinde tüm 8
  adayın removed component'i yüksek mekânsal koherans gösteriyor (0.83-
  1.0), yani her aday, gerçek uzun/yatay bir yansımayı bastırma riski
  taşıyor. Bkz. [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].
- **(Sprint 4A.1'de bulundu, 2026-07-16)** Paired-control sentetik deneyi:
  tüm 8 adayın `paired_control_long_target_retention` değeri ≈
  0.00007-0.017 — yani hiçbir aday uzun bir sentetik hedefi korumuyor,
  `overall_rms_retention_tendency` (0.62-0.77) bu riski GİZLİYORDU. A1/A2
  bu çelişkiyi (`CONFLICT`) tetikliyor. Bu bir kod hatası değil, bilimsel
  bir bulgu.
- **(Sprint 4A.2'de bulundu ve düzeltildi, 2026-07-16)** Sprint 4A.1'in
  KENDİ `localized_hyperbola` sentetik senaryosu bir sentetik-veri-üretim
  hatası içeriyordu (sabit `curvature=0.03` + kısa hedef → `depth_shift`
  her yerde 0'a yuvarlanıyordu, yani "hiperbol" pratikte düz bir olaydı).
  Bu bir jeofizik bulgu değil, düzeltilmiş bir kod hatasıydı — düzeltme
  sonrası hiperbol gerçekten eğri (7 farklı merkez-sample, 12 örnek
  maksimum kayma). "No background removal" (A0) artık insan reviewer için
  geçerli, açıkça belgelenmiş bir karar seçeneği; background removal
  canonical olmak ZORUNDA değil.
- Detay: [[01_PROJECT_STATE/04_Risks_and_Limitations]]

## Kesinlikle yapılmaması gerekenler
- Ham `.ogpr` dosyalarını değiştirme/üzerine yazma.
- Binary offset'leri koda sabit gömme.
- CRS bilgisini doğrulanmış kabul etme veya otomatik reproject etme.
- Otomatik time-zero pick'ini doğrulanmış fiziksel yüzey zamanı olarak sunma.
- Sprint kapsamı dışındaki işlem algoritmalarını (gain, migration, F-K, PCA/SVD background removal, vb.) uygulama.
- Bir dewow, band-pass, veya background-removal adayını OTOMATİK olarak canonical seçme.
- Tamamlanmamış özellikleri tamamlanmış gibi gösterme.
- Sprint 4A'nın 8 adayından biri canonical seçilmeden Gain'e başlama.

Tam liste: proje kökündeki `CLAUDE.md`.

## Bir sonraki görev
Bir kod görevi DEĞİL: **Human review of corrected hyperbola QC, A0
baseline, and common-scale real-data montages.** (`BACKGROUND_OUTPUT_
COMPARISON_CH00_CH05_CH10.png`, `BACKGROUND_REMOVED_COMPARISON_CH00_
CH05_CH10.png`, `BACKGROUND_METRICS_SUMMARY.png`, `PAIRED_CONTROL_
HYPERBOLA_VALIDATION.png`, `BACKGROUND_FINAL_DECISION_REQUIRED.md` — bkz.
[[01_PROJECT_STATE/02_Next_Development_Sprint]]). 8 adaydan birinin (veya
A0'ın, "hiç background removal yapmama") canonical seçilmesi, tek başına,
Gain'i otomatik olarak BAŞLATMAZ.

## Önce okunması gereken bağlantılar
1. Bu dosya
2. [[01_PROJECT_STATE/01_Current_Project_State]]
3. [[01_PROJECT_STATE/02_Next_Development_Sprint]]
4. [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]
5. [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]]
