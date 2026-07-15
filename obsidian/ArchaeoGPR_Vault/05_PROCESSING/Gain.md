---
type: processing-module
status: planned
implemented: false
---

# Kazanç (Gain)

## Purpose

Sinyalin derinlik/zamanla birlikte küresel yayılım (spherical spreading) ve soğurma (absorption) nedeniyle azalmasını telafi etmek amacıyla amplitüd kazancı uygulamak.

## Input

Dewow/arka plan çıkarma (ve varsa opsiyonel F-K filtreleme) uygulanmış bir `GPRDataset`.

## Output

Zaman/derinlikle ölçeklenmiş amplitüdlere sahip **yeni** bir `GPRDataset`; uygulanan kazanç fonksiyonu ve parametreleri `processing_history`'ye kaydedilir.

## Mathematical Basis

Yaygın kazanç fonksiyonları: (1) doğrusal kazanç `amplitude(t) *= (1 + k*t)`, (2) üstel kazanç `amplitude(t) *= exp(a*t)`, (3) Otomatik Kazanç Kontrolü (AGC) — kayan bir pencere içindeki ortalama/RMS genliğe göre normalize eden adaptif bir kazanç. AGC, göreli genlik ilişkilerini bozduğu için niceliksel (quantitative) bir amplitüd ölçüsü değildir.

## Parameters

- Kazanç fonksiyonu tipi (doğrusal / üstel / AGC).
- Başlangıç zamanı, kazanç oranı/katsayısı (doğrusal ve üstel için).
- AGC pencere uzunluğu (ns veya örnek sayısı olarak).

## Risks

- **Sıralama kısıtı (zorunlu):** Kazanç, dewow ve arka plan çıkarma gibi filtrelerden **önce asla** uygulanmamalıdır — kazanç, henüz giderilmemiş düşük-frekans sürüklenmesini veya sistem çınlamasını da güçlendirerek büyütür. Planlanan sırada kazanç bu iki adımdan sonra gelir (bkz. [[Processing_Order]]).
- **AGC çıktısı hiçbir zaman niceliksel amplitüd analizinde kullanılmamalıdır** (CLAUDE.md: "AGC products must never be used for quantitative amplitude analysis") — AGC, göreli genlik bilgisini yok eder.
- Yanlış kazanç parametreleri, gürültüyü gerçek sinyalden daha fazla büyütebilir.

## Required QC

Kazanç öncesi/sonrası genlik-zaman grafiği (özellikle derin örneklerde); uygulanan kazanç eğrisinin (gain curve) kendisi ayrı olarak çizilmeli; AGC kullanılıyorsa çıktının "niceliksel değildir" uyarısıyla etiketlenmesi.

## Acceptance Criteria

İleride implemente edildiğinde: (1) girdi mutasyona uğramamalı, (2) kazanç fonksiyonu/parametreleri kayıt altına alınmalı, (3) AGC çıktısı açıkça işaretlenmeli (metadata/uyarı ile), (4) fonksiyon dewow ve arka plan çıkarmadan önce çağrılmaya karşı en azından belgesel olarak uyarmalı, (5) fonksiyon opsiyonel olmalı.

## Implementation Status

Bu modül Sprint 1'de **implemente edilmemiştir**. Hiçbir kod veya placeholder implementasyon mevcut değildir.

## Related Modules

[[Processing_Index]], [[Processing_Order]], [[Background_Removal]], [[FK_Filter]], [[Velocity_Analysis]]
