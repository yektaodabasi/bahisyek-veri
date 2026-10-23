#!/usr/bin/env python3
"""Günlük kayıt: Nesine bülteninin ana pazar oranları + ESPN'deki DraftKings oranları (takip edilen ligler).
İleride "İddaa dünya piyasasına göre fazla ödediğinde gerçekten tutuyor mu" sorusunu ölçmek için birikir.
Çıktı: kayit/<tarih>.json (küçük)."""
import json, os, subprocess, datetime, sys, traceback

UA = "Mozilla/5.0 (Linux; Android 11; NX729J) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
LIGLER = ["tur.1", "eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "ned.1", "por.1", "bel.1", "sco.1", "uefa.champions", "uefa.europa", "uefa.europa.conf", "eng.2", "ger.2", "esp.2", "ita.2", "fra.2"]
ANA = {1: "MS", 3: "CS", 7: "IY", 11: "AU1.5", 12: "AU2.5", 13: "AU3.5", 38: "KG"}


def al(url, basliklar=()):
    k = ["curl", "-sS", "-L", "--compressed", "--max-time", "120", "-A", UA]
    for b in basliklar: k += ["-H", b]
    k.append(url)
    try:
        s = subprocess.run(k, capture_output=True, text=True, timeout=150)
        return json.loads(s.stdout) if s.returncode == 0 and s.stdout else None
    except Exception as e:
        print("al", url[:80], type(e).__name__, flush=True)
        return None


def liste(x, n):
    """nsn alanları liste ya da sözlük gelebilir; her durumda en çok n öğelik liste döner."""
    if isinstance(x, dict): x = list(x.values())
    return x[:n] if isinstance(x, list) else []


def sayi(x):
    try: return float(x)
    except Exception: return 0.0


def nesine_kaydet(kayit):
    j = al("https://cdnbulten.nesine.com/api/bulten/getprebultenfull", ["Referer: https://www.nesine.com/", "Origin: https://www.nesine.com"])
    if not j:
        kayit["hata"].append("nesine: yanıt yok"); return
    nsn = j.get("nsn") or {}
    kayit["nsnAnahtarlar"] = list(nsn.keys())[:40]
    kayit["yorumcular"] = liste(nsn.get("editorChoices"), 500)
    kayit["yorumcuYorumlari"] = liste(nsn.get("editorComments"), 200)
    kayit["enIyiKazananlar"] = liste(nsn.get("bestWinnersBets"), 100)
    kayit["yuzdeler"] = liste(nsn.get("percentages"), 300)
    sg = j.get("sg") or {}
    la = {l.get("LID"): l.get("N") for l in sg.get("LA", []) or []}
    sinir = (datetime.datetime.now().timestamp() + 3 * 86400) * 1000
    for e in sg.get("EA", []) or []:
        if e.get("TYPE") != 1: continue
        if sayi(e.get("ESD")) > sinir: continue
        oranlar = {}
        for m in e.get("MA", []) or []:
            ad = ANA.get(m.get("MTID"))
            if not ad: continue
            oranlar[ad] = [o.get("O") for o in m.get("OCA", []) or []]
        if oranlar:
            kayit["nesine"].append({"c": e.get("C"), "ev": e.get("HN"), "dep": e.get("AN"), "t": e.get("ESD"), "lig": la.get(e.get("LC")), "o": oranlar})


def main():
    bugun = datetime.date.today()
    os.makedirs("kayit", exist_ok=True)
    kayit = {"tarih": bugun.isoformat(), "nesine": [], "dk": [], "hata": []}
    try:
        nesine_kaydet(kayit)
    except Exception as e:
        kayit["hata"].append(f"nesine: {type(e).__name__}: {e}")
        traceback.print_exc()
    for lig in LIGLER:
        for gun in range(0, 3):
            d = (bugun + datetime.timedelta(days=gun)).strftime("%Y%m%d")
            try:
                s = al(f"{ESPN}/{lig}/scoreboard?dates={d}&limit=200")
            except Exception as e:
                kayit["hata"].append(f"espn {lig} {d}: {type(e).__name__}"); s = None
            if not s: continue
            for e in s.get("events", []):
                c = e.get("competitions", [{}])[0]
                o = next((x for x in c.get("odds", []) or [] if x), None)
                if not o: continue
                ml = o.get("moneyline") or {}
                tk = {k.get("homeAway"): k for k in c.get("competitors", [])}
                kayit["dk"].append({"id": e.get("id"), "lig": lig, "t": e.get("date"), "ev": tk.get("home", {}).get("team", {}).get("displayName"), "dep": tk.get("away", {}).get("team", {}).get("displayName"),
                                    "ev_id": tk.get("home", {}).get("team", {}).get("id"), "dep_id": tk.get("away", {}).get("team", {}).get("id"),
                                    "o1": (ml.get("home") or {}).get("close", {}).get("odds"), "ox": (ml.get("draw") or {}).get("close", {}).get("odds"), "o2": (ml.get("away") or {}).get("close", {}).get("odds"),
                                    "au": o.get("overUnder"), "ust": ((o.get("total") or {}).get("over") or {}).get("close", {}).get("odds"), "alt": ((o.get("total") or {}).get("under") or {}).get("close", {}).get("odds")})
    json.dump(kayit, open(f"kayit/{bugun.isoformat()}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    ozet = f"nesine {len(kayit['nesine'])} dk {len(kayit['dk'])} yorumcu {len(kayit.get('yorumcular', []))} yorum {len(kayit.get('yorumcuYorumlari', []))} hata {kayit['hata'][:3]}"
    print(ozet)
    print(f"::notice title=Bülten kaydı::{ozet}")


if __name__ == "__main__":
    main()
