---
type: sprint
tags: [sprint, gui, cscan]
sprint: 3D-1
status: in_progress
started: 2026-07-20
completed:
---

# Sprint 3D-1 — Actual X/Y Point-Grid C-scan and Time-Slice Viewer

> **Kapsam:** Sprint 3D-0'ın ürettiği survey geometrisi ve readiness
> gate'leri üzerine, bir zaman-örneği veya zaman-penceresinden türetilen
> gerçek amplitude C-scan/time-slice değer gridini implemente etmek;
> bunu gerçek acquisition'ın kendi X/Y point grid'inde (varsayılan, hiç
> interpolasyon yok) veya idealize edilmiş türetilmiş s/c parametre
> gridinde (açıkça etiketli, asla birinciyle karıştırılmaz) göstermek;
> Raw/Current/Preview kaynaklarını desteklemek; trace/channel/zaman
> seçimini B-scan/A-scan/Plan View/C-scan arasında senkronize etmek;
> gelecekteki bir PyVista/hacim sprintinin tüketeceği doğrulanmış bir veri
> sözleşmesi kurmak. **Bu sprintte YOK**: spatial interpolation, IDW,
> kriging, Delaunay gridding, raster resampling, smoothing, PyVista, VTK,
> volume rendering, isosurface, derinlik dönüşümü, hız iş akışı,
> migration, gain, undo/redo, recipe, processed-dataset kaydetme,
> installer, signing, auto-update. Temel karar kaydı:
> [[06_DECISIONS/ADR_017_Actual_XY_CScan_and_No_Interpolation_Policy]].

## Goal

`obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/3D_Volume_Data_Model.md`'nin
planladığı gridding/volume işinin **önkoşulu** olan, gerçek amplitude
C-scan/time-slice görselleştirmesini native GUI'ye eklemek. Sprint 3D-0
`main`'e merge edilmiş durumda (2026-07-20, PR #5, merge commit
`a43d947`); bu sprint o survey-geometri temeli üzerine ilk gerçek
C-scan'i ekliyor — hâlâ hacim/gridding DEĞİL.

## Scope

- `src/archaeogpr/cscan/{__init__,models,compute,validation,export}.py`
  (yeni, Qt import yok) — `CScanAggregation`, `CScanSourceKind`,
  `CScanGeometryView`, `CScanRequest`, `CScanResult`, `CScanStatistics`,
  `compute_cscan()`, `CSCAN_REPORT_SCHEMA_VERSION`,
  `build_cscan_report()`/`export_cscan_report()`.
- `src/archaeogpr/gui/models/cscan_session.py` (yeni) — `CScanState`,
  `CScanSession`, `DatasetSession`/`GeometrySession`'dan bağımsız.
- `src/archaeogpr/gui/models/cscan_display_settings.py` (yeni) —
  `CScanDisplaySettings`, `compute_cscan_display_levels()`,
  `symmetric_levels_allowed()`.
- `src/archaeogpr/gui/workers/cscan_worker.py` (yeni) — `CScanWorker`,
  `FileLoadWorker`/`ProcessingWorker`'ın aynı `QObject`+`moveToThread`
  deseni.
- `src/archaeogpr/gui/views/cscan_view.py` (yeni) — C-scan/Time Slice
  render widget'ı (iki geometry view, seçim senkronizasyonu, hover).
- `src/archaeogpr/gui/views/bscan_view.py` — draggable zaman cursor'ı
  (`timeCursorDragged` sinyali, `set_time_cursor()`).
- `src/archaeogpr/gui/export.py` — `export_cscan_png()` eklendi.
- `src/archaeogpr/gui/main_window.py` — `ActiveTaskKind`, C-scan/Time
  Slice dock'u, 3 yönlü mutual exclusion (file load/processing/C-scan),
  trace/channel/zaman senkronizasyonu, File > Export C-scan PNG + JSON.
- `tests/test_cscan.py` (yeni) — 26 test, Qt'siz.
- `tests/test_gui_cscan.py` (yeni) — 39 test, `@pytest.mark.gui`
  (item 26-66, gerçek-dosya entegrasyon testleri dahil).
- Dokümantasyon: bu not, ADR-017, README, Current_Project_State,
  Next_Development_Sprint, Sprint_Index, Decision_Index, GUI_Architecture,
  3D_Volume_Data_Model, Processing_Preview_and_Commit_Model,
  Windows_Executable_Build.
- Version: `0.4.0` → `0.5.0` (minor — yeni kullanıcı-görünür özellik).

## Out of Scope

Spatial interpolation, IDW, kriging, Delaunay gridding, raster resampling,
smoothing, PyVista, VTK, volume rendering, isosurface, derinlik dönüşümü,
hız iş akışı, migration, gain, undo/redo, recipe, processed dataset
kaydetme, installer, signing, auto-update. İki geometry view (actual X/Y
ve derived s/c) birbirine asla resample edilmiyor/harmanlanmıyor —
bkz. ADR-017 Decision 6.

## Input Data

`data/raw/Swath003_Array02.ogpr` (gerçek dosya, shape `(175, 11, 1024)`)
+ `tests/conftest.py`'deki `ogpr_builder`/`dataset_factory` fixture'ları
(yeniden kullanıldı). Yeni yardımcılar: `_make_real_geolocation_dataset`,
`_load_dataset`, `_select_geometry_view`/`_select_aggregation`,
`_compute_and_wait`, `_GatedCompute` (`test_gui_processing.py`'nin
`_GatedApply` deseninin cscan karşılığı, cross-file coupling'den
kaçınmak için yerel kopya).

## Tasks

- [x] Repository doğrulandı (`main` @ `a43d947`, Sprint 3D-0 merge
  commit'i, temiz).
- [x] Eski `sprint-3d-0-geometry-inspector` yerel dalı (main'e tam merge
  edildiği doğrulandıktan sonra) güvenle kaldı; yeni
  `sprint-3d-1-actual-xy-cscan` branch'i `main`'den açıldı.
- [x] C-scan/time-axis audit'i yapıldı (doğrudan kod okuması):
  `GPRDataset.amplitudes` şekli `(slice, channel, sample)` — "trace"
  harici (DatasetSession/SurveyGeometry) sözlüğü, gerçek bir tutarsızlık
  değil; `GPRDataset`'te mask alanı yok, tek mask
  `ProcessingResult.valid_mask` `(channel_count, sample_count)`
  (kanal-bazlı, trace-bazlı DEĞİL); `time_ns` time-zero-relative olduğu
  için negatif olabiliyor (bkz. ADR-004) — C-scan zaman penceresi bunu
  hesaba katmalı.
- [x] Qt-free `archaeogpr.cscan` paketi yazıldı (models/compute/
  validation/export) — geometri paketinin aksine mevcut hiçbir
  fonksiyonu yeniden kullanmıyor, çünkü hiçbir önceki modül zaman
  örneği/penceresi seçip amplitude agregasyonu yapmıyordu.
- [x] `CScanSession` yazıldı, stale-result koruması (source/geometry
  revision snapshot karşılaştırması) dahil.
- [x] `CScanWorker` yazıldı, `FileLoadWorker`/`ProcessingWorker`'ın
  QObject+moveToThread deseninin birebir aynısı.
- [x] `ActiveTaskKind` eklendi — mevcut `is_loading`/`is_processing`'i
  DEĞİŞTİRMEDEN, üçüncü bir `is_computing_cscan` ile birlikte 3 yönlü
  mutual exclusion.
- [x] C-scan/Time Slice dock'u (Request/Display/Export bölümleri +
  `CScanView`) `MainWindow`'a entegre edildi.
- [x] Actual X/Y point-map (`pg.ScatterPlotItem`) ve derived s/c
  parameter-grid (`pg.ImageItem`, transpose doğrulandı) render'ı yazıldı.
- [x] B-scan zaman cursor'ı + trace/channel/zaman senkronizasyonu
  (B-scan/A-scan/Plan View/C-scan arasında iki yönlü) tamamlandı.
- [x] `CScanDisplaySettings` + PNG/JSON export (atomik, `no_interpolation:
  true`) yazıldı.
- [x] Version `0.5.0`'a yükseltildi.
- [x] 26 domain testi yazıldı (`tests/test_cscan.py`) — bir hesaplama
  hatası (test'in kendisinde) yazım sırasında yakalanıp düzeltildi.
- [x] 39 GUI testi yazıldı (`tests/test_gui_cscan.py`, item 26-66) —
  yazım/doğrulama sırasında 2 gerçek production hatası + 3 test hatası
  bulunup düzeltildi (bkz. Issues Discovered).
- [ ] Final doğrulama: ruff/mypy/core/gui/cscan-filtered/vault validator
  (bkz. görev #287).
- [ ] Executable `0.5.0` olarak build edilecek, yeni ZIP oluşturulacak
  (bkz. görev #288).

## Acceptance Criteria

Kullanıcının orijinal talimatındaki 47. bölüm ("Son Rapor") maddelerinin
tamamı — bkz. bu sprintin sonuç raporu (kullanıcıya sunulan mesaj).

## Implementation Notes

### `archaeogpr.cscan`: geometri paketinin aksine, gerçekten yeni matematik

Sprint 3D-0'ın `archaeogpr.geometry`'si mevcut `compute_trace_spacing()`/
`compute_cross_channel_spacing_m()`'i yeniden kullanıyordu.
`archaeogpr.cscan` için böyle bir öncül fonksiyon yok — `compute_cscan()`
bu projede ilk kez bir zaman örneği/penceresi seçip amplitude'ları
agregasyon eden kod. Qt/pyqtgraph'a VE `archaeogpr.geometry`'ye hiç
bağımlı değil — C-scan değer gridi yalnızca amplitude/zamanın bir
fonksiyonu, koordinatların değil. Detay: ADR-017 Decision 1.

### `CScanAggregation`: tek işaretli seçim, üç negatif-olmayan pencere

`SINGLE_SAMPLE` (en yakın örneğin gerçek işaretli genliği) dışında bilinçli
olarak işaretli bir pencere-ortalaması YOK — pozitif/negatif yarım-döngü
iptali güçlü bir yansımanın tam üzerinde yanlışlıkla küçük bir değer
üretebilir. `RMS`/`MEAN_ABSOLUTE`/`MAXIMUM_ABSOLUTE` bu yüzden yapısal
olarak negatif değil. Detay: ADR-017 Decision 2.

### Half-open zaman penceresi: kırp-ve-uyar vs tamamen-reddet

`[center-width/2, center+width/2)` — `time_ns`'in (time-zero-relative,
negatif olabilen) ekseni üzerinde doğrudan boolean maskeleme.
Kısmi taşma sessizce kırpılır + kullanılan gerçek aralığı adlandıran bir
uyarı; TAMAMEN aralık dışıysa `CScanError`. `time_ns` monotonluğu
`compute_cscan()` içinde BAĞIMSIZ doğrulanıyor — herhangi bir geometry
readiness gate'ine değil, çünkü C-scan gerçek X/Y point grid üzerinde
`rectilinear_cscan_ready=False` olsa bile çalışmalı (gerçek dosyada olduğu
gibi). Detay: ADR-017 Decision 3.

### İki katmanlı geçerlilik: kanal-bazlı yapısal mask + gerçekten hücre-bazlı mask

`compute_cscan()`'e verilen `valid_mask` `(channel_count, sample_count)`
(ProcessingResult ile aynı şekil) ama `CScanResult.valid_mask`
`(trace_count, channel_count)` — gerçekten hücre-bazlı, çünkü tek bir
trace'in kendi genliği non-finite olabilir kanal/örnek nominal geçerliyken
bile. Detay: ADR-017 Decision 4.

### İki geometry view, asla birbirine resample edilmez

`ACTUAL_XY_POINT_MAP` (varsayılan, gerçek `x_coordinates`/`y_coordinates`,
tek vektörel `pg.ScatterPlotItem`, "no interpolation" etiketi) vs
`DERIVED_PARAMETER_GRID` (idealize `along_track_coordinates`/
`cross_track_offsets`'ten broadcast edilmiş grid, `pg.ImageItem`,
`values.T` transpose — `plan_view`'daki `_acquisition_point_grid()`'in
aksine gerçek x/y varsa bile ASLA onun yerine geçmiyor, çünkü bu view'ın
tüm amacı ilk view'dan yapısal olarak ayrı kalmak). İki view'ın hangisinin
kullanılabilir olduğu, adlandırılmış bir readiness gate kontrolüyle değil,
altta yatan koordinat dizilerinin (x/y veya along/cross) var olup
olmamasıyla doğal olarak belirleniyor — ADR-016'nın gate mantığını GUI
katmanında tekrarlamaktan daha basit ve senkron dışı kalamaz. Detay:
ADR-017 Decision 5-6.

### `CScanSession`: `GeometrySession`'ın bağımsızlık deseni, ama iki oturuma karşı staleness takibi

`DatasetSession`/`GeometrySession`'a hiç referans tutmuyor — yalnızca
geçmiş bir compute'un kullandığı revision'ların bir anlık görüntüsü,
`MainWindow` tarafından canlı revision'lara karşı karşılaştırılıyor
(`ProcessingWorker`'ın `base_revision` deseninin aynısı). Başarısızlık/
iptal SADECE `state`/`error`'ı günceller — son geçerli sonuç ekranda
kalır, "Stale"/"Cancelled"/"Failed" olarak yeniden etiketlenir (projenin
"kullanıcıyı haberdar et, gizleme" felsefesi — CRS-unverified etiketleriyle
aynı). Implementasyon sırasında yakalanan gerçek bir boşluk: Preview
kaynağının staleness takibi başta `preview_base_revision` kullanıyordu,
ama aynı base revision'da farklı parametrelerle yeniden preview yapmayı
yakalayamıyordu — `id(session.preview_dataset)`'e geçilerek düzeltildi
(şema değişikliği yok, `CScanRequest.source_revision`'ın mevcut `int`
tipine uyuyor). Detay: ADR-017 Decision 7.

### `CScanWorker`: `FileLoadWorker`/`ProcessingWorker`'ın birebir yapısal aynısı

`QObject`+`moveToThread` (asla `QThread` alt sınıfı), token-bazlı
stale-result reddi, kooperatif `threading.Event` iptali, temizlik SADECE
`_on_cscan_thread_finished`'da (`thread.finished`'a bağlı, asla bir sonuç
handler'ında). Detay: ADR-017 Decision 8; ADR-014/ADR-015.

### `ActiveTaskKind`: yeni bir convenience enum, mevcut gate'lerin yerine geçmiyor

Üçüncü bir arka plan görevi (C-scan compute) katıldığında,
`is_loading`/`is_processing`'i tek bir state machine'e dönüştürmek yerine,
her ikisi de bağımsız/otoriter kalıyor; `active_task_kind` bunların üstüne
saf türetilmiş bir property. Her busy-state guard'ı (dosya yükleme,
processing başlatma, geometry apply, C-scan compute, close/shutdown) aynı
`self._close_pending or self.is_loading or self.is_processing or
self.is_computing_cscan` deseniyle genişletildi. Bir test tarafından
yakalanan gerçek bir eksiklik: `open_path()` blanket bir `if A or B or C:`
satırı değil ayrı `if` blokları kullandığı için yeni C-scan guard'ı ilk
seferde atlandı — `test_file_load_rejected_during_cscan_compute`
düzeltti. Detay: ADR-017 Decision 9.

### Export: PNG + JSON, atomik, geometri export'unun deseni

`archaeogpr.cscan.export`, `gui/export.py`'nin eski, atomik-olmayan
`.display.json` deseni yerine `archaeogpr.geometry.export`'un
şema-versiyonlu/`source_sha256`/atomik-yazma desenini takip ediyor.
Yazım sırasında bulunan gerçek bir hata: `export_cscan_png()`'nin atomik
temp dosyası `.tmp` uzantılı olduğu için matplotlib'in `savefig()`'i format
çıkarımı yapamıyor, `ValueError: Format 'tmp' is not supported` fırlatıyordu
— `format="png"` açıkça geçilerek düzeltildi. Detay: ADR-017 Decision 10.

### Test yazarken bulunan sorunlar (2 gerçek production hatası, 3 test hatası)

1. **Gerçek production hatası**: `open_path()`'te eksik
   `is_computing_cscan` guard'ı (yukarıda, ActiveTaskKind notunda
   detaylandırıldı).
2. **Gerçek production hatası**: `export_cscan_png()`'de matplotlib format
   çıkarımı hatası (yukarıda, Export notunda detaylandırıldı) —
   `test_export_produces_png_and_json` ve
   `test_real_ogpr_hash_and_mtime_unchanged_by_cscan_operations` bunu
   yakaladı.
3. **Test hatası**: `test_cscan.py::test_negative_time_axis_sample_selection`
   yanlış elle hesaplanmış bir indeks bekliyordu (`14` yerine doğrusu
   `2`) — çalıştırılmadan önce elle yeniden hesaplanarak yakalandı ve
   düzeltildi.
4. **Test hatası**: `_CScanThreadRecorder` düz bir sınıf olarak
   yazılmıştı; `_ProcessingThreadRecorder`'ın (QueuedConnection'ın doğru
   çözülmesi için) `QObject` alt sınıfı olması gerektiği emsaliyle
   uyuşmuyordu — `test_result_handler_runs_on_qt_main_thread` bunu
   yakaladı, `QObject`'ten miras alınarak düzeltildi.
5. **Test hatası**: `test_trace_channel_change_updates_cscan_highlight`
   3-trace'lik varsayılan `ogpr_builder` fixture'ında (geçerli indeksler
   0-2) trace indeksi 3 seçiyordu — `clamp_trace(3)` bunu 2'ye kırpıyordu,
   assertion `== 3` başarısız oluyordu. Hemen altındaki kardeş test
   (`test_plan_view_synchronization_preserved`) zaten aynı fixture için
   doğru indeks 2'yi kullanıyordu; aynı düzeltme uygulandı.

Ayrıca iki test (`test_export_produces_png_and_json`,
`test_real_ogpr_hash_and_mtime_unchanged_by_cscan_operations`) ve
savunma amaçlı iki test daha (`test_shutdown_pending_rejects_cscan_
compute_and_export`, ve zaten güvenli olan bir üçüncüsü) eksik
`no_blocking_dialogs` fixture'ı yüzünden gerçek, mock'suz bir
`QMessageBox.critical`/`.warning` çağrısının offscreen test ortamında
sonsuza kadar bloke olma riskini taşıyordu (ADR-015/ADR-016'da zaten
belgelenen aynı tuzak) — hepsine fixture eklendi.

## Validation Results

| Kontrol | Sonuç |
|---|---|
| `pytest tests/test_cscan.py` (Qt'siz, `-W error`) | ✅ 26 passed |
| `pytest tests/test_gui_cscan.py` (`-m gui`, offscreen, `-W error`) | ✅ 39 passed |
| `ruff format --check .` / `ruff check .` | (görev #287 sonrası kesinleşecek) |
| `mypy src/archaeogpr` | (görev #287 sonrası kesinleşecek) |
| `pytest -m "not gui"` (tam çekirdek takım) | (görev #287 sonrası kesinleşecek) |
| `pytest -m gui` (tam GUI takımı) | (görev #287 sonrası kesinleşecek) |
| Vault validator | (görev #287 sonrası kesinleşecek) |

### Yeni testler

| Dosya | Test sayısı | Kapsam |
|---|---|---|
| `tests/test_cscan.py` (Qt'siz) | 26 | aggregation matematiği (RMS/mean-absolute/maximum-absolute/single-sample), half-open pencere seçimi (kırpma/tam-red/negatif eksen), bağımsız monotonluk kontrolü, mask/NaN/overflow güvenliği, request validasyonu, sonuç immutability, JSON export (şema, no_interpolation, hash, NaN-safe) |
| `tests/test_gui_cscan.py` (`@pytest.mark.gui`) | 39 | dock oluşturma, iki geometry view'ın etiket/render'ı (gerçek dosyanın rectilinear/CRS uyarıları dahil), GUI thread dışında compute, 3 yönlü mutual exclusion, cancel/stale/failed sonuç koruması, trace/channel/zaman-cursor senkronizasyonu, display settings, Raw/Current/Preview kaynak davranışı, PNG+JSON export (başarı/stale-red/shutdown-pending-red), deferred close, raw dosya değişmezliği |

## Generated Outputs

Bu sprint `outputs/`'a hiçbir dosya yazmadı (GUI kodu/test). `dist/ArchaeoGPR/`
`0.5.0` olarak build edilecek (görev #288); yeni ZIP:

- Yol: `C:\Dev\ArchaeoGPR-Releases\ArchaeoGPR-0.5.0-win64.zip`
- Boyut: (sonuç raporunda kesin değer)
- SHA-256: (sonuç raporunda kesin değer)

Eski `0.1.0`-`0.4.0` ZIP'leri değiştirilmedi/silinmedi.

## Issues Discovered

Bkz. Implementation Notes "Test yazarken bulunan sorunlar" — özet: 2 gerçek
production hatası (`open_path()`'te eksik C-scan busy-state guard'ı;
`export_cscan_png()`'de matplotlib format-çıkarımı hatası) ve 3 test yazım
hatası (bir hesaplama hatası, bir eksik `QObject` mirası, bir off-by-one
trace indeksi) bulunup düzeltildi. Ayrıca üç test dosyasına savunma amaçlı
`no_blocking_dialogs` fixture'ı eklendi (gerçek bir hataya karşı değil,
zaten bilinen bir offscreen-hang tuzağına karşı önlem).

## Decisions

1. `archaeogpr.cscan` Qt-free paketi genuinely yeni matematik — geometri
   paketinin aksine mevcut bir fonksiyonu yeniden kullanmıyor.
2. `SINGLE_SAMPLE` tek işaretli aggregation; `RMS`/`MEAN_ABSOLUTE`/
   `MAXIMUM_ABSOLUTE` yapısal olarak negatif değil; işaretli pencere
   ortalaması kasıtlı olarak yok.
3. Half-open `[start, stop)` zaman penceresi; kısmi taşma kırpma+uyarı,
   tam taşma hata; monotonluk kontrolü geometry gate'lerinden bağımsız.
4. `CScanResult.valid_mask` gerçekten hücre-bazlı `(trace_count,
   channel_count)` — `ProcessingResult.valid_mask`'tan farklı bir şekil.
5. İki geometry view (actual X/Y, derived s/c) asla birbirine resample
   edilmez/karıştırılmaz; kullanılabilirlik altta yatan koordinat
   dizilerinin varlığından doğal olarak türetilir.
6. `CScanSession`, `DatasetSession`/`GeometrySession`'dan bağımsız;
   başarısızlık/iptal son geçerli sonucu korur, yalnızca etiketler.
7. Preview kaynağı staleness takibi `id(preview_dataset)` kullanıyor,
   `preview_base_revision` değil.
8. `CScanWorker`, `FileLoadWorker`/`ProcessingWorker`'ın birebir aynı
   QObject+moveToThread deseni.
9. `ActiveTaskKind` mevcut `is_loading`/`is_processing`'in yerine
   geçmeyen, saf türetilmiş bir convenience enum; 3 yönlü mutual
   exclusion mevcut fonksiyonel guard deseniyle genişletildi.
10. C-scan export'u geometri export'unun şema-versiyonlu/atomik desenini
    takip ediyor; `no_interpolation: true` her zaman kaydediliyor.

## Manuel Kabul Turu 1 — BAŞARISIZ: Dock-Layout Regresyonu (2026-07-20)

Kullanıcının manuel kabul denemesi bir dock-layout regresyonu nedeniyle
**BAŞARISIZ** oldu: Processing dock'u sol/merkez alanın üzerine taşıyor,
C-scan dock'u Processing/merkez grafikler/sağ dock'un üzerine biniyor, dock
başlıkları sıkışıyordu. **Manuel kabul bu ekran görüntüsü nedeniyle henüz
tamamlanmadı** — düzeltilmiş build'e karşı yeniden yapılmalı.

**Not (2026-07-20, sonradan eklendi):** bu turun ardındaki dock-layout
düzeltmesi ve Manuel Kabul Turu 2'nin settings-isolation düzeltmesi
tamamlandıktan sonra, kullanıcı düzeltilmiş build'e karşı manuel kabulü
tekrarladı ve onayladı — bkz. aşağıdaki "Manual Visual Acceptance" bölümü.

Root-cause audit'i (kod değiştirilmeden yapıldı) bunun kalıcı-state değil
**construction-time default-layout hatası** olduğunu buldu: `MainWindow`'da
hiç `saveState`/`restoreState`/`QSettings` yoktu; her açılışta aynı bozuk
sabit düzen kuruluyordu. Asıl neden: sol ve sağ kolonlarda
`splitDockWidget(..., Vertical)` ile üst üste dikey yığılmış, scroll-area'sız
dört uzun form paneli — her panelin doğal minimum yüksekliği kolon
yüksekliğinin yarısını aştığı için C-scan dock'u eklendiğinde Qt'nin dock
layout'u over-constrained kaldı. Düzeltme ve kalıcı mimari karar:
[[06_DECISIONS/ADR_018_Versioned_Dock_Layout_and_Reset_Policy]] — özetle:

- Üç tabified çift (Dataset+Processing sol, Metadata+Survey Geometry sağ,
  Plan View+C-scan alt — tam genişlik), merkezde yalnızca B-scan/A-scan.
- Her dock'a benzersiz `objectName`; `setDockNestingEnabled(True)` + açık
  corner sahipliği.
- Versiyonlu window-state kalıcılığı (`window_state.py`,
  `WINDOW_STATE_SCHEMA_VERSION = 1`, ayrı INI dosyası) — şema uyuşmazlığı/
  bozuk state/ekrana-sığmayan geometri/kaydedilenden-küçük pencere
  durumlarının tümü deterministik default layout'a düşer.
- View → Reset Window Layout komutu.
- Processing/Survey Geometry/C-scan panelleri `QScrollArea` ile sarıldı.
- Floating dock desteklenmiyor (zaten örtük olarak yoktu; artık açık karar
  — bkz. ADR-018 Decision 5).
- 27 yeni dock-layout GUI testi (`tests/test_gui_dock_layout.py`) — gerçek
  geometri-kesişim assertion'ları, 1280×800 ve 1366×768'de doğrulandı.

Aynı turda Section-11 C-scan sertleştirmeleri de tamamlandı (bilimsel
matematik değişmedi — bkz. ADR-017 Addendum): `id(preview_dataset)` yerine
monotonic `preview_generation` sayacı; geometry-view combo item'larının
adlandırılmış readiness gate'lerine bağlanması; center-time değişince
B-scan cursor'unun anında güncellenmesi; form değişince sonucun "Stale
(parameters changed)" etiketlenmesi (otomatik compute asla başlamaz);
merkezi `can_start_background_task` start-karar property'si; export
partial-failure semantiği (JSON sidecar başarısız olursa PNG geri alınır);
1×N/N×1/1×1 degenerate shape testleri; pip metadata'sının 0.5.0'a
yenilenmesi. +8 yeni test (3 domain + 5 GUI).

## Manuel Kabul Turu 2 — commit-öncesi durduruldu: Settings-Isolation Riski (2026-07-20, aynı gün)

Dock-layout düzeltmesinin kendisi ("Manuel Kabul Turu 1" bölümündeki 6 madde
+ Section-11 C-scan sertleştirmeleri) kabul edildi. Ancak commit/manuel kabul
öncesinde **release-blocking bir ikinci sorun** bulundu: önceki raporun
kendisi, `test_gui.py`'nin bazı eski testlerinin, executable'ın
`--smoke-test` modunun, ve `build_windows.ps1`'in gerçek kullanıcı dosyasını
(`%LOCALAPPDATA%\ArchaeoGPR\window_state.ini`) okuyabileceğini/
yazabileceğini itiraf ediyordu — otomatik doğrulamanın gerçek bir
kullanıcının kaydettiği pencere düzenini ezmesi, dock düzeninin kendisi
doğru olsa bile kabul edilemez.

Düzeltme, tam mimari kararı için bkz.
[[06_DECISIONS/ADR_018_Versioned_Dock_Layout_and_Reset_Policy]] "Addendum:
Settings Isolation for Automated Verification" — özetle:

- `open_window_settings()`'e `path_override`/`ephemeral` parametreleri;
  `MainWindow`'a `persist_window_state`/`window_settings_factory` keyword-only
  parametreleri.
- `--smoke-test` artık her ikisini birlikte kullanıyor (persist=False +
  ephemeral factory) — gerçek dosya ne okunuyor ne yazılıyor.
- `ARCHAEOGPR_WINDOW_STATE_PATH` env override — `build_windows.ps1`'in
  subprocess smoke test'i ve `tests/conftest.py`'nin yeni autouse
  `_isolate_gui_window_state` fixture'ı (yalnızca `test_gui_dock_layout.py`
  değil, **tüm** `@pytest.mark.gui` test koleksiyonu) tarafından kullanılıyor.
- `build_windows.ps1`'e preflight kontrolü (çalışan bir ArchaeoGPR.exe
  instance'ı varsa net bir hatayla dur, asla otomatik kill yapma) + gerçek
  `window_state.ini`'nin smoke test öncesi/sonrası SHA-256/boyut'unun (veya
  yokluğunun) birebir aynı kaldığını kanıtlayan bir doğrulama eklendi.
- Reset Window Layout yalnızca aktif (injected/ephemeral veya gerçek)
  backend'i temizliyor — asla başka bir settings store'a dokunmuyor.
- 18 yeni test (`tests/test_gui_window_state.py`).

## Manual Visual Acceptance

Manual acceptance was confirmed by the user for the native Windows v0.5.0
build.

User acceptance covered:

- The default dock layout no longer overlaps.
- Dataset and Processing are tabified.
- Metadata and Survey Geometry are tabified.
- Plan View and C-scan / Time Slice are tabified.
- Long dock contents scroll within their dock boundaries.
- View → Reset Window Layout works.
- The window layout persists across normal application restarts.
- The C-scan / Time Slice panel opens and is usable.
- Actual X/Y point-map and Derived s/c parameter-grid modes are
  distinguishable.
- No obvious QThread, QLayout, RuntimeWarning or Traceback error was
  observed.
- Raw OGPR files remained unchanged.

This is a user acceptance statement. The interactive steps were not
executed or observed by Claude and must not be presented as
automated-test evidence.

Bu kabul, Manuel Kabul Turu 1 (dock-layout regresyonu) ve Manuel Kabul
Turu 2'nin (settings-isolation riski) her ikisinin de düzeltildiği build'e
karşı yapıldı. `main`'e merge henüz gerçekleşmedi — bu commit/push turu
yalnızca feature branch'i günceller.

## Completion Summary

Manuel kabul turu 1 dock-layout regresyonu nedeniyle, turu 2
settings-isolation riski nedeniyle commit-öncesi durduruldu; her iki
düzeltme de tamamlandı ve yukarıdaki "Manual Visual Acceptance" bölümünde
kaydedilen kullanıcı beyanıyla kabul edildi. Sprint'in kod/test/dokümantasyon
kapsamı tamamlandı; `main`'e merge ve PR açma bu sprintin bir sonraki,
henüz gerçekleşmemiş adımıdır.

## Next Sprint Recommendation

Kullanıcının kendi isteğiyle: bu sprintin bilinçli olarak temelini attığı
ama implemente etmediği PyVista/VTK volume rendering, gridding/resampling,
derinlik dönüşümü (bkz. [[03_ARCHITECTURE/3D_Volume_Data_Model]]), gain,
undo/redo stack, recipe sistemi, veya processed dataset kaydetme.

## İlgili Notlar

[[06_DECISIONS/ADR_017_Actual_XY_CScan_and_No_Interpolation_Policy]],
[[06_DECISIONS/ADR_018_Versioned_Dock_Layout_and_Reset_Policy]],
[[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]],
[[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]],
[[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]],
[[03_ARCHITECTURE/3D_Volume_Data_Model]],
[[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]],
[[03_ARCHITECTURE/GUI_Architecture]],
[[02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector]],
[[02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply]],
[[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]],
[[09_REFERENCES/Windows_Executable_Build]], [[02_SPRINTS/Sprint_Index]]
