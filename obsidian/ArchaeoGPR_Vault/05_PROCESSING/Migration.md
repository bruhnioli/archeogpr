---
type: processing-module
status: planned
implemented: false
---

# Migrasyon (Migration)

## Purpose

Difraksiyon hiperbollerini gerçek yer altı nokta/yapı konumlarına geri toplamak (collapse). Bu, izole yansıtıcıların (örn. bir taş, boru veya küçük bir arkeolojik nesne) B-scan üzerinde göründüğü yayılmış hiperbol şeklini, gerçek konumlarını temsil eden kompakt bir noktaya/şekle dönüştürür.

## Input

Gain uygulanmış bir `GPRDataset` ve [[Velocity_Analysis]]'ten elde edilen bir hız modeli.

## Output

Difraksiyon hiperbolleri toplanmış (migrated) **yeni** bir `GPRDataset`; kullanılan hız modeli ve migrasyon algoritması `processing_history`'ye kaydedilir.

## Mathematical Basis

Yaygın algoritmalardan biri Kirchhoff migrasyonudur: her çıktı (x, z) noktası için, o noktadan kaynaklanmış olabilecek difraksiyon hiperbolü boyunca giriş verisindeki enerji toplanır (summation), böylece gerçek kaynak noktasında yapıcı girişim (constructive interference), diğer yerlerde yıkıcı girişim (destructive interference) oluşur. Daha basit "hiperbol toplama" yaklaşımları da aynı ilkeye dayanır; ikisi de doğrudan bir hız modeline bağımlıdır.

## Parameters

- Hız modeli kaynağı (dosya metadata'sındaki sabit 0.1 m/ns varsayımı vs [[Velocity_Analysis]] çıktısı).
- Migrasyon algoritması seçimi (örn. Kirchhoff, faz-kaydırma tabanlı yöntemler).
- Toplama açıklığı (aperture) — yanal olarak ne kadar geniş bir alanın toplama işlemine dahil edileceği.

## Risks

- Yanlış/hatalı bir hız modeli, yapıları gerçek konumlarından kaydırır veya bulanıklaştırır (smear) — migrasyon çıktısının doğruluğu tamamen [[Velocity_Analysis]] adımının kalitesine bağımlıdır.
- Profilin kenarlarında (aperture sınırlarında) yapay kenar artefaktları oluşabilir.
- Migrasyon, gürültüyü de tutarlı görünen sahte yapılara dönüştürebilir; bu nedenle migrasyon sonrası hiçbir anomali otomatik olarak arkeolojik bir nesne olarak yorumlanmamalıdır (CLAUDE.md: "Do not automatically interpret anomalies as archaeological objects").

## Required QC

Migrasyon öncesi/sonrası B-scan karşılaştırması; bilinen/sentetik bir hiperbol test verisinde toplama kalitesinin görsel ve sayısal değerlendirmesi; kullanılan hız modelinin ve kaynağının (metadata vs Velocity Analysis) açıkça belirtilmesi.

## Acceptance Criteria

İleride implemente edildiğinde: (1) girdi mutasyona uğramamalı, (2) kullanılan hız modeli kaynağı ve algoritma kayıt altına alınmalı, (3) sentetik hiperbol test verisinde toplamanın beklenen konumda gerçekleştiği doğrulanmalı, (4) çıktı hiçbir otomatik "arkeolojik nesne" etiketlemesi içermemeli.

## Implementation Status

Bu modül Sprint 1'de **implemente edilmemiştir**. Hiçbir kod veya placeholder implementasyon mevcut değildir.

## Related Modules

[[Processing_Index]], [[Processing_Order]], [[Velocity_Analysis]], [[Depth_Slices]]
