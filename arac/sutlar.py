#!/usr/bin/env python3
"""Şut verisi (isabetli şut ≈ xG): üst liglerin biten maçları için ESPN maç özetinden şut / isabetli şut.
Önceki dosyanın üstüne eksikleri tamamlar (tur başına en çok SINIR maç). Model gücü hesaplarken golle karıştırılır
(ileriye dönük testte 3.043 maçta 1X2 ve 2,5 A/Ü hatası düştü).
Çıktı: cikti/sutlar.json.gz  {maç id: [ev isabetli, dep isabetli, ev şut, dep şut]}
Kullanım: sutlar.py <eski veri klasörü>
"""
import json, gzip, os, sys, subprocess, concurrent.futures, datetime

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
UA = "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36"
LIGLER = {"tur.1", "eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "ned.1", "por.1", "bel.1", "sco.1", "eng.2", "ger.2", "esp.2", "ita.2", "fra.2",
          "uefa.champions", "uefa.europa", "uefa.europa.conf", "gre.1", "aut.1", "sui.1", "den.1"}
BASLANGIC = int(datetime.datetime(2025, 7, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
SINIR = int(os.environ.get("SUT_SINIR", "900"))


def al(url):
    try:
        s = subprocess.run(["curl", "-sS", "-L", "--compressed", "--max-time", "30", "-A", UA, url], capture_output=True, text=True, timeout=40)
        return json.loads(s.stdout) if s.returncode == 0 and s.stdout else None
    except Exception:
        return None


def ozet(lig, mid, ev, dep):
    j = al(f"{ESPN}/{lig}/summary?event={mid}")
    if not j: return None
    st = {}
    for t in (j.get("boxscore") or {}).get("teams", []):
        tid = (t.get("team") or {}).get("id")
        d = {s.get("name"): s.get("displayValue") for s in t.get("statistics", [])}
        try: st[tid] = (int(float(d.get("shotsOnTarget"))), int(float(d.get("totalShots"))))
        except (TypeError, ValueError): pass
    if ev in st and dep in st:
        return [st[ev][0], st[dep][0], st[ev][1], st[dep][1]]
    return None


def main():
    eski = sys.argv[1] if len(sys.argv) > 1 else "eski"
    sut = {}
    yol = os.path.join(eski, "sutlar.json.gz")
    if os.path.exists(yol):
        try: sut = json.load(gzip.open(yol, "rt", encoding="utf-8"))
        except Exception: sut = {}
    p = json.load(gzip.open("cikti/paket.json.gz", "rt", encoding="utf-8")); A = {a: i for i, a in enumerate(p["alanlar"])}
    eksik = [r for r in p["maclar"] if r[A["lig"]] in LIGLER and r[A["zaman"]] >= BASLANGIC and r[A["evGol"]] is not None and r[A["id"]] not in sut]
    eksik.sort(key=lambda r: -r[A["zaman"]])  # önce yeniler
    eksik = eksik[:SINIR]
    yeni = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for r, s in zip(eksik, ex.map(lambda r: ozet(r[A["lig"]], r[A["id"]], r[A["evId"]], r[A["depId"]]), eksik)):
            if s: sut[r[A["id"]]] = s; yeni += 1
            else: sut.setdefault(r[A["id"]], None)  # özet yok: bir daha denenmesin
    paket_id = {r[A["id"]] for r in p["maclar"]}
    sut = {k: v for k, v in sut.items() if k in paket_id}
    with gzip.open("cikti/sutlar.json.gz", "wt", encoding="utf-8") as f: json.dump(sut, f, separators=(",", ":"))
    dolu = sum(1 for v in sut.values() if v)
    print(f"::notice title=Şut verisi::{dolu} maç (bu tur +{yeni}, kalan eksik ~{max(0, len([1 for r in p['maclar'] if r[A['lig']] in LIGLER and r[A['zaman']] >= BASLANGIC and r[A['evGol']] is not None]) - len(sut))})")


if __name__ == "__main__":
    main()
