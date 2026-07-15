---
type: sprint
tags: [sprint, review]
sprint: 2.2
status: done
started: 2026-07-15
completed: 2026-07-15
---

# Sprint 2.2 — Time-Zero-Relative Time Axis and Target-Invariant DC Offset

## Goal
Bu sprint yeni bir filtre veya sinyal işleme algoritması DEĞİLDİR. Amacı,
Sprint 2.1'in gerçek veri karşılaştırmasında bulunan çarpıcı DC offset
farkını (`target_sample=0` → ≈-398.5 vs `target_sample=16` → ≈81.7) kök
nedenine kadar inceleyip, mevcut time-zero ve DC offset uygulamasını
bilimsel olarak tutarlı (target-sample-invariant) hale getirmektir.

## Scope
- `correct_time_zero()`'nun çıktı `time_ns`'ini time-zero-relative olarak
  yeniden üretmesi (`time_ns[target_sample] == 0.0`).
- `correct_dc_offset()`'e `window_reference: Literal["dataset_time",
  "sample_index"]` eklenmesi, varsayılan `"dataset_time"`.
- Canonical DC offset politikası: `method="mean"`, `window_start_ns=20.0`,
  `window_end_ns=100.0`, `window_reference="dataset_time"` — CLI
  varsayılanı olarak (fonksiyona sabit gömülü DEĞİL).
- 22 yeni test (zaman ekseni 10, DC penceresi 7, target-invariance 5).
- Gerçek veri: `target_sample=16` için canonical çıktı
  (`outputs/sprint02/canonical_target16/`), yalnızca tüm target-invariance
  testleri geçtikten SONRA üretildi.
- Karşılaştırma/doğrulama çıktıları (`outputs/sprint02_2_validation/`).

## Out of Scope
Dewow, band-pass, background removal, gain, AGC, F-K, migration, velocity
analysis, envelope, time/depth-slice, Blender/QGIS export, GUI,
trace-by-trace time-zero, sub-sample shift, **otomatik fiziksel yüzey
kalibrasyonu**. Sprint 3 bu sprintte kesinlikle BAŞLATILMADI.

## Trigger — Neden bu sprint gerekli oldu
Sprint 2.1'in gerçek veri karşılaştırması (bkz.
[[Sprint_02_1_TimeZero_DCOffset_Review]]), aynı kanallar ve aynı otomatik
pick'lerle `target_sample=0` ve `target_sample=16`'nın DC offset
ortalamalarının çarpıcı biçimde farklı çıktığını gösterdi. Kök neden analizi
iki bağlantılı sorun buldu:
1. `correct_time_zero()`, `time_ns`'i HİÇ değiştirmiyordu — çıktı hep
   `arange(samples)*sampling_time_ns` kalıyordu, `target_sample`'dan
   bağımsız olarak.
2. Sprint 2.1'in DC offset'i, pencere verilmeden tüm-valid-trace
   ortalamasını kullanıyordu — bu istatistik, ne kadar erken (güçlü,
   asimetrik) pulse örneğinin "valid" bölgede kaldığına, dolayısıyla
   `target_sample`'a bağımlı.

Tam analiz: [[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]].

## Code-Level Audit: Önceki `time_ns` Davranışı
`correct_time_zero()`, çıktı dataset'ini `dataclasses.replace(dataset,
amplitudes=..., processing_history=...)` ile üretiyordu — `time_ns=...`
HİÇ geçirilmiyordu, yani çıktı `time_ns`'i girdiden değişmeden miras
alıyordu. Sonuç: `target_sample=16` ile bile, `time_ns[0]` her zaman `0.0`
kalıyordu — halbuki fiziksel olarak pick artık örnek 16'da, örnek 0'da
değil. Bu, `correct_dc_offset()`'in ns pencerelerinin (`ns_window_to_
samples`, sample 0 = 0 ns varsayımıyla) `target_sample`'dan bağımsız olarak
HEP AYNI mutlak örnek aralığını seçmesine yol açıyordu — "aynı ns
penceresi," farklı `target_sample` değerlerinde farklı fiziksel içerik
seçiyordu.

## Changes Made
- `processing/common.py`: `time_zero_relative_time_ns()`,
  `dataset_time_window_mask()` eklendi.
- `processing/time_zero.py`: çıktı `time_ns`'i yeniden üretiliyor;
  `sampling_time_ns` artık HER yöntem için zorunlu; `diagnostics["time_
  axis"]` eklendi (target_sample, time_zero_reference_ns=0.0, önceki/
  düzeltilmiş eksen özet parametreleri).
- `processing/dc_offset.py`: `window_reference` parametresi eklendi;
  pencere hesaplaması boolean mask'e birleştirildi (her iki referans modu
  aynı downstream mantığı kullanıyor); yeni `diagnostics["window_
  reference"]`.
- `export/processed.py`: `write_relative_time_axis_csv()` eklendi;
  `write_sprint2_summary_json()` artık `time_axis` ve DC pencere alanlarını
  içeriyor.
- `cli.py`: `--dc-window-reference`; `--dc-window-start-ns`/`--dc-window-
  end-ns` CLI varsayılanları 20.0/100.0'a çekildi (fonksiyonun kendi
  varsayılanı değişmedi); `sprint2` komutu artık `channel_picks.csv`,
  `dc_offsets.csv`, `channel_medians_before_after.png`,
  `padding_mask_channelNN.png`, `valid_sample_summary.json`,
  `processing_metadata.json`, `relative_time_axis.csv` de üretiyor; yeni
  terminal çıktıları (corrected time axis, target sample zaman değeri,
  negatif-zaman sample sayısı, DC window + örnek indeksleri, padding
  istatistikleri).

## Testing
22 yeni test, mevcut 101 test hiç bozulmadı — toplam **123/123 passed**
(bkz. [[07_VALIDATION/Test_Results]]):
- `test_time_zero.py` (30→40, +10): `time_ns[target_sample]==0`, öncesi
  negatif, sonrası pozitif, örnek aralığı korunuyor, target=0 sıfırdan
  başlıyor, target=16'da sample 0 = -16·dt, girdi eksen değişmiyor,
  çıktı eksen salt-okunur, diagnostics doğru, `sampling_time_ns` artık
  manual için de zorunlu.
- `test_dc_offset.py` (24→31, +7): `dataset_time` doğru örnekleri seçiyor,
  `[start,end)` yarı-açık davranış, negatif-zaman örnekleri pozitif
  pencereye girmiyor, valid mask ile doğru kesişim, padding hesaba
  katılmıyor, sıfır geçerli örnek hatası, mean/median aynı pencereyi
  kullanıyor.
- `test_target_invariance.py` (yeni dosya, +5): aynı göreli pencere aynı
  ham örnekleri seçiyor, ofset array'leri eşit, ortak göreli-zaman
  bölgesinde genlikler eşit, target=16'da tam 16 örnek daha az padding,
  processing history zaman eksenini ve DC penceresini kaydediyor.

## Real Data Validation
Gerçek `Swath003_Array02.ogpr` üzerinde (bkz.
[[07_VALIDATION/QC_Output_Validation]] "Sprint 2.2" bölümü):
- Canonical komut (`sprint2 ... --target-sample 16 --max-shift-samples 96
  --overflow-policy error --dc-window-start-ns 20 --dc-window-end-ns 100
  --dc-window-reference dataset-time`): 0 kırpılan kanal,
  `time_ns[16]==0.0`, `time_ns[0]==-2.0` ns, 16 negatif-zaman örneği.
- Target-invariance: 11 kanalın hepsinde `[20,100)` ns penceresi AYNI ham
  örnek aralığını seçti; ofset array'leri TAM olarak eşit (fark=0.0);
  ortak göreli-zaman bölgesinde (1008/1024 örnek) genlikler TAM olarak eşit
  (fark=0.0). Bkz. `outputs/sprint02_2_validation/VALIDATION_RESULT.md`.
- DC penceresinin kendi ortalaması, düzeltme sonrası her kanalda ~1e-7
  (float32 hassasiyetinde tam sıfır); tüm-valid-trace ortalaması (-5.62)
  bilerek bu kadar sıkı değil (bkz. gerekçe: Known Uncertainties).
- Mean vs median: bazı kanallarda işaret bile değişiyor (`max_abs_
  difference≈226.4`) — açık bilimsel belirsizlik olarak kaydedildi.

## QC Outputs
`outputs/sprint02/canonical_target16/` (17 dosya) ve
`outputs/sprint02_2_validation/{target_invariance,dc_window}/` — tam liste
ve doğrulama: [[07_VALIDATION/QC_Output_Validation]].

## Decisions
[[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]] — time-zero-
relative eksen, `window_reference`, canonical pencere politikası,
whole-trace ortalamasının neden canonical olmadığı, target-invariance
gereksinimi, `target_sample=16` mühendislik önerisi.

## Acceptance Criteria (§13, hepsi doğrulandı)
0 kırpılan kanal · `target_sample=16` · `time_ns[16]==0` ·
`time_ns[0]==-2.0 ns` · 16 negatif-zaman örneği · DC window=20-100ns ·
target 0/16 ofset farkı=0.0 (tolerans içinde) · ortak göreli-zaman genlik
farkı=0.0 · padding=0 · valid-sample (pencere-içi) ortalaması ~1e-7 ·
NaN/Inf yok · girdi immutable · ham hash değişmedi · canonical çıktı
downstream için valid. Hepsi **PASS** — bkz.
`outputs/sprint02_2_validation/VALIDATION_RESULT.md`.

## Sprint 2 Status Update
Bu sprintin sonucunda [[Sprint_02_TimeZero_DCOffset]]'in durumu
`review_required` → **`done`**'a döndü (kabul kriterlerinin hepsi geçti).
[[Sprint_02_1_TimeZero_DCOffset_Review]]'in durumu da `done`'a çekildi —
o sprintin bulguları (kırpma, padding kirlenmesi) çözüldü VE bu sprintin
bulduğu ek sorun (whole-trace DC offset'in target_sample'a bağımlılığı) da
çözüldü.

## Next Sprint
Sprint 3 (dewow + band-pass) hâlâ yalnızca PLANDIR, başlatılmadı. Detay:
[[01_PROJECT_STATE/02_Next_Development_Sprint]].

## Related Notes
[[Sprint_02_TimeZero_DCOffset]], [[Sprint_02_1_TimeZero_DCOffset_Review]],
[[Sprint_Index]], [[06_DECISIONS/ADR_002_TimeZero_Reference_and_Shift_Policy]],
[[06_DECISIONS/ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]],
[[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]],
[[05_PROCESSING/Time_Zero_Correction]], [[05_PROCESSING/DC_Offset]]
