---
type: processing-module
status: done
implemented: true
canonical: false
---

# Arka Plan Çıkarma (Background Removal)

> **Canonical policy: A0 (uygulanmadı).** İnsan/jeofizik kararı
> (2026-07-16): background removal canonical zincire dahil edilmedi.
> Bu modül repository'de tam çalışan, deneysel/opt-in bir araç olarak
> kalıyor (`background`/`sprint4a-candidates` CLI alt komutları) — kod
> silinmedi. Bkz.
> [[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]].

## Purpose

Tüm izlerde ortak olan yatay bantlanma/çınlamayı (örn. sistem/anten
kaynaklı ringing) gidermek amacıyla, bir kanal için tüm dilimler
(slices) üzerinden (global) veya kayan bir pencere (sliding) üzerinden
hesaplanan trace-axis istatistiğini her izden çıkarmak.

## Input

Canonical Sprint 3 çıktısı (D2 dewow + B1 band-pass uygulanmış bir
`GPRDataset`) — bkz. [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]].

## Output

Kanal-bazlı background çıkarılmış **yeni** bir `GPRDataset`; çıkarılan
bileşen (`removed_component`) ve hesaplama parametreleri
`processing_history`/`diagnostics`'e kaydedilir.

## Mathematical Basis

Bir kanal `c` için, her örnek indeksi `s`'de: `background[c, s] =
TraceAxisStatistic(amplitudes[:, c, s])`, `amplitudes_corrected[slice, c,
s] = amplitudes[slice, c, s] - background[c, s]`. `TraceAxisStatistic`
dört yöntemden biridir: `global_mean`/`global_median` (tüm profil
üzerinden tek bir background değeri) veya `sliding_mean`/`sliding_median`
(merkezi bir kayan pencere, her iz için yeniden hesaplanır). Ortalama/
medyan **hiçbir zaman** kanallar arasında birleştirilmez — her kanal
kendi trace ekseninden bağımsız hesaplanır.

## Parameters

- `method`: `global_mean` | `global_median` | `sliding_mean` |
  `sliding_median`.
- `window_traces` / `window_m` (yalnızca sliding yöntemler için, ikisinden
  tam olarak biri) — metre→trace dönüşümü dataset'in kendi trace-spacing'i
  ile hesaplanır (`compute_trace_spacing()`: geolocation → metadata →
  unavailable önceliği), hiçbir zaman sabit gömülü değil; en yakın tek
  sayıya yuvarlanır.
- `edge_mode`: `reflect` (varsayılan) | `nearest` — sliding yöntemler için;
  asla sıfır-padding.

## Risks

- **Bu, projenin şu ana kadar implemente ettiği en bilimsel açıdan
  riskli filtredir.** Tüm profil boyunca yatay olarak uzanan gerçek
  arkeolojik hedefleri (örn. düz-yatan bir taban/döşeme kalıntısı, bir
  duvar temeli, bir katman sınırı) "arka plan" olarak yanlış tanıyıp
  bastırabilir — yatay süreklilik gösteren gerçek sinyal ile gerçek arka
  plan gürültüsü, bu yöntemle ayırt edilemez.
- **Global yöntemler (A1/A2) bu riski maksimum taşır** — background tüm
  profil üzerinden hesaplandığı için, profil boyunca gerçekten uzanan bir
  yansıma da background'a dahil olur.
- **Kayan pencere, pencereden daha geniş bir olayı kendi merkezinde
  neredeyse tamamen yok eder** (sentetik olarak doğrulandı — bkz.
  `outputs/sprint04a/background_candidates/comparison/
  window_length_vs_target_attenuation.png`); pencere çok kısaysa gerçek
  dikey/eğik yapılar da etkilenir. Genel kural: pencere, korunması
  istenen herhangi bir hedeften çok daha büyük seçilmelidir.
- Median tabanlı yöntemler outlier trace'lere karşı daha dayanıklıdır ama
  bu, gerçek veride "her zaman daha iyi" olduğu anlamına gelmez —
  yalnızca bir belgelenmiş politika farkıdır.

## Required QC

Çıkarılan bileşen (removed component) ayrıca görselleştirilir; düzeltme
öncesi/sonrası/çıkarılan/fark B-scan karşılaştırması; sinyal-koruma
metrikleri (RMS/energy/spectral retention, waveform correlation, local
event amplitude retention); removed-component metrikleri (energy ratios,
spatial coherence/concentration, frequency-band energy); QC-only
"localized event risk" proxy'si (`compute_localized_event_risk()` —
arkeolojik sınıflandırma YAPMAZ). Tam liste:
[[02_SPRINTS/Sprint_04A_Background_Removal]].

## Timing metriği açıklaması (Sprint 4A Closure, 2026-07-16)

`remove_background()` örnek/zaman eksenini ASLA yeniden örneklemez veya
kaydırmaz — her adayın çıktısı girdinin `time_ns` eksenini birebir
paylaşır. `candidate_metrics.csv`'deki `median_trace_cross_correlation_
lag_proxy_w5` kolonu (eski adı: `median_trace_cross_correlation_lag_w5`)
bir çapraz-korelasyon PİKİ gecikmesidir, programatik bir sample shift
DEĞİLDİR. A1-A8'de görülen sıfır-olmayan değerler, medyan izin kendi
dalga şeklinin (içeriğinin bir kısmı çıkarıldığı için) yeterince
değişmesi sonucu öncesi/sonrası medyan izler arasındaki korelasyon
pikinin başka bir lag'e kaymasıdır — hiçbir örneğin fiziksel olarak
kaydırıldığının kanıtı DEĞİLDİR. Bkz.
`outputs/sprint04a/BACKGROUND_FINAL_DECISION_REQUIRED.md` "How to read
this table" bölümü.

## Acceptance Criteria
Girdi mutasyona uğramaz; çıkarılan bileşen QC için erişilebilir
(`removed_component`); yatay hedef bastırma riski açıkça belgelenir
(ADR-008); fonksiyon opsiyoneldir (`remove_background()` her zaman açık
bir `method` parametresi gerektirir, varsayılan bir yöntem otomatik
uygulanmaz); valid_mask/padding güvenliği (çıktı VE removed component'te
padding tam sıfır); reprocessing guard (`allow_reprocessing=True` açık
opt-in gerektirir). **Hiçbir aday otomatik olarak canonical seçilmez.**

## Implementation Status

Bu modül Sprint 4A'da implemente edildi
(`src/archaeogpr/processing/background.py::remove_background()`,
`compute_trace_spacing()`). 8 aday (A1-A8) canonical Sprint 3 çıktısı
üzerinde gerçek veride çalıştırıldı. **2026-07-16'da insan/jeofizik
kararı: canonical policy = A0 (background removal uygulanmadı)** —
A1-A8'den hiçbiri canonical seçilmedi, canonical zincir Sprint 3 D2+B1
çıktısında kaldı, Gain başlatılmadı. Bu modül repository'de tam çalışan,
deneysel/opt-in bir araç olarak kalıyor. Bkz.
[[02_SPRINTS/Sprint_04A_Background_Removal]],
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]],
[[01_PROJECT_STATE/03_Open_Issues]] ISSUE-012 (kapatıldı).

## Related Modules

[[Processing_Index]], [[Processing_Order]], [[Bandpass_Filter]], [[FK_Filter]], [[Gain]]
