---
type: processing-module
---

# Processing Order

## Amaç

Bu not, sinyal işleme adımlarının **hedeflenen çalıştırma sırasını** tam olarak belgeler. Sprint 3 itibarıyla bu sıranın ilk dört adımı (Time-zero, DC offset, Dewow, Band-pass) gerçek kodla implemente edilmiştir (bkz. [[Processing_Index]]); kalan adımlar için bu not, gelecekteki bir uygulamanın uyması gereken sırayı ve sıralamayla ilgili zorunlu kısıtları kayıt altına alır.

## Planlanan Sıra

```
Data QC → Time-zero correction → DC offset → Dewow → Band-pass → Background removal
   → Optional F-K → Gain → Velocity analysis → Migration → Envelope → Time/depth slices
```

Adım adım, vault'ta karşılık gelen not ile:

1. **Data QC** — Sprint 1'de zaten implemente edilmiş metadata/QC türetimi (bu bir "processing" modülü değildir; bkz. [[Architecture_Overview]]).
2. [[Time_Zero_Correction]] — zaman-sıfırı düzeltmesi. **implemented** (Sprint 2).
3. [[DC_Offset]] — DC ofset giderimi. **implemented** (Sprint 2).
4. [[Dewow]] — düşük frekanslı sürüklenme giderimi. **implemented** (Sprint 3) — canonical pencere henüz seçilmedi, bkz. [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-010.
5. [[Bandpass_Filter]] — band-geçiren filtre. **implemented** (Sprint 3) — canonical aralık henüz seçilmedi, bkz. [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-011.
6. [[Background_Removal]] — arka plan çıkarma.
7. **Optional F-K** — [[FK_Filter]]; adından da anlaşılacağı gibi bu adım isteğe bağlıdır ve akışın normal bir parçası değildir.
8. [[Gain]] — amplitüd kazancı.
9. [[Velocity_Analysis]] — hız analizi.
10. [[Migration]] — migrasyon.
11. **Envelope** — Hilbert zarfı (envelope) çıkarımı; Sprint 1 kapsamında bu adım için ayrı bir vault notu henüz oluşturulmamıştır ve README.md'de "implemente edilmemiş" olarak listelenir.
12. [[Depth_Slices]] — zaman/derinlik dilimleri.

## Zorunlu Sıralama Kısıtları

- **Kazanç (Gain) hiçbir zaman diğer filtrelerden önce uygulanmamalıdır.** Dewow, band-pass ve arka plan çıkarma gibi adımlar kazançtan **önce** gelmelidir; aksi hâlde kazanç, henüz giderilmemiş düşük-frekans sürüklenmesini veya sistem çınlamasını da büyütür. Ayrıntı için [[Gain]].
- **F-K filtreleme hiçbir zaman varsayılan olarak etkinleştirilmemelidir.** Bu adım sıradaki konumunda "Optional" olarak işaretlenmiştir ve yalnızca kullanıcı açıkça talep ettiğinde çalıştırılmalıdır. Ayrıntı için [[FK_Filter]].
- Migrasyon ([[Migration]]) ve derinlik dilimleri ([[Depth_Slices]]), açık bir yayılım hızı modeli gerektirir (bkz. [[Velocity_Analysis]]); CLAUDE.md kuralı: "Depth conversion requires an explicit propagation velocity."

## İlgili Notlar

- [[Processing_Index]] — tüm modüllerin indeksi.
- [[Time_Zero_Correction]], [[DC_Offset]], [[Dewow]], [[Bandpass_Filter]], [[Background_Removal]], [[FK_Filter]], [[Gain]], [[Velocity_Analysis]], [[Migration]], [[Depth_Slices]] — sıradaki her modülün kendi notu.
