---
type: architecture
---

# Processing Pipeline Architecture

## Amaç

Bu not, sinyal işleme hattının mimari sözleşmesini (contract) tanımlar.
Sprint 2-4A itibarıyla bu sözleşme beş modül için (time-zero, DC offset,
dewow, band-pass, background removal) gerçek kodla karşılanmıştır; kalan
beş planlanan modül için hâlâ yalnızca bu sözleşmenin kendisi geçerlidir,
gerçek kod yoktur.

> **Güncel durum (Sprint 4A):** `time-zero correction`, `DC offset`,
> `dewow`, `bandpass`, `background removal` — beşi de implemente edildi
> (bkz. [[05_PROCESSING/Processing_Index]]). Background removal, 8 aday
> olarak implemente edildi — **hiçbiri canonical değil** (bkz.
> [[06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy]]).
> `gain, AGC, F-K filtering, migration, Hilbert envelope, depth slices`
> için hâlâ ne gerçek ne de placeholder/sahte-çalışan bir implementasyon
> yoktur.

## Planlanan Sözleşme: `GPRDataset -> GPRDataset`

Gelecekteki her işleme fonksiyonu şu sözleşmeye uymalıdır:

- Girdi olarak bir `GPRDataset` alır, çıktı olarak **yeni** bir `GPRDataset` döndürür.
- Girdi nesnesini **hiçbir zaman yerinde değiştirmez** (`GPRDataset` zaten değişmez olduğu için bu zaten dil seviyesinde de garantidir — bkz. [[Data_Model]]).
- Uyguladığı adımı, kullandığı parametreleri ve ürettiği uyarıları `dataset.with_processing_step(record)` çağrısıyla `processing_history`'ye ekler; bu şekilde çıktı dataset'i, kendisine nasıl ulaşıldığının tam kaydını taşır.

Kavramsal şablon (henüz kod değildir, sadece planlanan şekildir):

```
def some_future_step(dataset: GPRDataset, *, param1=..., param2=...) -> GPRDataset:
    # 1. dataset.amplitudes üzerinde salt okunur işlem yap, yeni bir dizi üret
    # 2. yeni diziden yeni bir GPRDataset kur (veya dataclasses.replace kullan)
    # 3. record = {"step": "some_future_step", "params": {...}, "warnings": [...]}
    # 4. return new_dataset.with_processing_step(record)
```

## CLAUDE.md Kurallarının Bu Sözleşmedeki Karşılığı

- "Every processing function must preserve input data" → girdi `GPRDataset` asla mutasyona uğramaz, her adım yeni bir nesne üretir.
- "Every future processing operation must record parameters and warnings" → `processing_history`'ye eklenen `record` sözlüğü bunun mekanizmasıdır.
- "Every filter must be optional" ve "Every filter must expose the removed or difference component for QC" → bu mimari not seviyesinde bir kısıtlama değil, her modülün kendi notunda (`## Risks`, `## Required QC`) ayrıca ele alınır; bkz. [[Processing_Index]].

## Planlanan Modüller ve Sıra

On (10) planlanan işleme modülü ve bunların çalıştırılma sırası [[Processing_Order]] notunda tanımlıdır. Her modülün amacı, matematiksel temeli, riskleri ve kabul kriterleri kendi notunda ayrı ayrı belgelenmiştir — tam liste için [[Processing_Index]]'e bakın.

## İlgili Notlar

- [[Processing_Index]] — tüm planlanan işleme modüllerinin indeksi.
- [[Processing_Order]] — planlanan çalıştırma sırası ve sıralama kısıtları (örn. gain'in diğer filtrelerden önce uygulanmaması).
- [[Data_Model]] — `GPRDataset.with_processing_step()` ve değişmezlik garantilerinin tam tanımı.
