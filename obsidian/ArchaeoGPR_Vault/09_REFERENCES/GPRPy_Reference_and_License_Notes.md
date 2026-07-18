---
type: reference
---

# GPRPy Reference and License Notes

## Amaç ve Kapsam

`archaeogpr`'ın GUI/3D dönüşümü, [NSGeophysics/GPRPy](https://github.com/NSGeophysics/GPRPy)
reposunu **yalnızca** aşağıdaki konularda referans olarak kullanır:

- GPR kullanıcı iş akışı
- profil görüntüleme
- processing menülerinin organizasyonu
- picking yaklaşımı
- undo ve processing history davranışı
- processing parametrelerinin kullanıcıdan alınması
- işleme zincirinin tekrar çalıştırılabilir olması
- profil ve CMP/WARR çalışma modlarının organizasyonu

**GPRPy fork edilmemiştir ve yeni ana proje olarak kullanılmamıştır.**
GPRPy'nin Tkinter GUI mimarisi aynen kopyalanmamıştır — bkz.
[[03_ARCHITECTURE/GUI_Architecture]]. Bu nota kadar (Sprint GUI-0,
2026-07-17) GPRPy'den `archaeogpr`'a **hiçbir kod satırı kopyalanmamış
veya uyarlanmamıştır** — yalnızca mimari/UX fikirleri, aşağıda madde madde
kaynağıyla birlikte kaydedilmiştir.

## Lisans

**GPRPy: MIT License.** Tam telif satırı (`LICENSE`):
`Copyright (c) 2018 Near Surface Geophysics`. Standart MIT metni
(kopyalama/değiştirme/dağıtma serbest, telif+izin bildirimi korunmalı,
"AS IS" garanti yok). Atıf talebi (yasal zorunluluk değil, proje kendi
`pleaseCite.txt`'inde rica ediyor): Plattner (2020), DOI
`10.1190/tle39050332.1`.

**Kritik istisna — fk migration KODU MIT DEĞİLDİR ve GPRPy reposuna
dahil bile değildir.** GPRPy'nin `gprpy/toolbox/mig_fk.py`'ı, kurulum
sırasında ayrı bir script (`installMigration.py`) tarafından
`https://github.com/AlainPlattner/irlib.git`'ten (Nat Wilson'ın
CREWES-türevli Python 2 kodunun bir fork'u) indirilir; GPRPy'nin kendi
kurulum script'i bunu **"you are downloading an external software with a
more restrictive license"** uyarısıyla yapar. GPRPy'nin kendi GUI
tooltip'i migration'ı şöyle nitelendiriyor: *"Stolt's fk migration using
a code originally written in Matlab for the CREWES software package.
Translated into Python 2 by Nat Wilson."*

**Bu projenin politikası (kullanıcı talimatı ile sabit):
CREWES/irlib/Nat Wilson fk-migration kodu hiçbir koşulda kullanılmaz
veya uyarlanmaz.** Migration bir gün implemente edilirse (ADVANCED
sprint, henüz planlanmadı), bağımsız, literatür-tabanlı (örn. Stolt
1978'in orijinal makalesinden) bir implementasyon yazılacak ve bu karar
kendi ADR'ında kayıt altına alınacaktır.

## Kod Alınırsa Gereken Dokümantasyon (henüz uygulanmadı — bu bölüm bir şablon)

Eğer ileride GPRPy'den doğrudan veya önemli ölçüde kod alınırsa (yalnızca
ayrı, açık kullanıcı onayıyla — bkz. Sprint GUI-0 talimatı madde 7),
burada şu dört alan kayıt altına alınacaktır: **(1)** kaynak dosya
(GPRPy'deki tam yol), **(2)** orijinal fonksiyon/sınıf adı, **(3)**
yapılan değişiklik (satır satır veya özet), **(4)** MIT lisans/telif
bildirimi (yukarıdaki tam metin). Şu ana kadar bu tablo **boştur** —
hiçbir satırı doldurulacak bir kopyalama olmamıştır.

## Alınan Fikirler ve Kaynakları (fikir düzeyinde, kod değil)

| Fikir | GPRPy'deki kaynağı | `archaeogpr`'daki karşılığı (tasarım) |
|---|---|---|
| İşlem sırasını GUI panel düzeniyle öğretme | `gprpyGUI.py` sağ sütun (import→adjProfile→...→pick→export) | Processing panel sırası [[05_PROCESSING/Processing_Order]]'ı yansıtır |
| Y-ekseni domain geçişi (time→depth→elevation) | `plotProfileData` (`velocity`/`maxTopo` `None`-sentinel dallanması) | Explicit `AxisDomain` enum + görünür hız/kaynak etiketi — bkz. [[03_ARCHITECTURE/GUI_Architecture]] |
| Çalıştırılabilir işlem geçmişi export'u | `writeHistory()` → çalıştırılabilir `.py` scripti | Yapısal JSON/YAML recipe + `apply_recipe()` — bkz. [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]] |
| Tek kaydıraçla simetrik contrast aralığı | `plotProfileData`'daki `contrast` `DoubleVar` | Percentile + manuel min/max + simetrik mod üçlüsü (genelleştirilmiş) |
| Her kontrole mikro-dokümantasyon (tooltip) | `Pmw.Balloon()` her butonda | Qt tooltip'leri |
| Nearest-neighbor'ı maliyet gerekçesiyle varsayılan seçme, opsiyonel smoothing | `makeDataCube(method='nearest', smooth=...)` | [[03_ARCHITECTURE/3D_Volume_Data_Model]] — ama maskesiz doldurma yerine açık `missing_mask` |
| Picking export biçimi (profil + 3D koordinat) | `startPicking`/`stopPicking`, `_profile.txt`/`_3D.txt` | ADVANCED sprint referansı (henüz tasarlanmadı) |
| CMP/WARR'ın ayrı bir çalışma modu olması | `gprpyCW`/`GPRPyCWApp` | Mimaride "workspace mode" kavramı için yer ayrıldı — implementasyon ADVANCED |

## Alınmayan Mimari Unsurlar (bilinçli olarak reddedildi)

Aşağıdakiler GPRPy kaynak kodunun doğrudan okunmasıyla tespit edilmiştir
ve **hiçbir şekilde** yeni GUI'ye taşınmayacaktır:

- **Tkinter + modül-global layout sabitleri + closure'a yakalanmış tek
  `proj` nesnesi** (`gprpyGUI.py`) — çoklu dosya/sekme desteğini
  imkânsız kılıyor. Bkz. [[06_DECISIONS/ADR_011_GUI_Technology_Decision]]
  Alternatives Considered.
- **History'nin çalıştırılabilir Python kaynak-string listesi olması**
  (`self.history.append("mygpr.dewow(%d)" % window)`) — hard-coded
  `mygpr` değişken adı, `%g`/`%d` formatlamasıyla hassasiyet kaybı,
  replay = script'i elle çalıştırmak.
- **Tek seviyeli, referans-kopyalı undo, redo yok**
  (`self.previous = {"data": self.data, ...}`) — `gprpyProfile` ve
  `gprpyCW`'nin `storePrevious()`'ları farklı alan setleri saklıyor,
  tek `undo()` ile tutarsız (latent bug).
- **Render mantığının üç ayrı yerde kopyası**
  (`prepProfileFig`, `plotProfileData`, `plotCWData`/`plotStAmp`).
- **`numpy.matrix` kullanımı** (deprecated, 2D'ye zorluyor).
- **Pozisyonel, versiyonsuz `pickle` persistence** (`.gpr` dosyaları —
  13 elemanlı liste, güvensiz, alan sırası/sayısı değişirse kırılıyor).
- **String identity karşılaştırmaları** (`if self.dtype is "WARR"`) ve
  uyarı gösterip **yine de işlemi çalıştıran** hata yolları
  (`antennaSep`/`fkMigration` GUI çağrıları).
- **Saf Python for-döngülü kayan pencere filtreleri**
  (`dewow`/`smooth`/`remMeanTrace`/`agcGain`) — O(n·window), yavaş.
- **Hard-coded figure boyutları ve ekran-oranı hack'leri**
  (`Figure(figsize=(9,5))`, `widfac=1280/720`).

## GPRPy'nin Veri/Undo Mimarisi — Kısa Teknik Özet (karşılaştırma için)

`gprpyProfile` durumu düz bir attribute çantasıdır (`self.data` bir
`numpy.matrix`, `self.info` bir dict, `self.history` bir liste,
`self.previous` bir dict). `undo()`, `self.previous`'tan alanları geri
yükler ve `history`'nin son elemanını siler — **tek seviyeli**, tekrar
`undo()` çağrısı ikinci bir adımı geri almaz. `storePrevious()`
referansları kopyalar (`self.previous["data"] = self.data`), sadece her
işlem `self.data`'yı **yeniden atadığı** (yerinde değiştirmediği) için
güvenlidir. `archaeogpr`'ın `GPRDataset` immutability'si (bkz.
[[06_DECISIONS/ADR_001_OpenGPR_Internal_Data_Model]]) bu kırılganlığı
başından beri yapısal olarak önlüyor — bkz.
[[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]].

## İlgili Notlar

- [[03_ARCHITECTURE/GUI_Architecture]]
- [[03_ARCHITECTURE/3D_Volume_Data_Model]]
- [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]]
- [[06_DECISIONS/ADR_001_OpenGPR_Internal_Data_Model]]
- [[06_DECISIONS/ADR_011_GUI_Technology_Decision]]
- [[01_PROJECT_STATE/06_GUI_3D_Risk_Register]]
- [[02_SPRINTS/Sprint_GUI_0_Foundation]]
- [[External_Resources]]
