---
type: validation-report
tags: [validation, risk]
---

# Known Uncertainties

Bu dosya, kodun kendisinin bir hatası olmayan ama sonuçların
yorumlanmasını etkileyebilecek bilinen belirsizlikleri toplar. Ayrıca
bkz. [[01_PROJECT_STATE/04_Risks_and_Limitations]] (proje-seviyesi riskler)
ve [[01_PROJECT_STATE/03_Open_Issues]] (aksiyon takibi).

## CRS belirsizliği
`Swath003_Array02.ogpr` header'ı EPSG:32632 belirtiyor; bu, coğrafi olarak
projenin bilinen saha bağlamıyla (Marmara Ereğlisi, Türkiye) uyuşmuyor
olabilir. Kod bu değeri doğrulanmış kabul etmez. Bkz.
[[04_DATASETS/Swath003_Array02]].

## Velocity belirsizliği
Derinlik/elevation tahminleri (`max_depth_m ≈ 6.4`, `depth_per_sample_m ≈
0.00625`) header'daki `propagationVelocity_mPerSec` (0.1 m/ns) metadata
değerine dayanır. Bu değerin sahadaki gerçek dielektrik/hız koşullarını
yansıttığına dair bağımsız bir doğrulama yoktur.

## Processing geçmişi belirsizliği
Header'daki `dataBlockDescriptors[0].metadata.processing` alanı `null`.
Verinin ekipman tarafında herhangi bir ön işlemden geçip geçmediği bilgisi
mevcut değil. `dataset.processing_history` bu proje tarafında da boş
(Sprint 1 hiçbir işleme uygulamıyor), ama bu "verinin kesinlikle ham
olduğu" anlamına gelmez — sadece "bu projenin hiçbir işleme uygulamadığı"
anlamına gelir.

## Time-zero referansının fiziksel olarak doğrulanmamış olması
Sprint 2'de `correct_time_zero()` uygulandı, ancak bu bir **sinyal işleme
referansı** seçer — sample 0'ın (veya `target_sample`'ın) gerçek yer
yüzeyine mi yoksa antenin içindeki bir referans noktasına mı karşılık
geldiği hâlâ SAHA KALİBRASYONU olmadan kesinleşmiyor. Her sonuçta bu açıkça
belirtilir (`TIME_ZERO_REFERENCE_WARNING`). Derinlik hesapları (Sprint 1'in
`depth_top_m = 0` noktasından başlayan tahminleri) bu belirsizliği miras
alıyor — Sprint 2 bunu ÇÖZMEDİ, yalnızca sinyal işleme seviyesinde bir
hizalama sağladı. Bkz. [[05_PROCESSING/Time_Zero_Correction]],
[[06_DECISIONS/ADR_002_TimeZero_Reference_and_Shift_Policy]].

## Varsayılan max_shift_samples'ın gerçek veriye uygunluğu (Sprint 2.1'de kısmen çözüldü)
Gerçek dosyada varsayılan `max_shift_samples=64` ile `target_sample=0`
kombinasyonu 9/11 kanalı kırpıyordu (bkz.
[[01_PROJECT_STATE/03_Open_Issues]] eski ISSUE-005/yeni ISSUE-006). Sprint
2.1'de `overflow_policy="error"` varsayılanı ile bu artık SESSİZCE
olmuyor — aşan bir shift veriye dokunulmadan hata verir. Ancak bu, hâlâ
KODUN belirleyemeyeceği bir soruyu çözmüyor: saha verisi için doğru
`max_shift_samples`/`target_sample` kombinasyonu jeofizik ekibiyle
doğrulanmamıştır (bkz. aşağıdaki yeni madde).

## target_sample seçimi (0 vs 16) — mühendislik önerisi verildi, fiziksel soru kapanmadı (Sprint 2.1'de eklendi, Sprint 2.2'de güncellendi)
`target_sample=0`, her kanalın picked_sample'ından önceki tüm örnekleri
(61–74 örnek, kanala göre) geri dönüşü olmayan biçimde atıyor.
`target_sample=16` bu kaybı 16 örnek azaltıyor (45–58 örnek atılıyor) ama
ortadan kaldırmıyor. Sprint 2.2'de `target_sample=16`, bu ölçülen trade-
off'a ve target-invariance doğrulamasına dayanarak mühendislik önerisi
olarak kaydedildi (bkz. [[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]])
ve canonical çıktı bu değerle üretildi
(`outputs/sprint02/canonical_target16/`). **Bu, otomatik pick'i fiziksel
olarak doğrulamaz** — pick'in kendisi hâlâ fiziksel olarak doğrulanmamış
olduğundan (bkz. yukarıdaki "Time-zero referansının fiziksel olarak
doğrulanmamış olması"), `target_sample=16`'nın "gerçek yer yüzeyine" karşılık
geldiği iddia edilemez; bu yalnızca hangi sample'ın işleme referansı olarak
kullanılacağına dair bir mühendislik kararıdır. Karşılaştırmalı veri:
`outputs/sprint02_review/REVIEW_REQUIRED.md`,
`outputs/sprint02_review/comparison/discarded_leading_samples.csv`,
`outputs/sprint02/canonical_target16/CANONICAL_PROCESSING_NOTE.md`. Bkz.
[[01_PROJECT_STATE/03_Open_Issues]] ISSUE-008.

## Whole-trace DC offset'in target_sample'a bağımlı olması (Sprint 2.2'de bulundu ve düzeltildi)
Sprint 2.1'in tüm-valid-trace ortalamasına dayanan DC offset yaklaşımı,
gerçek veride `target_sample=0` ile ≈-398.5, `target_sample=16` ile ≈81.7
sonuç veriyordu — aynı kanallar, aynı pick'ler. Bu, whole-trace
ortalamasının fiziksel olarak sabit bir referans OLMADIĞINI, `target_
sample`'ın ne kadar erken pulse örneğini "valid" bıraktığına bağlı
olduğunu gösterdi. Düzeltme: `correct_time_zero()` artık time-zero-
relative bir `time_ns` üretiyor, `correct_dc_offset()` bu eksene göre
sabit bir `[20,100)` ns penceresi kullanabiliyor
(`window_reference="dataset_time"`) — gerçek veride, bu pencerenin
`target_sample`'dan bağımsız olarak AYNI ham örnekleri seçtiği (fark=0.0)
doğrulandı. Bkz. [[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]].

## Mean vs median DC offset'in gerçek veride bazı kanallarda işaret değiştirmesi (Sprint 2.2, açık belirsizlik)
Canonical `[20,100)` ns penceresinde `method="mean"` ve `method="median"`,
bazı kanallarda (örn. kanal 2, 4, 8) İŞARET bile değiştirecek kadar farklı
sonuç veriyor (`max_abs_difference≈226.4`). Bu, pencerenin genlik
dağılımının en azından bazı kanallarda basit/simetrik olmadığını gösterir.
Canonical politika (`mean`) bu veri üzerinde `median`'a karşı kanıtlanmış
olarak üstün değildir — belgelenmiş bir politika seçimidir, jeofizik
ekibiyle doğrulanmamıştır. Bkz.
`outputs/sprint02_2_validation/dc_window/dc_window_summary.json`,
[[01_PROJECT_STATE/03_Open_Issues]] ISSUE-009.

## DC offset penceresinin doğru seçimi (Sprint 2.2'de kısmen netleşti)
`method="mean"` ve pencere verilmediğinde güçlü doğrudan dalga tahmini
etkileyebilir (kod bunu uyarır). Sprint 2.2'de canonical bir başlangıç
penceresi (`[20,100)` ns, time-zero-relative) belirlendi ve gerçek veride
target-invariant olduğu doğrulandı — ama bu pencerenin GENİŞLİĞİ/
KONUMUNUN bu saha verisi için (veya başka veri setleri/ekipman ayarları
için) fiziksel olarak en uygun seçim olduğu jeofizik ekibiyle
doğrulanmamıştır; bu açıkça bir "başlangıç politikası" olarak
belgelenmiştir (bkz. [[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]]
madde 7). Sprint 2 hem `mean` hem `median` seçeneğini sunar ama hangisinin
"doğru" olduğuna karar vermez (bkz. yukarıdaki mean-vs-median maddesi).

## Gerçek arkeolojik anomali yorumlarının henüz yapılmamış olması
Bu proje şu ana kadar hiçbir anomali tespiti veya arkeolojik yorumlama
yapmadı ve yapmamalıdır (bkz. `CLAUDE.md`). B-scan'lerdeki yüzeye yakın
yüksek genlikli bant, doğrudan dalga/ringing olarak yorumlanmıştır (genel
GPR bilgisiyle tutarlı) ama bu bir arkeolojik yorum değildir — sinyal
işleme aşamasına (gain, background removal, migration) kadar hiçbir
görsel örnek arkeolojik bir hedef olarak etiketlenmemelidir.

## Sample Geolocations kaydının reverse-engineer edilmiş olması
Kayıt düzeni (bkz. [[03_ARCHITECTURE/OpenGPR_File_Structure]]) header'da
belgelenmediği için tek bir gerçek dosya üzerinde doğrulanarak çıkarıldı.
Farklı bir OpenGPR dosyasında bu düzen farklı olabilir; parser byte-size
uyuşmazlığında açık hata verir (sessizce yanlış okumaz), ama bu düzenin
"genel OpenGPR standardı" olduğu iddia edilemez — yalnızca bu örnekte
doğrulanmış bir düzendir.

## Dewow penceresi ve band-pass aralığı seçimi (Sprint 3, açık — kod hatası değil)
Sprint 3, dört dewow adayı (D1-D4) ve dört band-pass adayı (B1-B4, D2
tabanında) üretti ve karşılaştırdı; kodun kendisi hiçbirini diğerine karşı
"doğru" olarak seçmedi. Kısa dewow penceresi gerçek sinyali de kaldırma,
uzun pencere yetersiz giderme riski taşır; dar band-pass gerçek enerjiyi
reddetme, geniş band-pass gürültü tutma riski taşır — bunlar ölçülmüş
trade-off'lardır (bkz. `outputs/sprint03/dewow_candidates/comparison/
dewow_candidate_metrics.csv`,
`outputs/sprint03/bandpass_candidates/comparison/
bandpass_candidate_metrics.csv`) ama hangisinin bu saha verisi için en
uygun olduğu jeofizik incelemesi gerektirir. Header'ın 600 MHz nominal
frekansı TEK BAŞINA bir band-pass aralığı seçim kriteri değildir —
bağımsız yeniden ölçülmedi (bkz.
`outputs/sprint03/spectrum/SPECTRUM_INTERPRETATION_NOTES.md`). Bkz.
[[01_PROJECT_STATE/03_Open_Issues]] ISSUE-010, ISSUE-011,
[[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]],
[[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]].

## Dewow'un ISSUE-009 (mean vs median DC offset) üzerindeki etkisi (Sprint 3, açık)
Her dewow adayı için, canonical `[20,100)` ns penceresindeki mean/median
DC-ofset metriği ayrıca izlendi (dewow çıktısına yeniden zincirlenmeden,
saf QC amaçlı). Bu, dewow'un ISSUE-009'daki mean-vs-median
uyuşmazlığını ne ölçüde etkilediğini gösterir ama uyuşmazlığın kendisini
ÇÖZMEZ — bu hâlâ açık bir bilimsel belirsizliktir. Bkz.
[[01_PROJECT_STATE/03_Open_Issues]] ISSUE-009,
`outputs/sprint03/dewow_candidates/comparison/
mean_vs_median_dc_metric_comparison.png`.

## Geç-zaman penceresinde medyan-iz gecikmesinin spektral farklılıktan etkilenmesi (Sprint 3.1, metodolojik bulgu — hata değil)
B2'nin 20-100 ns (doğrudan dalga sonrası) penceresinde, D2 (önce) ile
D2+B2 (sonra) arasındaki ham medyan-iz çapraz-korelasyon gecikmesi 40
örnek çıktı — **bu gerçek bir faz kayması DEĞİLDİR**. B2'nin dar bandı
(120-800 MHz), dewow-only çıktının bu pencerede hâlâ taşıdığı düşük-
frekans içeriğin çoğunu kaldırıyor; "önce" ve "sonra" sinyalleri bu dar
pencerede önemli ölçüde farklı spektral karaktere sahip oluyor — çapraz-
korelasyonu çapalayacak güçlü, ortak bir olay kalmıyor (doğrudan dalga
penceresinin veya tüm geçerli segmentin aksine, ki ikisi de lag=0
gösteriyor). B1'in daha geniş bandı bu pencerede daha fazla ortak
düşük-frekans içerik bıraktığı için B1'in geç-zaman gecikmesi 0 kalıyor.
Yetkili sıfır-faz kanıtı hâlâ `correct_bandpass()`'in kendi tam-segment
tanılamasıdır (ADR-006, B1 ve B2 için lag=0). Bkz.
`outputs/sprint03_1/PHASE_METRICS_INTERPRETATION_NOTES.md`,
[[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]].

## D2 dewow ve B1 band-pass seçimi (Sprint 3.1 mühendislik önerisi, sprint canonicalization'da insan kararıyla kesinleşti — Sprint 3/3.1'de artık kapalı, ama önceki paragrafta belgelenen belirsizlikler açık kalıyor)
D2, 4/4 ölçülebilir koşulla (padding değişmemiş, faz kayması yok, removed
component koherent bir olay değil, 20-100ns tamamen bastırılmamış)
mühendislik önerisi olarak kaydedilmişti (`recommended_dewow_candidate =
D2`); B1 vs B2 arasında yalnızca bir mühendislik eğilimi
(preservation-favoring/B1) belgelenmişti. **2026-07-15'te kullanıcı bu iki
öneriyi insan/jeofizik kararı olarak onayladı: D2 confirmed, B1 selected**
— bkz. [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
`outputs/sprint03/canonical_D2_B1/`. Bu, kodun OTOMATİK bir seçimi
DEĞİLDİR — insan tarafından verilmiş, belgelenmiş bir karardır ve yalnızca
`Swath003_Array02.ogpr` için geçerlidir; başka bir veri seti kendi aday
karşılaştırmasını ve kendi insan/jeofizik incelemesini gerektirir. B1'in
800-900 MHz bandında koruduğu enerjinin kesin bir arkeolojik hedef
yorumu OLMADIĞI (yalnızca bir QC gözlemi) ADR-007'de açıkça belirtiliyor.
Bkz. `outputs/sprint03_1/{D2_DEWOW_DECISION.md,BANDPASS_FINAL_DECISION_REQUIRED.md}`.

## Background-removal adayı seçimi (Sprint 4A, kod hatası değil — insan kararıyla 2026-07-16'da kapatıldı)
Sprint 4A, 8 background-removal adayı (2 global + 6 sliding, canonical
Sprint 3 çıktısı üzerinde) üretti ve karşılaştırdı; kodun kendisi
hiçbirini diğerine karşı "doğru" olarak seçmedi. Bu, dewow/band-pass
seçiminden (ISSUE-010/011) daha da bilimsel açıdan risklidir — background
removal, gerçek uzun/yatay bir yansımayı ortak-mod gürültüden hiçbir
zaman ayırt edemez, bu yöntemin kendi doğasında var olan bir sınırlamadır
(bir aday seçilse bile bu sınırlama ortadan kalkmaz). Bu veri setinde
tüm 8 adayın removed component'i yüksek mekânsal koherans gösteriyor
(0.83-1.0, W5) ve paired-control uzun-hedef retention'ı tüm 8 adayda
0.3'ün çok altında (gerçek: 0.0000676-0.0172) — bu, hangi aday seçilirse
seçilsin gerçek bir riskin var olduğunu gösteren bir QC sinyalidir,
"gerçek bir hedef yok" anlamına gelmez. **2026-07-16'da kullanıcı bunu
insan/jeofizik nihai kararı olarak kapattı: canonical policy = A0**
(background removal uygulanmadı, preservation-first) — bkz.
[[01_PROJECT_STATE/03_Open_Issues]] ISSUE-012 (kapatıldı),
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]]. A1-A8
repository'de deneysel/opt-in araçlar olarak kalıyor; bu karar yalnızca
`Swath003_Array02.ogpr` için geçerlidir.

## Trace-spacing kaynağının veri setine göre değişebilmesi (Sprint 4A, mimari not — hata değil)
`compute_trace_spacing()`'in önceliği (geolocation → metadata
`sampling_step_m` → unavailable) tasarım gereği veri setine göre farklı
bir kaynak seçebilir. Bu gerçek dosyada: canonical Sprint 3 NPZ'si
geolocation dizileri taşımadığı için (bu projenin işlenmiş NPZ'leri şu an
geolocation kaydetmiyor), gerçek çalıştırma `metadata_sampling_step`
kaynağını kullandı (`trace_spacing_m=0.04008848472894169`) — bu, ham
`.ogpr` dosyasının kendi geolocation'ından ölçülen bir değer DEĞİL,
dosyanın `sampling.sampling_step_m` metadata alanından okunan bir
nominal survey-design değeridir. Bu ayrım `trace_spacing_and_window.json`
her aday için ayrı ayrı kaydedilir (`trace_spacing_source` alanı). Bkz.
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].

## İlgili notlar
[[01_PROJECT_STATE/04_Risks_and_Limitations]], [[01_PROJECT_STATE/03_Open_Issues]],
[[Parser_Validation]], [[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]],
[[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]],
[[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]],
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
[[02_SPRINTS/Sprint_02_2_TimeAxis_DCWindow_Validation]],
[[02_SPRINTS/Sprint_03_Dewow_Bandpass]],
[[02_SPRINTS/Sprint_03_1_Dewow_Bandpass_Decision_QC]],
[[02_SPRINTS/Sprint_04A_Background_Removal]]
