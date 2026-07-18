---
type: decision-index
tags: [decision]
---

# Decision Index

| ADR | Başlık | Durum |
|---|---|---|
| ADR-001 | [[ADR_001_OpenGPR_Internal_Data_Model]] | accepted |
| ADR-002 | [[ADR_002_TimeZero_Reference_and_Shift_Policy]] | accepted (madde 6, ADR-003 tarafından supersede edildi) |
| ADR-003 | [[ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]] | accepted |
| ADR-004 | [[ADR_004_TimeZero_Relative_Axis_and_DC_Window]] | accepted |
| ADR-005 | [[ADR_005_Dewow_Window_and_Edge_Policy]] | accepted |
| ADR-006 | [[ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]] | accepted |
| ADR-007 | [[ADR_007_Canonical_D2_B1_Selection]] | accepted |
| ADR-008 | [[ADR_008_Background_Removal_Channelwise_and_Window_Policy]] | accepted |
| ADR-009 | [[ADR_009_Canonical_No_Background_Removal_Policy]] | accepted |
| ADR-011 | [[ADR_011_GUI_Technology_Decision]] | accepted |
| ADR-012 | [[ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime]] | accepted |
| ADR-013 | [[ADR_013_Display_Policy_and_Non_Destructive_Visualization]] | accepted |

ADR-010 numarası bu index'te kasıtlı olarak atlanmıştır: `src/archaeogpr/
sprint4b_candidates.py` (untracked, `sprint-04b-gain-candidates`
branch'i) kod içinde bir ADR-010'a atıf yapıyor, ancak bu ADR henüz
vault'a yazılmamıştır — bkz.
[[01_PROJECT_STATE/06_GUI_3D_Risk_Register]] R11. Bu numara, o Sprint 4B
kararı resmen belgelendiğinde ADR-010 tarafından doldurulacaktır;
şimdiden başka bir karara verilmemiştir.

Yeni bir önemli mimari karar alındığında yeni bir ADR oluşturun (eskisini
sessizce değiştirmeyin — karar değişirse eski ADR'yi `superseded` olarak
işaretleyip yeni bir ADR oluşturun). Şablon: [[Template_ADR]].

## İlgili notlar
[[03_ARCHITECTURE/Data_Model]], [[00_HOME]]
