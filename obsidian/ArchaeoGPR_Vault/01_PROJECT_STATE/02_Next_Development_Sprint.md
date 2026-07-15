---
type: project-state
tags: [project-state, sprint]
---

# Next Development Sprint — Sprint 4 (henüz tanımlanmadı)

## Durum: D2 + B1 canonical seçildi; sıradaki adım hâlâ bir SPRINT DEĞİL, kullanıcının kendi açık isteği

Sprint 3 ([[02_SPRINTS/Sprint_03_Dewow_Bandpass]]) dewow ve band-pass
algoritmalarını, frekans spektrumu QC'sini ve aday parametre
karşılaştırmalarını (dewow D1-D4, band-pass B1-B4, kombine C1-C6)
uyguladı. Sprint 3.1
([[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]]), D2 dewow adayını
ayrıntılı doğruladı (4/4 koşul geçti → `recommended_dewow_candidate = D2`,
mühendislik önerisi) ve yalnızca B1/B2 band-pass adaylarını karar-odaklı QC
ile karşılaştırdı (mühendislik eğilimi: preservation-favoring/B1).
**2026-07-15'te kullanıcı bu iki öneriyi insan/jeofizik kararı olarak
onayladı: D2 dewow + B1 band-pass canonical** — bkz.
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]], `outputs/sprint03/canonical_D2_B1/`.
Toplam 254/254 test geçti; gerçek veride sıfır-faz, padding-güvenliği,
hash-değişmezliği ve determinizm doğrulandı.

**Next action: the user's own explicit request to define and start
Sprint 4.**

D2/B1'in canonical seçilmiş olması, tek başına, Sprint 4'ü
BAŞLATMAZ — bu proje hiçbir sprintte kendi kendine bir sonraki sprinte
geçmez. **Sprint 4 henüz TANIMLANMADI ve kullanıcının kendi açık isteği
olmadan BAŞLATILMAYACAK.**

Detay: [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
`outputs/sprint03/canonical_D2_B1/CANONICAL_PROCESSING_NOTE.md`,
`outputs/sprint03_1/DECISION_PANEL_D2_B1_B2.png`,
`outputs/sprint03_1/BANDPASS_FINAL_DECISION_REQUIRED.md`,
`outputs/sprint03_1/D2_DEWOW_DECISION.md`,
[[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]],
[[02_SPRINTS/Sprint_03_Dewow_Bandpass]].

---

## Sprint 4 için olası kapsam (yalnızca bir taslak — henüz onaylanmadı)

Dewow ve band-pass adayları artık seçildiğine göre (D2 + B1, bkz. ADR-007),
olası bir Sprint 4 şu adımlardan birini/birkaçını kapsayabilir
(kesinleşmiş DEĞİL, yalnızca [[05_PROCESSING/Processing_Order]]'daki
planlanan sırayı yansıtan bir taslak): background removal, gain, (isteğe
bağlı ve varsayılan KAPALI) F-K filtering — canonical `outputs/sprint03/
canonical_D2_B1/sprint03_processed.npz` girdisi üzerinde. Bu liste bir
taahhüt değildir; Sprint 4'ün kesin kapsamı yalnızca kullanıcının açık
isteğiyle netleşecektir.

## Kesinlikle yapılmayacaklar (bir sonraki adım için)
- Yeni bir dewow veya band-pass adayını OTOMATİK olarak canonical
  seçmek (D2/B1'in kendisi de kullanıcının insan kararıydı, kodun
  otomatik seçimi değil).
- Kullanıcının kendi açık isteği olmadan Sprint 4'ü başlatmak.
- D2/B1'in `Swath003_Array02.ogpr` dışındaki bir veri setine otomatik
  olarak (kendi aday karşılaştırması/insan incelemesi olmadan)
  uygulanması.
- Header'ın 600 MHz nominal frekansını tek başına bir band-pass aralığı
  seçim kriteri olarak kullanmak (bkz.
  `outputs/sprint03/spectrum/SPECTRUM_INTERPRETATION_NOTES.md`).
- B2'nin geç-zaman penceresindeki ham medyan-iz gecikmesini (40 örnek,
  bkz. `outputs/sprint03_1/PHASE_METRICS_INTERPRETATION_NOTES.md`) gerçek
  bir faz kayması olarak yorumlamak.
- Herhangi bir anomali/arkeolojik yorum yapmak.

## İlgili notlar
[[02_SPRINTS/Sprint_Index]], [[02_SPRINTS/Sprint_03_Dewow_Bandpass]],
[[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]],
[[01_PROJECT_STATE/04_Risks_and_Limitations]],
[[01_PROJECT_STATE/03_Open_Issues]], [[05_PROCESSING/Dewow]],
[[05_PROCESSING/Bandpass_Filter]], [[05_PROCESSING/Processing_Order]],
[[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]],
[[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]
