---
type: project-state
tags: [project-state, risk]
---

# Risks and Limitations

Bu liste, projenin şu anki (Sprint 4A sonu, review_required) durumunda
bilinen risk ve sınırlamaları kaydeder. Kod bu risklerin hiçbirini sessizce
çözmez veya gizlemez — her biri metadata/uyarılarda veya belgelerde açıkça
yüzeye çıkarılır.

## 1. Header CRS bilgisinin gerçek saha konumuyla (Marmara Ereğlisi) uyuşmama ihtimali
`Swath003_Array02.ogpr` header'ı EPSG:32632 (UTM 32N, ~6–12°E) belirtiyor;
bilinen saha bağlamı Marmara Ereğlisi/Türkiye (~35–37N UTM) ile coğrafi
olarak uyuşmuyor. Kod bu bilgiyi doğru kabul etmez, yalnızca "as stored,
not validated" uyarısıyla birlikte raporlar. Bkz. [[01_PROJECT_STATE/03_Open_Issues]]
(ISSUE-001), [[04_DATASETS/Swath003_Array02]].

## 2. Metadata velocity değerinin gerçek saha hızını temsil etmeme ihtimali
Derinlik/elevation tahminleri `propagationVelocity_mPerSec` (0.1 m/ns)
metadata değerine dayanır; bu, ekipmanın varsayılan/ayarlı değeri olabilir,
sahada ölçülmüş gerçek bir hız olması gerekmez. Bkz. ISSUE-004 içinde
[[01_PROJECT_STATE/03_Open_Issues]], [[05_PROCESSING/Velocity_Analysis]].

## 3. Processing metadata'nın eksik olması
Header'daki `dataBlockDescriptors[0].metadata.processing` alanı bu gerçek
dosyada `null`. Bu, verinin hangi işlemlerden (varsa) geçtiğinin ekipman
tarafında da kayıtlı olmadığı anlamına gelir — dolayısıyla "ham" olduğu
varsayımı yalnızca bu boş alana dayanıyor, bağımsız doğrulanmadı.

## 4. OpenGPR varyantlarının farklı descriptor yapıları kullanabilmesi
Bu parser tek bir gerçek dosyaya (`Swath003_Array02.ogpr`, OpenGPR v2.0)
karşı doğrulandı. Aynı `type`/`name` alanlarını kullanan farklı dosyalarda
çalışması beklenir (offset/size/valueType her zaman descriptor'dan okunur),
ancak `Sample Geolocations` kaydının iç düzeni (bkz.
[[03_ARCHITECTURE/OpenGPR_File_Structure]]) header'da belgelenmediği için
reverse-engineered bir varsayımdır. Farklı bir düzen kullanan bir dosya,
byte-size uyuşmazlığı nedeniyle **açık bir hata ile reddedilir** — sessizce
yanlış okunmaz. Bkz. [[07_VALIDATION/Known_Uncertainties]].

## 5. Arkeolojik hedeflerin otomatik sınıflandırılmaması gerektiği
Bu proje hiçbir aşamada anomali tespiti veya arkeolojik nesne
sınıflandırması yapmaz/yapmamalıdır. B-scan ve geometry QC çıktıları
yalnızca veri kalitesi kontrolü amaçlıdır, yorumlama insan uzmana aittir.
Bkz. `CLAUDE.md`: "Do not automatically interpret anomalies as
archaeological objects."

## 6. Background ve F-K filtrelerinin gerçek hedefleri bastırabilmesi
**(Sprint 4A'da background removal implemente edildi — bu, projenin şu
ana kadarki en bilimsel açıdan riskli filtresidir.)** Background removal
(global veya sliding, mean veya median), bir kanalın trace ekseni
boyunca ortak/yavaş-değişen bir bileşeni çıkarır; düz/yatay gerçek
arkeolojik hedefler (bir taban, bir duvar temeli, bir katman sınırı) bu
bileşenden AYIRT EDİLEMEZ ve aynı etkinlikte bastırılabilir. Bu veri
setinde, tüm 8 background-removal adayının removed component'i yüksek
mekânsal koherans gösteriyor (0.83-1.0) — bu, yöntemden bağımsız olarak
gerçek bir riskin var olduğunu gösteren bir QC sinyalidir. **İnsan/
jeofizik nihai kararı (2026-07-16): canonical policy = A0 — background
removal canonical zincire dahil edilmedi, tam olarak bu risk yüzünden
(preservation-first politika).** A1-A8 repository'de deneysel/opt-in
araçlar olarak kalıyor. Bkz.
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]],
[[01_PROJECT_STATE/03_Open_Issues]] ISSUE-012 (kapatıldı).
F-K filtering (henüz uygulanmadı), dipli gürültüyü frekans-dalga sayısı
düzleminde temizler; dipli gerçek yansımalar da kaybedilebilir. Bu yüzden
F-K hiçbir zaman varsayılan olarak açık olmamalıdır. Bkz.
[[05_PROCESSING/Background_Removal]], [[05_PROCESSING/FK_Filter]].

## 7. AGC'nin nicel genlik analizinde kullanılamaması
(Henüz uygulanmadı.) AGC (Automatic Gain Control) her örneği yerel bir
pencereye göre normalize eder; görsel yorumlama için faydalı olsa da gerçek
genlik ilişkilerini bozar. AGC çıktısı hiçbir zaman nicel genlik
karşılaştırması için kullanılmamalıdır. Bkz. `CLAUDE.md`: "AGC products
must never be used for quantitative amplitude analysis.", [[05_PROCESSING/Gain]].

## 8. Otomatik time-zero pick'i doğrulanmış fiziksel yüzey zamanı değildir
(Sprint 2'de uygulandı.) `correct_time_zero()`'nun otomatik yöntemleri
(`channel_median_peak`, `channel_median_cross_correlation`) bir
sinyal-işleme referansı seçer — bu, saha kalibrasyonu olmadan "gerçek yer
yüzeyi" anlamına gelmez. Her sonuçta bu açıkça belirtilir:
*"Automatic time-zero picks are signal-processing references and are not
independently calibrated physical surface times."* Bkz.
[[06_DECISIONS/ADR_002_TimeZero_Reference_and_Shift_Policy]].

## 9. Kanal-bazlı sabit time-zero shift'i, kanal içi iz-bazlı farkları düzeltmez
(Sprint 2'de uygulandı, kasıtlı bir sınır.) Bir kanalın tüm slice'ları aynı
tam sayı örnek kaydırmasını alır; bu, donanımsal/anten gecikme farkını
düzeltir ama o kanal İÇİNDEKİ olası iz-bazlı gerçek zaman-sıfırı
farklılıklarını (varsa) düzeltmez. Trace-by-trace otomatik kaydırma bu
sprintte kasıtlı olarak uygulanmadı (gürültüye karşı dayanıksız olurdu).

## 10. Otomatik kırpma artık varsayılan değil; target_sample için mühendislik önerisi var ama fiziksel kalibrasyon sorusu kapanmadı
(Sprint 2.1'de politika değişti.) `overflow_policy` varsayılanı artık
`"error"` — bir shift `max_shift_samples`'ı aşarsa veriye dokunulmadan hata
verilir, sessizce kırpılmaz. HANGİ `target_sample`'ın kullanılacağı
sorusuna Sprint 2.2'de `target_sample=16` mühendislik önerisi olarak yanıt
verildi (ölçülebilir trade-off'lara dayanarak, bkz.
[[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]]) — ama bu,
otomatik pick'in fiziksel bir yüzey zamanı olduğu anlamına GELMEZ; bu
soru kalıcı olarak açık kalır. Bkz.
[[06_DECISIONS/ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]],
[[01_PROJECT_STATE/03_Open_Issues]] ISSUE-008.

## 11. DC offset'in padding'i kirletme riski (bulundu ve düzeltildi)
(Sprint 2.1'de bulundu ve düzeltildi.) Sprint 2'nin `correct_dc_offset()`'i
time-zero'nun ürettiği padding bölgesinden habersizdi; padding, ofset
hesaplamasına ve çıkarmaya gerçek veri gibi dahil edilip fabrikasyon bir
değere dönüşüyordu (somut reprodüksiyon: `[0,0,0,...]` → `[-8,-8,-8,...]`).
`ProcessingResult.valid_mask` ile düzeltildi ve gerçek veride doğrulandı
(padding, DC offset sonrası tam `[0.0]` kalıyor). Bkz.
[[06_DECISIONS/ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]],
[[01_PROJECT_STATE/03_Open_Issues]] ISSUE-007. Bu, gelecekteki tüm işleme
modüllerinin (dewow, gain, vb.) kendi girdisi bir `valid_mask` taşıyorsa
aynı deseni benimsemesi gerektiği anlamına gelir.

## 12. Whole-trace DC offset, target_sample'a bağımlı bir istatistik olduğu için canonical referans olarak kullanılamaz (bulundu ve düzeltildi)
(Sprint 2.2'de bulundu ve düzeltildi.) Sprint 2.1'in tüm-valid-trace
ortalamasına dayanan DC offset'i, gerçek veride `target_sample=0` ile
≈-398.5, `target_sample=16` ile ≈81.7 sonuç veriyordu — aynı kanallar, aynı
pick'ler. Kök neden: bu istatistik, `correct_time_zero()`'nun ürettiği
güçlü, asimetrik erken pulse'ın ne kadarının "valid" bölgede kaldığına
bağlıydı. Düzeltme: `time_ns` artık time-zero-relative üretiliyor ve DC
offset, bu eksene göre sabit bir `[20,100)` ns penceresi kullanıyor —
gerçek veride target-invariance TAM olarak (fark=0.0) doğrulandı. Bkz.
[[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]].

## 13. Mean vs median DC offset gerçek veride bazı kanallarda işaret değiştiriyor
(Sprint 2.2'de bulundu, açık bilimsel belirsizlik — hata değil.) Canonical
`[20,100)` ns penceresinde `mean` ve `median` bazı kanallarda ZIT işaretli
sonuç veriyor (`max_abs_difference≈226.4`). Canonical politika (`mean`)
bu veri üzerinde kanıtlanmış olarak üstün değildir, belgelenmiş bir
politika seçimidir. Bkz. [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-009,
[[07_VALIDATION/Known_Uncertainties]].

## 14. Dewow penceresi (D1-D4) ve band-pass aralığı (B1-B4) henüz seçilmedi
(Sprint 3'te üretildi, açık karar bekleyen konu — hata değil.) Dört dewow
adayı ve dört band-pass adayı (ortak bir dewow tabanı, D2, üzerinde)
gerçek veride çalıştırıldı ve karşılaştırıldı; hiçbiri diğerine karşı
kodun kendisi tarafından "daha doğru" olarak seçilmedi — kısa/uzun pencere
ve dar/geniş bant trade-off'ları ölçülmüş ama insan/jeofizik yargısı
gerektirir. Bkz. [[01_PROJECT_STATE/03_Open_Issues]] ISSUE-010, ISSUE-011.

## 15. Kayan-pencereli/filtreleme işlemlerinin padding boşluklarını asla aşmaması
(Sprint 3'te uygulandı.) Dewow ve band-pass, her ikisi de paylaşılan
`contiguous_true_runs()` yardımcısını kullanarak her ardışık geçerli
segmenti bağımsız işler — bir kayan pencere veya filtre asla bir padding
boşluğunu veya komşu bir segmenti okumaz/yazmaz. Bu, ADR-003'ün çözdüğü DC
offset padding-kirlenmesi hatasının (ISSUE-007) aynı sınıfından bir riski
Sprint 3'ün her iki yeni işlemi için de önler. Bkz.
[[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]],
[[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]].

## 16. Background-removal canonical politikası: A0 (uygulanmadı)
(Sprint 4A'da üretildi, Sprint 4A Closure'da karar verildi —
2026-07-16.) 8 background-removal adayı (2 global + 6 sliding, D2+B1
canonical zinciri üzerinde) gerçek veride çalıştırıldı ve karşılaştırıldı;
kodun kendisi hiçbirini diğerine karşı "doğru" olarak seçmedi. Global
yöntemler (A1/A2) en riskli olanlardır (tüm profil üzerinden hesaplanan
bir background); sliding yöntemler penceredan daha geniş bir olayı kendi
merkezinde neredeyse tamamen yok eder (sentetik olarak doğrulandı,
`window_length_vs_target_attenuation.png`). **İnsan/jeofizik nihai
kararı: canonical policy = A0** (background removal uygulanmadı) —
preservation-first politika, geri dönüşü olmayan bir işlemin gerçek uzun/
yatay bir arkeolojik olayı bastırma riskini kabul etmemek. Bkz.
[[01_PROJECT_STATE/03_Open_Issues]] ISSUE-012 (kapatıldı),
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
[[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]].

## İlgili notlar
[[01_PROJECT_STATE/03_Open_Issues]], [[07_VALIDATION/Known_Uncertainties]],
[[05_PROCESSING/Processing_Order]], [[06_DECISIONS/ADR_002_TimeZero_Reference_and_Shift_Policy]],
[[06_DECISIONS/ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]],
[[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]],
[[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]],
[[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]],
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]],
[[02_SPRINTS/Sprint_02_1_TimeZero_DCOffset_Review]],
[[02_SPRINTS/Sprint_02_2_TimeAxis_DCWindow_Validation]],
[[02_SPRINTS/Sprint_03_Dewow_Bandpass]], [[02_SPRINTS/Sprint_04A_Background_Removal]]
