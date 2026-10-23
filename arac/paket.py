#!/usr/bin/env python3
"""BahisYek veri paketi (GitHub Actions'ta çalışır; APK üretmez).
Avrupa'nın bütün liglerinden (ön elemeler dahil) iki sezonun biten maçlarını tek sıkıştırılmış dosyada toplar;
uygulama bu paketi indirip modeli bütün takımlarla oturtur (Lincoln, Celje gibi takımlar artık "bilinmeyen" değil).

- Paket varsa yalnız bu ay + geçen ay yenilenir (hızlı); yoksa Temmuz 2024'ten itibaren hepsi çekilir.
- Her maç: [id, lig, zaman(ms), evId, ev, evKisa, depId, dep, depKisa, evGol, depGol, iyEv, iyDep, notr, dk1, dkX, dk2, cizgi, ust, alt]
- Ayrıca bugünün/dünün maçları sonuç + DK oranıyla "gunluk/<tarih>.json" dosyasına yazılır (teşhis için).
Çıktı: cikti/paket.json.gz, cikti/paket_bilgi.json, cikti/gunluk/<tarih>.json
"""
import json, os, subprocess, sys, time, datetime, gzip, concurrent.futures, glob

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
UA = "Mozilla/5.0 (Linux; Android 11; NX729J) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36"
BUGUN = datetime.date.today()
ESKI = sys.argv[1] if len(sys.argv) > 1 else ""   # önceki paketin klasörü (varsa)

LIGLER = """tur.1 tur.2 eng.1 eng.2 eng.3 esp.1 esp.2 ita.1 ita.2 ger.1 ger.2 fra.1 fra.2 ned.1 ned.2 por.1 por.2 bel.1 sco.1 gre.1 cze.1 aut.1 sui.1 den.1 nor.1 swe.1 pol.1
rus.1 ukr.1 cro.1 srb.1 isr.1 cyp.1 hun.1 rou.1 bul.1 svk.1 slv.1 svn.1 kaz.1 aze.1 gib.1 arm.1 ltu.1 lva.1 est.1 isl.1 fin.1 irl.1 nir.1 wal.1 mlt.1 lux.1 fro.1 geo.1 mda.1 blr.1 bih.1 mne.1 mkd.1 kos.1 alb.1 and.1 smr.1
uefa.champions uefa.europa uefa.europa.conf uefa.champions_qual uefa.europa_qual uefa.europa.conf_qual uefa.super_cup
tur.cup eng.fa eng.league_cup esp.copa_del_rey ita.coppa_italia ger.dfb_pokal fra.coupe_de_france ned.cup por.taca_de_portugal sco.cup bel.cup""".split()


def al(url, zaman=60):
    try:
        s = subprocess.run(["curl", "-sS", "-L", "--compressed", "--max-time", str(zaman), "-A", UA, url], capture_output=True, text=True, timeout=zaman + 10)
        if s.returncode != 0 or not s.stdout: return None
        return json.loads(s.stdout)
    except Exception:
        return None


def amerikan(o):
    if o is None: return None
    try: v = float(str(o).replace("+", ""))
    except ValueError: return None
    if v == 0: return None
    return round(1 + v / 100 if v > 0 else 1 + 100 / (-v), 3)


def zaman_ms(s):
    for f in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ"):
        try: return int(datetime.datetime.strptime(s, f).replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
        except ValueError: pass
    return None


def olay(e, lig):
    """Biten maç → kompakt satır; bitmemişse (planlı/canlı) None (gunluk için ayrı işlenir)."""
    c = e.get("competitions", [{}])[0]
    st = (c.get("status") or e.get("status") or {}).get("type", {}).get("name")
    ev = dep = None
    for k in c.get("competitors", []):
        if k.get("homeAway") == "home": ev = k
        elif k.get("homeAway") == "away": dep = k
    if not ev or not dep: return None
    t = zaman_ms(e.get("date", ""))
    if t is None: return None
    bitti = st in ("STATUS_FULL_TIME", "STATUS_FINAL", "STATUS_FINAL_PEN", "STATUS_FINAL_AET")
    try:
        eg = int(float(ev.get("score"))) if bitti else None; dg = int(float(dep.get("score"))) if bitti else None
    except (TypeError, ValueError):
        eg = dg = None
    if bitti and (eg is None or dg is None): return None
    evId = ev.get("team", {}).get("id"); depId = dep.get("team", {}).get("id")
    iyE = iyD = None
    golculer = []
    if bitti:
        e1 = d1 = 0; var = False
        for d in c.get("details", []):
            if not d.get("scoringPlay"): continue
            var = True
            if not d.get("ownGoal"):
                for a in d.get("athletesInvolved", []) or []:
                    if a.get("id"): golculer.append([d.get("team", {}).get("id"), a.get("id"), a.get("displayName") or a.get("shortName") or ""])
            ekran = d.get("clock", {}).get("displayValue", "") or ""
            deger = d.get("clock", {}).get("value") or 0
            ilk = ekran.startswith("45'+") or (deger <= 2700 and not ekran.startswith("90'"))
            tid = d.get("team", {}).get("id")
            gol = max(1, int(d.get("scoreValue") or 1))
            if ilk:
                if tid == evId: e1 += gol
                elif tid == depId: d1 += gol
        if var or (eg == 0 and dg == 0): iyE, iyD = e1, d1
    dk = [None] * 6
    for o in c.get("odds", []) or []:
        if not o: continue
        ml = o.get("moneyline") or {}
        dk = [amerikan((ml.get("home") or {}).get("close", {}).get("odds")) or amerikan((o.get("homeTeamOdds") or {}).get("moneyLine")),
              amerikan((ml.get("draw") or {}).get("close", {}).get("odds")) or amerikan((o.get("drawOdds") or {}).get("moneyLine")),
              amerikan((ml.get("away") or {}).get("close", {}).get("odds")) or amerikan((o.get("awayTeamOdds") or {}).get("moneyLine")),
              o.get("overUnder"),
              amerikan(((o.get("total") or {}).get("over") or {}).get("close", {}).get("odds")) or amerikan(o.get("overOdds")),
              amerikan(((o.get("total") or {}).get("under") or {}).get("close", {}).get("odds")) or amerikan(o.get("underOdds"))]
        break
    satir = [e.get("id"), lig, t, evId, ev.get("team", {}).get("displayName"), ev.get("team", {}).get("abbreviation") or "",
             depId, dep.get("team", {}).get("displayName"), dep.get("team", {}).get("abbreviation") or "",
             eg, dg, iyE, iyD, 1 if c.get("neutralSite") else 0] + dk
    return st, satir, golculer


def ay_cek(lig, y, a):
    j = al(f"{ESPN}/{lig}/scoreboard?dates={y:04d}{a:02d}&limit=400")
    if not j: return None
    return [x for x in (olay(e, lig) for e in j.get("events", [])) if x]


def aylar(bas_y, bas_a):
    y, a = bas_y, bas_a
    l = []
    son = (BUGUN.year, BUGUN.month)
    while (y, a) <= son:
        l.append((y, a)); a += 1
        if a > 12: a = 1; y += 1
    return l


def main():
    os.makedirs("cikti/gunluk", exist_ok=True)
    eski = {}
    bilgi = {}
    if ESKI and os.path.exists(os.path.join(ESKI, "paket.json.gz")):
        try:
            with gzip.open(os.path.join(ESKI, "paket.json.gz"), "rt", encoding="utf-8") as f:
                for s in json.load(f)["maclar"]: eski[s[0]] = s
            bilgi = json.load(open(os.path.join(ESKI, "paket_bilgi.json"), encoding="utf-8"))
            print("önceki paket", len(eski), "maç", flush=True)
        except Exception as e:
            print("önceki paket okunamadı", e, flush=True); eski = {}
    tam = not eski
    if tam:
        isler = [(l, y, a) for l in LIGLER for (y, a) in aylar(2024, 7)]
    else:
        onceki = (BUGUN.replace(day=1) - datetime.timedelta(days=1))
        isler = [(l, y, a) for l in LIGLER for (y, a) in ((onceki.year, onceki.month), (BUGUN.year, BUGUN.month))]
    print("istek", len(isler), "tam" if tam else "artımlı", flush=True)
    yeni = dict(eski)
    # Golcüler: maç bazında (yeniden sayım kolay) — golcu_mac.json: {macId: [[takimId, oyuncuId, ad], ...]}
    golcu_mac = {}
    if ESKI and os.path.exists(os.path.join(ESKI, "golcu_mac.json.gz")):
        try:
            with gzip.open(os.path.join(ESKI, "golcu_mac.json.gz"), "rt", encoding="utf-8") as f: golcu_mac = json.load(f)
        except Exception: golcu_mac = {}
    # Planlı maçların oranları (bekleyen.json): maç bitince kapanış oranı olarak pakete geçer
    bekleyen_oran = {}
    if ESKI and os.path.exists(os.path.join(ESKI, "bekleyen.json")):
        try:
            for s in json.load(open(os.path.join(ESKI, "bekleyen.json"), encoding="utf-8")): bekleyen_oran[s[0]] = s
        except Exception: pass
    bekleyen_yeni = {}
    gunluk = []
    bas = time.time()
    dun = (BUGUN - datetime.timedelta(days=1)).isoformat(); bugun = BUGUN.isoformat()
    lig_say = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for (l, y, a), sonuc in zip(isler, ex.map(lambda x: ay_cek(*x), isler)):
            if sonuc is None: continue
            # Bu lig+ayın eski kayıtlarını at (sonuçlar/oranlar güncellensin)
            ayBas = int(datetime.datetime(y, a, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
            ySon, aSon = (y + 1, 1) if a == 12 else (y, a + 1)
            aySon = int(datetime.datetime(ySon, aSon, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
            eskiler = {k: s for k, s in yeni.items() if s[1] == l and ayBas <= s[2] < aySon}
            for k in eskiler: del yeni[k]
            for st, satir, goller in sonuc:
                tarih = datetime.datetime.fromtimestamp(satir[2] / 1000, datetime.timezone.utc).date().isoformat()
                if tarih in (dun, bugun): gunluk.append([st] + satir)
                if satir[9] is not None and goller: golcu_mac[satir[0]] = goller
                # ESPN maç bitince oranları siliyor: önceki turda yakalanan maç öncesi (kapanış) oranları korunur
                onceki = eskiler.get(satir[0]) or bekleyen_oran.get(satir[0])
                if onceki and satir[14] is None and onceki[14] is not None:
                    satir[14:20] = onceki[14:20]
                if satir[9] is not None:
                    yeni[satir[0]] = satir
                    lig_say[l] = lig_say.get(l, 0) + 1
                elif satir[14] is not None:
                    # Henüz oynanmamış ama oranı var: bir sonraki tur için sakla
                    bekleyen_yeni[satir[0]] = satir
    liste = sorted(yeni.values(), key=lambda s: s[2])
    print("paket", len(liste), "maç", round(time.time() - bas), "sn", flush=True)
    with gzip.open("cikti/paket.json.gz", "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump({"surum": 1, "uretim": int(time.time() * 1000), "alanlar": ["id", "lig", "zaman", "evId", "ev", "evKisa", "depId", "dep", "depKisa", "evGol", "depGol", "iyEv", "iyDep", "notr", "dk1", "dkX", "dk2", "cizgi", "ust", "alt"], "maclar": liste}, f, ensure_ascii=False, separators=(",", ":"))
    ligler = {}
    for s in liste: ligler[s[1]] = ligler.get(s[1], 0) + 1
    json.dump({"uretim": int(time.time() * 1000), "mac": len(liste), "ligler": ligler, "boyut": os.path.getsize("cikti/paket.json.gz")}, open("cikti/paket_bilgi.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(gunluk, open(f"cikti/gunluk/{bugun}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    # Golcüler: yalnız pakette kalan maçlar; takım başına en çok gol atan 8 oyuncu (bu sezon ağırlıklı: son 400 gün)
    paket_idler = set(yeni.keys())
    golcu_mac = {k: v for k, v in golcu_mac.items() if k in paket_idler}
    with gzip.open("cikti/golcu_mac.json.gz", "wt", encoding="utf-8") as f: json.dump(golcu_mac, f, ensure_ascii=False, separators=(",", ":"))
    sayim = {}
    sinir = int(time.time() * 1000) - 400 * 86_400_000
    for mid, goller in golcu_mac.items():
        m = yeni.get(mid)
        if not m or m[2] < sinir: continue
        for takim, oyuncu, ad in goller:
            t = sayim.setdefault(takim, {})
            g = t.setdefault(oyuncu, [ad, 0, set()])
            g[1] += 1; g[2].add(mid)
    golculer = {}
    for takim, oyuncular in sayim.items():
        liste = sorted(oyuncular.items(), key=lambda x: -x[1][1])[:8]
        golculer[takim] = [[oid, v[0], v[1], len(v[2])] for oid, v in liste]
    json.dump(golculer, open("cikti/golculer.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("golcü takım", len(golculer), flush=True)
    # Bekleyenler: yeni yakalananlar + henüz sonuçlanmamış eskiler (30 günden eski olanlar atılır)
    simdi_ms = int(time.time() * 1000)
    for k, s in bekleyen_oran.items():
        if k not in yeni and k not in bekleyen_yeni and s[2] > simdi_ms - 30 * 86_400_000: bekleyen_yeni[k] = s
    json.dump(list(bekleyen_yeni.values()), open("cikti/bekleyen.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("boyut", os.path.getsize("cikti/paket.json.gz"), "günlük", len(gunluk), flush=True)


if __name__ == "__main__":
    main()
