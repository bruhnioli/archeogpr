---
type: architecture
---

# Repository Map

## Amaç

Bu not, `archaeogpr` deposunun Sprint 4A sonundaki dizin/dosya yapısını, her öğe için tek satırlık bir açıklamayla listeler. Amaç, kod tabanında gezinmeden önce hızlı bir zihinsel harita sağlamaktır; ayrıntılı davranış için ilgili mimari notlara bakın ([[Architecture_Overview]], [[Processing_Pipeline_Architecture]]).

## Kök Dizin

- `` `pyproject.toml` `` — proje meta verisi, bağımlılıklar (`numpy`, `pandas`, `matplotlib`, `scipy`, `pyyaml`, `pytest`; dev: `ruff`, `mypy`), `archaeogpr` konsol script girişi. `scipy`/`pyyaml` Sprint 3'te eklendi (band-pass filtre tasarımı + aday YAML konfigürasyonları için).
- `` `README.md` `` — kurulum, CLI kullanımı, kapsam ve güvenlik notlarını içeren proje ana dokümanı.
- `` `CLAUDE.md` `` — projenin ve bu Obsidian vault'unun uyması gereken davranış kuralları (ham veri güvenliği, eksen sırası, işleme kısıtları, vault bakım kuralları).

## `data/`

- `` `data/raw/` `` — salt okunur girdi dizini; gerçek örnek dosya `Swath003_Array02.ogpr` burada tutulur ve hiçbir kod tarafından değiştirilmez.
- `` `data/reference/` `` — şu an boş; ileride referans/karşılaştırma verisi için ayrılmıştır.

## `outputs/`

- `` `outputs/inspect/` `` — `inspect` CLI komutunun ürettiği QC çıktıları: metadata JSON, header JSON, geolocation CSV, 3 PNG (kanal B-scan, tüm kanallar, survey geometry) ve `radar_volume.npz`.
- `` `outputs/sprint02/{time_zero,time_zero_manual,dc_offset,dc_offset_windowed,combined,canonical_target16}/` `` — Sprint 2/2.1/2.2 `time-zero`/`dc-offset`/`sprint2` CLI komutlarının ürettiği QC/export çıktıları; `canonical_target16/` canonical Sprint 2 çıktısıdır (Sprint 3'ün girdisi).
- `` `outputs/sprint03/{dewow_candidates,spectrum,bandpass_candidates,combined_candidates}/` `` — (Sprint 3) `dewow`/`bandpass`/`sprint3-candidates` CLI komutlarının ürettiği aday karşılaştırma çıktıları (209 dosya) + üst düzey `SPRINT3_REVIEW_REQUIRED.md`. **Hiçbiri canonical değildir.**
- `` `outputs/sprint03_1/` `` — (Sprint 3.1) `scripts/generate_sprint3_1_decision_qc.py`'nin ürettiği D2 doğrulama + B1/B2 karar QC çıktıları (24 dosya), `DECISION_PANEL_D2_B1_B2.png`, `BANDPASS_FINAL_DECISION_REQUIRED.md`. **Hiçbiri canonical değildir.**
- `` `outputs/sprint03/canonical_D2_B1/` `` — (Sprint 3 Canonicalization) `sprint3` CLI komutunun ürettiği canonical Sprint 3 çıktısı (15 dosya, D2 dewow + B1 band-pass, insan/jeofizik kararı — bkz. [[06_DECISIONS/ADR_007_Canonical_D2_B1_Selection]]). Sprint 4A'nın girdisi.
- `` `outputs/sprint04a/{background_candidates/{A1_global_mean,...,A8_sliding_median_150m},comparison}/` `` — (Sprint 4A) `sprint4a-candidates` CLI komutunun ürettiği 8 background-removal adayı (8×18 dosya) + karşılaştırma klasörü (19 dosya) + üst düzey `BACKGROUND_DECISION_PANEL.png`/`_DETAIL.png`/`BACKGROUND_FINAL_DECISION_REQUIRED.md`. **Hiçbiri canonical değildir** — bkz. [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].
- Bu dizinler üretilen (generated) içerik barındırır; vault'a kopyalanmaz, sadece not içinden yol olarak referans verilir.

## `configs/`

- `` `configs/time_zero_picks.json` `` — `time-zero --method manual --picks-file` için örnek/doğrulanmış kanal-bazlı pick dosyası (kanal → örnek indeksi).
- `` `configs/dewow_candidates.yaml` `` — (Sprint 3) dewow aday tanımları (D1-D4) + `edge_mode`; QC karşılaştırma girdisi, hiçbiri canonical değil.
- `` `configs/bandpass_candidates.yaml` `` — (Sprint 3) band-pass aday tanımları (B1-B4) + `dewow_base_candidate` + kombine aday çiftleri (C1-C6); QC karşılaştırma girdisi, hiçbiri canonical değil.
- `` `configs/background_candidates.yaml` `` — (Sprint 4A) background-removal aday tanımları (A1-A8) + `edge_mode`; QC karşılaştırma girdisi, hiçbiri canonical değil.

## `src/archaeogpr/`

- `` `src/archaeogpr/__init__.py` `` — paket girişi.
- `` `src/archaeogpr/__main__.py` `` — `python -m archaeogpr` çalıştırma girişi.
- `` `src/archaeogpr/cli.py` `` — argparse tabanlı CLI; `inspect`, `header`, `time-zero`, `dc-offset`, `sprint2`, `dewow`, `bandpass`, `sprint3-candidates`, `sprint3`, `background`, `sprint4a-candidates` alt komutlarını tanımlar.
- `` `src/archaeogpr/io/exceptions.py` `` — sekiz özel istisna sınıfı: `OGPRError`, `InvalidMagicError`, `InvalidHeaderError`, `MissingRadarBlockError`, `UnsupportedValueTypeError`, `TruncatedBlockError`, `InconsistentDimensionsError`, `InvalidGeolocationBlockError`.
- `` `src/archaeogpr/io/ogpr_reader.py` `` — `read_ogpr(path)` ve `read_ogpr_header(path)`; ikili/header okuyucunun tamamı.
- `` `src/archaeogpr/model/dataset.py` `` — değişmez `GPRDataset` frozen dataclass'ı ve `DatasetValidationError`.
- `` `src/archaeogpr/model/_frozen.py` `` — (Sprint 2) `GPRDataset` ve `ProcessingResult` arasında paylaşılan `FrozenDict` + array-freeze yardımcıları.
- `` `src/archaeogpr/processing/common.py` `` — (Sprint 2) ns→sample pencere dönüşümü, `padding_mask()`, `build_processing_record()`, `TIME_ZERO_REFERENCE_WARNING`; (Sprint 3) `contiguous_true_runs()` (dewow + band-pass tarafından paylaşılır).
- `` `src/archaeogpr/processing/result.py` `` — (Sprint 2) `ProcessingResult` (dataset + removed_component + diagnostics + warnings).
- `` `src/archaeogpr/processing/time_zero.py` `` — (Sprint 2) `correct_time_zero()`.
- `` `src/archaeogpr/processing/dc_offset.py` `` — (Sprint 2) `correct_dc_offset()`.
- `` `src/archaeogpr/processing/dewow.py` `` — (Sprint 3) `correct_dewow()` — running_mean/running_median, segment-bazlı. Bkz. [[06_DECISIONS/ADR_005_Dewow_Window_and_Edge_Policy]].
- `` `src/archaeogpr/processing/bandpass.py` `` — (Sprint 3) `correct_bandpass()` — zero-phase Butterworth + Ormsby, segment-bazlı. Bkz. [[06_DECISIONS/ADR_006_ZeroPhase_Bandpass_and_Masked_Segments]].
- `` `src/archaeogpr/processing/background.py` `` — (Sprint 4A) `remove_background()` — global_mean/global_median/sliding_mean/sliding_median, kanal-bazlı bağımsız; `compute_trace_spacing()`. Bkz. [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].
- `` `src/archaeogpr/qc/metadata.py` `` — türetilmiş metadata için saf (pure) fonksiyonlar, `derive_metadata()`.
- `` `src/archaeogpr/qc/bscan.py` `` — `plot_bscan`, `save_channel_bscan`, `save_all_channels_bscan`; (Sprint 2) `compute_shared_clip_limit`, `plot_bscan_difference`, `save_bscan_comparison`, `save_stage_differences`.
- `` `src/archaeogpr/qc/geometry.py` `` — `plot_survey_geometry`, `save_survey_geometry`.
- `` `src/archaeogpr/qc/time_zero.py` `` — (Sprint 2) median trace overlay + picks/shifts QC grafikleri.
- `` `src/archaeogpr/qc/dc_offset.py` `` — (Sprint 2) ofset histogramı, trace-mean karşılaştırması, kanal-bazlı ofset istatistikleri.
- `` `src/archaeogpr/qc/spectrum.py` `` — (Sprint 3) `compute_amplitude_spectrum()`, `save_spectrum_comparison()`, `to_db()`.
- `` `src/archaeogpr/qc/dewow.py` `` — (Sprint 3) `save_dewow_qc_suite()` ve ilgili tekil grafik fonksiyonları.
- `` `src/archaeogpr/qc/bandpass.py` `` — (Sprint 3) `save_bandpass_qc_suite()`, transfer fonksiyonu/dürtü tepkisi grafikleri.
- `` `src/archaeogpr/qc/spatial_coherence.py` `` — (Sprint 3.1) adjacent-trace correlation, local RMS, trace-to-trace difference energy, channel-to-channel consistency, band-energy concentration.
- `` `src/archaeogpr/qc/phase_metrics.py` `` — (Sprint 3.1) ana pik farkı, sıfır geçişi farkı, lokal waveform correlation, polarity korunması, `median_trace_lag()`.
- `` `src/archaeogpr/qc/band_energy.py` `` — (Sprint 3.1) bant enerjisi entegrasyonu, retention ratio.
- `` `src/archaeogpr/qc/decision_qc.py` `` — (Sprint 3.1) pencereli B-scan ızgaraları, çok-modlu spektrum karşılaştırması, karar paneli.
- `` `src/archaeogpr/qc/background.py` `` — (Sprint 4A) sinyal-koruma + removed-component metrikleri, `compute_localized_event_risk()` (QC-only, arkeolojik sınıflandırma YOK), plotting suite. Bkz. [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]].
- `` `src/archaeogpr/export/basic.py` `` — `write_metadata_json`, `write_header_json`, `write_geolocation_csv`, `write_radar_volume_npz`.
- `` `src/archaeogpr/export/processed.py` `` — (Sprint 2) `write_channel_picks_csv`, `write_offsets_csv`, `write_processing_metadata_json`, `write_corrected_npz`, `write_combined_npz`, `write_processing_history_json`, `write_sprint2_summary_json`.
- `` `src/archaeogpr/export/sprint3.py` `` — (Sprint 3) `read_processed_npz()` (güvenli NPZ yükleyici), `load_candidates_config()`, `write_padding_verification_json()`.
- `` `src/archaeogpr/export/sprint4a.py` `` — (Sprint 4A) `write_signal_preservation_metrics_json()`, `write_removed_component_metrics_json()`, `write_trace_spacing_and_window_json()`, `write_candidate_validation_json()`.
- `` `src/archaeogpr/sprint3_candidates.py` `` — (Sprint 3) dewow/spektrum/band-pass/kombine aday orkestrasyonu + karşılaştırma + `SPRINT3_REVIEW_REQUIRED.md` yazıcısı; `sha256_file()` (Sprint 3.1/canonicalization/4A tarafından da paylaşılır).
- `` `src/archaeogpr/sprint3_canonical.py` `` — (Sprint 3 Canonicalization) `run_sprint3_canonical()`, `write_canonical_processing_note()` — D2+B1 sabit parametreleri, yeni filtre algoritması YOK.
- `` `src/archaeogpr/sprint4a_candidates.py` `` — (Sprint 4A) 8-aday orkestrasyonu (`run_background_candidates()`, `run_synthetic_risk_experiments()`, `build_background_comparison()`, `save_decision_panel()`, `write_background_final_decision_required()`, `run_all_sprint4a_candidates()`) — **hiçbir aday canonical seçmez**.

## `tests/`

- `` `tests/conftest.py` `` — sentetik `.ogpr` byte-builder fixture'ı (`ogpr_builder`) ve (Sprint 2) sentetik `GPRDataset` fixture'ı (`dataset_factory`); gerçek dosyaya ihtiyaç duymadan birim testleri çalıştırmayı sağlar.
- `` `tests/test_ogpr_reader.py` `` — okuyucunun birim testleri.
- `` `tests/test_data_model.py` `` — `GPRDataset` değişmezlik/doğrulama testleri.
- `` `tests/test_real_ogpr_integration.py` `` — gerçek örnek dosyaya karşı entegrasyon testi; dosya yoksa **başarısız olmaz**, temiz şekilde atlanır (skip).
- `` `tests/test_time_zero.py` `` — (Sprint 2) `correct_time_zero()` sentetik testleri (40 test).
- `` `tests/test_dc_offset.py` `` — (Sprint 2) `correct_dc_offset()` sentetik testleri (31 test).
- `` `tests/test_processing_history.py` `` — (Sprint 2) birleşik pipeline'ın `processing_history` sırası/immutability testleri.
- `` `tests/test_sprint2_real_integration.py` `` — (Sprint 2) gerçek dosya üzerinde time-zero + DC offset entegrasyon testi; dosya yoksa skip.
- `` `tests/test_dewow.py` `` — (Sprint 3) `correct_dewow()` sentetik testleri (20 test).
- `` `tests/test_bandpass.py` `` — (Sprint 3) `correct_bandpass()` sentetik testleri (20 test, zero-phase karşıtlığı dahil).
- `` `tests/test_spectrum.py` `` — (Sprint 3) `compute_amplitude_spectrum()` testleri (24 test).
- `` `tests/test_sprint3_pipeline.py` `` — (Sprint 3) `contiguous_true_runs`, `read_processed_npz`, `load_candidates_config`, sentetik uçtan-uca zincir testleri (21 test).
- `` `tests/test_sprint3_real_integration.py` `` — (Sprint 3) gerçek dosya üzerinde dewow + band-pass entegrasyon testi; dosya yoksa skip.
- `` `tests/test_sprint3_1_decision_qc.py` `` — (Sprint 3.1) spatial coherence/phase metrics/band energy/decision QC testleri (23 test).
- `` `tests/test_sprint3_canonical.py` `` / `` `tests/test_cli_sprint3_canonical.py` `` — (Sprint 3 Canonicalization) D2+B1 canonical zinciri + CLI testleri (15+7 test).
- `` `tests/test_background.py` `` — (Sprint 4A) `remove_background()` sentetik testleri: core algoritma, pencere/geometri, edge/mask, processing-history, synthetic bilimsel-risk testleri (44 test).
- `` `tests/test_background_qc.py` `` — (Sprint 4A) sinyal-koruma/removed-component metrikleri, `compute_localized_event_risk()`, QC plotting suite testleri (11 test).
- `` `tests/test_sprint4a_pipeline.py` `` — (Sprint 4A) sentetik uçtan-uca zincir (time-zero→...→background removal) + `run_all_sprint4a_candidates()` sentetik uçtan-uca testleri (3 test).
- `` `tests/test_sprint4a_real_integration.py` `` — (Sprint 4A) gerçek canonical Sprint 3 NPZ'si üzerinde background removal + 8-aday orkestrasyonu entegrasyon testi; dosya yoksa skip (2 test).

## `scripts/`

- `` `scripts/validate_obsidian_vault.py` `` — bu Obsidian vault'u için wikilink/orphan-note/binary-dosya kontrol scripti (bu vault'un dışında, ayrı olarak yazılmıştır).
- `` `scripts/generate_sprint2_1_review_comparison.py` `` — (Sprint 2.1) `target_sample` 0 vs 16 karşılaştırma orkestrasyonu.
- `` `scripts/generate_sprint2_2_validation.py` `` — (Sprint 2.2) target-invariance + DC window doğrulama orkestrasyonu.
- `` `scripts/generate_sprint3_1_decision_qc.py` `` — (Sprint 3.1) D2 doğrulama + B1/B2 karar QC orkestrasyonu.

## `obsidian/ArchaeoGPR_Vault/`

- `` `attachments/` `` — bu vault içindeki ek dosyalar için ayrılmış klasör. **Şu an hiçbir ikili (binary) dosya içermiyor** ve kasıtlı olarak boş tutulur; büyük/ikili QC çıktıları asla vault'a kopyalanmaz, sadece `outputs/` altındaki gerçek konumlarına yol olarak referans verilir. Tam kural ve gerekçe için bkz. [[README]] (`attachments/README.md`).

## İlgili Notlar

- [[Architecture_Overview]] — bu dosyaların genel veri akışındaki rolü.
