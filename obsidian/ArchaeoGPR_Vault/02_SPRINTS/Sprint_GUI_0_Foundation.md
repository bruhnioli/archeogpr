---
type: sprint
tags: [sprint, gui]
sprint: GUI-0
status: done
started: 2026-07-17
completed: 2026-07-17
---

# Sprint GUI-0 — GUI/3D Dönüşümü: Repository Audit, Mimari Tasarım ve Bağımlılık İskeleti

> **Kapsam:** Bu sprint **yalnızca** dokümantasyon, ADR, `pyproject.toml`
> bağımlılık grupları ve `README.md`'nin durum bölümüdür.
> `src/archaeogpr/gui/` altında **hiçbir runtime kod yazılmadı** — bu
> kullanıcının kendi açık talimatıydı ("Bu turda yalnızca aşağıdakileri
> yap... BU TURDA YASAK OLANLAR: src/archaeogpr/gui runtime kodu
> oluşturma..."). GUI-1 (uygulama kabuğu), yalnızca kullanıcının ayrı,
> açık onayıyla başlayacak bir sonraki sprinttir.

## Goal

Mevcut ArchaeoGPR reposunu (source of truth), Obsidian vault'unu ve
[NSGeophysics/GPRPy](https://github.com/NSGeophysics/GPRPy)'yi
(yalnızca mimari/UX referansı — fork edilmedi, kod alınmadı) inceleyip,
kullanıcının onayladığı GUI/3D dönüşüm kararlarını (bkz. Decisions)
vault'a ADR + mimari + risk kaydı olarak işlemek; `pyproject.toml`'a
opsiyonel `gui`/`gui3d` bağımlılık gruplarını eklemek; ve mevcut
untracked Sprint 4B (gain) çalışmasını, ona dokunmadan/GUI'ye
karıştırmadan güvence altına almak.

## Scope

- Repository audit (bu sprintin kendisi bir önceki, kod-yazmayan turda
  yapıldı — bulgular bu nota ve aşağıdaki yeni belgelere aktarıldı).
- 7 yeni vault belgesi: [[03_ARCHITECTURE/GUI_Architecture]],
  [[03_ARCHITECTURE/3D_Volume_Data_Model]],
  [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]],
  [[06_DECISIONS/ADR_011_GUI_Technology_Decision]],
  [[09_REFERENCES/GPRPy_Reference_and_License_Notes]],
  [[01_PROJECT_STATE/06_GUI_3D_Risk_Register]], bu sprint notu.
- 6 mevcut belgenin kontrollü güncellenmesi: `01_Current_Project_State.md`,
  `02_Next_Development_Sprint.md`, `00_Claude_Context.md`,
  `05_Project_Roadmap.md`, `Sprint_Index.md`, `Decision_Index.md`.
- `pyproject.toml`: `gui`/`gui3d` opsiyonel bağımlılık grupları eklendi;
  `pytest` runtime `dependencies`'ten `dev` extra'sına taşındı (önce
  runtime kodunda `pytest` import'u olmadığı doğrulandı).
- `README.md`'de yalnızca GUI-0 durumu + planlanan opsiyonel kurulum
  komutları eklendi — henüz var olmayan GUI özellikleri implemente
  edilmiş gibi yazılmadı.
- Sprint 4B gain WIP dosyalarının güvence altına alınması (backup +
  hash doğrulaması) — bkz. Issues Discovered.

## Out of Scope

- `src/archaeogpr/gui/` altında herhangi bir runtime kod (MainWindow,
  File→Open, worker/thread, processing registry, recipe, gridding/3D
  kodu).
- Gain kodunun GUI'ye veya bu sprint'e bağlanması.
- Mevcut `io/model/processing/qc/export` veya `cli.py`'nin
  değiştirilmesi.
- Canonical processing kararlarının (D2+B1, A0) değiştirilmesi.
- Mevcut çıktı dosyalarının yeniden üretilmesi.
- `gui`/`gui3d` bağımlılıklarının fiilen kurulması (yalnızca metadata
  doğrulandı).
- Git branch değiştirme veya commit atma (bkz. Issues Discovered — bu
  konuda kullanıcıdan karar bekleniyor).

## Input Data

- ArchaeoGPR repository'sinin tamamı (`src/archaeogpr/`, `tests/`,
  `configs/`, `outputs/`, `data/raw/Swath003_Array02.ogpr`,
  `pyproject.toml`, `CLAUDE.md`, `README.md`) — source of truth.
- `obsidian/ArchaeoGPR_Vault/` — tüm proje-durumu, sprint, ADR,
  processing-planı, validation ve session-log notları.
- [NSGeophysics/GPRPy](https://github.com/NSGeophysics/GPRPy) —
  scratchpad'e (`C:\Users\baran\AppData\Local\Temp\claude\...\scratchpad\GPRPy`)
  **geçici, repository dışı** bir klon olarak incelendi; `archaeogpr`
  reposuna hiçbir dosyası kopyalanmadı.

## Tasks

- [x] ArchaeoGPR repository'sini oku (README, pyproject, `src/archaeogpr`
  altındaki tüm modüller, testler, configs, CLI, veri/metadata modelleri,
  OGPR reader, qc, processing history yapısı).
- [x] Obsidian vault'unu oku (proje durumu, sprintler, ADR'lar, planlanan
  processing modülleri, riskler, dataset notları, vault konvansiyonları).
- [x] GPRPy'yi klonla ve mimari/UX/lisans açısından oku (`gprpy.py`,
  GUI'ler, `toolbox/`, veri import fonksiyonları, history/undo
  davranışı, plotting/picking/migration).
- [x] Sprint 4B gain WIP dosyalarını tespit et, boyut/hash'lerini kaydet,
  repository dışı bir scratchpad konumuna birebir yedekle, kaynak/yedek
  hash eşleşmesini doğrula.
- [x] `pyproject.toml`'a `gui`/`gui3d`/`dev` gruplarını ekle (önce
  `pytest` import güvenliğini doğrulayarak).
- [x] 7 yeni vault belgesini yaz.
- [x] 6 mevcut vault belgesini kontrollü güncelle.
- [x] `README.md`'yi güncelle.
- [x] `ruff format --check`, `ruff check`, `mypy src/archaeogpr`,
  `pytest`, `python scripts/validate_obsidian_vault.py` çalıştır.

## Acceptance Criteria

- Vault validator: **PASS** (0 broken/ambiguous wikilink, 0 disallowed
  dosya).
- `pytest`: Sprint GUI-0'ın kendisi hiçbir test eklemedi/kod değiştirmedi
  (yalnızca `pyproject.toml` metadata'sı değişti) — dolayısıyla bu
  sprintin **kendi eklediği** hiçbir regresyon yoktur. Ancak bu turda,
  Sprint GUI-0'dan **bağımsız, önceden var olan** bir bulgu ortaya çıktı
  — bkz. Issues Discovered #3: ana çalışma ağacında (untracked Sprint 4B
  gain dosyaları mevcutken) `pytest` **343 passed, 1 failed** veriyor —
  kırılan tek test `test_gain_module_does_not_exist_and_report_confirms_
  gain_not_started` (`archaeogpr.processing.gain`'in var OLMADIĞINI
  doğrulayan bir regresyon koruması). Bu, untracked `gain.py`'nin fiziksel
  olarak diskte bulunmasının doğrudan sonucudur — git tracking durumu
  Python'un import mekanizması için önemsizdir. **Doğrulama:** `git
  worktree add --detach <kısa-yol> HEAD` ile committed HEAD'in (untracked
  hiçbir dosya içermeyen) ayrı bir kopyası oluşturuldu; `PYTHONPATH`'i o
  worktree'nin `src/`'ine açıkça yönlendirerek (editable install'ın asıl
  repoyu göstermesini bypass ederek) aynı test tek başına çalıştırıldığında
  **1 passed** verdi, tam suite ise **313 passed, 31 skipped** (31 skip —
  `data/raw/Swath003_Array02.ogpr` gitignore'lu olduğu için worktree'de
  yok; toplam 313+31=344, ana ağaçtaki gerçek-dosyalı 344 rakamıyla
  tutarlı). Bu, **committed kod tabanının kendisinin hâlâ 344/0/0**
  olduğunu, kırılmanın yalnızca untracked gain WIP + committed test'in
  çalışma ağacındaki birlikte varlığından kaynaklandığını kesin olarak
  doğruluyor. Geçici worktree sonrasında kaldırıldı (`git worktree
  remove`); `git status`/branch bu deneyden etkilenmedi (bkz. Issues
  Discovered #3 devamı — `.git/worktrees/agpr_verify` altında zararsız,
  kilitli bir metadata artığı kaldı, `git worktree list`'te görünmüyor).
- `ruff format --check`, `mypy src/archaeogpr`: temiz (Sprint GUI-0
  öncesiyle aynı). `ruff check`: 3 önceden var olan `E501` (satır çok
  uzun) hatası — **yalnızca** untracked `src/archaeogpr/
  sprint4b_candidates.py` içinde (satır 816, 817, 876), bu sprintin
  dokunmadığı bir dosyada. Bu proje kaynak kodunun geri kalanında
  (39 tracked dosya) `ruff check` **temiz**.
- `git diff --stat`: yalnızca `pyproject.toml`, `README.md` ve
  `obsidian/ArchaeoGPR_Vault/**` altında değişiklik; `src/archaeogpr/`
  altında **sıfır** değişiklik.
- Sprint 4B gain dosyaları: içerik/hash olarak **değişmemiş**, GUI'ye
  bağlanmamış, silinmemiş.
- Hiçbir eski ADR/sprint notu silinmedi veya tarihçesi yeniden
  yazılmadı.

## Implementation Notes

- **Gain WIP güvencesi**: `configs/gain_candidates.yaml`,
  `src/archaeogpr/export/sprint4b.py`, `src/archaeogpr/processing/gain.py`,
  `src/archaeogpr/qc/gain.py`, `src/archaeogpr/sprint4b_candidates.py`
  (toplam 5 untracked dosya) scratchpad'deki
  `sprint4b_gain_wip_backup/` altına birebir kopyalandı; SHA-256
  karşılaştırması her dosya için `MATCH` verdi (tam liste + hash'ler:
  bu backup dizinindeki `BACKUP_MANIFEST.md`). **Branch/commit işlemi
  yapılmadı** — bkz. Issues Discovered #1.
- **`pyproject.toml`**: `grep -rn "^import pytest\|^from pytest\|import
  pytest$" src/archaeogpr` → 0 eşleşme, `grep -rln pytest
  src/archaeogpr` → 0 dosya; bu doğrulamadan sonra `pytest` runtime
  `dependencies`'ten çıkarılıp `dev` extra'sına taşındı (yanına
  `pytest-qt>=4.4` eklendi). Yeni `gui` (`PySide6>=6.7`,
  `pyqtgraph>=0.13.7`) ve `gui3d` (`pyvista>=0.44`, `pyvistaqt>=0.11`)
  grupları eklendi. CI (`.github/workflows/ci.yml`) yalnızca
  `pip install -e ".[dev]"` çalıştırıyor — bu komut değişmedi ve
  `pytest`'i hâlâ kurar, dolayısıyla headless kurulum/CI etkilenmedi.
- **Vault belgeleri**: mevcut `Template_ADR.md`/`Template_Sprint.md`
  şablonları ve ADR-001/ADR-009/Sprint-04A'nın frontmatter/bölüm
  konvansiyonları izlendi; dil Türkçe (vault'un proje-durumu/mimari
  notlarının baskın dili).

## Validation Results

- `git status --short` (değişiklik öncesi): yalnızca 5 untracked Sprint
  4B gain dosyası; branch `sprint-04b-gain-candidates` (main değil).
- SHA-256 kaynak/yedek karşılaştırması: 5/5 dosya `MATCH` (bkz.
  Implementation Notes).
- `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"`
  → geçerli TOML; `dependencies`, `optional-dependencies.{dev,gui,gui3d}`
  beklenen içerikte.
- `ruff format --check .` → **70 files already formatted** (temiz).
- `ruff check .` → **3 hata**, tamamı untracked `src/archaeogpr/
  sprint4b_candidates.py` içinde (`E501` satır-uzunluğu, satır 816/817/876)
  — bu sprintin dokunmadığı, önceden var olan bir dosyada.
- `mypy src/archaeogpr` → **Success: no issues found in 43 source
  files.**
- `pytest` (ana çalışma ağacı, gerçek dosya + untracked gain WIP mevcut)
  → **343 passed, 1 failed** in 174.65s — tek kırılan test:
  `tests/test_sprint4a_candidates.py::
  test_gain_module_does_not_exist_and_report_confirms_gain_not_started`.
  Bağımsız doğrulama (`git worktree` + `PYTHONPATH` yönlendirmesi,
  untracked gain WIP'siz committed HEAD üzerinde): tek test **1 passed**,
  tam suite **313 passed, 31 skipped** (gerçek dosya worktree'de yok,
  gitignore'lu) — toplam 344, committed kod tabanının **0 failed**
  olduğunu doğruluyor. Bkz. Issues Discovered #3.
- `python scripts/validate_obsidian_vault.py obsidian/ArchaeoGPR_Vault` →
  ilk çalıştırmada **FAIL** (19 broken wikilink) — bu sprintin kendi
  yeni belgelerinde uzun satırları elle sarmalarken 19 çift-köşeli-
  parantezli bağlantı satır arasında bölünmüştü (regex tabanlı parser
  bunu tek bir hedef olarak çözemiyor). Tamamı tek satıra birleştirilerek
  düzeltildi. İkinci bir FAIL (1 broken wikilink) bu paragrafın kendi
  metninde bağlantı sözdizimini örneklerken kullanılan literal çift-
  köşeli-parantez örneğinden kaynaklandı (parser onu gerçek bir bağlantı
  sandı) — o örnek ifade de düzeltildi. Üçüncü çalıştırma **PASS** verdi:
  **79 markdown notu** (72 önceki + 7 yeni), **0 broken wikilink, 0
  ambiguous wikilink, 0 orphan note, 0 disallowed dosya**.

## Generated Outputs

Bu sprint hiçbir `outputs/` dosyası üretmedi (kod/CLI çalıştırma yok) —
yalnızca vault belgeleri, `pyproject.toml`, `README.md` ve repository
dışı bir scratchpad backup'ı (`sprint4b_gain_wip_backup/`,
repository'nin parçası değil).

## Issues Discovered

1. **Sprint 4B gain WIP dosyaları untracked ve testsiz** —
   `configs/gain_candidates.yaml`, `src/archaeogpr/export/sprint4b.py`,
   `src/archaeogpr/processing/gain.py`, `src/archaeogpr/qc/gain.py`,
   `src/archaeogpr/sprint4b_candidates.py` — henüz var olmayan bir
   ADR-010'a atıf yapıyor, CLI'ye bağlı değil, testi yok, vault'un
   "Gain başlamadı" kaydıyla çelişiyor. Bu sprint onları **değiştirmedi,
   silmedi, GUI'ye bağlamadı** — yalnızca hash-doğrulamalı bir yedeğini
   aldı. Bkz. [[01_PROJECT_STATE/06_GUI_3D_Risk_Register]] R11.
2. **Repository `main` üzerinde değil** — mevcut branch
   `sprint-04b-gain-candidates`. Bu, kullanıcının "gain dosyalarını yeni
   bir `sprint4b-gain-wip` branch'inde commit etmeyi değerlendir"
   talimatının varsaydığı durumdan farklı (zaten gain'e özgü bir
   branch'teyiz). Branch/commit işlemi bu yüzden **yapılmadı**, karar
   kullanıcıya bırakıldı. Bkz. [[01_PROJECT_STATE/06_GUI_3D_Risk_Register]]
   R12.
3. **Untracked gain WIP, committed bir regresyon testini kırıyor** —
   `tests/test_sprint4a_candidates.py::
   test_gain_module_does_not_exist_and_report_confirms_gain_not_started`,
   `archaeogpr.processing.gain`'in **var olmadığını** doğrulayan bir
   committed testtir (Sprint 4A Closure'dan, ADR-009'un "Gain
   başlamadı" iddiasının kod-seviyesi kanıtı). Untracked
   `src/archaeogpr/processing/gain.py`'nin ana çalışma ağacında fiziksel
   olarak var olması bu testi kırıyor (`pytest` → 343 passed, 1 failed —
   önceki vault kaydı olan "344 passed, 0 failed, 0 skipped"ten farklı).
   Bu, **Sprint GUI-0'ın neden olduğu bir regresyon DEĞİLDİR** — bağımsız
   bir `git worktree` + `PYTHONPATH` deneyiyle committed HEAD'in (gain
   WIP'siz) hâlâ 0 failed verdiği doğrulandı (bkz. Validation Results).
   Bu bulgu, gain WIP'in GUI-0'a karıştırılmaması kararının ne kadar
   yerinde olduğunu somut olarak gösteriyor. Düzeltme bu sprintin
   kapsamı dışında — gain dosyaları ya kaldırılmalı/branch'e taşınmalı ya
   da bu test güncellenmelidir, ama her iki karar da yalnızca Sprint 4B
   kapsamında, kullanıcının kendi isteğiyle alınabilir. Bkz.
   [[01_PROJECT_STATE/06_GUI_3D_Risk_Register]] R11 (güncellendi).
4. **Geçici doğrulama worktree'sinden zararsız bir artık kaldı** —
   `git worktree remove` bir Windows dosya-kilidi yüzünden
   `.git/worktrees/agpr_verify` metadata klasörünü silemedi
   (`Permission denied`); `git worktree prune` de aynı hatayı verdi.
   `git worktree list` bu worktree'yi artık **göstermiyor** ve
   `git status`/branch/dosya durumu tamamen temiz — bu yalnızca dahili,
   işlevsel olmayan bir klasör artığıdır. Kullanıcı dilerse ileride
   elle silebilir (`.git/worktrees/agpr_verify`); hiçbir işlevsel etkisi
   yoktur.

## Decisions

Kullanıcı tarafından bu sprint başlamadan önce onaylanan kararlar (bkz.
[[06_DECISIONS/ADR_011_GUI_Technology_Decision]] için tam gerekçe):

1. GUI stack: PySide6 + PyQtGraph (zorunlu değil, `gui` extra) +
   PyVista/pyvistaqt (yalnızca opsiyonel `gui3d` extra) + mevcut
   NumPy/SciPy/pandas; matplotlib yalnızca statik QC/export.
2. GUI aynı repository ve aynı Python paketi altında:
   `src/archaeogpr/gui`.
3. İlk 3D hedefi: mevcut tek swath'ın slice×channel geometrisinden
   oluşan quasi-3D time-domain volume.
4. Çok-swath birleştirme sonraki sprintlere bırakılacak.
5. Undo/redo: immutable `GPRDataset` state yığını + cursor yaklaşımı.
6. Recipe: JSON kanonik format, YAML opsiyonel okunabilir format.
7. GPRPy: yalnızca mimari/UX/iş akışı referansı; kod kopyalanmayacak;
   herhangi bir kod uyarlaması için önceden ayrıca onay gerekecek.
8. GPRPy/CREWES/irlib migration kodları hiçbir koşulda kullanılmayacak.
9. PyInstaller paketleme Sprint 3D-2 sonrasına bırakılacak.
10. Mevcut IO/model/processing/QC/export/CLI davranışı korunacak.

## Completion Summary

Sprint GUI-0, kullanıcının GUI/3D dönüşüm audit talebini ve onayladığı
10 mimari kararı, hiçbir runtime kod yazmadan vault'a ADR + mimari
tasarım + risk kaydı olarak işledi; `pyproject.toml`'a GUI/3D
bağımlılıklarını opsiyonel gruplar olarak ekledi; ve untracked Sprint 4B
gain çalışmasını, ona dokunmadan, hash-doğrulamalı bir yedekle güvence
altına aldı. Bu sprint kendisi hiçbir test/kod değiştirmedi, ama
doğrulama turunda önceden var olan bir bulgu ortaya çıktı: ana çalışma
ağacında untracked gain WIP mevcutken `pytest` 343 passed/1 failed
veriyor (committed kod tabanının kendisi, bağımsız `git worktree`
doğrulamasıyla teyit edildiği üzere, hâlâ 0 failed'dir) — bkz. Issues
Discovered #3. İki açık karar (gain WIP
branch'i, GUI-0 değişikliklerinin hangi branch'te kalacağı) kullanıcıya
bırakıldı.

## Next Sprint Recommendation

**GUI-1 (uygulama kabuğu)** — yalnızca kullanıcının bu sprint raporunu
inceleyip ayrıca, açıkça onay vermesiyle başlayacak: `src/archaeogpr/gui/`
iskeleti (`__init__`, `__main__`, `app`, `main_window`), Open OGPR/
processed NPZ, kanal seçici, temel B-scan (PyQtGraph), A-scan, metadata
paneli, dosya okuma worker'da; `tests/gui/test_smoke.py` (pytest-qt,
mevcut `tests/conftest.py`'deki sentetik `.ogpr` byte builder'ı yeniden
kullanarak). Bkz. [[03_ARCHITECTURE/GUI_Architecture]],
[[01_PROJECT_STATE/02_Next_Development_Sprint]] (Sprint 4B/Gain ile
karıştırılmamalı — bu iki track birbirinden bağımsızdır).

## İlgili Notlar

[[06_DECISIONS/ADR_011_GUI_Technology_Decision]],
[[03_ARCHITECTURE/GUI_Architecture]],
[[03_ARCHITECTURE/3D_Volume_Data_Model]],
[[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]],
[[09_REFERENCES/GPRPy_Reference_and_License_Notes]],
[[01_PROJECT_STATE/06_GUI_3D_Risk_Register]],
[[01_PROJECT_STATE/01_Current_Project_State]],
[[01_PROJECT_STATE/02_Next_Development_Sprint]],
[[02_SPRINTS/Sprint_Index]]
