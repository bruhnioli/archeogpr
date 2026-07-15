---
type: adr
tags: [decision]
id: ADR-003
status: accepted
date: 2026-07-15
---

# ADR-003 — Overflow Policy and Padding-Aware DC Offset

## Context
Sprint 2.1 (bkz. [[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]]),
Sprint 2'nin gerçek veri sonuçlarını denetlerken iki somut sorun buldu:
(1) [[ADR_002_TimeZero_Reference_and_Shift_Policy]] madde 6'nın tanımladığı
"aşan shift her zaman kırpılır" davranışı, gerçek dosyada 9/11 kanalı
`target_sample=0`'a hizalanmamış bir sonucu, normal bir "başarı" gibi
döndürüyordu; (2) `correct_dc_offset()`, time-zero'nun ürettiği padding
bölgesinden habersizdi ve onu gerçek veri gibi işleyip kirletiyordu (bkz.
Sprint 2.1 notundaki "Code-Level Audit Findings"). Bu ADR, her iki sorunu
çözen tasarım kararlarını kaydeder ve **ADR-002 madde 6'yı bu noktada
supersede eder** (ADR-002'nin diğer maddeleri — kanal-bazlı sabit shift,
padding/wrap-around mekaniği, `target_sample` semantiği, otomatik pick'in
fiziksel referans olmadığı ayrımı, `removed_component` tanımı — değişmeden
geçerlidir).

## Decision
1. **`overflow_policy: Literal["error", "clip"]`, varsayılan `"error"`.**
   Bir kanalın istenen shift'i `max_shift_samples`'ı aştığında, varsayılan
   davranış artık **veriye hiç dokunmadan** `ProcessingError` fırlatmaktır
   (kanal başına detaylı mesajla: hangi kanal, istenen shift, sınır).
   Kırpılmış/eksik bir sonuç asla normal bir başarı çıktısı gibi
   döndürülmez veya diske yazılmaz. Sebep: ADR-002 madde 6'nın "kırp + uyar"
   davranışı, gerçek dosyada 9/11 kanalın sessizce (yalnızca bir metin
   uyarısıyla, hiçbir sert engelle) yanlış hizalanmasına yol açtı — bu bir
   kod hatası değildi ama güvenli bir varsayılan değildi.
2. **`overflow_policy="clip"` yalnızca açık opt-in.** Kırpma hâlâ mümkündür
   (bazı kullanım senaryolarında kasıtlı olarak istenebilir) ama YALNIZCA
   çağıran taraf bunu açıkça talep ederse. Sonuç `diagnostics["has_clipped_
   shifts"]=True` ve `diagnostics["valid_for_downstream_processing"]=False`
   ile işaretlenir; CLI bu durumda ek bir konsol uyarısı basar. Bu iki
   bayrak, bir sonucun downstream'e (örn. gelecekteki Sprint 3 filtreleri)
   güvenle aktarılıp aktarılamayacağını makine-okunabilir şekilde belirtir.
3. **`ProcessingResult.valid_mask: np.ndarray | None`, şekil `(channels,
   samples)`.** Time-zero, her kanal için hangi örneklerin gerçek
   kaydırılmış veri (`True`) hangisinin `fill_value` padding'i (`False`)
   olduğunu bu maskede döndürür. `(slices, channels, samples)` DEĞİL —
   kanal-bazlı sabit shift (ADR-002 madde 1) sayesinde geçerlilik her
   slice için aynıdır, üçe katlama gereksizdir. Salt-okunur
   (`ProcessingResult.__post_init__` içinde dondurulur).
4. **`correct_dc_offset(..., valid_mask=...)`.** Verildiğinde: ofset
   SADECE `window ∩ valid_mask` kesişimindeki örneklerden hesaplanır;
   çıkarma SADECE geçerli konumlara uygulanır (padding pozisyonları
   girdiden hiç okunmaz/yazılmaz, dolayısıyla `fill_value`'da byte-bazında
   değişmeden kalır — fabrikasyon bir "−ofset bandı" asla oluşmaz). Bir
   kanalın pencere içinde sıfır geçerli örneği varsa açık `ProcessingError`
   verilir (sessizce NaN/0 üretmek yerine). Maske verilmezse (`None`,
   varsayılan), davranış Sprint 2'deki ile birebir aynıdır — bu, mevcut
   (maskesiz) çağıran kodun kırılmaması için kasıtlı bir geriye dönük
   uyumluluk kararıdır.
5. **`sprint2` CLI komutu, DC offset'e time-zero'nun `valid_mask`'ını
   otomatik geçirir.** Kullanıcı ayrıca bir bayrak belirtmek zorunda
   değildir — birleşik pipeline'da padding güvenliği varsayılan davranıştır.
6. **Gerçek veri doğrulaması için `max_shift_samples=96` kullanıldı, ama
   bu kodda yeni bir varsayılan DEĞİLDİR.** Varsayılan `max_shift_samples`
   hâlâ `64`'tür (fonksiyon imzasında); `96` yalnızca Sprint 2.1'in
   doğrulama komutlarında açıkça geçirilen bir CLI/fonksiyon argümanıdır.

## Alternatives Considered
- **Varsayılanı `"clip"` olarak bırakıp sadece uyarı metnini
  güçlendirmek:** Reddedildi. Bir metin uyarısı, otomatize edilmiş bir
  pipeline'da (örn. gelecekteki bir toplu işleme script'i) kolayca gözden
  kaçar; `valid_for_downstream_processing` gibi makine-okunabilir bir
  bayrak + varsayılan hata, aynı hatanın tekrarını yapısal olarak önler.
- **`valid_mask`'ı `(slices, channels, samples)` şeklinde saklamak:**
  Reddedildi — kanal-bazlı sabit shift nedeniyle her slice için özdeş
  olurdu; 3 katı bellek, ek bilgi olmadan.
  `valid_mask[np.newaxis, :, :]` ile çağıran taraf istediğinde
  broadcast edebilir.
  Consequences bölümünde not edildi.
- **Padding'i DC offset'ten önce ayrı bir adımda kırpıp sonra geri
  birleştirmek:** Reddedildi — gereksiz karmaşıklık; boolean mask ile
  hesaplama/atama filtrelemesi hem daha basit hem daha az hata payı
  bırakıyor.
- **`valid_mask`'ı `processing_history`'ye tam array olarak yazmak:**
  Reddedildi — `processing_history` JSON-serializable ve okunabilir
  kalmalı; onun yerine sadece özet istatistikler (`total_valid_samples`,
  `total_padded_samples`, kanal başına sayımlar) `diagnostics`'e yazılır,
  maskenin kendisi yalnızca `ProcessingResult.valid_mask` ve NPZ
  export'unda bulunur.

## Consequences
- ADR-002 madde 6 artık yalnızca tarihsel bir referanstır; gerçek davranış
  bu ADR'dedir. ADR-002'nin başına bu ADR'ye işaret eden bir not eklendi.
- Mevcut (Sprint 2) çağıran kod, `overflow_policy` belirtmeden bir
  overflow senaryosuna girerse artık `ProcessingError` alır (önceden
  sessizce kırpılıyordu) — bu KASITLI bir davranış değişikliğidir; bkz.
  [[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]] Testing bölümü,
  `test_shift_exceeding_max_shift_samples_is_clipped_with_warning_when_clip_is_requested`
  bu değişikliği yansıtacak şekilde güncellendi.
- Gelecekteki tüm işleme modülleri (dewow, gain, vb.), kendi girdisi bir
  time-zero `valid_mask`'ı taşıyorsa, aynı "padding'i hesaplama VE
  yazmadan hariç tut" desenini benimsemelidir — bu artık projenin
  padding-güvenliği için referans deseni.
- `target_sample` seçimi (0 vs 16) bu ADR'nin kapsamı DIŞINDADIR — bu
  yalnızca BİR TEKNIK POLİTİKA kararıdır (nasıl kırpılır/maskelenir),
  HANGİ target_sample'ın doğru olduğuna karar vermez. O karar insan/
  jeofizik incelemesine bırakılmıştır (bkz.
  [[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]] "Next Action").

## Validation
- `tests/test_time_zero.py` (+11), `tests/test_dc_offset.py` (+10),
  `tests/test_export_processed.py` (yeni, +3, NPZ round-trip),
  `tests/test_sprint2_real_integration.py` (+1) — toplam 101/101 test
  geçti (bkz. [[07_VALIDATION/Test_Results]]).
- Gerçek dosyada uçtan uca doğrulama: `target_sample` 0 ve 16, her ikisi
  `max_shift_samples=96, overflow_policy=error` ile sıfır kırpma; birleşik
  pipeline'da padding, DC offset'ten sonra tam olarak `fill_value`'da
  (`[0.0]`) kaldı (bkz.
  [[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]] "Real Data
  Validation").

## Related Files
- `src/archaeogpr/processing/time_zero.py`
- `src/archaeogpr/processing/dc_offset.py`
- `src/archaeogpr/processing/result.py`
- `src/archaeogpr/cli.py`
- [[ADR_002_TimeZero_Reference_and_Shift_Policy]]
- [[05_PROCESSING/Time_Zero_Correction]]
- [[05_PROCESSING/DC_Offset]]
- [[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]]
