---
type: adr
tags: [decision]
id: ADR-006
status: accepted
date: 2026-07-15
---

# ADR-006 — Zero-Phase Band-Pass Filtering and Masked-Segment Handling

## Context
Sprint 3 band-pass filtresi (`correct_bandpass()`), yansıma zamanlamasını
(reflection timing) bozmadan nominal frekans bandı dışındaki gürültüyü
reddetmelidir — `CLAUDE.md`'nin de dolaylı olarak gerektirdiği gibi, bir
filtrenin faz davranışı derinlik/zaman yorumlamasını sessizce
kaydırmamalıdır. Bu ADR, iki bağımsız filtre yönteminin (Butterworth,
Ormsby) tasarımını, faz-koruma doğrulama metodolojisini ve dewow ile
paylaşılan maskeli-segment politikasını kaydeder.

## Decision
1. **İki bağımsız yöntem, ikisi de sıfır-faz (zero-phase) olacak şekilde
   tasarlandı:**
   - `method="butterworth"`: `scipy.signal.butter(..., output="sos")` +
     `scipy.signal.sosfiltfilt(...)` — ileri-geri (forward-backward)
     çift geçiş, etkin genlik tepkisini karesi alınmış hale getirir ama
     net fazı sıfırlar. `zero_phase=False`, tek geçişli `sosfilt`'e düşer
     — bu KASITLI OLARAK gerçek bir faz gecikmesi üretir ve YALNIZCA
     sıfır-faz özelliğinin karşıtlıkla kanıtlanması için tutulur, canonical
     kullanım için değildir.
   - `method="ormsby"`: gerçek (kompleks değil), simetrik bir yamuk
     (trapezoidal) transfer fonksiyonu, doğrudan FFT çarpımıyla uygulanır.
     Gerçek bir transfer fonksiyonu yapısı gereği sıfır-fazdır — bu yöntem
     için ayrı bir `zero_phase` anahtarı yoktur.
2. **Parametre doğrulaması açık ve kesin:** Butterworth `0 < lowcut_mhz <
   highcut_mhz < nyquist_mhz` ve `order >= 1`; Ormsby `0 <= f1 < f2 < f3 <
   f4 < nyquist_mhz`. Her ihlal, hangi kısıtın ihlal edildiğini ve gerçek
   Nyquist değerini belirten açık bir `ProcessingError` üretir — sessiz bir
   clip veya varsayılan değere düşme YOKTUR.
3. **Yalnızca ardışık geçerli (valid) segmentler işlenir** — dewow ile
   AYNI paylaşılan `contiguous_true_runs()` yardımcısı kullanılır (bkz.
   [[ADR_005_Dewow_Window_and_Edge_Policy]] madde 6). Padding hiçbir zaman
   filtreye girmez ve hiçbir zaman değiştirilmez; `valid_mask` işlem
   öncesi/sonrası birebir aynı kalır.
4. **`sosfiltfilt` için minimum segment uzunluğu açıkça doğrulanır, sessiz
   bir fallback YOKTUR.** Zero-phase Butterworth, `padlen = min(3 ×
   order, segment_length - 1)` gerektirir; segment bu kadar uzun değilse
   (`length <= padlen`) açık bir `ProcessingError` verilir ("segment
   length {length} is too short for zero-phase Butterworth order={order}
   (needs more than {padlen} samples)"). `scipy`'nin kendi
   `sosfiltfilt`'inin fırlattığı bir `ValueError` da yakalanıp aynı açık
   `ProcessingError` biçimine dönüştürülür.
5. **Ormsby'nin dairesel evrişimi (circular convolution) önlemesi için iç
   reflect-doldurma (internal reflect-padding) kullanılır**, boyutu
   segmentin kendi uzunluğuna göre sınırlanır (`min(max(length // 4,
   32), 512, length - 1)`) — ne çok küçük segmentlerde sıfıra inip
   koruma sağlamaz, ne de çok büyük segmentlerde gereksiz şişer. Uygulanan
   iç doldurma miktarı her segment için `diagnostics
   ["internal_padding_samples_per_channel"]`'e kaydedilir.
6. **Sıfır-faz özelliği, hem sentetik hem gerçek veride, iki bağımsız
   metrikle doğrulandı: pik-örnek kayması (peak sample shift) ve medyan-iz
   çapraz-korelasyon gecikmesi (median-trace cross-correlation lag).**
   Tolerans: sıfır-faz varyant için beklenen değer TAM OLARAK 0 (yaklaşık
   değil). Sentetik bir Ricker pulse'ında (merkez örnek 256): zero_phase=
   True → çıktı piki tam örnek 256'da kaldı, medyan-iz gecikmesi = 0;
   zero_phase=False (nedensel/causal) → çıktı piki örnek 261'e kaydı,
   medyan-iz gecikmesi = 9 — bu KASITLI karşıtlık, testin gerçekten ayırt
   edici olduğunu (sadece her zaman sıfır rapor etmediğini) kanıtlar. Aynı
   metodoloji gerçek veride de uygulandı: 4 gerçek band-pass adayının
   (B1-B4) hepsinde medyan-iz çapraz-korelasyon gecikmesi TAM OLARAK 0
   ölçüldü. **Not:** iz-bazlı `peak_sample_shift` değerleri gerçek/gürültülü
   veride 0 etrafında doğal olarak dağılır (örn. 0, 1, -2, 12, -7, 9) —
   bu, gürültü kaynaklı beklenen bir saçılımdır ve gürbüz medyan-iz
   gecikmesinden (ki tam olarak 0'dır) AYRI, bir faz-kayması sorunu olarak
   YANLIŞ yorumlanmamalıdır.
7. **`removed_component := input - output`, padding'de tam sıfır, aynı
   şekil, salt-okunur** — dewow ile aynı sözleşme.
8. **B1-B4 adayları (2 Butterworth + 2 Ormsby), TEK bir dewow adayının
   (D2, `running_mean`, 8ns istenen) çıktısı üzerinde çalıştırıldı — ortak
   bir karşılaştırma tabanı sağlamak içindir, bu D2'yi canonical
   YAPMAZ.** Aynı şekilde C1-C6 kombine adayları kontrollü çiftlerdir
   (C1-C3: dewow penceresi değişken, band-pass sabit B2; C4-C6: band-pass
   değişken, dewow sabit D2) — tam bir 4×4 tarama DEĞİLDİR.

## Alternatives Considered
- **Yalnızca tek geçişli (causal) bir filtre tasarımı:** Reddedildi —
  gerçek bir faz gecikmesi üretir, bu da yansıma zamanlamasını (ve
  dolayısıyla gelecekteki derinlik yorumlamasını) sessizce kaydırabilir.
- **Tek bir filtre yöntemi (yalnızca Butterworth veya yalnızca Ormsby):**
  Reddedildi — görev tanımı açıkça iki bağımsız yöntemin karşılaştırmalı
  QC'sini istiyor (geçiş bandı şekli farkı: Butterworth düzgün/order'a
  bağlı yuvarlak omuzlar, Ormsby keskin doğrusal rampa).
- **Kesim frekanslarını spektral analizden otomatik seçmek (örn. "baskın
  frekans ±X MHz"):** Reddedildi — otomatik parametre seçimi proje kapsamı
  tarafından kesinlikle yasaklanıyor; B1-B4 yalnızca karşılaştırma
  adaylarıdır.
- **Kısa segmentlerde `sosfiltfilt`'in `padlen`'ini sessizce küçültüp
  devam etmek:** Reddedildi — bu, filtrenin kenar davranışını sessizce
  bozar; açık bir hata, insan gözden geçirmesini (segment'i hariç tutma
  veya farklı bir order seçme) zorunlu kılar.

## Consequences
- `contiguous_true_runs()` artık hem dewow hem band-pass tarafından
  paylaşılan, TEK doğrulanmış bir uygulamadır — gelecekteki herhangi bir
  segment-duyarlı zaman-domeni işlemi bunu yeniden kullanmalıdır.
- Sıfır-faz doğrulama metodolojisi (pik-kayması + çapraz-korelasyon
  gecikmesi, hem sıfır-faz hem nedensel varyantla karşıtlık) artık
  projenin faz-duyarlı herhangi bir gelecekteki işlemi için standart
  desendir.
- B1-B4/C1-C6 adaylarının hiçbiri canonical değildir; `outputs/sprint03/
  {bandpass_candidates,combined_candidates}/` yalnızca karşılaştırma
  girdileridir.

## Validation
- 20 sentetik test (`tests/test_bandpass.py`): geçiş-bandı sinüsü
  korunuyor (her iki yöntem), durdurma-bandı sinüsü bastırılıyor (her iki
  yöntem, düşük ve yüksek taraf), zero-phase Butterworth pulse pikini
  korurken causal varyant kaydırıyor (karşıtlık testi), Ormsby yapısı
  gereği sıfır-faz, girdi=çıktı+çıkarılan, padding hesaplamadan hariç/
  değişmeden, valid_mask bağımsız kopya, şekil/dtype, girdi mutasyonu yok,
  geçersiz method/Butterworth parametreleri/Ormsby sıralaması hatası,
  NaN girdi hatası, processing_history kaydı, tekrar-işleme guard'ı +
  override, NPZ round-trip.
- Gerçek dosya entegrasyonu: medyan-iz çapraz-korelasyon gecikmesi = 0
  (Butterworth VE Ormsby), geçiş-bandı enerjisi ortalama >0.8 korundu,
  durdurma-bandı enerjisi azaldı, ana olayın (direct-wave) örnek konumu
  ±5 örnek toleransında korundu.
- Gerçek aday karşılaştırması (`outputs/sprint03/bandpass_candidates/`,
  `combined_candidates/`): B1-B4 ve C1-C6 hepsi çalıştırıldı;
  `bandpass_candidate_metrics.csv`/`combined_candidate_metrics.csv`'de
  `max_abs_median_trace_lag == 0` her aday için doğrulandı (gerçek veride)
  — hiçbir aday canonical işaretlenmedi.

## Related Files
- `src/archaeogpr/processing/bandpass.py`
- `src/archaeogpr/processing/common.py` (`contiguous_true_runs`)
- `src/archaeogpr/qc/bandpass.py`
- `configs/bandpass_candidates.yaml`
- `src/archaeogpr/sprint3_candidates.py`
- [[ADR_005_Dewow_Window_and_Edge_Policy]]
- [[05_PROCESSING/Bandpass_Filter]]
- [[02_SPRINTS/Sprint_03_Dewow_Bandpass]]
