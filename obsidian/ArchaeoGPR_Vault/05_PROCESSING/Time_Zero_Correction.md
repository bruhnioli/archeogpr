---
type: processing-module
status: implemented
implemented: true
---

# Zaman-Sıfırı Düzeltmesi (Time-Zero Correction)

> Sprint 2'de implemente edildi. Kod: `src/archaeogpr/processing/time_zero.py`.
> Tasarım gerekçesi: [[06_DECISIONS/ADR_002_TimeZero_Reference_and_Shift_Policy]].

## Purpose

Kaydedilen her izde (trace) seçilen bir olayı (tipik olarak doğrudan
dalga/direct-wave varışı) belirli bir hedef örneğe (`target_sample`)
taşımak. **Önemli:** bu, o örneğin "gerçek yer yüzeyi" olduğunu KANITLAMAZ
— bkz. Risks.

## Input

Herhangi bir `GPRDataset`: `amplitudes (slices, channels, samples)`,
`time_ns (samples,)`, `metadata["sampling"]["sampling_time_ns"]` (otomatik
yöntemler için zorunlu).

## Output

Aynı shape/dtype'a sahip **yeni** bir `GPRDataset` (`ProcessingResult.dataset`);
her kanalın TÜM slice'ları aynı tam sayı örnek kaydırmasını alır (kanal-bazlı
sabit shift). Açığa çıkan bölge `fill_value` ile doldurulur, wrap-around
oluşmaz. `ProcessingResult.removed_component = input - output` (tam eşitlik,
bkz. ADR-002). `ProcessingResult.valid_mask` (şekil `(channels, samples)`,
dtype bool, salt-okunur) hangi örneklerin gerçek kaydırılmış veri (`True`)
hangisinin padding (`False`) olduğunu işaretler — bkz. ADR-003, [[DC_Offset]].

**(Sprint 2.2, bkz. ADR-004)** Çıktının `time_ns`'i de yeniden üretilir —
time-zero-relative: `time_ns[target_sample] == 0.0`, öncesi negatif,
sonrası pozitif, örnek aralığı korunur. Girdinin kendi `time_ns`'i
değişmez. Bu, aynı ns penceresinin (örn. DC offset'te) farklı
`target_sample` değerlerinde AYNI ham örnekleri seçebilmesini sağlar.

## Mathematical Basis

Üç yöntem uygulandı:

1. **`manual`** — kullanıcı her kanal için doğrulanmış bir örnek indeksi
   verir (`picks: dict[channel, sample]`); eksik kanal varsa açık hata.
2. **`channel_median_peak`** — her kanal için, arama penceresi içindeki
   (DC bias'a karşı yalnızca geçici olarak per-trace mean'i çıkarılmış)
   trace'lerin medyanı alınır; `peak_polarity` kriterine
   (`max_abs`/`positive_peak`/`negative_peak`) göre pik örneği bulunur.
3. **`channel_median_cross_correlation`** — referans kanalın piki (2)
   yöntemiyle bulunur; diğer kanalların median trace'leri, arama
   penceresi içinde referansla çapraz korelasyonla hizalanır
   (`max_shift_samples` ile sınırlı bir lag araması).

Kaydırma: `shift = target_sample - picked_sample`, `np.roll(trace, shift)`
+ açığa çıkan bölgenin `fill_value` ile maskelenmesi (`padding_mask()`).

## Parameters

`method`, `picks` (manual için), `search_start_ns`/`search_end_ns`,
`target_sample`, `peak_polarity`, `reference_channel` (cross-correlation
için), `max_shift_samples`, `fill_value`,
`overflow_policy` (`"error"`|`"clip"`, varsayılan `"error"` — bkz. ADR-003).
Tam imza: `src/archaeogpr/processing/time_zero.py::correct_time_zero`.

## Risks

- **Otomatik pick, doğrulanmış fiziksel yüzey zamanı değildir.** Her
  sonuçta şu uyarı bulunur: *"Automatic time-zero picks are
  signal-processing references and are not independently calibrated
  physical surface times."* (`TIME_ZERO_REFERENCE_WARNING`)
- Yanlış bir pick, tüm sonraki derinlik dönüşümlerini sistematik olarak
  kaydırır (bu proje henüz derinlik dönüşümü yapmıyor, ama gelecekteki
  modüller bu riski miras alacak).
- `max_shift_samples` çok küçükse, gerçek shift `overflow_policy="error"`
  (varsayılan) ile **veriye dokunulmadan hata** verir — artık sessizce
  kırpılmaz (Sprint 2.1'de değişti, bkz.
  [[06_DECISIONS/ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]]).
  Gerçek dosyada varsayılan `max_shift_samples=64` ile 9/11 kanal bu hatayı
  tetikler; `overflow_policy="clip"` açıkça istenirse kırpma hâlâ mümkündür
  ama sonuç `valid_for_downstream_processing=False` işaretlenir. Bkz.
  [[04_DATASETS/Swath003_Array02]], [[01_PROJECT_STATE/03_Open_Issues]]
  ISSUE-006.
- Kanal-bazlı sabit shift, o kanal içindeki iz-bazlı gerçek zaman-sıfırı
  farklarını (varsa) düzeltmez — bu sprintin kasıtlı sınırıdır.
- **`target_sample=0`, picked_sample'dan önceki tüm örnekleri geri
  dönüşü olmayan biçimde atar** (öndeki dalga biçimi/direct-wave onset
  kaybı riski). `target_sample=16` bu kaybı azaltır ama ortadan kaldırmaz.
  Hangi değerin doğru olduğu bu modül tarafından belirlenmez — insan/
  jeofizik incelemesi gerektirir. Bkz.
  [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-008,
  `outputs/sprint02_review/REVIEW_REQUIRED.md`.

## Required QC

`outputs/sprint02/time_zero/`: `channel_picks.csv`, median trace
before/after/overlay, channel00 before/after/difference B-scan, tüm
kanallar before/after, picks-and-shifts grafiği, `padding_mask_channelNN.png`
(valid/padding maskesi görselleştirmesi, Sprint 2.1), `valid_sample_summary.json`
(Sprint 2.1). Tam liste ve doğrulama: [[07_VALIDATION/QC_Output_Validation]].

## Acceptance Criteria

Tümü doğrulandı (bkz. [[02_SPRINTS/Sprint_02_TimeZero_DCOffset]],
[[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]]): (1) girdi mutasyona
uğramaz, (2) her kanalın shift'i `processing_history`'de saklanır, (3)
sentetik testlerde bilinen pulse konumları tam olarak bulunur ve hedefe
hizalanır, (4) fonksiyon opsiyoneldir (pipeline'ın zorunlu bir parçası
değildir), (5) `max_shift_samples` aşımı varsayılan olarak veriye
dokunulmadan hata verir (Sprint 2.1), (6) `valid_mask` doğru şekil/taraf/
salt-okunurlukla üretilir (Sprint 2.1).

## Implementation Status

**Implemented: true** (Sprint 2, genişletildi Sprint 2.1 ve Sprint 2.2).
Sentetik testler: `tests/test_time_zero.py` (40 test: 20 Sprint 2 + 10
Sprint 2.1 + 10 Sprint 2.2). Gerçek dosya entegrasyonu:
`tests/test_sprint2_real_integration.py`,
`tests/test_target_invariance.py`.

## Related Modules

[[Processing_Index]], [[Processing_Order]], [[DC_Offset]]
