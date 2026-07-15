---
type: adr
tags: [decision]
id: ADR-002
status: accepted
date: 2026-07-14
---

# ADR-002 — Time-Zero Reference and Shift Policy

> **Amendment (2026-07-15):** Madde 6 ("`max_shift_samples` aşılırsa
> sessizce uygulanmaz. Kırpılır VE açık bir uyarı üretilir.") Sprint 2.1'de
> [[ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]] tarafından
> supersede edildi — gerçek dosyada bu davranış 9/11 kanalı sessizce (yalnızca
> metin uyarısıyla) kırpıyordu. Yeni varsayılan: `overflow_policy="error"`
> (veriye dokunmadan hata); kırpma yalnızca açık opt-in. Bu sayfanın kalan
> maddeleri (1–5, 7, 8) değişmeden geçerlidir.

## Context
Sprint 2, `correct_time_zero()` fonksiyonunu (bkz.
[[02_SPRINTS/Sprint_02_TimeZero_DCOffset]]) uyguladı. Bu, projenin ilk
sinyal işleme fonksiyonuydu ve birkaç kritik, gelecekteki tüm işleme
modüllerini etkileyecek tasarım kararı gerektirdi: kaydırmanın granülerliği
(iz-bazlı mı kanal-bazlı mı), açığa çıkan (padding) bölgenin nasıl
işaretleneceği, "hedef sample" davranışının anlamı, ve en önemlisi —
otomatik bir pick'in ne olduğu/olmadığı konusunda dürüst bir epistemik
duruş.

## Decision
1. **Kaydırma her zaman kanal-bazlı ve sabittir.** Bir kanalın TÜM
   slice'ları aynı tam sayı örnek kaydırmasını alır. İz-bazlı (trace-by-
   trace) bağımsız otomatik kaydırma bu sprintte kesinlikle uygulanmadı
   (CLAUDE.md ve görev tanımı bunu açıkça yasaklıyor). Sebep: iz-bazlı
   serbest kaydırma, gürültüden kaynaklanan sahte "hizalamalar"
   üretebilir ve gerçek jeolojik/arkeolojik yapıyı bozabilir; kanal-bazlı
   sabit kaydırma ise antenin fiziksel/donanımsal gecikme farkını
   düzeltir, veriyi "düzleştirmez."
2. **Padding/wrap-around politikası:** `np.roll` ile kaydırma yapılır,
   ardından açığa çıkan bölge (`padding_mask()` ile tam olarak
   belirlenir) `fill_value` ile doldurulur. Wrap-around veriye ASLA
   sızmaz. `padding_mask()`, `processing/common.py` içinde TEK doğruluk
   kaynağıdır — hem düzeltme fonksiyonu hem QC görselleştirmesi bunu
   kullanır.
3. **`target_sample` semantiği:** Seçilen olay `target_sample` konumuna
   taşınır. `time_ns` dizisi SAYISAL olarak değişmez (her zaman
   `arange(samples)*sampling_time_ns`) — değişen şey örnek 0'ın hangi
   fiziksel olaya karşılık geldiğidir. `target_sample > 0` durumunda bu,
   `diagnostics["target_sample"]` ve `channel_picks_time_ns` üzerinden
   açıkça izlenebilir. Fiziksel derinlik dönüşümü bu sprintte YAPILMAZ.
4. **Otomatik pick, fiziksel yüzey zamanı değildir.** Bu üç kavram
   kesinlikle ayrı tutulur:
   - *Detected time-zero*: Algoritmanın (median trace + peak_polarity
     veya cross-correlation) seçtiği örnek — `channel_picks`.
   - *Applied reference sample*: Seçilen olayın taşındığı hedef —
     `target_sample`.
   - *Physical surface time*: Saha kalibrasyonu OLMADAN kesinleşmeyen
     fiziksel referans — bu proje hiçbir zaman iddia etmez.
   Her `ProcessingResult.warnings` ve `processing_history` kaydında
   `TIME_ZERO_REFERENCE_WARNING` sabiti bulunur: *"Automatic time-zero
   picks are signal-processing references and are not independently
   calibrated physical surface times."*
5. **Manual pick desteği ana kontrol yöntemidir.** `method="manual"`,
   jeofizikçi tarafından doğrulanmış pick'lerin uygulanması içindir ve
   EKSİKSİZ olmalıdır — bir kanal eksikse açık hata (`ProcessingError`)
   verilir, sessiz fallback uygulanmaz.
6. **`max_shift_samples` aşılırsa sessizce uygulanmaz.** Kırpılır VE açık
   bir uyarı üretilir (`"channel N: requested shift ... clipped to ..."`).
   Gerçek dosyada bu davranış doğrulandı: varsayılan `max_shift_samples=64`
   ile 9/11 kanal kırpıldı (bkz.
   [[02_SPRINTS/Sprint_02_TimeZero_DCOffset]] Real Data Validation).
7. **Processing history yaklaşımı:** Her işlem, `build_processing_record()`
   ile standart bir kayıt üretir (`operation`, `archaeogpr_version`,
   `applied_at`, `parameters`, `diagnostics`, `warnings`) ve
   `dataset.with_processing_step` yerine doğrudan
   `dataclasses.replace(dataset, amplitudes=..., processing_history=(...))`
   kullanılır (aynı sonuç, tek adımda).
8. **`removed_component := input - output`** (hem time-zero hem DC offset
   için). Bu tanım, `input == output + removed_component` eşitliğinin
   HER ZAMAN (yaklaşık değil, tam olarak) doğru olmasını sağlar. Padding
   bölgesinde bu fark `input - fill_value`'a eşittir — matematiksel olarak
   geçerlidir ama "fiziksel olarak neyin çıkarıldığı" yorumunun yalnızca
   padding-dışı ortak bölgede anlamlı olduğu ayrıca belgelenmiştir.

## Alternatives Considered
- **İz-bazlı (trace-by-trace) otomatik kaydırma:** Reddedildi. Görev
  tanımı ve CLAUDE.md bunu açıkça bu sprint için yasaklıyor; ayrıca
  gürültüye karşı dayanıksız olurdu.
- **Sub-sample (kesirli) kaydırma/interpolasyon:** Reddedildi (bu sprint
  için gereksiz karmaşıklık; görev tanımı zorunlu kılmıyor).
- **`removed_component`'i yalnızca padding-dışı bölgede tanımlamak (örn.
  padding bölgesinde `NaN`):** Değerlendirildi, reddedildi. Bu,
  `ProcessingResult`'ın "shape girdiyle aynı olmalı" ve "JSON-serializable
  diagnostics" gereksinimleriyle gereksiz bir karmaşıklık (NaN
  yayılımı riski) katardı; onun yerine basit, her zaman geçerli bir
  tanım (`input - output`) seçildi ve yorumlama sınırı ayrıca belgelendi.
- **Cross-correlation için referans kanalın da cross-correlation ile
  bulunması:** Reddedildi. Referans kanalın kendi mutlak konumu
  (`target_sample`'a göre) mutlaka `peak_polarity` ile bulunmalı; aksi
  halde hiçbir kanal `target_sample`'a çapa atmazdı.

## Consequences
- Kanal-bazlı sabit kaydırma, bazı kanallarda (gerçek dosyada 9/11)
  `max_shift_samples` varsayılanını aşabilir — kullanıcı bu parametreyi
  saha verisine göre ayarlamalıdır (bkz. [[01_PROJECT_STATE/03_Open_Issues]]
  ISSUE-005).
- Gelecekteki tüm işleme modülleri (dewow, gain, vb.) aynı
  `ProcessingResult` modelini ve `build_processing_record()` desenini
  kullanmalıdır — tutarlılık sağlanır ama her yeni modül bu sözleşmeye
  uymak zorundadır.

## Validation
- `tests/test_time_zero.py` (20 test): peak polarity doğruluğu, kanal-bazlı
  sabit kaydırma (bir slice'ın kendi bağımsız pikinin YOK SAYILDIĞININ
  doğrulanması dahil), wrap-around yokluğu, padding maskesi tutarlılığı,
  max_shift kırpması + uyarı, `TIME_ZERO_REFERENCE_WARNING`'in her sonuçta
  bulunması, removed_component eşitliğinin tam olarak (`atol` gerekmeden)
  doğrulanması.
- Gerçek dosya: [[02_SPRINTS/Sprint_02_TimeZero_DCOffset]] Real Data
  Validation bölümü.

## Related Files
- `src/archaeogpr/processing/time_zero.py`
- `src/archaeogpr/processing/common.py`
- `src/archaeogpr/processing/result.py`
- [[03_ARCHITECTURE/Processing_Pipeline_Architecture]]
- [[05_PROCESSING/Time_Zero_Correction]]
- [[04_DATASETS/Swath003_Array02]]
