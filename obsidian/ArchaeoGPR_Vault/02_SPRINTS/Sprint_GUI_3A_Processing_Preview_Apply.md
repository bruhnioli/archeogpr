---
type: sprint
tags: [sprint, gui]
sprint: GUI-3A
status: done
started: 2026-07-19
completed: 2026-07-19
---

# Sprint GUI-3A — Non-Destructive Processing Preview & Apply

> **Kapsam:** Mevcut ve testlerle doğrulanmış 5 stabil `processing/*.py`
> fonksiyonunu (time-zero, DC offset, dewow, band-pass, background
> removal) native GUI'ye **güvenli, iptal edilebilir ve non-destructive**
> bir preview→apply akışıyla bağlamak. **3D, gain, migration, depth
> conversion, recipe, processed dataset dosyaya kaydetme, undo/redo stack
> bu sprintte YOK.** Temel karar kaydı:
> [[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]].

## Goal

`obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/Processing_Preview_and_Commit_Model.md`
(Sprint GUI-0'da yazılan, "tasarım — henüz implemente edilmedi" olarak
işaretli belge)'nin registry + preview/apply bölümünü hayata geçirmek —
undo/redo stack ve recipe sistemi HARİÇ. GUI-0/GUI-1/GUI-2/GUI-1B
`main`'e merge edilmiş durumda (2026-07-18, PR #2 ve #3); bu sprint o
temel üzerine processing entegrasyonunu ekliyor.

## Scope

- `src/archaeogpr/gui/models/dataset_session.py` — raw/current/preview
  ayrımı, `current_valid_mask`/`preview_valid_mask`,
  `current_revision`/`preview_base_revision`, `has_fresh_preview`,
  `set_preview`/`discard_preview`/`apply_preview`/`reset_to_raw`.
- `src/archaeogpr/gui/processing/{__init__,models,registry,adapters}.py`
  (yeni) — `ParameterSpec`, `ProcessingOperationSpec`, 5 operation'ın
  registry kaydı ve adapter fonksiyonları. Qt import YOK.
- `src/archaeogpr/gui/workers/processing_worker.py` (yeni) —
  `ProcessingWorker` (QObject + worker-thread), `ProcessingState` enum.
- `src/archaeogpr/gui/main_window.py` — Processing dock (operation combo,
  parametre formu, Preview/Apply/Discard/Cancel/Reset-to-Raw, display
  source Raw/Current/Preview, history listesi), busy-state mutual
  exclusion (file load ↔ processing), deferred-close processing'e de
  uygulandı.
- `tests/test_gui_processing.py` (yeni) — 48 test, `@pytest.mark.gui`.
- Dokümantasyon: bu not, ADR-015, README, Current_Project_State,
  Next_Development_Sprint, Sprint_Index, Decision_Index, GUI_Architecture,
  Processing_Preview_and_Commit_Model (durum güncellemesi),
  Windows_Executable_Build.
- Version: `0.2.1` → `0.3.0` (minor — yeni kullanıcı-görünür özellik).

## Out of Scope

Gain, AGC, SEC gain, exponential gain, migration, depth conversion,
velocity fitting, hyperbola picking, C-scan, 3D, PyVista, VTK, volume
rendering, undo/redo stack, recipe sistemi, batch processing, processed
NPZ save, installer, code signing, auto-update. Time-zero'nun `"manual"`
metodu (kanal-başına pick girişi) ve band-pass'ın `"ormsby"` metodu da bu
sprint kapsamı dışında bırakıldı (bkz. ADR-015 Decision madde 3) — farklı
bir form şekli gerektirdikleri için kasıtlı olarak ertelendi, sessizce
atlanmadı.

## Input Data

`data/raw/Swath003_Array02.ogpr` (gerçek dosya, ~8 MB) +
`tests/conftest.py`'deki `dataset_factory`/`ogpr_builder` fixture'ları
(yeniden kullanıldı). Yeni yardımcılar: `_GatedApply` (bir operation
spec'inin `apply` çağrısını kontrollü biçimde bloklayan sahte fonksiyon,
`_GatedReader`'ın processing eşdeğeri), `_ProcessingThreadRecorder`
(`_ThreadRecorder`'ın processing eşdeğeri), `_spec_with_apply` (registry'yi
hiç mutasyona uğratmadan, tek seferlik bir `ProcessingOperationSpec`
kopyası üreten yardımcı).

## Tasks

- [x] Repository doğrulandı (`main` @ `870f0c8`, temiz).
- [x] `sprint-gui-3a-processing-preview-apply` branch'i `main`'den açıldı.
- [x] Eski `sprint-gui-1b-background-tasks` yerel branch'i (main'e tam
  merge edildiği doğrulandıktan sonra) güvenle silindi.
- [x] Processing API audit yapıldı (Explore agent + doğrudan kod okuması)
  — 5 fonksiyonun gerçek imzaları, `ProcessingResult`/`GPRDataset`
  sözleşmeleri, `valid_mask` semantiği, `time_ns` davranışı, NaN/gain
  durumu doğrulandı.
- [x] `DatasetSession` raw/current/preview modeliyle genişletildi;
  geriye dönük uyumluluk için `dataset` property + setter korundu.
- [x] Processing registry/adapters/models yazıldı (5 operation).
- [x] `ProcessingWorker` + `ProcessingState` yazıldı (ADR-014 deseni
  yeniden kullanıldı, 2 fark eklendi — bkz. ADR-015).
- [x] `MainWindow`'a Processing dock'u ve tüm handler'lar eklendi; busy-
  state mutual exclusion, deferred-close processing'e genişletildi.
- [x] Version `0.3.0`'a yükseltildi.
- [x] 48 yeni GUI testi yazıldı; yazım sırasında gerçek bir test hatası
  bulundu ve düzeltildi (bkz. Issues Discovered).
- [x] Final doğrulama: ruff/mypy/core/gui/vault validator.
- [x] Executable `0.3.0` olarak build edildi, yeni ZIP oluşturuldu.

## Acceptance Criteria

Kullanıcının orijinal talimatındaki 40. bölüm ("Son Rapor Formatı")
maddelerinin tamamı — bkz. bu sprintin sonuç raporu (kullanıcıya sunulan
mesaj).

## Implementation Notes

### Üç ayrı dataset: raw / current / preview — undo/redo stack değil

`DatasetSession` artık tek bir `dataset` alanı yerine `raw_dataset`,
`current_dataset`, `preview_dataset` tutuyor (+ `current_revision`,
`preview_base_revision`, `current_valid_mask`/`preview_valid_mask`).
`dataset` bir property olarak korundu (setter dahil) — GUI-1/GUI-2/GUI-1B
kodu ve `tests/test_gui.py`'nin **hiçbiri** değiştirilmeden çalışmaya
devam ediyor. Bu, orijinal tasarım belgesindeki `SessionState{states:
list[DatasetState], cursor: int}` tam undo/redo modeli DEĞİL —
`reset_to_raw()` doğrudan ham veriye döner, adım adım geri gitmez. Detay:
[[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]] Decision
madde 1.

### `valid_mask` zincirleme: CLI'nin kendi `sprint2` pipeline'ıyla aynı desen

`cli.py::_cmd_sprint2`'nin `tz_result.valid_mask`'i doğrudan
`correct_dc_offset(..., valid_mask=tz_result.valid_mask, ...)`'a
geçirdiği doğrulandı (kod okuması ile). GUI aynısını yapıyor:
`current_valid_mask`, her `apply_preview()`'dan sonra o operation'ın
`ProcessingResult.valid_mask`'i olarak güncelleniyor ve bir sonraki
preview'e otomatik geçiriliyor — kullanıcı bunu elle girmiyor. Detay:
ADR-015 Decision madde 2.

### Registry + adapter katmanı: gerçek fonksiyonları asla kopyalamaz

`src/archaeogpr/gui/processing/adapters.py`'deki her `apply_*` fonksiyonu
yalnızca GUI parametre dict'ini gerçek fonksiyonun gerçek keyword
argümanlarına çeviriyor ve `ProcessingResult`'ı olduğu gibi döndürüyor.
İki kasıtlı kapsam daraltması: time-zero'nun `"manual"` metodu (kanal-
başına pick girişi farklı bir form şekli gerektirir) ve band-pass'ın
`"ormsby"` metodu (4-köşe-frekans tasarımı) bu panelde YOK — yalnızca
otomatik time-zero metodları ve Butterworth band-pass. Band-pass'ın
Nyquist kontrolü, `processing/bandpass.py::_nyquist_mhz`'in birebir aynı
ifadesiyle (satır satır kopyalanmış, import edilmemiş — o modülün private
bir helper'ı) hesaplanıyor, böylece GUI'nin ön-kontrolü gerçek fonksiyonla
asla çelişmiyor. Detay: ADR-015 Decision madde 3.

### `ProcessingWorker`: ADR-014'ün deseni, iki ek fark

`FileLoadWorker`'ın QObject+moveToThread+`threading.Event`+token+
`thread.finished`-cleanup deseni **aynen** yeniden kullanıldı. İki fark:
(1) her terminal sinyal `base_revision` de taşıyor — committed dataset'in
bu worker başlatıldığından beri değişip değişmediğini kontrol etmek için
(token tek başına yalnızca "daha yeni bir istek bunu geçersiz kıldı mı"yı
yakalar, "temel veri değişti mi"yi yakalamaz); (2) başarı sinyali
`preview_ready` — asla `DatasetSession.current_dataset`'e dokunmuyor,
yalnızca Apply Preview commit ediyor. Ayrı bir ADR-016 oluşturulmadı —
bunlar ADR-014'ün zaten belgelenmiş kararlarına ek/genişletme, yeni bir
mimari karar değil. Detay: ADR-015 Decision madde 4.

### Busy-state: iki paralel state machine, tek birleşik BusyState değil

`FileLoadState` (ADR-014) hiç değiştirilmedi. `ProcessingState`
(`IDLE`/`RUNNING`/`CANCELLING`/`SUCCESS`/`ERROR`/`CANCELLED`) onun tam
aynı şeklini taşıyan, ayrı bir enum. `is_loading` ve `is_processing`
birbirini karşılıklı olarak engelliyor (`open_path()` ve
`_on_preview_clicked()`/`_start_processing_preview()` ikisini de
kontrol ediyor), tek paylaşılan kapı `_close_pending`. Detay: ADR-015
Decision madde 5.

### Parametre değişince veya operation değişince preview otomatik discard edilir

Üçüncü bir "outdated" görsel durum eklemek yerine (yalnızca "No preview /
Computing / Ready / Failed" — 4 durum), herhangi bir parametre alanı veya
operation combo değiştiğinde mevcut preview `discard_preview()` ile
temizleniyor. Detay: ADR-015 Decision madde 6.

### Deferred-close, processing worker'ı da kapsayacak şekilde genişletildi

`closeEvent()` artık `not self.is_loading and not self.is_processing`
kontrolü yapıyor; hangi arka plan işi aktifse onu iptal edip erteliyor
(iki dal da `elif` değil, koşulsuz — mutual exclusion varsayımı ileride
gevşetilse bile doğru kalmaya devam eder). `_on_processing_thread_finished`,
`_on_load_thread_finished`'ın birebir yapısal eşdeğeri. Detay: ADR-015
Decision madde 7.

### Display source ve History paneli: MainWindow'un görüş katmanı, DatasetSession'ın değil

`_display_source` (raw/current/preview) ve `_dataset_for_display()`
yalnızca `MainWindow`'da yaşıyor — `DatasetSession`'ın "şu an ne
gösteriliyor" diye bir fikri yok, yalnızca üç dataset'i takip ediyor.
History paneli gerçek `dataset.processing_history`'yi doğrudan render
ediyor (paralel bir veri yapısı icat edilmedi); preview görüntülenirken
henüz commit edilmemiş adım açıkça "-- PREVIEW, NOT APPLIED" ile
işaretleniyor. Detay: ADR-015 Decision madde 8-9.

### Test yazarken bulunan gerçek hata: `QMessageBox.critical` mock'suz çağrı → sonsuz donma

`test_new_processing_can_start_after_previous_finishes`'in ilk taslağı
aynı `dewow` operasyonunu üst üste iki kez, `allow_repeat_processing`
olmadan çalıştırıyordu. Gerçek fonksiyonun reprocessing guard'ı doğru
şekilde `ProcessingError` fırlattı, worker doğru şekilde `failed` sinyali
yaydı, `MainWindow._on_processing_failed` doğru şekilde bir
`QMessageBox.critical` açtı — ama bu test offscreen ortamda mock'lanmamıştı
ve `test_gui.py`'nin kendi modül docstring'inde zaten belgelenen tuzağa
düştü (tıklanacak hiçbir şey olmadan sonsuza kadar bekleyen modal dialog).
Bu, **üretim kodunda bir hata DEĞİL** — testin ikinci çalıştırma için
farklı bir operation (`dc_offset`, reprocessing guard'ı yok) seçmesiyle
düzeltildi. Detay: Issues Discovered, ADR-015 Validation.

### Disk alanı tükenmesi test çalıştırmalarını 2 kez donuk gösterdi (gerçek kod hatası değil)

Test suite'i ilk çalıştırıldığında sistem diski tamamen doluydu (932GB/
932GB, 0 byte boş) — bu, pytest/Qt G/Ç işlemlerinin donmasına neden oldu.
Kullanıcı disk alanını boşalttıktan sonra (131GB boş alan) testler normal
hızda (48 test ~7 saniyede) çalıştı. Bu, projeye özgü bir hata değildi —
proje dosyaları (`.venv`, `build/`, `dist/`, ZIP'ler) toplam yalnızca
~2.9GB kaplıyor.

## Validation Results

| Kontrol | Sonuç |
|---|---|
| `ruff format --check .` | ✅ 88 dosya zaten formatlı |
| `ruff check .` | ✅ All checks passed |
| `mypy src/archaeogpr` | ✅ 0 hata (59 dosya) |
| `pytest -m "not gui"` | ✅ 318 passed, 26 skipped, 122 deselected, 0 failed |
| `pytest -m gui` (offscreen) | ✅ **122 passed** (74 GUI-1/2/1B + 48 GUI-3A), 344 deselected, 0 failed |
| `archaeogpr.gui --version` | ✅ `0.3.0` |

### Yeni testler (48, `tests/test_gui_processing.py`)

| Bölüm | Test sayısı | Kapsam |
|---|---|---|
| A. Session/model | 8 | raw/current/preview kimliği, atomik apply, revision artışı, discard, reset-to-raw, stale-preview reddi |
| B. Registry/forms | 7 | 5 operation, gain yok, parametre widget'ları, invalid parametre reddi, Nyquist validation, operation değişince form yenilenmesi, parametre değişince preview discard |
| C. Processing worker | 15 | thread affinity, preview-not-commit, runtime hata/cancel session korur, stale token/revision reddi, mutual exclusion (iki yönlü), deferred close, QThread warning yok, shutdown-pending reddi |
| D. Views | 7 | display source seçimi, "not applied" etiketi, Preview seçeneği disabled, time-zero time axis değişimi, apply sonrası metadata/history, channel/trace/display settings korunuyor |
| E. Operation integration | 8 (1 parametrized × 5 + 3) | 5 operation input'u değiştirmiyor, shape/dtype korunuyor, valid_mask zincirleme, gerçek processing_history isimleri |
| F. Frozen smoke | 3 | `--open`/`--smoke-test` panel ile çalışıyor, gerçek OGPR hash/mtime değişmiyor |

## Generated Outputs

Bu sprint `outputs/`'a hiçbir dosya yazmadı (GUI kodu/test). `dist/ArchaeoGPR/`
`0.3.0` olarak build edildi; yeni ZIP:

- Yol: `C:\Dev\ArchaeoGPR-Releases\ArchaeoGPR-0.3.0-win64.zip`
- Boyut: 127,386,930 bayt
- SHA-256: `436A442FEE3FFC8795F553FE7872CC67A0C630C43DDAACF314828F80D9158935`

Eski `0.1.0`/`0.2.0`/`0.2.1` ZIP'leri değiştirilmedi/silinmedi.

## Issues Discovered

1. **Test yazarken: `dewow`'u aynı dataset üzerinde iki kez çalıştırmak
   (reprocessing guard) + mock'suz `QMessageBox.critical` → sonsuz
   offscreen donma** — üretim kodunda hata değil, testin kendisinde.
   Düzeltme: ikinci çalıştırma için `dc_offset` kullanıldı (bkz.
   Implementation Notes).
2. **Disk alanı tükenmesi (kullanıcının sisteminde, proje kaynaklı değil)
   test çalıştırmalarını iki kez donuk gösterdi** — kullanıcı disk
   alanını boşalttıktan sonra testler normal hızda çalıştı. Projenin
   kendi dosyaları (~2.9GB) 932GB'lık diskte küçük bir pay.
3. **mypy: `QAbstractItemModel` üzerinde `.item()` yok** — `QComboBox`'ın
   çalışma zamanındaki gerçek modeli her zaman `QStandardItemModel` ama
   statik tip bunu yansıtmıyor. `typing.cast(QStandardItemModel, ...)`
   ile düzeltildi (yalnızca statik tip daraltması, çalışma zamanı etkisi
   yok).
4. **`_preview_valid_mask` özel alan adı ile `preview_valid_mask` genel
   alan adı arasında bir yeniden adlandırma sırasında tek bir kullanım
   noktası atlandı** (`apply_preview()` içinde) — hemen fark edilip
   düzeltildi, hiçbir zaman commit edilmedi.

## Decisions

1. Raw/current/preview üç ayrı dataset, tam undo/redo stack değil.
2. `current_valid_mask`, CLI'nin `sprint2` pipeline'ıyla aynı desende
   otomatik zincirleniyor.
3. Registry + adapter katmanı gerçek fonksiyonları asla kopyalamıyor;
   time-zero `"manual"` ve band-pass `"ormsby"` bu panelde yok.
4. `ProcessingWorker`, ADR-014'ün worker desenini yeniden kullanıyor +
   `base_revision` stale-base koruması + preview-not-commit sonucu.
5. İki paralel state machine (`FileLoadState`, `ProcessingState`), tek
   birleşik `BusyState` değil — yalnızca `_close_pending` paylaşılıyor.
6. Parametre/operation değişince preview otomatik discard edilir (üçüncü
   "outdated" durumu yerine).
7. Deferred-close, processing worker'ı da kapsıyor (dosya yükleme ile
   aynı desen, koşulsuz iki dal).
8. Display source ve History paneli `MainWindow`'un görüş katmanında;
   `DatasetSession` yalnızca üç dataset'i takip ediyor.

## Manual Visual Acceptance (Kullanıcı Tarafından Doğrulandı)

**Bu bölüm bir otomatik test sonucu DEĞİLDİR** — kullanıcının, derlenmiş
native Windows executable (`dist\ArchaeoGPR\ArchaeoGPR.exe`, `0.3.0`)
üzerinde bizzat gözle ve elle doğruladığı davranışların kaydıdır. Otomatik
pytest sonuçları için bkz. yukarıdaki Validation Results.

Kullanıcı 2026-07-19 tarihinde aşağıdakileri manuel olarak doğruladı:

- Beş desteklenen processing işlemi (time-zero, DC offset, dewow,
  zero-phase band-pass, background removal) Preview ve Apply üzerinden
  çalışıyor.
- Raw, Current ve Preview görünümleri doğru ayrılıyor.
- Preview, Apply edilmeden Current'ı değiştirmiyor.
- Apply, Discard Preview ve Reset Current to Raw çalışıyor.
- Processing history, Apply sonrası güncelleniyor.
- Doğrulama hataları geçersiz bir processing işlemini engelliyor.
- Dosya yükleme (file loading) ve processing birbirini karşılıklı
  dışlıyor.
- Processing iptali (cancellation), commit edilmiş dataset'i koruyor.
- Processing sırasında pencere kapatma (deferred close) güvenli.
- Raw `.ogpr` dosyası değişmeden kalıyor.

## Completion Summary

`Processing_Preview_and_Commit_Model.md`'nin registry + preview/apply
bölümü hayata geçirildi — undo/redo stack ve recipe sistemi hariç. 5
stabil processing fonksiyonu artık native GUI üzerinden non-destructive
biçimde (preview → apply, ayrı `raw`/`current`/`preview` dataset'leri,
stale-token/stale-revision koruması) kullanılabiliyor; dosya yükleme ile
processing birbirini karşılıklı dışlıyor; kapatma her iki arka plan
işini de güvenle erteliyor. 48 yeni test + mevcut 74 GUI testi (toplam
122) ve 318 çekirdek test tamamen yeşil. Test yazım sürecinde bulunan tek
gerçek sorun (aynı operation'ı reprocessing guard'ına takılacak şekilde
iki kez çalıştıran bir test + mock'suz modal dialog) üretim kodunda değil
testin kendisindeydi ve düzeltildi. **Manual visual acceptance kullanıcı
tarafından tamamlandı. Sprint implementasyonu commit edildi** — feature
commit `6050c076867d711ee713b75b3e554f2e818f8f3e`, branch
`origin/sprint-gui-3a-processing-preview-apply`'a push edildi. **Pull
Request ve CI doğrulaması kalan gate'lerdir. `main`'e merge henüz
gerçekleşmedi.**

## Next Sprint Recommendation

Kullanıcının kendi isteğiyle: bu sprintin bilinçli olarak dışarıda
bıraktığı undo/redo stack ve recipe sistemi (orijinal tasarım belgesinin
geri kalanı), processed dataset kaydetme, veya 3D/gridding track'inin
başlangıcı (bkz. [[03_ARCHITECTURE/3D_Volume_Data_Model]]).

## İlgili Notlar

[[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]],
[[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]],
[[06_DECISIONS/ADR_013_Display_Policy_and_Non_Destructive_Visualization]],
[[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]],
[[03_ARCHITECTURE/GUI_Architecture]],
[[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]],
[[02_SPRINTS/Sprint_GUI_2_Display_Controls]],
[[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]],
[[09_REFERENCES/Windows_Executable_Build]], [[02_SPRINTS/Sprint_Index]]
