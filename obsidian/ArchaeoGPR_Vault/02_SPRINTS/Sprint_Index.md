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
| GUI-3A | Non-Destructive Processing Preview & Apply (5 stabil processing fonksiyonu: time-zero/DC offset/dewow/band-pass/background removal — preview→apply, raw/current/preview ayrımı, `0.3.0`) — undo/redo/recipe/gain/3D YOK | ✅ done | [[Sprint_GUI_3A_Processing_Preview_Apply]] |
| 3D-0 | Survey Geometry Inspector and C-scan Readiness (Qt-free `archaeogpr.geometry` paketi, alan-bazlı provenance, index/local/global koordinat çözümü, 7 readiness gate, Survey Geometry dock + override formu, 2D Plan View, geometry report JSON export, `0.4.0`) — volume render/PyVista/gerçek C-scan YOK | ✅ done | [[Sprint_3D_0_Survey_Geometry_Inspector]] |
| 3D-1 | Actual X/Y Point-Grid C-scan and Time-Slice Viewer (Qt-free `archaeogpr.cscan` paketi, half-open zaman penceresi, 4 aggregation, actual X/Y point-map + derived s/c parameter-grid — asla resample edilmez, CScanSession/CScanWorker, ActiveTaskKind 3-yönlü mutual exclusion, PNG+JSON export, `0.5.0`) — gridding/PyVista/volume render YOK | 🔄 in_progress (dokümantasyon + quality gate + build kaldı) | [[Sprint_3D_1_Actual_XY_Point_Grid_CScan]] |

GUI-0/GUI-1/GUI-2 `main`'e merge edildi (2026-07-18, PR #2, merge commit
`009fb9d`). GUI-1B `main`'e merge edildi (2026-07-18, PR #3, merge commit
`870f0c8`). GUI-3A `main`'e merge edildi (2026-07-19, PR #4, merge commit
`f3e516c`). 3D-0 `main`'e merge edildi (2026-07-20, PR #5, merge commit
`a43d947`). 3D-1 henüz commit/merge edilmedi (implementasyon + testler
tamam, dokümantasyon/quality gate/build sürüyor). Sprint 4B (Gain veya
başka bir kapsam) henüz TANIMLANMADI — bkz.
[[01_PROJECT_STATE/02_Next_Development_Sprint]]. GUI track'i, Sprint 4B
ile aynı şey DEĞİLDİR ve onu başlatmaz — ayrı, paralel bir track'tir
(GUI/3D dönüşümü). Bir sonraki GUI sprinti (undo/redo, recipe, veya
gridding/volume render) yalnızca kullanıcının ayrı, açık onayıyla başlar.

Yeni sprint notu oluştururken [[Template_Sprint]] şablonunu kullanın.

## İlgili notlar
[[01_PROJECT_STATE/05_Project_Roadmap]], [[00_HOME]]
