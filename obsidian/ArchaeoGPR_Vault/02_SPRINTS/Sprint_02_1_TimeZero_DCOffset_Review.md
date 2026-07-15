---
type: sprint
tags: [sprint, review]
sprint: 2.1
status: done
started: 2026-07-14
completed: 2026-07-15
---

# Sprint 2.1 — Time-Zero & DC Offset Real-Data Review, Padding-Mask Safety, and Final QC

> **Status update (2026-07-15):** `review_required` → **`done`**. This
> sprint's own findings (unsafe default clipping, DC-offset padding
> contamination) were fixed and verified here. The `target_sample=0` vs
> `16` question this sprint deliberately left open was resolved by
> [[Sprint_02_2_TimeAxis_DCWindow_Validation]], which also found and fixed
> an additional, deeper issue this sprint's comparison exposed but did not
> diagnose: the whole-valid-trace DC offset mean used below is itself not a
> target-sample-invariant statistic. The content below is this sprint's
> own original record and was left unmodified.

## Goal
Bu sprint yeni bir filtre veya sinyal işleme algoritması DEĞİLDİR. Amacı,
Sprint 2'nin gerçek veri sonuçlarının doğru olduğunu varsaymadan kod
seviyesinde denetlemek, time-zero'nun ürettiği padding bölgesinin DC offset
aşamasında güvenli ele alınmasını sağlamak, kırpma davranışını güvenli bir
politikaya taşımak, ve `target_sample=0` ile `target_sample=16` adaylarını
insan/jeofizik incelemesi için karşılaştırmalı olarak sunmaktır.

## Scope
- Kod denetimi: Sprint 2'nin `correct_dc_offset()`'inin time-zero padding
  bölgesini nasıl ele aldığının somut biçimde yeniden üretilmesi (audit).
- `overflow_policy: Literal["error", "clip"]` — varsayılan `"error"`
  (sessizce/otomatik kırpma YOK; veriye dokunulmadan önce açık hata).
  `"clip"` yalnızca açık opt-in ile erişilebilir ve sonucu
  `valid_for_downstream_processing=False` işaretler.
- `ProcessingResult.valid_mask` — time-zero'nun ürettiği, hangi örneklerin
  gerçek kaydırılmış veri (`True`) hangisinin padding (`False`) olduğunu
  gösteren `(channels, samples)` boyutlu, salt-okunur bir maske.
- `correct_dc_offset()`'in `valid_mask` ile bütünleşmesi: ofset hesaplaması
  VE çıkarma işlemi padding örneklerini hariç tutar; padding, time-zero'nun
  `fill_value`'unda tam olarak (byte-bazında) kalır.
- CLI: `--overflow-policy error|clip`, yeni çıktılar
  (`padding_mask_channelNN.png`, `valid_sample_summary.json`), `sprint2`
  komutunun DC offset'e time-zero'nun maskesini geçirmesi.
- 24 yeni test (bkz. Testing) + regresyon (mevcut 77 test).
- Gerçek veri: `target_sample` 0 ve 16 adaylarının
  `max_shift_samples=96, overflow_policy=error` ile karşılaştırmalı
  çalıştırılması — bu **doğrulama amaçlı bir komuttur**, kodda yeni bir
  varsayılan DEĞİLDİR.
- Karşılaştırma çıktıları ve `REVIEW_REQUIRED.md` — otomatik target_sample
  seçimi YOK.

## Out of Scope
Dewow, band-pass, background removal, gain, AGC, F-K, migration, velocity
analysis, envelope, depth-slice, anomaly detection, Blender/QGIS export,
GUI, trace-by-trace time-zero, sub-sample shifting, **otomatik
target_sample seçimi**, **otomatik arkeolojik yorum**. Sprint 3 bu
sprintte kesinlikle BAŞLATILMADI.

## Trigger — Neden bu sprint gerekli oldu
Sprint 2'nin gerçek veri çalıştırması (`outputs/sprint02/combined/`),
varsayılan `max_shift_samples=64` + `target_sample=0` ile **9/11 kanalı
kırptı** (bkz. [[01_PROJECT_STATE/03_Open_Issues]], eski ISSUE-005). Bu
durum üç ek soruyu gündeme getirdi:
1. Kırpılmış bir sonuç, normal bir "başarı" çıktısı gibi kaydediliyordu —
   bu güvenli bir varsayılan değildi.
2. Time-zero'nun ürettiği padding bölgesi, DC offset aşamasında nasıl ele
   alınıyordu? Sprint 2'de bu hiç denetlenmemişti.
3. `target_sample=0`, pick'ten önceki tüm örnekleri (öndeki dalga
   biçimini/direct-wave onset'ini) geri dönüşü olmayan biçimde atıyor
   olabilir.

Bu üçü, [[Sprint_02_TimeZero_DCOffset]]'in vault durumunu `review_required`
durumuna taşıyan sebeplerdir.

## Code-Level Audit Findings
### 1. Eski kırpma davranışı (Sprint 2, değiştirilmeden önce)
`correct_time_zero()`, `max_shift_samples` aşıldığında HER ZAMAN kırpıyordu
(opt-out yoktu, tek davranış buydu). Gerçek dosyada bu, 9/11 kanalın
`target_sample=0`'a TAM hizalanmadığı ama sonucun yine de normal bir
`ProcessingResult` olarak (açık uyarıyla birlikte) döndüğü anlamına
geliyordu. Kod hatası değildi ama güvensiz bir varsayılandı — kırpılmış
veri, kırpılmamış veriyle aynı "başarı" görünümündeydi.

### 2. Eski DC offset + padding etkileşimi (somut olarak yeniden üretildi)
Denetim için sentetik bir pulse+bias veri seti oluşturuldu ve eski (maske
farkındalığı olmayan) `correct_dc_offset()`, time-zero'dan sonra
çalıştırıldı: padding bölgesi time-zero çıkışında `[0, 0, 0, ...]`
(doğru, `fill_value=0.0`) idi, ama eski DC offset'ten SONRA
`[-8, -8, -8, ...]`'e döndü — yani padding, gerçek olmayan bir "ofset
bandı" ile kirleniyordu. Bu somut, yeniden üretilmiş bir bulgudur (yalnızca
teorik değil) ve bu sprintin ana motivasyonudur.

## Changes Made
- `processing/time_zero.py`: `_apply_overflow_policy()` eklendi
  (`"error"` → veriye dokunulmadan `ProcessingError`, kanal başına
  detaylı mesaj; `"clip"` → kırpar + `has_clipped_shifts=True`,
  `valid_for_downstream_processing=False` diagnostics'i işaretler + uyarı
  üretir). `valid_mask` (channels, samples) hesaplanır, `ProcessingResult`e
  eklenir.
- `processing/result.py`: `ProcessingResult.valid_mask: np.ndarray | None`
  eklendi; şekil `(channels, samples)`, dtype `bool`, salt-okunur
  (`__post_init__` içinde doğrulanır ve dondurulur).
- `processing/dc_offset.py`: `valid_mask` parametresi eklendi (varsayılan
  `None` — eski davranış birebir korunur). Verildiğinde: ofset SADECE
  `window ∩ valid_mask` kesişiminden hesaplanır; çıkarma SADECE geçerli
  konumlara uygulanır; padding girdiden hiç okunmadığı/yazılmadığı için
  `fill_value`'da byte-bazında değişmeden kalır. Bir kanalın pencere
  içinde sıfır geçerli örneği varsa açık `ProcessingError` verilir.
- `qc/time_zero.py`: `save_padding_mask_plot()` eklendi (yeşil=geçerli,
  kırmızı=padding, hedef çizgisi işaretli, sayısal özet metni).
- `qc/__init__.py`: `qc.time_zero`/`qc.dc_offset` export'ları düzeltildi
  (Sprint 2'den kalan bir boşluk — bu modüller vardı ama hiç export
  edilmiyordu).
- `export/processed.py`: `write_valid_sample_summary_json()` eklendi;
  `write_corrected_npz`/`write_combined_npz`, `valid_mask` mevcutsa NPZ'ye
  ekler (`has_valid_mask` her zaman yazılır, `None` object array olarak
  ASLA yazılmaz).
- `cli.py`: `--overflow-policy error|clip` (varsayılan `error`, hem
  `time-zero` hem `sprint2` alt komutlarında); `sprint2` komutu artık
  `correct_dc_offset(..., valid_mask=tz_result.valid_mask)` çağırıyor; yeni
  çıktılar (`padding_mask_channelNN.png`, `valid_sample_summary.json`) ve
  konsol uyarıları (`valid_for_downstream_processing=False` olduğunda)
  eklendi.
- `CLAUDE.md`: kırpma politikası satırı, yeni `overflow_policy`
  davranışını yansıtacak şekilde güncellendi (eski "aşan bir shift her
  zaman kırpılır" kuralı artık yanlıştı — bkz.
  [[06_DECISIONS/ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]]).

## Testing
24 yeni test + regresyon (mevcut 77 test hiç bozulmadı; toplam **101/101
passed**, bkz. [[07_VALIDATION/Test_Results]]):
- `test_time_zero.py` (20→30, +10): varsayılan politika veriye dokunmadan
  hata verir; `overflow_policy="error"` açıkça verildiğinde de hata verir;
  kırpılmış sonuca yalnızca açık opt-in ile erişilebilir; kırpılmış sonuç
  `valid_for_downstream_processing=False`, kırpılmamış sonuç `True`
  işaretlenir; `valid_mask` sol kaydırmada (trailing padding), sağ
  kaydırmada (leading padding), sıfır kaydırmada (tümü `True`) doğru;
  `valid_mask` şekli `(channels, samples)`; `valid_mask` salt-okunur.
- `test_dc_offset.py` (15→24, +9): padding, ofset hesaplamasından hariç
  tutulur; padding, çıkarma işleminden etkilenmez; sıfır padding değeri
  sıfır kalır; geçerli bölge ortalaması sıfıra yaklaşır (padding
  etkilenmeden); pencere ∩ maske kesişimi doğru hesaplanır; sıfır geçerli
  örnek olduğunda açık hata; maskesiz eski davranış birebir korunur;
  maskeli girdi mutasyona uğramaz; `processing_history` maske politikasını
  kaydeder.
- `test_export_processed.py` (yeni dosya, 0→4, +4): NPZ round-trip'in
  `valid_mask`'ı hem tekil (`write_corrected_npz`) hem birleşik
  (`write_combined_npz`, DC offset'in kendi maskesi olmadığında time-zero
  maskesine düşme davranışı dahil) export'ta koruduğu; maskesiz export'ta
  `valid_mask` anahtarının hiç yazılmadığı.
- `test_sprint2_real_integration.py` (1→2, +1): gerçek dosyada
  `max_shift_samples=96, overflow_policy=error` ile sıfır kırpma, tüm
  kanallarda `applied_shift == requested_shift`.

## Real Data Validation
Bkz. [[07_VALIDATION/QC_Output_Validation]] "Sprint 2.1" bölümü ve
[[04_DATASETS/Swath003_Array02]]. Özet:
- `target_sample=0` ve `target_sample=16`, her ikisi
  `max_shift_samples=96, overflow_policy=error` ile **sıfır kırpma**
  verdi (11/11 kanalda `applied_shift == requested_shift`,
  `has_clipped_shifts=False`, `valid_for_downstream_processing=True`).
- Ham dosya hash'i (`66d840c313b4beed10bea2e35d88431573f6fab0f02bba17792c0920028b62a6`)
  tüm çalıştırmalar boyunca (4 gerçek veri komutu + karşılaştırma script'i)
  değişmedi.
- Birleşik pipeline'da DC offset, time-zero'nun `valid_mask`'ını kullandı
  (`valid_mask_provided=True`, konsol çıktısında `DC offset valid_mask
  used: True`); her iki adayda da padding bölgesi DC offset'ten SONRA tam
  olarak `[0.0]` kaldı (11 kanalın hepsinde ayrı ayrı doğrulandı) —
  denetim bulgusu gerçek veri üzerinde somut olarak düzeltildi.
- Varsayılan parametrelerle (`max_shift_samples=64` implicit,
  `overflow_policy=error` implicit) çalıştırılan `time-zero` komutu
  beklendiği gibi hata ile durdu (exit code 1) ve **çıktı klasörü hiç
  oluşturulmadı** — kırpılmış/eksik bir sonucun "başarı" gibi
  kaydedilmediği doğrudan doğrulandı.

## Comparison Outputs (target_sample 0 vs 16)
`outputs/sprint02_review/` altında (repository'de, vault dışı):
- `target_sample_00/`, `target_sample_16/` — standalone time-zero, her
  biri 15 dosya (`channel_picks.csv`, `channel_median_traces_*.png`,
  `channel00_*.png`, `channel00_before_after_difference.png`,
  `all_channels_{before,after}.png`, `picks_and_shifts.png`,
  `padding_mask_channel00.png`, `valid_sample_summary.json`,
  `processing_metadata.json`, `time_zero_corrected.npz`).
- `combined_target00/`, `combined_target16/` — birleşik pipeline (DC
  offset, time-zero'nun `valid_mask`'ını kullanıyor).
- `comparison/` — `discarded_leading_samples.csv`, `padding_summary.csv`,
  `target00_vs_target16_channel00.png`,
  `target00_vs_target16_all_channel_medians.png`, `comparison_summary.json`.
- `REVIEW_REQUIRED.md` — insan/jeofizikçi incelemesi için özet.
  **Hiçbir otomatik "target 0 daha iyi" veya "target 16 daha iyi" kararı
  verilmedi** — yalnızca ölçülen/türetilmiş sayılar ve görseller sunuldu.

Eski `outputs/sprint02/combined/` (9/11 kanal kırpılmış) **silinmedi,
üzerine yazılmadı** — `SUPERSEDED_PENDING_REVIEW.md` sidecar dosyasıyla
işaretlendi (bkz. [[07_VALIDATION/QC_Output_Validation]]).

## Acceptance Criteria
- Varsayılan `overflow_policy` veriye dokunulmadan hata verir — **doğrulandı**.
- Kırpma yalnızca açık `overflow_policy="clip"` ile erişilebilir — **doğrulandı**.
- `valid_mask` doğru şekil/taraf/salt-okunurluk — **doğrulandı**.
- DC offset padding'i hem hesaplamadan hem çıkarmadan hariç tutar —
  **doğrulandı** (sentetik + gerçek veri).
- Gerçek veride `max_shift_samples=96` ile sıfır kırpma (her iki hedef) —
  **doğrulandı**.
- Karşılaştırma çıktıları üretildi, otomatik karar verilmedi — **doğrulandı**.
- Mevcut 77 test kırılmadı — **doğrulandı** (toplam 101/101 geçti).
- Sprint 3 başlatılmadı, nihai target_sample seçilmedi — **doğrulandı**.

## Next Action
**Next action: Human geophysical QC of target_sample 0 vs 16 candidates.**

Detay: `outputs/sprint02_review/REVIEW_REQUIRED.md` (repository'de, vault
dışı — büyük ikili çıktılar vault'a kopyalanmaz), bkz.
[[01_PROJECT_STATE/02_Next_Development_Sprint]].

## Related Notes
[[Sprint_02_TimeZero_DCOffset]], [[Sprint_Index]],
[[06_DECISIONS/ADR_002_TimeZero_Reference_and_Shift_Policy]],
[[06_DECISIONS/ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]],
[[05_PROCESSING/Time_Zero_Correction]], [[05_PROCESSING/DC_Offset]],
[[01_PROJECT_STATE/03_Open_Issues]], [[01_PROJECT_STATE/04_Risks_and_Limitations]]
