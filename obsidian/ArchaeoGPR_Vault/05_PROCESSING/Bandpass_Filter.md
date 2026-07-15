---
type: processing-module
status: implemented
implemented: true
---

# Band-Geçiren Filtre (Bandpass Filter)

> Sprint 3'te implemente edildi. Kod: `src/archaeogpr/processing/bandpass.py`.
> **Canonical bir aralık/yöntem seçildi (2026-07-15): B1** — bkz.
> "Canonical Parameters" bölümü ve
> [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]. Bu, `Swath003_Array02.ogpr` için
> insan/jeofizik kararıdır; başka bir veri seti için otomatik olarak
> geçerli SAYILMAZ.

## Canonical Parameters (2026-07-15, ADR-007)

`method="butterworth"`, `lowcut_mhz=100.0`, `highcut_mhz=900.0`,
`order=4`, `zero_phase=True` — yani **B1**. B1, B2'ye (120-800 MHz) karşı
**preservation-favoring** (bilgi-koruma öncelikli) mühendislik tercihi
olarak seçildi: daha fazla geçiş-bandı enerjisi + 800-900 MHz bandını
koruyor, daha yüksek geç-zaman waveform korelasyonu/mekânsal koherans
gösteriyor (bkz. [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]).
**800-900 MHz'de korunan enerji bir arkeolojik hedef yorumu DEĞİLDİR** —
yalnızca bir QC gözlemidir. Yalnızca `Swath003_Array02.ogpr` için
canonical — başka bir veri seti veya kazı ayarı kendi aday
karşılaştırmasını ve kendi insan/jeofizik incelemesini gerektirir.
Canonical çıktı: `outputs/sprint03/canonical_D2_B1/` (`python -m
archaeogpr sprint3` — CLI varsayılanları bu parametrelerdir).

## Purpose

Bir frekans bandını korurken bu bandın dışındaki gürültüyü reddetmek —
yansıma zamanlamasını (reflection timing) bozmadan (sıfır-faz).

## Input

Herhangi bir `GPRDataset` (tipik olarak dewow uygulanmış, ama fonksiyon
bunu zorunlu kılmaz). `valid_mask` (opsiyonel) verilirse padding
filtreden hariç tutulur.

## Output

Frekans içeriği belirtilen bantla sınırlandırılmış **yeni** bir
`GPRDataset`; kullanılan yöntem/kesim frekansları/order ve zengin
diagnostics `processing_history`'ye kaydedilir. `ProcessingResult.
removed_component := input - output`, padding'de tam sıfır.

## Mathematical Basis

İki bağımsız, ikisi de sıfır-faz (zero-phase) yöntem, her ardışık geçerli
segment içinde bağımsız uygulanır:
- **Butterworth**: `scipy.signal.butter(..., output="sos")` +
  `scipy.signal.sosfiltfilt(...)` — ileri-geri çift geçiş, net fazı
  sıfırlar.
- **Ormsby**: gerçek, simetrik bir yamuk transfer fonksiyonu, doğrudan FFT
  çarpımıyla uygulanır (dairesel evrişimi önlemek için iç reflect-doldurma
  ile); gerçek bir transfer fonksiyonu yapısı gereği sıfır-fazdır.

Tam tasarım ve faz-doğrulama metodolojisi:
[[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]].

## Parameters

`method` (`"butterworth"`/`"ormsby"`), Butterworth için `lowcut_mhz`,
`highcut_mhz`, `order` (varsayılan 4), `zero_phase` (varsayılan `True` —
`False` yalnızca faz-kayması karşıtlığını göstermek için), Ormsby için
`frequencies_mhz=(f1,f2,f3,f4)`, `valid_mask` (opsiyonel), `allow_repeat_
processing` (varsayılan `False`). Tam imza:
`src/archaeogpr/processing/bandpass.py::correct_bandpass`.

Parametre doğrulaması açık: Butterworth `0 < lowcut_mhz < highcut_mhz <
nyquist_mhz`, `order >= 1`; Ormsby `0 <= f1 < f2 < f3 < f4 < nyquist_mhz`.
Nyquist, gerçek `sampling_time_ns`'ten bağımsız hesaplanır.

## Risks

- Dar bant (B2: 120-800MHz, B4: 100/150/700/900MHz) gerçek sinyal
  enerjisini de reddedebilir.
- Geniş bant (B1: 100-900MHz, B3: 80/120/800/1000MHz) daha fazla bant-dışı
  gürültü tutar.
- `zero_phase=False` (yalnızca test/karşıtlık amaçlı) gerçek bir faz
  gecikmesi üretir — canonical kullanım için DEĞİLDİR.
- Segment, zero-phase Butterworth'ün gerektirdiği minimum uzunluktan
  kısaysa **hata verir** (sessiz bir fallback yoktur).
- Header'ın 600 MHz nominal frekansı TEK BAŞINA bir aralık seçim kriteri
  değildir — bağımsız yeniden ölçülmedi (bkz.
  `outputs/sprint03/spectrum/SPECTRUM_INTERPRETATION_NOTES.md`).
- NaN/Inf üretilirse fonksiyon **hata verir**.

## Required QC

Her aday için 13 dosyalık tam QC seti: `processing_metadata.json`,
`bandpass_processed.npz`, channel00 before/after/removed/difference
B-scan, all-channels-after, medyan iz before/after, spektrum before/after,
transfer fonksiyonu, dürtü tepkisi, `padding_verification.json`.
Karşılaştırma çıktıları (B1-B4 arası):
`outputs/sprint03/bandpass_candidates/comparison/` (metrik/faz-gecikmesi/
spektral CSV'leri + `BANDPASS_REVIEW_REQUIRED.md`). Tam liste ve
doğrulama: [[07_VALIDATION/QC_Output_Validation]].

## Acceptance Criteria

Tümü doğrulandı: (1) girdi mutasyona uğramaz, (2) kesim frekansları/yöntem
kayıt altına alınır, (3) sentetik testte geçiş-bandı sinüsü korunurken
durdurma-bandı sinüsü bastırılıyor (her iki yöntem), zero-phase pulse
pikini korurken causal varyant kaydırıyor (karşıtlık testi), (4) fonksiyon
opsiyoneldir, (5) `valid_mask` verildiğinde padding hariç tutulur ve
değişmeden kalır (gerçek veride doğrulandı, medyan-iz gecikmesi=0).

## Candidate Comparison (Sprint 3, D2 dewow tabanında, hiçbiri canonical değil)

| ID | Yöntem | Parametreler | Maks. medyan-iz gecikmesi (gerçek veri) |
|---|---|---|---|
| B1 | butterworth | 100-900 MHz, order=4 | 0 |
| B2 | butterworth | 120-800 MHz, order=4 | 0 |
| B3 | ormsby | 80/120/800/1000 MHz | 0 |
| B4 | ormsby | 100/150/700/900 MHz | 0 |

Hangi adayın canonical olacağı insan/jeofizik incelemesi gerektiriyor —
bkz. [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-011.

## Sprint 3.1 — B1 vs B2 Karar QC'si, Sprint Canonicalization'da B1 Seçildi
[[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]], B3/B4'ü hariç
tutarak yalnızca B1 ve B2'yi karar-odaklı olarak karşılaştırdı:
frekans-bandı enerji tabloları (B1, 800-900 MHz'de B2'ye göre ~3.3-3.6×
daha fazla enerji koruyor), mekânsal süreklilik (W4: B1=0.9247,
B2=0.9077), faz/waveform koruması. Mühendislik eğilimi
(**preservation-favoring/B1**), sprint canonicalization'da (2026-07-15)
insan/jeofizik kararıyla **B1'in canonical seçilmesiyle** sonuçlandı
(bkz. yukarıdaki "Canonical Parameters").
**Önemli metodolojik not:** B2'nin geç-zaman (20-100ns) penceresindeki ham
medyan-iz gecikmesi (40 örnek) gerçek bir faz kayması DEĞİLDİR — spektral
farklılıktan kaynaklanan bir ölçüm sınırlamasıdır; yetkili sıfır-faz kanıtı
(tam-segment lag=0, her iki aday için) ADR-006 ile hâlâ tutarlıdır. Detay:
`outputs/sprint03_1/BANDPASS_FINAL_DECISION_REQUIRED.md`,
`outputs/sprint03_1/PHASE_METRICS_INTERPRETATION_NOTES.md`.

## Implementation Status

**Implemented: true** (Sprint 3; B1/B2 Sprint 3.1'de karar-odaklı
karşılaştırıldı, B1 sprint canonicalization'da (2026-07-15) canonical
yapıldı — bkz. ADR-007). Sentetik testler: `tests/test_bandpass.py`
(20 test). Gerçek dosya entegrasyonu: `tests/test_sprint3_real_
integration.py`, `tests/test_sprint3_1_decision_qc.py`,
`tests/test_sprint3_canonical.py`, `tests/test_cli_sprint3_canonical.py`.
Gerçek aday çıktıları: `outputs/sprint03/bandpass_candidates/`,
`outputs/sprint03/combined_candidates/`, `outputs/sprint03_1/`. Canonical
çıktı: `outputs/sprint03/canonical_D2_B1/`.

## Related Modules

[[Processing_Index]], [[Processing_Order]], [[Dewow]],
[[Background_Removal]],
[[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
[[02_SPRINTS/Sprint_03_Dewow_Bandpass]],
[[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]]
