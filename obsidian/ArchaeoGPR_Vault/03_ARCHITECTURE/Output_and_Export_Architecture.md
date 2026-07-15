---
type: architecture
---

# Output and Export Architecture

## Amaç

Bu not, Sprint 1'de **gerçekten çalışan** çıktı üretim katmanını belgeler: `src/archaeogpr/export/basic.py` içindeki export fonksiyonları, `src/archaeogpr/qc/` içindeki grafik fonksiyonları, ve bunları birbirine bağlayan CLI komutları (`inspect`, `header`).

## Export Fonksiyonları — `export/basic.py`

Bu modülde hiçbir sinyal işleme yapılmaz; sadece `io.ogpr_reader.read_ogpr()` / `read_ogpr_header()` tarafından zaten çıkarılmış verinin serileştirilmesi vardır.

- **`write_metadata_json(dataset, output_path)`** — `build_metadata_export(dataset)` ile `dataset.metadata`'yı `qc.metadata.derive_metadata()` çıktısıyla birleştirip (`export["derived"]`) tek bir JSON dosyasına yazar; iki kaynaktan gelen uyarılar yinelenmeden (sıralarını koruyarak) tek listede toplanır.
- **`write_header_json(header_info, output_path)`** — `OgprHeaderInfo` nesnesindeki ham `magic`, `checksum`, `header_size` ve tam ayrıştırılmış JSON header'ı okunabilir şekilde kaydeder.
- **`write_geolocation_csv(dataset, output_path)`** — `build_geolocation_dataframe(dataset)` ile her (slice, channel) çifti için bir satır üretir: `slice, channel, x_top, y_top, depth_top_m, elevation_top_m, x_bottom, y_bottom, depth_bottom_m, elevation_bottom_m`. Dataset'te geolocation yoksa `ValueError` fırlatır (çağıran taraf, örn. CLI, bu fonksiyonu çağırmadan önce `dataset.has_geolocation` kontrolü yapar).
- **`write_radar_volume_npz(dataset, output_path)`** — `amplitudes`, `time_ns`, `has_geolocation`, `metadata_json` alanlarını sıkıştırılmış (`np.savez_compressed`) bir `.npz` dosyasına yazar; geolocation varsa `x`, `y`, `elevation_top_m` de eklenir. Geolocation yoksa koordinat anahtarları `None` olarak değil, tamamen **atlanarak** saklanır.

## QC Grafik Fonksiyonları — `qc/bscan.py`, `qc/geometry.py`

- **`plot_bscan(dataset, channel, ..., ax=None)`** / **`save_channel_bscan(...)`** — tek bir kanalın B-scan'ini çizer. `clip_percentile` parametresi (varsayılan 99.0) yalnızca renk eşleme aralığını (`imshow(vmin=-limit, vmax=+limit)`) simetrik ve sıfır-merkezli olarak sınırlar; `dataset.amplitudes` hiçbir zaman kopyalanmaz, kırpılmaz (clip) veya değiştirilmez — bu sadece görsel bir sınırlamadır.
- **`save_all_channels_bscan(dataset, output_path, ..., ncols=4)`** — tüm kanalları küçük panellerde tek bir QC figüründe birleştirir; başlıkta açıkça "QC only, not for quantitative use" belirtilir.
- **`plot_survey_geometry(dataset, ax=None)`** / **`save_survey_geometry(...)`** — her kanalın plan-view (x, y) çizgisini eşit-oranlı (equal-aspect) eksenlerde, başlangıç/bitiş işaretçileriyle çizer. Koordinatlar **tam olarak saklandığı gibi** çizilir; hiçbir yeniden projeksiyon yapılmaz. Grafiğin üzerine her zaman `"Coordinate values shown as stored; CRS not validated."` uyarı metni basılır. Dataset'te geolocation yoksa `ValueError` fırlatır.

## CLI Orkestrasyon — `cli.py`

- **`inspect <input> [--output-dir] [--channel] [--clip-percentile] [--cmap]`** — yukarıdaki tüm export ve QC fonksiyonlarını sırayla çağırır: `_metadata.json`, `_header.json`, (varsa) `_geolocation.csv` ve `_survey_geometry.png`, `_channel{NN}_bscan.png`, `_all_channels.png`, ve `radar_volume.npz`. Sonunda okunabilir bir özet ve toplanan uyarı listesini konsola yazdırır.
- **`header <input>`** — hiçbir çıktı dosyası üretmeden, sadece header'ın okunabilir bir özetini (`magic`, `checksum`, boyutlar, blok listesi) konsola yazdırır.
- Hatalar: `OGPRError` alt sınıfları ve `OSError` yakalanıp kullanıcı dostu bir mesajla `stderr`'e yazdırılır (çıkış kodu 1); `--debug` bayrağı verilirse tam traceback yeniden fırlatılır (`raise`).

## Çıktı Konumu Kuralı

Tüm çıktılar, kullanıcının belirttiği `--output-dir` altına yazılır (varsayılan: `outputs/inspect/`) — **hiçbir zaman** kaynak `.ogpr` dosyasının yanına yazılmaz. Bu, `data/raw/`'ın salt okunur kalmasını garantileyen mimari kuralın (bkz. CLAUDE.md: "Never overwrite or modify source radar files") doğrudan bir sonucudur.

## İlgili Notlar

- [[Repository_Map]] — bu dosyaların depo içindeki tam konumu ve `outputs/inspect/` dizininin içeriği.
- [[Data_Model]] — export edilen tüm verinin kaynağı olan `GPRDataset`.
