#!/usr/bin/env python3
"""Günlük kayıt: Nesine bülteninin ana pazar oranları + ESPN'deki DraftKings oranları (takip edilen ligler).
İleride "İddaa dünya piyasasına göre fazla ödediğinde gerçekten tutuyor mu" sorusunu ölçmek için birikir.
Çıktı: kayit/<tarih>.json (küçük)."""
import json, os, subprocess, datetime, sys

UA = "Mozilla/5.0 (Linux; Android 11; NX729J) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
LIGLER = ["tur.1", "eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "ned.1", "por.1", "bel.1", "sco.1", "uefa.champions", "uefa.europa", "uefa.europa.conf", "eng.2", "ger.2", "esp.2", "ita.2", "fra.2"]
ANA = {1: "MS", 3: "CS", 7: "IY", 11: "AU1.5", 12: "AU2.5", 13: "AU3.5", 38: "KG"}


def al(url, basliklar=()):
    k = ["curl", "-sS", "-L", "--compressed", "--max-time", "120", "-A", UA]
    for b in basliklar: k += ["-H", b]
    k.append(url)
    s = subprocess.run(k, capture_output=True, text=True, timeout=150)
    return json.loads(s.stdout) if s.returncode == 0 and s.stdout else None


def main():
    bugun = datetime.date.today()
    os.makedirs("kayit", exist_ok=True)
    kayit = {"tarih": bugun.isoformat(), "nesine": [], "dk": []}
    j = al("https://cdnbulten.nesine.com/api/bulten/getprebultenfull", ["Referer: https://www.nesine.com/", "Origin: https://www.nesine.com"])
    if j:
        nsn = j.get("nsn") or {}
        kayit["yorumcular"] = nsn.get("editorChoices", [])
        kayit["yorumcuYorumlari"] = nsn.get("editorComments", [])[:200]
        kayit["enIyiKazananlar"] = nsn.get("bestWinnersBets", [])[:100]
        kayit["yuzdeler"] = nsn.get("percentages", [])[:300]
        la = {l["LID"]: l["N"] for l in j["sg"].get("LA", [])}
        for e in j["sg"].get("EA", []):
            if e.get("TYPE") != 1: continue
            if e.get("ESD", 0) > (datetime.datetime.now().timestamp() + 3 * 86400) * 1000: continue
            oranlar = {}
            for m in e.get("MA", []):
                ad = ANA.get(m.get("MTID"))
                if not ad: continue
                oranlar[ad] = [o.get("O") for o in m.get("OCA", [])]
            if oranlar:
                kayit["nesine"].append({"c": e["C"], "ev": e.get("HN"), "dep": e.get("AN"), "t": e.get("ESD"), "lig": la.get(e.get("LC")), "o": oranlar})
    for lig in LIGLER:
        for gun in range(0, 3):
            d = (bugun + datetime.timedelta(days=gun)).strftime("%Y%m%d")
            s = al(f"{ESPN}/{lig}/scoreboard?dates={d}&limit=200")
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
    print("nesine", len(kayit["nesine"]), "dk", len(kayit["dk"]))


if __name__ == "__main__":
    main()
