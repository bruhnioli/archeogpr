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
Aktif bir sprint YOK. Sprint 3 ([[02_SPRINTS/Sprint_03_Dewow_Bandpass]])
ve Sprint 3.1 ([[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]]) her
ikisi de **done**. D2 dewow adayı Sprint 3.1'de 4/4 koşulla ayrıntılı
doğrulanmış, B1/B2 band-pass adayları karar-odaklı QC ile karşılaştırılmış
(mühendislik eğilimi: preservation-favoring/B1) idi; **2026-07-15'te
kullanıcı bu önerileri insan/jeofizik kararı olarak onayladı: D2 dewow +
B1 band-pass canonical** — bkz.
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]. Sprint 2, Sprint 2.1 ve Sprint 2.2
durumları da `done` — bkz. [[02_SPRINTS/Sprint_02_TimeZero_DCOffset]],
[[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]],
[[02_SPRINTS/Sprint_02_2_TimeAxis_DCWindow_Validation]]. Sprint 4 hâlâ
TANIMLANMADI — bu karar, tek başına, Sprint 4'ü otomatik olarak AÇMAZ.

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
  [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]. Sprint 4 hâlâ
  tanımlanmadı/başlatılmadı — bu karar tek başına Sprint 4'ü açmaz.

## Henüz uygulanmayan özellikler
Background removal, gain, AGC, F-K filtering, migration, Hilbert envelope,
depth-slice üretimi, anomaly detection, arkeolojik sınıflandırma, Blender
export, GUI. Hiçbiri için sahte/yarım implementasyon yok — sadece
`05_PROCESSING/` altında gelecek için planlanan API bağlamı var (bkz.
[[05_PROCESSING/Processing_Index]]).

## Mevcut kod mimarisi
`src/archaeogpr/{io,model,processing,qc,export}` + `cli.py`. Detay:
[[03_ARCHITECTURE/Architecture_Overview]], [[03_ARCHITECTURE/Repository_Map]],
[[03_ARCHITECTURE/Processing_Pipeline_Architecture]].

## Doğrulanan gerçek veri seti
`Swath003_Array02.ogpr` (`data/raw/Swath003_Array02.ogpr`, 8,010,373 byte,
SHA-256 `66d840c3...b62a6` — Sprint 1'den bu yana, tüm Sprint 2.1/2.2/3/
3.1/canonicalization çalıştırmaları dahil, değişmedi). Shape
`(175, 11, 1024)`, float32, 600 MHz, horizontal polarization, geolocation
mevcut. Canonical işlenmiş türev (Sprint 2): `outputs/sprint02/
canonical_target16/` (Sprint 2.2, SHA-256 `b2770b5c...af5afe`, Sprint
3/3.1/canonicalization boyunca değişmedi). Sprint 3 aday karşılaştırmaları:
`outputs/sprint03/{dewow_candidates,bandpass_candidates,
combined_candidates,spectrum}/` (202 dosya, tarihsel QC kanıtı — hiçbiri
canonical değil). Sprint 3.1 D2 doğrulama + B1/B2 karar QC'si:
`outputs/sprint03_1/` (24 dosya, tarihsel QC kanıtı — hiçbiri canonical
değil). **Canonical Sprint 3 çıktısı (2026-07-15): `outputs/sprint03/
canonical_D2_B1/`** (15 dosya, D2+B1, insan/jeofizik kararı — bkz.
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]). Eski türevler
(`outputs/sprint02/combined/`, `outputs/sprint02_review/`) korundu,
sidecar notlarla süperseded olarak işaretlendi. Detay:
[[04_DATASETS/Swath003_Array02]].

## Test durumu
`pytest` → **254 passed, 0 failed, 0 skipped** (2026-07-15, gerçek dosya
mevcutken çalıştırıldı: 232 önceki + 22 yeni canonicalization testi).
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
- İşleme: `src/archaeogpr/processing/{common,time_zero,dc_offset,dewow,bandpass}.py`
- QC: `src/archaeogpr/qc/{time_zero,dc_offset,spectrum,dewow,bandpass,
  spatial_coherence,phase_metrics,band_energy,decision_qc}.py`
- Sprint 3 yükleyici/orkestrasyon: `src/archaeogpr/export/sprint3.py`, `src/archaeogpr/sprint3_candidates.py`
- Sprint 3 canonicalization: `src/archaeogpr/sprint3_canonical.py`
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
  eski: `outputs/sprint02/combined/`, `outputs/sprint02_review/`
- Karşılaştırma/doğrulama script'leri:
  `scripts/generate_sprint2_1_review_comparison.py`,
  `scripts/generate_sprint2_2_validation.py`,
  `scripts/generate_sprint3_1_decision_qc.py`
- Canonicalization testleri: `tests/test_sprint3_canonical.py`,
  `tests/test_cli_sprint3_canonical.py`
- Aday konfigürasyonları: `configs/{dewow,bandpass}_candidates.yaml`
- Vault: `obsidian/ArchaeoGPR_Vault/`

## Bir sonraki somut görev
Bir kod görevi DEĞİL: **kullanıcının kendi açık isteğiyle Sprint 4'ü
tanımlaması**. D2 (dewow) + B1 (band-pass) 2026-07-15'te canonical
seçildi (bkz. [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]), ama bu
tek başına Sprint 4'ü AÇMAZ. Detay:
[[01_PROJECT_STATE/02_Next_Development_Sprint]].

## Son güncelleme tarihi
2026-07-15
