---
type: processing-module
status: implemented
implemented: true
---

# DC Ofset Giderimi (DC Offset Removal)

> Sprint 2'de implemente edildi. Kod: `src/archaeogpr/processing/dc_offset.py`.

## Purpose

Her (slice, channel) izindeki sabit (frekanssız) amplitüd yanlılığını
(bias/DC bileşeni) **bağımsız olarak** gidermek — tek bir global ofset
asla kullanılmaz.

## Input

Herhangi bir `GPRDataset` (time-zero uygulanmış olması gerekmez, ama
`processing/Processing_Order`'a göre time-zero'dan sonra gelmesi önerilir).

## Output

Aynı shape/dtype'a sahip **yeni** bir `GPRDataset`; her trace'in
ortalaması sıfıra çekilmiş olur. `ProcessingResult.removed_component`, her
trace boyunca sabit ofset değerinin tekrarlandığı, girdiyle aynı shape'e
sahip bir array'dir.

## Mathematical Basis

Her trace için: `offset[i,j] = location(trace[i,j, pencere ∩ valid_mask])`,
`corrected[i,j,t] = trace[i,j,t] - offset[i,j]` (yalnızca `t ∈ valid_mask`
için; `valid_mask` verilmezse tüm örnekler geçerli sayılır — Sprint 2
davranışıyla birebir aynı). `location` = `mean` veya `median`. Hesaplama
float64 ara hassasiyetle yapılır, çıktı girdinin dtype'ına (float32)
döndürülür — bu açıkça belgelenmiş bir dtype politikasıdır.
`valid_mask=False` olan konumlar girdiden hiç okunmaz/yazılmaz — bu yüzden
time-zero'nun `fill_value`'unda byte-bazında değişmeden kalırlar (Sprint 2.1,
bkz. ADR-003).

## Parameters

`method` (`mean`/`median`), `window_start_ns`/`window_end_ns` (opsiyonel;
verilmezse tüm iz kullanılır, ikisi de verilmeli veya ikisi de atlanmalı),
`valid_mask` (opsiyonel, şekil `(channels, samples)` bool — tipik olarak
`correct_time_zero()`'nun `ProcessingResult.valid_mask`'ı; Sprint 2.1),
`window_reference` (`"dataset_time"`/`"sample_index"`, varsayılan
`"dataset_time"`; Sprint 2.2, bkz. ADR-004). Tam imza:
`src/archaeogpr/processing/dc_offset.py::correct_dc_offset`.

**(Sprint 2.2)** `window_reference="dataset_time"` (varsayılan), pencereyi
`dataset.time_ns`'in kendisine göre çözer — time-zero-relative bir eksende
bu, aynı ns penceresinin farklı `target_sample` değerlerinde AYNI ham
örnekleri seçmesini sağlar (target-invariance, gerçek veride doğrulandı).
`"sample_index"`, Sprint 2.2 öncesi davranışı (mutlak örnek konumu,
`time_ns`'ten bağımsız) korur. **Canonical politika**
(`method="mean", window_start_ns=20.0, window_end_ns=100.0,
window_reference="dataset_time"`) fonksiyonun kendi varsayılanı DEĞİLDİR —
yalnızca CLI'nin varsayılanıdır, `--dc-window-start-ns` vb. ile
değiştirilebilir.

## Risks

- `method="mean"` ve pencere verilmezse, güçlü doğrudan dalga tüm-iz
  ortalamasını etkileyebilir — bu durumda otomatik bir uyarı üretilir
  ("Offset computed as the full-trace mean with no window; a strong
  direct/air wave can bias this estimate...").
- `method="median"`, aykırı değerlere (örn. güçlü doğrudan dalga) karşı
  daha dayanıklı bir alternatiftir.
- Ofset penceresi gerçek sinyal içeriyorsa, çıkarılan "ofset" sinyalin bir
  kısmını taşıyabilir.
- NaN/Inf üretilirse (girdi zaten bozuksa) fonksiyon **hata verir**, sessizce
  geçmez.
- Bir kanalın seçilen pencere içinde `valid_mask` ile sıfır geçerli örneği
  varsa (tüm pencere padding ise) fonksiyon **hata verir**.
- **(Sprint 2.1'de bulundu ve düzeltildi.)** `valid_mask` verilmeden
  time-zero'dan sonra çağrılırsa, padding örnekleri gerçek veri gibi
  işlenip fabrikasyon bir ofset bandı üretebilirdi (somut reprodüksiyon:
  `[0,0,0,...]` → `[-8,-8,-8,...]`). `sprint2` CLI komutu artık
  `valid_mask`'ı otomatik geçirir; standalone kullanımda çağıran taraf
  bunu açıkça geçirmelidir. Bkz.
  [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-007.
- **(Sprint 2.2'de bulundu ve düzeltildi.)** Pencere verilmeden (tüm-valid-
  trace ortalaması) kullanmak, `target_sample`'a bağımlı bir sonuç
  üretiyordu — gerçek veride `target_sample=0` ile ≈-398.5,
  `target_sample=16` ile ≈81.7 (aynı kanallar, aynı pick'ler). Kök neden:
  bu istatistik, güçlü erken pulse'ın ne kadarının "valid" kaldığına bağlı.
  Çözüm: canonical politika artık zaman-referanslı, sabit bir pencere
  (`window_reference="dataset_time"`, 20-100 ns) kullanıyor — bkz. ADR-004,
  [[02_SPRINTS/Sprint_02_2_TimeAxis_DCWindow_Validation]].
- **(Sprint 2.2, açık belirsizlik — hata değil.)** Aynı pencerede
  `mean` ve `median` gerçek veride bazı kanallarda İŞARET bile
  değiştirecek kadar farklılaşıyor (`max_abs_difference≈226.4`) — bkz.
  [[07_VALIDATION/Known_Uncertainties]].

## Required QC

`outputs/sprint02/dc_offset/`: `offsets.csv`, channel00 before/after/
difference B-scan (aynı clip), ofset histogramı, trace mean before/after
karşılaştırması, kanal-bazlı ofset boxplot'u. Sprint 2.1'den itibaren,
`valid_mask` verildiğinde `diagnostics` ayrıca geçerli/padding-only
ortalamalarını ve padding değer istatistiklerini içerir (bkz.
[[07_VALIDATION/QC_Output_Validation]] "Sprint 2.1" bölümü). Tam liste ve
doğrulama: [[07_VALIDATION/QC_Output_Validation]].

## Acceptance Criteria

Tümü doğrulandı: (1) girdi mutasyona uğramaz, (2) her trace için ofset
`removed_component` ve `offsets.csv` üzerinden erişilebilir, (3) sentetik
sabit-ofsetli veri sıfıra iner (`atol=1e-4`), (4) fonksiyon opsiyoneldir,
(5) `valid_mask` verildiğinde padding hem ofset hesaplamasından hem
çıkarmadan hariç tutulur ve `fill_value`'da değişmeden kalır (Sprint 2.1,
gerçek veride doğrulandı).

## Implementation Status

**Implemented: true** (Sprint 2; `valid_mask` Sprint 2.1'de,
`window_reference`/canonical pencere Sprint 2.2'de eklendi). Sentetik
testler: `tests/test_dc_offset.py` (31 test: 15 Sprint 2 + 9 Sprint 2.1 +
7 Sprint 2.2). Gerçek dosya entegrasyonu:
`tests/test_sprint2_real_integration.py`, `tests/test_target_invariance.py`.

## Related Modules

[[Processing_Index]], [[Processing_Order]], [[Time_Zero_Correction]], [[Dewow]]
