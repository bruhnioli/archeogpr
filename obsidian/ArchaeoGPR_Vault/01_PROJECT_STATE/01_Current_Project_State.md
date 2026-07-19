---
type: project-state
tags: [project-state]
---

# Current Project State

Bu belge kısa, güncel ve operasyoneldir. Uzun tarihçe burada tutulmaz —
geçmiş oturumlar için [[08_SESSION_LOGS/Session_Index]]'e bakın.

## Projenin amacı
IDS GeoRadar tarafından üretilen OpenGPR `.ogpr` dosyalarını okuyan,
doğrulayan ve arkeolojik GPR görselleştirmesi için temel QC çıktıları üreten
modüler bir Python yazılımı geliştirmek. Sinyal işleme algoritmaları
sırayla, sprint bazında ve açıkça istenmeden eklenmiyor (bkz. `CLAUDE.md`).

## Mevcut sprint
**Sprint 4A** ([[02_SPRINTS/Sprint_04A_Background_Removal]]) —
**done** (2026-07-16'da kapandı). Dört background-removal yöntemi
(global_mean/global_median/sliding_mean/sliding_median) implemente
edildi; 8 aday (A1-A8) canonical Sprint 3 çıktısı (D2+B1) üzerinde
gerçek veride çalıştırıldı, sinyal-koruma + removed-component
metrikleri hesaplandı, 5 synthetic bilimsel-risk deneyi çalıştırıldı.
**İnsan/jeofizik kararı: canonical policy = A0 (background removal
uygulanmadı) — A1-A8'den hiçbiri canonical seçilmedi, Gain
başlatılmadı** — bkz.
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]].
Sprint 3 ([[02_SPRINTS/Sprint_03_Dewow_Bandpass]]) ve Sprint 3.1
([[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]]) her ikisi de
**done** — 2026-07-15'te kullanıcı D2 dewow + B1 band-pass'i insan/
jeofizik kararı olarak canonical seçti (bkz.
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]). Sprint 2, Sprint 2.1
ve Sprint 2.2 durumları da `done` — bkz.
[[02_SPRINTS/Sprint_02_TimeZero_DCOffset]],
[[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]],
[[02_SPRINTS/Sprint_02_2_TimeAxis_DCWindow_Validation]].

Bunun yanında, kullanıcının ayrı isteğiyle başlayan **GUI/3D dönüşüm
track'i** altı sprint ilerledi. **GUI-0/GUI-1/GUI-2 `main`'e merge edildi**
(2026-07-18, PR #2, merge commit `009fb9d`); **GUI-1B `main`'e merge
edildi** (2026-07-18, PR #3, merge commit `870f0c8`); **GUI-3A `main`'e
merge edildi** (2026-07-19, PR #4, merge commit `f3e516c`): **Sprint
GUI-0** ([[02_SPRINTS/Sprint_GUI_0_Foundation]], done, yalnızca audit/ADR/
mimari tasarım, kod yok), **Sprint GUI-1**
([[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]], done, native PySide6 viewer +
Windows executable), **Sprint GUI-2**
([[02_SPRINTS/Sprint_GUI_2_Display_Controls]], done, kontrast/colormap/
A-scan modları/PNG export, `0.2.0`), **Sprint GUI-1B**
([[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]], done, background
file-loading worker, `0.2.1`), **Sprint GUI-3A**
([[02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply]], done, 5 stabil
processing fonksiyonu artık GUI'de non-destructive preview→apply ile
kullanılabiliyor — undo/redo/recipe/gain/3D YOK, `0.3.0`). **Sprint 3D-0**
([[02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector]], done, survey
geometry inspector + C-scan/3D readiness raporlama — index/local/global
koordinat çözümü, alan-bazlı provenance, 2D plan view, geometry report
export, `0.4.0`; volume render/PyVista/gerçek C-scan YOK) henüz **merge
edilmedi**, kullanıcının onayı bekleniyor. Sprint 4B (Gain, yukarıda) ile
bu GUI track'i birbirinden bağımsız, paralel track'lerdir — biri diğerini
başlatmaz veya değiştirmez. Bkz.
[[06_DECISIONS/ADR_011_GUI_Technology_Decision]],
[[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]],
[[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]],
[[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]].

## Tamamlanan özellikler
**Sprint 1:** OpenGPR header/preamble okuyucu, Radar Volume + Sample
Geolocations binary blok okuyucuları, `GPRDataset` immutable veri modeli,
türetilmiş metadata, temel QC görselleri/exportlar, `inspect`/`header` CLI.

**Sprint 2:**
- `correct_time_zero()` — `manual`, `channel_median_peak`,
  `channel_median_cross_correlation` yöntemleri; kanal-bazlı sabit shift;
  `np.roll` + `fill_value` ile padding, wrap-around yok.
- `correct_dc_offset()` — `mean`/`median`, opsiyonel pencere, her trace
  bağımsız düzeltilir.
- `ProcessingResult` (dataset + removed_component + diagnostics + warnings);
  `removed_component := input - output` her zaman tam olarak geçerli.
- QC: median trace overlay, picks/shifts grafiği, before/after/difference
  B-scan (paylaşılan clip), ofset histogramı/boxplot'u, trace-mean karşılaştırması.
- Export: `channel_picks.csv`, `offsets.csv`, `processing_metadata.json`,
  `*_corrected.npz`, birleşik `sprint02_processed.npz`/`processing_history.json`/`sprint02_summary.json`.
- CLI: `time-zero`, `dc-offset`, `sprint2` alt komutları.
- 41 yeni sentetik/entegrasyon testi (toplam 77).

**Sprint 2.1** (review_required — kod tamam, insan incelemesi bekleniyor):
- `overflow_policy: Literal["error","clip"]` — varsayılan `"error"`
  (veriye dokunmadan hata); kırpma yalnızca açık opt-in, sonuç
  `valid_for_downstream_processing=False` işaretlenir.
- `ProcessingResult.valid_mask` — time-zero'nun padding bölgesini
  işaretleyen `(channels, samples)` bool, salt-okunur maske.
- `correct_dc_offset(..., valid_mask=...)` — padding'i hem ofset
  hesaplamasından hem çıkarmadan hariç tutar (Sprint 2'de bulunan bir
  padding-kirlenmesi hatası düzeltildi, gerçek veride doğrulandı).
- CLI: `--overflow-policy`, `padding_mask_channelNN.png`,
  `valid_sample_summary.json`; `sprint2` komutu artık `valid_mask`'ı
  otomatik geçiriyor.
- Gerçek veride `target_sample=0` vs `16` karşılaştırması
  (`max_shift_samples=96`, sıfır kırpma); karşılaştırma çıktıları +
  `REVIEW_REQUIRED.md` — nihai seçim bu sprintte yapılmadı.
- 24 yeni test (toplam 101).

**Sprint 2.2** (done):
- `correct_time_zero()`'nun çıktı `time_ns`'i time-zero-relative üretiliyor
  (`time_ns[target_sample]==0.0`); `sampling_time_ns` her yöntem için
  zorunlu.
- `correct_dc_offset(..., window_reference="dataset_time")` (varsayılan) —
  pencere, zaman eksenine göre çözülür; `target_sample`'dan bağımsız olarak
  AYNI ham örnekleri seçer (gerçek veride fark=0.0 doğrulandı).
- Canonical DC politikası: `method="mean", window=[20,100) ns` (CLI
  varsayılanı, fonksiyona sabit gömülü değil).
- `target_sample=16` mühendislik önerisi olarak kaydedildi (fiziksel iddia
  DEĞİL); canonical çıktı: `outputs/sprint02/canonical_target16/`.
- 22 yeni test (toplam 123). Sprint 2 ve Sprint 2.1 durumları `done`'a
  döndü.

**Sprint 3** (done — D2+B1 canonical seçildi, bkz. Sprint 3 Canonicalization aşağıda):
- `correct_dewow()` — `running_mean`/`running_median`, pencere dönüşümü
  (çift→tek yuvarlama, hiçbir zaman sessiz), `reflect`/`nearest` kenar
  modu, her ardışık geçerli segment bağımsız işlenir (paylaşılan
  `contiguous_true_runs()`).
- `correct_bandpass()` — zero-phase Butterworth (SOS + `sosfiltfilt`) ve
  Ormsby (gerçek yamuk transfer fonksiyonu, FFT); sıfır-faz hem sentetik
  hem gerçek veride pik-kayması + medyan-iz çapraz-korelasyon gecikmesiyle
  doğrulandı (gecikme=0).
- `compute_amplitude_spectrum()` — genlik (asla güç) spektrumu, gerçek
  frekans ekseni/Nyquist, mean/median/RMS agregasyon, Hann taper, sabit
  detrend; QC metrikleri hiçbir zaman fiziksel bir antena-bandı iddiası
  olarak sunulmaz.
- `read_processed_npz()` — güvenli (`allow_pickle=False`) NPZ yükleyici;
  eksik alan/geçersiz JSON/sıra-dışı history/valid_mask şekil uyuşmazlığı
  için açık hata.
- Aday karşılaştırmaları: dewow D1-D4, band-pass B1-B4 (D2 tabanında),
  kombine C1-C6 — `outputs/sprint03/` (209 dosya). **Hiçbiri canonical
  seçilmedi.**
- CLI: `dewow`, `bandpass`, `sprint3-candidates` alt komutları (hepsi
  `Canonical selected: false` basar).
- 86 yeni test (toplam 209). Sprint 4 tanımlanmadı/başlatılmadı.

**Sprint 3.1** (done — D2 doğrulandı, B1 seçildi, bkz. Sprint 3 Canonicalization aşağıda):
- D2'nin removed component'i pencere-bazlı (5 zaman penceresi × kanal
  0/5/10) B-scan incelemesiyle doğrulandı; 4/4 koşul geçti
  (`recommended_dewow_candidate = D2`, mühendislik önerisi).
- Yalnızca B1/B2 band-pass adayları (B3/B4 hariç) karar-odaklı QC ile
  karşılaştırıldı: mutlak/ortak-dB/kendi-piki-normalize spektrum, frekans-
  bandı enerji tabloları, mekânsal süreklilik metrikleri, faz/waveform
  koruması (doğrudan dalga + geç-zaman).
- Önemli bulgu: B2'nin geç-zaman penceresindeki ham medyan-iz gecikmesi
  (40 örnek) spektral farklılıktan kaynaklanan bir ölçüm sınırlamasıdır,
  gerçek faz kayması DEĞİLDİR — yetkili kanıt (tam-segment lag=0) hâlâ
  geçerlidir.
- Mühendislik eğilimi: preservation-favoring (B1) — kesin seçim
  YAPILMADI.
- `outputs/sprint03_1/` (24 dosya): `DECISION_PANEL_D2_B1_B2.png`,
  `BANDPASS_FINAL_DECISION_REQUIRED.md`, `D2_DEWOW_DECISION.md`, +.
- 23 yeni test (toplam 232). Sprint 4 tanımlanmadı/başlatılmadı.

**Sprint 3 Canonicalization** (done — 2026-07-15):
- Kullanıcı, Sprint 3.1'in mühendislik önerisini/eğilimini insan/jeofizik
  kararı olarak onayladı: **D2** dewow (`running_mean`, 8.125 ns
  uygulanan/65 örnek, `edge_mode=reflect`) + **B1** band-pass
  (Butterworth, 100-900 MHz, order=4, zero-phase).
- `sprint3_canonical.py::run_sprint3_canonical()` — `correct_dewow()`/
  `correct_bandpass()`'i D2/B1 sabit parametreleriyle çağırır (yeni bir
  filtre algoritması YOK); `write_canonical_processing_note()`.
- CLI: `sprint3` alt komutu — D2/B1 varsayılan, override edilirse
  `canonical selected: false` + uyarı basar. Ham dosya hash'i (`dataset.
  metadata["source_file"]["path"]`'ten türetilir) ve Sprint 2 canonical
  NPZ hash'i ayrı ayrı doğru raporlanır.
- Canonical çıktı: `outputs/sprint03/canonical_D2_B1/` (tam olarak 15
  dosya) — eski aday klasörleri (202 dosya) değişmeden kaldı.
- Doğrulandı: işleme geçmişi sırası
  `[time_zero_correction, dc_offset_correction, dewow_correction,
  bandpass_correction]`, faz gecikmesi=0, padding tam sıfır, girdi/ham
  dosya hash'i değişmedi, iki bağımsız çalıştırma bit-bazında özdeş.
- 22 yeni test (toplam 254). Bkz.
  [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]].

**Sprint 4A** (review_required — kod tamam, insan/jeofizik incelemesi bekleniyor):
- `remove_background()` — `global_mean`/`global_median`/`sliding_mean`/
  `sliding_median`, kanal-bazlı bağımsız (kanallar hiçbir zaman
  birleştirilmez); `compute_trace_spacing()` — geolocation → metadata
  `sampling_step_m` → `unavailable` önceliği, hiçbir zaman sabit gömülü.
- Pencere dönüşümü her zaman en yakın tek sayıya yuvarlanır, istenen/
  uygulanan değer ayrı ayrı kaydedilir; `reflect`/`nearest` edge modu
  (asla sıfır-padding); valid-mask/padding güvenliği (10 kural).
- 8 aday (A1-A8) canonical Sprint 3 çıktısı (D2+B1) üzerinde gerçek
  veride çalıştırıldı: A1/A2=global mean/median, A3-A5=sliding_mean
  (0.5/1.0/1.5 m), A6-A8=sliding_median (aynı pencereler).
  `outputs/sprint04a/` (8×18 dosya + karşılaştırma + karar paneli/rapor).
  **Hiçbir aday canonical seçilmedi, Gain başlatılmadı.**
- Sinyal-koruma + removed-component metrikleri (waveform/median-trace
  correlation, RMS/energy retention, spatial coherence/concentration,
  yeni QC-only `compute_localized_event_risk()` proxy'si — asla
  arkeolojik sınıflandırma yapmaz) + 5 synthetic bilimsel-risk deneyi.
- CLI: `background`, `sprint4a-candidates` alt komutları.
- 60 yeni test (toplam 314). Bkz.
  [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].

**Sprint 4A.1** (2026-07-16, PR #1 üzerinde):
- Karar QC düzeltmesi: pencere terminolojisi (`applied_window_nominal_
  length_m` vs `_center_to_center_span_m`), ortak-scale B-scan montajları
  (`BACKGROUND_OUTPUT_COMPARISON_CH00_CH05_CH10.png`, `BACKGROUND_
  REMOVED_COMPARISON_CH00_CH05_CH10.png`, `BACKGROUND_METRICS_
  SUMMARY.png`), `1 - coherence` "preservation" çerçevesinin kaldırılması.
- YENİ paired-control sentetik hedef-retention deneyi
  (`run_paired_control_target_attenuation_experiments()`) — **kritik
  bulgu:** tüm 8 aday uzun bir sentetik hedefi neredeyse tamamen yok
  ediyor (`paired_control_long_target_retention` ≈ 0.00007-0.017),
  yüksek `overall_rms_retention_tendency`ye (0.62-0.77) rağmen. A1/A2
  için `Engineering interpretation`'da açık `CONFLICT` bayrağı.
- Çekirdek `remove_background()` implementasyonu DEĞİŞMEDİ, Gain
  başlatılmadı, `main`'e doğrudan commit atılmadı.
- 14 yeni test (toplam 328). Bkz.
  [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]]
  "Sprint 4A.1 Correction" bölümü.

**Sprint 4A.2** (2026-07-16, aynı PR #1):
- `localized_hyperbola` sentetik hedefinin (sabit `curvature=0.03` +
  kısa hedef yüzünden) pratikte düz bir olay olduğu bulundu ve
  düzeltildi — `curvature` artık istenen bir maksimum kaymadan
  türetiliyor, gerçek bir `target_mask` döndürülüyor, retention apex/kol
  olarak ayrı raporlanıyor. Yeni `PAIRED_CONTROL_HYPERBOLA_
  VALIDATION.png`.
- Yeni **A0** (`no_background_removal`) — dokuzuncu bir filtre değil,
  karar/QC katmanında sabit değerli bir referans politikası; nihai karar
  tablosuna, metrics summary paneline, `candidate_metrics.csv`'ye
  eklendi (B-scan montajlarına DEĞİL, NPZ/ProcessingResult üretmiyor).
- 16 yeni test (toplam 342). Bkz.
  [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]]
  "Sprint 4A.2 Correction" bölümü.

**Sprint 4A Closure — insan kararı** (2026-07-16, aynı PR #1, sprint
`done` olarak kapandı):
- Timing metriği netleştirildi: `candidate_metrics.csv`'deki kolon
  `median_trace_cross_correlation_lag_proxy_w5` olarak yeniden
  adlandırıldı + nihai raporda açık bir açıklama eklendi (background
  removal örnek/zaman eksenini asla kaydırmaz; A1-A8'deki sıfır-olmayan
  lag değerleri programatik bir sample shift değil, waveform
  değişiminden dolayı korelasyon piki'nin başka bir lag'e geçmesidir).
- **İnsan/jeofizik nihai kararı: canonical background-removal policy =
  A0.** A1-A8'den hiçbiri canonical seçilmedi; canonical Sprint 3 (D2+B1)
  çıktısına background removal uygulanmayacak; yeni bir canonical NPZ
  üretilmedi; A1-A8 repository'de deneysel/opt-in araçlar olarak kaldı;
  Gain başlatılmadı. Bkz.
  [[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]],
  [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-012 (kapatıldı).

**Sprint GUI-0** (done — 2026-07-17, kod YOK, yalnızca tasarım):
- Repository audit + Obsidian vault audit + GPRPy (yalnızca referans,
  fork edilmedi/kod alınmadı) mimari incelemesi.
- 7 yeni vault belgesi: [[06_DECISIONS/ADR_011_GUI_Technology_Decision]]
  (PySide6 + PyQtGraph + opsiyonel PyVista/pyvistaqt kararı),
  [[03_ARCHITECTURE/GUI_Architecture]],
  [[03_ARCHITECTURE/3D_Volume_Data_Model]],
  [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]],
  [[09_REFERENCES/GPRPy_Reference_and_License_Notes]],
  [[01_PROJECT_STATE/06_GUI_3D_Risk_Register]],
  [[02_SPRINTS/Sprint_GUI_0_Foundation]].
- `pyproject.toml`: opsiyonel `gui`/`gui3d` bağımlılık grupları eklendi;
  `pytest` runtime `dependencies`'ten `dev` extra'sına taşındı (runtime
  kodunda `pytest` import'u olmadığı önce doğrulandı) — headless
  kurulum/CI davranışı değişmedi.
- `src/archaeogpr/gui/` **henüz yoktur**. Bkz.
  [[02_SPRINTS/Sprint_GUI_0_Foundation]].

## Henüz uygulanmayan özellikler
Gain, AGC, F-K filtering, migration, Hilbert envelope, depth-slice
üretimi, anomaly detection, arkeolojik sınıflandırma, Blender export.
Background removal implemente edildi ve repository'de deneysel/opt-in
bir araç olarak mevcut, ama **canonical policy = A0 (uygulanmadı)** —
bkz. Sprint 4A yukarıda,
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]].
Hiçbiri için sahte/yarım implementasyon yok — sadece `05_PROCESSING/`
altında gelecek için planlanan API bağlamı var (bkz.
[[05_PROCESSING/Processing_Index]]). **GUI artık çalışan runtime koduna
sahiptir** (native PySide6 viewer + Windows executable, `0.4.0`, bkz.
yukarıdaki GUI-0/GUI-1/GUI-2/GUI-1B/GUI-3A/3D-0 girdileri ve
[[03_ARCHITECTURE/GUI_Architecture]]). **Sprint GUI-3A ile 5 stabil
processing fonksiyonu (time-zero/DC offset/dewow/band-pass/background
removal) artık GUI'den preview→apply ile kullanılabiliyor** (non-
destructive, raw/current/preview ayrımı, bkz.
[[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]]). **Sprint
3D-0 ile survey geometry artık denetlenebiliyor** (index/local/global
koordinat çözümü, alan-bazlı provenance, 5 C-scan/3D readiness gate'i, 2D
plan view, geometry report export — bkz.
[[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]]) — ancak
gain, undo/redo, recipe, processed dataset kaydetme, ve gerçek C-scan/3D
volume render (PyVista/VTK, gridding/resampling, derinlik dönüşümü)
hiçbiri henüz yoktur; bu ayrım kasıtlı olarak korunuyor.

## Mevcut kod mimarisi
`src/archaeogpr/{io,model,processing,qc,export}` + `cli.py`. Detay:
[[03_ARCHITECTURE/Architecture_Overview]], [[03_ARCHITECTURE/Repository_Map]],
[[03_ARCHITECTURE/Processing_Pipeline_Architecture]].

## Doğrulanan gerçek veri seti
`Swath003_Array02.ogpr` (`data/raw/Swath003_Array02.ogpr`, 8,010,373 byte,
SHA-256 `66d840c3...b62a6` — Sprint 1'den bu yana, tüm Sprint 2.1/2.2/3/
3.1/canonicalization/4A çalıştırmaları dahil, değişmedi). Shape
`(175, 11, 1024)`, float32, 600 MHz, horizontal polarization, geolocation
mevcut. Canonical işlenmiş türev (Sprint 2): `outputs/sprint02/
canonical_target16/` (Sprint 2.2, SHA-256 `b2770b5c...af5afe`, Sprint
3/3.1/canonicalization/4A boyunca değişmedi). Sprint 3 aday
karşılaştırmaları: `outputs/sprint03/{dewow_candidates,bandpass_candidates,
combined_candidates,spectrum}/` (202 dosya, tarihsel QC kanıtı — hiçbiri
canonical değil). Sprint 3.1 D2 doğrulama + B1/B2 karar QC'si:
`outputs/sprint03_1/` (24 dosya, tarihsel QC kanıtı — hiçbiri canonical
değil). **Canonical Sprint 3 çıktısı (2026-07-15): `outputs/sprint03/
canonical_D2_B1/`** (15 dosya, D2+B1, insan/jeofizik kararı — bkz.
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]], SHA-256
`2044dd8f...82fd026`, Sprint 4A boyunca değişmedi). **Sprint 4A aday
karşılaştırmaları (2026-07-15): `outputs/sprint04a/`** (8 aday × 18
dosya + karşılaştırma + karar paneli/rapor, tarihsel QC kanıtı — hiçbiri
canonical değil, bkz.
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]]).
Eski türevler (`outputs/sprint02/combined/`, `outputs/sprint02_review/`)
korundu, sidecar notlarla süperseded olarak işaretlendi. Detay:
[[04_DATASETS/Swath003_Array02]].

## Test durumu
`pytest` → **344 passed, 0 failed, 0 skipped** (2026-07-16, Sprint 4A
Closure; gerçek dosya mevcutken çalıştırıldı: 314 (Sprint 4A) + 14
(Sprint 4A.1) + 16 (Sprint 4A.2) + 2 yeni kapanış testi (ADR-009 kaydı,
canonical zincirin `background_removal` içermediği)).
Detay: [[07_VALIDATION/Test_Results]].

## Bilinen hatalar
Şu anda bilinen bir AÇIK kod hatası yok. Bulunup düzeltilen kod hataları
(kayıt amaçlı): Sprint 2.1'de eski `correct_dc_offset()`'in time-zero
padding'ini kirletmesi (bkz. ISSUE-007); Sprint 2.2'de whole-trace DC
offset'in `target_sample`'a bağımlı (dolayısıyla fiziksel olarak kararsız)
bir istatistik olması (bkz.
[[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]]); Sprint
3'te `read_processed_npz()`'nin `valid_mask` şeklini `amplitudes`'e karşı
doğrulamıyor olması (yalnızca `ndim` kontrol ediliyordu, düzeltildi).
Sprint 3.1'de metodolojik bir bulgu (kod hatası değil): B2'nin geç-zaman
penceresindeki ham medyan-iz gecikmesi (40 örnek) spektral farklılıktan
kaynaklanıyor, gerçek faz kayması değil — bkz.
`outputs/sprint03_1/PHASE_METRICS_INTERPRETATION_NOTES.md`.
Açık sorunlar (hata değil, belirsizlik/karar bekleyen konular) için
[[01_PROJECT_STATE/03_Open_Issues]].

## Kritik varsayımlar
- Radar Volume için endianness header'da belirtilmiyor; little-endian
  varsayımı kod içinde belgelenmiş bir varsayım olarak kullanılıyor.
- Derinlik/elevation hesapları metadata'daki propagation velocity
  (0.1 m/ns) varsayımına dayanıyor; sahada doğrulanmadı.
- Sample Geolocations kaydının iç yapısı header'da tanımlı değil; gerçek
  dosyadan doğrulanarak çıkarıldı (bkz. [[03_ARCHITECTURE/OpenGPR_File_Structure]]).
- EPSG:32632 CRS bilgisi doğrulanmadan kullanılıyor (bkz. [[01_PROJECT_STATE/04_Risks_and_Limitations]]).
- Otomatik time-zero pick'i, doğrulanmış fiziksel yüzey zamanı DEĞİLDİR
  (bkz. [[06_DECISIONS/ADR_002_TimeZero_Reference_and_Shift_Policy]]).

## Önemli dosya yolları
- Okuyucu: `src/archaeogpr/io/ogpr_reader.py`
- Veri modeli: `src/archaeogpr/model/dataset.py`
- İşleme: `src/archaeogpr/processing/{common,time_zero,dc_offset,dewow,bandpass,background}.py`
- QC: `src/archaeogpr/qc/{time_zero,dc_offset,spectrum,dewow,bandpass,
  spatial_coherence,phase_metrics,band_energy,decision_qc,background}.py`
- Sprint 3 yükleyici/orkestrasyon: `src/archaeogpr/export/sprint3.py`, `src/archaeogpr/sprint3_candidates.py`
- Sprint 3 canonicalization: `src/archaeogpr/sprint3_canonical.py`
- Sprint 4A yazıcı/orkestrasyon: `src/archaeogpr/export/sprint4a.py`, `src/archaeogpr/sprint4a_candidates.py`
- CLI: `src/archaeogpr/cli.py`
- Gerçek örnek veri: `data/raw/Swath003_Array02.ogpr`
- QC çıktıları: `outputs/inspect/`, `outputs/sprint02/canonical_target16/`
  (Sprint 2 canonical), `outputs/sprint02_2_validation/` (target-invariance
  + DC window doğrulaması), `outputs/sprint03/{dewow_candidates,
  bandpass_candidates,combined_candidates,spectrum}/` (Sprint 3 aday
  karşılaştırmaları, tarihsel QC kanıtı — hiçbiri canonical değil),
  `outputs/sprint03_1/` (Sprint 3.1 D2 doğrulama + B1/B2 karar QC'si,
  tarihsel QC kanıtı — hiçbiri canonical değil),
  `outputs/sprint03/canonical_D2_B1/` (**Sprint 3 canonical çıktısı, D2+B1**),
  `outputs/sprint04a/` (Sprint 4A 8 background-removal adayı, tarihsel QC
  kanıtı — hiçbiri canonical değil),
  eski: `outputs/sprint02/combined/`, `outputs/sprint02_review/`
- Karşılaştırma/doğrulama script'leri:
  `scripts/generate_sprint2_1_review_comparison.py`,
  `scripts/generate_sprint2_2_validation.py`,
  `scripts/generate_sprint3_1_decision_qc.py`
- Canonicalization testleri: `tests/test_sprint3_canonical.py`,
  `tests/test_cli_sprint3_canonical.py`
- Sprint 4A testleri: `tests/test_background.py`,
  `tests/test_background_qc.py`, `tests/test_sprint4a_pipeline.py`,
  `tests/test_sprint4a_real_integration.py`
- Sprint 4A.1 testleri: `tests/test_sprint4a_candidates.py` (yeni)
- Aday konfigürasyonları: `configs/{dewow,bandpass,background}_candidates.yaml`
- Vault: `obsidian/ArchaeoGPR_Vault/`

## Bir sonraki somut görev
Bir kod görevi DEĞİL: Sprint 4A kapandı, canonical policy = A0 (bkz.
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]]). Sprint
4B (Gain veya başka bir kapsam) henüz TANIMLANMADI ve kullanıcının kendi
açık isteği olmadan BAŞLATILMAYACAK. Detay:
[[01_PROJECT_STATE/02_Next_Development_Sprint]].

## Son güncelleme tarihi
2026-07-19 (Sprint 3D-0 — survey geometry inspector ve C-scan readiness,
`0.4.0`, henüz merge edilmedi, kullanıcının onayı bekleniyor; Sprint
GUI-3A 2026-07-19'da `main`'e merge edildi, PR #4, commit `f3e516c`,
`0.3.0`; GUI-1B 2026-07-18'de `main`'e merge edildi, `0.2.1`; en son
processing/sinyal-işleme sprinti hâlâ Sprint 4A Closure, 2026-07-16)
