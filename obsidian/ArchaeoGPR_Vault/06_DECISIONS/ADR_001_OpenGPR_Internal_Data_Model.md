---
type: adr
tags: [decision]
id: ADR-001
status: accepted
date: 2026-07-14
---

# ADR-001 — OpenGPR Internal Data Model

## Context
`archaeogpr`, OpenGPR `.ogpr` dosyalarını okuyup ileride (gelecek
sprint'lerde) işleme algoritmaları uygulayacak bir Python yazılımıdır.
Sprint 1'de, hem okuyucunun hem de gelecekteki işleme modüllerinin
üzerinde çalışacağı ortak bir iç veri modeline karar vermek gerekti.
Gereksinimler: ham veriyi asla yerinde değiştirmeyen, eksen anlamları
açık, koordinatları isteğe bağlı (geolocation her dosyada olmayabilir),
metadata'sı JSON-serializable ve gelecekteki işleme geçmişini kayıt
altına alabilen bir model.

## Decision
- Ana array (`amplitudes`) eksen sırası sabit olarak `(slice, channel,
  sample)` kabul edildi. Bu sıra hem gerçek dosyanın `mainDescriptor`
  alanlarıyla (`slicesCount, channelsCount, samplesCount`) hem de tüm
  kodda (`metadata["dimensions"]["axis_order"]`) tutarlı.
- İç veri modeli tamamen NumPy tabanlı (`numpy.ndarray`), harici bir
  tensor/array kütüphanesi eklenmedi.
- Ham veri immutable kabul edildi: `GPRDataset.__post_init__` her array'i
  kopyalayıp `setflags(write=False)` ile salt okunur işaretliyor; yerinde
  değiştirme girişimi `ValueError` fırlatıyor (numpy'nin kendi mekanizması).
- Koordinat alanları (`x, y, depth_top_m, elevation_top_m, depth_bottom_m,
  elevation_bottom_m`) `(slice, channel)` boyutunda tutuluyor — spesifikasyondaki
  öneriyle aynı. Ek olarak `x_bottom`/`y_bottom` alanları eklendi (bkz.
  Alternatives Considered) çünkü geolocation CSV export'unun ham kaydı
  tam olarak yeniden oluşturması gerekiyordu.
- Metadata (`dataset.metadata`), processing history'den (`dataset.processing_history`)
  tamamen ayrı tutuluyor: metadata "bu dosyadan ne okundu" bilgisini,
  processing_history "bu veriye hangi işlemler hangi parametrelerle
  uygulandı" bilgisini taşıyor. Sprint 1'de `processing_history` her zaman
  boş tuple.
- Metadata, `types.MappingProxyType` değil, özel bir `FrozenDict` (dict
  alt sınıfı, mutating metodları bloke eden) ile saklanıyor — böylece
  `json.dumps(dataset.metadata)` doğrudan çalışıyor (bkz. Alternatives
  Considered).
- CRS/spatial reference bilgisi header'dan olduğu gibi metadata'ya
  ekleniyor ama hiçbir zaman doğrulanmış kabul edilmiyor veya otomatik
  reproject edilmiyor; her koordinat içeren çıktı bunu açıkça belirtiyor.

## Alternatives Considered
- **`types.MappingProxyType` ile metadata sarma:** Denendi, ardından
  reddedildi. Geliştirme sırasında `json.dumps(dataset.metadata)` çağrısı
  `TypeError: Object of type mappingproxy is not JSON serializable`
  hatası verdi — spesifikasyonun "metadata açık ve JSON-serializable hale
  getirilebilmeli" gereksinimiyle doğrudan çelişiyordu. `FrozenDict` (dict
  alt sınıfı) hem mutation'ı bloke ediyor hem `isinstance(x, dict)` olduğu
  için `json.dumps` ile doğrudan çalışıyor.
- **Spesifikasyondaki dataclass'ı olduğu gibi kullanmak (`x_bottom`/`y_bottom`
  olmadan):** Reddedildi. Geolocation CSV export'u (`x_top, y_top, ...,
  x_bottom, y_bottom, ...`) tam ham kaydı istiyor; bu iki alan olmadan
  bottom koordinatları hiçbir yerde saklanamıyordu. Bunun yerine metadata
  içine büyük array'ler gömmek (JSON'da binlerce float) de değerlendirildi
  ve dataset boyutunu şişirdiği, tekrar veri (CSV ile) oluşturduğu için
  reddedildi.
- **Ayrı bir "raw header" objesi tutmadan sadece işlenmiş metadata
  saklamak:** Reddedildi. `read_ogpr_header()` ayrı bir public fonksiyon
  olarak tutuldu (spesifikasyonun önerdiği gibi) çünkü CLI'nin `header`
  komutu ve `_header.json` çıktısı ham header'ı olduğu gibi göstermeli.

## Consequences
- Her yeni koordinat/derinlik alanı eklemek dataclass'ı büyütüyor; kabul
  edilebilir çünkü alan sayısı sabit ve küçük.
- Immutability, her işleme fonksiyonunun (gelecekte) yeni bir `GPRDataset`
  döndürmesini gerektiriyor — bellek açısından biraz daha maliyetli ama
  veri bütünlüğü ve QC izlenebilirliği için tercih edildi.
- `FrozenDict` yalnızca üst seviye anahtarları koruyor (nested dict'ler
  hâlâ mutable) — "reasonable measures" seviyesinde bir garanti, mutlak
  değil. Bu, `MappingProxyType`'a göre de bir gerileme değil (o da yalnızca
  shallow koruma sağlıyordu).

## Validation
- `tests/test_data_model.py`: read-only array garantisi, metadata JSON
  serializability, metadata mutation'ın engellenmesi, shape doğrulama
  hataları, `with_processing_step` immutability.
- Gerçek dosya üzerinde: `dataset.shape == (175, 11, 1024)`,
  `json.dumps(dataset.metadata)` başarılı, `dataset.x_bottom`/`y_bottom`
  gerçek geolocation kaydıyla eşleşiyor (bkz. [[07_VALIDATION/Parser_Validation]]).

## Related Files
- `src/archaeogpr/model/dataset.py`
- `src/archaeogpr/io/ogpr_reader.py`
- [[03_ARCHITECTURE/Data_Model]]
- [[03_ARCHITECTURE/OpenGPR_File_Structure]]
- [[04_DATASETS/Swath003_Array02]]
