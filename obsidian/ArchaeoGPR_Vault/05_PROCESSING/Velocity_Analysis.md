---
type: processing-module
status: planned
implemented: false
---

# Hız Analizi (Velocity Analysis)

## Purpose

Yer altı elektromanyetik dalga yayılım hızını (propagation velocity), dosyanın metadata'sındaki doğrulanmamış varsayımına (şu an 0.1 m/ns, bkz. [[OpenGPR_File_Structure]]) bir alternatif veya iyileştirme olarak tahmin etmek.

## Input

İşlenmiş (gain uygulanmış) bir `GPRDataset`; tercihen izole nokta-yansıtıcı (point reflector) difraksiyon hiperbolleri içeren bir B-scan.

## Output

Bir hız modeli (sabit tek değer veya derinlikle değişen bir profil); bu modelin kendisi `GPRDataset`'in amplitüdlerini değiştirmez, ancak `processing_history`'ye bir kayıt olarak eklenir ve [[Migration]] ile [[Depth_Slices]] adımlarına girdi olarak aktarılması planlanır.

## Mathematical Basis

Standart yaklaşım, difraksiyon hiperbolü eğrisine ("hyperbola fitting") en küçük kareler ile uydurma yapmaktır:

`t(x) = sqrt(t0^2 + (2x/v)^2)`

Burada `t0` hiperbol tepe noktasının (apex) iki-yönlü zamanı, `x` tepe noktasından yatay uzaklık, `v` aranan yayılım hızıdır. Kullanıcı (veya gelecekte otomatik bir algoritma) hiperbol üzerindeki noktaları işaretler (pick), ve `v` bu noktalara en iyi uyan eğri ile kestirilir.

## Parameters

- İşaretlenen (picked) hiperbol noktaları veya otomatik tespit eşiği.
- Başlangıç hız tahmini (optimizasyon için).
- Sabit-hız (tek katman) vs derinlikle değişen hız modeli seçimi.

## Risks

- Elle işaretleme öznel (subjective) hata payı taşır; farklı kullanıcılar farklı `v` değerleri bulabilir.
- Yöntem, görünür ve net bir difraksiyon hiperbolü gerektirir; katmanlı veya karmaşık bir alt yüzeyde her zaman uygun hiperbol bulunamayabilir.
- Tek bir sabit hız varsayımı, gerçekte derinlikle değişen (katmanlı) bir ortamda sistematik hataya yol açar.
- Bu veri setinde tekrarlı/çok-ofsetli (multi-offset/CMP) ölçüm yoksa, hız analizi tek kanallı hiperbol uydurmayla sınırlı kalır; bu bir metodolojik kısıtlamadır ve sonuçların kesinliği buna göre değerlendirilmelidir.

## Required QC

İşaretlenen hiperbol noktaları ile uydurulan eğrinin B-scan üzerine bindirilmiş hâli; uydurma artıklarının (residuals) grafiği; tahmin edilen hızın dosya metadata'sındaki 0.1 m/ns değeriyle karşılaştırılması.

## Acceptance Criteria

İleride implemente edildiğinde: (1) girdi mutasyona uğramamalı, (2) tahmin edilen hız ve kullanılan yöntem/noktalar kayıt altına alınmalı, (3) sentetik olarak bilinen bir hızla üretilmiş bir hiperbol test verisinde kabul edilebilir bir tolerans içinde doğru hız tahmin edilmeli, (4) sonuç dosya metadata hızının yerine geçmeden, ayrı ve açıkça etiketlenmiş bir alternatif olarak saklanmalı.

## Implementation Status

Bu modül Sprint 1'de **implemente edilmemiştir**. Hiçbir kod veya placeholder implementasyon mevcut değildir.

## Related Modules

[[Processing_Index]], [[Processing_Order]], [[Gain]], [[Migration]], [[Depth_Slices]]
