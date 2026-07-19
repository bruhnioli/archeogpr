---
type: sprint
tags: [sprint, gui, geometry]
sprint: 3D-0
status: done
started: 2026-07-19
completed: 2026-07-19
---

# Sprint 3D-0 — Survey Geometry Inspector and C-scan Readiness

> **Kapsam:** OGPR verisinin trace/channel geometrisini bilimsel olarak
> denetlemek; bilinen/türetilmiş/kullanıcı-girişli/eksik geometrik
> bilgileri açıkça ayırmak; acquisition footprint'i 2D plan görünümünde
> göstermek; C-scan ve gelecekteki 3D sprintleri için güvenilir bir
> coordinate grid sözleşmesi üretmek; veri setinin C-scan/3D için hazır
> olup olmadığını raporlamak. **Bu sprintin amacı hacim render etmek
> DEĞİLDİR** — PyVista, VTK, volume rendering, gerçek amplitude C-scan bu
> sprintte YOK. Temel karar kaydı:
> [[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]].

## Goal

`obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/3D_Volume_Data_Model.md`'nin
planladığı gridding/3D işinin **önkoşulu** olan güvenilir bir survey
geometrisi modelini, açık provenance takibiyle, native GUI'ye eklemek.
GUI-0/GUI-1/GUI-2/GUI-1B/GUI-3A `main`'e merge edilmiş durumda
(2026-07-19, PR #4, merge commit `f3e516c`); bu sprint o temel üzerine
geometry inspection'ı ekliyor.

## Scope

- `src/archaeogpr/geometry/{__init__,models,resolve,validation,export,
  summary}.py` (yeni, Qt import yok) — `GeometryProvenance`,
  `CoordinateMode`, `CrossTrackDirection`, `ReadinessStatus`/
  `ReadinessGates`, `SurveyGeometry`, `GeometryOverrides`,
  `GeometryResolution`, `resolve_survey_geometry()`, `GeometrySummary`,
  `compute_geometry_summary()`, geometry report JSON export.
- `src/archaeogpr/gui/models/geometry_session.py` (yeni) — `GeometrySession`,
  `DatasetSession`'dan bağımsız.
- `src/archaeogpr/gui/views/geometry_panel.py` (yeni) — salt-okunur
  Survey Geometry bilgi ağacı (`MetadataPanel` deseni).
- `src/archaeogpr/gui/views/plan_view.py` (yeni) — 2D acquisition
  footprint plan view (PyQtGraph, vektörel scatter).
- `src/archaeogpr/gui/main_window.py` — Survey Geometry dock, Plan View
  dock, override formu, Apply/Discard/Reset, File > Export Geometry
  Report, trace/channel <-> plan view seçim senkronizasyonu.
- `tests/test_geometry.py` (yeni) — 25 test, Qt'siz.
- `tests/test_gui_geometry.py` (yeni) — 30 test, `@pytest.mark.gui`.
- Dokümantasyon: bu not, ADR-016, README, Current_Project_State,
  Next_Development_Sprint, Sprint_Index, Decision_Index, GUI_Architecture,
  Processing_Preview_and_Commit_Model, 3D_Volume_Data_Model,
  Windows_Executable_Build.
- Version: `0.3.0` → `0.4.0` (minor — yeni kullanıcı-görünür özellik).

## Out of Scope

Amplitude C-scan, time-slice aggregation, RMS slice, interpolation,
gridding/resampling, PyVista, VTK, volume rendering, isosurface, depth
conversion, velocity input, migration, gain, undo/redo, processing recipe,
processed dataset kaydetme, installer, signing, auto-update. Geographic
(lat/lon) coordinate modu enum olarak var ama bu sprintte hiç
üretilmiyor — reprojection bağımlılığı eklenmedi.

## Input Data

`data/raw/Swath003_Array02.ogpr` (gerçek dosya, ~8 MB, gerçek geolocation
içeriyor) + `tests/conftest.py`'deki `ogpr_builder`/`dataset_factory`
fixture'ları (yeniden kullanıldı — `ogpr_builder` zaten sentetik geolocation
içeriyordu, EPSG:32632 dahil). Yeni yardımcılar:
`_make_real_geolocation_dataset` (ogpr_builder + read_ogpr round-trip, GLOBAL
mode testleri için), `_GatedApply`/`_spec_with_apply`/`_select_operation`
(test_gui_processing.py'nin desenleri, cross-file coupling'den kaçınmak için
yerel kopyalar).

## Tasks

- [x] Repository doğrulandı (`main` @ `f3e516c`, temiz).
- [x] `sprint-gui-1b-background-tasks` yerel dalı (main'e tam merge
  edildiği doğrulandıktan sonra) güvenle silindi.
- [x] `sprint-3d-0-geometry-inspector` branch'i `main`'den açıldı.
- [x] Geometry/metadata audit yapıldı (Explore agent + doğrudan kod/gerçek
  dosya okuması) — gerçek dosyada azimuth/heading/anten-offset hiç yok,
  CRS doğrulanmamış (ISSUE-001), gerçek per-trace x/y koordinatları zaten
  mevcut.
- [x] Geometry domain modeli, resolver, coordinate transform'lar,
  readiness gate'ler yazıldı (5 madde).
- [x] `GeometrySession` yazıldı, `DatasetSession`'dan bağımsız.
- [x] Geometry Inspector dock (6 bölüm: A-F), override formu, Plan View
  yazıldı ve `MainWindow`'a entegre edildi.
- [x] Trace/channel <-> plan view seçim senkronizasyonu (iki yönlü).
- [x] File-load/processing busy-state entegrasyonu (fonksiyonel guard'lar,
  ADR-015'in aynı deseni).
- [x] Version `0.4.0`'a yükseltildi.
- [x] 25 domain testi + 30 GUI testi yazıldı; yazım sırasında 3 gerçek
  test hatası bulundu ve düzeltildi (bkz. Issues Discovered).
- [x] Final doğrulama: ruff/mypy/core/gui/vault validator.
- [x] Executable `0.4.0` olarak build edildi, yeni ZIP oluşturuldu.

## Acceptance Criteria

Kullanıcının orijinal talimatındaki 44. bölüm ("Son Rapor") maddelerinin
tamamı — bkz. bu sprintin sonuç raporu (kullanıcıya sunulan mesaj).

## Implementation Notes

### Qt-free `archaeogpr.geometry` paketi: mevcut processing/QC matematiğini asla tekrarlamaz

`compute_trace_spacing()` (`processing/background.py`) ve
`compute_cross_channel_spacing_m()` (`qc/metadata.py`) doğrudan
çağrılıyor — trace/channel spacing için hiçbir yeni hesaplama kodu
yazılmadı. Detay: [[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]]
Decision madde 1.

### `SurveyGeometry`: her alanda ayrı provenance etiketi

`GeometryProvenance` (FILE_METADATA/DERIVED/USER_SUPPLIED/INDEX_SPACE/
MISSING) her alan için ayrı ayrı kaydediliyor. Gerçek dosyada azimuth/
heading/anten-offset/channel-identifier **hiç yok** (audit ile kanıtlandı,
0 grep sonucu) — bu üçü asla varsayılmıyor, yalnızca DERIVED (gerçek x/y
varsa) veya MISSING/USER_SUPPLIED. Tek istisna: channel zero offset'in
`0.0` varsayılanı — bu fiziksel bir iddia değil, bir koordinat sistemi
orijin kuralı (INDEX_SPACE olarak etiketleniyor). Detay: ADR-016 Decision
madde 2-3.

### İki bağımsız GLOBAL_PROJECTED yolu

Gerçek dosyada zaten per-trace x/y varsa (has_geolocation=True) bunlar
doğrudan kullanılıyor — azimuth/origin/cross-track-direction'a hiç ihtiyaç
yok, ama bu üçü görüntüleme amaçlı aynı gerçek koordinatlardan DERIVED
olarak hesaplanıyor (ve gerçek dosyaya karşı çapraz doğrulandı: azimuth
≈131.3°, cross-track sağa-artan — fiziksel olarak tutarlı). Gerçek
geolocation yoksa, kullanıcının origin+azimuth+cross-track-direction+CRS
girmesiyle section-9 formülü devreye giriyor — cross-track yönü UNKNOWN
ise bu yol her zaman reddediliyor. Detay: ADR-016 Decision madde 4.

### Beş readiness gate, tek boolean değil

`index_view_ready`, `local_cscan_ready`, `global_cscan_ready`,
`time_volume_ready`, `depth_volume_ready` — her biri
`(ready, blocking_issues, warnings)`. `depth_volume_ready` bu sprintte
**her zaman False** (hız onayı akışı yok). Detay: ADR-016 Decision madde 5.

### `GeometrySession`: `DatasetSession`'dan bağımsız, yeni alan değil

Geometry, dosya başına bir kez resolve ediliyor
(`resolve_for_new_dataset`, `_refresh_for_new_dataset`'ten çağrılıyor) ve
processing preview/apply/discard/reset-to-raw'da **hiç** yeniden resolve
edilmiyor — çünkü 5 processing operasyonundan hiçbiri trace/channel
sayısını değiştirmiyor. Başarısız/iptal edilen bir yükleme
`_refresh_for_new_dataset`'i hiç çağırmadığı için önceki dosyanın
geometrisi otomatik olarak korunuyor, ekstra kod gerekmedi. Detay: ADR-016
Decision madde 6.

### Override belirsizliği: bazı alanların "unset" durumu yalnızca Discard/Reset ile ulaşılabilir

`trace_spacing_m`/`channel_spacing_m` için `0.0` = "not set"
(`setSpecialValueText`, çünkü gerçek spacing her zaman pozitif).
`channel_zero_offset_m`/`origin_x`/`origin_y`/`azimuth_deg` için `0.0`
geçerli bir gerçek değer olduğundan bu sentinel kullanılamıyor — widget'a
dokunulduğu an USER_SUPPLIED olur, yalnızca Discard/Reset ile geri
alınabilir. Bilinçli bir basitleştirme, atlanmış bir detay değil. Detay:
ADR-016 Decision madde 7.

### Plan View: tek vektörel scatter, asla nokta başına widget

~1925 acquisition point tek bir `pg.ScatterPlotItem` ile render ediliyor.
Along-track yönü start/end marker + çizgi (qc/geometry.py'nin kendi
konvansiyonu), channel-ascending yönü ayrı bir cross-track çizgisiyle
gösteriliyor — ikisi fiziksel olarak bağımsız eksenler. Detay: ADR-016
Decision madde 8.

### Busy-state: fonksiyonel guard'lar, üçüncü bir deferred-close state machine değil

`resolve_survey_geometry()` hızlı, senkron, saf Python — kendi QThread'ine
ihtiyacı yok. Her geometry handler'ı `_close_pending`/`is_loading`/
`is_processing`'i kontrol ediyor (Reset-to-Raw'ın aynı deseni). Salt-okunur
bilgi ağacı ve Plan View (seçim senkronizasyonu dahil) processing
sırasında kullanılabilir kalıyor — yalnızca override formu/Apply/Discard/
Reset/Export engelleniyor. Detay: ADR-016 Decision madde 10.

### Test yazarken bulunan üç sorun (biri gerçek production kod eksikliği, ikisi test hatası)

1. **Gerçek, küçük bir production kodu eksikliği**: `MainWindow.__init__`
   yeni Survey Geometry dock'unun override formunu/butonlarını
   `_refresh_geometry_panel()` ile başlangıçta disable etmiyordu (Processing
   dock'un `_set_processing_state(ProcessingState.IDLE)` çağrısının eşdeğeri
   eksikti). `test_geometry_controls_disabled_with_no_dataset` bunu yakaladı;
   `__init__`'in sonuna `self._refresh_geometry_panel()` eklenerek düzeltildi.
2. **Test hatası**: geometry report export testi var olmayan bir
   `Path("x.ogpr")` kullanıyordu — export fonksiyonu gerçek dosyayı
   hashlemeye çalışıp `FileNotFoundError` fırlattı, `main_window.py` bunu
   doğru şekilde `QMessageBox.critical` ile gösterdi, ama test
   `no_blocking_dialogs` fixture'ını kullanmadığı için sonsuza kadar
   offscreen döndü (ADR-015'te belgelenen aynı tuzak). Gerçek, diskte var
   olan bir dosya kullanılarak düzeltildi.
3. **Test hatası**: time-zero preview testi çok küçük bir sentetik veri
   seti kullanıyordu (4 örnek × 0.5 ns = 2 ns) — `correct_time_zero`'nun
   varsayılan `[5, 15)` ns arama penceresi bu aralığın tamamen dışında
   kaldığı için fonksiyon doğru şekilde `ProcessingError` fırlattı. Daha
   büyük bir örnek sayısı/aralığı kullanılarak düzeltildi.

Üçü de Issues Discovered'da tekrar özetleniyor.

## Validation Results

| Kontrol | Sonuç |
|---|---|
| `ruff format --check .` | ✅ tüm dosyalar zaten formatlı |
| `ruff check .` | ✅ All checks passed |
| `mypy src/archaeogpr` | ✅ 0 hata (68 dosya) |
| `pytest -m "not gui"` | ✅ 343 passed, 26 skipped, 152 deselected, 0 failed |
| `pytest -m gui` (offscreen) | ✅ **152 passed** (74 GUI-1/2/1B + 48 GUI-3A + 30 3D-0), 369 deselected, 0 failed |
| `archaeogpr.gui --version` | ✅ `0.4.0` |

### Yeni testler

| Dosya | Test sayısı | Kapsam |
|---|---|---|
| `tests/test_geometry.py` (Qt'siz) | 25 | index/local/global geometri, provenance, override önceliği, immutability, global transform (azimuth 0°/90°/sağ/sol), unknown cross-track reddi, missing CRS/local readiness, duplicate/non-finite coordinate detection, JSON export |
| `tests/test_gui_geometry.py` (`@pytest.mark.gui`) | 30 | dock oluşturma, özet güncelleme, disabled-with-no-dataset, index/local/global mod eksen etiketleri+CRS, provenance/readiness/validation gösterimi, Apply/Discard/Reset, busy-state reddi (processing+file load), failed/cancelled load geometriyi korur, plan<->trace/channel senkronizasyonu, equal-aspect, fit-to-data, invalid point crash yok, hover readout, export (başarı/iptal/shutdown-pending reddi), raw dosya değişmezliği |

## Generated Outputs

Bu sprint `outputs/`'a hiçbir dosya yazmadı (GUI kodu/test). `dist/ArchaeoGPR/`
`0.4.0` olarak build edildi; yeni ZIP:

- Yol: `C:\Dev\ArchaeoGPR-Releases\ArchaeoGPR-0.4.0-win64.zip`
- Boyut: (sonuç raporunda kesin değer)
- SHA-256: (sonuç raporunda kesin değer)

Eski `0.1.0`/`0.2.0`/`0.2.1`/`0.3.0` ZIP'leri değiştirilmedi/silinmedi.

## Issues Discovered

1. **Production kodu: `MainWindow.__init__` Survey Geometry dock'unu
   başlangıçta disable etmiyordu** — `_refresh_geometry_panel()` çağrısı
   eksikti. Bir GUI testi tarafından yakalandı, tek satırlık ekleme ile
   düzeltildi.
2. **Test yazarken: geometry export testi var olmayan bir dosya yolu
   kullanıyordu + mock'suz `QMessageBox.critical` → sonsuz offscreen
   donma** — üretim kodunda hata değil. Gerçek, diskte var olan bir dosya
   kullanılarak düzeltildi.
3. **Test yazarken: time-zero preview testi çok küçük bir sentetik veri
   seti kullanıyordu, varsayılan arama penceresi veri aralığının dışına
   taşıyordu** — üretim kodunda hata değil (`correct_time_zero` doğru
   şekilde reddetti). Daha büyük bir veri seti kullanılarak düzeltildi.

## Commit-Öncesi Audit Turu (2026-07-19)

Kullanıcı, kod tabanını yeniden yazmadan önce hedefli bir commit-öncesi
audit istedi. Bulunan ve düzeltilen maddeler (detaylı gerekçe:
[[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]] "Addendum:
Pre-Commit Audit Fixes"):

1. **Dosya kapsamı raporlama hatası**: önceki iki raporda "18 değişiklik
   (10 modified + 8 untracked)" denmişti — gerçekte 11 modified + 8
   untracked *satır*, ama bu 8 satırdan biri (`src/archaeogpr/geometry/`)
   6 gerçek dosyayı tek satırda gösteren bir dizin. Gerçek sayı: **11
   modified + 13 added = 24 dosya**. Beklenmedik bir dosya yoktu — saf bir
   raporlama hatasıydı.
2. **`PlanView`'da gerçek bir `RuntimeWarning`**: tüm bir trace'in
   `along_track_coordinates` değeri NaN olduğunda, bu değer o satırın tüm
   kanallarına broadcast ediliyor ve `invalid_scatter.setData()`'ya
   verildiğinde pyqtgraph'ın kendi `np.nanmin`/`np.nanmax` sınır
   hesaplaması "All-NaN slice encountered" uyarısı veriyordu (crash yok,
   ama gürültülü). Düzeltme: her eksen için invalid alt kümede en az bir
   finite değer var mı kontrol ediliyor, yoksa o güncelleme için hiçbir
   şey render edilmiyor.
3. **`CrsValidationStatus`** (`MISSING`/`DECLARED_UNVERIFIED`/
   `USER_SUPPLIED_UNVERIFIED`/`VALIDATED`) eklendi — `SurveyGeometry` üzerinde
   hesaplanan bir property (ayrı bir alan değil). GUI artık asla çıplak
   "Global projected" yazmıyor — "Global projected — declared CRS,
   unverified" gibi. **ISSUE-001 hâlâ açık** — bu belirsizlik yalnızca
   görünür kılındı, çözülmedi.
4. **Gerçek grid ile idealize edilmiş rectilinear grid ayrımı**
   (`src/archaeogpr/geometry/regularity.py`, yeni): along/cross-track
   dizileri her zaman tek bir spacing istatistiğinden kurulan idealize
   edilmiş bir rectilinear yapı — gerçek noktaların buna ne kadar uyduğunu
   yansıtmaz. Üç şekil istatistiği (adım uzunluğu CV, kanal-arası spacing
   CV, yön dairesel std'si) ile ölçülüyor; `footprint_area_m2` yalnızca bu
   üçü tolerans içindeyken hesaplanıyor. **Önemli, veriye dayalı bulgu**:
   gerçek dosyaya karşı test edilen dördüncü bir aday metrik (idealize
   rekonstrüksiyona karşı nokta-bazlı residual) gating kriteri olarak
   reddedildi — gerçek dosyada residual 38 cm'ye çıkıyor (tolerans ~0.4 cm
   olurdu) ama şekil istatistikleri mükemmel (%2.3 CV, 1.7° yön std'si) —
   çünkü gerçek GPS-tetiklemeli trace pozisyonları, tamamen düz bir hatta
   bile, iki-nokta doğrusal rekonstrüksiyondan mesafeyle büyüyen bir sapma
   gösteriyor. Bu metrik gating için kullanılsaydı neredeyse tüm gerçek
   saha verisi reddedilirdi. Yine de bilgilendirme amaçlı hesaplanıp
   raporlanıyor.
5. **`MainWindow`'ın +305 satırı denetlendi, refactor yapılmadı**: her
   ekleme ya saf widget kurulumu (mevcut `_build_*` dock desenleriyle
   birebir) ya da `GeometrySession`/`GeometryPanel`/`PlanView`/
   `archaeogpr.geometry.export`'a ince bir delegasyon — GUI-3A'nın
   Processing dock deseniyle yapısal olarak özdeş.
6. **Ayrı bir gerçek production hatası**: `geometry_panel.py`'nin "F.
   Validation" bölümü yalnızca `local_cscan_ready.warnings`'i topluyordu,
   diğer 4 gate'in warning'lerini (ve `GeometrySummary.warnings`'i hiç)
   sessizce atlıyordu — düzeltilmeseydi madde 3-4'teki yeni uyarılar GUI'de
   hiç görünmeyecekti. Tüm 5 gate + summary warning'leri toplanacak şekilde
   düzeltildi.

Yeni test sayıları: `tests/test_geometry.py` 25 → 39 (+14); `tests/
test_gui_geometry.py` 30 → 31 (+1 yeni, 1 güçlendirilmiş).

## Commit-Öncesi Audit Turu 2 — Regularity Model İnceliği (2026-07-19, aynı gün)

Kullanıcı, Tur 1'i büyük ölçüde kabul etti ama bilimsel bir kavram
ayrımının hâlâ eksik olduğunu belirledi: **düzenli örnekleme** ile
**rectilinear geometri** aynı şey değildir, ve Tur 1'in tek `is_regular`
alanı ikisini birleştiriyordu. Tam gerekçe:
[[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]]
"Addendum 2".

- **`GridRegularity` dört ayrı kavrama bölündü**: `actual_point_grid_
  available` (düz bool), `sampling_regular` (adım uzunluğu + kanal-arası
  spacing CV'si, gerçek noktalar arası — origin/azimuth gerekmez),
  `direction_consistent` (yön dairesel std'si — o da origin/azimuth
  gerektirmez), `rectilinear_fit_acceptable` (gerçek grid ile idealize
  rekonstrüksiyon arasındaki residual, boyutsuz oranlarla — TEK gerçekten
  origin/azimuth/yön/spacing gerektiren kontrol).
- **Tolerans**: `max(kanal spacing'in %50'si, along-track span'in %1'i)`
  VE `direction_consistent` — sabit, gerekçeli, boyutsuz oranlara dayalı
  (bkz. ADR-016 Addendum 2 madde 2). Tur 1'in %10 residual kontrolü artık
  yalnızca bilgilendirme amaçlı, gating için KULLANILMIYOR.
- **Gerçek dosya sonucu**: `sampling_regular=True`, `direction_
  consistent=True`, `rectilinear_fit_acceptable=False` — residual 0.3817 m
  = kanal spacing'in 5.09 katı, kullanıcının kendi "~5 kanal aralığı"
  tahminiyle birebir örtüşüyor.
- **Readiness gate'leri 5'ten 7'ye çıktı**: `local_cscan_ready` →
  `local_parameter_grid_ready` (yeniden adlandırıldı), yeni
  `rectilinear_cscan_ready` ve `actual_xy_point_grid_ready` eklendi;
  `global_cscan_ready`/`time_volume_ready`'nin semantiği netleştirildi
  (davranış değil, yalnızca hangi grid temsiline dayandıkları).
- **Footprint area üçe bölündü**: `rectilinear_parameter_grid_area_m2`
  (yalnızca `rectilinear_fit_acceptable=True` iken), `approximate_ribbon_
  area_m2` (gerçek yol uzunluğu × nominal genişlik, her zaman warning'li),
  `actual_polygon_area_m2` (shoelace formülü, kendi kendine kesişme/
  bozulma riski varsa reddedilir). Gerçek dosya için ilk alan `None`,
  diğer ikisi ~5.22-5.24 m² ile birbirine yakın.
- **C-scan sözleşmesi**: gelecekteki bir gridding sprinti iki yol arasında
  AÇIKÇA seçmeli — rectilinear parameter-grid render (`rectilinear_
  cscan_ready`'e bağlı) veya actual/curvilinear point-grid render
  (`actual_xy_point_grid_ready`'e bağlı) — hiçbiri sessizce diğerinin
  yerine geçmemeli.
- **6 yeni domain testi + 1 yeni GUI testi** eklendi; bu süreçte hem
  `rectilinear_parameter_grid_area_m2`'nin yanlışlıkla koşulsuz hale
  geldiği bir implementasyon hatası hem de test fixture'ının kendi
  azimuth varsayımıyla eşleşmeyen bir eksen kuralı hatası bulunup
  düzeltildi (üretim kodu hatası değil, test yazım hatası).

Yeni test sayıları: `tests/test_geometry.py` 39 → 45 (+6); `tests/
test_gui_geometry.py` 31 → 32 (+1, + 1 mevcut testin sabit grup sayısı
6'dan 7'ye güncellendi).

## Decisions

1. `archaeogpr.geometry` Qt-free paketi mevcut `compute_trace_spacing()`/
   `compute_cross_channel_spacing_m()`'i yeniden kullanıyor, kopyalamıyor.
2. Her geometry alanı için ayrı provenance etiketi; azimuth/heading/anten-
   offset gerçek dosyada yok, asla varsayılmıyor.
3. Öncelik sırası: user override > file metadata > derived > index
   fallback > missing (channel zero offset'in 0.0 varsayılanı hariç, bu
   bir koordinat konvansiyonu).
4. İki bağımsız GLOBAL_PROJECTED yolu: gerçek x/y varsa doğrudan kullan;
   yoksa azimuth+origin+cross-track-direction+CRS ile reconstruction,
   unknown yönde her zaman reddedilir.
5. Beş readiness gate, `(ready, blocking_issues, warnings)` yapısında;
   depth_volume_ready bu sprintte her zaman False.
6. `GeometrySession`, `DatasetSession`'dan bağımsız; geometry yalnızca
   dosya yüklemede resolve edilir, processing geçişlerinde asla.
7. Bazı override alanları (signed float) için "unset" yalnızca Discard/
   Reset ile ulaşılabilir — per-field clear kontrolü eklenmedi.
8. Plan View tek vektörel scatter item kullanıyor; along-track ve
   cross-track yönleri ayrı görsel olarak gösteriliyor.
9. Geometry Inspector, `MetadataPanel`'in grouped tree deseni yeniden
   kullanılarak inşa edildi.
10. Geometry busy-state, yeni bir state machine yerine mevcut
    `is_loading`/`is_processing`/`_close_pending` fonksiyonel guard'larını
    kullanıyor.

## Completion Summary

Survey Geometry Inspector, `archaeogpr.geometry` Qt-free paketi (models/
resolve/validation/export/summary), `GeometrySession`, Geometry Inspector
dock (6 bölüm + override formu), ve Plan View (2D acquisition footprint,
iki yönlü trace/channel senkronizasyonu) ile hayata geçirildi. Beş
readiness gate (index/local/global/time-volume/depth-volume) ve JSON
geometry report export'u eklendi. 55 yeni test (25 domain + 30 GUI) + mevcut
152 GUI testi ve 343 çekirdek test tamamen yeşil. Test yazım sürecinde
bulunan iki gerçek test hatası ve bir küçük production kodu eksikliği
(dock'un başlangıç disable durumu) düzeltildi. **Main'e merge henüz
gerçekleşmedi.** Native Windows build için manuel kullanıcı kabulü alındı
(bkz. Manual Visual Acceptance).

## Manual Visual Acceptance

Manual acceptance was confirmed by the user for the native Windows build.

Kullanıcının kabul ettiği kapsam:

- Survey Geometry panel opens and displays the loaded survey.
- Declared-but-unverified CRS status is visible.
- Sampling regularity and rectilinear fit are shown separately.
- The real survey reports regular sampling but an unacceptable rectilinear
  fit.
- Actual X/Y point-grid readiness and rectilinear C-scan readiness are
  distinct.
- Plan View renders and synchronizes trace/channel selection.
- Geometry overrides, Discard and Reset operate as expected.
- Processing does not alter geometry state.
- Geometry Report JSON export works.
- Raw OGPR integrity is preserved.

This is a user acceptance statement. The interactive steps were not
executed or observed by Claude and must not be presented as
automated-test evidence.

## Next Sprint Recommendation

Kullanıcının kendi isteğiyle: bu sprintin bilinçli olarak temelini attığı
ama implemente etmediği C-scan/3D gridding (`GeometryDiagnostics`,
resample, missing_mask — bkz. [[03_ARCHITECTURE/3D_Volume_Data_Model]]),
gain, undo/redo stack, recipe sistemi, veya processed dataset kaydetme.

## İlgili Notlar

[[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]],
[[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]],
[[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]],
[[03_ARCHITECTURE/3D_Volume_Data_Model]],
[[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]],
[[03_ARCHITECTURE/GUI_Architecture]],
[[03_ARCHITECTURE/OpenGPR_File_Structure]],
[[02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply]],
[[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]],
[[02_SPRINTS/Sprint_GUI_2_Display_Controls]],
[[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]],
[[09_REFERENCES/Windows_Executable_Build]], [[02_SPRINTS/Sprint_Index]]
