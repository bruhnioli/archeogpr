---
type: processing-module
status: planned
implemented: false
---

# F-K Filtreleme (F-K Filter)

## Purpose

Eğik (dipping) gürültü/artefaktları (örn. hava dalgası, çınlama, çok-yollu yansımalar) iki boyutlu frekans-dalgasayısı (frequency-wavenumber, f-k) domeninde filtrelemek.

## Input

Arka plan çıkarma uygulanmış bir `GPRDataset` (opsiyonel bir adım olarak).

## Output

Belirli görünür hız/eğim bantları bastırılmış **yeni** bir `GPRDataset`; kullanılan maske/parametreler `processing_history`'ye kaydedilir.

## Mathematical Basis

Bir kanalın (dilim, örnek) yani (x, t) verisi üzerinde 2 boyutlu FFT alınarak (dilim-ekseni ve zaman-ekseni birlikte) (k, f) domenine geçilir. Burada belirli görünür hız/eğim doğrularına karşılık gelen enerji bir maske ile bastırılır veya geçirilir; ardından 2B ters FFT ile zaman domenine dönülür.

## Parameters

- Reddedilecek/geçirilecek görünür hız veya eğim aralığı.
- Maske şekli (örn. yamuk/kama şekilli fan filtresi) ve kenar yumuşatma (taper).

## Risks

- **Asla varsayılan olarak etkin olmamalıdır (CLAUDE.md: "F-K filtering must never be enabled by default")** — gerçek eğik yansıtıcıları (örn. eğimli bir arkeolojik yapı veya hendek duvarı) gürültüyle aynı görünür hız bandında olabilir ve yanlışlıkla kaldırılabilir.
- Maske sınırlarının yanlış seçimi, gerçek sinyalin bir kısmını sessizce siler; bu genellikle B-scan üzerinde fark edilmesi en zor bozulmalardan biridir.

## Required QC

Filtreleme öncesi/sonrası f-k spektrumunun (2B genlik spektrumu) görselleştirilmesi; kaldırılan enerjinin zaman-domenindeki karşılığının (fark B-scan'i) ayrıca gösterilmesi; bu filtrenin etkin olduğu her çalıştırmada açık bir uyarı.

## Acceptance Criteria

İleride implemente edildiğinde: (1) girdi mutasyona uğramamalı, (2) filtre varsayılan olarak kapalı (disabled) gelmeli ve açıkça etkinleştirilmesi gerekmeli, (3) etkinleştirildiğinde bunun `processing_history`'de ve çalışma zamanı uyarısında görünmesi gerekli, (4) kaldırılan bileşen QC için erişilebilir olmalı.

## Implementation Status

Bu modül Sprint 1'de **implemente edilmemiştir**. Hiçbir kod veya placeholder implementasyon mevcut değildir.

## Related Modules

[[Processing_Index]], [[Processing_Order]], [[Background_Removal]], [[Gain]]
