---
type: sprint
tags: [sprint, gui]
sprint: GUI-1B
status: done
started: 2026-07-18
completed: 2026-07-18
---

# Sprint GUI-1B — Background Tasks & Responsive File Loading

> **Kapsam:** Yalnızca büyük OGPR dosyaları açılırken GUI'nin donmaması,
> ilerleme durumunun gösterilmesi ve yüklemenin güvenli biçimde iptal
> edilebilmesi. **Bu sprintte processing algoritmaları GUI'ye
> bağlanmadı** — time-zero, DC offset, dewow, band-pass, background
> removal, gain, undo/redo, recipe, 3D hiçbiri eklenmedi. Temel karar
> kaydı: [[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]].

## Goal

`DatasetSession.load()`'daki GUI-1'den beri açık duran
`TODO: GUI-1B: file loading background worker` yorumunu kapatmak: dosya
okuma işlemini Qt ana thread'inden bir arka plan `QThread`'ine taşımak,
kullanıcıya ilerleme/durum göstermek, ve `main`'e daha yeni merge edilmiş
(PR #2, 2026-07-18) native viewer'ın GÜVENİLİRLİĞİNİ artırmak — yeni bir
kullanıcı-görünür özellik eklemek değil.

## Scope

- `src/archaeogpr/gui/workers/__init__.py`, `workers/file_loader.py`
  (yeni) — `FileLoadWorker` (QObject + worker-thread), `FileLoadState`
  enum.
- `src/archaeogpr/gui/models/dataset_session.py` — `commit_dataset()`
  (yeni, atomik commit), `load()` artık ona delege ediyor.
- `src/archaeogpr/gui/main_window.py` — `open_path()` artık worker
  başlatıyor, progress/Cancel UI (status bar), file-load state machine,
  `closeEvent()` güvenli kapanış.
- `src/archaeogpr/gui/app.py` — `--open --smoke-test` artık event loop'u
  yükleme bitene kadar pompalıyor, sonucu exit code'a çeviriyor.
- `tests/test_gui.py` — 22 yeni test + fix-round'da 8 yeni/2 kaldırılan
  test + fix-round-2'de 1 yeni test (toplam GUI testi: 45 → 67 → 73 → 74).
- Dokümantasyon: bu not, ADR-014, README, Current_Project_State,
  Next_Development_Sprint, Sprint_Index, Decision_Index, GUI_Architecture,
  Windows_Executable_Build.
- Version: `0.2.0` → `0.2.1` (patch — yeni kullanıcı-görünür davranış +
  güvenilirlik düzeltmesi).

## Out of Scope

Processing registry, time-zero/DC/dewow/band-pass/background-removal/gain
GUI'si, preview/apply, undo/redo, recipe, processed NPZ save, survey map,
depth conversion, picking, migration, PyVista/VTK, 3D, installer,
one-file, code signing, auto-update.

## Input Data

`data/raw/Swath003_Array02.ogpr` (gerçek dosya, ~8 MB) +
`tests/conftest.py`'deki `dataset_factory`/`valid_ogpr_path` fixture'ları
(yeniden kullanıldı). Yeni bir `_GatedReader`/`_ThreadRecorder` test
yardımcısı eklendi (bkz. Implementation Notes).

## Tasks

- [x] Repository/branch doğrulandı (`main` @ `009fb9d`, temiz).
- [x] `sprint-gui-1b-background-tasks` branch'i `main`'den açıldı.
- [x] `FileLoadWorker` + `FileLoadState` tasarlandı ve implemente edildi.
- [x] `DatasetSession.commit_dataset()` eklendi, `load()` ona delege
  ediyor.
- [x] `MainWindow.open_path()` worker/thread başlatacak şekilde yeniden
  yazıldı; progress/Cancel UI, state machine, `closeEvent()` eklendi.
- [x] `app.py`'nin `--open --smoke-test` yolu asenkron yüklemeyi
  bekleyecek şekilde güncellendi.
- [x] 22 yeni GUI testi yazıldı (toplam 67), 2 gerçek hata testler
  yazılırken bulundu ve düzeltildi (bkz. Issues Discovered).
- [x] Version `0.2.1`'e yükseltildi (tek source of truth korundu).
- [x] Dokümantasyon güncellendi (bu not, ADR-014, README ve 6 vault
  belgesi).
- [x] Final doğrulama: ruff/mypy/core/gui/vault validator.
- [x] Executable `0.2.1` olarak yeniden build edildi, yeni ZIP oluşturuldu.
- [x] Fix Round 2: close-pending race bulundu ve düzeltildi (`open_path()`
  guard'ı + `_close_pending`'in yalnızca gerçek kapanışta temizlenmesi).
- [x] Fix Round 2 regresyon testi eklendi (toplam GUI testi 73 → 74).
- [x] Final doğrulama tekrar çalıştırıldı (ruff/mypy/core/gui/vault
  validator), executable + ZIP yeniden build edilip doğrulandı.

## Acceptance Criteria

Kullanıcının orijinal talimatındaki 26. bölüm ("Son Rapor Formatı")
maddelerinin tamamı — bkz. bu sprintin sonuç raporu (kullanıcıya sunulan
mesaj).

## Implementation Notes

### Worker mimarisi: worker-object + `QThread`, `QThread` alt sınıfı değil

`FileLoadWorker`, `moveToThread()` ile bare bir `QThread`'e taşınan sade
bir `QObject`'tir — Qt'nin kendi önerdiği desen. Bu, `run()`'ın doğrudan
çağrılarak (hiç thread olmadan) success/failure sinyal testlerinde
izole test edilebilmesini sağlıyor.

### Kritik hata: lambda ile cross-thread sinyal bağlantısı GUI'yi çökertiyordu

İlk implementasyon, generation-counter'ı bir lambda closure'ı ile
taşıyordu: `worker.loaded.connect(lambda dataset, p, g=generation:
self._on_worker_loaded(g, dataset, p))`. Bu, gerçek bir **Windows access
violation** ile çöktü (`pyqtgraph`/Qt widget'larına worker thread'inden
erişim) — çünkü PySide6, bir cross-thread `AutoConnection`'ı yalnızca
receiver bir QObject'in bound method'u olduğunda `QueuedConnection`'a
çözebiliyor; bir lambda'nın (veya sonradan bir sınıfa/instance'a
monkeypatch edilmiş bir metodun — bu da testler yazılırken ayrıca
doğrulandı) hiçbir QObject receiver'ı yok, bu yüzden Qt sessizce
`DirectConnection`'a düşüyor ve slot **worker thread'inde** çalışıyor.

**Düzeltme:** her cross-thread sinyal artık doğrudan `self`
(`MainWindow`, ana thread'de yaşayan bir QObject)'in bound method'una
bağlanıyor — asla lambda, asla monkeypatch edilmiş bir wrapper. Detay ve
tam gerekçe: [[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]]
Decision madde 2.

### Stale-result rejection: `sender()` değil, sinyal payload'ındaki token

Lambda artık kullanılamadığı için generation counter bir closure'da
taşınamıyordu; `QObject.sender()`'ı denedik ama bu da queued/cross-thread
bağlantılarda güvenilmez çıktı (bir test bunu ampirik olarak doğruladı —
`sender()` taze bir sonucu yanlışlıkla "stale" olarak reddetti). Nihai
tasarım: her worker bir `token: int` ile construct ediliyor, her sinyal
bunu ilk argüman olarak taşıyor, `MainWindow` her handler'da
`self._current_load_token` ile karşılaştırıyor. Bkz. ADR-014 Decision
madde 3, `test_stale_worker_result_cannot_overwrite_newer_session`.

### Cancellation: kooperatif, asla `QThread.terminate()`

`read_ogpr()` tek bloklayıcı bir çağrı, iç cancellation noktası yok.
`request_cancel()` yalnızca bir flag set ediyor, çağrı öncesi/sonrası
kontrol ediliyor. Garanti: iptal edilmiş bir sonuç asla session'a commit
edilmiyor (okuma başarılı OLSA BİLE). Detay: ADR-014 Decision madde 4.

### `FileLoadState` enum + `_set_file_load_state()` merkezi fonksiyonu

`IDLE`/`LOADING`/`CANCELLING`/`SUCCESS`/`ERROR`/`CANCELLED`. Bulunan bir
gerçek hata: `__init__` içinde `_set_file_load_state(IDLE)` hiç
çağrılmıyordu — taze bir `QPushButton` varsayılan olarak enabled kalıyor,
bu yüzden Cancel butonu hiç yükleme başlamadan önce yanlışlıkla enabled
görünüyordu. `test_loading_state_disables_open_enables_cancel` bunu
yakaladı; `__init__` sonuna açık bir `_set_file_load_state(FileLoadState.IDLE)`
çağrısı eklendi.

### Progress: her zaman indeterminate, sahte yüzde yok

`read_ogpr()`'ın iç ilerleme callback'i yok — `load_progress_bar` her
zaman `(0, 0)` (Qt'nin indeterminate aralığı). Durum metinleri gerçek
işe karşılık geliyor ("Reading OGPR…" worker thread'deki bloklayıcı
çağrıdan hemen önce, "Updating viewer…" ana thread'deki gerçek
view-refresh'ten hemen önce), fabrike edilmiş bir yüzde/aşama yok.

### Shutdown (ilk versiyon, fix round'da değiştirildi — bkz. aşağıda)

İlk versiyon: `closeEvent()`: cancel iste → `thread.quit()` →
`wait(_SHUTDOWN_WAIT_MS=3000)`. Bitmezse: uyarı logla + `setParent(None)`
(Qt'nin hâlâ çalışan bir QThread'i yok etmeye çalışmasını önlemek için) —
`QThread.terminate()` asla çağrılmadı. **Bu tasarım kullanıcının pre-commit
review'ında güvensiz bulundu ve deferred-close tasarımıyla değiştirildi —
bkz. "Fix Round" bölümü.**

### Test altyapısı: `_GatedReader` + `_ThreadRecorder`, gerçek sleep yok

`_GatedReader`: `read_ogpr`'ı monkeypatch eden, `threading.Event` ile
kontrol edilen sahte bir okuyucu — testler ne zaman worker'ın bloklayıcı
çağrıya ulaştığını (`.started`) bilir ve ne zaman devam edeceğini
(`.release()`) kontrol eder; hiçbir gerçek zamanlı uzun sleep yok.
`_ThreadRecorder`: gerçek bir `QObject` alt sınıfı (thread-safety testi
için) — `MainWindow._on_worker_loaded`'ı monkeypatch etmenin (denendi,
başarısız oldu — yukarıdaki lambda/monkeypatch bulgusunun bir varyasyonu)
yerine ayrı, gerçek bir QObject'in bound method'unu ek bir bağlantı
olarak kullanıyor.

### Fix Round 2 — Close-Pending Race Düzeltmesi (2026-07-18, aynı gün)

Fix Round'un deferred-close tasarımı kabul edildikten sonra, bir sonraki
pre-commit review'da **kalan bir race condition** bulundu: eski
`_on_load_thread_finished()`, `self._close_pending`'i `self._load_thread`
temizliği ve `QTimer.singleShot(0, self.close)` retry'ının
zamanlanmasıyla **aynı senkron çağrı içinde** `False`'a çekiyordu. Bu
handler'ın dönüşü ile zamanlanan retry'ın gerçekten çalışması arasında
gerçek bir event-loop turu var — o turda hem `is_loading`
(`self._load_thread is not None`) hem de `_close_pending` zaten `False`
idi, yani programatik bir `open_path()` çağrısı tam o boşlukta hiçbir
guard tarafından reddedilmeden yeni bir yükleme başlatabilirdi (yeni
thread/worker gerçekten oluşur, reader ikinci kez çağrılırdı) — üstelik
uygulama zaten kapanmaya çalışırken.

**Düzeltme:** `_on_load_thread_finished`, `_close_pending`'i artık
temizlemiyor — bu yalnızca `closeEvent()`'in `if not self.is_loading:`
dalında, kapanış gerçekten kabul edilirken (`super().closeEvent(event)`
çağrılmadan hemen önce) yapılıyor. Bu, `_close_pending`'in ilk deferred
`closeEvent()` çağrısından pencerenin gerçekten kapandığı ana kadar
**kesintisiz** `True` kalmasını sağlıyor. `open_path()`'e de açık, önce
kontrol edilen bir guard eklendi: `if self._close_pending: return`
(mevcut `if self.is_loading: return`'den önce) — UI görünürlüğünden
bağımsız, programatik çağrıları da kapsayan, yapısal bir reddetme.

Yeni regression testi: `test_new_load_is_rejected_while_deferred_close_is_pending`
— `QTimer.singleShot`'u gerçek zamanlayıcı yerine bir listeye yakalayacak
şekilde monkeypatch ederek tam o boşluğu deterministik olarak tetikliyor;
yeni thread/worker/token oluşmadığını ve reader'ın ikinci kez
çağrılmadığını doğruluyor. Detay:
[[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]]
Decision madde 8 (ikinci fix-round bulgusu).

Toplam GUI testi: 73 → **74** (net +1; mevcut 73 testin hiçbiri
kaldırılmadı/değiştirilmedi).

### `qtbot` teardown + öksüz (orphaned) thread etkileşimi (ilk versiyonda gözlendi)

İlk versiyonun timeout/orphan testi ilk yazıldığında asılı kaldı (test
fonksiyonunun kendisi tamamlanıyordu, ama pytest hiç `PASSED` basmıyordu)
— kök neden: pytest-qt'nin `qtbot` fixture teardown'ı, izlediği bir
widget'ın hâlâ çalışan (owned/orphan) bir `QThread`'i varken asılı
kalıyordu. Fix round'daki deferred-close tasarımı thread'i asla "orphan"
bırakmadığı (her zaman `MainWindow` tarafından `thread.finished`'a kadar
izlendiği) için bu sorun artık kendiliğinden ortadan kalktı — yeni
testlerin hiçbirinde manuel bir `wait()` iş-arounduna gerek kalmadı.

### Fix Round — Shutdown/Cancellation Güvenlik Düzeltmesi (2026-07-18, aynı gün, henüz commit edilmemiş)

Kullanıcı ilk teslimatın (34-section rapor) shutdown yolunu pre-commit
review'da inceledi ve iki gerçek yaşam-döngüsü riski buldu — hiçbiri
otomatik testle daha önce yakalanmamıştı, ikisi de kod incelemesiyle
bulundu:

1. **`closeEvent()` GUI thread'ini 3000ms'e kadar bloklayan bir `wait()`
   çağrısı içeriyordu** — sprintin kendi "responsive GUI" hedefiyle
   doğrudan çelişiyordu.
2. **Timeout'ta `setParent(None)` ile "orphan" bırakma, çalışan bir
   `QThread`'i güvenli hale getirmiyordu** — yalnızca Qt'nin object-tree
   temizliğinin thread'i yok etmeye çalışmasını engelliyordu; MainWindow
   veya uygulamanın kendisi o sırada yok edilseydi risk hâlâ gerçekti.

**Düzeltme — deferred-close tasarımı** (bkz.
[[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]]
Decision madde 8 için tam detay): `closeEvent()` artık hiçbir `wait()`
çağrısı içermiyor. Yükleme sürüyorken: `_close_pending=True`, cancellation
token'ı hemen set edilir, state `CANCELLING`'e döner, `event.ignore()` +
`self.hide()` (pencere kullanıcıya "kapandı" gibi görünür ama
MainWindow/thread/worker nesneleri canlı kalır) — worker'ın kendi
`QThread.finished` sinyali ateşlendiğinde (`_on_load_thread_finished`)
referanslar temizlenir, state `IDLE`'a döner, ve `_close_pending` ise
`QTimer.singleShot(0, self.close)` ile kapanma yeniden denenir — bu kez
`is_loading` `False` olduğu için normal kabul edilir.

**Ek düzeltme — cancellation token artık `threading.Event`:** eskiden
düz bir `bool` attribute'du (`self._cancel_requested`); CPython'ın GIL'i
altında bu pratikte güvenliydi ama bu implicit bir yorumlayıcı detayıydı,
dokümante edilmiş bir garanti değildi. `MainWindow` artık bir
`threading.Event` oluşturuyor, worker'a constructor ile veriyor, ve
Cancel/close sırasında **doğrudan** `.set()` çağırıyor — worker'ın (var
olmayan) event loop'una hiç bağımlı değil.

**Ek düzeltme — cleanup sırası:** `self._load_thread`/`_load_worker`
temizliği artık `worker.finished` (token taşıyan ama thread'in OS
seviyesinde gerçekten bitmiş olduğunu garanti etmeyen) yerine
`thread.finished`'a (Qt'nin kendi, argümansız sinyali) taşındı. Bu, "stale
thread.finished başka bir aktif load'un referanslarını temizlememeli"
riskini bir kontrolle değil, **yapısal olarak** ortadan kaldırıyor:
`is_loading` (`self._load_thread is not None`) artık `open_path()`'in tek
otoriter "hâlâ devam eden bir yükleme var mı" kontrolü, ve bu yalnızca
`thread.finished`'da temizlendiği için, yeni bir yükleme eskisinin
thread'i gerçekten bitmeden asla başlayamıyor.

10 yeni/değiştirilmiş test eklendi (2 eski test — hem başarılı-bounded-wait
hem timeout/orphan senaryolarını test eden, artık var olmayan davranışı
test ediyorlardı — kaldırılıp yerine yeni deferred-close davranışını test
eden 8 test kondu; toplam GUI testi 67 → **73**).

## Validation Results

| Kontrol | Sonuç |
|---|---|
| `ruff format --check .` | ✅ temiz |
| `ruff check .` | ✅ All checks passed |
| `mypy src/archaeogpr` | ✅ 0 hata (54 dosya) |
| `pytest -m "not gui"` | ✅ 318 passed, 26 skipped, 74 deselected, 0 failed |
| `pytest -m gui` (offscreen) | ✅ **74 passed** (45 GUI-1/2 + 28 GUI-1B fix-round-1 + 1 GUI-1B fix-round-2), 344 deselected |
| `archaeogpr.gui --version` / `pip show archaeogpr` | ✅ ikisi de `0.2.1` |

### Fix-round regresyon testleri (net +6, toplam 73)

| Test | Kapsam |
|---|---|
| `test_close_while_blocked_defers_destruction` | A: bloklanmışken close, hiçbir şey yok edilmiyor |
| `test_close_completes_after_worker_finishes` | B: worker bitince deferred close tamamlanıyor |
| `test_cancel_token_is_set_immediately_even_while_worker_is_blocked` | C: token senkron/anında set ediliyor |
| `test_cancelled_load_preserves_previous_session` | D: geç gelen sonuç discard ediliyor (mevcut, korundu) |
| `test_cancellation_takes_precedence_over_a_late_failure` | E: cancel, geç hatadan önce geliyor (mevcut, korundu) |
| `test_load_thread_finished_cleanup_is_idempotent` | F: cleanup iki kez çağrılsa da güvenli |
| `test_outcome_handled_does_not_prematurely_clear_thread_reference` | G: stale-finished koruması (yapısal) |
| `test_no_qthread_destroyed_warning_during_deferred_close` | H: "Destroyed while running" uyarısı yok |
| `test_close_without_active_worker_accepts_immediately` | I: normal close hemen kabul ediliyor |
| `test_gui_remains_responsive_while_close_is_pending` | J: event loop close-pending sırasında da işliyor |

### Fix-round-2 regresyon testi (net +1, toplam 74)

| Test | Kapsam |
|---|---|
| `test_new_load_is_rejected_while_deferred_close_is_pending` | K: `_close_pending`/cleanup boşluğunda `open_path()` reddi (monkeypatch'lenmiş `QTimer.singleShot` ile deterministik) |

## Generated Outputs

Bu sprint `outputs/`'a hiçbir dosya yazmadı (görüntüleme/test kodu).
`dist/ArchaeoGPR/` `0.2.1` olarak yeniden build edildi (Fix Round 2'den
sonra tekrar); güncel ZIP:

- Yol: `C:\Dev\ArchaeoGPR-Releases\ArchaeoGPR-0.2.1-win64.zip`
- Boyut: `127,334,470` byte
- SHA-256: `125d95853916f4cdce873ae6faa1aa09bfcc34f87e345334e73be92830a223d6`

Eski `0.1.0`/`0.2.0` ZIP'leri değiştirilmedi/silinmedi.

## Issues Discovered

1. **Cross-thread lambda sinyal bağlantısı worker thread'inde direkt
   çalışıyor, GUI'yi çökertiyordu** — bu sprintin kendi test yazım süreci
   sırasında bulundu (review'da değil). Kök neden ve düzeltme: bkz.
   Implementation Notes ve
   [[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]].
2. **`QObject.sender()` queued/cross-thread bağlantılarda güvenilmez** —
   ilk stale-result-rejection tasarımı `sender()` kullanıyordu, testler
   yazılırken taze bir sonucun yanlışlıkla stale sayıldığı bulundu; token-
   in-payload tasarımına geçildi.
3. **`__init__` içinde `_set_file_load_state(IDLE)` çağrılmıyordu** —
   Cancel butonu başlangıçta yanlışlıkla enabled kalıyordu; bir testte
   yakalandı, tek satırlık düzeltme.
4. **pytest-qt `qtbot` teardown'ı öksüz bir QThread ile asılı kalıyor** —
   ilk versiyonda testin kendisi (`window._load_thread.wait()`) thread'in
   bitmesini garanti ederek düzeltilmişti; fix round'daki deferred-close
   tasarımı thread'i artık hiç "orphan" bırakmadığı için bu iş-around
   gerekmiyor (bkz. Fix Round).
5. **`closeEvent()` GUI thread'ini 3000ms'e kadar bloklayan bir `wait()`
   içeriyordu** — kullanıcının pre-commit review'ında bulundu (otomatik
   testle yakalanmadı). Deferred-close tasarımıyla düzeltildi — bkz. Fix
   Round, ADR-014 Decision madde 8.
6. **Timeout'ta `setParent(None)` ile "orphan" bırakma, çalışan bir
   `QThread`'i güvenli hale getirmiyordu** — aynı review'da bulundu. Aynı
   deferred-close düzeltmesiyle tamamen kaldırıldı.
7. **Cancellation flag düz bir `bool` idi, dokümante edilmiş bir
   thread-safety garantisi yoktu** — kullanıcının tercih ettiği çözümle
   (`threading.Event`) değiştirildi; CPython'ın GIL'i altında pratikte
   zaten güvenliydi, ama garanti implicit değil explicit olmalıydı.
8. **(Fix round 2) `_close_pending`, `_on_load_thread_finished` içinde
   `_load_thread` temizliğiyle aynı anda `False`'a çekiliyordu** —
   handler'ın dönüşü ile zamanlanan `QTimer.singleShot(0, self.close)`
   retry'ının çalışması arasındaki event-loop boşluğunda hem `is_loading`
   hem `_close_pending` `False` oluyordu, bu da programatik bir
   `open_path()` çağrısının shutdown-pending durumunu hiç görmeden yeni
   bir yükleme başlatabilmesine yol açıyordu — kullanıcının pre-commit
   review'ında bulundu. `_close_pending`'in yalnızca gerçek kabul edilen
   `closeEvent()`'te temizlenmesi + `open_path()`'e açık bir
   `_close_pending` guard'ı eklenmesiyle düzeltildi; bkz. Implementation
   Notes "Fix Round 2" ve ADR-014 Decision madde 8.

## Decisions

1. Worker-object + `QThread` (alt sınıflama değil).
2. Cross-thread sinyaller yalnızca bound method'lara bağlanır, asla
   lambda/monkeypatch.
3. Stale-result rejection: sinyal payload'ındaki token, `sender()` değil.
4. Cancellation kooperatif — `QThread.terminate()` asla kullanılmaz.
5. Progress her zaman indeterminate — sahte yüzde/aşama üretilmez.
6. **(Fix round)** Shutdown deferred: `closeEvent()` hiçbir zaman bloklamaz
   (`wait()` yok), pencere `hide()` edilir ama `MainWindow`/thread/worker
   `thread.finished`'a kadar canlı kalır, sonra kapanma yeniden denenir.
7. `DatasetSession.commit_dataset()` atomik commit'in tek yeri;
   `load()` ona delege eder.
8. **(Fix round)** Cancellation token `threading.Event` — GUI thread'i
   doğrudan `.set()` çağırır, worker event loop'una bağımlı değil.
9. **(Fix round)** `self._load_thread`/`_load_worker` temizliği
   `thread.finished`'da yapılır (`worker.finished`'da değil) — bu,
   stale-thread-finished riskini bir kontrolle değil yapısal olarak ortadan
   kaldırır (`is_loading` tek otoriter "hâlâ devam ediyor" bayrağı olur).
10. **(Fix round 2)** `_close_pending` yalnızca `closeEvent()`'in kapanışı
    gerçekten kabul ettiği anda temizlenir (artık `_on_load_thread_finished`
    içinde değil) — bu, ilk deferred `closeEvent()`'ten pencerenin
    gerçekten kapandığı ana kadar kesintisiz `True` kalmasını sağlar.
    `open_path()`, `_close_pending` iken yeni yüklemeyi UI görünürlüğünden
    bağımsız, açıkça reddeder.

## Completion Summary

`DatasetSession.load()`'daki GUI-1'den beri açık TODO kapatıldı: dosya
yükleme artık ana thread'i bloklamıyor, ilerleme/Cancel gösteriyor, ve
iptal/hata durumunda mevcut session'ı asla bozmuyor. İlk teslimat (34
bölümlük rapor) sonrası kullanıcının pre-commit review'ı shutdown yolunda
iki gerçek yaşam-döngüsü riski buldu (bloklayan `wait()`, güvensiz
orphan-thread bırakma) — deferred-close tasarımıyla düzeltildi, ayrıca
cancellation token `threading.Event`'e taşındı ve cleanup sırası
`thread.finished`'a hizalandı. Bir sonraki pre-commit review'da **kalan
bir race condition** daha bulundu: `_close_pending`'in `_on_load_thread_finished`
içinde erken temizlenmesi, cleanup ile deferred retry arasındaki
event-loop boşluğunda `open_path()`'in shutdown-pending durumunu
kaçırmasına yol açabiliyordu — `_close_pending`'in yalnızca gerçek kabul
edilen `closeEvent()`'te temizlenmesi ve `open_path()`'e açık bir guard
eklenmesiyle düzeltildi (Fix Round 2). Toplamda 31 yeni/değiştirilmiş test
(net +7, toplam **74** GUI testi) üç turun bulgularını da kilitliyor. Bu
süreçte ayrıca gerçek, ciddi bir threading hatası (worker-thread'den GUI
erişimi → çökme) bulundu ve düzeltildi; üçünün de kök nedeni ve düzeltmesi
ADR-014'te tam olarak belgelendi. Bu belgeyi de içeren tüm değişiklik seti
(orijinal GUI-1B + Fix Round 1 + Fix Round 2), kullanıcının onayı üzerine
tek bir commit olarak `sprint-gui-1b-background-tasks` branch'ine
kaydedilip origin'e push edilir.

## Next Sprint Recommendation

Kullanıcının kendi isteğiyle: **GUI-3** (processing entegrasyonu — bkz.
[[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]]) veya 3D/gridding
track'inin başlangıcı (bkz. [[03_ARCHITECTURE/3D_Volume_Data_Model]]).

## İlgili Notlar

[[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]],
[[06_DECISIONS/ADR_013_Display_Policy_and_Non_Destructive_Visualization]],
[[06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime]],
[[06_DECISIONS/ADR_011_GUI_Technology_Decision]],
[[02_SPRINTS/Sprint_GUI_2_Display_Controls]],
[[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]],
[[09_REFERENCES/Windows_Executable_Build]], [[02_SPRINTS/Sprint_Index]]
