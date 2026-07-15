---
type: processing-module
status: planned
implemented: false
---

# Derinlik Dilimleri (Depth Slices)

## Purpose

Zaman-domenindeki radar hacmini, bir hız modeli kullanarak derinlik-kayıtlı yatay dilimlere dönüştürmek. Bu, herhangi bir GIS/arkeolojik-katman görselleştirmesi için önkoşuldur (prerequisite).

## Input

Migrasyon uygulanmış (veya en azından gain uygulanmış) bir `GPRDataset` ve bir hız modeli ([[Velocity_Analysis]] çıktısı veya dosya metadata'sındaki 0.1 m/ns varsayımı).

## Output

`(depth, channel/x, y)` benzeri bir gride yeniden örneklenmiş, derinlik-eksenli yeni bir veri yapısı (Sprint 1'de kesin dönüş tipi henüz tasarlanmamıştır); her derinlik dilimi seviyesi ve kullanılan hız modeli kaynağı kayıt altına alınır.

## Mathematical Basis

Tek yönlü derinlik dönüşümü: `depth = velocity * time / 2` (gidiş-dönüş zamanının yarısı, çünkü sinyal yüzeyden hedefe gidip geri döner). Bu formülle her örnek indeksi bir derinlik değerine eşlenir; ardından sabit derinlik seviyelerinde (örn. her 0.1 m'de bir) yatay bir kesit almak için zaman ekseni boyunca interpolasyon yapılır. Konumsal (x, y) düzlemde tutarlı bir grid oluşturmak için dilim/kanal geolocation verisi (bkz. [[Data_Model]]) kullanılarak mekansal ızgaralama (spatial gridding/interpolation) da gerekir.

## Parameters

- Derinlik örnekleme aralığı (m).
- Hız modeli kaynağı (metadata sabiti vs [[Velocity_Analysis]] çıktısı; sabit vs derinlikle değişen).
- Mekansal ızgaralama çözünürlüğü ve interpolasyon yöntemi.

## Risks

- Derinlik dönüşümü tamamen hız modeline bağımlıdır; dosyanın metadata hızı (0.1 m/ns) doğrulanmamış bir varsayımdır (bkz. [[OpenGPR_File_Structure]], [[Known_Uncertainties]]) — bu varsayımla üretilen "derinlik" dilimleri gerçek derinlikten sistematik olarak sapabilir.
- CRS riski (bkz. [[OpenGPR_File_Structure]]) ile birleştiğinde, üretilen derinlik dilimlerinin mekansal konumu da güvenilir olmayabilir; herhangi bir GIS çıktısı bu iki belirsizliği birlikte taşır.
- Mekansal ızgaralama, ölçüm noktaları arasında olmayan alanlar için yapay (interpolasyon kaynaklı) sürekliliğe yol açabilir.

## Required QC

Kullanılan hız modelinin ve derinlik varsayımının her çıktıda açıkça belirtilmesi; birkaç derinlik seviyesinde örnek dilim görselleştirmesi; mekansal ızgaralamanın ölçüm noktalarını (gerçek iz konumlarını) da gösteren bir kapsama (coverage) haritası.

## Acceptance Criteria

İleride implemente edildiğinde: (1) girdi mutasyona uğramamalı, (2) her çıktı diliminde kullanılan hız modeli kaynağı ve derinlik varsayımı açıkça belirtilmeli, (3) CRS'in doğrulanmadığı uyarısı her mekansal çıktıda tekrarlanmalı, (4) fonksiyon açık bir hız modeli parametresi gerektirmeli (CLAUDE.md: "Depth conversion requires an explicit propagation velocity").

## Implementation Status

Bu modül Sprint 1'de **implemente edilmemiştir**. Hiçbir kod veya placeholder implementasyon mevcut değildir.

## Related Modules

[[Processing_Index]], [[Processing_Order]], [[Migration]], [[Velocity_Analysis]]
