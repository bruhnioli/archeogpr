---
type: project-state
tags: [project-state]
---

# Project Roadmap

Aşağıdaki fazlar projenin genel yol haritasıdır. **Faz 1 ve Faz 2
tamamlandı.** Diğer tüm fazlar planlanmıştır ve henüz uygulanmamıştır —
hiçbiri için kod veya sahte/yarım implementasyon yoktur.

| Faz | Açıklama | Durum |
|---|---|---|
| 1 | OpenGPR veri altyapısı | ✅ Tamamlandı (Sprint 1) |
| 2 | Time-zero ve DC offset | ✅ Tamamlandı (Sprint 2, bkz. [[02_SPRINTS/Sprint_02_TimeZero_DCOffset]]) |
| 3 | Dewow ve band-pass | ⏳ Planlandı (önerilen Sprint 3, bkz. [[01_PROJECT_STATE/02_Next_Development_Sprint]]) |
| 4 | Background removal ve gain | ⏳ Planlandı |
| 5 | F-K deneysel modülü | ⏳ Planlandı (varsayılan olarak kapalı olacak) |
| 6 | Hız analizi ve migration | ⏳ Planlandı |
| 7 | Time/depth-slice üretimi | ⏳ Planlandı |
| 8 | QGIS ve Blender export | ⏳ Planlandı |
| 9 | Kullanıcı arayüzü (GUI) | ⏳ Planlandı |
| 10 | Arkeolojik karar destek çıktıları | ⏳ Planlandı |

## Faz 1 — OpenGPR veri altyapısı (tamamlandı)
`.ogpr` okuyucu, `GPRDataset` veri modeli, metadata/QC türetme, temel
görselleştirme ve export, CLI, test suite. Detay: [[02_SPRINTS/Sprint_01_OpenGPR_Infrastructure]].

## Faz 2 — Time-zero ve DC offset (tamamlandı)
`correct_time_zero()` (manual/channel_median_peak/channel_median_cross_correlation)
ve `correct_dc_offset()` (mean/median), QC çıktıları, sentetik + gerçek
dosya testleri. Detay: [[02_SPRINTS/Sprint_02_TimeZero_DCOffset]],
[[05_PROCESSING/Time_Zero_Correction]], [[05_PROCESSING/DC_Offset]].

## Faz 3–10 (planlandı)
Sırasıyla dewow/band-pass, background removal/gain, F-K, hız analizi/migration,
time-depth slice, GIS/Blender export, GUI ve arkeolojik karar destek
çıktıları. Her biri kendi sprint'inde ayrıca kapsamı netleştirilene kadar
başlatılmaz (bkz. `CLAUDE.md`: "Do not implement processing algorithms
until their sprint is explicitly requested."). İşlem modülleri için
mühendislik bağlamı: [[05_PROCESSING/Processing_Index]].

## İlgili notlar
[[05_PROCESSING/Processing_Order]], [[01_PROJECT_STATE/01_Current_Project_State]]
