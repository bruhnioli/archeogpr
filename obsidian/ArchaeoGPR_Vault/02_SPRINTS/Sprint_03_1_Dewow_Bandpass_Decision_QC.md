---
type: sprint
tags: [sprint, review]
sprint: 3.1
status: done
started: 2026-07-15
completed: 2026-07-15
---

# Sprint 3.1 — D2 Dewow Confirmation & B1/B2 Band-Pass Decision QC

> **Human Decision (2026-07-15):** the user reviewed
> `DECISION_PANEL_D2_B1_B2.png` and `BANDPASS_FINAL_DECISION_REQUIRED.md`
> and made the final call: **D2 is confirmed** (the engineering
> recommendation below is accepted as-is) and **B1 is selected** over B2
> (following this sprint's documented preservation-favoring engineering
> trend). The canonical chain is Sprint 2 canonical → D2 → B1 — see
> [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]] and
> `outputs/sprint03/canonical_D2_B1/`. This sprint's status moves to
> `done`. The content below is this sprint's own original record and was
> left unmodified.

## Goal
Yeni bir sinyal işleme algoritması GELİŞTİRİLMEDİ. Sprint 3'ün mevcut
`correct_dewow()`/`correct_bandpass()` implementasyonlarını kullanarak: (1)
D2 dewow adayını ayrıntılı biçimde doğrulamak, (2) yalnızca B1 ve B2
band-pass adaylarını (B3/B4 hariç) karşılaştırmak, (3) doğrudan dalga
dışındaki (20-100 ns) refleksiyonların korunmasını incelemek, (4) nihai
band-pass seçimi için karar odaklı QC çıktıları üretmek. **Hiçbir aday bu
sprintte canonical seçilmedi.**

## Scope
- D2'nin çıkarılan bileşeninin (removed component) pencere-bazlı B-scan
  incelemesi (kanal 0/5/10, 5 zaman penceresi).
- Yalnızca B1 ve B2'nin pencere-bazlı B-scan karşılaştırması.
- Mutlak / ortak-dB-referanslı / kendi-piki-normalize edilmiş spektrum
  karşılaştırması (W1-W4).
- Frekans-bandı enerji tabloları (kanal-bazlı, pencere-bazlı) + B1 vs B2
  800-900 MHz enerji özeti (5 spesifik soru numerik olarak yanıtlandı).
- Mekânsal süreklilik metrikleri (adjacent-trace correlation, local RMS,
  trace-to-trace difference energy, channel-to-channel consistency,
  removed-component coherence).
- Faz/dalgacık koruması: ana pik farkı, sıfır geçişi farkı, lokal waveform
  correlation, polarity korunması — hem doğrudan dalga hem geç-zaman (W4)
  pencerelerinde.
- D2 karar notu (koşullu, otomatik canonical seçim DEĞİL).
- B1/B2 karar dosyası (`BANDPASS_FINAL_DECISION_REQUIRED.md`) — mühendislik
  eğilimi belirtilir, kesin seçim yapılmaz.
- Tek karar paneli (`DECISION_PANEL_D2_B1_B2.png`).
- 23 yeni test.

## Out of Scope
Background removal, gain, AGC, F-K, migration, velocity analysis, envelope,
depth-slice, Blender/QGIS export, GUI, otomatik arkeolojik sınıflandırma,
Sprint 4, yeni bir filtre yöntemi, otomatik canonical band-pass seçimi. B3
ve B4 için yeniden çıktı üretilmedi (yalnızca B1/B2).

## Candidates Used (Sprint 3'ten değişmeden)
- **D2**: `running_mean`, `requested_window_ns=8.0` → `applied_window_ns=
  8.125` (65 örnek), `edge_mode=reflect`.
- **B1**: Butterworth, 100-900 MHz, order=4, zero-phase (= Sprint 3'ün C4
  kombinasyonunun band-pass tarafı).
- **B2**: Butterworth, 120-800 MHz, order=4, zero-phase (= Sprint 3'ün C2
  kombinasyonunun band-pass tarafı).

## Implementation
Yeni kod, yalnızca QC/analiz katmanıdır — hiçbir yeni filtre algoritması
içermez:
- `src/archaeogpr/qc/spatial_coherence.py` — adjacent-trace correlation,
  local RMS, trace-to-trace difference energy, channel-to-channel
  consistency, removed-component coherence, band-energy concentration.
- `src/archaeogpr/qc/phase_metrics.py` — ana pik farkı, sıfır geçişi farkı,
  lokal waveform correlation, polarity korunması, ve `median_trace_lag()`
  (ADR-006'nın medyan-iz çapraz-korelasyon yöntemini genelleştirir).
- `src/archaeogpr/qc/band_energy.py` — bant enerjisi entegrasyonu
  (`compute_amplitude_spectrum`'u yeniden kullanır), iz-bazlı bant enerjisi
  (yeni, tek genuinely yeni hesaplama), retention ratio, RMS farkı.
- `src/archaeogpr/qc/decision_qc.py` — pencereli B-scan ızgaraları, 3-modlu
  spektrum karşılaştırması, karar paneli (tüm plotting; padding her zaman
  açıkça gri maskelenir).
- `scripts/generate_sprint3_1_decision_qc.py` — orkestrasyon (Sprint
  2.1/2.2'nin `generate_*.py` desenini izler); `outputs/sprint03_1/`'a
  yazar.

## Önemli Metodolojik Bulgu: Geç-Zaman Faz Metriği Sınırlaması
B2'nin geç-zaman (20-100 ns) penceresindeki medyan-iz gecikmesi 40 örnek
çıktı — bu **gerçek bir faz kayması DEĞİLDİR**. B2'nin dar bandı (120-800
MHz), dewow-only çıktının bu pencerede hâlâ taşıdığı düşük-frekans içeriğin
çoğunu kaldırıyor; bu yüzden "önce" (D2) ve "sonra" (D2+B2) sinyalleri, bu
dar pencerede önemli ölçüde farklı spektral karaktere sahip oluyor —
çapraz-korelasyonu çapalayacak güçlü, ortak bir olay kalmıyor (doğrudan
dalga penceresinin veya tüm geçerli segmentin aksine). Yetkili sıfır-faz
kanıtı, `correct_bandpass()`'in kendi tam-segment tanılamasıdır (ADR-006,
B1 ve B2 için lag=0, bu sprintte de yeniden doğrulandı). Tam detay:
`outputs/sprint03_1/PHASE_METRICS_INTERPRETATION_NOTES.md`.

## Testing
23 yeni test (`tests/test_sprint3_1_decision_qc.py`), mevcut 209 test hiç
bozulmadı — toplam **232/232 passed**: mutlak/normalize/ortak-dB spektrum
modları, pencere örnek seçimi, padding FFT'ten hariç, bant enerjisi
entegrasyonu/retention oranı, B1/B2 ortak amplitude scale, çıkarılan
bileşen doğruluğu, mekânsal korelasyon (sentetik koherent olayda yüksek,
rastgele gürültüde düşük), bilinen sıfır-faz filtrede medyan-iz gecikmesi
sıfır (causal karşıtlığıyla), girdi/zaman ekseni/valid_mask/ham+canonical
hash değişmiyor (gerçek dosya varsa).

## Real Data Results
- Girdi: `outputs/sprint02/canonical_target16/sprint02_processed.npz`
  (hash değişmedi), padding D2'den sonra byte-bazında değişmedi.
- D2 karar koşulları (4/4 geçti): padding değişmemiş; faz kayması yok
  (medyan-iz gecikmesi=0, doğrudan dalga); çıkarılan bileşen koherent bir
  olay değil (adjacent-trace corr 0.994-0.998, tüm pencerelerde); 20-100ns
  tamamen bastırılmamış (RMS oranı 0.4801 > 0.3 eşiği).
  → `recommended_dewow_candidate = D2` (mühendislik önerisi, otomatik
  canonical seçim DEĞİL).
- B1 vs B2 800-900 MHz: B1 ~3.3-3.6× daha fazla enerji koruyor (kanal
  bazında tutarlı, CV≈0.33); bu enerji trace'ler arasında biraz
  yoğunlaşmış (top-%5 trace, enerjinin %30.7'sini taşıyor); B2'nin
  çıkardığı bu bandın mekânsal korelasyonu yüksek (0.9605 medyan).
- 20-100ns RMS farkı (B1 vs B2, tüm kanallar): 210.7.
- Mekânsal koherans (W4): D2=0.8449, B1=0.9247, B2=0.9077.
- Mühendislik eğilimi: **preservation-favoring candidate** (B1) — ama
  kesin seçim yapılmadı.

## Generated Outputs
`outputs/sprint03_1/` (24 dosya): `dewow_D2_validation/`,
`bandpass_B1_B2_bscan/`, `spectrum_windows/`,
`DECISION_PANEL_D2_B1_B2.png`, `BANDPASS_FINAL_DECISION_REQUIRED.md`,
`D2_DEWOW_DECISION.md`, `band_energy_by_channel.csv`,
`band_energy_by_time_window.csv`, `B1_vs_B2_energy_summary.json`,
`spatial_coherence_metrics.csv`, `spatial_coherence_comparison.png`,
`removed_component_coherence.png`, `phase_waveform_metrics.json`,
`PHASE_METRICS_INTERPRETATION_NOTES.md`, `BAND_ENERGY_TABLE_NOTES.md`. Tam
liste ve doğrulama: [[07_VALIDATION/QC_Output_Validation]].

## Acceptance Criteria
Girdi/ham dosya/canonical NPZ hash değişmedi · girdi mutasyona uğramadı ·
`time_ns`/`valid_mask` değişmedi · padding tüm işlemlerden sonra tam sıfır
kaldı · B1/B2 ortak amplitude scale gerçekten ortak · ortak dB referansı
gerçekten ortak · 232/232 test geçti · ruff/mypy temiz · vault validator
PASS · **hiçbir band-pass adayı canonical yapılmadı** · Sprint 4
başlatılmadı. Hepsi **PASS**.

## Next Action
**Resolved (2026-07-15):** the user reviewed `DECISION_PANEL_D2_B1_B2.png`
and `BANDPASS_FINAL_DECISION_REQUIRED.md` and decided — D2 confirmed, B1
selected over B2. See [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]
and `outputs/sprint03/canonical_D2_B1/`. Sprint 4 is still not activated
by this decision alone and requires the user's own explicit request —
see [[01_PROJECT_STATE/02_Next_Development_Sprint]].

## Related Notes
[[Sprint_Index]], [[Sprint_03_Dewow_Bandpass]],
[[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]],
[[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
[[05_PROCESSING/Dewow]], [[05_PROCESSING/Bandpass_Filter]],
[[01_PROJECT_STATE/02_Next_Development_Sprint]]
