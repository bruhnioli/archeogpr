---
type: adr
tags: [decision]
id: ADR-005
status: accepted
date: 2026-07-15
---

# ADR-005 — Dewow Window Conversion, Edge Handling, and Masked-Segment Policy

## Context
Sprint 3 dewow'u (`correct_dewow()`), her (slice, channel) izini bağımsız
olarak, çok-düşük-frekanslı "wow" sürüklenmesini kayan pencere (mean/median)
tabanlı bir taban çizgisi tahmini çıkararak düzeltir. Bu, ADR-003'te
kaydedilen `valid_mask`/padding deseniyle (bkz.
[[ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]]) doğrudan
etkileşen ilk *kayan pencereli* işlemdir — bir kayan pencere, `correct_dc_
offset()`'in tek-nokta ofsetinin aksine, padding sınırına yaklaştıkça
kenar etkisi (edge effect) üretebilir. Bu ADR, pencere/örnek dönüşümünün,
kenar (edge) davranışının ve padding/valid-segment ele alınışının kesin
politikasını kaydeder.

## Decision
1. **Pencere dönüşümü hiçbir zaman sessizce yuvarlanmaz.** Kullanıcının
   istediği `window_ns`, `requested_samples = round(window_ns /
   sampling_time_ns)` ile örneğe çevrilir. Ortalanmış bir pencere tek
   sayıda örnek gerektirdiği için, çift bir sonuç **her zaman yukarı**
   yuvarlanır (`applied_samples = requested_samples + 1`) — asla aşağı
   (bu pencereyi istenenden daha dar ve daha fazla sinyal-yiyen yapardı).
   Hem `requested_window_ns`/`requested_window_samples` hem `applied_
   window_ns`/`applied_window_samples` her zaman `diagnostics`'e kaydedilir
   ve bir bump olduğunda açık bir uyarı üretilir — uygulanan değer hiçbir
   zaman sessizce ikame edilmez. Gerçek veride D1-D4 adaylarının uygulanan
   pencereleri: 4.125/8.125/12.125/8.125 ns (istenen 4.0/8.0/12.0/8.0
   ns'den, 0.125 ns örnekleme aralığında, hepsi 65/33/97/65 örnek gibi tek
   sayılara yuvarlandı).
2. **Uygulanan pencere 3 örneğin altına düşerse hata verilir**
   (`_MIN_APPLIED_WINDOW_SAMPLES = 3`) — bu kadar dar bir pencere
   anlamlı bir "yavaş sürüklenme" tahmini değil, gürültünün kendisidir.
3. **Kenar (edge) modu yalnızca `"reflect"` (varsayılan) veya `"nearest"`
   olabilir — sıfır-doldurma (zero-padding) hiçbir zaman bir seçenek
   değildir.** Sıfır-doldurma, geçerli segmentin kendi kenarında yapay bir
   süreksizlik (sahte bir "sıfıra düşüş") yaratırdı; bu, kayan pencerenin
   segment kenarına yakın örneklerdeki tahminini bozardı. `"reflect"`
   segmenti kendi değerleriyle aynalar (numpy'nin `reflect` modu);
   `"nearest"` kenar örneğini dışarıya sabit tutar (numpy'nin `edge` modu).
4. **Pencere, padding'i veya komşu segmentleri hiçbir zaman okumaz.**
   `contiguous_true_runs()` (bkz. madde 6) her kanalın geçerli
   örneklerini bağımsız aralıklara ayırır; kayan pencere yalnızca KENDİ
   segmentinin içine `numpy.pad` uygular — asla padding'e veya farklı bir
   segmente. Bir segmentin uygulanan penceresi kendi uzunluğunu aşarsa
   (`applied_window_samples > segment_length`) açık `ProcessingError`
   verilir — asla sessizce daha dar bir pencereye düşülmez.
5. **Padding, çıktıda byte-bazında değişmeden kalır; `removed_component`
   padding'de tam olarak sıfırdır.** Girdi `input_amplitudes`'in bir kopyası
   üzerine yalnızca geçerli segment konumları yazılır — padding
   konumlarına asla yazılmaz.
6. **`contiguous_true_runs(mask_1d)` paylaşılan bir yardımcıya
   taşındı** (`processing/common.py`) — hem dewow hem Sprint 3 band-pass
   (bkz. [[ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]]) bu AYNI
   fonksiyonu kullanır; bir kayan-pencere/filtre işleminin padding
   boşluğunu asla aşmaması için TEK bir doğrulanmış uygulama vardır.
7. **`method="running_mean"` bu sprintin karşılaştırma amaçlı bir adayıdır
   (D1-D4), `method="running_median"` gürbüz (robust) bir QC alternatifi
   olarak sunulur — hiçbiri canonical olarak seçilmez.** İkisi arasındaki
   fark tek bir örnekte %100000 (bir outlier) genlikli sentetik testte
   somut olarak gösterildi: `running_mean` taban çizgisi outlier'dan
   >1000 birim etkilenirken, `running_median` taban çizgisi tam olarak
   0.0 kaldı (bkz. `tests/test_dewow.py::
   test_running_mean_and_running_median_differ_on_outlier_trace`).
   `running_median` kullanıldığında, doğrusal olmadığına dair bir uyarı
   her zaman üretilir.
8. **float64 hesaplama → float32 çıktı.** Kayan pencere ortalaması/medyanı
   float64 hassasiyetinde hesaplanır (biriken yuvarlama hatasını
   önlemek için), sonuç girdinin orijinal dtype'ına (float32) geri
   dönüştürülür.
9. **ISSUE-009 (mean vs median DC offset) metriği her dewow adayı için
   ayrıca izlenir, ama hiçbir zaman yeniden zincirlenmez.** Her aday için,
   `[20,100)` ns penceresinde kanal-bazlı mean/median ofset anlık görüntüsü
   (`_dc_metric_snapshot`), atılan (uygulanmayan) bir `correct_dc_offset()`
   çağrısıyla hesaplanır — bu, dewow'un DC ofset üzerindeki YAN etkisini
   ölçen saf bir QC metriğidir, dewow çıktısına asla otomatik olarak
   yeniden uygulanmaz.

## Alternatives Considered
- **Kenar için sıfır-doldurma kullanmak:** Reddedildi — segment kenarında
  yapay bir süreksizlik yaratır, kayan pencerenin kenara yakın örneklerdeki
  tahminini bozar.
- **Padding boşluğu genelinde tek bir global kayan pencere uygulamak (segment
  ayrımı yapmadan):** Reddedildi — bir segmentin taban çizgisi tahminini
  komşu segmentin (veya padding'in) tamamen farklı genlik ölçeğiyle
  kirletirdi; bu tam olarak ADR-003'ün çözdüğü DC offset padding-kirlenmesi
  hatasının (ISSUE-007) aynı sınıfından bir risktir.
- **"En iyi" pencereyi otomatik olarak bir enerji kriterine göre seçmek:**
  Reddedildi — proje kapsamı ve `CLAUDE.md`, herhangi bir işleme
  parametresinin otomatik seçimini kesinlikle yasaklıyor. D1-D4 yalnızca
  karşılaştırma adaylarıdır; nihai seçim insan/jeofizikçi incelemesi
  gerektirir (bkz. [[02_SPRINTS/Sprint_03_Dewow_Bandpass]]).

## Consequences
- Gelecekteki her kayan-pencereli/segment-duyarlı işlem (örn. gelecekte
  eklenebilecek başka bir zaman-domeni filtresi), `contiguous_true_runs()`
  ve aynı "padding'i asla oku/yazma" desenini benimsemelidir.
- `edge_mode` seçenekleri (`reflect`/`nearest`) artık projenin standart
  kenar-politikası kelime dağarcığıdır — Sprint 3 band-pass'in Ormsby
  yöntemi de kavramsal olarak benzer bir reflect-pad kullanır (bkz.
  ADR-006).
- D1-D4 adaylarının hiçbiri canonical değildir; `outputs/sprint03/dewow_
  candidates/` yalnızca karşılaştırma girdileridir.

## Validation
- 20 sentetik test (`tests/test_dewow.py`): sabit iz tam sıfıra iniyor,
  yüksek frekanslı sinyal korunurken düşük frekanslı sürüklenme
  kaldırılıyor (periyodu tam pencere uzunluğuna eşit bir sinüs için ayrık
  toplam özdeşliğiyle KANITLANDI), pulse konumu korunuyor, girdi=çıktı+
  çıkarılan, padding hesaplamadan hariç/değişmeden, valid_mask bağımsız
  kopya olarak dönüyor, mean/median outlier'da farklılaşıyor, çift
  pencere tek sayıya yuvarlanıyor+uyarı, tek sayı pencere değişmeden
  kullanılıyor+uyarı yok, geçersiz method/edge_mode hatası, minimum
  pencere hatası, segmentten geniş pencere hatası, NaN girdi hatası,
  processing_history kaydı, tekrar-işleme guard'ı + `allow_repeat_
  processing` override'ı, NPZ round-trip.
- Gerçek dosya entegrasyonu (`tests/test_sprint3_real_integration.py`):
  gerçek `Swath003_Array02.ogpr` üzerinde dewow, düşük-frekans enerji
  oranını azalttı (spektrum tamamen çökmedi) ve padding her zaman tam
  `0.0` kaldı.
- Gerçek aday karşılaştırması (`outputs/sprint03/dewow_candidates/`): D1-D4
  hepsi çalıştırıldı, `dewow_candidate_metrics.csv`'de uygulanan
  pencere/yöntem/enerji-oranı/mean-vs-median metrikleri kaydedildi — hiçbir
  aday canonical işaretlenmedi.

## Related Files
- `src/archaeogpr/processing/dewow.py`
- `src/archaeogpr/processing/common.py` (`contiguous_true_runs`)
- `src/archaeogpr/qc/dewow.py`
- `configs/dewow_candidates.yaml`
- `src/archaeogpr/sprint3_candidates.py`
- [[ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]]
- [[ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]]
- [[05_PROCESSING/Dewow]]
- [[02_SPRINTS/Sprint_03_Dewow_Bandpass]]
