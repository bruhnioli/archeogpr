---
type: validation-report
tags: [validation]
date: 2026-07-14
---

# QC Output Validation

`python -m archaeogpr inspect data/raw/Swath003_Array02.ogpr --output-dir
outputs/inspect` komutuyla üretilen her çıktı dosyası için doğrulama
kaydı. Tüm dosyalar `outputs/inspect/` altında (vault dışında).

## `Swath003_Array02_metadata.json`
- Oluştu: Evet (2099 byte)
- Sıfır byte değil: Evet
- Açılabildi: Evet (`json.load()` başarılı)
- İçerik: kaynak dosya bilgisi, boyutlar, dtype, sampling, radar, spatial
  reference, warnings, `derived` (time_window_ns, depth_estimate, geometry,
  amplitude_statistics) — bkz. [[04_DATASETS/Swath003_Array02]] için tam değerler.
- Görsel/QC değerlendirmesi: değerler [[Parser_Validation]] ve gerçek
  dosya integration testiyle çapraz doğrulandı, tutarlı.

## `Swath003_Array02_header.json`
- Oluştu: Evet (1250 byte)
- Sıfır byte değil: Evet
- Açılabildi: Evet (`json.load()` başarılı)
- İçerik: magic, checksum, header_size, ham `header` objesi (mainDescriptor
  + dataBlockDescriptors) — CLI'nin `header` komutu çıktısıyla tutarlı.

## `Swath003_Array02_geolocation.csv`
- Oluştu: Evet (237,108 byte)
- Sıfır byte değil: Evet
- Açılabildi: Evet (`pandas.read_csv()` başarılı)
- Beklenen satır sayısı: 175 × 11 = 1925 → **doğrulandı, tam eşleşiyor**.
- Kolonlar: `slice, channel, x_top, y_top, depth_top_m, elevation_top_m,
  x_bottom, y_bottom, depth_bottom_m, elevation_bottom_m` — spesifikasyonla eşleşiyor.

## `Swath003_Array02_channel00_bscan.png`
- Oluştu: Evet (65,128 byte)
- Sıfır byte değil: Evet
- Görsel QC değerlendirmesi: Y ekseni (sample) üstte 0, alta doğru artıyor;
  yüzeye yakın (örnek ~60-120) yüksek genlikli kırmızı/mavi bant (doğrudan
  dalga/ringing), derinlikle hızla sönümleniyor. Renk skalası sıfır
  merkezli ve simetrik (±99. percentile clip). Ham/ungained veri için
  fiziksel olarak makul bir görüntü.

## `Swath003_Array02_all_channels.png`
- Oluştu: Evet (338,764 byte)
- Sıfır byte değil: Evet
- Görsel QC değerlendirmesi: 11 kanalın tümü 3×4 subplot grid'inde (son
  hücre boş/kapalı), her biri tek kanal B-scan ile aynı görsel dili
  kullanıyor; kanallar arası genel görünüm tutarlı, bazı kanallarda
  (örn. Ch03, Ch07, Ch09) yüzey yakını daha gürültülü — beklenen bir
  kanal-bazlı değişkenlik.

## `Swath003_Array02_survey_geometry.png`
- Oluştu: Evet (257,075 byte)
- Sıfır byte değil: Evet
- Görsel QC değerlendirmesi: 11 kanalın x-y hatları birbirine paralel,
  eşit eksen ölçeği uygulanmış, başlangıç (yeşil daire) ve bitiş (kırmızı
  kare) işaretli, CRS uyarı kutusu görünür durumda.

## `radar_volume.npz`
- Oluştu: Evet (5,918,087 byte)
- Sıfır byte değil: Evet
- Açılabildi: Evet (`numpy.load()` başarılı)
- `amplitudes.shape == (175, 11, 1024)` → doğrulandı
- `amplitudes.dtype == float32` → doğrulandı
- `time_ns.shape == (1024,)` → doğrulandı
- `has_geolocation == True`, `x`/`y`/`elevation_top_m` anahtarları mevcut
  (geolocation olmayan bir dosyada bu anahtarlar hiç yazılmaz, `None`
  object array olarak KAYDEDİLMEZ).
- `metadata_json` alanı `json.loads()` ile başarıyla parse edildi.

---

# Sprint 2 — Time-Zero & DC Offset QC Outputs

`python -m archaeogpr time-zero|dc-offset|sprint2 data/raw/Swath003_Array02.ogpr
...` komutlarıyla üretilen çıktılar. Tüm dosyalar `outputs/sprint02/`
altında (vault dışında). Parametreler görev tanımındaki örnek komutlarla
birebir eşleşiyor (bkz. [[Sprint_02_TimeZero_DCOffset]]).

## `time_zero/` (auto, channel_median_peak, max_abs, 5–15 ns, target=0)
- `channel_picks.csv`: 11 satır (bir kanal/satır) → **doğrulandı**. Kolonlar
  spesifikasyonla eşleşiyor (`channel, picked_sample, picked_time_ns,
  target_sample, shift_samples, shift_ns, method, warning`).
- `channel_median_traces_{before,after,overlay}.png`: sıfır byte değil
  (62–116 KB). Görsel QC: overlay'de 11 kanalın dashed (before) pikleri
  farklı konumlarda, solid (after) çizgileri hedefe (0) doğru toplanıyor;
  kırpılan kanallarda tam 0'a değil ~0–10 aralığına hizalanıyor (beklenen,
  bkz. ISSUE-005).
- `channel00_{before,after,difference}.png`: sıfır byte değil, aynı clip
  değeri (before/after) kullanılıyor, fark görüntüsü kaydırılan
  ringing'i gösteriyor.
- `all_channels_{before,after}.png`: sıfır byte değil (334–339 KB).
- `picks_and_shifts.png`: sıfır byte değil; üst panel pick'leri, alt panel
  shift'leri (kırpılanlar kırmızı) doğru gösteriyor.
- `processing_metadata.json`: `json.load()` başarılı; `operation ==
  "time_zero_correction"`.
- `time_zero_corrected.npz`: `numpy.load()` başarılı, `amplitudes.shape ==
  (175, 11, 1024)`, `dtype == float32`, `np.isfinite(...).all() == True`.

## `time_zero_manual/` (method=manual, `configs/time_zero_picks.json`)
Aynı dosya seti üretildi; pick'ler otomatik yöntemle **birebir aynı**
çıktı verdi (manuel dosya, otomatik yöntemin bulduğu değerlerle
oluşturulduğu için) — yöntemden bağımsız shift/kırpma mantığının tutarlı
çalıştığını doğrular.

## `dc_offset/` (method=mean, tüm iz)
- `offsets.csv`: 1925 satır (175×11) → **doğrulandı**. Kolonlar
  spesifikasyonla eşleşiyor.
- `channel00_{before,after,difference}.png`: sıfır byte değil.
- `trace_offset_histogram.png`, `trace_means_before_after.png`,
  `channel_offset_statistics.png`: sıfır byte değil (32–40 KB).
- `processing_metadata.json`: `operation == "dc_offset_correction"`.
- `dc_offset_corrected.npz`: açıldı, shape/dtype doğrulandı, NaN/Inf yok.
- Uyarı doğru üretildi: pencere verilmediği için "strong direct/air wave"
  uyarısı mevcut.

## `dc_offset_windowed/` (method=median, 20–100 ns)
Aynı dosya seti, farklı istatistikler (offset mean ≈13.96, tüm-iz
mean=270.36'dan belirgin şekilde farklı — pencere doğru kullanılıyor).
Uyarı YOK (pencere verildi + median) — doğru davranış.

## `combined/` (sprint2: time-zero → dc-offset)
- `sprint02_processed.npz`: açıldı, shape doğrulandı, NaN/Inf yok,
  `removed_component_time_zero` ve `removed_component_dc_offset` ayrı
  anahtarlar olarak mevcut.
- `processing_history.json`: `["time_zero_correction",
  "dc_offset_correction"]` sırası → **doğrulandı**.
- `channel00_{raw,timezero,final}.png`, `channel00_stage_differences.png`:
  sıfır byte değil; stage_differences'ta time-zero paneli kaydırılan
  ringing'i, dc-offset paneli tüm sample'lar boyunca sabit bir dikey
  bantlanmayı gösteriyor (ofset her örnekte aynı olduğu için beklenen).
- `sprint02_summary.json`: `json.load()` başarılı; `raw_file_sha256`
  alanı gerçek hash'le eşleşiyor.

## Genel doğrulamalar (Sprint 2)
- Toplam 49 çıktı dosyası üretildi, hepsi sıfır byte değil.
- Ham dosya hash'i her komuttan önce/sonra karşılaştırıldı: değişmedi.
- `read_ogpr()` ile ham dosya tekrar okundu ve orijinal `raw.amplitudes`
  ile byte-bazında eşleştiği doğrulandı (`test_sprint2_real_integration.py`).

---

# Sprint 2.1 — Review, Overflow Policy & Padding-Mask Safety QC Outputs

`outputs/sprint02_review/` altında (repository'de, vault dışı).

## Varsayılan overflow davranışı (negatif doğrulama)
`--max-shift-samples` verilmeden (varsayılan 64) çalıştırılan `time-zero`
komutu: `ProcessingError` ile durdu (exit code 1), kanal başına detaylı
mesaj basıldı, ve **çıktı klasörü hiç oluşturulmadı** (`output_dir.mkdir()`
çağrısı `correct_time_zero()`'dan SONRA olduğu için) — kırpılmış/eksik bir
sonucun normal başarı gibi kaydedilmediği doğrudan doğrulandı.

## `target_sample_00/`, `target_sample_16/` (standalone time-zero, `--max-shift-samples 96 --overflow-policy error`)
Her ikisi için: `Has clipped shifts: False`, `Valid for downstream
processing: True`, 11/11 kanalda `requested_shift == applied_shift`
(target 0: -74..-61; target 16: -58..-45). Her klasörde 15 dosya üretildi
(`channel_picks.csv`, `channel_median_traces_{before,after,overlay}.png`,
`channel00_{before,after,difference,before_after_difference}.png`,
`all_channels_{before,after}.png`, `picks_and_shifts.png`,
`padding_mask_channel00.png`, `valid_sample_summary.json`,
`processing_metadata.json`, `time_zero_corrected.npz`).

## `combined_target00/`, `combined_target16/` (sprint2, aynı parametreler)
Her ikisi: `DC offset valid_mask used: True`. `sprint02_processed.npz`
içindeki `valid_mask` (şekil `(11, 1024)`, bool) doğrulandı; her 11 kanalın
padding bölgesindeki **tüm** benzersiz değerler `[0.]` — DC offset'ten
sonra padding kirlenmesi YOK (denetim bulgusunun gerçek veri üzerinde
düzeltildiğinin kanıtı).

## Programatik PNG denetimi (32 dosya)
`outputs/sprint02_review/` altındaki tüm 32 PNG için: dosya boyutu > 0,
`matplotlib.image.imread()` ile açılabildi, tüm piksel değerleri finite
(NaN/Inf yok), tek renkli/boş DEĞİL. Sonuç: **32/32 sorunsuz**.
Ek doğrulamalar:
- `padding_mask_channel00.png` (her iki hedef): piksel-seviyesi analizle
  padding'in doğru tarafta (trailing/sağ) ve doğru orandaki (target 0:
  %7,09 ölçülen vs %7,13 beklenen; target 16: %5,54 ölçülen vs %5,57
  beklenen — fark, hedef çizgisi/anti-aliasing piksellerinden) olduğu
  doğrulandı; doğrudan görsel incelemeyle de teyit edildi.
- `processing_metadata.json`'daki `diagnostics.target_sample` her iki
  klasörde de beklenen değerle (0, 16) eşleşiyor.
- `all_channels_after.png`: 3×4 grid, 11 dolu panel (Ch00–Ch10) + 1 boş
  hücre — görsel olarak doğrulandı.
- `comparison/target00_vs_target16_all_channel_medians.png`: dashed
  (target=0) ve solid (target=16) eğrileri, aynı dalga biçimini tam 16
  örnek kaydırılmış olarak gösteriyor (uygulamanın iç tutarlılığının
  görsel kanıtı).
- `removed_component` (channel 0, her iki hedef): %100 sıfır olmayan
  oran, maks. mutlak değer ~487000–494000 — fark anlamlı, ihmal edilebilir
  değil.

## `comparison/` (target_sample 0 vs 16)
`discarded_leading_samples.csv` (22 satır: 11 kanal × 2 hedef),
`padding_summary.csv` (22 satır), `comparison_summary.json`,
`target00_vs_target16_channel00.png`,
`target00_vs_target16_all_channel_medians.png` — tümü üretildi ve
programatik/görsel olarak doğrulandı (yukarıda). **Hiçbir otomatik
target_sample kararı içermiyor.**

## `REVIEW_REQUIRED.md`
Üretildi (`outputs/sprint02_review/REVIEW_REQUIRED.md`); target 0/16
davranışı, öndeki dalga biçimi kaybı, padding miktarı, filtre kenar-etkisi
riski, otomatik pick'in fiziksel kesinlik taşımadığı ve nihai seçimin
insan/jeofizik incelemesi gerektirdiği açıkça belirtiliyor. Otomatik bir
"0 daha iyi"/"16 daha iyi" ifadesi YOK.

## Eski canonical çıktının durumu
`outputs/sprint02/combined/` **silinmedi, üzerine yazılmadı**.
`outputs/sprint02/combined/SUPERSEDED_PENDING_REVIEW.md` sidecar dosyası
eklendi (mevcut dosyaların hiçbiri değiştirilmedi) — bu klasörün 9/11 kanal
kırpılmış olduğunu ve `outputs/sprint02_review/` altındaki adaylara
bakılması gerektiğini belirtiyor.

## Genel doğrulamalar (Sprint 2.1)
- Ham dosya hash'i (`66d840c313b4beed10bea2e35d88431573f6fab0f02bba17792c0920028b62a6`)
  tüm 4 gerçek veri komutu + karşılaştırma script'i boyunca değişmedi.
- Girdi array'lerinin mutasyona uğramadığı hem testlerde (bkz.
  `test_input_dataset_is_not_mutated_when_a_valid_mask_is_given`) hem
  gerçek CLI çalıştırmalarında (her komut kendi `read_ogpr()` çağrısıyla
  taze bir kopya okuyor) doğrulandı.

---

# Sprint 2.2 — Time-Zero-Relative Axis & Target-Invariant DC Offset QC Outputs

## `outputs/sprint02/canonical_target16/` (canonical, 17 dosya)
`python -m archaeogpr sprint2 ... --target-sample 16 --max-shift-samples 96
--overflow-policy error --dc-window-start-ns 20 --dc-window-end-ns 100
--dc-window-reference dataset-time` ile üretildi, tüm target-invariance
testleri geçtikten SONRA. Terminal çıktısı doğrulandı: 0 kırpılan kanal,
`Corrected time axis: [-2.0, 125.875] ns`, `Target sample (=16) time
value: 0.0 ns`, `Negative-time sample count: 16`,
`DC window: [20.0, 100.0) ns (reference=dataset_time)`,
`DC window sample indices: [176, 816)`, `Padding statistics: {unique_
count: 1, min: 0.0, max: 0.0}`, `Raw file hash unchanged: True`.
`CANONICAL_PROCESSING_NOTE.md` üretildi (target sample, sampling interval,
negatif zaman bölgesi, DC window, method, overflow policy, valid mask,
fiziksel kalibrasyon uyarısı, raw hash — tümü gerçek değerlerle).

## `outputs/sprint02_2_validation/target_invariance/`
`scripts/generate_sprint2_2_validation.py` ile üretildi (gerçek dosyada
target=0 ve target=16'yı in-process yeniden hesaplayarak — canonical CLI
çıktısıyla deterministik olarak aynı). Doğrulanan sonuçlar
(`target_invariance_summary.json`): `all_channels_raw_window_matches:
true` (11/11 kanal), `max_offset_abs_difference: 0.0`,
`offsets_allclose_rtol_1e-6_atol_1e-3: true`,
`max_common_time_amplitude_abs_difference: 0.0`,
`common_relative_time_region_sample_count: 1008`,
`target16_minus_target0_padding_count_per_channel`: her kanalda tam `-16`.
`offset_comparison.png`, `relative_time_axis_comparison.png`: görsel
olarak doğrulandı (bar'lar/çizgiler pixel-eşit görünüyor).
`common_time_data_difference.png`: tamamen tek renkli (fark=0.0) —
beklenen ve doğru.

## `outputs/sprint02_2_validation/dc_window/`
`channel_median_traces_with_window.png`: görsel olarak doğrulandı — güçlü
erken pulse (±400-500k) ilk ~10ns'de yoğunlaşıyor, `[20,100)` ns penceresi
bu bölgeden açıkça uzak (sinyal görsel olarak sıfıra yakın), canonical
pencere seçiminin gerekçesini görsel olarak destekliyor.
`mean_vs_median_offsets.png`, `dc_window_summary.json`: bazı kanallarda
(2, 4, 8) mean/median işaret bile değiştiriyor (`max_abs_difference≈
226.4`) — bu doğrudan [[07_VALIDATION/Known_Uncertainties]]'e ve
ISSUE-009'a kaydedildi, gizlenmedi.

## Programatik denetim (Sprint 2.2)
14 yeni PNG + tüm CSV/JSON/NPZ (`outputs/sprint02/canonical_target16/`,
`outputs/sprint02_2_validation/`) programatik olarak denetlendi: sıfır
byte değil, açılabilir, NaN/Inf yok, tek-renkli/boş DEĞİL (kasıtlı sıfır-
fark görüntüsü hariç tutuldu) — **0 sorun**. NPZ'lerin `amplitudes`,
`time_ns`, `valid_mask` anahtarlarını içerdiği ve finite olduğu doğrulandı.

## Eski canonical çıktının durumu (güncellendi)
`outputs/sprint02/combined/SUPERSEDED_PENDING_REVIEW.md` ve
`outputs/sprint02_review/` (Sprint 2.1) **silinmedi/üzerine yazılmadı**;
`SUPERSEDED_PENDING_REVIEW.md`, artık `outputs/sprint02/canonical_
target16/`'ya işaret edecek şekilde güncellendi.

---

# Sprint 3 — Dewow & Band-Pass Filtering, Spectrum QC & Candidate Comparison Outputs

`outputs/sprint03/` altında (repository'de, vault dışı), `python -m
archaeogpr sprint3-candidates outputs/sprint02/canonical_target16/
sprint02_processed.npz --output-dir outputs/sprint03` ile üretildi.
Girdi NPZ hash'i (`b2770b5c264214a119521c47ebf58252c457c1738594b200e814c
ff5b7af5afe`) ve raw `.ogpr` hash'i tüm komutlar boyunca değişmedi.

## `dewow_candidates/{D1_mean_4ns,D2_mean_8ns,D3_mean_12ns,D4_median_8ns}/`
Her klasörde 13 dosya (`processing_metadata.json`, `dewow_processed.npz`,
channel00 before/after/removed/difference, all_channels_after, medyan iz
before/after, çıkarılan bileşen medyan izi, trace-mean histogramı,
düşük-frekans spektrumu before/after, `padding_verification.json`) —
4×13=52 dosya, hepsi sıfır byte değil. `dewow_candidate_metrics.csv`:
uygulanan pencereler 4.125/8.125/12.125/8.125 ns (istenen 4.0/8.0/12.0/8.0
ns'den, hepsi tek sayı örneğe yuvarlandı); düşük-frekans enerji oranı
(sonra) D1=0.7440, D2=0.8785, D3=0.5587, D4=0.9392.

## `dewow_candidates/comparison/`
6 dosya: `channel00_all_dewow_candidates.png` (görsel olarak doğrulandı —
raw canonical + 4 aday medyan izi, hepsi ana direct-wave pulse'ını
yakından takip ediyor, ~20ns'den sonra sıfıra yakınsıyor),
`all_channel_medians_candidates.png`, `low_frequency_energy_comparison.png`,
`mean_vs_median_dc_metric_comparison.png` (ISSUE-009 metriği her aday için
ayrıca izlendi), `dewow_candidate_metrics.csv`,
`DEWOW_REVIEW_REQUIRED.md` (kısa/uzun pencere riski, medyan filtre
doğrusal-olmama uyarısı, hiçbir adayın seçilmediği açıkça belirtiliyor).

## `spectrum/`
6 dosya: `raw_canonical_spectrum.{csv,png}`, `dewow_candidate_spectra.png`,
`spectrum_metrics.csv`, `spectrum_metadata.json`,
`SPECTRUM_INTERPRETATION_NOTES.md` (600 MHz header değerinin bağımsız
yeniden ölçülmediği açıkça belirtiliyor).

## `bandpass_candidates/{B1_butter_100_900,...,B4_ormsby_100_150_700_900}/`
Her klasörde 13 dosya (dewow ile aynı desen + `transfer_function.png`,
`impulse_response.png`, `spectrum_before_after.png`) — 4×13=52 dosya.
`impulse_response.png` (B2, görsel olarak doğrulandı): mükemmel simetrik,
t=0'da merkezlenmiş dürtü tepkisi — sıfır-faz özelliğinin doğrudan görsel
kanıtı (nedensel bir filtre bu şekli üretemezdi).
`transfer_functions_all_candidates.png` (görsel olarak doğrulandı):
Butterworth (B1/B2) düzgün yuvarlak omuzlu geçiş, Ormsby (B3/B4) keskin
doğrusal rampa — beklenen ve doğru şekil farkı.

## `bandpass_candidates/comparison/`
9 dosya: `channel00_all_bandpass_candidates.png`,
`all_channel_medians_bandpass_candidates.png`, `spectra_all_candidates.png`,
`transfer_functions_all_candidates.png`, `removed_components_all_
candidates.png`, `phase_lag_comparison.csv` (**tüm 4 aday için medyan-iz
gecikmesi = 0**), `spectral_metrics_comparison.csv`,
`bandpass_candidate_metrics.csv` (geçiş-bandı enerji korunumu: B1≈99.2%,
B2≈99.1%, B3≈98.4%, B4≈95.4%), `BANDPASS_REVIEW_REQUIRED.md`.

## `combined_candidates/{C1_D1_B2,...,C6_D2_B4}/`
6 aday × 13 dosya = 78 dosya. `combined_candidate_metrics.csv`: **tüm 6
adayda medyan-iz gecikmesi = 0**.

## `combined_candidates/comparison/`
5 dosya: `channel00_all_combined_candidates.png` (görsel olarak
doğrulandı), `all_channel_medians_combined.png`, `combined_spectra.png`,
`combined_candidate_metrics.csv`, `COMBINED_REVIEW_REQUIRED.md`.

## `SPRINT3_REVIEW_REQUIRED.md` (üst düzey)
Tüm adayları, ana metrikleri (padding/faz doğrulaması, düşük-frekans
enerji oranı, geçiş-bandı korunumu, baskın frekans) ve insan incelemesi
gereken görselleri listeler. **"No dewow or band-pass candidate has been
selected as canonical"** açıkça belirtiliyor.

## Programatik denetim (Sprint 3)
Toplam **209 dosya** üretildi. Tüm 14 `padding_verification.json` dosyası
programatik olarak denetlendi: **14/14** `all_channels_padding_untouched=
true` ve `all_channels_removed_component_zero_at_padding=true`. Tüm 10
band-pass/kombine adayında `max_abs_median_trace_lag == 0` doğrulandı.

---

# Sprint 3.1 — D2 Dewow Confirmation & B1/B2 Band-Pass Decision QC Outputs

`outputs/sprint03_1/` altında (repository'de, vault dışı), `python
scripts/generate_sprint3_1_decision_qc.py` ile üretildi (24 dosya). Girdi
NPZ hash'i ve raw `.ogpr` hash'i değişmedi.

## `dewow_D2_validation/`
3 dosya (`channel{00,05,10}_D2_windowed_review.png`) + `D2_removed_
component_qc_notes.md`. Görsel olarak doğrulandı: her kanal için 5 zaman
penceresi (satır) × 4 panel (input/D2 output/removed/fark) ızgarası; her
satır kendi ortak amplitude scale'ini kullanıyor; padding `full` satırında
açıkça gri maskelendi; "input - output" sütunu "removed component"
sütunune piksel-eşit görünüyor (matematiksel özdeşliğin görsel kanıtı).
20-100ns aralığındaki removed component, yatay/laterally-continuous bir
geçiş gösteriyor — hiperbolik veya dipli bir desen yok (QC gözlemi,
arkeolojik yorum değil).

## `bandpass_B1_B2_bscan/`
3 dosya (`channel{00,05,10}_B1_B2_windowed_comparison.png`). Görsel olarak
doğrulandı: D2/D2+B1/D2+B2 sütunları (1-3) ortak scale, B1/B2 removed
sütunları (4-5) ayrı ortak scale, B1-B2 fark sütunu (6) kendi scale'i;
D2+B1 ve D2+B2, 20-100ns'de görsel olarak neredeyse özdeş.

## `spectrum_windows/`
4 dosya (`W{1,2,3,4}_spectrum_comparison.png`), her biri 3 alt-grafik
(mutlak / ortak-dB-D2-referanslı / kendi-piki-normalize) — görsel olarak
doğrulandı, her mod ayrı eksen etiketiyle açıkça işaretli.

## Üst düzey çıktılar
- `DECISION_PANEL_D2_B1_B2.png`: tek, yüksek çözünürlüklü panel — kanal
  0/5/10 için 20-100ns D2/D2+B1/D2+B2 B-scan'leri, B1/B2 removed, mutlak +
  ortak-dB W4 spektrumu, band-enerjisi ve mekânsal-koherans özet
  tabloları. Direct wave hariç tutulduğu için genlik skalasına hakim
  olmuyor. Görsel olarak doğrulandı.
- `BANDPASS_FINAL_DECISION_REQUIRED.md`: 11 kriterlik karşılaştırma
  tablosu; mühendislik eğilimi `preservation-favoring candidate` (B1) —
  **kesin seçim yapılmadı**.
- `D2_DEWOW_DECISION.md`: 4 koşul da geçti →
  `recommended_dewow_candidate = D2` (mühendislik önerisi).
- `band_energy_by_channel.csv` (1320 satır), `band_energy_by_time_window.csv`
  (120 satır): 4 pencere × 5 aday × 6 bant × (11 kanal veya toplam).
- `B1_vs_B2_energy_summary.json`: 5 spesifik soru numerik olarak
  yanıtlandı (800-900MHz'de B1 ~3.3-3.6× daha fazla enerji, CV≈0.33
  tutarlılık, top-%5 trace enerjinin %30.7'sini taşıyor, B2'nin çıkardığı
  bandın mekânsal korelasyonu 0.9605, toplam RMS farkı 210.7).
- `spatial_coherence_metrics.csv` (42 satır), `spatial_coherence_comparison.png`,
  `removed_component_coherence.png`: görsel olarak doğrulandı, D2 < B1/B2
  < (beklenen, filtreleme gürültüyü azaltıp görünür korelasyonu artırıyor).
- `phase_waveform_metrics.json`, `PHASE_METRICS_INTERPRETATION_NOTES.md`:
  B2'nin geç-zaman penceresindeki 40-örneklik ham gecikmesinin spektral
  farklılıktan kaynaklandığı, gerçek faz kayması olmadığı açıkça belgelendi
  (yetkili tam-segment kanıtı: B1=0, B2=0).
- `BAND_ENERGY_TABLE_NOTES.md`: kısa pencerelerde (W1-W3) 100-120 MHz
  bandının FFT çözünürlüğünden dar olduğu, "0 enerji"nin bir ölçüm
  eksikliği değil bin-yerleşimi artefaktı olduğu belgelendi.

## Programatik denetim (Sprint 3.1)
Toplam **24 dosya** üretildi, hepsi sıfır byte değil. Tüm PNG'ler
`matplotlib.image.imread()` ile açıldı, tüm pikseller finite. Tüm CSV'ler
`pandas` ile okundu (satır sayıları doğrulandı). Tüm JSON'lar geçerli.

---

# Sprint 3 Canonicalization — D2 + B1 Selection Outputs

`outputs/sprint03/canonical_D2_B1/` altında (repository'de, vault dışı),
`python -m archaeogpr sprint3 outputs/sprint02/canonical_target16/
sprint02_processed.npz --output-dir outputs/sprint03/canonical_D2_B1
--dewow-method running-mean --dewow-window-ns 8 --dewow-edge-mode reflect
--bandpass-method butterworth --lowcut-mhz 100 --highcut-mhz 900 --order 4
--zero-phase` ile üretildi. Girdi NPZ hash'i (`b2770b5c264214a119521c47eb
f58252c457c1738594b200e814cff5b7af5afe`) ve raw `.ogpr` hash'i
(`66d840c313b4beed10bea2e35d88431573f6fab0f02bba17792c0920028b62a6`) her
ikisi de komuttan önce/sonra karşılaştırıldı — değişmedi.

## Tam olarak 15 dosya (belirtilen listeyle birebir eşleşiyor)
`sprint03_processed.npz`, `processing_history.json`,
`processing_metadata.json`, `canonical_parameters.json`,
`channel00_raw.png`, `channel00_after_dewow.png`, `channel00_final.png`,
`channel00_removed_dewow.png`, `channel00_removed_bandpass.png`,
`all_channels_final.png`, `spectrum_before_after.png`,
`transfer_function.png`, `padding_verification.json`,
`phase_verification.json`, `CANONICAL_PROCESSING_NOTE.md`.

## Programatik denetim
Tüm 15 dosya sıfır byte değil. Tüm 8 PNG `matplotlib.image.imread()` ile
açıldı, tüm pikseller finite. Tüm 5 JSON dosyası `json.loads()` ile
geçerli. `sprint03_processed.npz`, `read_processed_npz()`
(`allow_pickle=False`) ile yeniden açıldı — shape `(175, 11, 1024)`,
`float32`, tüm değerler finite. Yeniden açılan `processing_history`
sırası: `["time_zero_correction", "dc_offset_correction",
"dewow_correction", "bandpass_correction"]` — doğrulandı.
`canonical_parameters.json`: `canonical=true`,
`selection_authority="human/geophysical review"`,
`dewow.candidate_id="D2"` (`applied_window_samples=65`,
`applied_window_ns≈8.125`), `bandpass.candidate_id="B1"`
(`lowcut_mhz=100.0`, `highcut_mhz=900.0`), `dataset_scope` metninde
`Swath003_Array02.ogpr` geçiyor. `phase_verification.json`:
`confirmed_zero_phase=true`,
`max_abs_median_trace_cross_correlation_lag=0`. `padding_verification.json`:
`all_channels_padding_untouched=true`,
`all_channels_removed_component_zero_at_padding=true`.

## Görsel denetim
`channel00_final.png`: direct-wave/ringing bandı üstte yoğunlaşıyor,
derinlikle hızla sönümleniyor — beklenen ve Sprint 1/2/3 çıktılarıyla
tutarlı bir B-scan görünümü. `spectrum_before_after.png`: "after"
(D2+B1) eğrisi ~900 MHz civarında keskin bir şekilde düşüyor — B1'in
100-900 MHz Butterworth band-geçirgen davranışının doğrudan görsel
kanıtı. `transfer_function.png`: Butterworth order=4, [100, 900] MHz
geçiş bandı + zero-phase (`sosfiltfilt`) etkin `|H(f)|²` eğrisi net
şekilde görünüyor. `channel00_removed_dewow.png`: D2'nin çıkardığı
bileşen yatay/laterally-continuous bir düşük-frekans taban çizgisi
gösteriyor — hiperbolik/lokalize bir olay değil (D2'nin removed
component'inin "gerçek bir yansımayı kaldırmadığı" iddiasıyla tutarlı).

## Eski aday çıktılarının durumu
`outputs/sprint03/{dewow_candidates,bandpass_candidates,
combined_candidates}/` (202 dosya) ve `outputs/sprint03_1/` (24 dosya)
**silinmedi/üzerine yazılmadı** — canonicalization çalıştırmasından önce
ve sonra dosya sayıları karşılaştırıldı, değişmedi.

## İlgili notlar
[[Test_Results]], [[Parser_Validation]], [[04_DATASETS/Swath003_Array02]],
[[Sprint_02_TimeZero_DCOffset]], [[Sprint_02_1_TimeZero_DCOffset_Review]],
[[Sprint_02_2_TimeAxis_DCWindow_Validation]], [[Sprint_03_Dewow_Bandpass]],
[[Sprint_03_1_Dewow_Bandpass_Decision_QC]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]
