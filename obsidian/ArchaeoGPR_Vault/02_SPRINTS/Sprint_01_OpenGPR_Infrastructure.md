---
type: sprint
tags: [sprint]
sprint: 1
status: done
started: 2026-07-14
completed: 2026-07-14
---

# Sprint 1 — OpenGPR Infrastructure

## Goal
IDS GeoRadar OpenGPR (`.ogpr`) dosyalarını güvenli, genel (tek dosyaya özgü
olmayan) bir şekilde okuyan, doğrulayan ve temel QC çıktıları üreten
modüler bir Python yazılımının temelini kurmak. İşleme algoritmaları
(dewow, gain, migration, vb.) bu sprintin kapsamı dışındadır.

## Scope
- `archaeogpr` paket iskeleti (`src/` layout): `io`, `model`, `qc`, `export`, `cli`.
- OpenGPR header + binary blok okuyucu (`read_ogpr`, `read_ogpr_header`).
- Immutable `GPRDataset` veri modeli.
- Türetilmiş metadata (zaman penceresi, derinlik tahmini, geometry/amplitude istatistikleri).
- QC görselleri: B-scan (tek kanal + 11 kanal karşılaştırma), survey geometry planı.
- Temel export: metadata JSON, header JSON, geolocation CSV, `radar_volume.npz`.
- CLI (`inspect`, `header`).
- Unit test suite (sentetik fixture) + gerçek dosya entegrasyon testi.
- README, CLAUDE.md, Obsidian vault senkronizasyonu.

## Out of Scope
Time-zero correction, DC offset correction, dewow, band-pass filtering,
background removal, gain, AGC, F-K filtering, migration, Hilbert envelope,
depth-slice, anomaly detection, arkeolojik sınıflandırma, Blender export, GUI.

## Input Data
`Swath003_Array02.ogpr` — proje içinde `data/raw/Swath003_Array02.ogpr`
olarak bulundu (orijinal konum: kullanıcının `Downloads` klasörü; oradan
salt okunur şekilde kopyalandı, orijinal değiştirilmedi). 8,010,373 byte.
Detay: [[04_DATASETS/Swath003_Array02]].

## Tasks
- [x] Repository structure
- [x] OpenGPR reader
- [x] Data model
- [x] Metadata extraction
- [x] QC plots
- [x] Basic exports
- [x] Unit tests
- [x] Real file integration test
- [x] Documentation
- [x] Vault synchronization

## Acceptance Criteria
- Ham `.ogpr` dosyası hiçbir aşamada değiştirilmez (hash öncesi/sonrası
  aynı — bkz. Validation Results).
- Hiçbir binary offset koda sabit gömülmez; hepsi header descriptor'larından okunur.
- `GPRDataset` array'leri yerinde değiştirilemez (read-only).
- Metadata `json.dumps()` ile doğrudan serileştirilebilir.
- Gerçek dosyadan okunan değerler görev tanımındaki "doğrulanmış örnek veri
  bilgileri" ile eşleşir (bkz. Validation Results).
- `pytest` tüm testler geçer; gerçek dosya yoksa entegrasyon testi skip
  eder (fail olmaz).
- CLI gerçek dosya üzerinde çalışır ve tüm QC çıktılarını üretir.

## Implementation Notes
- OpenGPR ikili formatı, gerçek dosyanın byte'ları doğrudan okunarak
  reverse-engineer edildi (bkz. [[03_ARCHITECTURE/OpenGPR_File_Structure]]);
  hiçbir değer harici bir spesifikasyondan kopyalanmadı.
- `Sample Geolocations` bloğunun kayıt düzeni header'da belgeli değildi;
  gerçek dosyanın tamamı üzerinde (yalnızca ilk slice değil) doğrulandı —
  slice index alanı 0..174 sırasıyla eşleşti, x_top/y_top ile
  x_bottom/y_bottom her noktada birebir eşit çıktı (traceler dikey).
- Veri modeli spesifikasyondaki öneriye `x_bottom`/`y_bottom` alanları
  eklenerek genişletildi; nedeni: geolocation CSV export'unun ham kaydı
  tam olarak yeniden oluşturabilmesi gerekiyordu ve önerilen dataclass'ta
  bu iki alan yoktu. Detay: [[06_DECISIONS/ADR_001_OpenGPR_Internal_Data_Model]].
- Metadata için `types.MappingProxyType` yerine özel bir `FrozenDict`
  (dict alt sınıfı) kullanıldı; `MappingProxyType` `json.dumps()` ile
  doğrudan serileştirilemiyordu (`TypeError: Object of type mappingproxy
  is not JSON serializable`) — bu, geliştirme sırasında manuel testle
  yakalanan gerçek bir hataydı ve düzeltildi.
- CLI, `argparse` (stdlib) ile yazıldı; ek bir CLI kütüphanesi (click/typer)
  eklenmedi (gereksiz bağımlılık).
- Kod formatlama/lint için `ruff`, tip kontrolü için `mypy` eklendi
  (opsiyonel dev bağımlılığı). mypy'nin `python_version` pin'i kaldırıldı
  çünkü kurulu numpy'nin kendi stub dosyaları 3.12+ sözdizimi kullanıyordu
  ve 3.11 hedefiyle mypy'yi hata veriyordu — bu bir proje kodu hatası değil,
  araç yapılandırması meselesiydi.

## Validation Results
- `pytest`: **36 passed, 0 failed, 0 skipped**. Detay: [[07_VALIDATION/Test_Results]].
- `ruff format .`: 6 dosya yeniden biçimlendirildi (yalnızca stil).
- `ruff check .`: başlangıçta 8 hata (import sıralama, gereksiz quote'lar,
  `typing.Mapping` → `collections.abc.Mapping`), `--fix` ile otomatik
  düzeltildi, sonrasında "All checks passed!".
- `mypy src/archaeogpr`: `qc/geometry.py`'de 4 tip hatası bulundu
  (`x`/`y`'nin `None` olabileceği, `has_geolocation` kontrolüyle daraltılmadığı
  için) — açık bir `assert` eklenerek düzeltildi; sonrasında "Success: no
  issues found in 14 source files".
- Ham dosya SHA-256 hash'i CLI çalıştırmadan önce ve sonra karşılaştırıldı:
  **`66d840c313b4beed10bea2e35d88431573f6fab0f02bba17792c0920028b62a6`** —
  değişmedi (hem `data/raw/` kopyası hem orijinal `Downloads` dosyası).
- Üretilen JSON dosyaları (`_metadata.json`, `_header.json`) `json.load()`
  ile başarıyla parse edildi.
- `radar_volume.npz` yeniden açıldı: `amplitudes.shape == (175, 11, 1024)`,
  `dtype == float32`, `time_ns.shape == (1024,)` doğrulandı.
- `_geolocation.csv`: 1925 satır (175 × 11) doğrulandı.
- Üç PNG dosyası da sıfır byte değil ve görsel olarak incelendi (B-scan
  beklenen şekilde üstte yüksek genlikli direct-wave/ringing gösteriyor,
  derinlikle hızla sönümleniyor — ham/ungained veri için fiziksel olarak
  makul).

## Generated Outputs
- `outputs/inspect/Swath003_Array02_metadata.json`
- `outputs/inspect/Swath003_Array02_header.json`
- `outputs/inspect/Swath003_Array02_geolocation.csv`
- `outputs/inspect/Swath003_Array02_channel00_bscan.png`
- `outputs/inspect/Swath003_Array02_all_channels.png`
- `outputs/inspect/Swath003_Array02_survey_geometry.png`
- `outputs/inspect/radar_volume.npz`

## Issues Discovered
Bkz. [[01_PROJECT_STATE/03_Open_Issues]] (ISSUE-001 — ISSUE-004): CRS
uyuşmazlığı, geolocation index alanının anlamı, endianness'ın header'da
açık olmaması, derinlik tahmininin hız varsayımına bağlılığı. Hiçbiri kod
hatası değil; hepsi belgelenmiş, kabul edilmiş belirsizlikler.

## Decisions
[[06_DECISIONS/ADR_001_OpenGPR_Internal_Data_Model]] — iç veri modeli,
eksen sırası, immutability yaklaşımı, koordinat alanları.

## Completion Summary
Sprint 1 kapsamındaki tüm görevler tamamlandı. Kod, sentetik ve gerçek
dosya testleriyle doğrulandı. CLI gerçek dosya üzerinde uçtan uca çalıştı
ve tüm beklenen QC çıktılarını üretti. Ham dosya değişmedi. Hiçbir işleme
algoritması (kapsam dışı) uygulanmadı.

## Next Sprint Recommendation
Sprint 2 — Time-Zero & DC Offset Correction (yalnızca bunlar + ilgili QC
ve testler). Detay: [[01_PROJECT_STATE/02_Next_Development_Sprint]].
