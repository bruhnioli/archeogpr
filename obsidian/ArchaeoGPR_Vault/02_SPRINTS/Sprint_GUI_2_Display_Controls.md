---
type: sprint
tags: [sprint, gui]
sprint: GUI-2
status: done
started: 2026-07-17
completed: 2026-07-17
---

# Sprint GUI-2 — Display Controls & Interaction

> **Kapsam:** Yalnızca interaktif görüntüleme kontrolleri (kontrast,
> colormap, A-scan modları, metadata okunabilirliği, PNG export) ve
> `0.2.0` executable'ı. **Bu sprintte veri işleme YOK** — time-zero, DC
> offset, dewow, band-pass, background removal, gain, migration, 3D,
> depth conversion hiçbiri eklenmedi. Temel ilke:
> [[06_DECISIONS/ADR_013_Display_Policy_and_Non_Destructive_Visualization]].

## Goal

Kullanıcının GUI-1'in manuel demosunda gözlemlediği gerçek, beklenen bir
sonucu — ham verinin geniş dinamik aralığının (8-12 ns civarındaki güçlü
doğrudan geliş/anten kuplajı) sabit bir kontrast aralığını domine etmesi —
kullanıcının kendi kontrolünde, veriye hiç dokunmadan çözmesini sağlamak.

## Scope

- `src/archaeogpr/gui/models/display_settings.py` (yeni) — `DisplaySettings`
  + `compute_display_levels()`.
- `src/archaeogpr/gui/export.py` (yeni) — PNG export + `.display.json`
  sidecar.
- `views/bscan_view.py` — render pipeline refactoru, merkezi colormap LUT,
  visible-range autoscale, trace-tıklama `floor()` düzeltmesi.
- `views/ascan_view.py` — full/robust/normalize modları, x=0 referans
  çizgisi, başlıkta trace/channel/peak/mod bilgisi.
- `views/metadata_panel.py` — Value sütunu stretch, tooltip, kopyalama
  context menüsü.
- `main_window.py` — Display kontrol paneli (colormap, percentile,
  symmetric/manual, autoscale, Auto Levels/Reset View/Reset Display,
  A-scan modu), ayrı selected/cursor status etiketleri, display özeti,
  PNG export menü aksiyonu, layout ayarları.
- `tests/test_gui.py` — 23 yeni test (toplam 35).
- `.github/workflows/ci.yml` — ayrı `gui` job'ı.
- `pyproject.toml` — `dynamic = ["version"]` (tek source of truth:
  `archaeogpr.__version__`).
- `src/archaeogpr/__init__.py` — `__version__ = "0.2.0"`.
- `packaging/archaeogpr.spec` — değişmedi (aynı entry point).
- Dokümantasyon: bu not, ADR-013, README, `Windows_Executable_Build.md`,
  vault index güncellemeleri.

## Out of Scope

Processing registry, processing dialogları (time-zero/DC/dewow/band-pass/
background/gain GUI), preview/apply, undo/redo, recipe, processed NPZ
save, background file-loading worker, survey map, depth conversion,
velocity editor, hyperbola fitting, picking, annotation, migration,
PyVista, VTK, 3D grid, time/depth slice, one-file build, installer,
auto-update, code signing, main merge, GitHub Release.

## Input Data

`data/raw/Swath003_Array02.ogpr` (gerçek dosya) + `tests/conftest.py`'deki
`dataset_factory`/`valid_ogpr_path` fixture'ları (yeniden kullanıldı, yeni
bir builder yazılmadı).

## Tasks

- [x] Repository/branch/Qt ortamı doğrulandı (`sprint-gui-1-viewer-shell`
  @ `cf24ab8`, temiz, gain yok).
- [x] `sprint-gui-2-display-controls` branch'i `cf24ab8`'den açıldı.
- [x] `DisplaySettings` + `compute_display_levels()` yazıldı.
- [x] Merkezi colormap LUT (`colormap_lookup_table()`, matplotlib
  gray/seismic'ten örneklenmiş) + B-scan render pipeline refactoru.
- [x] Percentile (90-100, adım 0.1, varsayılan 99.0), symmetric/asymmetric,
  manual levels (geçersizse otomatik fallback) implemente edildi.
- [x] Display kontrol paneli (colormap, percentile spin+slider,
  symmetric/manual checkbox, min/max, autoscale, 3 buton, A-scan modu).
- [x] A-scan full/robust/normalize modları + x=0 çizgisi + başlık bilgisi.
- [x] Trace seçimi 0/80/174 sınırlarında doğrulandı, `floor()` düzeltmesi
  yapıldı (bkz. Implementation Notes).
- [x] Status bar: ayrı "Selected trace" ve "Cursor" etiketleri + display
  özeti (permanent widget).
- [x] Metadata paneli: Value stretch, tooltip, kopyalama context menüsü.
- [x] PNG export + `.display.json` sidecar.
- [x] Layout: dock min-width, splitter, resizeDocks.
- [x] Performans: percentile hesaplama benchmark edildi (~2.2 ms/çağrı) —
  cache eklenmedi (gerekçe: Implementation Notes).
- [x] 23 yeni test yazıldı (toplam GUI testi: 35), hepsi offscreen geçti.
- [x] CI'a ayrı `gui` job'ı eklendi (Windows runner, offscreen,
  `pytest -m gui`).
- [x] Version tek source of truth yapıldı (`pyproject.toml`
  `dynamic=["version"]` → `archaeogpr.__version__`), `0.1.0` → `0.2.0`.
- [x] Dokümantasyon (bu not, ADR-013, README, `Windows_Executable_Build.md`,
  vault index düzeltmeleri — GUI-1/ADR-012 satırları da eksikti, birlikte
  eklendi).

## Acceptance Criteria

Kullanıcının orijinal talimatındaki 28. bölüm ("Son Rapor Formatı")
maddelerinin tamamı — bkz. bu sprintin sonuç raporu (kullanıcıya sunulan
mesaj).

## Implementation Notes

### Manual levels ↔ symmetric mode kararı

Seçenek B uygulandı: Manual levels açıldığında Symmetric otomatik olarak
kapanıyor (iki checkbox arasında karşılıklı dışlama). Gerekçe ve
alternatif A'nın neden reddedildiği:
[[06_DECISIONS/ADR_013_Display_Policy_and_Non_Destructive_Visualization]].
Manual alanlar ilk açıldığında geçerli otomatik seviyelerle
dolduruluyor (0/0'dan başlamak yerine).

### Geçersiz manual level'ın render pipeline'a asla ulaşmaması

`compute_display_levels()` — manual etkin ama `min >= max` veya
non-finite ise **sessizce** otomatik (symmetric/asymmetric) hesaplamaya
düşüyor. UI ayrıca alanları kırmızı arka planla işaretliyor — bu iki
mekanizma birbirinden bağımsız (UI'daki bir hata pipeline'ın bozuk bir
aralık üretmesine asla yol açamaz, çünkü fallback UI'nin fark etmesine
bağlı değil).

### Trace tıklama — `int()` yerine `math.floor()`

`_trace_and_sample_at()`'te `trace = int(view_point.x())` idi;
Python'da `int()` sıfıra doğru keser, `floor()` değil — negatif kenar
durumunda (`view_point.x()` çok küçük negatif bir değerse) yanlışlıkla
trace 0'a "yapışabilirdi". `math.floor()`'a geçildi. Trace 0, 80 ve 174
sınırlarında hem doğrudan koordinat hesabıyla hem de gerçek
`_on_mouse_clicked` yolu üzerinden (sahte mouse event + zoom'lu bir
view ile) test edildi — hepsi doğru trace'i seçiyor.

### Visible-range autoscale ertelenmedi, tam implemente edildi

Görev talimatı "karmaşıklık gereksiz büyürse GUI-2B TODO'ya bırakabilirsin"
diyordu, ama gerçek karmaşıklık makul çıktı:
`ViewBox.sigRangeChanged` → 200ms debounce (tek seferlik `QTimer`) →
görünen zaman aralığını `time_ns` üzerinde `searchsorted` ile örnek
aralığına çevir → yalnızca o dilimden robust seviye hesapla →
`ImageItem.setLevels()`. Zoom/pan sırasında her ara karede değil, yalnızca
hareket durduktan sonra bir kez hesaplanıyor.

### Performans: cache eklenmedi (ölçülerek karar verildi)

Gerçek örnek veri (175×1024, tek kanal) üzerinde `compute_display_levels()`
200 çağrıda 443 ms → **~2.2 ms/çağrı**. Bu, herhangi bir algılanabilir
UI gecikmesi eşiğinin (16ms/60fps) çok altında — cache eklenmedi, erken
optimizasyon yapılmadı. `ImageItem` her ayar değişiminde yeniden
oluşturulmuyor, yalnızca `setLevels()`/`setLookupTable()` çağrılıyor
(yalnızca `set_data()` — kanal değişimi/dosya açma — `setImage()`
çağırıyor).

### PNG export, `qc/bscan.py::plot_bscan`'i yeniden kullanmadı

`plot_bscan`'in `vlimit` parametresi yalnızca simetriktir
(`vmin=-limit, vmax=limit`); GUI-2'nin asymmetric/manual (simetrik
olmayan) seviyeleri de doğru export edebilmesi gerekiyordu. Bu yüzden
`archaeogpr/gui/export.py::export_bscan_png()` ayrı, küçük bir fonksiyon
olarak yazıldı — `(vmin, vmax)` tuple'ı doğrudan kabul ediyor, aynı
matplotlib `imshow`/`origin="upper"` kuralını koruyor (görsel tutarlılık).

### Version: tek source of truth

`pyproject.toml`'da `version = "0.1.0"` sabit stringi, `dynamic =
["version"]` + `[tool.setuptools.dynamic] version = {attr =
"archaeogpr.__version__"}` ile değiştirildi — artık `src/archaeogpr/
__init__.py`'deki `__version__` tek kaynak. `pip install -e .` yeniden
çalıştırılarak paket metadata'sı yenilendi; `pip show archaeogpr` ve
`python -m archaeogpr.gui --version` ikisi de `0.2.0` gösteriyor.

### Vault index düzeltmesi (GUI-1'den kalan eksiklik)

`Sprint_Index.md`'de GUI-1 satırı ve `Decision_Index.md`'de ADR-012
satırı, GUI-1 sprintinde eklenmemiş olduğu fark edildi — bu sprintte
GUI-2/ADR-013 ile birlikte ikisi de eklendi.

## Validation Results

| Kontrol | Sonuç |
|---|---|
| `ruff format --check .` | ✅ temiz |
| `ruff check .` | ✅ All checks passed |
| `mypy src/archaeogpr` | ✅ 0 hata |
| `pytest -m "not gui"` | ✅ 318 passed, 26 skipped, 45 deselected, 0 failed |
| `pytest -m gui` (offscreen) | ✅ **45 passed** (12 GUI-1 + 23 GUI-2 ilk teslim + 10 fix-round regresyon), 344 deselected |
| Manuel doğrulama scripti (offscreen) | ✅ trace 0/80/174, percentile/symmetric/asymmetric/manual (+ geçersiz fallback), colormap, A-scan normalize, reset display, dataset immutability, metadata stretch, PNG+sidecar — hepsi geçti |
| Percentile benchmark | ~2.2 ms/çağrı (175×1024 gerçek veri) |
| `archaeogpr.gui --version` / `pip show archaeogpr` | ✅ ikisi de `0.2.0` |

### Fix-round regresyon testleri (10 yeni, toplam 45)

| # | Test | Kapsam |
|---|---|---|
| 36 | `test_ascan_normalize_mode_is_visible_with_correct_range` | Normalize görünür + X range tam olarak `[-1.05, 1.05]` |
| 37 | `test_ascan_normalize_to_full_restores_raw_scale` | Normalize→Full: ham eğri + ham ölçek X range döner |
| 38 | `test_ascan_normalize_to_robust_uses_raw_percentile_range` | Normalize→Robust: ham eğri + robust percentile range |
| 39 | `test_ascan_time_axis_matches_dataset_bounds_and_blocks_overshoot_pan` | İlk yükleme = gerçek sınırlar, overshoot pan clamp edilir, Reset View sınırlara döner |
| 40 | `test_ascan_time_axis_preserves_negative_time_zero_minimum` | Negatif time-zero ekseni (`time_ns` min≠0) korunur |
| 41 | `test_manual_and_visible_autoscale_are_mutually_exclusive` | Manual↔visible-autoscale iki yönlü karşılıklı dışlama |
| 42 | `test_display_summary_shows_single_active_mode` | Özet etiket 4 moddan yalnızca birini gösterir |
| 43 | `test_visible_range_autoscale_recomputes_from_visible_samples_only` | Visible-range autoscale gerçekten yalnızca görünür örneklerden hesaplıyor (fonksiyonel doğrulama, yalnızca checkbox görünürlüğü değil) |
| 44 | `test_visible_region_autoscale_skipped_when_manual_active` | Manual aktifken visible-range hesaplaması hiç çağrılmıyor |
| 45 | `test_cursor_status_reflects_current_channel_after_switch` | Stale-cursor regresyon kilidi (channel 00→05 sonrası cursor metni doğru kanalı gösteriyor) |

## Generated Outputs

Bu sprint `outputs/`'a hiçbir dosya yazmadı (görüntüleme/test kodu).
`dist/ArchaeoGPR/` 0.2.0 olarak yeniden build edilecek (bkz. rapor).

## Issues Discovered

1. **GUI-1'de `Sprint_Index.md`/`Decision_Index.md` güncellenmemişti** —
   bu sprintte düzeltildi (bkz. Implementation Notes).
2. **`int()` truncate-toward-zero, trace tıklamada teorik bir kenar-durum
   riskiydi** — `math.floor()`'a geçilerek düzeltildi (kod hatası değil,
   önleyici düzeltme; gerçek veride gözlemlenen yanlış bir seçim yoktu).

### Fix Round — Manuel Test Sonrası Düzeltmeler (2026-07-17)

Kullanıcının ilk teslimat sonrası yaptığı ikinci manuel görsel testte 2
gerçek görüntüleme hatası + 1 UX çakışması bulundu (commit/push henüz
yapılmamışken, aynı `sprint-gui-2-display-controls` branch'i üzerinde
düzeltildi — version `0.2.0` sabit kaldı, henüz commit edilmemiş bir
sprint'in patch'i artırılmaz).

3. **Normalize for display modunda A-scan eğrisi görünmez oluyordu** —
   kök neden: `ascan_view.py::_redraw()`'daki X-range if/elif zincirinde
   `"normalize"` için hiçbir dal yoktu (yalnızca `"robust"` ve `"full"`
   ele alınıyordu). Sonuç: X ekseni bir önceki Full/Robust modundan kalan
   ham genlik ölçeğinde (~±60000) kalıyordu, normalize edilmiş eğri
   (~[-1, +1]) o ölçekte piksel genişliğinde bir çizgiye sıkışıp görsel
   olarak kayboluyordu. **Düzeltme**: `elif self._mode == "normalize":
   self.view_box.setXRange(-1.05, 1.05, padding=0.0)` — açık, koşulsuz bir
   dal eklendi. Mod geçişleri (Normalize↔Full, Normalize↔Robust) ayrı ayrı
   regresyon testleriyle doğrulandı (bkz. Validation Results).
4. **A-scan zaman (Y) ekseni dataset sınırlarının çok dışına taşıyordu**
   (128 ns'lik veri için 200-225 ns) — kök neden: A-scan Y ekseni hiçbir
   zaman `dataset.time_ns`'den açıkça türetilmiyordu; yalnızca pyqtgraph'ın
   örtük `enableAutoRange()`/padding mekanizmasına güveniliyordu, bu da
   panning/zoom sonrası gerçek sınırların dışına taşınabiliyordu.
   **Düzeltme**: `AScanView._apply_time_axis_bounds()` her zaman
   `dataset.time_ns`'in gerçek `min()`/`max()`'ini (hardcode 0 varsaymadan,
   gelecekteki time-zero-relative negatif eksenler için) hesaplayıp
   `ViewBox.setLimits(yMin=, yMax=)` ile sert bir pan/zoom sınırı koyuyor;
   `force_reset=True` (yalnızca ilk yükleme ve `reset_view()`) ile mevcut
   görünüm de tam sınırlara sıfırlanıyor. Kanal/trace/mod değişiminde
   kullanıcının zoom'u korunuyor (yalnızca limitler yeniden uygulanıyor,
   `BScanView` ile aynı davranış). Yeni `AScanView.reset_view()` metodu
   `main_window.py`'nin Reset View butonuna bağlandı.
5. **Manual levels ve Visible-range autoscale aynı anda işaretli
   kalabiliyordu** — iki çakışan seviye kaynağı arasında UI hiçbir karşılıklı
   dışlama uygulamıyordu. **Düzeltme**: `main_window.py::_on_manual_toggled`
   artık manual açılınca autoscale checkbox'ını hem uncheck hem disable
   ediyor; `_on_autoscale_toggled` simetrik bir savunma satırı içeriyor.
   `BScanView._visible_region_autoscale_active()` (yeni) render pipeline
   seviyesinde de bunu garanti ediyor — `visible_region_autoscale=True`
   VE `manual_levels_enabled=True` aynı anda olsa bile (örn. `DisplaySettings`
   doğrudan oluşturulursa) visible-range hesaplaması **hiç çalışmıyor**,
   yalnızca manual değerler uygulanıyor. Display özet etiketi de artık 4
   ayrı, birbirini dışlayan modu (`symmetric`/`asymmetric`/`manual`/
   `visible-range auto`) gösteriyor — önceden `visible-range auto` hiç
   ayrı bir etiket olarak gösterilmiyordu.

Üçü de kullanıcının **gerçek bir çalışan build üzerinde yaptığı manuel
görsel testte** bulundu — hiçbiri otomatik testlerle önceden yakalanmamıştı
(regresyon testleri bu turda eklendi, bkz. Validation Results).

## Decisions

1. Manual levels açılınca symmetric otomatik kapanır (seçenek B).
2. Visible-range autoscale ertelenmedi, tam implemente edildi.
3. Cache eklenmedi (ölçülerek: gereksiz).
4. PNG export ayrı bir modülde (`gui/export.py`), `qc/bscan.py`'den
   bağımsız.
5. Version tek source of truth: `archaeogpr.__version__`.
6. Colormap LUT merkezi tek fonksiyonda (`bscan_view.py` içinde, ayrı
   dosya değil).
7. **(Fix round)** A-scan Y ekseni her zaman `dataset.time_ns` gerçek
   min/max'ından türetilir, hiçbir zaman `time_ns[0]`/`0` varsayılmaz;
   `ViewBox.setLimits()` sert bir pan/zoom sınırı olarak kalıcıdır, ancak
   *view sıfırlama* yalnızca ilk yükleme ve Reset View'de olur (kanal/
   trace/mod değişiminde kullanıcının zoom'u korunur).
8. **(Fix round)** Manual levels ve Visible-range autoscale iki yönlü
   karşılıklı dışlanır (UI + render pipeline seviyesinde çift savunma) —
   aynı anda iki farklı level kaynağı asla aktif görünmez/çalışmaz.

## Completion Summary

Kullanıcının GUI-2 hedefinin tamamı (kontrast/colormap/A-scan modları/
metadata okunabilirliği/status readout/PNG export/0.2.0 executable)
veri işlemeye hiç dokunmadan teslim edildi — her adımda
`dataset.amplitudes` immutability ve hash değişmezliği ayrıca test
edildi. İlk teslimattan sonra kullanıcının ikinci manuel görsel testinde
bulduğu 2 görüntüleme hatası + 1 UX çakışması aynı branch üzerinde
düzeltildi (bkz. Issues Discovered → Fix Round), 10 yeni regresyon testiyle
kilitlendi (toplam 45 GUI testi). **Commit/push henüz yapılmadı** —
kullanıcının onayı bekleniyor.

## Next Sprint Recommendation

Kullanıcının kendi isteğiyle: **GUI-3** (processing entegrasyonu — bkz.
[[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]]) veya **GUI-1B**
(background file-loading worker, GUI-1'den beri açık TODO).

## İlgili Notlar

[[06_DECISIONS/ADR_013_Display_Policy_and_Non_Destructive_Visualization]],
[[06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime]],
[[06_DECISIONS/ADR_011_GUI_Technology_Decision]],
[[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]],
[[09_REFERENCES/Windows_Executable_Build]], [[02_SPRINTS/Sprint_Index]]
