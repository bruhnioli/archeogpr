---
type: project-state
tags: [project-state, risk]
---

# GUI/3D Risk Register

Bu liste, GUI/3D dönüşümünün (Sprint GUI-0'dan itibaren) bilinen risk ve
açık kararlarını kaydeder — [[04_Risks_and_Limitations]]'ın GUI/3D'ye
özel eki. Kod (henüz yazılmadığı için) bu risklerin hiçbirini şu an
çözmüyor; bu liste, implementasyon başladığında (GUI-1'den itibaren)
hangi tasarım kararlarının bu riskleri karşılayacağını izler.

## Bellek/Performans

### R1 — State yığını + 3D grid bellek büyümesi
Tek swath küçük (~7.9 MB) ama undo/redo state yığını + her adımın
`removed_component`'i + 3D grid ile çarpan büyür. Azaltma: `SessionState`
için `max_states`/`max_bytes` sınırı; 3D öncesi bellek tahmini
kullanıcıya gösterilir (bkz. [[03_ARCHITECTURE/3D_Volume_Data_Model]]).
Durum: tasarlandı, implemente edilmedi (GUI-3/3D-1).

### R2 — PyVista/VTK paket boyutu ve soğuk başlatma
`gui3d` opsiyonel grubu (~150+ MB, VTK dahil) yalnızca 3D görünüm
açıldığında lazy-import edilecek — 2D-only kurulum etkilenmemeli.
Durum: mimaride karar verildi
([[06_DECISIONS/ADR_011_GUI_Technology_Decision]]), implementasyonda
doğrulanacak (Sprint 3D-2).

### R3 — Repository OneDrive altında senkronize ediliyor
Proje kökü `C:\Users\baran\OneDrive\Desktop\School Stuff\Staj 2026\`
altında. Qt/VTK çalışırken OneDrive dosya kilitleri/senkron çakışması
yaşanabilir. Öneri: en azından `outputs/`, `.venv/` için OneDrive
dışı çalışma veya klasör-bazlı "always keep offline"/senkron istisnası.
Durum: **açık, kullanıcı kararı bekliyor** — henüz hiçbir işlem
yapılmadı.

### R4 — Büyük gelecek dosyalarda render performansı
PyQtGraph mevcut boyutlar için (≤175×1024/kanal) sorunsuz olmalı; çok
kanallı/çok-swath birleşimlerde downsample'lı render modu gerekebilir.
Durum: tasarım notu (bkz. [[03_ARCHITECTURE/GUI_Architecture]]),
implementasyon yalnızca gerekirse eklenecek.

## Bilimsel/Doğruluk

### R5 — Derinlik her yerde varsayım-hız tahminidir
ISSUE-004 (bkz. [[03_Open_Issues]]) devam ediyor. GUI hiçbir depth
ekseni/hacmi üretmeden önce kullanıcıdan açık hız onayı ister; varsayılan
metadata hızı (0.1 m/ns) yalnızca *öneri* olarak gösterilir. Durum:
tasarlandı ([[03_ARCHITECTURE/GUI_Architecture]],
[[03_ARCHITECTURE/3D_Volume_Data_Model]]), implemente edilmedi.

### R6 — EPSG:32632 doğrulanmamış (ISSUE-001)
3D grid **yerel** koordinatta kurulacak (origin çıkarma + PCA); CRS
"as stored, not validated" etiketiyle taşınır, hiçbir reprojection
yapılmaz. Durum: tasarlandı, implemente edilmedi.

### R7 — Canonical D2+B1 ve A0 kararları yalnızca bu dataset'e kapsamlı
GUI, recipe'lere dataset-scope etiketi ekleyecek — bir recipe'nin başka
bir dosyaya "canonical" diye sessizce uygulanmasını önlemek için. Durum:
tasarım aşamasında not edildi
([[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]]), implemente edilmedi.

### R8 — Background removal'ın hedef-yıkma riski (ADR-008/009)
GUI'de bu işlem her uygulandığında kalıcı bir uyarı gösterilecek
(preview panelinde ve history kaydında). Durum: tasarım niyeti,
implemente edilmedi.

## Lisans/Provenance

### R9 — GPRPy'den kod alınması ihtimali
Şu ana kadar hiçbir kod kopyalanmadı (bkz.
[[09_REFERENCES/GPRPy_Reference_and_License_Notes]]). Eğer ileride bir kod parçası
uyarlanırsa, **kullanıcının önceden ayrıca onayı** gerekir (Sprint GUI-0
talimatı madde 7) ve kaynak/orijinal fonksiyon/değişiklik/MIT bildirimi
dokümante edilmelidir. Durum: politika kayıt altına alındı, ihlal yok.

### R10 — CREWES/irlib fk-migration kodu
Hiçbir koşulda kullanılmayacak (kullanıcı talimatı, madde 8). Migration
implemente edilirse bağımsız, literatür-tabanlı bir implementasyon
yazılacak. Durum: politika kayıt altına alındı, migration henüz
başlamadı.

## Süreç

### R11 — Commit edilmemiş Sprint 4B gain kodu ile vault kaydı çelişkisi
`configs/gain_candidates.yaml`, `src/archaeogpr/{export/sprint4b.py,
processing/gain.py, qc/gain.py, sprint4b_candidates.py}` untracked halde
`sprint-04b-gain-candidates` branch'inde duruyor; testsiz, CLI'siz,
henüz var olmayan bir ADR-010'a atıfla. Sprint GUI-0 kapsamında bu
dosyalar **değiştirilmedi, GUI'ye bağlanmadı** — yalnızca hash
doğrulamalı bir yedeği alındı (bkz.
[[02_SPRINTS/Sprint_GUI_0_Foundation]] Issues Discovered). **Somut, ölçülmüş etki:**
bu untracked dosyaların ana çalışma ağacında fiziksel olarak var olması,
committed bir regresyon testini (`tests/test_sprint4a_candidates.py::
test_gain_module_does_not_exist_and_report_confirms_gain_not_started`)
kırıyor — `pytest` ana ağaçta **343 passed, 1 failed** veriyor
(committed HEAD'in kendisi, bağımsız `git worktree` doğrulamasıyla, hâlâ
0 failed). Bkz. [[02_SPRINTS/Sprint_GUI_0_Foundation]] Issues Discovered
#3. Durum: **açık, kullanıcı kararı bekliyor** — bkz. aşağıdaki "Onay
bekleyen kararlar".

### R12 — GUI-0/GUI-1 hangi branch üzerinde ilerleyecek
Repository şu an `main` üzerinde değil, `sprint-04b-gain-candidates`
branch'inde. Sprint GUI-0'ın dosya değişiklikleri (bu belgeler +
`pyproject.toml` + `README.md`) bu branch'in çalışma ağacına yazıldı,
**hiçbir commit atılmadı**. Durum: **açık, kullanıcı kararı bekliyor**.

## Onay Bekleyen Kararlar (özet)

1. Sprint 4B gain WIP dosyaları için: (a) ayrı `sprint4b-gain-wip`
   branch'inde commit edilsin, (b) mevcut `sprint-04b-gain-candidates`
   branch'inde olduğu gibi commit edilmeden bırakılsın, (c) başka bir
   işlem. Ayrıca bunun kırdığı `test_gain_module_does_not_exist_and_
   report_confirms_gain_not_started` testi için: gain dosyaları geçici
   olarak çalışma ağacından çıkarılana kadar test kırık kalsın (mevcut
   durum), yoksa test Sprint 4B'nin kendi kapsamında mı güncellenecek —
   bu sprintin (GUI-0) kararı değil. Bkz. R11.
2. Sprint GUI-0'ın dosya değişiklikleri hangi branch'te kalacak/commit
   edilecek — mevcut `sprint-04b-gain-candidates` mı, `main` mı, yeni bir
   `gui-0`/`gui-foundation` branch'i mi. Bkz. R12.
3. OneDrive altında Qt/VTK geliştirme için özel bir önlem alınacak mı
   (R3).

## İlgili Notlar

- [[04_Risks_and_Limitations]]
- [[03_Open_Issues]]
- [[03_ARCHITECTURE/GUI_Architecture]]
- [[03_ARCHITECTURE/3D_Volume_Data_Model]]
- [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]]
- [[06_DECISIONS/ADR_011_GUI_Technology_Decision]]
- [[09_REFERENCES/GPRPy_Reference_and_License_Notes]]
- [[02_SPRINTS/Sprint_GUI_0_Foundation]]
