---
type: sprint
tags: [sprint, review]
sprint: 3
status: done
started: 2026-07-15
completed: 2026-07-15
---

# Sprint 3 — Dewow & Band-Pass Filtering, Frequency Spectrum QC, and Candidate Parameter Comparison

> **Follow-up (2026-07-15):** [[Sprint_03_1_Dewow_Bandpass_Decision_QC]]
> built decision-focused QC on top of this sprint's D2, B1, and B2
> candidates specifically (deeper removed-component review, B1-vs-B2-only
> comparison, band-energy/spatial-coherence/phase metrics,
> `DECISION_PANEL_D2_B1_B2.png`, `BANDPASS_FINAL_DECISION_REQUIRED.md`).
> D2 was recommended as an engineering candidate (4/4 conditions passed).
> The content below is this sprint's own original record and was left
> unmodified.
>
> **Canonicalization (2026-07-15):** the user supplied an explicit
> human/geophysicist decision — **D2** dewow + **B1** band-pass are now
> the **canonical** Sprint 3 chain (Sprint 2 canonical → D2 → B1). See
> [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]] for the full
> rationale and `outputs/sprint03/canonical_D2_B1/` for the canonical
> output. This sprint's status is now `done`. All D1-D4/B2-B4/C1-C6
> candidate outputs below remain unchanged and are preserved as the QC
> evidence supporting this decision.

## Goal
Sprint 2.2'nin canonical çıktısı (`outputs/sprint02/canonical_target16/`)
üzerinde dewow ve band-pass filtreleme algoritmalarını uygulamak, her ikisi
için frekans spektrumu QC altyapısı sağlamak, sentetik + gerçek veri
testleriyle doğrulamak, ve **aday parametre karşılaştırmaları** üretmek —
**hiçbir dewow veya band-pass adayını canonical olarak seçmeden.** Nihai
parametre seçimi bu sprintte YAPILMAZ; insan/jeofizikçi incelemesi
gerektirir.

## Scope
1. Dewow algoritması (`correct_dewow()`, running_mean/running_median).
2. Band-pass filtre algoritmaları (`correct_bandpass()`, Butterworth
   zero-phase + Ormsby trapezoidal FFT).
3. Frekans spektrumu analizi (`compute_amplitude_spectrum()`).
4. Sentetik + gerçek veri doğrulaması.
5. Öncesi/sonrası/çıkarılan-bileşen QC çıktıları.
6. Aday parametre karşılaştırmaları (dewow D1-D4, band-pass B1-B4, kombine
   C1-C6).
7. Obsidian senkronizasyonu.

## Out of Scope
Background removal, gain, AGC, F-K filtering, migration, velocity
analysis, Hilbert envelope, depth-slice üretimi, anomaly detection,
arkeolojik sınıflandırma, Blender/QGIS export, GUI, ve **kritik olarak:
herhangi bir dewow veya band-pass parametresinin OTOMATİK olarak
canonical/final seçilmesi.** Sprint 4 bu sprintte kesinlikle
BAŞLATILMADI.

## Trigger
Sprint 2.2'nin tamamlanmasıyla (`target_sample=16` mühendislik önerisi,
target-invariant DC offset penceresi) Sprint 3'ün teknik ön koşulları
karşılandı (bkz. [[01_PROJECT_STATE/02_Next_Development_Sprint]]).
Kullanıcı Sprint 3'ü açıkça başlattı.

## Implementation

### Dewow (`processing/dewow.py`)
`correct_dewow(dataset, *, window_ns=8.0, method="running_mean",
valid_mask=None, edge_mode="reflect", allow_repeat_processing=False)`.
Her (slice, channel) izi, her ardışık geçerli segment içinde bağımsız
olarak düzeltilir: `corrected(t) = trace(t) - MovingWindow[trace(t)]`.
Pencere/kenar/padding politikası: [[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]].

### Band-pass (`processing/bandpass.py`)
`correct_bandpass(dataset, *, method="butterworth"|"ormsby", ...)`. İki
bağımsız yöntem, ikisi de sıfır-faz: Butterworth SOS + `sosfiltfilt`,
Ormsby gerçek yamuk transfer fonksiyonu (FFT çarpımı). Faz-koruma ve
maskeli-segment politikası: [[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]].

### Frekans spektrumu (`qc/spectrum.py`)
`compute_amplitude_spectrum(dataset, *, time_start_ns, time_end_ns,
valid_mask=None, detrend="constant", taper="hann", aggregation="median")`
— genlik (asla güç) spektrumu, gerçek `sampling_time_ns`'ten türetilen
frekans ekseni, Nyquist bağımsız hesaplandı, padding FFT'ten hariç
(tüm kanallarda ortak geçerli maske ile), mean/median/RMS agregasyon
seçenekleri. QC metrikleri (baskın frekans, spektral ağırlık merkezi, -3dB
bandı, enerji yüzdelik bantları) **hiçbir zaman** "gerçek anten bandı"
iddiası olarak sunulmaz.

### Yükleyici (`export/sprint3.py`)
`read_processed_npz(path)` — `allow_pickle=False`, eksik zorunlu alan/
geçersiz JSON/sıra-dışı processing_history/`valid_mask` şekil uyuşmazlığı
için açık hata, dönen array'ler salt-okunur. `load_candidates_config(path)`
— `configs/*.yaml` için `yaml.safe_load` + mapping doğrulaması.
`write_padding_verification_json(result, path)` — padding'in dokunulmadığını
ve `removed_component`'in padding'de sıfır olduğunu makine-okunabilir
biçimde raporlar.

### Orkestrasyon (`sprint3_candidates.py` + CLI)
`run_all_sprint3_candidates()` — dewow adayları → spektrum analizi →
band-pass adayları (D2 tabanı üzerinde) → kombine adaylar → `SPRINT3_
REVIEW_REQUIRED.md`. CLI: `dewow`, `bandpass`, `sprint3-candidates` alt
komutları — her biri terminale `Canonical selected: false` basar.

## Testing
86 yeni test, mevcut 123 test hiç bozulmadı — toplam **209/209 passed**
(bkz. [[07_VALIDATION/Test_Results]]):
- `test_dewow.py` (yeni, 20): sabit iz→tam sıfır, düşük-frekans sürüklenme
  kaldırılırken yüksek-frekans korunuyor (ayrık toplam özdeşliğiyle
  kanıtlandı), pulse konumu korunuyor, girdi=çıktı+çıkarılan, padding
  hariç/değişmeden, valid_mask bağımsız kopya, mean/median outlier
  farkı, pencere dönüşümü (çift→tek yuvarlama+uyarı), geçersiz method/
  edge_mode/pencere hataları, NaN guard, processing_history, tekrar-işleme
  guard'ı, NPZ round-trip.
- `test_bandpass.py` (yeni, 20): geçiş/durdurma bandı (her iki yöntem),
  zero-phase pulse-pozisyon koruması + causal karşıtlığı, Ormsby yapısal
  sıfır-faz, girdi=çıktı+çıkarılan, padding hariç/değişmeden, valid_mask
  bağımsız kopya, geçersiz Butterworth/Ormsby parametreleri (Nyquist +
  sıralama), NaN guard, processing_history, tekrar-işleme guard'ı, NPZ
  round-trip.
- `test_spectrum.py` (yeni, 24): baskın frekans doğru tespit, gerçek
  örnekleme aralığından frekans ekseni/Nyquist, padding ortak-geçerli
  maskeyle hariç, `dataset_time` pencere seçimi, sabit detrend DC
  bileşenini kaldırıyor, Hann taper sızıntıyı ölçülebilir şekilde artırıyor
  (kanıtlandı: bin-hizalı sinüsün konsantrasyonu taper'sız ~1.0, Hann ile
  ~0.5), mean/median/RMS agregasyon farklılaşması (güç-ortalaması
  eşitsizliğiyle RMS>mean>median outlier'lı veride), genlik (asla güç)
  doğrusal ölçekleniyor (2× girdi → tam 2× spektrum, 4× DEĞİL), dB
  dönüşümü sıfır girdide bile sonlu, tüm hata yolları.
- `test_sprint3_pipeline.py` (yeni, 21): paylaşılan `contiguous_true_runs`
  yardımcısı, `read_processed_npz` round-trip + tüm hata yolları + salt-
  okunurluk, `load_candidates_config` gerçek YAML dosyalarını okuyor,
  `write_padding_verification_json`, sentetik uçtan-uca time-zero→dc-
  offset→dewow→band-pass zinciri + yeniden-yüklenen NPZ'de tekrar-işleme
  guard'ının çalıştığının doğrulanması.
- `test_sprint3_real_integration.py` (yeni, 1, gerçek dosya varsa çalışır):
  gerçek `Swath003_Array02.ogpr` üzerinde canonical Sprint 2.2 zinciri +
  dewow + Butterworth + Ormsby; şekil/dtype/sonluluk, zaman ekseni/valid_
  mask korunuyor, padding tam sıfır, processing_history sırası, dewow
  düşük-frekans enerjisini azaltıyor (spektrum çökmeden), band-pass
  geçiş-bandı enerjisini koruyor + durdurma-bandı enerjisini azaltıyor,
  medyan-iz ana olay konumu ±5 örnek toleransında korunuyor, NPZ/QC
  round-trip, girdi/ham dosya değişmedi.

## Real Data Validation
- Canonical girdi: `outputs/sprint02/canonical_target16/sprint02_
  processed.npz` (SHA-256 `b2770b5c...af5afe`), shape `(175, 11, 1024)`,
  `time_ns[16]==0.0`.
- Tüm padding_verification.json dosyaları (14 aday: 4 dewow + 4 band-pass
  + 6 kombine) programatik olarak denetlendi: **14/14** `all_channels_
  padding_untouched=true` ve `all_channels_removed_component_zero_at_
  padding=true`.
- Tüm band-pass/kombine adaylarında (10 aday) medyan-iz çapraz-korelasyon
  gecikmesi: **tam olarak 0** (gerçek veride sıfır-faz doğrulaması).
- Band-pass geçiş-bandı enerji korunumu: B1≈99.2%, B2≈99.1%, B3≈98.4%,
  B4≈95.4% (önce: 87.0-96.6%) — filtrelemenin enerjiyi geçiş bandına
  yoğunlaştırdığı beklenen davranış.
- Girdi NPZ hash'i ve raw `.ogpr` hash'i tüm CLI çalıştırmaları boyunca
  değişmedi.

## Dewow Candidates (`outputs/sprint03/dewow_candidates/`)
| ID | Yöntem | İstenen pencere | Uygulanan pencere | Düşük-frek. enerji oranı (sonra) |
|---|---|---|---|---|
| D1 | running_mean | 4.0 ns | 4.125 ns (33 örnek) | 0.7440 |
| D2 | running_mean | 8.0 ns | 8.125 ns (65 örnek) | 0.8785 |
| D3 | running_mean | 12.0 ns | 12.125 ns (97 örnek) | 0.5587 |
| D4 | running_median | 8.0 ns | 8.125 ns (65 örnek) | 0.9392 |

Her aday 13 dosyalık tam QC seti + `comparison/` altında 6 karşılaştırma
çıktısı (`DEWOW_REVIEW_REQUIRED.md` dahil) üretti. **Hiçbiri canonical
seçilmedi.**

## Spectrum Analysis (`outputs/sprint03/spectrum/`)
Ham canonical spektrum + 4 dewow adayının spektrumu, QC metrikleriyle
birlikte (`spectrum_metrics.csv`). `SPECTRUM_INTERPRETATION_NOTES.md`
açıkça belirtiyor: hiçbir değer "gerçek anten bandı" iddiası değildir;
header'ın 600 MHz nominal frekansı bağımsız yeniden ölçülmedi.

## Band-Pass Candidates (`outputs/sprint03/bandpass_candidates/`, D2 tabanında)
| ID | Yöntem | Parametreler | Padding OK | Maks. medyan-iz gecikmesi |
|---|---|---|---|---|
| B1 | butterworth | 100-900 MHz, order=4 | evet | 0 |
| B2 | butterworth | 120-800 MHz, order=4 | evet | 0 |
| B3 | ormsby | 80/120/800/1000 MHz | evet | 0 |
| B4 | ormsby | 100/150/700/900 MHz | evet | 0 |

D2'nin ortak taban olarak kullanılması D2'yi canonical yapmaz. Her aday 13
dosyalık tam QC seti + `comparison/` altında 9 karşılaştırma çıktısı
(`BANDPASS_REVIEW_REQUIRED.md` dahil) üretti. **Hiçbiri canonical
seçilmedi.**

## Combined Candidates (`outputs/sprint03/combined_candidates/`)
Kontrollü çiftler (tam 4×4 tarama DEĞİL): C1-C3 dewow penceresini
değiştirir (B2 sabit), C4-C6 band-pass'i değiştirir (D2 sabit). Tüm 6
adayda medyan-iz gecikmesi = 0. **Hiçbiri canonical seçilmedi.**

## QC Outputs
`outputs/sprint03/{dewow_candidates,spectrum,bandpass_candidates,
combined_candidates}/` (209 dosya toplam) + üst düzey `outputs/sprint03/
SPRINT3_REVIEW_REQUIRED.md`. Tam liste ve doğrulama:
[[07_VALIDATION/QC_Output_Validation]].

## Decisions
- [[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]] — pencere
  dönüşümü, kenar modu, maskeli-segment politikası.
- [[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]] —
  sıfır-faz iki-yöntem tasarımı, faz doğrulama metodolojisi, paylaşılan
  maskeli-segment deseni.

## Acceptance Criteria
Girdi/ham dosya değişmedi · canonical NPZ üzerine yazılmadı · girdi
GPRDataset mutasyona uğramadı · `time_ns` değişmedi · valid_mask
korunmadan/daraltılmadan geçti · padding her işlemden sonra tam sıfır ·
her işlem yeni bir GPRDataset/ProcessingResult döndürdü · her işlemin
parametreleri/diagnostics/uyarıları processing_history'ye kaydedildi ·
her filtre çıkarılan/fark bileşenini gösterdi · **hiçbir aday canonical
işaretlenmedi** · 209/209 test geçti · ruff/mypy temiz · vault validator
PASS. Hepsi **PASS**.

## Next Action
**Resolved (2026-07-15):** human/geophysical QC selected **D2** (dewow)
and **B1** (band-pass) as canonical — see
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]] and
`outputs/sprint03/canonical_D2_B1/`. Sprint 4 is still not activated by
this decision alone and requires the user's own explicit request — see
[[01_PROJECT_STATE/02_Next_Development_Sprint]].

Detay: `outputs/sprint03/SPRINT3_REVIEW_REQUIRED.md`,
`outputs/sprint03/dewow_candidates/comparison/DEWOW_REVIEW_REQUIRED.md`,
`outputs/sprint03/bandpass_candidates/comparison/BANDPASS_REVIEW_REQUIRED.md`,
`outputs/sprint03/combined_candidates/comparison/COMBINED_REVIEW_REQUIRED.md`.

## Related Notes
[[Sprint_Index]], [[Sprint_02_2_TimeAxis_DCWindow_Validation]],
[[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]],
[[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
[[05_PROCESSING/Dewow]], [[05_PROCESSING/Bandpass_Filter]],
[[01_PROJECT_STATE/03_Open_Issues]], [[01_PROJECT_STATE/04_Risks_and_Limitations]]
