---
type: sprint
tags: [sprint]
sprint: 2
status: done
started: 2026-07-14
completed: 2026-07-14
---

# Sprint 2 — Time-Zero and DC Offset Correction

> **Status history:** `done` (2026-07-14) → `review_required` (2026-07-15,
> Sprint 2.1's audit found 9/11 channels clipped and DC offset padding
> contamination) → **`done`** (2026-07-15, Sprint 2.2). All real-data
> acceptance criteria now pass against the canonical output
> (`outputs/sprint02/canonical_target16/`) — see
> [[Sprint_02_1_TimeZero_DCOffset_Review]] and
> [[Sprint_02_2_TimeAxis_DCWindow_Validation]] for the fixes. The content
> below is Sprint 2's own original (2026-07-14) completion record and was
> left unmodified — it does not reflect the overflow_policy, valid_mask,
> or time-zero-relative time axis work done afterward.

## Goal
Ham radar genliklerini hiçbir aşamada değiştirmeden, geri döndürülebilir ve
QC'si mümkün şekilde (1) time-zero correction ve (2) DC offset correction
uygulamak; her iki işlem için sentetik ve gerçek veri testleri, öncesi/
sonrası/fark QC çıktıları ve işlem geçmişi kaydı sağlamak.

## Scope
- `processing/common.py`, `processing/result.py` — paylaşılan altyapı
  (ns→sample pencere dönüşümü, `ProcessingResult`, işlem geçmişi kaydı,
  time-zero uyarı metni, padding maskesi).
- `processing/time_zero.py` — `correct_time_zero()`: `manual`,
  `channel_median_peak`, `channel_median_cross_correlation` yöntemleri.
- `processing/dc_offset.py` — `correct_dc_offset()`: `mean`, `median`
  yöntemleri, opsiyonel pencere.
- `qc/time_zero.py`, `qc/dc_offset.py` ve `qc/bscan.py`'a eklenen paylaşılan
  before/after/difference B-scan yardımcıları.
- `export/processed.py` — CSV/JSON/NPZ exportları.
- CLI: `time-zero`, `dc-offset`, `sprint2` alt komutları.
- Sentetik testler (`test_time_zero.py`, `test_dc_offset.py`,
  `test_processing_history.py`) + gerçek dosya entegrasyon testi
  (`test_sprint2_real_integration.py`).

## Out of Scope
Dewow, band-pass filtering, background removal, gain, AGC, F-K filtering,
velocity analysis, migration, Hilbert envelope, depth-slice, anomaly
detection, archaeological classification, QGIS export, Blender export, GUI,
trace-by-trace otomatik time-zero warping, sub-sample shifting. Hiçbiri
uygulanmadı; boş/sahte implementasyon da eklenmedi.

## Input Data
[[04_DATASETS/Swath003_Array02]] — Sprint 1'de doğrulanan gerçek dosya,
değişmeden kullanıldı (SHA-256 `66d840c3...b62a6`, Sprint 1'den bu yana
aynı).

## Algorithm Decisions
Tam gerekçe: [[06_DECISIONS/ADR_002_TimeZero_Reference_and_Shift_Policy]].
Özet:
- Time-zero shift'i her zaman **kanal-bazlı ve sabit**tir; trace-by-trace
  bağımsız kaydırma bu sprintte kesinlikle uygulanmadı.
- Otomatik pick, median trace üzerinde `peak_polarity` kriterine
  (`max_abs`/`positive_peak`/`negative_peak`) göre bulunur; picker'ın DC
  bias'a karşı kararlılığı için yalnızca geçici, kaydedilmeyen bir per-trace
  mean-removal kopyası kullanılır (nihai veriye asla yazılmaz).
  `channel_median_cross_correlation` yöntemi, referans kanalın kendi pikine
  göre diğer kanalları hizalar.
- `np.roll` ile kaydırma + açığa çıkan bölgenin `fill_value` ile
  doldurulması; wrap-around veriye asla sızmaz (`padding_mask` tek doğruluk
  kaynağı).
- `removed_component := input - output` (her iki işlem için de); bu eşitlik
  inşa yoluyla her yerde **tam olarak** geçerlidir (yalnızca "yaklaşık"
  değil) — time-zero'da padding bölgesindeki fiziksel yorum sınırlıdır ama
  matematiksel eşitlik bozulmaz.
- `max_shift_samples` aşılırsa **sessizce uygulanmaz**; kırpılır ve açık bir
  uyarı üretilir.
- **Otomatik pick, doğrulanmış fiziksel yüzey zamanı değildir** — bu ayrım
  her sonuçta `TIME_ZERO_REFERENCE_WARNING` ile açıkça belirtilir:
  *"Automatic time-zero picks are signal-processing references and are not
  independently calibrated physical surface times."*
- DC offset her (slice, channel) trace'i **bağımsız** düzeltir; tek bir
  global ofset asla kullanılmaz. Pencere verilmezse ve `method="mean"` ise,
  güçlü doğrudan dalganın tahmini etkileyebileceği açıkça uyarılır.

## Tasks
- [x] `processing/common.py`, `processing/result.py`
- [x] `processing/time_zero.py`
- [x] `processing/dc_offset.py`
- [x] `qc/time_zero.py`, `qc/dc_offset.py`, `qc/bscan.py` genişletmeleri
- [x] `export/processed.py`
- [x] CLI: `time-zero`, `dc-offset`, `sprint2`
- [x] Sentetik testler
- [x] Gerçek dosya entegrasyon testi
- [x] Regresyon (Sprint 1 testleri)
- [x] Kalite kontrolleri (ruff, mypy)
- [x] Gerçek dosyada CLI çalıştırması ve çıktı doğrulaması
- [x] Vault senkronizasyonu

## Acceptance Criteria
- Time-zero ve DC offset fonksiyonları girdiyi değiştirmez, yeni bir
  `GPRDataset`/`ProcessingResult` döndürür — **doğrulandı**
  ([[07_VALIDATION/Test_Results]]).
- Her iki fonksiyon da opsiyoneldir (ne CLI ne pipeline onları zorunlu
  kılmaz; `sprint2` komutu ikisini sırayla çalıştırır ama her biri tek
  başına da çağrılabilir) — **doğrulandı**
  (`test_operations_are_composable_in_either_order`).
- `processing_history`'ye parametreler, tanılama (diagnostics) ve uyarılar
  kaydedilir — **doğrulandı**.
- `removed_component` her iki işlemde de erişilebilir ve doğru — **doğrulandı**.
- Sentetik + gerçek dosya testleri geçer; Sprint 1 testleri kırılmadı —
  **doğrulandı** (77/77 passed).

## Synthetic Validation
40 yeni sentetik test (bkz. [[07_VALIDATION/Test_Results]] için tam liste):
`test_time_zero.py` (20 test: peak polarity doğruluğu, manual pick, kanal-
bazlı sabit shift, wrap-around yokluğu, padding maskesi, shape/immutability,
search window dışı olayın göz ardı edilmesi, geçersiz pencere hatası,
max_shift kırpması, processing history, hedef sample'da hizalama, removed
component eşitliği, gaussian noise ve DC bias'a karşı dayanıklılık, pencere
kenarına yakın pick), `test_dc_offset.py` (15 test), `test_processing_history.py`
(5 test: sıra doğruluğu, ham veri değişmezliği, ara veri geçmişinin
etkilenmemesi, iki yönde de birleştirilebilirlik, JSON serileştirme).

## Real Data Validation
Gerçek `Swath003_Array02.ogpr` üzerinde (bkz. [[07_VALIDATION/QC_Output_Validation]]):
- Time-zero (`channel_median_peak`, `max_abs`, arama 5–15 ns, target_sample=0,
  varsayılan `max_shift_samples=64`): pick'ler örnek 61–74 arasında (arama
  penceresi [40,120) içinde, doğrulandı); **9/11 kanal** varsayılan
  `max_shift_samples=64` sınırını aştığı için kırpıldı (kanal 3 ve 9 hariç,
  gerçek shift -61) — bu, güvenlik mekanizmasının **doğru çalıştığının**
  kanıtıdır, bir hata değildir. Tam tablo: [[04_DATASETS/Swath003_Array02]].
- DC offset (`mean`, tüm iz): offset ortalama ≈270.36 (Sprint 1'in ham
  genlik ortalamasıyla birebir eşleşiyor — çapraz doğrulama). Düzeltme
  sonrası trace mean'ler ~1e-4 büyüklüğüne düştü (pratik olarak sıfır).
- Birleşik pipeline (time-zero → dc-offset): `processing_history` sırası
  doğrulandı, ham dosya hash'i değişmedi, NaN/Inf yok.

## QC Outputs
`outputs/sprint02/{time_zero,time_zero_manual,dc_offset,dc_offset_windowed,combined}/`
— tam liste ve doğrulama: [[07_VALIDATION/QC_Output_Validation]].

## Issues Discovered
Geliştirme sırasında (kod hataları, düzeltildi — Sprint 1'deki "bilinen
belirsizlikler" listesine ek DEĞİL, bunlar gerçek kod hatalarıydı):
- `_cross_correlation_lag`'da `max_shift_samples` pencere uzunluğunu
  aştığında Python'un negatif indeks dilimlemesi (`arr[:-k]`) "boş" değil
  "sondan k eleman hariç" anlamına geldiği için shape uyuşmazlığı hatası
  oluşuyordu. Düzeltme: aday lag `min(max_shift_samples, pencere_uzunluğu-1)`
  ile sınırlandırıldı.
- `qc/dc_offset.py`'de `ax.hist(bins=...)` çağrısına `numpy.ndarray`
  verilmesi mypy tip hatası üretti (matplotlib stub'ları `Sequence[float]`
  bekliyor); `.tolist()` ile düzeltildi.
- `qc/geometry.py`'deki (Sprint 1) mypy hatası bu sprintte tekrar
  oluşmadı — önceden düzeltilmişti.

Gerçek veri bulgusu (hata değil, beklenen sonuç): varsayılan
`max_shift_samples=64` ve `target_sample=0` ile gerçek dosyanın 9 kanalı
kırpma sınırına giriyor. Bu, [[01_PROJECT_STATE/03_Open_Issues]]'a
ISSUE-005 olarak eklendi (bir "sorun" değil, kullanıcı için parametre
seçimi notu).

## Decisions
[[06_DECISIONS/ADR_002_TimeZero_Reference_and_Shift_Policy]] — kanal-bazlı
shift politikası, padding/wrap-around davranışı, target_sample semantiği,
otomatik pick'in fiziksel referans olmadığı ayrımı, manual pick desteği,
processing history yaklaşımı.

## Completion Summary
Sprint 2 kapsamındaki tüm görevler tamamlandı. Time-zero (3 yöntem) ve DC
offset (2 yöntem) doğru, immutable, test edilmiş ve QC'si eksiksiz şekilde
uygulandı. Gerçek dosya üzerinde uçtan uca çalıştırıldı; ham dosya
değişmedi (hash doğrulandı), tüm çıktılar üretildi ve doğrulandı. Sprint 1
testleri (36) hiç bozulmadı; toplam 77/77 test geçti. Kapsam dışı hiçbir
işleme algoritması uygulanmadı.

## Next Sprint Recommendation
Sprint 3 — Dewow + Band-pass filtering (yalnızca bunlar + ilgili frekans
spektrumu QC + sentetik/gerçek veri testleri). Detay:
[[01_PROJECT_STATE/02_Next_Development_Sprint]]. Background removal, gain
ve F-K Sprint 3'e dahil edilmedi.
