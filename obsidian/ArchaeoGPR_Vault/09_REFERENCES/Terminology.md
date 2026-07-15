---
type: reference
---

# Terminology

## Amaç

Bu not, proje içinde ve vault'un diğer notlarında sıkça geçen GPR (yer radarı) ve OpenGPR terimlerinin kısa tanımlarını verir. İngilizce terim her zaman kalın (bold) olarak korunur; tanımın kendisi Türkçedir.

## Tanımlar

- **B-scan**: Tek bir kanalın, dilim (x) eksenine karşı örnek/zaman (y) eksenine göre çizildiği iki boyutlu radar görüntüsü. `qc/bscan.py` içindeki `plot_bscan` bu görselleştirmeyi üretir.
- **Slice (dilim)**: Bir survey hattı boyunca kaydedilen tek bir ölçüm konumu/anı. `GPRDataset.amplitudes` dizisinin birinci eksenidir; bu örnek dosyada 175 dilim vardır.
- **Channel (kanal)**: Bir anten array'indeki tek bir alıcı/verici birimi. Bu örnek dosyada 11 kanal vardır; `amplitudes` dizisinin ikinci eksenidir.
- **Sample (örnek)**: Bir izdeki (trace) tek bir zaman-domeni ölçüm noktası. Bu örnek dosyada iz başına 1024 örnek vardır; `amplitudes` dizisinin üçüncü eksenidir.
- **Trace (iz)**: Belirli bir (dilim, kanal) çifti için kaydedilen tam örnek dizisi, yani `amplitudes[slice, channel, :]`.
- **Time-zero (zaman-sıfırı)**: Kaydın, gerçek yer yüzeyine / doğrudan dalga (direct wave) varışına karşılık gelmesi gereken referans zaman noktası. Bkz. [[Time_Zero_Correction]].
- **Dewow**: Bir izdeki çok-düşük-frekanslı sürüklenmeyi ("wow") gidermeyi amaçlayan filtreleme adımı. Bkz. [[Dewow]].
- **Background removal (arka plan çıkarma)**: Tüm izlerde ortak olan yatay bileşenin (kanal başına ortalama iz) çıkarılması. Bkz. [[Background_Removal]].
- **Gain / AGC**: Derinlik/zamanla azalan sinyali telafi eden amplitüd büyütme işlemi. AGC (Automatic Gain Control / Otomatik Kazanç Kontrolü), kayan pencere tabanlı adaptif bir gain türüdür ve göreli genlik bilgisini bozduğu için niceliksel analizde kullanılmamalıdır. Bkz. [[Gain]].
- **F-K filter (F-K filtresi)**: Frekans-dalgasayısı (frequency-wavenumber) domeninde, görünür hız/eğime göre gürültü ayıklayan iki boyutlu filtre. Bkz. [[FK_Filter]].
- **Migration (migrasyon)**: Difraksiyon hiperbollerini gerçek yer altı nokta/yapı konumlarına geri toplayan işlem. Bkz. [[Migration]].
- **Depth slice (derinlik dilimi)**: Zaman-domenindeki radar hacminin bir hız modeliyle derinliğe çevrilip sabit derinlik seviyelerinde kesilmiş hâli. Bkz. [[Depth_Slices]].
- **Propagation velocity (yayılım hızı)**: Elektromanyetik dalganın ortam içindeki hızı. Bu örnek dosyada metadata varsayımı 0.1 m/ns'dir (`propagationVelocity_mPerSec = 100000000.0`) ve ground-truth ile doğrulanmamıştır. Bkz. [[OpenGPR_File_Structure]], [[Velocity_Analysis]].
- **Polarization (polarizasyon)**: Anten tarafından yayılan/alınan elektromanyetik alanın yönelimi. Bu örnek dosyada `"horizontal"`.
- **EPSG / CRS**: EPSG, coğrafi koordinat referans sistemlerini (CRS — Coordinate Reference System) numaralandıran bir kayıt sistemidir. Bu örnek dosyada header'da `EPSG:32632` saklanır; bu değerin doğruluğu **doğrulanmamıştır** — bkz. [[OpenGPR_File_Structure]].
- **OpenGPR**: IDS GeoRadar sistemlerinin ürettiği `.ogpr` ikili/JSON melez dosya formatının adı; bu projenin okuduğu tek format.
- **Swath**: Bir survey oturumunda kaydedilen tek bir hat/geçiş. Bu örnek dosyada `swathName = "Swath003"`.
- **Array**: Birden fazla kanalı barındıran fiziksel anten dizisi. Bu örnek dosyada `arrayId = 2` (dosya adında `02` olarak gösterilir).

## İlgili Notlar

- [[Reference_Index]]
- [[OpenGPR_File_Structure]]
