---
type: session-log
tags: [session-log]
date: 2026-07-15
sprint: 3 canonicalization
status: done
---

# Session Summary

## User Request
ArchaeoGPR projesinde Sprint 3 canonicalization görevini tamamla: yeni
filtre algoritması geliştirmeden ve Sprint 4'ü başlatmadan, kullanıcının
verdiği açık insan/jeofizik kararını (dewow: **D2**, `running_mean`,
`requested_window_ns=8.0` → beklenen `applied_window_ns=8.125`/65 örnek,
`edge_mode=reflect`; band-pass: **B1**, Butterworth, 100-900 MHz, order=4,
zero-phase) canonical Sprint 3 zinciri (Sprint 2 canonical → D2 → B1)
olarak kodlamak. Ayrıntılı istekler: `outputs/sprint03/canonical_D2_B1/`
altında tam olarak 15 dosya (eski aday klasörlerine dokunmadan); kapsamlı
güvenlik/doğrulama listesi (hash değişmezliği, immutability, shape/time
axis/valid_mask korunumu, padding sıfır, NaN/Inf yok, removed component
doğruluğu, zero-phase lag=0, processing_history sırası, D2/B1'in gerçekten
uygulandığının doğrulanması, `allow_pickle=False` ile NPZ yeniden açılması);
belirli içerikte `CANONICAL_PROCESSING_NOTE.md`; belirtilen tam CLI komutu
ve zorunlu terminal çıktıları (`canonical selected: true`, `selection
authority: human/geophysical review`, vb.); ≥10 test gereksinimi; Obsidian
senkronizasyonu (Sprint 3/3.1'i `done` yapmak, Dewow.md/Bandpass_Filter.md'ye
canonical parametre eklemek, yeni ADR-007, 11+ dosya güncellemesi, yeni
session log) — Sprint 4'ü KESİNLİKLE başlatmadan; kalite kontrolleri
(ruff/mypy/pytest/vault validator/gerçek CLI); ve 13 maddelik tamamlanma
raporu.

## Work Completed
- `src/archaeogpr/sprint3_canonical.py` yazıldı:
  `run_sprint3_canonical()` (yalnızca `correct_dewow()`/`correct_bandpass()`'i
  D2/B1 sabit parametreleriyle çağırır — yeni bir filtre algoritması YOK)
  ve `write_canonical_processing_note()` (D2/B1 gerekçesi, 800-900 MHz'in
  kesin bir hedef yorumu olmadığı, veri-seti-özel kapsam, doğrulama, "bu
  not ne yapmaz" bölümleri).
- `src/archaeogpr/cli.py`'ye `sprint3` alt komutu eklendi (`_cmd_sprint3`):
  D2/B1'i varsayılan olarak kullanır, parametre override edilirse
  `canonical selected: false` + uyarı basar. Ham dosya hash'i (`dataset.
  metadata["source_file"]["path"]`'ten türetilerek, hiçbir yerde sabit
  gömülmeden) ve Sprint 2 canonical NPZ hash'i ayrı ayrı, doğru şekilde
  raporlanıyor (ilk taslakta ikisi yanlışlıkla aynı NPZ'nin hash'iydi —
  düzeltildi, bkz. Issues Found).
- `tests/test_sprint3_canonical.py` (15 test) ve
  `tests/test_cli_sprint3_canonical.py` (7 test) yazıldı: canonical sabitler
  D2/B1'i kodluyor, işleme sırası doğru, D2/B1 gerçek parametreleriyle
  uygulanıyor, faz gecikmesi sıfır, zaman ekseni/valid_mask/padding
  korunuyor, girdi mutasyona uğramıyor, hash'ler değişmiyor, deterministik,
  `canonical_parameters.json`'da `selection_authority` alanı var,
  aday-karşılaştırma kod yolu (`run_dewow_candidates`/
  `run_bandpass_candidates`) hiçbir zaman "canonical" işaretlemiyor, CLI
  hem varsayılan hem override durumunda doğru davranıyor.
- Gerçek canonical CLI çalıştırıldı:
  `outputs/sprint03/canonical_D2_B1/` (tam olarak 15 dosya); eski aday
  klasörleri (202 dosya) değişmeden kaldı.
- Tüm 15 dosya programatik olarak denetlendi (sıfır byte yok, PNG'ler
  sonlu piksellerle açılıyor, JSON'lar geçerli, NPZ `allow_pickle=False`
  ile yeniden açılıyor, processing_history sırası doğru) + görsel olarak
  denetlendi (B-scan'ler, spektrum karşılaştırması, transfer fonksiyonu,
  removed component — hepsi beklenen desenle tutarlı).
- ADR-007 yazıldı: D2/B1 gerekçesi, preservation-first politika, 800-900
  MHz belirsizliği, veri-seti-özel kapsam, yeniden-doğrulama gerekliliği.
- Obsidian vault senkronize edildi (aşağıya bakın).

## Files Created
`src/archaeogpr/sprint3_canonical.py`, `tests/test_sprint3_canonical.py`,
`tests/test_cli_sprint3_canonical.py`. Vault:
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]] (yeni), bu dosya.

## Files Modified
`src/archaeogpr/cli.py` (`sprint3` alt komutu + `_cmd_sprint3` + dispatch
wiring). Ham `.ogpr` dosyası ve tüm önceki canonical/aday çıktıları
**değiştirilmedi/üzerine yazılmadı** — yalnızca yeni
`outputs/sprint03/canonical_D2_B1/` klasörü eklendi.

## Commands Executed
`pytest`, `ruff format .`, `ruff check .`, `mypy src/archaeogpr`,
`python -m archaeogpr sprint3 outputs/sprint02/canonical_target16/
sprint02_processed.npz --output-dir outputs/sprint03/canonical_D2_B1
--dewow-method running-mean --dewow-window-ns 8 --dewow-edge-mode reflect
--bandpass-method butterworth --lowcut-mhz 100 --highcut-mhz 900 --order 4
--zero-phase`, `python scripts/validate_obsidian_vault.py
obsidian/ArchaeoGPR_Vault`, SHA-256 karşılaştırmaları.

## Tests Run
`pytest` → **254 passed, 0 failed, 0 skipped** (232 önceki + 22 yeni
canonicalization testi; gerçek dosya entegrasyon testleri dahil — skip
edilmedi). Tam çıktı: [[07_VALIDATION/Test_Results]].

## Outputs Generated
`outputs/sprint03/canonical_D2_B1/` (tam olarak 15 dosya):
`sprint03_processed.npz`, `processing_history.json`,
`processing_metadata.json`, `canonical_parameters.json`,
`channel00_{raw,after_dewow,final,removed_dewow,removed_bandpass}.png`,
`all_channels_final.png`, `spectrum_before_after.png`,
`transfer_function.png`, `padding_verification.json`,
`phase_verification.json`, `CANONICAL_PROCESSING_NOTE.md`. Tam liste ve
doğrulama: [[07_VALIDATION/QC_Output_Validation]].

## Decisions Made
[[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]] — D2 + B1 canonical
seçimi, insan/jeofizik kararı olarak kaydedildi (kod tarafından otomatik
seçilmedi). Bu seçim yalnızca `Swath003_Array02.ogpr` için geçerlidir.

## Issues Found
Geliştirme sırasında kendi kendime bulunan ve düzeltilen bir hata (kod
hiçbir zaman commit/paylaşılmadı): `_cmd_sprint3`'ün ilk taslağında, ham
`.ogpr` dosyasının hash'i yerine yanlışlıkla Sprint 2 canonical NPZ'nin
hash'i iki kez hesaplanıp hem "ham dosya hash'i" hem "Sprint 2 canonical
hash'i" olarak raporlanıyordu. Düzeltme: ham dosyanın yolu
`dataset.metadata["source_file"]["path"]`'ten (hiçbir yerde sabit
gömülmeden) türetildi ve ayrı olarak hash'lendi; CLI artık iki hash'i de
doğru ve ayrı ayrı yazdırıyor (`Raw source file hash (sha256): ...`,
`Sprint 2 canonical NPZ hash (sha256): ...`).

## Remaining Work
- Sprint 4 hâlâ tanımlanmadı ve **kullanıcının kendi açık isteği
  olmadan başlatılmayacak** (D2+B1'in canonical seçilmiş olması, tek
  başına, Sprint 4'ü otomatik olarak açmaz).
- 800-900 MHz bandındaki korunan enerjinin kesin bir arkeolojik hedef
  yorumu olmadığı ADR-007'de açıkça belgelendi; bu belirsizlik kalıcı
  olarak açık kalır (bir kod hatası değil).
- D2/B1 parametreleri yalnızca bu veri seti için canonical — başka bir
  veri seti kendi Sprint-3-benzeri aday karşılaştırmasını ve kendi
  Sprint-3.1-benzeri karar QC'sini gerektirir.

## Recommended Next Prompt
"Sprint 4'ü başlatmak istiyorum: [kapsam] üzerinde çalış" — yalnızca
kullanıcı kendi isteğiyle Sprint 4'ü tanımlamaya karar verirse.

## Vault Files Updated
`00_HOME.md`, `01_PROJECT_STATE/{00_Claude_Context,01_Current_Project_
State,02_Next_Development_Sprint,03_Open_Issues}.md`,
`02_SPRINTS/{Sprint_Index,Sprint_03_Dewow_Bandpass,
Sprint_03_1_Dewow_Bandpass_Decision_QC}.md`,
`04_DATASETS/Swath003_Array02.md`,
`05_PROCESSING/{Dewow,Bandpass_Filter,Processing_Index}.md`,
`06_DECISIONS/{ADR_007_Canonical_D2_B1_Selection (yeni),Decision_Index}.md`,
`07_VALIDATION/{Test_Results,QC_Output_Validation,Known_Uncertainties}.md`,
`08_SESSION_LOGS/{Session_Index,bu dosya}.md`.
