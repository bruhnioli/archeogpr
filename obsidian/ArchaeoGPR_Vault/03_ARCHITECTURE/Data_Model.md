---
type: architecture
---

# Data Model

## Amaç

Bu not, projenin tek merkezi veri taşıyıcısı olan `GPRDataset` frozen dataclass'ını (`src/archaeogpr/model/dataset.py`) alan bazında belgeler. Okuyucu (`io/`), QC (`qc/`) ve export (`export/`) katmanlarının tümü bu tek nesne üzerinden konuşur; başka hiçbir yerde radar verisi için ayrı bir gösterim (representation) yoktur.

## `GPRDataset` Alanları

| Alan | Şekil / Tip | Açıklama |
|---|---|---|
| `amplitudes` | `ndarray`, `(slices, channels, samples)` | Ham radar amplitüd hacmi. |
| `time_ns` | `ndarray`, `(samples,)` | Her örneğin (sample) izdeki iki-yönlü zaman değeri, nanosaniye. |
| `x`, `y` | `ndarray \| None`, `(slices, channels)` | Her izin üst (yüzey) yatay konumu. Geolocation bloğu yoksa `None`. |
| `x_bottom`, `y_bottom` | `ndarray \| None`, `(slices, channels)` | Alt konum; tam round-trip sadakati için ayrı tutulur. |
| `depth_top_m`, `elevation_top_m` | `ndarray \| None`, `(slices, channels)` | Üst noktanın derinliği ve yükseltisi (metre). |
| `depth_bottom_m`, `elevation_bottom_m` | `ndarray \| None`, `(slices, channels)` | Alt noktanın derinliği ve yükseltisi (metre). |
| `metadata` | `Mapping[str, Any]` (`FrozenDict`) | JSON-serileştirilebilir metadata haritası. |
| `processing_history` | `tuple[Mapping[str, Any], ...]` | Uygulanan işleme adımlarının kaydı; Sprint 1'de her zaman `()`. |

Amplitüd hacminin eksen sırası sabittir ve her yerde aynı şekilde indekslenir:

```
amplitudes[slice, channel, sample]
```

Bu sıra `dataset.metadata["dimensions"]["axis_order"]` içinde de `["slice", "channel", "sample"]` olarak açıkça saklanır — CLAUDE.md kuralı olan "Radar axis order is slice, channel, sample" burada kod seviyesinde garanti edilir.

## Üst / Alt Konum Ayrımı Neden Var

`x_bottom`/`y_bottom` alanları, gerçek örnek dosyada (`Swath003_Array02.ogpr`) `x`/`y` ile sayısal olarak eşit çıksa da, ayrı alanlar olarak saklanır. Amaç, kaynak dosyanın "Sample Geolocations" bloğundaki ham kaydı (üst ve alt uç noktalarını) kayıpsız şekilde yeniden oluşturabilmektir — okuyucu iki uç birbirine eşit olmayan bir dosyayla karşılaşırsa (yatay ofset > 1e-6 m), bu durum `metadata["warnings"]` içine otomatik olarak not düşülür.

## `metadata` — `FrozenDict`

`metadata` alanı ham bir `dict` değil, `FrozenDict` adında özel bir `dict` alt sınıfıdır (`__setitem__`, `update`, `pop`, `popitem`, `setdefault`, `clear` hepsi bloklanmıştır ve çağrıldıklarında `TypeError` fırlatır). `types.MappingProxyType` yerine bu tasarımın seçilme nedeni: `FrozenDict` hâlâ `isinstance(x, dict)` olarak görünür, dolayısıyla `json.dumps(dataset.metadata)` hiçbir sarma (unwrapping) işlemine gerek kalmadan doğrudan çalışır. Koruma yalnızca üst seviyededir — iç içe (nested) dict/list değerleri sıradan mutable nesnelerdir; bu, `MappingProxyType`'ın da verdiği aynı sığ (shallow) garantidir.

## Değişmezlik (Immutability) Garantileri

- Yapıcıya (`__post_init__`) geçirilen tüm `ndarray` alanları **kopyalanır** ve `ndarray.setflags(write=False)` ile salt okunur işaretlenir. Bu nedenle `dataset.amplitudes[0] = 0` gibi yerinde bir mutasyon her zaman `ValueError` fırlatır.
- Şekil/boyut uyumsuzlukları (örn. `time_ns` uzunluğunun `amplitudes.shape[2]`'ye eşit olmaması, veya bir koordinat dizisinin `(slices, channels)` şeklinde olmaması) `DatasetValidationError` (bir `ValueError` alt sınıfı) fırlatır.
- `processing_history` bir `tuple` olmak zorundadır; değilse yine `DatasetValidationError` fırlatılır.
- `amplitudes` ve `time_ns` zorunludur (`None` olamaz); koordinat/derinlik/yükselti alanlarının tümü isteğe bağlıdır ve dosyada geolocation bloğu yoksa hepsi birlikte `None` olur.

## Birimler

- `x`, `y`, `depth_*_m`, `elevation_*_m`: **metre**.
- `time_ns`: **nanosaniye**.
- `amplitudes`: dosyadaki ham (gain uygulanmamış) float32 amplitüd değerleri; birimsizdir.

## Yardımcı Özellikler ve Metotlar

- `dataset.shape` → `(slices, channels, samples)` (salt `amplitudes.shape`'in kısayolu).
- `dataset.has_geolocation` → `x` ve `y` her ikisi de `None` değilse `True`.
- `dataset.with_processing_step(record)` → `self`'i **değiştirmeden**, `record`'u `processing_history`'ye ekleyerek **yeni** bir `GPRDataset` döndürür (`dataclasses.replace` ile). Sprint 1'deki hiçbir kod bu metodu çağırmaz; bu, gelecekteki işleme modüllerinin (time-zero, dewow, gain, ...) kullanacağı API sınırıdır — bkz. [[Processing_Pipeline_Architecture]].

## İlgili Notlar

- [[OpenGPR_File_Structure]] — `GPRDataset` alanlarının kaynak `.ogpr` dosyasındaki hangi bloktan/alandan geldiği.
- [[ADR_001_OpenGPR_Internal_Data_Model]] — bu veri modelinin neden bu şekilde tasarlandığına dair karar kaydı.
- [[Architecture_Overview]] — `GPRDataset`'in genel veri akışındaki yeri.
