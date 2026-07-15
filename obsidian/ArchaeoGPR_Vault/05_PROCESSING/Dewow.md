---
type: processing-module
status: implemented
implemented: true
---

# Dewow (Düşük Frekanslı Sürüklenme Giderimi)

> Sprint 3'te implemente edildi. Kod: `src/archaeogpr/processing/dewow.py`.
> **Canonical pencere/yöntem seçildi (2026-07-15): D2** — bkz. "Canonical
> Parameters" bölümü ve [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]].
> Bu, `Swath003_Array02.ogpr` için insan/jeofizik kararıdır; başka bir veri
> seti için otomatik olarak geçerli SAYILMAZ.

## Canonical Parameters (2026-07-15, ADR-007)

`method="running_mean"`, `requested_window_ns=8.0` →
`applied_window_ns=8.125` (65 örnek), `edge_mode="reflect"` — yani **D2**.
İnsan/jeofizik kararıyla seçildi (bkz.
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]), kodun kendisi tarafından otomatik
seçilmedi. Yalnızca `Swath003_Array02.ogpr` için canonical — başka bir
veri seti veya kazı ayarı kendi aday karşılaştırmasını ve kendi insan/
jeofizik incelemesini gerektirir. Canonical çıktı:
`outputs/sprint03/canonical_D2_B1/` (`python -m archaeogpr sprint3` — CLI
varsayılanları bu parametrelerdir).

## Purpose

Her izdeki çok-düşük-frekanslı sürüklenmeyi ("wow"), genellikle anten
indüksiyonu veya doygunluk etkilerinden kaynaklanan yavaş dalgalanmayı
gidermek. DC ofset gideriminden sonra ama band-pass filtrelemeden önce
uygulanır.

## Input

Herhangi bir `GPRDataset` (tipik olarak DC ofseti giderilmiş, ama fonksiyon
bunu zorunlu kılmaz). `valid_mask` (opsiyonel, şekil `(channels,
samples)`) verilirse padding hesaplamadan ve çıkarmadan hariç tutulur.

## Output

Düşük frekans bileşeni her izden çıkarılmış **yeni** bir `GPRDataset`;
kullanılan pencere/yöntem/kenar-modu parametreleri ve zengin diagnostics
`processing_history`'ye kaydedilir. `ProcessingResult.removed_component`
tahmini taban çizgisidir (baseline); padding'de tam sıfırdır.

## Mathematical Basis

Her (slice, channel) izi, her ardışık geçerli segment içinde bağımsız
olarak: `baseline(t) = MovingWindow[trace(t)]` (mean veya median, ortalanmış),
`corrected(t) = trace(t) - baseline(t)`. Pencere, segmentin kendi
değerleriyle (reflect/nearest) genişletilir — padding veya komşu segment
asla okunmaz. Hesaplama float64 hassasiyetinde yapılır, çıktı girdinin
dtype'ına (float32) döndürülür.

## Parameters

`window_ns` (varsayılan 8.0), `method` (`"running_mean"`/`"running_
median"`), `valid_mask` (opsiyonel), `edge_mode` (`"reflect"`
varsayılan/`"nearest"`), `allow_repeat_processing` (varsayılan `False`).
Tam imza: `src/archaeogpr/processing/dewow.py::correct_dewow`.

`window_ns`, `requested_samples = round(window_ns / sampling_time_ns)`
ile örneğe çevrilir; çift bir sonuç her zaman yukarı yuvarlanır (ortalanmış
pencere tek sayı gerektirir) — hem istenen hem uygulanan pencere her zaman
`diagnostics`'e ayrı ayrı kaydedilir, hiçbir zaman sessizce ikame edilmez.
Tam pencere/kenar politikası: [[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]].

## Risks

- Pencere çok kısa seçilirse (D1: 4ns) gerçek düşük-frekanslı yansımalar
  da zayıflatılabilir — ölçülen düşük-frekans enerji oranı D1 için
  0.7440 (D2: 0.8785, D4: 0.9392'ye kıyasla daha agresif kaldırma).
- Pencere çok uzun seçilirse (D3: 12ns) "wow" etkili şekilde
  giderilemeyebilir — ölçülen oran D3 için 0.5587 (en düşük giderme).
- `method="running_median"` doğrusal olmayan bir filtredir; running_mean'e
  basit bir eşdeğer olarak varsayılmamalıdır (kullanıldığında otomatik
  uyarı üretilir).
- Uygulanan pencere bir segmentin kendi uzunluğunu aşarsa **hata verir**
  (sessizce daha dar bir pencereye düşülmez).
- NaN/Inf üretilirse (girdi zaten bozuksa) fonksiyon **hata verir**.

## Required QC

Her aday için 13 dosyalık tam QC seti: `processing_metadata.json`,
`dewow_processed.npz`, channel00 before/after/removed/difference B-scan,
all-channels-after, medyan iz before/after, çıkarılan bileşenin medyan izi,
trace-mean histogramı, düşük-frekans spektrumu before/after,
`padding_verification.json`. Karşılaştırma çıktıları (D1-D4 arası):
`outputs/sprint03/dewow_candidates/comparison/` (metrik CSV'si +
`DEWOW_REVIEW_REQUIRED.md`). Tam liste ve doğrulama:
[[07_VALIDATION/QC_Output_Validation]].

## Acceptance Criteria

Tümü doğrulandı: (1) girdi mutasyona uğramaz, (2) çıkarılan bileşen
`removed_component` üzerinden erişilebilir, (3) sentetik testte periyodu
tam pencere uzunluğuna eşit bir yüksek-frekans sinyali korunurken
yavaş bir düşük-frekans bileşeni kaldırılıyor (ayrık toplam özdeşliğiyle
kanıtlandı), (4) fonksiyon opsiyoneldir, (5) `valid_mask` verildiğinde
padding hem pencere hesaplamasından hem çıkarmadan hariç tutulur ve
`fill_value`'da değişmeden kalır (gerçek veride doğrulandı).

## Candidate Comparison (Sprint 3, hiçbiri canonical değil)

| ID | Yöntem | İstenen pencere | Uygulanan pencere |
|---|---|---|---|
| D1 | running_mean | 4.0 ns | 4.125 ns |
| D2 | running_mean | 8.0 ns | 8.125 ns |
| D3 | running_mean | 12.0 ns | 12.125 ns |
| D4 | running_median | 8.0 ns | 8.125 ns |

Hangi adayın canonical olacağı insan/jeofizik incelemesi gerektiriyor —
bkz. [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-010.

## Sprint 3.1 — D2 Ayrıntılı Doğrulama, Sprint Canonicalization'da Onaylandı
[[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]], D2'nin removed
component'ini kanal 0/5/10 × 5 zaman penceresinde B-scan ile inceledi.
4 koşul da geçti: padding değişmemiş, faz kayması yok (medyan-iz
gecikmesi=0), çıkarılan bileşen koherent bir olay değil (adjacent-trace
corr 0.994-0.998, tüm pencerelerde — laterally continuous, hiperbolik
değil), 20-100ns tamamen bastırılmamış (RMS oranı 0.4801). Sonuç:
`recommended_dewow_candidate = D2` — bu mühendislik önerisi, sprint
canonicalization'da (2026-07-15) insan/jeofizik onayıyla **canonical**
yapıldı (bkz. yukarıdaki "Canonical Parameters"). Detay:
`outputs/sprint03_1/D2_DEWOW_DECISION.md`,
`outputs/sprint03_1/dewow_D2_validation/`.

## Implementation Status

**Implemented: true** (Sprint 3; D2 Sprint 3.1'de ayrıntılı doğrulandı,
sprint canonicalization'da (2026-07-15) canonical yapıldı — bkz. ADR-007).
Sentetik testler: `tests/test_dewow.py` (20 test). Gerçek dosya
entegrasyonu: `tests/test_sprint3_real_integration.py`,
`tests/test_sprint3_1_decision_qc.py`, `tests/test_sprint3_canonical.py`,
`tests/test_cli_sprint3_canonical.py`. Gerçek aday çıktıları:
`outputs/sprint03/dewow_candidates/`, `outputs/sprint03_1/`. Canonical
çıktı: `outputs/sprint03/canonical_D2_B1/`.

## Related Modules

[[Processing_Index]], [[Processing_Order]], [[DC_Offset]],
[[Time_Zero_Correction]], [[Bandpass_Filter]],
[[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
[[02_SPRINTS/Sprint_03_Dewow_Bandpass]],
[[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]]
