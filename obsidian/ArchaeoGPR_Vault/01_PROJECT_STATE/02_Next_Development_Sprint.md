---
type: project-state
tags: [project-state, sprint]
---

# Next Development Sprint — Sprint 4B / Gain (henüz tanımlanmadı)

## Durum: Sprint 4A review_required; sıradaki adım hâlâ bir SPRINT DEĞİL, kullanıcının kendi açık isteği

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

**Next action: Human review of corrected hyperbola QC, A0 baseline, and common-scale real-data montages.**

8 adaydan birinin veya A0'ın ("hiç background removal yapmama") canonical
seçilmesi, tek başına, bir sonraki sprinti (Gain veya başka bir işlem)
BAŞLATMAZ — bu proje hiçbir sprintte kendi kendine bir sonraki sprinte
geçmez. **Sprint 4B (Gain veya başka bir kapsam) henüz TANIMLANMADI ve
kullanıcının kendi açık isteği olmadan BAŞLATILMAYACAK.**

Detay: [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
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
PANEL.png`/`_DETAIL.png` tarihsel uyumluluk için korunuyor ama artık asıl
karar dosyaları DEĞİL. **"No background removal" (A0), insan reviewer
için geçerli, açıkça belgelenmiş bir karar seçeneğidir — background
removal canonical olmak ZORUNDA değildir.**

---

## Sprint 4B için olası kapsam (yalnızca bir taslak — henüz onaylanmadı)

Background-removal adayları artık üretildiğine göre (bkz. Sprint 4A),
olası bir Sprint 4B şu adımlardan birini/birkaçını kapsayabilir
(kesinleşmiş DEĞİL, yalnızca [[05_PROCESSING/Processing_Order]]'daki
planlanan sırayı yansıtan bir taslak): background-removal adaylarından
birinin canonical seçimi (insan/jeofizik kararı) ve/veya Gain — insan
kararı verilmiş bir background-removal çıktısı üzerinde. Bu liste bir
taahhüt değildir; Sprint 4B'nin kesin kapsamı yalnızca kullanıcının açık
isteğiyle netleşecektir.

## Kesinlikle yapılmayacaklar (bir sonraki adım için)
- Yeni bir background-removal adayını (A1-A8'den biri) OTOMATİK olarak
  canonical seçmek.
- Kullanıcının kendi açık isteği olmadan bir sonraki sprinti (Gain veya
  başka bir kapsam) başlatmak.
- 8 background-removal adayından biri canonical seçilmeden Gain'e
  başlamak.
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
- A0'ı ("hiç background removal yapmama") otomatik olarak canonical
  seçmek veya A1-A8'e göre otomatik olarak "daha iyi" saymak — A0 sadece
  bir referans noktasıdır, kullanıcının kendi kararı olmadan hiçbir satır
  (A0 dahil) canonical DEĞİLDİR.
- Herhangi bir anomali/arkeolojik yorum yapmak.

## İlgili notlar
[[02_SPRINTS/Sprint_Index]], [[02_SPRINTS/Sprint_04A_Background_Removal]],
[[02_SPRINTS/Sprint_03_Dewow_Bandpass]],
[[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]],
[[01_PROJECT_STATE/04_Risks_and_Limitations]],
[[01_PROJECT_STATE/03_Open_Issues]], [[05_PROCESSING/Background_Removal]],
[[05_PROCESSING/Gain]], [[05_PROCESSING/Processing_Order]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]]
