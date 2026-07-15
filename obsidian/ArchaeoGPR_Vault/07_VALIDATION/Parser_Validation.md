---
type: validation-report
tags: [validation]
date: 2026-07-14
---

# Parser Validation

Bu not, `src/archaeogpr/io/ogpr_reader.py`'nin gerçek
`Swath003_Array02.ogpr` dosyasına ve sentetik fixture'lara karşı nasıl
doğrulandığını kaydeder. Format detayları: [[03_ARCHITECTURE/OpenGPR_File_Structure]].

## Magic kontrolü
Gerçek dosyanın ilk satırı `ogpr` olarak doğrulandı. Sentetik testte
(`test_invalid_magic_is_rejected`) magic `XXXX` yapılınca `InvalidMagicError`
fırlatıldığı doğrulandı.

## Header parse sonucu
Gerçek dosyada header 893 byte, offset [47, 940) aralığında, geçerli JSON.
`mainDescriptor.samplesCount/channelsCount/slicesCount` = 1024/11/175.
Sentetik testte bozuk JSON (`{not-valid-json`) `InvalidHeaderError`
fırlattı (`test_invalid_json_header_is_rejected`).

## Radar block doğrulaması
`dataBlockDescriptors[0].type == "Radar Volume"`, `byteOffset=940`,
`byteSize=7884800`, `valueType="float"`. Blok bulunamama durumu sentetik
testte doğrulandı (`test_missing_radar_block_raises` →
`MissingRadarBlockError`).

## Byte size hesabı
`byteSize (7884800) == slicesCount(175) * channelsCount(11) *
samplesCount(1024) * itemsize(4)` — gerçek dosyada tam eşleşiyor. Sentetik
testte kasıtlı uyuşmazlık (`radar_byte_size_override=999999`)
`InconsistentDimensionsError` fırlattı (`test_inconsistent_radar_dimensions_raises`).

## Shape doğrulaması
Gerçek dosyada reshape sonrası `amplitudes.shape == (175, 11, 1024)`
doğrulandı (`test_real_file_matches_documented_metadata`). Sentetik
fixture'da küçük bir shape (3, 2, 4) için reshape doğruluğu element-bazında
doğrulandı (`test_radar_dimensions_are_reshaped_correctly`).

## Dtype doğrulaması
`valueType="float"` → `numpy.dtype("<f4")`. Desteklenmeyen bir tip
(`"int16"`) sentetik testte `UnsupportedValueTypeError` fırlattı
(`test_unsupported_value_type_raises`).

## Geolocation block doğrulaması
Gerçek dosyada `byteOffset=7885740`, `byteSize=124600`. Kayıt düzeni
(8 byte int64 + 11 kanal × 8 float64) tüm 175 slice üzerinde doğrulandı:
`slice_index` alanı tam olarak `0..174` sırasıyla eşleşti; her noktada
`x_top == x_bottom` ve `y_top == y_bottom` (traceler dikey). Sentetik
testte kasıtlı byteSize uyuşmazlığı (`geo_byte_size_override=123`)
`InvalidGeolocationBlockError` fırlattı (`test_invalid_geolocation_block_raises`).
Geolocation bloğu olmayan bir dosyanın hâlâ radar verisiyle açılabildiği
de doğrulandı (`test_file_without_geolocation_opens_with_radar_data`).

## Gerçek dataset sonucu
`tests/test_real_ogpr_integration.py` gerçek dosyayı okuyup
[[04_DATASETS/Swath003_Array02]]'de belgelenen tüm değerleri doğruluyor
(shape, dtype, sampling_time_ns≈0.125, frequency≈600, polarization
horizontal, geolocation mevcut, time_window_ns≈128, max_depth_m≈6.4).

## Sentetik fixture sonucu
`tests/conftest.py::build_synthetic_ogpr_bytes` gerçek formatla aynı
preamble/header/blok yapısını üretir (3 slice × 2 kanal × 4 sample,
varsayılan). Tüm 11 unit test senaryosu (magic, header, missing block,
unsupported type, truncated block, reshape, time_ns, coordinate shape,
geolocation-less file, immutability, + ek senaryolar) bu fixture'larla
geçti. Detay: [[Test_Results]].

## İlgili notlar
[[03_ARCHITECTURE/OpenGPR_File_Structure]], [[Test_Results]],
[[Known_Uncertainties]]
