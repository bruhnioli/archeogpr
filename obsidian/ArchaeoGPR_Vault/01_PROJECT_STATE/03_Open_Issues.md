---
type: project-state
tags: [project-state, risk]
---

# Open Issues

Bu dosya kod hatası değil, karar/doğrulama bekleyen açık konuları takip eder.
Kod hataları için [[07_VALIDATION/Test_Results]] ve `pytest` çıktısına bakın
(şu anda bilinen bir test hatası yok).

## ISSUE-001 — EPSG:32632 CRS bilgisi gerçek saha konumuyla uyuşmuyor olabilir

- Status: Open
- Severity: High (coğrafi yorumlama için kritik, veri okuma için değil)
- Category: Spatial reference / CRS
- Detected in: Sprint 1, `Swath003_Array02.ogpr` header'ında `srs.value = 32632` okunurken
- Description: Header, `Sample Geolocations` bloğunda EPSG:32632 (UTM Zone 32N,
  yaklaşık 6°E–12°E, İtalya/Orta Avrupa) belirtiyor. Projenin bilinen saha
  bağlamı (Marmara Ereğlisi, Tekirdağ, Türkiye) yaklaşık 35N–37N UTM
  bölgesine denk gelir.
- Evidence: `dataset.metadata["spatial_reference"] == {"type": "EPSG", "value": 32632}`;
  ham x/y değerleri 614325–614332 / 4840257–4840262 aralığında (bkz.
  [[04_DATASETS/Swath003_Array02]]).
- Impact: Koordinatlar doğrudan haritada/GIS'te kullanılırsa yanlış konumda
  görünebilir. Kod bu bilgiyi doğru kabul etmiyor, sadece olduğu gibi
  raporluyor (bkz. [[01_PROJECT_STATE/04_Risks_and_Limitations]]).
- Proposed next action: Saha ekibi/jeofizik ile gerçek CRS'i doğrulamak;
  gerekirse doğru EPSG kodunu ayrı bir "doğrulanmış override" metadata alanı
  olarak eklemek (otomatik reprojection YAPMADAN).
- Owner: TBD (saha/jeofizik ekibi + proje sahibi)

## ISSUE-002 — Sample Geolocations kaydının baştaki int64 alanının anlamı belirsiz

- Status: Open
- Severity: Low (okuma için engel değil, yalnızca bilgi eksikliği)
- Category: OpenGPR format / parser
- Detected in: Sprint 1, binary format reverse-engineering
- Description: Her slice kaydının başında 8 byte'lık bir little-endian int64
  alan var; gerçek dosyada tam olarak `0..174` sırasıyla eşleşiyor ama
  header'da bu alanın adı/anlamı belgelenmiyor.
- Evidence: `struct.unpack('<q', ...)` ile doğrulandı — bkz.
  [[03_ARCHITECTURE/OpenGPR_File_Structure]], [[07_VALIDATION/Parser_Validation]].
- Impact: Düşük — parser bu alanı yalnızca bir bütünlük/sıra kontrolü için
  kullanıyor (uyuşmazsa uyarı üretir, hata vermez), veri modelinde
  kullanılmıyor.
- Proposed next action: OpenGPR resmi format dokümantasyonu bulunursa
  (bkz. [[09_REFERENCES/External_Resources]]) bu alanın adını doğrulamak.
- Owner: TBD

## ISSUE-003 — Radar Volume endianness header'da açıkça belirtilmiyor

- Status: Open (kabul edilmiş varsayımla birlikte)
- Severity: Low
- Category: OpenGPR format / parser
- Detected in: Sprint 1, header alan analizi
- Description: `dataBlockDescriptors[0].valueType == "float"` ama byte-order
  alanı yok. Reader little-endian (`<f4`) varsayıyor; bu varsayım kodda
  belgelenmiş ve gerçek dosyayla tutarlı, ama header'ın kendisi bunu teyit
  etmiyor.
- Evidence: `src/archaeogpr/io/ogpr_reader.py::_resolve_dtype` — açık
  `byteOrder`/`endianness` alanı varsa onu kullanır, yoksa little-endian'a
  düşer.
- Impact: Büyük-endian üreten bir OpenGPR varyantı olursa (şu ana kadar
  görülmedi) veri sessizce yanlış okunabilir. Reader'ın kontrollü fallback
  mekanizması bu riski azaltıyor ama sıfırlamıyor.
- Proposed next action: OpenGPR spesifikasyonu bulunursa endianness
  garantisini doğrulamak.
- Owner: TBD

## ISSUE-004 — Derinlik/elevation figürleri tamamen doğrulanmamış hız varsayımına bağlı

- Status: Open
- Severity: Medium
- Category: Geophysics / metadata
- Detected in: Sprint 1, `qc/metadata.py::derive_metadata`
- Description: `max_depth_m` ve `depth_per_sample_m`, header'daki
  `propagationVelocity_mPerSec` (0.1 m/ns) değerine dayanıyor. Bu değer
  sahada ölçülmüş bir hız değil, ekipman/metadata varsayımı.
- Evidence: `derived["depth_estimate"]["basis"]` alanı bunu açıkça belirtir;
  bkz. [[04_DATASETS/Swath003_Array02]].
- Impact: Gerçek derinlik saha koşullarına (toprak nemi, litoloji) göre
  farklı olabilir.
- Proposed next action: Sprint'te (Velocity Analysis, bkz.
  [[05_PROCESSING/Velocity_Analysis]]) hiperbol analizi veya bilinen bir
  hedefle hız kalibrasyonu yapılana kadar bu değerler yalnızca yaklaşık
  kabul edilmeli.
- Owner: TBD (jeofizik ekibi)

## ISSUE-005 — Varsayılan max_shift_samples, gerçek dosyada çoğu kanalı kırpıyor

- Status: **Superseded by ISSUE-006** (2026-07-15) — orijinal bulgu doğruydu
  ama "kabul edilmiş davranış" değerlendirmesi Sprint 2.1'de değişti: bu
  artık kabul edilebilir bir varsayılan olarak görülmüyor, güvenli bir
  politika değişikliğiyle (bkz. ISSUE-006) düzeltildi.
- Severity: Medium (varsayılan parametrelerle çalıştırıldığında sonucu etkiler)
- Category: Time-zero correction / parameter tuning
- Detected in: Sprint 2, gerçek dosyada `time-zero` CLI komutu varsayılan
  parametrelerle (`--target-sample 0`, `max_shift_samples=64`) çalıştırılırken
- Description: `channel_median_peak` yöntemi gerçek dosyada pick'leri örnek
  61–74 aralığında buluyor (arama penceresi 5–15 ns = örnek [40,120), doğru).
  `target_sample=0` ile gerekli shift -61 ile -74 arasında değişiyor;
  varsayılan `max_shift_samples=64`, 9/11 kanalda bu değeri aşıyor ve
  kırpma devreye giriyor.
- Evidence: `outputs/sprint02/time_zero/channel_picks.csv` — 9 satırda
  "clipped" uyarısı; tam tablo [[04_DATASETS/Swath003_Array02]].
- Impact: Kırpılan kanallar `target_sample=0`'a tam hizalanmaz (yaklaşık
  0–10 aralığında kalır). Sprint 2'de bu "güvenlik mekanizmasının doğru
  çalıştığının kanıtı" olarak değerlendirildi (sessiz uygulama yok, açık
  uyarı var); Sprint 2.1'de bu değerlendirme yeniden ele alındı — bir metin
  uyarısı, kırpılmış bir sonucun normal bir "başarı" gibi kaydedilmesini
  engellemek için yeterli değil. Bkz. ISSUE-006.
- Proposed next action: Bkz. ISSUE-006 (çözüldü) ve ISSUE-008 (açık —
  hangi `target_sample`'ın kullanılacağı).
- Owner: TBD (jeofizik ekibi + proje sahibi)

## ISSUE-006 — 9/11 channel shift clipping in initial Sprint 2 default run

- Status: **Resolved** (2026-07-15, Sprint 2.1)
- Severity: Medium (varsayılan parametrelerle çalıştırıldığında sonucu
  etkiliyordu)
- Category: Time-zero correction / overflow policy
- Detected in: Sprint 2.1'in kod denetimi, ISSUE-005'in gerçek veri
  bulgusunu yeniden değerlendirirken
- Description: ISSUE-005'teki bulgunun kendisi (9/11 kanal, varsayılan
  `max_shift_samples=64` + `target_sample=0` ile kırpıldı) doğruydu, ama
  bu Sprint 2'de yalnızca bir metin uyarısıyla bildirilen, sonucu
  "normal başarı" gibi görünen bir davranıştı — makine-okunabilir hiçbir
  ayrım yoktu.
- Evidence: `outputs/sprint02/combined/sprint02_summary.json` içinde 9
  "clipped" uyarısı (bkz. `outputs/sprint02/combined/
  SUPERSEDED_PENDING_REVIEW.md`).
- Impact: Otomatize edilmiş bir pipeline, kırpılmış (yanlış hizalanmış) bir
  sonucu fark etmeden kullanabilirdi.
- Resolution: `overflow_policy: Literal["error","clip"]` eklendi,
  varsayılan `"error"` (veriye dokunmadan hata). `"clip"` yalnızca açık
  opt-in; sonuç `has_clipped_shifts=True`,
  `valid_for_downstream_processing=False` ile işaretlenir. Gerçek veride
  `max_shift_samples=96` ile doğrulandı: sıfır kırpma, 11/11 kanalda
  `applied_shift == requested_shift`. Bkz.
  [[06_DECISIONS/ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]].
- Owner: Resolved by Sprint 2.1.

## ISSUE-007 — Padding contamination risk in DC offset

- Status: **Resolved** (2026-07-15, Sprint 2.1)
- Severity: High (sessizce yanlış genlik değerleri üretiyordu)
- Category: DC offset correction / time-zero integration
- Detected in: Sprint 2.1'in kod denetimi — "mevcut sonuçların doğru
  olduğunu varsayma" talimatıyla, sentetik bir reprodüksiyonla doğrulandı
- Description: Sprint 2'nin `correct_dc_offset()`'i, time-zero'nun
  ürettiği padding bölgesinden (bkz. `padding_mask()`) habersizdi. Padding
  örnekleri, ofset hesaplamasına ve çıkarma işlemine gerçek veri gibi
  dahil ediliyordu.
- Evidence: Sentetik pulse+bias reprodüksiyonu: time-zero çıkışında
  padding `[0, 0, 0, ...]` (doğru, `fill_value=0.0`), eski DC offset'ten
  SONRA `[-8, -8, -8, ...]` (kirlenmiş, fabrikasyon bir "ofset bandı").
- Impact: Birleşik pipeline (`sprint2` komutu) çıktısında padding bölgesi
  gerçek olmayan, sabit bir genlik değeri taşıyordu — bu bölge gelecekte
  bir filtreye (örn. Sprint 3 band-pass) girdi olarak kullanılsaydı, kenar
  etkisi (edge effect) fabrikasyon bir sinyal üzerinden yayılabilirdi.
- Resolution: `ProcessingResult.valid_mask` eklendi (time-zero'dan);
  `correct_dc_offset(..., valid_mask=...)` ofset hesaplamasını VE
  çıkarmayı `window ∩ valid_mask` ile sınırlıyor; padding girdiden hiç
  okunmuyor/yazılmıyor. Gerçek veride doğrulandı: her iki `target_sample`
  adayında, 11 kanalın hepsinde DC offset'ten sonra padding tam olarak
  `[0.0]`. Bkz.
  [[06_DECISIONS/ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset]].
- Owner: Resolved by Sprint 2.1.

## ISSUE-008 — Peak-to-sample-zero leading-wavelet truncation risk

- Status: **Resolved as an engineering recommendation** (2026-07-15, Sprint
  2.2) — `target_sample=16` mühendislik önerisi olarak kaydedildi ve
  target-invariance ile doğrulandı (bkz.
  [[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]]). **Bu,
  fiziksel bir kalibrasyon iddiası DEĞİLDİR** — otomatik pick'in fiziksel
  anlamına ilişkin standing epistemik sınır (bkz.
  [[07_VALIDATION/Known_Uncertainties]]) değişmeden geçerlidir; bu madde
  yalnızca HANGİ örneğin işlenmek üzere kullanılacağına dair mühendislik
  kararının artık verildiğini belirtir. Aşağıdaki orijinal analiz (Sprint
  2.1'den, değiştirilmedi) hâlâ geçerli bir arka plan bilgisidir.
- Severity: Medium (arşivlenmiş veri kalitesini etkiler, kod hatası değil)
- Category: Time-zero correction / target_sample selection
- Detected in: Sprint 2.1, target_sample=0 vs 16 karşılaştırması
- Description: `target_sample=0`, her kanalın picked_sample'ından ÖNCEKİ
  tüm örnekleri (61–74 örnek, kanala göre) geri dönüşü olmayan biçimde
  atıyor — bu, doğrudan dalganın/direct-wave'in erken/zayıf kısmını
  (varsa) içerebilir. `target_sample=16`, bu kaybı 16 örnek azaltıyor
  (45–58 örnek atılıyor) ama ortadan kaldırmıyor.
- Evidence: `outputs/sprint02_review/comparison/discarded_leading_samples.csv`,
  `outputs/sprint02_review/REVIEW_REQUIRED.md`.
- Impact: Hangi `target_sample`'ın "doğru" olduğu, otomatik pick'in
  fiziksel olarak doğrulanmamış olması nedeniyle (bkz.
  [[07_VALIDATION/Known_Uncertainties]]) kod tarafından belirlenemez.
- Proposed next action: **Human geophysical QC of target_sample 0 vs 16
  candidates** — bkz. `outputs/sprint02_review/REVIEW_REQUIRED.md`. Bu
  proje bu seçimi OTOMATİK yapmaz.
- Resolution (2026-07-15, Sprint 2.2): `target_sample=16`, yukarıdaki
  ölçülen trade-off'a dayanarak (daha az öndeki veri kaybı, array
  sınırından uzak pick, target-invariance ile doğrulanmış DC offset)
  mühendislik önerisi olarak kaydedildi ve canonical çıktı üretildi
  (`outputs/sprint02/canonical_target16/`). Bkz.
  [[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]] madde 6.
  Bu bir OTOMATİK seçim değildir (kod tarafından bir kriter optimize
  edilerek seçilmedi) — açıkça belgelenmiş, insan tarafından gözden
  geçirilebilir bir mühendislik kararıdır ve otomatik pick'in fiziksel
  anlamını değiştirmez.
- Owner: Resolved by Sprint 2.2 (engineering recommendation); fiziksel
  kalibrasyon sorusu kalıcı olarak açık kalır (bkz.
  [[07_VALIDATION/Known_Uncertainties]]).

## ISSUE-009 — Mean vs median DC offset disagree substantially per channel

- Status: Open (bilimsel belirsizlik — kod hatası değil)
- Severity: Medium (canonical DC offset değerinin yorumlanmasını etkiler)
- Category: DC offset correction / method selection
- Detected in: Sprint 2.2, canonical `[20,100)` ns penceresinde `mean` ve
  `median` sonuçlarının QC amaçlı karşılaştırılması
- Description: Aynı `[20,100)` ns penceresinde, `method="mean"` ve
  `method="median"` gerçek dosyada bazı kanallarda İŞARET bile değiştirecek
  kadar farklı sonuç veriyor (örn. kanal 2: mean +129.9, median -35.8;
  kanal 8: mean +165.9, median -60.5). `max_abs_mean_vs_median_difference
  ≈ 226.4`.
- Evidence: `outputs/sprint02_2_validation/dc_window/dc_window_summary.json`,
  `mean_vs_median_offsets.png`.
- Impact: Pencerenin genlik dağılımı en azından bazı kanallarda basit/
  simetrik değil — canonical politika (`mean`) bu veri üzerinde `median`'a
  karşı KANITLANMIŞ olarak üstün değildir, yalnızca belgelenmiş bir
  politika seçimidir (bkz. ADR-004 madde 5).
- Proposed next action: Jeofizik ekibiyle hangi location istatistiğinin
  (`mean`/`median`) bu veri seti için daha uygun olduğunu değerlendirmek;
  gerekirse pencere genişliğinin/konumunun de gözden geçirilmesi.
- Owner: TBD (jeofizik ekibi)
- Owner: TBD (jeofizik ekibi + proje sahibi)

## ISSUE-010 — Dewow penceresi (D1-D4 arasından) henüz seçilmedi

- Status: **Resolved** (2026-07-15, Sprint 3 canonicalization) — kullanıcı
  D2'yi (`running_mean`, 8.125 ns uygulanan/65 örnek, `edge_mode=reflect`)
  insan/jeofizik kararı olarak seçti. Bkz.
  [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
  `outputs/sprint03/canonical_D2_B1/`. Bu seçim yalnızca
  `Swath003_Array02.ogpr` için geçerlidir; başka bir veri seti kendi aday
  karşılaştırmasını gerektirir.
- Severity: Medium (nihai işlenmiş veri kalitesini etkiler)
- Category: Dewow / parameter selection
- Detected in: Sprint 3, dewow aday karşılaştırması
- Description: Dört dewow adayı (D1: running_mean 4ns, D2: running_mean
  8ns, D3: running_mean 12ns, D4: running_median 8ns) canonical Sprint 2
  çıktısı üzerinde çalıştırıldı ve karşılaştırıldı. Kısa pencere (D1)
  gerçek yansıma sinyalini de kaldırma riski taşır; uzun pencere (D3)
  "wow"u yeterince gidermeme riski taşır; medyan (D4) doğrusal olmayan bir
  filtredir. Ölçülen düşük-frekans enerji oranları (sonra): D1=0.7440,
  D2=0.8785, D3=0.5587, D4=0.9392 — hiçbiri diğerine karşı "kanıtlanmış
  üstün" değildir.
- Evidence: `outputs/sprint03/dewow_candidates/comparison/
  dewow_candidate_metrics.csv`,
  `outputs/sprint03/dewow_candidates/comparison/DEWOW_REVIEW_REQUIRED.md`.
- Impact: Sprint 4'ün (henüz tanımlanmamış) hangi dewow çıktısı üzerinde
  çalışacağı bu seçime bağlıdır.
- Proposed next action (tarihsel, çözülmeden önce): Jeofizik ekibiyle
  `channel00_all_dewow_candidates.png`,
  `all_channel_medians_candidates.png` ve
  `mean_vs_median_dc_metric_comparison.png`'yi inceleyip bir aday seçmek.
  Bu proje bu seçimi otomatik yapmaz.
- Owner: Resolved by Sprint 3 canonicalization (2026-07-15) — kullanıcı
  kararı D2.

## ISSUE-011 — Band-pass aralığı (B1-B4 arasından) henüz seçilmedi

- Status: **Resolved** (2026-07-15, Sprint 3 canonicalization) — kullanıcı
  B1'i (Butterworth, 100-900 MHz, order=4, zero-phase) preservation-
  favoring mühendislik eğilimini takip ederek insan/jeofizik kararı
  olarak seçti. Bkz.
  [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]],
  `outputs/sprint03/canonical_D2_B1/`. 800-900 MHz'de korunan enerjinin
  kesin bir arkeolojik hedef yorumu OLMADIĞI ADR-007'de açıkça
  belirtiliyor. Bu seçim yalnızca `Swath003_Array02.ogpr` için geçerlidir.
- Severity: Medium (nihai işlenmiş veri kalitesini etkiler)
- Category: Band-pass filtering / parameter selection
- Detected in: Sprint 3, band-pass aday karşılaştırması
- Description: Dört band-pass adayı (B1: Butterworth 100-900MHz, B2:
  Butterworth 120-800MHz, B3: Ormsby 80/120/800/1000MHz, B4: Ormsby
  100/150/700/900MHz), ortak bir dewow tabanı (D2) üzerinde çalıştırıldı.
  Dar bant (B2/B4) gerçek sinyal enerjisini de reddetme riski taşır;
  geniş bant (B1/B3) daha fazla bant-dışı gürültü tutar; Butterworth ve
  Ormsby'nin geçiş-bandı şekli (yuvarlak omuz vs keskin doğrusal rampa)
  farklıdır. Header'ın 600 MHz nominal frekansı TEK BAŞINA bir aralık
  seçim kriteri değildir (bağımsız yeniden ölçülmedi).
- Evidence: `outputs/sprint03/bandpass_candidates/comparison/
  bandpass_candidate_metrics.csv`,
  `outputs/sprint03/bandpass_candidates/comparison/BANDPASS_REVIEW_REQUIRED.md`,
  `outputs/sprint03/spectrum/SPECTRUM_INTERPRETATION_NOTES.md`.
- Impact: Sprint 4'ün (henüz tanımlanmamış) hangi band-pass çıktısı
  üzerinde çalışacağı bu seçime bağlıdır. Ayrıca D2'nin ortak taban olarak
  kullanılmış olması D2'yi dewow için canonical yapmaz (bkz. ISSUE-010).
- Proposed next action (tarihsel, çözülmeden önce): Jeofizik ekibiyle
  `channel00_all_bandpass_candidates.png`,
  `spectra_all_candidates.png` ve
  `transfer_functions_all_candidates.png`'yi inceleyip bir aday seçmek.
  Bu proje bu seçimi otomatik yapmaz.
- Owner: Resolved by Sprint 3 canonicalization (2026-07-15) — kullanıcı
  kararı B1.

## ISSUE-012 — Background-removal adayı (A1-A8 arasından) henüz seçilmedi

- Status: Open (insan/jeofizik incelemesi bekleniyor — kod hatası değil)
- Severity: Medium (nihai işlenmiş veri kalitesini etkiler)
- Category: Background removal / parameter selection
- Detected in: Sprint 4A, background-removal aday karşılaştırması
- Description: 8 background-removal adayı (A1: global_mean, A2:
  global_median, A3-A5: sliding_mean 0.5/1.0/1.5 m, A6-A8: sliding_median
  aynı pencereler) canonical Sprint 3 çıktısı (D2+B1) üzerinde çalıştırıldı
  ve karşılaştırıldı. Global yöntemler (A1/A2) gerçek uzun/yatay bir
  yansımayı, tüm profil üzerinden hesaplanan bir background'a karışıp
  bastırma riskini maksimum taşır; sliding yöntemler pencereden daha
  geniş bir olayı kendi merkezinde neredeyse tamamen yok eder (sentetik
  olarak doğrulandı). Bu veri setinde tüm 8 adayın removed component'i
  yüksek mekânsal koherans gösteriyor (adjacent-trace correlation
  0.83-1.0, W5) — bu, YÖNTEMDEN BAĞIMSIZ olarak gerçek bir uzun yansımayı
  bastırma riskinin var olduğunu gösteren bir QC sinyalidir, "bu veri
  setinde gerçek bir hedef yok" anlamına gelmez.
- Evidence: `outputs/sprint04a/background_candidates/comparison/
  candidate_metrics.csv`,
  `outputs/sprint04a/BACKGROUND_FINAL_DECISION_REQUIRED.md`.
- Impact: Bir sonraki sprintin (Gain veya başka bir kapsam, henüz
  tanımlanmadı) hangi background-removal çıktısı üzerinde çalışacağı
  (veya hiç background-removal uygulanmamış bir girdi üzerinde
  çalışacağı) bu seçime bağlıdır.
- Proposed next action: Jeofizik ekibiyle
  `BACKGROUND_DECISION_PANEL.png`, `BACKGROUND_DECISION_PANEL_DETAIL.png`
  ve her adayın kendi removed-component B-scan'lerini inceleyip bir aday
  seçmek (veya hiçbirini seçmeyip başka bir yaklaşım istemek). Bu proje
  bu seçimi otomatik yapmaz.
- Owner: TBD (jeofizik ekibi + proje sahibi)
