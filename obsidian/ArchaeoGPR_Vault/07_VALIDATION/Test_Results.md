---
type: validation-report
tags: [validation]
---

# Test Results

Gerçek `pytest` terminal çıktıları, tarih sırasıyla (en yeni en üstte).
Başarısız testler gizlenmez — şu ana kadar başarısız test kaydı yoktur.

## 2026-07-15 (Sprint 4A — Background Removal Candidate Development & Geophysical QC)

Command:
```bash
pytest -q
```

Result:
```text
........................................................................ [ 22%]
........................................................................ [ 45%]
........................................................................ [ 68%]
........................................................................ [ 91%]
..........................                                               [100%]
314 passed in 151.64s (0:02:31)
```

254 önceki test hiç bozulmadı; 60 yeni Sprint 4A testi eklendi ve geçti:
`tests/test_background.py` (44: `remove_background()` core algoritma —
global_mean/global_median/sliding_mean/sliding_median her biri sabit
iz→tam sıfır, girdi=çıktı+çıkarılan, kanal-bazlı bağımsızlık; pencere/
geometri — metre→trace dönüşümü çift→tek yuvarlama+uyarı,
`window_traces`/`window_m` ikisi birden hatası, minimum/maksimum pencere
hataları, trace-spacing önceliği (geolocation→metadata→unavailable);
edge/mask — `reflect`/`nearest` sentetik kenar-olay testleri, padding
hariç/değişmeden, valid_mask bağımsız kopya; processing-history/export —
tekrar-işleme guard'ı+override, NPZ round-trip; synthetic bilimsel-risk
testleri — window-length vs target-length attenuation (kısa hedef
korunuyor, geniş hedef merkezde neredeyse tamamen yok oluyor — ilk
taslakta ters bir varsayım düzeltildi), global vs sliding uzun-olay
testi, mean vs median outlier testi), `tests/test_background_qc.py`
(11: sinyal-koruma metrikleri her zaman penceresini kapsıyor, RMS
retention dominant background çıkarıldığında <1.0, removed-component
metrikleri band-energy entegrasyonu dahil doğru yapıda, removed-component
coherence paylaşılan background için yüksek (>0.9), localized-event-risk
düz background'da düşük/eğri-lokal olayda yüksek, degenerate şekiller
finite değil, QC plotting suite tüm dosyaları üretiyor, hiçbir metrik
"canonical" anahtarı içermiyor), `tests/test_sprint4a_pipeline.py` (3:
sentetik uçtan-uca zincir time-zero→...→background removal, NPZ
round-trip'lerle her aşamada; `run_all_sprint4a_candidates()` sentetik
uçtan-uca — tüm 8 aday üretiliyor/hiçbiri canonical değil; gerçek
`window_m`/`window_traces` orkestrasyon hatası bu testte bulundu ve
düzeltildi), `tests/test_sprint4a_real_integration.py` (2, gerçek dosya
varsa çalışır: canonical Sprint 3 NPZ'si üzerinde background removal —
shape/dtype/finiteness/zaman ekseni/valid_mask/padding korunumu,
input=output+removed_component float32 hassasiyetinde, girdi mutasyona
uğramıyor; 8-aday orkestrasyonu gerçek veride — tüm hash'ler değişmedi,
ölçülebilir farklar var, hiçbir aday canonical).

Kod incelemesi sırasında spec bölüm 15/16/20'nin literal gereksinimleriyle
karşılaştırmalı bir denetim yapıldı ve üç boşluk bulundu/düzeltildi
(`removed_input_absolute_energy_ratio`, spatial concentration,
median-trace correlation, local-event amplitude retention, channel
consistency before/after, ve `BACKGROUND_FINAL_DECISION_REQUIRED.md`'nin
3 eksik kolonu) — düzeltme sonrası tüm 16 Sprint 4A testi ve tam 314 test
takımı yeniden çalıştırıldı, hepsi geçti. Detay:
[[02_SPRINTS/Sprint_04A_Background_Removal]] Issues Discovered.

### Diğer kalite kontrolleri (Sprint 4A, 2026-07-15)

```bash
ruff format . && ruff check . && mypy src/archaeogpr
```
`ruff format .`: 65 dosya (temiz, `test_sprint4a_pipeline.py` bir kez
yeniden biçimlendirildi — yalnızca stil). `ruff check .`: `All checks
passed!`. `mypy src/archaeogpr`: `Success: no issues found in 39 source
files` (spec-tamlık düzeltmesi sonrası dahil).

### Gerçek dosya CLI doğrulaması (Sprint 4A)

`python -m archaeogpr sprint4a-candidates outputs/sprint03/canonical_D2_B1/
sprint03_processed.npz --output-dir outputs/sprint04a` → girdi hash'i
`2044dd8f...82fd026`, işleme geçmişi `[time_zero_correction,
dc_offset_correction, dewow_correction, bandpass_correction]`, 8 aday
[A1..A8] çalıştırıldı, mühendislik kategorileri (A1/A2=preservation-
favoring, A3/A6=suppression-favoring, A4/A5/A7/A8=balanced), ham dosya
hash'i ve Sprint 2 canonical NPZ hash'i her ikisi de değişmedi, `Input
file hash unchanged: True`, `Canonical selected: false`, `Gain started:
false`. Programatik denetim: 8/8 aday NPZ'si geçerli (shape/dtype/NaN-Inf/
işleme geçmişi/padding), tüm JSON/CSV parse edilebilir, tüm PNG'ler finite
piksellerle açılabiliyor, hiçbir dosyada `"canonical": true` yok. Tam
detay: [[QC_Output_Validation]],
[[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].

## 2026-07-15 (Sprint 3 Canonicalization — D2 + B1 Selection)

Command:
```bash
pytest
```

Result:
```text
============================= test session starts =============================
platform win32 -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\baran\OneDrive\Desktop\School Stuff\Staj 2026\archaeogpr
configfile: pyproject.toml
testpaths: tests
collected 254 items

tests\test_bandpass.py ....................                              [  7%]
tests\test_cli_sprint3_canonical.py .......                              [ 10%]
tests\test_data_model.py .....................                           [ 18%]
tests\test_dc_offset.py ...............................                  [ 31%]
tests\test_dewow.py ....................                                 [ 38%]
tests\test_export_processed.py ....                                      [ 40%]
tests\test_ogpr_reader.py .............                                  [ 45%]
tests\test_processing_history.py .....                                   [ 47%]
tests\test_real_ogpr_integration.py ..                                   [ 48%]
tests\test_spectrum.py ........................                          [ 57%]
tests\test_sprint2_real_integration.py ..                                [ 58%]
tests\test_sprint3_1_decision_qc.py .......................              [ 67%]
tests\test_sprint3_canonical.py ...............                          [ 73%]
tests\test_sprint3_pipeline.py .....................                     [ 81%]
tests\test_sprint3_real_integration.py .                                 [ 82%]
tests\test_target_invariance.py .....                                    [ 84%]
tests\test_time_zero.py ........................................         [100%]

============================= 254 passed in 82.69s (0:01:22) ========================
```

232 önceki test hiç bozulmadı; 22 yeni canonicalization testi eklendi ve
geçti: `tests/test_sprint3_canonical.py` (15: canonical sabitler D2/B1'i
kodluyor, işleme sırası tam olarak `[time_zero_correction,
dc_offset_correction, dewow_correction, bandpass_correction]`, D2 gerçekten
`applied_window_ns=8.125`/65 örnek uyguluyor, B1 gerçekten 100-900 MHz
order=4 zero-phase uyguluyor, faz gecikmesi=0, zaman ekseni/valid_mask
korunuyor, padding tam sıfır, NaN/Inf yok, girdi mutasyona uğramıyor +
hash değişmiyor, iki bağımsız çalıştırma bit-bazında özdeş çıktı üretiyor,
`canonical_parameters.json`'da `selection_authority`/`selection_
references`/`dataset_scope` alanları doğru, çıktı NPZ `allow_pickle=False`
ile yeniden açılıyor, `CANONICAL_PROCESSING_NOTE.md` tüm gerekli
öğeleri içeriyor, aday-karşılaştırma kod yolu (`run_dewow_candidates`/
`run_bandpass_candidates`) hiçbir zaman "canonical" işaretlemiyor,
`correct_dewow`/`correct_bandpass`'in doğrudan çağrılması canonical
çıktıyla bit-bazında özdeş sonuç veriyor — yeni bir filtre algoritması
olmadığının kanıtı), `tests/test_cli_sprint3_canonical.py` (7: varsayılan
parametrelerle `canonical selected: true` + uyarı YOK, override edilince
`canonical selected: false` + açık uyarı, ham dosya hash'i ile Sprint 2
canonical NPZ hash'i CLI çıktısında ayrı ayrı ve doğru raporlanıyor (birbi-
rinden farklı, ikisi de değişmemiş), gerekli tüm tanılamalar basılıyor,
tam olarak 15 dosya üretiliyor, iki bağımsız CLI çalıştırması deterministik,
ham/canonical dosyalara dokunulmuyor).

### Diğer kalite kontrolleri (Sprint 3 Canonicalization, 2026-07-15)

```bash
ruff format . && ruff check . && mypy src/archaeogpr
```
`ruff format .`: 2 dosya yeniden biçimlendirildi (yalnızca stil —
`cli.py`, yeni test dosyaları). `ruff check .`: ilk çalıştırmada 1 hata
(satır uzunluğu, `tests/test_sprint3_canonical.py`'deki bir docstring);
bölünerek düzeltildi. Sonraki çalıştırma: `All checks passed!`. `mypy
src/archaeogpr`: `Success: no issues found in 35 source files` (ilk
çalıştırmadan itibaren hatasız — `sprint3_canonical.py` ve `cli.py`'nin
`sprint3` eklentisi dahil).

### Gerçek dosya CLI doğrulaması (Sprint 3 Canonicalization)

`python -m archaeogpr sprint3 outputs/sprint02/canonical_target16/
sprint02_processed.npz --output-dir outputs/sprint03/canonical_D2_B1
--dewow-method running-mean --dewow-window-ns 8 --dewow-edge-mode reflect
--bandpass-method butterworth --lowcut-mhz 100 --highcut-mhz 900 --order 4
--zero-phase` → `canonical selected: true`, `selection authority:
human/geophysical review`, D2 (`applied=8.125ns`, 65 örnek,
`edge_mode=reflect`), B1 (butterworth [100.0, 900.0] MHz order=4
zero_phase=True), işleme geçmişi sırası doğru, `padding verification`
dosyası üretildi, `Phase lag: max_abs_median_trace_cross_correlation_lag=0,
confirmed_zero_phase=True`, ham dosya hash'i ve Sprint 2 canonical NPZ
hash'i her ikisi de değişmedi. Tam olarak 15 dosya üretildi; eski
`outputs/sprint03/{dewow_candidates,bandpass_candidates,
combined_candidates}/` (202 dosya) değişmeden kaldı. Tam detay:
[[QC_Output_Validation]], [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]].

## 2026-07-15 (Sprint 3.1 — D2 Dewow Confirmation & B1/B2 Band-Pass Decision QC)

Command:
```bash
pytest -q
```

Result:
```text
........................................................................ [ 31%]
........................................................................ [ 62%]
........................................................................ [ 93%]
................                                                         [100%]
232 passed in 11.79s
```

209 önceki test hiç bozulmadı; 23 yeni Sprint 3.1 testi eklendi ve geçti
(`tests/test_sprint3_1_decision_qc.py`): mutlak/normalize spektrum modları
farklı sonuç veriyor, ortak dB referansı tüm adaylarda aynı (10x küçük
genlik → ~-20dB, kendi piki değil), pencere örnek seçimi doğru, padding
FFT'ten hariç, bant enerjisi entegrasyonu bilinen sinüste doğru bantta
toplanıyor, retention oranı doğru (+ sıfır referansta nan), B1/B2 ortak
amplitude scale (`_shared_limit`) kombine max'i kullanıyor, çıkarılan
bileşen = girdi - çıktı (pencereli), adjacent-trace correlation sentetik
koherent olayda yüksek (>0.9) rastgele gürültüde düşük (<0.2), bant enerjisi
yoğunlaşması ölçümü tekdüze/yoğunlaşmış veriyi ayırt ediyor,
channel-to-channel consistency benzer/farklı kanalları ayırt ediyor,
medyan-iz gecikmesi bilinen zero-phase filtrede sıfır (causal karşıtlığıyla,
yeni `median_trace_lag()` fonksiyonu üzerinden), polarity_preserved işaret
değişimini yakalıyor, girdi/zaman ekseni/valid_mask D2→B1/B2 zincirinde
değişmiyor, ham+canonical hash değişmiyor (gerçek dosya varsa, skip
edilmedi).

### Diğer kalite kontrolleri (Sprint 3.1, 2026-07-15)

```bash
ruff format src tests scripts configs && ruff check src tests scripts configs && mypy src
```
`ruff format`: 4-5 dosya yeniden biçimlendirildi (yalnızca stil). `ruff
check`: ilk çalıştırmada 20 hata (1 kullanılmayan import, 1 kullanılmayan
değişken, 2 f-string-without-placeholder, 16 satır-uzunluğu — çoğu
`scripts/generate_sprint3_1_decision_qc.py`'nin uzun tanılama print/reason
string'lerinde); hepsi bölünerek/kısaltılarak düzeltildi. `mypy src`:
`Success: no issues found in 34 source files` (ilk çalıştırmadan itibaren
hatasız).

### Gerçek dosya CLI/script doğrulaması (Sprint 3.1)

`python scripts/generate_sprint3_1_decision_qc.py` → D2 (`applied_window_ns
=8.125`), B1 (100-900 MHz), B2 (120-800 MHz); canonical NPZ hash değişmedi;
padding D2'den sonra değişmedi; D2/B1/B2 çıktılarında NaN/Inf yok; D2 karar
`recommended_dewow_candidate = D2`; band-pass mühendislik eğilimi
`preservation-favoring candidate`; `Canonical selected: false`.
Programatik denetim: 24 dosyanın hepsi sıfır byte değil, tüm PNG'ler
sonlu piksellerle açılabiliyor, tüm CSV/JSON geçerli. Tam detay:
[[QC_Output_Validation]], [[Sprint_03_1_Dewow_Bandpass_Decision_QC]].

## 2026-07-15 (Sprint 3 — Dewow & Band-Pass Filtering, Spectrum QC & Candidate Comparison)

Command:
```bash
pytest -q
```

Result:
```text
........................................................................ [ 34%]
........................................................................ [ 68%]
.................................................................        [100%]
209 passed in 12.09s
```

123 önceki test hiç bozulmadı; 86 yeni Sprint 3 testi eklendi ve geçti:
`test_dewow.py` (yeni, 20: sabit iz→tam sıfır, düşük-frekans sürüklenme
kaldırılırken yüksek-frekans korunuyor — periyodu tam pencere uzunluğuna
eşit bir sinüsün ayrık toplam özdeşliğiyle kanıtlandı — pulse konumu
korunuyor, girdi=çıktı+çıkarılan, padding hariç/değişmeden, valid_mask
bağımsız kopya, mean/median outlier farkı, pencere dönüşümü çift→tek
yuvarlama+uyarı, geçersiz method/edge_mode/pencere hataları, NaN guard,
processing_history, tekrar-işleme guard'ı+override, NPZ round-trip),
`test_bandpass.py` (yeni, 20: geçiş/durdurma bandı her iki yöntem,
zero-phase pulse-pozisyon koruması + causal karşıtlığı (kasıtlı, testin
ayırt edici olduğunu kanıtlamak için), Ormsby yapısal sıfır-faz,
girdi=çıktı+çıkarılan, padding hariç/değişmeden, valid_mask bağımsız kopya,
geçersiz Butterworth/Ormsby parametreleri, NaN guard, processing_history,
tekrar-işleme guard'ı, NPZ round-trip), `test_spectrum.py` (yeni, 24:
baskın frekans tespiti, gerçek frekans ekseni/Nyquist, padding ortak-
geçerli maskeyle hariç, `dataset_time` pencere seçimi, detrend/taper
(Hann sızıntısı ölçülebilir şekilde kanıtlandı), mean/median/RMS
agregasyon farklılaşması (güç-ortalaması eşitsizliği: RMS>mean>median),
genlik doğrusal ölçekleniyor (asla kare), dB dönüşümü sıfırda bile sonlu,
tüm hata yolları), `test_sprint3_pipeline.py` (yeni, 21: paylaşılan
`contiguous_true_runs`, `read_processed_npz` round-trip+hata yolları+
salt-okunurluk, `load_candidates_config`, sentetik uçtan-uca zincir +
yeniden-yüklenen NPZ'de tekrar-işleme guard'ı), `test_sprint3_real_
integration.py` (yeni, 1, gerçek dosya varsa çalışır: canonical zincir +
dewow + Butterworth + Ormsby, şekil/dtype/sonluluk/zaman ekseni/valid_mask/
padding/processing_history, düşük-frekans enerji azalması, geçiş-bandı
korunumu, medyan-iz konum toleransı, NPZ/QC round-trip, girdi/ham dosya
değişmedi).

### Diğer kalite kontrolleri (Sprint 3, 2026-07-15)

```bash
ruff format src tests configs && ruff check src tests configs && mypy src
```
`ruff format`: 12 dosya yeniden biçimlendirildi (yalnızca stil). `ruff
check`: ilk çalıştırmada 12 hata (2 kullanılmayan import — `shutil`,
`save_spectrum_comparison` — + 10 satır-uzunluğu, çoğu markdown tablo
başlığı/print f-string'i); kullanılmayan importlar `--fix` ile, satır
uzunlukları f-string'leri bölerek/tablo başlıklarını kısaltarak elle
düzeltildi. `mypy src`: 1 hata (`processing/dewow.py`, `np.pad`'in `mode`
parametresi için `str`→`Literal["reflect","edge"]` tip daraltması eksikti);
`_NUMPY_PAD_MODE` ve `_moving_window_baseline`'ın `pad_mode` parametresi
`Literal` ile tipize edilerek düzeltildi. Sonraki çalıştırmalar: `All
checks passed!`, `Success: no issues found in 30 source files`.

### Gerçek dosya CLI doğrulaması (Sprint 3)

`python -m archaeogpr sprint3-candidates outputs/sprint02/canonical_
target16/sprint02_processed.npz --output-dir outputs/sprint03` → dewow
adayları [D1,D2,D3,D4], band-pass adayları [B1,B2,B3,B4] (D2 tabanında),
kombine adaylar [C1..C6], girdi NPZ hash'i değişmedi, `Canonical selected:
false`. `python -m archaeogpr dewow|bandpass ...` standalone komutları da
ayrıca gerçek veride doğrulandı (her ikisi de `Canonical selected: false`
basıyor). Tam detay: [[QC_Output_Validation]],
[[Sprint_03_Dewow_Bandpass]].

## 2026-07-15 (Sprint 2.2 — Time-Zero-Relative Time Axis & Target-Invariant DC Offset)

Command:
```bash
pytest
```

Result:
```text
============================= test session starts =============================
platform win32 -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\baran\OneDrive\Desktop\School Stuff\Staj 2026\archaeogpr
configfile: pyproject.toml
testpaths: tests
collected 123 items

tests\test_data_model.py .....................                           [ 17%]
tests\test_dc_offset.py ...............................                  [ 42%]
tests\test_export_processed.py ....                                      [ 45%]
tests\test_ogpr_reader.py .............                                  [ 56%]
tests\test_processing_history.py .....                                  [ 60%]
tests\test_real_ogpr_integration.py ..                                   [ 61%]
tests\test_sprint2_real_integration.py ..                                [ 63%]
tests\test_target_invariance.py .....                                    [ 67%]
tests\test_time_zero.py ........................................         [100%]

============================= 123 passed in 5.30s =============================
```

101 Sprint 1+2+2.1 testi hiç bozulmadı; 22 yeni Sprint 2.2 testi eklendi ve
geçti: `test_time_zero.py` (30→40, +10: `time_ns[target_sample]==0`,
öncesi negatif/sonrası pozitif, örnek aralığı korunuyor, target=0/16 uç
değerleri, girdi eksen değişmiyor, çıktı eksen salt-okunur, diagnostics,
`sampling_time_ns` artık manual için de zorunlu), `test_dc_offset.py`
(24→31, +7: `dataset_time` doğru örnekleri seçiyor, yarı-açık pencere,
negatif-zaman dışlanıyor, valid mask kesişimi, padding hariç, sıfır
geçerli örnek hatası, mean/median aynı pencere), yeni
`test_target_invariance.py` (+5: aynı ham örnekler, eşit ofset array'leri,
ortak göreli-zaman bölgesinde eşit genlikler, target=16'da tam 16 örnek
daha az padding, processing history kaydı).

### Diğer kalite kontrolleri (Sprint 2.2, 2026-07-15)

```bash
ruff format src tests scripts && ruff check src tests scripts && mypy src
```
`ruff format`: 5 dosya yeniden biçimlendirildi (yalnızca stil). `ruff
check`: ilk çalıştırmada 3 satır-uzunluğu hatası (`cli.py`), f-string'ler
birden fazla satıra bölünerek düzeltildi. `mypy src`: 1 nullable-narrowing
hatası (`dc_offset.py`, `window_start_ns`/`window_end_ns`'in
`window_given` ile daraltılmaması); açık bir `assert` eklenerek
düzeltildi. Sonraki çalıştırmalar: `All checks passed!`,
`Success: no issues found in 23 source files`.

### Gerçek dosya CLI doğrulaması (Sprint 2.2)

`python -m archaeogpr sprint2 ... --target-sample 16 --max-shift-samples 96
--overflow-policy error --dc-window-start-ns 20 --dc-window-end-ns 100
--dc-window-reference dataset-time` → 0 kırpılan kanal,
`time_ns[16]==0.0`, `time_ns[0]==-2.0` ns, 16 negatif-zaman örneği, DC
offset mean=87.83521790660512. Aynı komut `--target-sample 0` ile
(ayrı, scratch konuma) çalıştırıldığında DC offset mean **tam olarak
aynı** değeri verdi (87.83521790660512, tüm gösterilen ondalıklara kadar).
Ham dosya hash'i tüm komutlar boyunca değişmedi. Tam detay:
[[QC_Output_Validation]], [[Sprint_02_2_TimeAxis_DCWindow_Validation]].

## 2026-07-15 (Sprint 2.1 — Review, Overflow Policy & Padding-Mask Safety)

Command:
```bash
pytest
```

Result:
```text
============================= test session starts =============================
platform win32 -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\baran\OneDrive\Desktop\School Stuff\Staj 2026\archaeogpr
configfile: pyproject.toml
testpaths: tests
collected 101 items

tests\test_data_model.py .....................                           [ 20%]
tests\test_dc_offset.py ........................                         [ 44%]
tests\test_export_processed.py ....                                      [ 48%]
tests\test_ogpr_reader.py .............                                  [ 61%]
tests\test_processing_history.py .....                                  [ 66%]
tests\test_real_ogpr_integration.py ..                                   [ 68%]
tests\test_sprint2_real_integration.py ..                                [ 70%]
tests\test_time_zero.py ..............................                   [100%]

============================= 101 passed in 4.54s =============================
```

77 Sprint 1+2 testi hiç bozulmadı; 24 yeni Sprint 2.1 testi eklendi ve
geçti: `test_time_zero.py` (20→30, +10: overflow_policy varsayılan/açık hata,
kırpmanın yalnızca opt-in ile erişilebilir olması,
`has_clipped_shifts`/`valid_for_downstream_processing` bayrakları,
`valid_mask` sol/sağ/sıfır-shift doğruluğu, şekil, salt-okunurluk),
`test_dc_offset.py` (15→24, +9: padding'in ofset hesaplamasından ve çıkarmadan
hariç tutulması, sıfır-padding-değerinin korunması, geçerli-bölge
ortalamasının sıfıra yaklaşması, pencere ∩ maske kesişimi, sıfır geçerli
örnek hatası, maskesiz eski davranışın korunması, mutasyon yokluğu,
processing history), yeni `test_export_processed.py` (0→4, +4: NPZ round-trip
`valid_mask` koruması, birleşik export'un DC-offset-maskesi-yoksa
time-zero maskesine düşmesi, maskesiz export'ta anahtarın hiç
yazılmaması), `test_sprint2_real_integration.py` (1→2, +1: gerçek dosyada
`max_shift_samples=96` ile sıfır kırpma).

`test_time_zero.py`'deki eski
`test_shift_exceeding_max_shift_samples_is_clipped_with_warning` testi,
yeni güvenli politikaya uygun biçimde
`test_shift_exceeding_max_shift_samples_is_clipped_with_warning_when_clip_is_requested`
olarak yeniden adlandırıldı ve `overflow_policy="clip"`'i açıkça geçirecek
şekilde güncellendi (gevşetilmedi — hâlâ aynı kırpma davranışını
doğruluyor, sadece artık açık opt-in gerektiğini de doğruluyor).

### Diğer kalite kontrolleri (Sprint 2.1, 2026-07-15)

```bash
ruff format src tests && ruff check src tests && mypy src
```
`ruff format`: 4 dosya yeniden biçimlendirildi (yalnızca stil —
`export/processed.py`, `test_dc_offset.py`, `test_sprint2_real_integration.py`,
`test_time_zero.py`). `ruff check`: `All checks passed!`. `mypy src`:
`Success: no issues found in 23 source files`.

### Gerçek dosya CLI doğrulaması (Sprint 2.1)

- Varsayılan parametrelerle (`max_shift_samples=64` implicit,
  `overflow_policy=error` implicit) `time-zero` komutu: `ProcessingError`
  ile durdu (exit code 1), çıktı klasörü hiç oluşturulmadı.
- `--max-shift-samples 96 --overflow-policy error`, `target_sample` 0 ve
  16: her ikisi `Has clipped shifts: False`,
  `Valid for downstream processing: True`, 11/11 kanalda
  `requested_shift == applied_shift`.
- `sprint2` komutu (her iki target): `DC offset valid_mask used: True`;
  üretilen `sprint02_processed.npz`'de her 11 kanalın padding bölgesi
  `unique values == [0.]`.
- Ham dosya SHA-256
  (`66d840c313b4beed10bea2e35d88431573f6fab0f02bba17792c0920028b62a6`)
  tüm komutlar boyunca değişmedi. Tam detay: [[QC_Output_Validation]],
  [[Sprint_02_1_TimeZero_DCOffset_Review]].

## 2026-07-14 (Sprint 2 — Time-Zero & DC Offset)

Command:
```bash
pytest
```

Result:
```text
============================= test session starts =============================
platform win32 -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\baran\OneDrive\Desktop\School Stuff\Staj 2026\archaeogpr
configfile: pyproject.toml
testpaths: tests
collected 77 items

tests\test_data_model.py .....................                           [ 27%]
tests\test_dc_offset.py ...............                                  [ 46%]
tests\test_ogpr_reader.py .............                                  [ 63%]
tests\test_processing_history.py .....                                  [ 70%]
tests\test_real_ogpr_integration.py ..                                   [ 72%]
tests\test_sprint2_real_integration.py .                                 [ 74%]
tests\test_time_zero.py ....................                             [100%]

============================= 77 passed in 4.03s ==============================
```

36 Sprint 1 testi (`test_data_model.py`, `test_ogpr_reader.py`,
`test_real_ogpr_integration.py`) hiç bozulmadı; 41 yeni Sprint 2 testi
(`test_time_zero.py`: 20, `test_dc_offset.py`: 15, `test_processing_history.py`:
5, `test_sprint2_real_integration.py`: 1) eklendi ve geçti.

### Diğer kalite kontrolleri (Sprint 2, 2026-07-14)

```bash
ruff format . && ruff check . && mypy src/archaeogpr
```
`ruff format .`: 8 dosya yeniden biçimlendirildi (yalnızca stil).
`ruff check .`: ilk çalıştırmada 7 hata (satır uzunluğu, import sıralama,
gereksiz quote'lar), 6'sı `--fix` ile otomatik düzeltildi, 1'i (docstring
satır uzunluğu, `export/processed.py`) elle kısaltıldı. Sonraki çalıştırma:
`All checks passed!`.
`mypy src/archaeogpr`: `qc/dc_offset.py`'de 2 tip hatası (`ax.hist(bins=...)`'e
`numpy.ndarray` verilmesi; matplotlib stub'ları `Sequence[float]` bekliyor).
`.tolist()` ile düzeltildi. Sonraki çalıştırma: `Success: no issues found
in 23 source files`.

### Gerçek dosya CLI doğrulaması (Sprint 2)

`time-zero`, `dc-offset` (varsayılan + pencereli), `sprint2` komutları
gerçek dosya üzerinde çalıştırıldı; tüm çıktılar üretildi, NaN/Inf yok, ham
dosya hash'i değişmedi. Tam detay: [[QC_Output_Validation]],
[[Sprint_02_TimeZero_DCOffset]].

## 2026-07-14 (Sprint 1)

Command:
```bash
pytest -v
```

Result:
```text
============================= test session starts =============================
platform win32 -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\baran\OneDrive\Desktop\School Stuff\Staj 2026\archaeogpr
configfile: pyproject.toml
testpaths: tests
collected 36 items

tests/test_data_model.py::test_amplitudes_are_read_only PASSED           [  2%]
tests/test_data_model.py::test_functions_do_not_mutate_amplitudes_in_place PASSED [  5%]
tests/test_data_model.py::test_metadata_is_json_serializable_directly PASSED [  8%]
tests/test_data_model.py::test_metadata_mapping_rejects_item_assignment PASSED [ 11%]
tests/test_data_model.py::test_constructing_with_non_serializable_metadata_raises PASSED [ 13%]
tests/test_data_model.py::test_processing_history_starts_empty PASSED    [ 16%]
tests/test_data_model.py::test_with_processing_step_does_not_mutate_original PASSED [ 19%]
tests/test_data_model.py::test_mismatched_coordinate_shape_raises[x] PASSED [ 22%]
tests/test_data_model.py::test_mismatched_coordinate_shape_raises[y] PASSED [ 25%]
tests/test_data_model.py::test_mismatched_coordinate_shape_raises[depth_top_m] PASSED [ 27%]
tests/test_data_model.py::test_mismatched_coordinate_shape_raises[elevation_top_m] PASSED [ 30%]
tests/test_data_model.py::test_mismatched_coordinate_shape_raises[depth_bottom_m] PASSED [ 33%]
tests/test_data_model.py::test_mismatched_time_ns_length_raises PASSED   [ 36%]
tests/test_data_model.py::test_dataset_without_geolocation_is_constructible PASSED [ 38%]
tests/test_data_model.py::test_compute_time_window_ns PASSED             [ 41%]
tests/test_data_model.py::test_compute_depth_estimates PASSED            [ 44%]
tests/test_data_model.py::test_compute_profile_length_and_along_track_spacing PASSED [ 47%]
tests/test_data_model.py::test_compute_cross_channel_spacing_and_swath_width PASSED [ 50%]
tests/test_data_model.py::test_compute_amplitude_statistics_known_values PASSED [ 52%]
tests/test_data_model.py::test_derive_metadata_reports_missing_velocity_warning PASSED [ 55%]
tests/test_data_model.py::test_derive_metadata_geometry_matches_dataset_coordinates PASSED [ 58%]
tests/test_ogpr_reader.py::test_invalid_magic_is_rejected PASSED         [ 61%]
tests/test_ogpr_reader.py::test_invalid_json_header_is_rejected PASSED   [ 63%]
tests/test_ogpr_reader.py::test_missing_radar_block_raises PASSED        [ 66%]
tests/test_ogpr_reader.py::test_unsupported_value_type_raises PASSED     [ 69%]
tests/test_ogpr_reader.py::test_truncated_radar_block_raises PASSED      [ 72%]
tests/test_ogpr_reader.py::test_inconsistent_radar_dimensions_raises PASSED [ 75%]
tests/test_ogpr_reader.py::test_invalid_geolocation_block_raises PASSED  [ 77%]
tests/test_ogpr_reader.py::test_radar_dimensions_are_reshaped_correctly PASSED [ 80%]
tests/test_ogpr_reader.py::test_time_ns_axis_is_correct PASSED           [ 83%]
tests/test_ogpr_reader.py::test_file_without_geolocation_opens_with_radar_data PASSED [ 86%]
tests/test_ogpr_reader.py::test_frequency_typo_fallback_is_supported PASSED [ 88%]
tests/test_ogpr_reader.py::test_read_ogpr_header_exposes_raw_header PASSED [ 91%]
tests/test_ogpr_reader.py::test_geolocation_fields_round_trip PASSED     [ 94%]
tests/test_real_ogpr_integration.py::test_real_file_matches_documented_metadata PASSED [ 97%]
tests/test_real_ogpr_integration.py::test_real_file_derived_metadata_is_physically_sane PASSED [100%]

============================= 36 passed in 0.73s ==============================
```

Not: `test_real_ogpr_integration.py` bu çalıştırmada **skip edilmedi** —
`data/raw/Swath003_Array02.ogpr` mevcuttu, dosya bulunamasaydı bu iki test
`pytest.mark.skipif` ile skip olurdu (test suite fail olmazdı).

## Diğer kalite kontrolleri (2026-07-14)

```bash
ruff format .
```
6 dosya yeniden biçimlendirildi (yalnızca stil), 12 dosya değişmedi.

```bash
ruff check .
```
İlk çalıştırmada 8 hata (import sıralama/stil), `ruff check . --fix` ile
tamamı otomatik düzeltildi. Sonraki çalıştırma: `All checks passed!`.

```bash
mypy src/archaeogpr
```
İlk çalıştırmada `qc/geometry.py`'de 4 tip hatası (nullable `x`/`y`'nin
`has_geolocation` kontrolüyle daraltılmaması). Açık bir `assert` eklenerek
düzeltildi. Sonraki çalıştırma: `Success: no issues found in 14 source files`.

## İlgili notlar
[[Parser_Validation]], [[QC_Output_Validation]], [[Sprint_01_OpenGPR_Infrastructure]]
