---
type: adr
tags: [decision]
id: ADR-004
status: accepted
date: 2026-07-15
---

# ADR-004 — Time-Zero-Relative Time Axis and DC Window

## Context
Sprint 2.1'in gerçek veri karşılaştırması, aynı kanallar ve aynı otomatik
pick'lerle çalıştırıldığında `target_sample=0` ve `target_sample=16`
adaylarının DC offset ortalamalarının çarpıcı biçimde farklı çıktığını
gösterdi (yaklaşık -398.5 vs 81.7). Bu fark, tüm-valid-trace ortalamasının
(1) time-zero'nun ürettiği güçlü, asimetrik erken pulse'ın ne kadarının
"valid" bölgede kaldığına ve (2) `correct_time_zero()`'nun `time_ns`'i HİÇ
değiştirmemesi nedeniyle bir ns penceresinin daima MUTLAK örnek konumuna
(sample 0 = 0 ns varsayımıyla) çözülmesine bağlı olduğunu ortaya çıkardı —
bu iki neden de aynı ns penceresinin farklı `target_sample` değerlerinde
FİZİKSEL olarak farklı bölgeleri seçmesine yol açıyordu. Bu ADR, bu sorunu
kalıcı olarak çözen iki bağlantılı tasarım kararını kaydeder.

## Decision
1. **`correct_time_zero()`, `time_ns`'i time-zero-relative olarak yeniden
   üretir.** Yeni eksen: `time_ns = (arange(samples) - target_sample) *
   sampling_time_ns`. Böylece `time_ns[target_sample] == 0.0` (tam olarak,
   float toleransı içinde), `target_sample`'dan önceki örnekler negatif,
   sonraki örnekler pozitiftir. Örnek aralığı (`sampling_time_ns`) değişmez.
   Bu, HER yöntem için (artık `manual` dahil) `sampling_time_ns`'in zorunlu
   olmasını gerektirir — önceden yalnızca otomatik yöntemler için
   zorunluydu.
2. **Önceki eksen sessizce atılmaz.** `diagnostics["time_axis"]`,
   `target_sample`, `time_zero_reference_ns=0.0`, önceki ve düzeltilmiş
   eksenin başlangıç/bitiş değerlerini kaydeder — tam array değil, onu
   yeniden inşa etmeye yetecek özet parametreler (bkz.
   [[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]]'deki aynı ilke:
   büyük array'ler `processing_history`'ye yazılmaz).
3. **`correct_dc_offset()`, `window_reference: Literal["dataset_time",
   "sample_index"]` alır, varsayılan `"dataset_time"`.** `"dataset_time"`,
   pencereyi `dataset.time_ns`'in KENDİSİNE göre çözer
   (`(time_ns >= start_ns) & (time_ns < end_ns)`) — bu, `target_sample`'a
   bağlı olarak FARKLI mutlak örnek aralıkları seçer ama AYNI ham
   (kaydırma-öncesi) örnekleri seçer, çünkü zaman ekseni tam olarak
   kaydırmayı telafi edecek şekilde yeniden tanımlanmıştır. `"sample_index"`
   eski (Sprint 2.2 öncesi) davranışı korur: `round(ns/sampling_time_ns)`
   ile mutlak örnek konumu, `time_ns`'ten bağımsız.
4. **Bütün-trace (whole-valid-trace) ortalaması ASLA canonical DC offset
   referansı olarak kullanılmaz.** Sebep: bu istatistik, ne kadar erken
   pulse örneğinin "valid" bölgede kaldığına (yani `target_sample`'a)
   bağlıdır — fiziksel olarak sabit bir referans değildir. Onun yerine
   canonical politika, time-zero olayından yeterince uzak, sabit bir ns
   penceresi kullanır (`window_start_ns=20.0, window_end_ns=100.0,
   window_reference="dataset_time"`, `method="mean"`) — bu pencerenin
   `target_sample`'dan bağımsız olarak AYNI ham örnekleri seçtiği, gerçek
   veride 11 kanalın hepsinde doğrulandı (bkz. Validation).
5. **`method="median"` sonucu QC amacıyla hesaplanır ama canonical çıktıya
   otomatik uygulanmaz.** Gerçek veride mean ve median, bazı kanallarda
   işaret bile değiştirecek kadar (`max_abs_mean_vs_median_difference ≈
   226.4`) farklılaşıyor — bu, pencerenin genlik dağılımının her kanalda
   basit/simetrik olmadığını gösteriyor ve hangi yöntemin daha uygun
   olduğuna dair açık bir bilimsel belirsizlik olarak kayıtlıdır (bkz.
   [[07_VALIDATION/Known_Uncertainties]]).
6. **`target_sample=16`, mühendislik önerisi olarak kaydedilir — fiziksel
   bir iddia DEĞİLDİR.** Gerekçe: pick'i array sınırından uzak tutar, 16
   pre-zero örneğini korur, `target_sample=0`'a göre daha az öndeki veri
   kaybı (45-58 örnek atılır, 61-74 yerine) ve daha az trailing padding
   üretir, pozitif zaman bölgesindeki veriyi değiştirmez. *"target_sample=16
   is the recommended storage/processing reference. It is not an
   independently calibrated physical ground-surface time."* Otomatik
   pick'in fiziksel anlamı bu kararla değişmez (bkz. ADR-002/ADR-003).
7. **20-100 ns penceresi kalıcı/sabit bir bilimsel gerçek değil, bir
   BAŞLANGIÇ politikasıdır.** CLI'dan `--dc-window-start-ns`/
   `--dc-window-end-ns`/`--dc-window-reference` ile değiştirilebilir;
   `correct_dc_offset()`'in kendi varsayılanı hâlâ "pencere yok/tüm iz"tir
   (20/100 CLI-seviyesi bir varsayılandır, fonksiyona sabit gömülmemiştir).
   Şu uyarı `dc_offset.py` kullanım belgesinde durur: *"The selected 20-100
   ns window is an initial processing choice and requires geophysical
   validation for other datasets or acquisition settings."*

## Alternatives Considered
- **Whole-trace mean'i `valid_mask`'la sınırlı tutup yeterli kabul etmek:**
  Reddedildi. Sprint 2.1 bunu zaten uyguluyordu (padding hariç tutuluyordu)
  ama bu, ADR'nin Context bölümündeki asıl sorunu (target_sample'a göre
  DEĞİŞEN bir istatistik) çözmüyordu — padding'in doğru ele alınması ayrı
  bir sorundu (ADR-003), whole-trace'in fiziksel referans olarak
  kararsızlığı başka bir sorundu (bu ADR).
- **`time_ns`'i değiştirmeden, DC offset'e ayrıca bir `target_sample`
  parametresi geçirip pencereyi manuel kaydırmak:** Reddedildi.
  `correct_dc_offset()`'in time-zero'nun iç semantiğinden (shift, pick)
  habersiz kalması istendi (ayrı sorumluluklar); `time_ns`'i düzeltmek,
  bu bilgiyi DC offset'in zaten okuduğu genel bir alana (`dataset.time_ns`)
  doğal olarak taşıyor.
- **`target_sample`'ı otomatik seçmek (örn. hangi değer en düşük mean/median
  farkını veriyorsa):** Reddedildi — görev tanımı ve proje kuralları
  otomatik target_sample seçimini kesinlikle yasaklıyor. Öneri (16) insan
  tarafından gözden geçirilebilir bir mühendislik notu olarak kaydedildi,
  koda gömülü bir "otomatik karar" mekanizması OLARAK değil.

## Consequences
- `correct_time_zero()`'yu çağıran her kod artık `sampling_time_ns`
  metadata'sının mevcut olmasını gerektirir (manual method dahil) — bu,
  geriye dönük bir davranış değişikliğidir ama mevcut tüm test fixture'ları
  ve gerçek dosya zaten bu alanı sağladığı için pratikte hiçbir çağıranı
  bozmadı.
- Gelecekteki tüm zaman-pencereli işlemler (örn. Sprint 3'ün dewow/band-pass
  filtreleri, eğer zaman pencereli bir parametre alırlarsa) aynı
  `window_reference="dataset_time"` desenini benimsemelidir — bu artık
  projenin zaman-referanslı pencereleme için standart deseni.
- `outputs/sprint02/combined/` (Sprint 2, kırpılmış) ve
  `outputs/sprint02_review/` (Sprint 2.1 adayları, eski whole-trace DC
  offset) her ikisi de artık `outputs/sprint02/canonical_target16/`
  tarafından supersede edildi — silinmediler, sidecar notlarla
  işaretlendiler.

## Validation
- 22 yeni test (`tests/test_time_zero.py` +10, `tests/test_dc_offset.py`
  +7, `tests/test_target_invariance.py` yeni dosya +5) — toplam 123/123
  test geçti (bkz. [[07_VALIDATION/Test_Results]]).
- Gerçek dosyada: `target_sample` 0 ve 16, aynı `[20,100)` ns penceresiyle,
  her 11 kanalda AYNI ham (kaydırma-öncesi) örnek aralığını seçti
  (`raw_window_matches=true`); ofset array'leri tam olarak (fark=0.0) eşit;
  ortak göreli-zaman bölgesindeki (1008/1024 örnek) genlikler tam olarak
  eşit. Bkz. `outputs/sprint02_2_validation/VALIDATION_RESULT.md`,
  [[02_SPRINTS/Sprint_02_2_TimeAxis_DCWindow_Validation]].

## Related Files
- `src/archaeogpr/processing/time_zero.py`
- `src/archaeogpr/processing/dc_offset.py`
- `src/archaeogpr/processing/common.py` (`time_zero_relative_time_ns`,
  `dataset_time_window_mask`)
- `src/archaeogpr/cli.py`
- [[ADR_002_TimeZero_Reference_and_Shift_Policy]]
- [[ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]]
- [[05_PROCESSING/Time_Zero_Correction]]
- [[05_PROCESSING/DC_Offset]]
- [[02_SPRINTS/Sprint_02_2_TimeAxis_DCWindow_Validation]]
