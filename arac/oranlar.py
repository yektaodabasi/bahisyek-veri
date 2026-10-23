#!/usr/bin/env python3
"""Keskin piyasa oranları (The-Odds-API, ücretsiz kota ayda 500 istek).
Önümüzdeki ~48 saatte maçı olan liglerden h2h (1X2) ve toplam gol oranlarını çeker; Pinnacle varsa onu,
yoksa kitapçıların marjsız medyanını "konsensüs" olarak yazar. Günde en çok ~16 kredi harcar (lig başına 2).
Kullanım: ODDS_API_KEY ortam değişkeni; önceki çıktı eski/oranlar.json (varsa, kota ve saat takibi için).
Çıktı: cikti/oranlar.json
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
    # Önceki olaylar: başlamamış olanlar kalsın (kota tasarrufu: aynı gün ikinci çekim yapılmaz)
    olaylar = {o["id"]: o for o in eski.get("olaylar", []) if o.get("t", 0) > (simdi - 3 * 3600) * 1000}
    if simdi - eski.get("sonCekim", 0) < 20 * 3600:
        print("son çekim 20 saatten yeni; atlandı", flush=True)
        eski["olaylar"] = list(olaylar.values())
        json.dump(eski, open("cikti/oranlar.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        return
    # Hangi liglerde 48 saat içinde maç var: ESPN skor tablosu (ücretsiz)
    ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
    gunler = [(datetime.date.today() + datetime.timedelta(days=i)).strftime("%Y%m%d") for i in range(2)]
    aktif = []
    for lig, anahtar in LIGLER:
        var = False
        for g in gunler:
            j, _ = al(f"{ESPN}/{lig}/scoreboard?dates={g}&limit=100")
            if j and any(e.get("status", {}).get("type", {}).get("state") == "pre" for e in j.get("events", [])):
                var = True; break
        if var: aktif.append((lig, anahtar))
    print("maçı olan ligler:", [l for l, _ in aktif], flush=True)
    kalan = None
    for lig, spor in aktif:
        if gunKredi + 2 > GUNLUK_KREDI:
            print("günlük kredi sınırı; kalan ligler atlandı", flush=True); break
        j, b = al(f"{API}/{spor}/odds/?apiKey={ANAHTAR}&regions=eu&markets=h2h,totals&oddsFormat=decimal")
        kullanilan = b.get("x-requests-used"); kalan = b.get("x-requests-remaining")
        gunKredi += int(b.get("x-requests-last", "2") or 2)
        if not isinstance(j, list):
            print(lig, "yanıt yok", str(j)[:200], flush=True); continue
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
    cikti = {"olaylar": list(olaylar.values()), "sonCekim": simdi, "gunKredi": gunKredi, "gun": bugun, "kalan": kalan}
    json.dump(cikti, open("cikti/oranlar.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("keskin oran olayı", len(olaylar), flush=True)


if __name__ == "__main__":
    main()
