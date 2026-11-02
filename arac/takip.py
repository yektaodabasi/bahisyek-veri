#!/usr/bin/env python3
"""Yüksek oran takibi (sunucu): her gün İY/MS kombinasyonları ve 6+ gol için günün listesini kilitler, maçlar bitince puanlar;
kümülatif özet yazar. BahisYek'in Dönüş avcısı / Gol yağmuru hesabının Python kopyası.

Günün listesi: 4 dönüş (1/2 ya da 2/1, maç başına olası olan) + 4 beraberlikli (X/1, X/2, 1/X, 2/X; İddaa oranı ≥ 3,5, maç başına
olası olan) ve 8 adet 6+ gol; her listede "en iyi 3" = olasılık × oran en yüksek olanlar (ilk3 işareti).
Kilit: İstanbul saatiyle 08:00'den sonraki ilk çalışmada (dosya yoksa), 30 dk'dan sonra başlayacak maçlar arasından.
Kaynak önceliği: Pinnacle (1X2 + gol çizgileri) → DraftKings (ESPN) → İddaa'nın kendi oranları.
Kalibrasyon (2.716 geçmiş maç, DK kapanış + İY skoru, üst çeyrek ağırlıklı): 1/2 ×1,15, 2/1 ×0,85, X/1 ×0,95, X/2 ×0,97, 1/X ×1,0,
2/X ×1,15; 6+ ×0,90. Canlı düzeltme: listelerin gerçekleşen / ham beklenen oranı, n/(n+600) ile 1'e çekilmiş, [0,8; 1,25]
(ozet.json "kalibrasyon"); kilitte olasılıklar bununla çarpılır ve kullanılan değer dosyaya yazılır (kCanli), özet ham beklenene bakar.

Kullanım: takip.py <eski veri klasörü>   (çalışma dizininde kayit/, cikti/ hazır olmalı)
Çıktı: cikti/takip/<gün>.json, cikti/takip/ozet.json
"""
import json, os, sys, math, datetime, glob, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eslestirme import benzerlik

IST = datetime.timezone(datetime.timedelta(hours=3))
BITTI = {"STATUS_FULL_TIME", "STATUS_FINAL", "STATUS_FINAL_PEN", "STATUS_FINAL_AET"}
KOMB = {"1/2": 1.15, "2/1": 0.85, "X/1": 0.95, "X/2": 0.97, "1/X": 1.0, "2/X": 1.15, "X/X": 1.0}
K12, K21, K6, ILK_YARI = KOMB["1/2"], KOMB["2/1"], 0.90, 0.44
DONUSLER = ["1/2", "2/1"]; BERABERLIKLILER = ["X/1", "X/2", "1/X", "2/X"]
BERABERLIK_EN_AZ_ORAN = 3.5; LISTE_DONUS = 4; LISTE_BERABERLIK = 4; LISTE_GOL = 8; ILK3 = 3
CANLI_CEKIM, CANLI_ALT, CANLI_UST = 600.0, 0.8, 1.25
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


def kombinasyonlar(lam, mu, s=ILK_YARI):
    """Ham (kalibresiz) İY/MS kombinasyon olasılıkları + ilk yarı önde/berabere olasılıkları"""
    h = skellam(s * lam, s * mu); g = skellam((1 - s) * lam, (1 - s) * mu)
    alt = []; a = 0.0
    for x in g: a += x; alt.append(a)
    k = {"1/2": sum(h[d + N] * alt[-d - 1 + N] for d in range(1, N)),
         "2/1": sum(h[-d + N] * (1 - alt[d + N]) for d in range(1, N)),
         "1/X": sum(h[d + N] * g[-d + N] for d in range(1, N)),
         "2/X": sum(h[-d + N] * g[d + N] for d in range(1, N)),
         "X/1": h[N] * (1 - alt[N]), "X/2": h[N] * alt[N - 1], "X/X": h[N] * g[N]}
    onde_ev = sum(h[d + N] for d in range(1, N + 1)); onde_dep = sum(h[-d + N] for d in range(1, N + 1))
    return k, onde_ev, onde_dep, h[N]


def donus(lam, mu, s=ILK_YARI):
    k, oe, od, _ = kombinasyonlar(lam, mu, s)
    return k["1/2"] * K12, k["2/1"] * K21, oe, od


def en_iyi3(liste):
    """Listenin en iyi 3'ü (olasılık × oran) ilk3=True ile işaretlenir"""
    for x in liste: x["ilk3"] = False
    oranli = [x for x in liste if x.get("oran")]
    for x in sorted(oranli, key=lambda x: -(x["p"] * x["oran"]))[:ILK3]: x["ilk3"] = True
    return liste


def canli_k(ozet_eski, anahtar):
    """Önceki özetten canlı düzeltme (yoksa 1)"""
    try: return float(((ozet_eski or {}).get(anahtar) or {}).get("kalibrasyon") or 1.0)
    except (TypeError, ValueError): return 1.0


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


def kilitle(gun, kayit, pin, gunluk_satir, simdi, k_donus=1.0, k_gol=1.0):
    g0 = datetime.datetime.combine(gun, datetime.time(0, 0), IST).timestamp() * 1000; g1 = g0 + 86_400_000
    secim_d, secim_b, secim_g = [], [], []
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
            ham, oe, od, ob = kombinasyonlar(*lm)
            kal = {kk: min(0.95, v * KOMB[kk] * k_donus) for kk, v in ham.items()}
            oranlar = dict(zip(IYMS, iy))
            ortak = {"evOnde": round(oe, 3), "depOnde": round(od, 3), "iyBerabere": round(ob, 3), "xg": [round(lm[0], 2), round(lm[1], 2)],
                     "hepsi": {kk: round(v, 4) for kk, v in kal.items()}, "kCanli": round(k_donus, 4)}
            pz = "1/2" if kal["1/2"] >= kal["2/1"] else "2/1"
            secim_d.append({**temel, "tur": "dönüş", "pazar": pz, "p": round(kal[pz], 4), "oran": oranlar.get(pz), "p12": round(kal["1/2"], 4), "p21": round(kal["2/1"], 4), **ortak})
            havuz = [kk for kk in BERABERLIKLILER if (oranlar.get(kk) or 0) >= BERABERLIK_EN_AZ_ORAN]
            if havuz:
                pz = max(havuz, key=lambda kk: kal[kk])
                secim_b.append({**temel, "tur": "beraberlik", "pazar": pz, "p": round(kal[pz], 4), "oran": oranlar.get(pz), **ortak})
        if gg and len(gg) == 4 and gg[3]:
            if pu6 is not None:
                t6 = toplam(pu6, cizgi6)
            else:
                a35 = o.get("AU3.5"); u35 = marjsiz([a35[1], a35[0]]) if a35 and len(a35) == 2 else None
                t6 = toplam(u35[0], 3.5) if (u35 and kaynak == "İddaa") else t
            if t6:
                secim_g.append({**temel, "pazar": "6+", "p": round(min(0.95, p6(t6) * k_gol), 4), "oran": gg[3], "beklenen": round(t6, 2), "kCanli": round(k_gol, 4)})
    sira = lambda x: (x["kaynak"] == "İddaa", -x["p"])
    secim_d.sort(key=sira); secim_b.sort(key=sira); secim_g.sort(key=sira)
    return {"gun": gun.isoformat(), "kilit": int(simdi), "kilitSaat": datetime.datetime.fromtimestamp(simdi / 1000, IST).strftime("%Y-%m-%d %H:%M"),
            "donus": en_iyi3(secim_d[:LISTE_DONUS] + secim_b[:LISTE_BERABERLIK]), "gol6": en_iyi3(secim_g[:LISTE_GOL]),
            "donusTum": len(secim_d), "beraberlikTum": len(secim_b), "gol6Tum": len(secim_g)}


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
                iy = "1" if ie > idp else ("X" if ie == idp else "2"); msn = "1" if e > d else ("X" if e == d else "2")
                s["sonuc"] = s["pazar"] == f"{iy}/{msn}"
    dosya["tamam"] = hepsi
    return dosya


def _bos(): return {"secim": 0, "tuttu": 0, "oranli": 0, "getiri": 0.0, "beklenen": 0.0, "beklenenHam": 0.0}


def _topla(x, sec):
    for s in sec:
        x["secim"] += 1; x["beklenen"] += s["p"]; x["beklenenHam"] += s["p"] / (s.get("kCanli") or 1.0)
        if s["sonuc"]: x["tuttu"] += 1
        if s.get("oran"): x["oranli"] += 1; x["getiri"] += s["oran"] if s["sonuc"] else 0.0


def _kapat(x, canli=True):
    x["birTLgetiri"] = round(x["getiri"] / x["oranli"], 3) if x["oranli"] else None
    if canli:
        n = x["secim"]; oran = (x["tuttu"] / x["beklenenHam"]) if x["beklenenHam"] > 0 else 1.0
        x["kalibrasyon"] = round(min(CANLI_UST, max(CANLI_ALT, 1 + (oran - 1) * n / (n + CANLI_CEKIM))), 4)
    for a in ("beklenen", "beklenenHam", "getiri"): x[a] = round(x[a], 2)
    x.pop("beklenenHam", None) if not canli else None


def ozet(klasor):
    o = {"donus": _bos(), "gol6": _bos(), "gunler": []}
    ilk3 = {"donus": _bos(), "gol6": _bos()}
    for yol in sorted(glob.glob(f"{klasor}/2*.json")):
        f = oku(yol, {})
        satir = {"gun": f.get("gun")}
        for k in ("donus", "gol6"):
            sec = [s for s in f.get(k, []) if isinstance(s.get("sonuc"), bool)]
            _topla(o[k], sec); _topla(ilk3[k], [s for s in sec if s.get("ilk3")])
            t = sum(1 for s in sec if s["sonuc"]); g = sum(s["oran"] for s in sec if s["sonuc"] and s.get("oran"))
            satir[k] = {"secim": len(sec), "tuttu": t, "bekleyen": sum(1 for s in f.get(k, []) if s.get("sonuc") is None), "getiri": round(g / len(sec), 3) if sec else None,
                        "ilk3Tuttu": sum(1 for s in sec if s.get("ilk3") and s["sonuc"]), "ilk3Secim": sum(1 for s in sec if s.get("ilk3"))}
        o["gunler"].append(satir)
    for k in ("donus", "gol6"):
        _kapat(o[k]); _kapat(ilk3[k], canli=False); o[k]["ilk3"] = ilk3[k]
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
            oz_eski = oku("cikti/takip/ozet.json") or oku(f"{eski}/takip/ozet.json") or {}
            d = kilitle(bugun, kayit, pin, gun_satir, simdi, canli_k(oz_eski, "donus"), canli_k(oz_eski, "gol6"))
            json.dump(d, open(hedef, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"kilitlendi {bugun}: dönüş {len(d['donus'])} ({d['donusTum']} dönüş + {d['beraberlikTum']} beraberlikli aday) · 6+ {len(d['gol6'])}/{d['gol6Tum']} · canlı K {canli_k(oz_eski, 'donus')} / {canli_k(oz_eski, 'gol6')}")
    # Puanla (tamamlanmamış dosyalar)
    for yol in sorted(glob.glob("cikti/takip/2*.json")):
        f = oku(yol, {})
        if f.get("tamam"): continue
        f = puanla(f, sonuclar)
        json.dump(f, open(yol, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    oz = ozet("cikti/takip")
    json.dump(oz, open("cikti/takip/ozet.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    d, g = oz["donus"], oz["gol6"]
    print(f"::notice title=Yüksek oran takibi::Dönüş {d['tuttu']}/{d['secim']} (beklenen {d['beklenen']}) 1₺→{d['birTLgetiri']} K{d['kalibrasyon']} · 6+ {g['tuttu']}/{g['secim']} (beklenen {g['beklenen']}) 1₺→{g['birTLgetiri']} K{g['kalibrasyon']} · en iyi 3: dönüş {d['ilk3']['tuttu']}/{d['ilk3']['secim']} 1₺→{d['ilk3']['birTLgetiri']} · 6+ {g['ilk3']['tuttu']}/{g['ilk3']['secim']} 1₺→{g['ilk3']['birTLgetiri']}")


if __name__ == "__main__":
    main()
