#!/usr/bin/env python3
"""Yüksek oran takibi (sunucu): her gün İY/MS dönüşleri (1/2, 2/1) ve 6+ gol için en olası seçimleri kilitler,
maçlar bitince puanlar; kümülatif özet yazar. BahisYek'in Dönüş avcısı / Gol yağmuru hesabının Python kopyası.

Kilit: İstanbul saatiyle 08:00'den sonraki ilk çalışmada (dosya yoksa), 30 dk'dan sonra başlayacak maçlar arasından.
Kaynak önceliği: Pinnacle (1X2 + gol çizgileri) → DraftKings (ESPN) → İddaa'nın kendi oranları.
Kalibrasyon (2.716 geçmiş maç): 1/2 ×1,27, 2/1 ×0,91, 6+ ×0,90.

Kullanım: takip.py <eski veri klasörü>   (çalışma dizininde kayit/, cikti/ hazır olmalı)
Çıktı: cikti/takip/<gün>.json, cikti/takip/ozet.json
"""
import json, os, sys, math, datetime, glob, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eslestirme import benzerlik

IST = datetime.timezone(datetime.timedelta(hours=3))
BITTI = {"STATUS_FULL_TIME", "STATUS_FINAL", "STATUS_FINAL_PEN", "STATUS_FINAL_AET"}
K12, K21, K6, ILK_YARI = 1.27, 0.91, 0.90, 0.44
N = 25
LF = [0.0]
for i in range(1, N + 1): LF.append(LF[-1] + math.log(i))
IYMS = ["1/1", "1/X", "1/2", "X/1", "X/X", "X/2", "2/1", "2/X", "2/2"]


def poisson(l, k): return math.exp(-l + k * math.log(l) - LF[k]) if l > 0 else (1.0 if k == 0 else 0.0)


def skellam(l, m):
    px = [poisson(l, k) for k in range(N + 1)]; py = [poisson(m, k) for k in range(N + 1)]
    s = [0.0] * (2 * N + 1)
    for x in range(N + 1):
        for y in range(N + 1): s[x - y + N] += px[x] * py[y]
    return s


def toplam(pu, cizgi):
    k = math.floor(cizgi)
    f = lambda t: (1 - sum(poisson(t, i) for i in range(k + 1))) - pu
    lo, hi = 0.2, 9.0
    if f(lo) > 0 or f(hi) < 0: return None
    for _ in range(50):
        m = (lo + hi) / 2
        if f(m) < 0: lo = m
        else: hi = m
    return (lo + hi) / 2


def ayir(t, p1, p2):
    hedef = p1 - p2
    def f(d):
        s = skellam((t + d) / 2, (t - d) / 2)
        return sum(s[N + i] - s[N - i] for i in range(1, N + 1)) - hedef
    lo, hi = -t + 0.02, t - 0.02
    if f(lo) > 0 or f(hi) < 0: return None
    for _ in range(40):
        m = (lo + hi) / 2
        if f(m) < 0: lo = m
        else: hi = m
    d = (lo + hi) / 2
    return (t + d) / 2, (t - d) / 2


def donus(lam, mu, s=ILK_YARI):
    h = skellam(s * lam, s * mu); g = skellam((1 - s) * lam, (1 - s) * mu)
    alt = []; a = 0.0
    for x in g: a += x; alt.append(a)
    p12 = sum(h[d + N] * alt[-d - 1 + N] for d in range(1, N))
    p21 = sum(h[-d + N] * (1 - alt[d + N]) for d in range(1, N))
    onde_ev = sum(h[d + N] for d in range(1, N + 1)); onde_dep = sum(h[-d + N] for d in range(1, N + 1))
    return p12 * K12, p21 * K21, onde_ev, onde_dep


def p6(t): return (1 - sum(poisson(t, k) for k in range(6))) * K6


def marjsiz(o):
    if not o or any((x is None or x <= 1) for x in o): return None
    s = sum(1 / x for x in o); return [1 / x / s for x in o]


def amerikan(o):
    try: v = float(str(o).replace("+", ""))
    except (TypeError, ValueError): return None
    if v == 0: return None
    return 1 + v / 100 if v > 0 else 1 + 100 / (-v)


def ms(s):
    for f in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ"):
        try: return datetime.datetime.strptime(s, f).replace(tzinfo=datetime.timezone.utc).timestamp() * 1000
        except (ValueError, TypeError): pass
    return None


def oku(yol, varsayilan=None):
    try: return json.load(open(yol, encoding="utf-8"))
    except Exception: return varsayilan


def eslesen(ad_ev, ad_dep, t, adaylar, ev_k, dep_k, t_k, esik=0.6):
    """adaylar arasında saat ±3 saat ve isim benzerliği en yüksek olan"""
    en = None
    for a in adaylar:
        ta = t_k(a)
        if ta is None or abs(ta - t) > 3 * 3_600_000: continue
        s = (benzerlik(ad_ev, ev_k(a)) + benzerlik(ad_dep, dep_k(a))) / 2
        if s >= esik and (en is None or s > en[1]): en = (a, s)
    return en[0] if en else None


def kilitle(gun, kayit, pin, gunluk_satir, simdi):
    g0 = datetime.datetime.combine(gun, datetime.time(0, 0), IST).timestamp() * 1000; g1 = g0 + 86_400_000
    secim_d, secim_g = [], []
    for n in kayit.get("nesine", []):
        if not (max(g0, simdi + 30 * 60_000) < n["t"] < g1): continue
        if any(x in (n.get("ev") or "") for x in ("(K)", "U19", "U21", "U23")): continue
        o = n.get("o") or {}
        iy = o.get("IYMS"); gg = o.get("G")
        if not iy and not gg: continue
        # ESPN maçı (sonuç için şart)
        e = eslesen(n["ev"], n["dep"], n["t"], gunluk_satir, lambda r: r[5], lambda r: r[8], lambda r: r[3])
        if not e: continue
        # Dünya piyasası
        p1 = p2 = pu = None; cizgi = 2.5; kaynak = None; cizgi6 = None; pu6 = None
        k = eslesen(n["ev"], n["dep"], n["t"], pin, lambda x: x["ev"], lambda x: x["dep"], lambda x: x["t"])
        if k:
            q = marjsiz(k.get("pin")) if k.get("pin") else k.get("kons")
            c = k.get("cizgiler") or {}
            if q and "2.5" in c:
                p1, p2 = q[0], q[2]; pu = marjsiz(c["2.5"])[0]; kaynak = "Pinnacle" if k.get("pin") else "Konsensüs"
            yarim = [x for x in c if float(x) % 1 == 0.5]
            if yarim:
                cz = max(yarim, key=float); cizgi6 = float(cz); pu6 = marjsiz(c[cz])[0]
        if kaynak is None:
            d = next((d for d in kayit.get("dk", []) if d.get("id") == e[1]), None)
            if d and d.get("au") is not None and float(d["au"]) % 1 == 0.5:
                q = marjsiz([amerikan(d.get("o1")), amerikan(d.get("ox")), amerikan(d.get("o2"))])
                u = marjsiz([amerikan(d.get("ust")), amerikan(d.get("alt"))])
                if q and u:
                    p1, p2, pu = q[0], q[2], u[0]; cizgi = float(d["au"]); kaynak = "DraftKings"
                    if cizgi6 is None: cizgi6, pu6 = cizgi, pu
        if kaynak is None:
            q = marjsiz(o.get("MS")); a = o.get("AU2.5")
            u = marjsiz([a[1], a[0]]) if a and len(a) == 2 else None
            if q and u: p1, p2, pu = q[0], q[2], u[0]; kaynak = "İddaa"
        if kaynak is None: continue
        t = toplam(pu, cizgi)
        if t is None: continue
        lm = ayir(t, p1, p2)
        if not lm: continue
        saat = datetime.datetime.fromtimestamp(n["t"] / 1000, IST).strftime("%H:%M")
        temel = {"id": e[1], "nesine": n["c"], "mac": f"{n['ev']} – {n['dep']}", "lig": n.get("lig"), "t": n["t"], "saat": saat, "kaynak": kaynak}
        if iy and len(iy) == 9:
            a12, a21, oe, od = donus(*lm)
            pz, p, oran = ("1/2", a12, iy[2]) if a12 >= a21 else ("2/1", a21, iy[6])
            secim_d.append({**temel, "pazar": pz, "p": round(p, 4), "oran": oran, "p12": round(a12, 4), "p21": round(a21, 4),
                            "evOnde": round(oe, 3), "depOnde": round(od, 3), "xg": [round(lm[0], 2), round(lm[1], 2)]})
        if gg and len(gg) == 4 and gg[3]:
            if pu6 is not None:
                t6 = toplam(pu6, cizgi6)
            else:
                a35 = o.get("AU3.5"); u35 = marjsiz([a35[1], a35[0]]) if a35 and len(a35) == 2 else None
                t6 = toplam(u35[0], 3.5) if (u35 and kaynak == "İddaa") else t
            if t6:
                secim_g.append({**temel, "pazar": "6+", "p": round(p6(t6), 4), "oran": gg[3], "beklenen": round(t6, 2)})
    secim_d.sort(key=lambda x: (x["kaynak"] == "İddaa", -x["p"])); secim_g.sort(key=lambda x: (x["kaynak"] == "İddaa", -x["p"]))
    return {"gun": gun.isoformat(), "kilit": int(simdi), "kilitSaat": datetime.datetime.fromtimestamp(simdi / 1000, IST).strftime("%Y-%m-%d %H:%M"),
            "donus": secim_d[:8], "gol6": secim_g[:8], "donusTum": len(secim_d), "gol6Tum": len(secim_g)}


def puanla(dosya, sonuclar):
    """Seçimlerin sonucunu doldurur; hepsi bittiyse tamam=True"""
    hepsi = True
    for anahtar in ("donus", "gol6"):
        for s in dosya.get(anahtar, []):
            if s.get("sonuc") is not None: continue
            r = sonuclar.get(s["id"])
            if not r or r[0] not in BITTI or r[10] is None or r[11] is None:
                if r and r[0] in ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_ABANDONED"): s["sonuc"] = "iptal"; continue
                hepsi = False; continue
            e, d, ie, idp = r[10], r[11], r[12], r[13]
            s["skor"] = f"{e}-{d}" + (f" (İY {ie}-{idp})" if ie is not None and idp is not None else "")
            if anahtar == "gol6":
                s["sonuc"] = (e + d) >= 6
            else:
                if ie is None or idp is None: s["sonuc"] = "veri yok"; continue
                s["sonuc"] = (ie > idp and e < d) if s["pazar"] == "1/2" else (ie < idp and e > d)
    dosya["tamam"] = hepsi
    return dosya


def ozet(klasor):
    o = {"donus": {"secim": 0, "tuttu": 0, "oranli": 0, "getiri": 0.0, "beklenen": 0.0}, "gol6": {"secim": 0, "tuttu": 0, "oranli": 0, "getiri": 0.0, "beklenen": 0.0}, "gunler": []}
    for yol in sorted(glob.glob(f"{klasor}/2*.json")):
        f = oku(yol, {})
        satir = {"gun": f.get("gun")}
        for k in ("donus", "gol6"):
            sec = [s for s in f.get(k, []) if isinstance(s.get("sonuc"), bool)]
            t = sum(1 for s in sec if s["sonuc"]); g = sum(s["oran"] for s in sec if s["sonuc"] and s.get("oran"))
            o[k]["secim"] += len(sec); o[k]["tuttu"] += t; o[k]["getiri"] += g; o[k]["oranli"] += sum(1 for s in sec if s.get("oran"))
            o[k]["beklenen"] += sum(s["p"] for s in sec)
            satir[k] = {"secim": len(sec), "tuttu": t, "bekleyen": sum(1 for s in f.get(k, []) if s.get("sonuc") is None), "getiri": round(g / len(sec), 3) if sec else None}
        o["gunler"].append(satir)
    for k in ("donus", "gol6"):
        x = o[k]; x["birTLgetiri"] = round(x["getiri"] / x["oranli"], 3) if x["oranli"] else None; x["beklenen"] = round(x["beklenen"], 2); x["getiri"] = round(x["getiri"], 2)
    o["uretim"] = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    return o


def main():
    eski = sys.argv[1] if len(sys.argv) > 1 else "eski"
    os.makedirs("cikti/takip", exist_ok=True)
    if os.path.isdir(f"{eski}/takip"):
        for yol in glob.glob(f"{eski}/takip/*.json"):
            hedef = f"cikti/takip/{os.path.basename(yol)}"
            if not os.path.exists(hedef): shutil.copy(yol, hedef)
    simdi = datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000
    bugun = datetime.datetime.now(IST).date()
    # Sonuçlar: son 3 günün günlük dosyaları (yeni olan eskiyi ezer)
    sonuclar = {}
    for yol in sorted(glob.glob("cikti/gunluk/*.json"))[-4:]:
        for r in oku(yol, []): sonuclar[r[1]] = r
    # Kilit
    hedef = f"cikti/takip/{bugun.isoformat()}.json"
    if not os.path.exists(hedef) and datetime.datetime.now(IST).hour >= 8:
        kayit = oku(f"kayit/{bugun.isoformat()}.json") or oku(f"cikti/kayit/{bugun.isoformat()}.json") or {}
        pin = (oku("cikti/oranlar.json") or oku(f"{eski}/oranlar.json") or {}).get("olaylar", [])
        gun_satir = [r for r in sonuclar.values() if r[0] == "STATUS_SCHEDULED"]
        if kayit.get("nesine"):
            d = kilitle(bugun, kayit, pin, gun_satir, simdi)
            json.dump(d, open(hedef, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"kilitlendi {bugun}: dönüş {len(d['donus'])}/{d['donusTum']} · 6+ {len(d['gol6'])}/{d['gol6Tum']}")
    # Puanla (tamamlanmamış dosyalar)
    for yol in sorted(glob.glob("cikti/takip/2*.json")):
        f = oku(yol, {})
        if f.get("tamam"): continue
        f = puanla(f, sonuclar)
        json.dump(f, open(yol, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    oz = ozet("cikti/takip")
    json.dump(oz, open("cikti/takip/ozet.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    d, g = oz["donus"], oz["gol6"]
    print(f"::notice title=Yüksek oran takibi::Dönüş {d['tuttu']}/{d['secim']} (beklenen {d['beklenen']}) 1₺→{d['birTLgetiri']} · 6+ {g['tuttu']}/{g['secim']} (beklenen {g['beklenen']}) 1₺→{g['birTLgetiri']}")


if __name__ == "__main__":
    main()
