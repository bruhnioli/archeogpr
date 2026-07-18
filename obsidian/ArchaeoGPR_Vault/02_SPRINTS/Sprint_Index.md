---
type: sprint-index
tags: [sprint]
---

# Sprint Index

| Sprint | Başlık | Durum | Not |
|---|---|---|---|
| 1 | OpenGPR Infrastructure | ✅ done | [[Sprint_01_OpenGPR_Infrastructure]] |
| 2 | Time-Zero & DC Offset Correction | ✅ done | [[Sprint_02_TimeZero_DCOffset]] |
| 2.1 | Time-Zero/DC Offset Review, Padding-Mask Safety & QC | ✅ done | [[Sprint_02_1_TimeZero_DCOffset_Review]] |
| 2.2 | Time-Zero-Relative Time Axis & Target-Invariant DC Offset | ✅ done | [[Sprint_02_2_TimeAxis_DCWindow_Validation]] |
| 3 | Dewow & Band-pass Filtering, Frequency Spectrum QC & Candidate Comparison | ✅ done (D2+B1 canonical seçildi, bkz. ADR-007) | [[Sprint_03_Dewow_Bandpass]] |
| 3.1 | D2 Dewow Confirmation & B1/B2 Band-Pass Decision QC | ✅ done (insan kararı: D2 onaylandı, B1 seçildi) | [[Sprint_03_1_Dewow_Bandpass_Decision_QC]] |
| 4A | Background Removal Candidate Development, Signal-Preservation Validation & Geophysical QC | ✅ done (insan kararı: canonical policy = A0, background removal uygulanmadı) | [[Sprint_04A_Background_Removal]] |
| GUI-0 | GUI/3D Dönüşümü: Repository Audit, Mimari Tasarım ve Bağımlılık İskeleti (kod YOK — yalnızca ADR/mimari/risk belgeleri + pyproject metadata) | ✅ done | [[Sprint_GUI_0_Foundation]] |
| GUI-1 | Native Windows Viewer Shell + Executable (PySide6 uygulama kabuğu, File→Open OGPR, B-scan/A-scan, metadata paneli, `ArchaeoGPR.exe`) | ✅ done | [[Sprint_GUI_1_Viewer_Shell]] |
| GUI-2 | Display Controls & Interaction (kontrast/percentile/colormap/A-scan modları, metadata okunabilirliği, PNG export, `0.2.0`) — veri işleme YOK | ✅ done | [[Sprint_GUI_2_Display_Controls]] |
| GUI-1B | Background Tasks & Responsive File Loading (QThread worker, progress/Cancel UI, kooperatif iptal, atomik session commit, `0.2.1`) — veri işleme YOK | ✅ done | [[Sprint_GUI_1B_Background_Tasks]] |

GUI-0/GUI-1/GUI-2/GUI-1B `main`'e merge edildi (2026-07-18, PR #2, merge
commit `009fb9d`). Sprint 4B (Gain veya başka bir kapsam) henüz
TANIMLANMADI — bkz. [[01_PROJECT_STATE/02_Next_Development_Sprint]].
GUI track'i, Sprint 4B ile aynı şey DEĞİLDİR ve onu başlatmaz — ayrı,
paralel bir track'tir (GUI/3D dönüşümü). Bir sonraki GUI sprinti
(processing entegrasyonu veya 3D/gridding) yalnızca kullanıcının ayrı,
açık onayıyla başlar.

Yeni sprint notu oluştururken [[Template_Sprint]] şablonunu kullanın.

## İlgili notlar
[[01_PROJECT_STATE/05_Project_Roadmap]], [[00_HOME]]
