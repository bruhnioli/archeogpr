---
type: processing-module
status: planned
implemented: false
---

# Arka Plan Çıkarma (Background Removal)

## Purpose

Tüm izlerde ortak olan yatay bantlanma/çınlamayı (örn. sistem/anten kaynaklı ringing) gidermek amacıyla, bir kanal için tüm dilimler (slices) üzerinden hesaplanan ortalama izi her izden çıkarmak.

## Input

Band-geçiren filtre uygulanmış bir `GPRDataset`.

## Output

Kanal-bazlı ortalama iz çıkarılmış **yeni** bir `GPRDataset`; hesaplanan ortalama iz(ler) ve pencereleme parametreleri `processing_history`'ye kaydedilir.

## Mathematical Basis

Bir kanal `c` için, her örnek indeksi `s`'de tüm dilimler üzerinden ortalama: `background[c, s] = mean over slices of amplitudes[:, c, s]`. Bu, her izden çıkarılır: `amplitudes_corrected[slice, c, s] = amplitudes[slice, c, s] - background[c, s]`. Ortalama, tüm profil üzerinden (global) veya kayan bir pencere (sliding window) üzerinden hesaplanabilir.

## Parameters

- Ortalama hesaplama penceresi (global vs kayan pencere uzunluğu, dilim sayısı olarak).
- Kanal-bazlı mı yoksa tüm kanallar için tek bir ortalama mı kullanılacağı.

## Risks

- **Açık risk (CLAUDE.md ile uyumlu):** Bu işlem, tüm profil boyunca yatay olarak uzanan gerçek arkeolojik hedefleri (örn. düz-yatan bir taban/döşeme kalıntısı) "arka plan" olarak yanlış tanıyıp bastırabilir. Yatay süreklilik gösteren gerçek sinyal ile gerçek arka plan gürültüsü, bu yöntemle ayırt edilemez.
- Kayan pencere çok kısaysa gerçek dikey/eğik yapılar da etkilenebilir; çok uzunsa etkisiz kalır.

## Required QC

Çıkarılan ortalama izin (background trace) kendisi ayrıca görselleştirilmeli; düzeltme öncesi/sonrası B-scan karşılaştırması; özellikle yatay/düz hedeflerin bastırılıp bastırılmadığını değerlendirmek için fark görüntüsü (difference image) sağlanmalı.

## Acceptance Criteria

İleride implemente edildiğinde: (1) girdi mutasyona uğramamalı, (2) çıkarılan arka plan bileşeni QC için erişilebilir olmalı, (3) belgelerde yatay hedef bastırma riski kullanıcıya açıkça hatırlatılmalı (örn. çalışma zamanı uyarısı), (4) fonksiyon opsiyonel olmalı.

## Implementation Status

Bu modül Sprint 1'de **implemente edilmemiştir**. Hiçbir kod veya placeholder implementasyon mevcut değildir.

## Related Modules

[[Processing_Index]], [[Processing_Order]], [[Bandpass_Filter]], [[FK_Filter]], [[Gain]]
