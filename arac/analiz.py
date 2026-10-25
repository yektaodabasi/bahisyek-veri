#!/usr/bin/env python3
"""İddaa hata haritası: kaydedilen maç öncesi son İddaa oranları × Pinnacle'ın maç öncesi son (marjsız) fiyatı × sonuç.
Her seçim için değer = İddaa oranı × Pinnacle olasılığı (1'in üstü: İddaa Pinnacle'a göre fazla ödüyor).
Lig × pazar ve pazar bazında: seçim sayısı, ortalama değer, gerçekleşen getiri (1 ₺ tekli), Pinnacle kalibrasyonu.
Uygulama yalnız yeterli örnekli grupları kullanır (n ≥ 150).
Girdi: cikti/kayit/<gün>.json, cikti/kayit/pin_<gün>.json, cikti/gunluk/<gün>.json. Çıktı: cikti/analiz.json
"""
import json, glob, os, sys, math, datetime, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eslestirme import benzerlik
from takip import toplam, ayir, poisson, marjsiz, BITTI

PAZAR_GRUP = {"MS1": "MS", "MSX": "MS", "MS2": "MS", "ÇŞ1X": "ÇŞ", "ÇŞ12": "ÇŞ", "ÇŞX2": "ÇŞ",
              "1.5A": "1,5 A/Ü", "1.5U": "1,5 A/Ü", "2.5A": "2,5 A/Ü", "2.5U": "2,5 A/Ü", "3.5A": "3,5 A/Ü", "3.5U": "3,5 A/Ü", "KGV": "KG", "KGY": "KG"}


def iddaa_oranlar(o):
    r = {}
    def al(ad, i):
        l = o.get(ad)
        return l[i] if l and i < len(l) and l[i] and l[i] > 1 else None
    for i, k in enumerate(["MS1", "MSX", "MS2"]): r[k] = al("MS", i)
    for i, k in enumerate(["ÇŞ1X", "ÇŞ12", "ÇŞX2"]): r[k] = al("CS", i)
    for c in ("1.5", "2.5", "3.5"): r[f"{c}A"] = al(f"AU{c}", 0); r[f"{c}U"] = al(f"AU{c}", 1)
    r["KGV"] = al("KG", 0); r["KGY"] = al("KG", 1)
    return {k: v for k, v in r.items() if v}


def pinnacle_olasilik(e):
    """Pinnacle (yoksa konsensüs) 1X2 + toplam gol çizgilerinden pazar olasılıkları"""
    q = marjsiz(e.get("pin")) if e.get("pin") else e.get("kons")
    if not q: return {}
    p = {"MS1": q[0], "MSX": q[1], "MS2": q[2], "ÇŞ1X": q[0] + q[1], "ÇŞ12": q[0] + q[2], "ÇŞX2": q[1] + q[2]}
    c = e.get("cizgiler") or {}
    for cz in ("1.5", "2.5", "3.5"):
        if cz in c and len(c[cz]) >= 2:
            u = marjsiz(c[cz])
            if u: p[f"{cz}U"], p[f"{cz}A"] = u[0], u[1]
    if "2.5U" in p:
        t = toplam(p["2.5U"], 2.5); lm = ayir(t, q[0], q[2]) if t else None
        if lm:
            lam, mu = lm
            pe = [poisson(lam, k) for k in range(11)]; pd = [poisson(mu, k) for k in range(11)]
            kg = (1 - pe[0]) * (1 - pd[0])
            p["KGV"], p["KGY"] = kg, 1 - kg
            for cz, k in (("1.5", 1), ("3.5", 3)):
                if f"{cz}U" not in p:
                    alt = sum(pe[i] * pd[j] for i in range(11) for j in range(11) if i + j <= k)
                    p[f"{cz}A"], p[f"{cz}U"] = alt, 1 - alt
    return p


def sonuc(pz, e, d):
    t = e + d
    return {"MS1": e > d, "MSX": e == d, "MS2": e < d, "ÇŞ1X": e >= d, "ÇŞ12": e != d, "ÇŞX2": e <= d,
            "1.5U": t > 1, "1.5A": t <= 1, "2.5U": t > 2, "2.5A": t <= 2, "3.5U": t > 3, "3.5A": t <= 3,
            "KGV": e > 0 and d > 0, "KGY": not (e > 0 and d > 0)}[pz]


def main():
    k = "cikti"
    # Nesine kayıtları: aynı maç birden çok günde görünebilir → en son görülen (s) kayıt
    nes = {}
    for yol in sorted(glob.glob(f"{k}/kayit/2*.json")):
        try: j = json.load(open(yol, encoding="utf-8"))
        except Exception: continue
        for n in j.get("nesine", []):
            if not n.get("t"): continue
            eski = nes.get(n["c"])
            if eski is None or (n.get("s") or 0) >= (eski.get("s") or 0): nes[n["c"]] = n
    pin = {}
    for yol in glob.glob(f"{k}/kayit/pin_*.json"):
        try: pin.update(json.load(open(yol, encoding="utf-8")))
        except Exception: pass
    pin_l = list(pin.values())
    sonuclar = {}
    for yol in sorted(glob.glob(f"{k}/gunluk/*.json")):
        try:
            for r in json.load(open(yol, encoding="utf-8")): sonuclar[r[1]] = r
        except Exception: pass
    biten = [r for r in sonuclar.values() if r[0] in BITTI and r[10] is not None and r[11] is not None]
    # Zaman dizinli eşleştirme
    by_t = collections.defaultdict(list)
    for r in biten: by_t[int(r[3] // 3_600_000)].append(r)
    pin_t = collections.defaultdict(list)
    for e in pin_l: pin_t[int(e["t"] // 3_600_000)].append(e)
    def yakin(d, t):
        h = int(t // 3_600_000); return [x for hh in range(h - 3, h + 4) for x in d.get(hh, [])]
    gruplar = collections.defaultdict(lambda: {"n": 0, "deger": 0.0, "getiri": 0.0, "tuttu": 0, "pinP": 0.0})
    eslesen = 0
    for n in nes.values():
        if n.get("s") and n["s"] > n["t"]: continue  # güvenlik: maç sonrası görüntü
        # sonuç
        en = None
        for r in yakin(by_t, n["t"]):
            sc = (benzerlik(n["ev"], r[5]) + benzerlik(n["dep"], r[8])) / 2
            if sc >= 0.6 and (en is None or sc > en[1]): en = (r, sc)
        if not en: continue
        r = en[0]
        # Pinnacle
        ep = None
        for e in yakin(pin_t, n["t"]):
            sc = (benzerlik(n["ev"], e["ev"]) + benzerlik(n["dep"], e["dep"])) / 2
            if sc >= 0.55 and (ep is None or sc > ep[1]): ep = (e, sc)
        if not ep: continue
        q = pinnacle_olasilik(ep[0])
        io = iddaa_oranlar(n.get("o") or {})
        if not q or not io: continue
        eslesen += 1
        lig = r[2]
        for pz, o in io.items():
            if pz not in q: continue
            y = sonuc(pz, r[10], r[11]); v = o * q[pz]
            for anahtar in ((lig, PAZAR_GRUP[pz]), ("*", PAZAR_GRUP[pz]), ("*", "*"), ("*", f"değer {'≥1,00' if v >= 1 else '0,95–1,00' if v >= 0.95 else '0,90–0,95' if v >= 0.9 else '<0,90'}")):
                g = gruplar[anahtar]
                g["n"] += 1; g["deger"] += v; g["getiri"] += o if y else 0.0; g["tuttu"] += y; g["pinP"] += q[pz]
    liste = []
    for (lig, pg), g in gruplar.items():
        nn = g["n"]
        liste.append({"lig": lig, "pazar": pg, "n": nn, "ortDeger": round(g["deger"] / nn, 4), "getiri": round(g["getiri"] / nn, 4),
                      "isabet": round(g["tuttu"] / nn, 4), "pinnacleOrt": round(g["pinP"] / nn, 4)})
    liste.sort(key=lambda x: (-x["n"]))
    cikti = {"uretim": int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000), "mac": eslesen, "gruplar": liste,
             "not": "ortDeger: İddaa oranı × Pinnacle olasılığı ortalaması (1 üstü İddaa fazla ödüyor). getiri: 1 ₺ tekli ortalama dönüş. Güvenilirlik için n ≥ 150."}
    json.dump(cikti, open(f"{k}/analiz.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    genel = next((x for x in liste if x["lig"] == "*" and x["pazar"] == "*"), None)
    print(f"::notice title=İddaa hata haritası::{eslesen} maç · {genel['n'] if genel else 0} seçim · ort. değer {genel['ortDeger'] if genel else '-'} · getiri {genel['getiri'] if genel else '-'}")


if __name__ == "__main__":
    main()
