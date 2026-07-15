---
type: architecture
---

# OpenGPR File Structure

## Amaç

Bu not, `.ogpr` dosya formatının bayt seviyesinde yapısını, gerçek örnek dosya `Swath003_Array02.ogpr` (8.010.373 bayt, SHA-256 `66d840c313b4beed10bea2e35d88431573f6fab0f02bba17792c0920028b62a6`, `data/raw/Swath003_Array02.ogpr` altında salt okunur saklanır) üzerinden **doğrudan doğrulanmış** değerlerle belgeler. Uygulama kodu `src/archaeogpr/io/ogpr_reader.py` içindedir.

> **Önemli:** Bu notta verilen bayt ofset ve boyut değerleri (940, 7884800, 7885740, 124600, vb.) **yalnızca bu bir örnek dosyada doğrulanmış** değerlerdir ve okuyucu bunları çalışma zamanında dosyanın kendi header tanımlayıcılarından (descriptor) okur — koda gömülü (hardcoded) sabitler **değildir**. Aynı formatta farklı bir OpenGPR dosyasının ofsetleri farklı olabilir; okuyucu bunları o dosyanın kendi header'ından doğru şekilde okuyacaktır. Bu, CLAUDE.md kuralı "Never hardcode binary offsets from a sample file / Read all offsets, sizes and data types from descriptors" ile birebir örtüşür.

## Genel Düzen

```
[metin ön eki: magic + checksum + header boyutu]
[JSON header, tam olarak header boyutu kadar bayt]
[ikili veri blokları: Radar Volume, Sample Geolocations, ...]
```

## 1. Metin Ön Eki (Preamble)

| Satır | İçerik | Bu dosyadaki değer |
|---|---|---|
| 1 | Magic string | `ogpr` |
| 2 | 32 karakterlik hex checksum | `4e014092a258c4485afd1c5f717948b1` — okunur ama bağımsız olarak yeniden doğrulanmaz |
| 3 | JSON header'ın tam bayt uzunluğu, 8 hane, sıfırla doldurulmuş ASCII ondalık | `00000893` (893 bayt) |

Bu üç satırın hemen ardından, tam olarak 3. satırda belirtilen kadar bayt (bu dosyada 893 bayt) JSON header gelir; header'dan önce/sonra fazladan bir satır sonu karakteri yoktur. Bu dosyada header, bayt [47, 940) aralığını kaplar.

## 2. JSON Header — `mainDescriptor`

- `samplesCount = 1024`
- `channelsCount = 11`
- `slicesCount = 175`
- `metadata.swathName = "Swath003"`
- `metadata.swathId = "828f7c62c2d1949daed0be4168f29c30"`
- `metadata.arrayId = 2` — header'da tam sayı olarak saklanır; dosya adı kuralına uyacak şekilde `02` olarak sıfırla doldurularak gösterilmesi tamamen sunum amaçlıdır, saklanan bir alan değildir.

## 3. `dataBlockDescriptors[0]` — "Radar Volume"

| Alan | Değer |
|---|---|
| `byteOffset` | 940 |
| `byteSize` | 7.884.800 (= 175 × 11 × 1024 × 4 bayt) |
| `valueType` | `"float"` → little-endian float32 (`<f4`) olarak çözümlenir |
| `radar.samplingStep_m` | ≈ 0.04008848472894169 |
| `radar.samplingTime_ns` | 0.125 |
| `radar.propagationVelocity_mPerSec` | 100000000.0 (= 0.1 m/ns) |
| `radar.fequency_MHz` | 600 |
| `radar.polarization` | `"horizontal"` |

**Risk alanı 1 — `fequency_MHz` yazım hatası:** Gerçek dosyada anahtar, doğru yazım olan `frequency_MHz` değil, "r" harfi eksik `fequency_MHz` olarak geçer. Okuyucu bunu tesadüfen değil, kontrollü bir fallback olarak ele alır: önce `frequency_MHz`'i dener, bulamazsa `fequency_MHz`'e düşer. Bu iki anahtardan biri de yoksa `metadata["warnings"]`'e açık bir uyarı eklenir.

**Endianness notu:** Bu OpenGPR sürümünün header'ında açık bir byte-order/endianness alanı **yoktur**. Little-endian, doğrulanmış varsayılan (default) davranıştır. Okuyucu yine de gelecekteki bir dosya varyantı `byteOrder`/`endianness`/`endian` alanlarından birini eklerse bunu okuyup uygulayacak bir fallback yoluna sahiptir (`_resolve_dtype` fonksiyonu, `src/archaeogpr/io/ogpr_reader.py`); bu sessiz bir varsayım değil, kodda belgelenmiş açık bir davranıştır.

## 4. `dataBlockDescriptors[1]` — "Sample Geolocations"

| Alan | Değer |
|---|---|
| `byteOffset` | 7.885.740 |
| `byteSize` | 124.600 |
| `srs` | `{"type": "EPSG", "value": 32632}` |

**Risk alanı 2 — header'da belgelenmemiş kayıt düzeni:** Bu bloğun iç kayıt (record) düzeni, JSON header'ın **hiçbir yerinde** alan bazında tanımlanmaz. Düzen, geliştirici tarafından gerçek dosyanın baytları doğrudan okunup çapraz kontrol edilerek tersine mühendislik (reverse engineering) yoluyla çıkarılmıştır — dış bir spesifikasyondan kopyalanmamıştır, varsayılmamıştır.

Doğrulanmış düzen, dilim (slice) başına:

1. 8 bayt little-endian `int64` bir "öncü indeks" alanı — bu dosyada ampirik olarak tam olarak `0..174` sırasıdır; anlamı belgelenmemiştir ve okuyucu tarafından bir tutarlılık kontrolü dışında kullanılmaz.
2. Ardından 11 kanal × 8 little-endian `float64` alan, her kanal için tam olarak şu sırayla: `x_top, y_top, depth_top_m, elevation_top_m, x_bottom, y_bottom, depth_bottom_m, elevation_bottom_m`.

Bu, dilim başına `8 + 11 × 8 × 8 = 712` bayt eder; `712 × 175 = 124.600` bayt, yani beyan edilen `byteSize` ile **tam olarak** örtüşür.

Okuyucu bu düzeni "OpenGPR v2.0 Sample Geolocations blok şeması" olarak ele alır ve toplam bayt boyutunu `slicesCount`/`channelsCount`'a göre çapraz kontrol eder; bu formül tutmazsa (yani farklı yapıdaki bir OpenGPR dosyası bu bloğu farklı düzenlerse), okuyucu sessizce yanlış okumak yerine açık bir `InvalidGeolocationBlockError` fırlatır.

> **Önemli sınırlama:** Bu tersine mühendislik yapılmış şema, **yalnızca bu tek gerçek dosyaya karşı** doğrulanmıştır. Yapısı farklı bir OpenGPR dosyasıyla karşılaşılırsa, bu şema geçici (provisional) kabul edilmeli ve yeniden doğrulanmalıdır.

## 5. CRS Riski — EPSG:32632 Uyuşmazlığı (Çözülmemiş)

Header'daki `srs = {"type": "EPSG", "value": 32632}` değeri **UTM Zone 32N**'i belirtir; bu bölge coğrafi olarak kabaca 6°E–12°E arasını, yani İtalya/Orta Avrupa'yı kapsar. Projenin gerçek dünya saha bağlamı ise Türkiye olarak biliniyor (proje notlarında "Marmara Ereğlisi", Tekirdağ geçiyor), ki bu konum UTM Zone ~35N–37N aralığına düşer — 32N'e değil.

Bu, **belgelenmiş ve çözülmemiş bir risktir**: header'da saklanan CRS metadata'sı, gerçek saha konumunu doğru tanımlamıyor olabilir. Kod tabanı bu CRS değerinin doğru olduğunu **hiçbir zaman varsaymaz** ve **hiçbir zaman yeniden projeksiyon (reprojection) yapmaz** — değeri sadece olduğu gibi (as-is) raporlar ve göründüğü her yerde açık bir "doğrulanmadı" uyarısı ekler (örn. `qc/geometry.py` içindeki `CRS_WARNING_TEXT = "Coordinate values shown as stored; CRS not validated."`).

## İlgili Notlar

- [[Data_Model]] — bu bloklardan okunan verilerin `GPRDataset` alanlarına nasıl eşlendiği.
- [[Parser_Validation]] — bu dosya yapısının test/doğrulama kaydı.
- [[Known_Uncertainties]] — CRS riski ve geolocation şemasının provisional durumu dahil, bilinen belirsizliklerin listesi.
