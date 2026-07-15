---
type: processing-module-index
---

# Processing Index

## Amaç

Bu not, `archaeogpr` için tüm sinyal işleme modüllerinin tek girişli
indeksidir. Sprint 3 itibarıyla **dört modül implemente edildi**
(Time-Zero, DC Offset, Dewow, Band-pass Filter); geri kalan altısı hâlâ
planlanmış durumdadır — bkz. her modülün kendi "Implementation Status"
bölümü ve genel bakış için [[Processing_Pipeline_Architecture]].

## Modül Listesi

| Modül | Tek Satır Amaç | Durum |
|---|---|---|
| [[Time_Zero_Correction]] | Seçilen olayı (örn. doğrudan dalga) hedef bir örneğe hizalamak | **implemented** (Sprint 2) |
| [[DC_Offset]] | Her izdeki sabit amplitüd yanlılığını (DC bileşeni) gidermek | **implemented** (Sprint 2) |
| [[Dewow]] | Çok-düşük-frekanslı "wow" sürüklenmesini gidermek | **implemented** (Sprint 3) — canonical: D2 (bkz. ADR-007) |
| [[Bandpass_Filter]] | Nominal frekans bandı dışındaki gürültüyü reddetmek | **implemented** (Sprint 3) — canonical: B1 (bkz. ADR-007) |
| [[Background_Removal]] | Tüm izlerde ortak yatay bantlanma/çınlamayı çıkarmak | planned |
| [[Gain]] | Derinlik/zamanla azalan sinyali amplitüd kazancıyla telafi etmek | planned |
| [[FK_Filter]] | Eğik gürültü/artefaktları f-k domeninde filtrelemek (varsayılan kapalı) | planned |
| [[Velocity_Analysis]] | Yer altı yayılım hızını hiperbol uydurma ile tahmin etmek | planned |
| [[Migration]] | Difraksiyon hiperbollerini gerçek konumlarına toplamak | planned |
| [[Depth_Slices]] | Zaman-domeni hacmini derinlik-kayıtlı yatay dilimlere çevirmek | planned |

Kalan 6 modül için ortak durum: **`status: planned`, `implemented: false`**.
Hiçbiri için placeholder veya sahte-çalışan kod yoktur. Time-Zero ve DC
Offset'in gerçek implementasyonu: [[02_SPRINTS/Sprint_02_TimeZero_DCOffset]],
[[06_DECISIONS/ADR_002_TimeZero_Reference_and_Shift_Policy]]. Dewow ve
Band-pass Filter'ın gerçek implementasyonu ve canonical aday seçimi (D2 +
B1, insan/jeofizik kararı): [[02_SPRINTS/Sprint_03_Dewow_Bandpass]],
[[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]],
[[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]].

## Planlanan Çalıştırma Sırası

Modüllerin planlanan çalıştırma sırası (bağımlılıklar dahil) [[Processing_Order]] notunda tam olarak belgelenmiştir.

## Şablon

Yeni bir işleme modülü notu oluşturulacaksa [[Template_Processing_Module]] şablonunu temel alın.

## İlgili Notlar

- [[Processing_Order]] — planlanan çalıştırma sırası ve sıralama kısıtları.
- [[Processing_Pipeline_Architecture]] — `GPRDataset -> GPRDataset` sözleşmesinin mimari açıklaması.
