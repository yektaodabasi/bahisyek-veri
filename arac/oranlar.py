#!/usr/bin/env python3
"""Keskin piyasa oranları (The-Odds-API, ücretsiz kota ayda 500 kredi; lig başına çekim 2 kredi: h2h + toplam gol).
Akıllı zamanlama: nöbet 15 dakikada bir çağırır; bir ligin maçı 25–70 dk içinde başlıyorsa ve o lig son 2 saatte çekilmediyse
çeker (kapanışa yakın fiyat en isabetli tahmindir; uygulama yarım saat içinde alır). Günlük harcama = kalan kredi / ayın kalan günleri (hafta içi artanı hafta sonuna kalır).
Lig önceliği LIGLER sırası. ZORLA=1: maçı olan bütün ligler (günlük sınır içinde).
Pinnacle varsa onu, yoksa kitapçıların marjsız medyanını "konsensüs" olarak yazar.
Çıktı: cikti/oranlar.json, cikti/kayit/pin_<gün>.json (maç öncesi son fiyatlar arşivi; analiz için).
"""
import json, os, subprocess, sys, time, datetime

ANAHTAR = os.environ.get("ODDS_API_KEY", "").strip()
ESKI = sys.argv[1] if len(sys.argv) > 1 else ""
API = "https://api.the-odds-api.com/v4/sports"
# ESPN lig kodu → Odds API spor anahtarı (öncelik sırasıyla)
LIGLER = [
    ("tur.1", "soccer_turkey_super_league"), ("uefa.champions", "soccer_uefa_champs_league"), ("uefa.europa", "soccer_uefa_europa_league"),
    ("uefa.europa.conf", "soccer_uefa_europa_conference_league"), ("eng.1", "soccer_epl"), ("esp.1", "soccer_spain_la_liga"), ("ita.1", "soccer_italy_serie_a"),
    ("ger.1", "soccer_germany_bundesliga"), ("fra.1", "soccer_france_ligue_one"), ("ned.1", "soccer_netherlands_eredivisie"), ("por.1", "soccer_portugal_primeira_liga"),
    ("bel.1", "soccer_belgium_first_div"), ("sco.1", "soccer_spl"), ("eng.2", "soccer_efl_champ"), ("ger.2", "soccer_germany_bundesliga2"),
    ("esp.2", "soccer_spain_segunda_division"), ("ita.2", "soccer_italy_serie_b"), ("fra.2", "soccer_france_ligue_two"),
]
GUNLUK_KREDI = 16


def al(url):
    s = subprocess.run(["curl", "-sS", "--max-time", "60", "-D", "-", url], capture_output=True, text=True, timeout=70)
    if s.returncode != 0 or not s.stdout: return None, {}
    bas, _, govde = s.stdout.partition("\r\n\r\n")
    if not govde: bas, _, govde = s.stdout.partition("\n\n")
    basliklar = {}
    for satir in bas.splitlines()[1:]:
        if ":" in satir:
            k, v = satir.split(":", 1); basliklar[k.strip().lower()] = v.strip()
    try: return json.loads(govde), basliklar
    except Exception: return None, basliklar


def marjsiz(fiyatlar):
    t = sum(1 / f for f in fiyatlar if f and f > 1)
    return [((1 / f) / t if f and f > 1 else None) for f in fiyatlar] if t > 0 else [None] * len(fiyatlar)


def medyan(l):
    l = sorted(x for x in l if x)
    if not l: return None
    n = len(l)
    return l[n // 2] if n % 2 else (l[n // 2 - 1] + l[n // 2]) / 2


def main():
    os.makedirs("cikti", exist_ok=True)
    eski = {"olaylar": [], "sonCekim": 0, "gunKredi": 0, "gun": ""}
    if ESKI and os.path.exists(os.path.join(ESKI, "oranlar.json")):
        try: eski = json.load(open(os.path.join(ESKI, "oranlar.json"), encoding="utf-8"))
        except Exception: pass
    simdi = time.time()
    bugun = datetime.date.today().isoformat()
    if not ANAHTAR:
        print("ODDS_API_KEY yok; keskin oranlar atlandı", flush=True)
        json.dump(eski, open("cikti/oranlar.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        return
    gunKredi = eski.get("gunKredi", 0) if eski.get("gun") == bugun else 0
    ligCekim = eski.get("ligCekim", {})
    # Önceki olaylar: başlamamış olanlar kalsın
    olaylar = {o["id"]: o for o in eski.get("olaylar", []) if o.get("t", 0) > (simdi - 3 * 3600) * 1000}
    # Günlük harcama sınırı: kalan krediyi ayın kalan günlerine yay (10 kredi yedek)
    kalanKredi = eski.get("kalan")
    try: kalanKredi = int(float(kalanKredi)) if kalanKredi is not None else None
    except ValueError: kalanKredi = None
    bg = datetime.date.today(); ay_son = (bg.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
    kalan_gun = (ay_son - bg).days + 1
    if kalanKredi is None: gunSinir = 16
    else: gunSinir = max(4, min(80, (kalanKredi - 10) // kalan_gun + gunKredi))
    zorla = os.environ.get("ZORLA") == "1"
    # Hangi liglerde yakında maç var: ESPN skor tablosu (ücretsiz). Pencere: 25–70 dk sonra başlayan
    ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
    gunler = [(datetime.datetime.utcnow() + datetime.timedelta(days=i)).strftime("%Y%m%d") for i in range(2)]
    aktif = []
    for lig, anahtar in LIGLER:
        yakin = False; herhangi = False
        for g in gunler:
            j, _ = al(f"{ESPN}/{lig}/scoreboard?dates={g}&limit=100")
            for e in (j or {}).get("events", []):
                if e.get("status", {}).get("type", {}).get("state") != "pre": continue
                herhangi = True
                try: ts = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00")).timestamp()
                except Exception: continue
                if 25 * 60 <= ts - simdi <= 70 * 60: yakin = True
        son = ligCekim.get(lig, 0)
        if zorla and herhangi and simdi - son > 3600: aktif.append((lig, anahtar))
        elif yakin and simdi - son > 2 * 3600: aktif.append((lig, anahtar))
    print("çekilecek ligler:", [l for l, _ in aktif], "| günlük sınır", gunSinir, "harcanan", gunKredi, "| kalan kredi", kalanKredi, flush=True)
    if not aktif:
        eski["olaylar"] = list(olaylar.values())
        json.dump(eski, open("cikti/oranlar.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        return
    kalan = None
    for lig, spor in aktif:
        if gunKredi + 2 > gunSinir:
            print("günlük kredi sınırı; kalan ligler atlandı", flush=True); break
        j, b = al(f"{API}/{spor}/odds/?apiKey={ANAHTAR}&regions=eu&markets=h2h,totals&oddsFormat=decimal")
        kullanilan = b.get("x-requests-used"); kalan = b.get("x-requests-remaining")
        gunKredi += int(b.get("x-requests-last", "2") or 2)
        if not isinstance(j, list):
            print(lig, "yanıt yok", str(j)[:200], flush=True); continue
        ligCekim[lig] = simdi
        for e in j:
            ev, dep = e.get("home_team"), e.get("away_team")
            try: t = int(datetime.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")).timestamp() * 1000)
            except Exception: continue
            h2h = {}; toplam = {}
            pin_h2h = None; pin_top = None
            for bk in e.get("bookmakers", []):
                anahtar_bk = bk.get("key")
                for m in bk.get("markets", []):
                    if m.get("key") == "h2h":
                        f = {o["name"]: o.get("price") for o in m.get("outcomes", [])}
                        fiyat = [f.get(ev), f.get("Draw"), f.get(dep)]
                        if all(fiyat):
                            h2h[anahtar_bk] = fiyat
                            if anahtar_bk == "pinnacle": pin_h2h = fiyat
                    elif m.get("key") == "totals":
                        for cizgi in {o.get("point") for o in m.get("outcomes", [])}:
                            ust = next((o.get("price") for o in m["outcomes"] if o.get("name") == "Over" and o.get("point") == cizgi), None)
                            alt = next((o.get("price") for o in m["outcomes"] if o.get("name") == "Under" and o.get("point") == cizgi), None)
                            if ust and alt:
                                toplam.setdefault(cizgi, {})[anahtar_bk] = [ust, alt]
                                if anahtar_bk == "pinnacle" and cizgi == 2.5: pin_top = [ust, alt]
            if not h2h: continue
            # Konsensüs: her kitapçının marjsız olasılığı → medyan → yeniden oran
            olas = [marjsiz(v) for v in h2h.values()]
            kons = [medyan([o[i] for o in olas]) for i in range(3)]
            top25 = toplam.get(2.5, {})
            kons_top = None
            if top25:
                olas_t = [marjsiz(v) for v in top25.values()]
                kons_top = [medyan([o[0] for o in olas_t]), medyan([o[1] for o in olas_t])]
            olaylar[e["id"]] = {
                "id": e["id"], "lig": lig, "ev": ev, "dep": dep, "t": t,
                "pin": pin_h2h, "kons": kons, "kitapci": len(h2h),
                "pinTop": pin_top, "konsTop": kons_top,
                "cizgiler": {str(c): v.get("pinnacle") or next(iter(v.values())) for c, v in toplam.items()},
                "cekim": int(simdi * 1000),
            }
        print(lig, len(j), "maç · kullanılan", kullanilan, "kalan", kalan, flush=True)
    cikti = {"olaylar": list(olaylar.values()), "sonCekim": simdi, "gunKredi": gunKredi, "gun": bugun, "kalan": kalan if kalan is not None else eski.get("kalan"), "ligCekim": ligCekim}
    json.dump(cikti, open("cikti/oranlar.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    # Arşiv: bugünkü maçların maç öncesi son fiyatları (analiz için; başlamış maçın fiyatı güncellenmez)
    arsiv_dir = os.environ.get("ARSIV_DIR", "cikti/kayit")
    os.makedirs(arsiv_dir, exist_ok=True)
    for o in olaylar.values():
        gun = datetime.datetime.fromtimestamp(o["t"] / 1000, datetime.timezone(datetime.timedelta(hours=3))).date().isoformat()
        yol = f"{arsiv_dir}/pin_{gun}.json"
        if not os.path.exists(yol) and ESKI and os.path.exists(os.path.join(ESKI, "kayit", f"pin_{gun}.json")):
            import shutil; shutil.copy(os.path.join(ESKI, "kayit", f"pin_{gun}.json"), yol)
        arsiv = {}
        if os.path.exists(yol):
            try: arsiv = json.load(open(yol, encoding="utf-8"))
            except Exception: arsiv = {}
        e = arsiv.get(o["id"])
        if o.get("cekim", 0) < o["t"] and (e is None or e.get("cekim", 0) <= o.get("cekim", 0)):
            arsiv[o["id"]] = o
            json.dump(arsiv, open(yol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    open("oran_degisti", "w").write("1")
    print("keskin oran olayı", len(olaylar), flush=True)


if __name__ == "__main__":
    main()
