---
type: adr
tags: [decision]
id: ADR-011
status: accepted
date: 2026-07-17
---

# ADR-011 — GUI Technology Decision (PySide6 + PyQtGraph + optional PyVista)

## Context

Sprint 4A ([[02_SPRINTS/Sprint_04A_Background_Removal]]) kapandı
(canonical policy = A0,
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]]).
Kullanıcı, `archaeogpr`'ı [NSGeophysics/GPRPy](https://github.com/NSGeophysics/GPRPy)
projesini yalnızca **mimari/UX/iş akışı referansı** olarak kullanarak modern
bir 2D/3D GPR masaüstü uygulamasına dönüştürmek istiyor
([[01_PROJECT_STATE/05_Project_Roadmap|Project Roadmap]] Faz 9 — GUI —
zaten planlanmıştı). Bu ADR, o dönüşümün ilk teknik kararını — GUI
teknoloji stack'ini — kayıt altına alır. Kapsam yalnızca bu **karardır**;
`src/archaeogpr/gui/` altında henüz hiçbir runtime kod yoktur (bkz.
[[02_SPRINTS/Sprint_GUI_0_Foundation]]).

Gereksinimler (kullanıcının audit talebinden): Windows'ta çalışan,
ileride paketlenebilir bir masaüstü uygulama; interaktif 2D radargram
görüntüleme (zoom/pan/crosshair/kontrast); tek swath'ın slice×channel
geometrisinden oluşan quasi-3D zaman-domeni hacmi + ortogonal
slice/volume rendering; GUI'nin `io/model/processing/qc/export`
katmanlarını **hiç değiştirmeden** yeniden kullanması; mevcut CLI
davranışının bozulmaması; ağır işlemlerin GUI'yi dondurmaması.

Mevcut çalışma ortamı: Python 3.12 venv'inde yalnızca `numpy`, `scipy`,
`pandas`, `matplotlib`, `pytest`, `ruff`, `mypy`, `pyyaml` kurulu — hiçbir
Qt/VTK bağımlılığı yok (bkz. `pyproject.toml` öncesi hali). Tkinter,
projenin kendi kuralı gereği hariç tutuldu (kullanıcı: "Tkinter tabanlı
yeni bir GUI oluşturma").

## Decision

1. **PySide6** (Qt for Python, LGPL) — ana pencere/widget/thread/sinyal
   çatısı. PyQt6 yerine tercih edildi (bkz. Alternatives Considered).
2. **PyQtGraph** — 2D B-scan/A-scan görüntüleme (`ImageItem`,
   `PlotWidget`), crosshair, gerçek-zamanlı contrast/colormap.
   Matplotlib-embed yerine tercih edildi (interaktif performans).
3. **PyVista + pyvistaqt** — yalnızca `gui3d` opsiyonel paketleme
   grubunda (`pyproject.toml`). 2D-only kurulum ve mevcut headless
   processing/CLI/test akışı bu bağımlılığı **hiç görmez**.
4. **NumPy/SciPy/pandas/PyYAML** aynen korunuyor — `io/model/processing/
   qc/export` katmanları değişmiyor.
5. **Matplotlib** yalnızca statik QC raporu ve export için kalıyor
   (mevcut `qc/*.py` modülleri) — interaktif GUI görüntülemesinde
   kullanılmayacak.
6. GUI, ayrı bir repository/paket olarak değil, aynı paket altında
   `src/archaeogpr/gui/` alt paketi olarak geliştirilecek — ortak
   `GPRDataset`/`ProcessingResult` modeli ve tek CI/test suite paylaşılır.
7. `pytest` (ve `pytest-qt`, GUI smoke testleri için), runtime
   `dependencies` listesinden `dev` optional-dependency grubuna taşındı —
   runtime kaynak kodunda (`src/archaeogpr/`) hiçbir `import pytest`
   bulunmadığı doğrulandıktan sonra (bkz. Validation). Bu, "GUI/3D
   bağımlılıkları zorunlu runtime bağımlılığı olmasın" prensibiyle aynı
   paketleme hijyeni kararının bir parçasıdır.
8. Paketleme (PyInstaller) bu ADR'nin kapsamı dışında — Sprint 3D-2
   sonrasına bırakıldı (ayrı, gelecekteki bir karar).

## Alternatives Considered

- **PyQt6 yerine PySide6:** PyQt6 GPL/ticari ikili lisans modeline
  sahiptir; PySide6 (Qt Company'nin resmi Python binding'i) LGPL —
  ticari/kapalı paketleme senaryosunda daha az sürtünme. API'leri hemen
  hemen aynı olduğundan teknik bir dezavantaj yok. Reddedildi (PyQt6):
  lisans tercihi.
- **Tkinter (GPRPy'nin kullandığı):** Kullanıcı tarafından açıkça
  reddedildi ("Tkinter tabanlı yeni bir GUI oluşturma"). Ayrıca GPRPy'nin
  kendi mimarisi (modül-global layout sabitleri, closure'a yakalanmış tek
  `proj` nesnesi, render mantığının üç yerde kopyalanması — bkz.
  [[09_REFERENCES/GPRPy_Reference_and_License_Notes]]) çoklu
  dosya/sekme ve modern responsive layout'u desteklemiyor.
  Reddedildi.
  <br><br>Not: GPRPy — hedef projesi/referans — kendisi Tkinter kullanıyor
  olsa da bu proje **GPRPy'nin GUI mimarisini kopyalamayacak**, yalnızca
  iş akışı fikirlerini alacak (bkz. görev talimatı madde 4).
- **Matplotlib embed (GPRPy'nin `FigureCanvasTkAgg` yaklaşımının Qt
  eşdeğeri, `FigureCanvasQTAgg`):** Değerlendirildi. Statik/az sayıda
  yeniden çizim için yeterli, ama pan/zoom/crosshair gibi sık, düşük
  gecikmeli etkileşimlerde PyQtGraph'ın GPU-hızlandırmalı, OpenGL tabanlı
  render yolunun gerisinde kalıyor; büyük B-scan dizilerinde (bu projede
  tek kanal ≤ 175×1024 ama gelecekte çok-swath birleştirmede büyüyebilir)
  fark daha belirgin olur. Reddedildi (interaktif ana görüntüleme için);
  matplotlib yine de statik export/rapor rolünde kalıyor.
- **VisPy (3D için PyVista alternatifi):** Daha hafif (VTK'yı
  getirmiyor), ama volume rendering/orthogonal-slice/opacity-transfer-
  function gibi hazır, üst-seviye widget'ları PyVista/`pyvistaqt` kadar
  olgun değil — bu özellikleri sıfırdan OpenGL ile yazmak gerekirdi.
  Reddedildi; VTK'nın paket boyutu maliyeti (`gui3d` opsiyonel grup
  olarak izole edilerek) kabul edilebilir bulundu.
- **PySide6/PyQtGraph'ı da zorunlu runtime bağımlılığı yapmak (headless
  CLI kurulumuna dahil etmek):** Reddedildi — kullanıcı talimatı
  ("PySide6/PyQtGraph de ana headless processing kurulumu için zorunlu
  olmamalı") ve mevcut CI'nin (`pip install -e ".[dev]"`) sade kalması
  gerekliliği. `gui`/`gui3d` ayrı optional-dependency grupları olarak
  tutuldu.

## Consequences

- `pyproject.toml`'da iki yeni optional-dependency grubu eklendi: `gui`
  (`PySide6>=6.7`, `pyqtgraph>=0.13.7`) ve `gui3d` — **kendi kendine
  yeten** (self-contained) bir üst küme: `PySide6>=6.7`,
  `pyqtgraph>=0.13.7`, `pyvista>=0.44`, `pyvistaqt>=0.11`. `gui`
  listesi `gui3d` içinde bilinçli olarak **tekrarlandı** (bir
  `"archaeogpr[gui]"` öz-referansı yerine) — böylece `pip install -e
  ".[gui3d]"` tek başına tam 2D+3D yığınını kurar, ayrıca `.[gui]`
  kurmayı gerektirmez. `dev` grubuna `pytest>=7.4` ve `pytest-qt>=4.4`
  eklendi. `dependencies` listesinden `pytest` çıkarıldı. Mevcut headless
  kurulum/test/CI komutları (`pip install -e ".[dev]"`, `pytest`, `ruff`,
  `mypy`) değişmeden çalışmaya devam ediyor (bkz. Validation).
- `src/archaeogpr/gui/` henüz **yoktur** — bu ADR bir teknoloji kararıdır,
  bir implementasyon değil. GUI-1'de (kullanıcının ayrı onayıyla)
  oluşturulacak iskelet, bu kararı uygulayacak.
- 3D görüntüleme (`gui3d`), 2D kullanım ve tüm mevcut CLI/test/işleme
  akışından tamamen izole — VTK/PyVista kurulu olmadan uygulamanın geri
  kalanı (varsayım: GUI-2 sonrasında) çalışabilmelidir; bu, GUI
  mimarisinde `gui3d` import'unun lazy (yalnızca 3D görünüm açıldığında)
  yapılmasını zorunlu kılar — bkz. [[03_ARCHITECTURE/GUI_Architecture]].
- `io/model/processing/qc/export` ve `cli.py` bu kararla **hiç
  değişmedi** — GUI bu katmanları çağıran yeni bir tüketicidir, onları
  yeniden yazmaz (bkz. [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]]).

## Validation

- `grep -rn "^import pytest\|^from pytest\|import pytest$" src/archaeogpr`
  → **0 eşleşme** — runtime kaynak kodu `pytest`'i hiçbir yerde import
  etmiyor, dolayısıyla `pytest`'in `dev` extra'sına taşınması headless
  runtime kurulumunu bozmuyor.
  `grep -rln pytest src/archaeogpr` → **0 dosya**.
- `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"`
  → `pyproject.toml` geçerli TOML; `dependencies`, `optional-
  dependencies.{dev,gui,gui3d}` beklenen listeleri veriyor (bkz.
  [[02_SPRINTS/Sprint_GUI_0_Foundation]] Validation Results).
- Yerel `.venv`'de `pytest==9.1.1`, `ruff==0.15.21`, `mypy==2.3.0` zaten
  kurulu (önceki `dev` extra kurulumundan) — bu ADR'nin `pyproject.toml`
  değişikliği bu ortamı bozmadı; `pytest`/`ruff`/`mypy` bu Sprint GUI-0
  turunda da sorunsuz çalıştı (bkz.
  [[02_SPRINTS/Sprint_GUI_0_Foundation]]).
- `gui`/`gui3d` bağımlılıkları bu turda **fiilen kurulmadı** (gerçek
  PySide6/PyVista paketleri indirilip kurulmadı) — ama bağımlılık
  **çözünürlüğü**, repository/branch ayrım turunda
  `pip install --dry-run -e ".[gui]"` ve `pip install --dry-run -e
  ".[gui3d]"` ile doğrulandı: `.[gui]` → `PySide6-6.11.1` (+
  `PySide6_Essentials`/`PySide6_Addons`/`shiboken6`) + `pyqtgraph-0.14.0`;
  `.[gui3d]` → aynı PySide6/pyqtgraph yığını **artı**
  `pyvista-0.48.4`/`pyvistaqt-0.12.0`/`vtk-9.6.2` ve transitive
  bağımlılıkları — `gui3d`'nin `.[gui]`'ye ek bir kurulum gerektirmeden
  kendi kendine yeterli olduğu bu şekilde kanıtlandı. Gerçek paketlerin
  fiilen indirilip içe aktarılması (import edilebilirlik testi) GUI-1'in
  ilk kurulumuna bırakıldı.

## Related Files

- `pyproject.toml`
- [[02_SPRINTS/Sprint_GUI_0_Foundation]]
- [[03_ARCHITECTURE/GUI_Architecture]]
- [[03_ARCHITECTURE/3D_Volume_Data_Model]]
- [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]]
- [[09_REFERENCES/GPRPy_Reference_and_License_Notes]]
- [[01_PROJECT_STATE/06_GUI_3D_Risk_Register]]
- [[01_PROJECT_STATE/05_Project_Roadmap]] (Faz 9)
