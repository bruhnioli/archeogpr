---
type: sprint
tags: [sprint, gui]
sprint: GUI-1
status: done
started: 2026-07-17
completed: 2026-07-17
---

# Sprint GUI-1 — Native Windows Viewer Shell + Executable

> **Kapsam:** Native PySide6 masaüstü uygulama kabuğu: dosya açma, kanal
> seçimi, B-scan, A-scan, metadata paneli, ve kullanıcının çift tıklayarak
> açabileceği bir Windows executable (`dist\ArchaeoGPR\ArchaeoGPR.exe`).
> **Processing ve 3D bu sprintte YOK** — bkz. Out of Scope.

## Goal

Kullanıcının gerçek bir `.ogpr` dosyasını, terminal/Python bilmeden,
`ArchaeoGPR.exe`'ye çift tıklayarak açıp B-scan/A-scan olarak
görüntüleyebileceği ilk gösterilebilir Windows masaüstü uygulamasını teslim
etmek.

## Scope

- `src/archaeogpr/gui/` (yeni): `app.py`, `__main__.py`, `main_window.py`,
  `logging_setup.py`, `models/dataset_session.py`,
  `views/{bscan_view,ascan_view,metadata_panel}.py`.
- File → Open OGPR, kanal seçici, B-scan, A-scan, metadata paneli,
  status bar readout, zoom/pan (pyqtgraph yerleşik).
- `tests/test_gui.py` — 12 test, `@pytest.mark.gui`, offscreen.
- `packaging/archaeogpr.spec`, `scripts/build_windows.ps1`.
- `dist/ArchaeoGPR/ArchaeoGPR.exe` — one-folder, windowed, PyInstaller build.
- Qt DLL sorununun kök nedeninin bulunup çözülmesi (bkz.
  [[06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime]]).
- `pyproject.toml` extras yeniden düzenlendi: `dev` (Qt'siz), `gui`,
  `gui-test`, `gui3d`, `packaging`.

## Out of Scope

Processing registry, processing dialogları (time-zero/DC/dewow/band-pass/
background/gain GUI), preview/apply, undo/redo, recipe, worker/thread
framework (bkz. `GUI-1B` TODO), depth conversion, velocity analysis,
survey map, picking, annotation, migration, PyVista/VTK/3D grid/time-depth
slice, project/session save, installer (MSI/Inno/NSIS), auto-update,
code signing, slice selector (bkz. Decisions — bilinçli olarak yok).

## Input Data

`data/raw/Swath003_Array02.ogpr` (gerçek dosya, 175×11×1024, float32, read-only
kabul edilir) + `tests/conftest.py`'deki sentetik `.ogpr` byte builder
(`valid_ogpr_path`, `dataset_factory` fixture'ları, yeniden kullanıldı —
yeni bir builder yazılmadı).

## Tasks

- [x] Repository/branch durumu doğrulandı (`sprint-gui-0-foundation` @
  `ef42fc6`, temiz, gain yok).
- [x] Qt DLL sorunu kök nedeni bulundu ve çözüldü (bkz. ADR-012).
- [x] `pyproject.toml` extras yeniden düzenlendi.
- [x] `sprint-gui-1-viewer-shell` branch'i `ef42fc6`'dan açıldı.
- [x] GUI paketi + entry point yazıldı.
- [x] Ana pencere, B-scan, A-scan, metadata paneli implemente edildi.
- [x] Log sistemi eklendi.
- [x] 12 GUI testi yazıldı, offscreen doğrulandı; core testler `pytest-qt`
  olmadan da çalıştığı ayrı bir venv'de doğrulandı.
- [x] PyInstaller spec + build script yazıldı, `ArchaeoGPR.exe` üretildi.
- [x] Executable gerçek veriyle, Türkçe/boşluklu yolla, hash doğrulamasıyla
  test edildi.
- [x] Dokümantasyon (bu not, ADR-012, README, `Windows_Executable_Build.md`).

## Acceptance Criteria

Kullanıcının 24. bölümdeki (`Kabul Kriterleri`) tüm maddeleri — bkz.
Completion Summary'deki madde madde eşleme.

## Implementation Notes

### Axis semantiği kararı (kullanıcının 10. bölüm talebi)

`GPRDataset.amplitudes` `(slice, channel, sample)`; bu veri setinde
`slice` **along-track trace eksenidir** — `src/archaeogpr/qc/bscan.py::
plot_bscan`'ın zaten yaptığı gibi (`dataset.amplitudes[:, channel, :]`
→ `(slice, sample)` → `.T` → imshow). **Bilinçli olarak ayrı bir "slice
selector" eklenmedi** — bu, aynı fiziksel ekseni iki farklı isim/kontrol
altında ikinci kez göstermek olurdu. Bunun yerine: **kanal seçici**
(gerçek, bağımsız bir fiziksel eksen) + B-scan'e tıklayarak **seçilen
trace**. Karar `dataset_session.py`'nin modül docstring'inde, bu notta ve
[[03_ARCHITECTURE/GUI_Architecture]]'da belgeleniyor.

### Tek merkezi transpose noktası

`views/bscan_view.py::BScanView.set_data()` — `channel_data =
dataset.amplitudes[:, channel, :]` → `channel_data.T` — `qc/bscan.py` ile
birebir aynı transpose. Başka hiçbir GUI kodu amplitude dizisini
transpoze/yeniden yönlendirmiyor.

### pyqtgraph eksen yönü (deneysel olarak doğrulandı, varsayılmadı)

`pg.setConfigOptions(imageAxisOrder='row-major')` + `ImageItem.setRect(...)`
+ `ViewBox.invertY(True)` kombinasyonu, offscreen bir Qt ortamında küçük
bir deney scriptiyle doğrulandı: satır 0 (en erken zaman) view-Y'de en
küçük değere (`t0`) karşılık geliyor; `invertY(True)` olmadan bu ekranın
ALTINDA görünürdü (pyqtgraph'ın varsayılan Y-yukarı kuralı yüzünden) —
`invertY(True)` ile ekranın ÜSTÜNDE görünüyor, `qc/bscan.py`'nin
`origin="upper"` matplotlib kuralıyla eşleşiyor (zaman aşağı doğru artıyor).

### QMessageBox.critical() offscreen'de bloke oluyor (bulundu, testlerde ele alındı)

Manuel bir doğrulama scripti sırasında keşfedildi: `QMessageBox.critical()`
modal'dır (kendi iç event loop'u) ve offscreen platformda hiç kimse
tıklamayacağı için **sonsuza dek bloke olur** — script zorla
sonlandırılmak zorunda kaldı. `tests/test_gui.py`'deki hata-yolu testi
(`test_open_bad_path_preserves_previous_session`) bu yüzden
`QMessageBox.critical`'ı `monkeypatch` ile no-op yapıyor.

### Qt DLL kök nedeni ve çözümü

Bkz. [[06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime]]
— özet: Anaconda tabanlı venv'de `PySide6.QtCore` DLL yükleme hatası
veriyordu; python.org CPython 3.13 tabanlı izole bir ortamda **ilk
denemede** çalıştı. VC++ runtime güncel olduğu doğrulandı (kök neden
Anaconda'ya özgü bir DLL çakışması olarak değerlendirildi, tam olarak
teşhis edilmedi ama iş yapıyor). `py -0p` yalnızca CPython 3.13 gösterdi
(3.12/3.11 yok) — 3.13 kullanıldı (python.org, yasaklı liste dışı,
`requires-python>=3.11` karşılıyor).

### PyInstaller: `pyqtgraph.examples`/`opengl` hariç tutuldu

`collect_submodules("pyqtgraph")` varsayılan olarak pyqtgraph'ın ~100
demo script'ini (`pyqtgraph.examples.*`) ve `pyqtgraph.opengl`'i
(PyOpenGL kurulu değil, zaten bir uyarıyla atlanıyor) da topluyordu.
`packaging/archaeogpr.spec`'te bir `filter=` ile ikisi de hariç
tutuldu — "yalnızca gerçekten gereken hidden importlar" kuralı.

## Validation Results

| Kontrol | Sonuç |
|---|---|
| `git diff --check` | ✅ temiz |
| `ruff format --check .` | ✅ 78 dosya zaten formatlı |
| `ruff check .` | ✅ All checks passed |
| `mypy src/archaeogpr` | ✅ 50 dosya, sıfır hata |
| `pytest -m "not gui"` | ✅ 318 passed, 26 skipped, 12 deselected, 0 failed |
| `pytest -m gui` (offscreen) | ✅ 12 passed, 344 deselected |
| Ayrı `dev`-only venv (Qt paketi yok) | ✅ `pytest`/`pytest -m "not gui"` → 318 passed, 27 skipped, 0 failed — `test_gui.py` `importorskip` ile temiz skip, collection hatası yok |
| Vault validator | ✅ PASS — 81 not (79 + bu iki yeni belge), 0 broken/ambiguous/orphan |
| Frozen `ArchaeoGPR.exe --smoke-test` | ✅ exit 0, log'a "smoke test passed" yazıldı |
| Frozen `ArchaeoGPR.exe --version` | ✅ `archaeogpr 0.1.0` |
| Frozen `ArchaeoGPR.exe --open <gerçek .ogpr> --smoke-test` | ✅ exit 0, shape=(175, 11, 1024) log'landı |
| Türkçe karakter + boşluklu yol (`Türkçe Klasör Şişli Öğrenci Ünvanı\Örnek Veri Çığşöü.ogpr`) | ✅ exit 0, doğru açıldı, log'landı |
| Raw dosya SHA-256 (önce/sonra, tüm testler boyunca) | ✅ `66d840c3...b62a6` — değişmedi |

## Generated Outputs

- `dist/ArchaeoGPR/ArchaeoGPR.exe` (+ `_internal/`) — 288 MB toplam,
  one-folder, windowed.
- `build/ArchaeoGPR/` — PyInstaller ara çıktıları (warn/xref raporları
  dahil), `.gitignore`'a eklenmeli (bkz. Issues Discovered).
- `%LOCALAPPDATA%\ArchaeoGPR\logs\archaeogpr.log` — çalışma zamanı logu.

## Issues Discovered

1. **PowerShell 5.1, native exe'ye gömülü çift tırnak içeren argümanları
   bozuyor** — `python -c "...f\"...\"..."` şeklinde bir here-string,
   f-string'in çift tırnaklarını sessizce siliyordu
   (`SyntaxError: invalid syntax`). Çözüm: `build_windows.ps1`'deki tüm
   çok satırlı Python kontrolleri geçici `.py` script dosyalarına
   yazılıp öyle çalıştırılıyor (bkz. script'in kendi yorum satırı).
2. **`QMessageBox.critical()` offscreen'de bloke oluyor** — bkz.
   Implementation Notes; testlerde `monkeypatch` ile ele alındı, ama
   gerçek uygulamada (görünür bir pencere + gerçek event loop ile) sorun
   yok — yalnızca otomatik/offscreen test bağlamında ortaya çıkıyor.
3. **`build/`, `dist/`, `.venv_anaconda_broken_20260717/` `.gitignore`'a
   henüz eklenmedi** — bu sprint bunları commit etmedi (bkz. Sprint
   GUI-0'ın "commit öncesi onay" politikası, bu sprint de aynı şekilde
   commit atmadan durdu) ama gelecekte commit aşamasında `.gitignore`
   güncellenmesi gerekecek.
4. **288 MB one-folder boyutu** — büyük ölçüde PySide6 (Qt Widgets/Gui/
   Quick/Qml/Pdf) + numpy/scipy OpenBLAS + pandas + matplotlib'in
   kaçınılmaz boyutu. `pyqtgraph.examples`/`opengl` hariç tutuldu ama
   PySide6 Addons'un getirdiği kullanılmayan Qt modülleri (QtQml/QtQuick/
   QtPdf) daha agresif `excludes=` ile küçültülebilir — bu sprintin
   kapsamı dışında bırakıldı (risk: hook kırılganlığı, zaman kısıtı).

## Decisions

1. Slice selector **eklenmedi** — kanal seçici + B-scan-tıklama ile trace
   seçimi (bkz. Implementation Notes).
2. Qt geliştirme ortamı: python.org CPython (3.13, tek mevcut sürüm),
   Anaconda/Miniconda/MS Store asla.
3. `pytest-qt` `dev`'den çıkarılıp yeni `gui-test` extra'sına taşındı.
4. Dosya yükleme senkron (worker framework yok) — `GUI-1B` TODO'su kodda
   açıkça bırakıldı.
5. İkon yok (proje `.ico`'su yok) — varsayılan PyInstaller ikonu kabul
   edildi.
6. `pyqtgraph.examples`/`opengl` PyInstaller bundle'ından hariç tutuldu.

## Completion Summary

Kullanıcının 24. bölümdeki kabul kriterlerinin tamamı karşılandı:
PySide6.QtCore/QApplication offscreen/native PySide6 uygulaması/tarayıcı
yok/localhost yok/terminal gerektirmiyor/`ArchaeoGPR.exe` çift tıklamayla
açılıyor/console penceresi yok (`console=False`)/File→Open çalışıyor/
gerçek B-scan/kanal seçimi/trace seçimi/A-scan güncelleniyor/metadata
paneli/zoom-pan (pyqtgraph yerleşik)/raw hash değişmiyor/core testler
sıfır fail/GUI testleri sıfır fail/ruff sıfır hata/mypy sıfır hata/vault
validator PASS/executable smoke exit 0/executable gerçek OGPR açıyor/
bağımsız bundle (Python kurulu olmayan kullanıcı için)/gain-processing-3D
kodu eklenmedi.

**Commit/push henüz yapılmadı** — kullanıcının onayı bekleniyor (bkz. asıl
talimat, bölüm 25).

## Next Sprint Recommendation

**GUI-1B** (kodda TODO olarak işaretli): dosya yükleme için background
worker (QThread), böylece daha büyük dosyalarda GUI donmaz. Ardından —
yalnızca kullanıcının ayrı isteğiyle — Sprint GUI-2 (interaktif
contrast/colormap paneli, survey geometry haritası, PNG/TIFF export) veya
Sprint GUI-3 (processing entegrasyonu, bkz.
[[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]]).

## İlgili Notlar

[[06_DECISIONS/ADR_011_GUI_Technology_Decision]],
[[06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime]],
[[03_ARCHITECTURE/GUI_Architecture]],
[[09_REFERENCES/Windows_Executable_Build]],
[[02_SPRINTS/Sprint_GUI_0_Foundation]], [[02_SPRINTS/Sprint_Index]]
