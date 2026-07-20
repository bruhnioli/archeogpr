---
type: project-state
tags: [project-state, sprint]
---

# Next Development Sprint — Sprint 4B / Gain (henüz tanımlanmadı)

> **Not (2026-07-19 güncellemesi):** Bu belge yalnızca **Sprint 4B (Gain)**
> track'ini kapsar; aşağıdaki içerik GUI sprintleriyle **değiştirilmedi**.
> Ayrı, paralel bir GUI/3D dönüşüm track'i altı sprint ilerledi:
> **Sprint GUI-0** (tasarım/ADR, kod yok), **Sprint GUI-1** (native
> PySide6 viewer + Windows executable), **Sprint GUI-2** (display
> controls, `0.2.0`) — üçü `main`'e merge edildi (2026-07-18, PR #2).
> **Sprint GUI-1B** (background file-loading worker, `0.2.1`) — `main`'e
> merge edildi (2026-07-18, PR #3). **Sprint GUI-3A** (non-destructive
> processing preview & apply — 5 stabil processing fonksiyonu, `0.3.0`) —
> `main`'e merge edildi (2026-07-19, PR #4, merge commit `f3e516c`).
> **Sprint 3D-0** (survey geometry inspector + C-scan/3D readiness
> raporlama — volume render YOK, `0.4.0`) — `main`'e merge edildi
> (2026-07-20, PR #5, merge commit `a43d947`). **Sprint 3D-1** (actual
> X/Y point-grid C-scan/time-slice viewer — Qt-free `archaeogpr.cscan`
> paketi, gridding/PyVista/volume render YOK, `0.5.0`) — implementasyon +
> testler tamam, dokümantasyon/quality gate/build sürüyor, henüz
> commit/merge edilmedi. Bkz.
> [[02_SPRINTS/Sprint_GUI_0_Foundation]],
> [[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]],
> [[02_SPRINTS/Sprint_GUI_2_Display_Controls]],
> [[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]],
> [[02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply]],
> [[02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector]],
> [[02_SPRINTS/Sprint_3D_1_Actual_XY_Point_Grid_CScan]],
> [[06_DECISIONS/ADR_011_GUI_Technology_Decision]],
> [[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]],
> [[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]],
> [[06_DECISIONS/ADR_017_Actual_XY_CScan_and_No_Interpolation_Policy]]. Bu
> iki track birbirinden bağımsızdır: GUI track'inin ilerlemesi Sprint
> 4B'yi BAŞLATMAZ, Sprint 4B'nin tanımsız kalması da bir sonraki GUI
> sprintini (gridding/volume render, undo/redo, recipe) engellemez —
> ikisi de yalnızca kullanıcının kendi, ayrı açık isteğiyle başlar.

## Durum: Sprint 4A done (canonical policy = A0); sıradaki adım hâlâ bir SPRINT DEĞİL, kullanıcının kendi açık isteği

Sprint 4A ([[02_SPRINTS/Sprint_04A_Background_Removal]]) dört
background-removal yöntemini (global_mean, global_median, sliding_mean,
sliding_median) implemente etti ve 8 aday (A1-A8) canonical Sprint 3
çıktısı (D2+B1, bkz. [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]])
üzerinde gerçek veride çalıştırdı. Sinyal-koruma ve removed-component
metrikleri her aday/kanal/zaman-penceresi için hesaplandı; 5 synthetic
bilimsel-risk deneyi (window-length vs target-length, global-vs-sliding
uzun-olay, mean-vs-median outlier, edge testleri) çalıştırıldı. **Hiçbir
aday otomatik olarak canonical seçilmedi** — bkz.
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
`outputs/sprint04a/`.

**Sprint 4A.1 düzeltmesi (2026-07-16):** karar QC'sindeki üç kusur
(pencere terminolojisi, bağımsız-ölçekli B-scan'ler, `1 - coherence`
"preservation" çerçevesi) düzeltildi ve YENİ bir paired-control sentetik
hedef-retention deneyi eklendi — bu deney, RMS-bazlı "preservation-
favoring" etiketinin (A1/A2) gerçekte uzun sentetik hedefleri neredeyse
tamamen yok ettiğini (`paired_control_long_target_retention` ≈
0.00007-0.01) ortaya çıkardı. Bkz.
[[02_SPRINTS/Sprint_04A_Background_Removal]] "Sprint 4A.1" bölümü.

**Sprint 4A.2 düzeltmesi (2026-07-16, aynı PR #1):** Sprint 4A.1'in KENDİ
`localized_hyperbola` sentetik senaryosunun pratikte düz bir olay olduğu
bulundu ve düzeltildi (gerçek eğrilik + mask-tabanlı apex/arm retention +
yeni `PAIRED_CONTROL_HYPERBOLA_VALIDATION.png`); karar katmanına **A0**
("hiç background removal yapmama") sabit-değerli bir referans politikası
olarak eklendi — nihai karar tablosunda, metrics summary panelinde ve
`candidate_metrics.csv`'de. Bkz.
[[02_SPRINTS/Sprint_04A_Background_Removal]] "Sprint 4A.2" bölümü.

**Human decision (2026-07-16): canonical background-removal policy = A0
(no_background_removal).** A1-A8'den hiçbiri canonical seçilmedi;
canonical Sprint 3 (D2+B1) çıktısına background removal uygulanmayacak;
canonical işlem zinciri değişmeden kalıyor; yeni bir canonical NPZ
üretilmedi; A0 için `ProcessingResult`/`removed_component`/NPZ
üretilmedi; A1-A8 repository'de deneysel/opt-in araçlar olarak kaldı
(silinmedi). Karar gerekçesi, tüm sayısal kanıt ve alternatiflerin
değerlendirmesi:
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]].
[[01_PROJECT_STATE/03_Open_Issues]] ISSUE-012 bu kararla **kapatıldı**.

Bu kararın kendisi, tek başına, bir sonraki sprinti (Gain veya başka bir
işlem) BAŞLATMAZ — bu proje hiçbir sprintte kendi kendine bir sonraki
sprinte geçmez. **Sprint 4B (Gain veya başka bir kapsam) henüz
TANIMLANMADI ve kullanıcının kendi açık isteği olmadan
BAŞLATILMAYACAK.**

Detay: [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]],
`outputs/sprint04a/BACKGROUND_OUTPUT_COMPARISON_CH00_CH05_CH10.png`,
`outputs/sprint04a/BACKGROUND_REMOVED_COMPARISON_CH00_CH05_CH10.png`,
`outputs/sprint04a/BACKGROUND_METRICS_SUMMARY.png`,
`outputs/sprint04a/BACKGROUND_FINAL_DECISION_REQUIRED.md`,
`outputs/sprint04a/background_candidates/comparison/
PAIRED_CONTROL_HYPERBOLA_VALIDATION.png`,
`outputs/sprint04a/background_candidates/comparison/
paired_control_target_attenuation.csv`,
`outputs/sprint04a/background_candidates/comparison/candidate_metrics.csv`
(A0 satırı dahil),
`outputs/sprint04a/background_candidates/comparison/BACKGROUND_REVIEW_REQUIRED.md`,
[[02_SPRINTS/Sprint_04A_Background_Removal]]. `BACKGROUND_DECISION_
PANEL.png`/`_DETAIL.png` tarihsel uyumluluk için korunuyor ama asıl karar
dosyaları DEĞİL.

Canonical processing chain (`Swath003_Array02.ogpr`, değişmedi):
`time_zero_correction → dc_offset_correction → dewow_correction (D2) →
bandpass_correction (B1)`. Background removal: **disabled / not
applied**.

---

## Sprint 4B için olası kapsam (yalnızca bir taslak — henüz onaylanmadı)

Background-removal kararı artık kapandığına göre (canonical policy = A0,
bkz. Sprint 4A yukarıda), olası bir Sprint 4B şu adımlardan birini/
birkaçını kapsayabilir (kesinleşmiş DEĞİL, yalnızca
[[05_PROCESSING/Processing_Order]]'daki planlanan sırayı yansıtan bir
taslak): Gain — canonical Sprint 3 (D2+B1, background-removal-siz) çıktı
üzerinde. Bu liste bir taahhüt değildir; Sprint 4B'nin kesin kapsamı
yalnızca kullanıcının açık isteğiyle netleşecektir.

## Kesinlikle yapılmayacaklar (bir sonraki adım için)
- A0 kararını (veya A1-A8'den herhangi birini) daha sonra sessizce
  değiştirmek — bu karar yalnızca kullanıcının kendi yeni, açık isteğiyle
  değişebilir (bkz.
  [[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]]).
- Kullanıcının kendi açık isteği olmadan bir sonraki sprinti (Gain veya
  başka bir kapsam) başlatmak.
- "Canonical policy = A0" kararını Gain'i otomatik olarak başlatma
  gerekçesi olarak kullanmak.
- D2/B1'in veya herhangi bir background-removal adayının
  `Swath003_Array02.ogpr` dışındaki bir veri setine otomatik olarak
  (kendi aday karşılaştırması/insan incelemesi olmadan) uygulanması.
- Bu veri setindeki tüm 8 adayın removed component'inin yüksek mekânsal
  koherans göstermesini (0.83-1.0) otomatik olarak "bu veri setinde
  gerçek uzun bir yansıma yok" şeklinde yorumlamak — bu yalnızca bir risk
  göstergesidir, bir sonuç değildir (bkz.
  [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]]).
- `overall_rms_retention_tendency`'nin yüksek olmasını arkeolojik-hedef
  koruması ile eşdeğer saymak — Sprint 4A.1'in paired-control deneyi bu
  veri setinde tam tersini gösterdi (A1/A2 yüksek RMS retention ama
  paired-control uzun-hedef retention ≈ 0).
- A1-A8'i (artık deneysel/opt-in araçlar) repository'den silmek — bu
  karar onları kaldırmıyor, sadece canonical seçmiyor.
- Herhangi bir anomali/arkeolojik yorum yapmak.

## İlgili notlar
[[02_SPRINTS/Sprint_Index]], [[02_SPRINTS/Sprint_04A_Background_Removal]],
[[02_SPRINTS/Sprint_03_Dewow_Bandpass]],
[[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]],
[[01_PROJECT_STATE/04_Risks_and_Limitations]],
[[01_PROJECT_STATE/03_Open_Issues]], [[05_PROCESSING/Background_Removal]],
[[05_PROCESSING/Gain]], [[05_PROCESSING/Processing_Order]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]]

Ayrı, paralel GUI/3D track'i için: [[02_SPRINTS/Sprint_GUI_0_Foundation]],
[[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]],
[[02_SPRINTS/Sprint_GUI_2_Display_Controls]],
[[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]],
[[02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply]],
[[02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector]],
[[02_SPRINTS/Sprint_3D_1_Actual_XY_Point_Grid_CScan]],
[[06_DECISIONS/ADR_011_GUI_Technology_Decision]],
[[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]],
[[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]],
[[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]],
[[06_DECISIONS/ADR_017_Actual_XY_CScan_and_No_Interpolation_Policy]],
[[01_PROJECT_STATE/06_GUI_3D_Risk_Register]].
