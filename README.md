# BahisYek veri paketi

Avrupa liglerinin (ön elemeler dahil) iki sezonluk biten maçları ve dünya piyasası kapanış oranları, 6 saatte bir
GitHub Actions ile ESPN'in açık skor servisinden derlenir. BahisYek uygulaması `paket.json.gz` dosyasını indirir.

- `paket.json.gz` — `{"surum":1,"uretim":ms,"alanlar":[...],"maclar":[[id, lig, zaman, evId, ev, evKisa, depId, dep, depKisa, evGol, depGol, iyEv, iyDep, notr, dk1, dkX, dk2, cizgi, ust, alt], ...]}`
- `paket_bilgi.json` — lig başına maç sayısı
- `kayit/<tarih>.json` — günün Nesine ana pazar oranları, DK oranları, Nesine yorumcu seçimleri (kalibrasyon için)
- `gunluk/<tarih>.json` — dün/bugün biten maçlar

Kod: `arac/` (asıl geliştirme `hava` deposundaki BahisYek/yoklama altında).
