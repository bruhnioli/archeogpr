---
type: dataset
tags: [dataset]
format: OpenGPR
swath: Swath003
array: "02"
status: validated
crs_status: unvalidated
processing_status: unknown
---

# Dataset — Swath003_Array02

Bu notun tüm sayısal değerleri gerçek parser/CLI çıktısından alınmıştır
(`python -m archaeogpr inspect data/raw/Swath003_Array02.ogpr --output-dir outputs/inspect`,
2026-07-14). Elle varsayım yapılmamıştır.

## Kaynak dosya
- Ad: `Swath003_Array02.ogpr`
- Konum (bu repo içinde, salt okunur): `data/raw/Swath003_Array02.ogpr`
- Dosya boyutu: 8,010,373 byte
- SHA-256: `66d840c313b4beed10bea2e35d88431573f6fab0f02bba17792c0920028b62a6`
- OpenGPR version: 2.0
- Header checksum (dosyadan okunan, bağımsız doğrulanmadı): `4e014092a258c4485afd1c5f717948b1`
- Swath name / ID: `Swath003` / `828f7c62c2d1949daed0be4168f29c30`
- Array ID: `2` (header'da integer; dosya adı kuralına göre `02` olarak gösterilir)

## Boyutlar ve dtype
- Shape (`slice, channel, sample`): `(175, 11, 1024)`
- Slice count: 175
- Channel count: 11
- Sample count: 1024
- Dtype: `float32` (little-endian)

## Sampling ve frekans
- Sampling time: 0.125 ns
- Sampling step: ≈ 0.04008848472894169 m
- Time window: 128.0 ns (= 1024 × 0.125 ns)
- Nominal frequency: 600 MHz (header'da `fequency_MHz` typo alanından okundu)
- Polarization: horizontal

## Hız ve derinlik (metadata varsayımına dayalı — bkz. uyarı)
- Metadata propagation velocity: 100,000,000 m/s (= 0.1 m/ns)
- Yaklaşık depth-per-sample: 0.00625 m
- Yaklaşık maximum depth: 6.4 m
- **Uyarı:** bu derinlik değerleri sahada ölçülmüş bir hıza değil, dosya
  metadata'sındaki hız varsayımına dayanır; ground-truth ile doğrulanmadı.
  Bkz. [[01_PROJECT_STATE/03_Open_Issues]] (ISSUE-004).

## Geometri
- Profile length (tahmini): ≈ 6.972058 m
- Along-track spacing (median): ≈ 0.040296 m
- Cross-channel spacing (median): ≈ 0.074957 m
- Swath width (tahmini): ≈ 0.749566 m
- X aralığı: 614325.8070 – 614331.5392
- Y aralığı: 4840256.9930 – 4840262.1542
- Elevation aralığı: 45.0436 – 51.5880 m

## CRS bilgisi
- Header'daki `srs`: `{"type": "EPSG", "value": 32632}` (UTM Zone 32N)
- **CRS doğrulama uyarısı:** Bu değer dosyadan olduğu gibi okunmuştur,
  bağımsız doğrulanmamıştır ve reprojection yapılmamıştır. EPSG:32632
  coğrafi olarak ~6–12°E (İtalya/Orta Avrupa) kapsar; projenin bilinen
  saha bağlamı (Marmara Ereğlisi, Türkiye, ~35–37N UTM) ile uyuşmuyor
  olabilir. Bkz. [[01_PROJECT_STATE/04_Risks_and_Limitations]] (madde 1),
  [[01_PROJECT_STATE/03_Open_Issues]] (ISSUE-001).

## Processing metadata
Header'daki `dataBlockDescriptors[0].metadata.processing` alanı: `null`.
Verinin ekipman tarafında hangi işlemlerden geçtiğine dair bir kayıt yok —
bu `processing_status: unknown` frontmatter alanı HAM dosyanın kendi
bilinmeyen geçmişini ifade eder ve Sprint 2'den sonra da değişmez. Bu proje
artık işlenmiş türevler üretiyor (aşağıya bakın), ama bunlar `data/raw/`
altındaki ham dosyayı hiçbir şekilde değiştirmiyor.

## İşlenmiş Türevler (Sprint 2 — Time-Zero & DC Offset)
Gerçek CLI çalıştırmasından alınan değerler (`--method channel-median-peak
--search-start-ns 5 --search-end-ns 15 --peak-polarity max-abs
--target-sample 0`, varsayılan `max_shift_samples=64`):

| Kanal | Picked sample | Shift (samples) | Kırpıldı mı? |
|---|---|---|---|
| 00 | 73 | -64 | Evet (gerçek: -73) |
| 01 | 69 | -64 | Evet (gerçek: -69) |
| 02 | 74 | -64 | Evet (gerçek: -74) |
| 03 | 61 | -61 | Hayır |
| 04 | 73 | -64 | Evet (gerçek: -73) |
| 05 | 69 | -64 | Evet (gerçek: -69) |
| 06 | 74 | -64 | Evet (gerçek: -74) |
| 07 | 68 | -64 | Evet (gerçek: -68) |
| 08 | 73 | -64 | Evet (gerçek: -73) |
| 09 | 61 | -61 | Hayır |
| 10 | 74 | -64 | Evet (gerçek: -74) |

9/11 kanal varsayılan `max_shift_samples=64` sınırını aştığı için kırpıldı.
**Otomatik pick, doğrulanmış fiziksel yüzey zamanı değildir** (bkz.
[[06_DECISIONS/ADR_002_TimeZero_Reference_and_Shift_Policy]]).

> **Sprint 2.1 güncellemesi (2026-07-15):** Yukarıdaki tablo, artık
> supersede edilmiş bir davranışı (sessiz varsayılan kırpma) yansıtıyor —
> tarihsel kayıt olarak değiştirilmedi. Sprint 2.1'de `max_shift_samples=96,
> overflow_policy=error` ile aynı pick'ler (61–74) hem `target_sample=0`
> hem `target_sample=16` için **sıfır kırpma** verdi (tüm kanallarda
> `applied_shift == requested_shift`). Hangi `target_sample`'ın
> kullanılacağı henüz seçilmedi — bkz.
> [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-006 (kırpma, resolved) ve
> ISSUE-008 (target_sample seçimi, open),
> [[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]],
> `outputs/sprint02_review/REVIEW_REQUIRED.md`.

> **Sprint 2.2 güncellemesi (2026-07-15):** `target_sample=16`, ölçülen
> trade-off'lara dayanarak mühendislik önerisi olarak kaydedildi ve
> canonical çıktı üretildi: `outputs/sprint02/canonical_target16/`
> (bkz. [[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]]).
> Ayrıca, DC offset artık zaman-referanslı (time-zero-relative) sabit bir
> `[20,100)` ns penceresi kullanıyor — bu, gerçek veride `target_sample`'a
> bağımsız (fark=0.0) olduğu doğrulanan bir DC offset üretir; aşağıdaki
> "DC offset (method=mean, tüm iz...)" satırı ESKİ (whole-trace, Sprint 2)
> davranışı yansıtır ve artık canonical DEĞİLDİR. Bkz.
> [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-008 (resolved) ve ISSUE-009
> (mean vs median belirsizliği, open).

DC offset (method=mean, tüm iz, ham veri üzerinde bağımsız çalıştırma):
offset min=-138.14, max=568.56, mean=270.36 (ham genlik ortalamasıyla
birebir eşleşir — çapraz doğrulama), median=312.61, std=120.47. Pencereli
(method=median, 20–100 ns): offset mean=13.96 — tüm-iz değerinden belirgin
şekilde farklı, pencerenin doğru kullanıldığını doğrular.

Birleşik pipeline (time-zero → dc-offset) sonrası trace mean'ler ~1e-4
büyüklüğüne düştü (pratik olarak sıfır). Tam detay:
[[02_SPRINTS/Sprint_02_TimeZero_DCOffset]], [[07_VALIDATION/QC_Output_Validation]].

## İşlenmiş Türevler (Sprint 3 — Dewow & Band-Pass Aday Karşılaştırmaları)
Canonical Sprint 2 çıktısı (`outputs/sprint02/canonical_target16/
sprint02_processed.npz`) üzerinde dört dewow adayı (D1-D4) ve dört
band-pass adayı (B1-B4, D2 tabanında) çalıştırıldı ve karşılaştırıldı —
karşılaştırma aşamasında hiçbiri canonical seçilmedi (bkz. aşağıdaki
canonicalization bölümü için nihai insan kararı). Ölçülen düşük-frekans
enerji oranı (dewow sonrası): D1=0.7440, D2=0.8785, D3=0.5587,
D4=0.9392. Tüm 10 band-pass/kombine adayında medyan-iz çapraz-korelasyon
gecikmesi gerçek veride **tam olarak 0** (sıfır-faz doğrulaması).
Geçiş-bandı enerji korunumu: B1≈99.2%, B2≈99.1%, B3≈98.4%, B4≈95.4%. Tam
detay: [[02_SPRINTS/Sprint_03_Dewow_Bandpass]],
[[07_VALIDATION/QC_Output_Validation]].

## İşlenmiş Türevler (Sprint 3 Canonicalization — D2 + B1, 2026-07-15)
Kullanıcı, Sprint 3.1'in mühendislik önerisini/eğilimini insan/jeofizik
kararı olarak onayladı: **D2** dewow (`running_mean`, 8.125 ns/65 örnek,
`edge_mode=reflect`) + **B1** band-pass (Butterworth, 100-900 MHz,
order=4, zero-phase). Canonical zincir: Sprint 2 canonical
(`target_sample=16`) → D2 → B1. Canonical çıktı:
`outputs/sprint03/canonical_D2_B1/` (15 dosya:
`sprint03_processed.npz`, işleme geçmişi/metadata/padding/faz doğrulama
JSON'ları, canonical parametre JSON'u, 8 QC PNG'si,
`CANONICAL_PROCESSING_NOTE.md`). Doğrulanan sonuçlar: ham dosya hash'i ve
Sprint 2 canonical NPZ hash'i değişmedi, işleme geçmişi sırası tam olarak
`[time_zero_correction, dc_offset_correction, dewow_correction,
bandpass_correction]`, padding tam sıfır, `confirmed_zero_phase=true`
(`max_abs_median_trace_cross_correlation_lag=0`). Bu seçim yalnızca bu
veri seti için canonical — başka bir veri seti kendi aday karşılaştırmasını
ve kendi insan/jeofizik incelemesini gerektirir. Tam detay:
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
[[07_VALIDATION/QC_Output_Validation]].

## Amplitude statistics (ham, gain uygulanmamış)
| İstatistik | Değer |
|---|---|
| min | -490287.65625 |
| max | 405377.4375 |
| mean | 270.36480712890625 |
| std | 35828.51953125 |
| p1 | -42219.753125 |
| p50 (median) | 25.21875 |
| p99 | 100700.890625 |

Genlik dağılımının çok geniş olması (min/max ile p1/p99 arasındaki büyük
fark) ham/ungained veri için beklenen bir durumdur — yüzeye yakın
doğrudan dalga/ringing enerjisi derinlikle hızla sönümlenir.

## Geolocation
- Mevcut: Evet (`Sample Geolocations` bloğu, byteOffset=7885740, byteSize=124600)
- Kayıt düzeni header'da belgeli değildi; gerçek dosyadan doğrulanarak
  çıkarıldı. Detay: [[03_ARCHITECTURE/OpenGPR_File_Structure]].
- `x_top == x_bottom` ve `y_top == y_bottom` (bu dosyada tüm noktalarda,
  ölçüm hassasiyeti dahilinde) — traceler dikey (düz aşağı).

## Üretilen QC çıktıları
**Sprint 1 (`outputs/inspect/`):** `Swath003_Array02_metadata.json`,
`_header.json`, `_geolocation.csv` (1925 satır = 175 × 11),
`_channel00_bscan.png`, `_all_channels.png`, `_survey_geometry.png`,
`radar_volume.npz`.

**Sprint 2 (`outputs/sprint02/`):** `time_zero/`, `time_zero_manual/`,
`dc_offset/`, `dc_offset_windowed/`, `combined/`, `canonical_target16/`
altında toplam 66 dosya (CSV/JSON/NPZ/PNG). Tam liste ve doğrulama:
[[07_VALIDATION/QC_Output_Validation]].

**Sprint 3 (`outputs/sprint03/`):** `dewow_candidates/`, `spectrum/`,
`bandpass_candidates/`, `combined_candidates/` altında toplam 209 dosya +
`SPRINT3_REVIEW_REQUIRED.md` — **hiçbiri canonical değil**. Tam liste ve
doğrulama: [[07_VALIDATION/QC_Output_Validation]].

## İlgili testler
`tests/test_real_ogpr_integration.py`, `tests/test_sprint2_real_integration.py`,
`tests/test_sprint3_real_integration.py`, `tests/test_sprint3_canonical.py`,
`tests/test_cli_sprint3_canonical.py` (hepsi bu dosya mevcut olduğu
için skip edilmedi, geçti). Detay: [[07_VALIDATION/Test_Results]],
[[07_VALIDATION/Parser_Validation]].

## Bilinen belirsizlikler
- CRS doğrulanmadı (bkz. yukarı).
- Derinlik/elevation hesapları hız varsayımına bağlı (bkz. yukarı).
- Geolocation kaydındaki baştaki int64 alanının anlamı belgelenmemiş
  (0..174 sırasıyla eşleşiyor, kullanılmıyor). Bkz. [[07_VALIDATION/Known_Uncertainties]].
- Otomatik time-zero pick'i fiziksel yüzey zamanı değildir; eski varsayılan
  `max_shift_samples=64` bu dosyada çoğu kanalı kırpardı (Sprint 2.1'de
  `overflow_policy` ile düzeltildi, bkz. yukarı,
  [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-006).
- `target_sample=0` vs `16` seçimi Sprint 2.2'de mühendislik önerisi olarak
  çözüldü (ISSUE-008, resolved) ama otomatik pick'in fiziksel anlamı
  değişmedi.
- Dewow penceresi (D1-D4) ve band-pass aralığı (B1-B4) seçimi 2026-07-15'te
  insan/jeofizik kararıyla çözüldü: D2 + B1 canonical — bkz.
  [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-010 (resolved), ISSUE-011
  (resolved), [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]. Bu seçim
  yalnızca bu veri seti için geçerlidir.

## İlgili notlar
[[Dataset_Index]], [[03_ARCHITECTURE/OpenGPR_File_Structure]],
[[05_PROCESSING/Processing_Index]], [[02_SPRINTS/Sprint_02_TimeZero_DCOffset]],
[[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]],
[[02_SPRINTS/Sprint_02_2_TimeAxis_DCWindow_Validation]],
[[02_SPRINTS/Sprint_03_Dewow_Bandpass]],
[[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]
