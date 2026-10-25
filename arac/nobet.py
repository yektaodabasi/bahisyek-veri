#!/usr/bin/env python3
"""Nöbet: GitHub'ın zamanlayıcısı bu depoda saatlerce gecikip tur atlayabildiği için iş, maç saatlerinde kendini canlı tutar.
- 15 dakikada bir hafif tur (maçı 25–70 dk içinde başlayacak liglerin Pinnacle fiyatı + İddaa anlık görüntüsü),
- saatte bir tam tur (sonuçlar, şut, bülten, yüksek oran takibi, hata haritası).
İzlenen liglerde oynanan ya da 6 saat içinde başlayacak maç kalmayınca biter (gece). Çalışma süresi dolunca
(GitHub iş sınırı 6 saat) bir sonraki çalışmayı kendisi başlatır: GITHUB_OUTPUT'a devam=1 yazar.
Kullanım: nobet.py   (iş başında tam tur zaten yapılmış olmalı)
"""
import json, os, subprocess, sys, time, datetime, concurrent.futures

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oranlar import LIGLER, al

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
SURE = int(os.environ.get("NOBET_SURE", str(5 * 3600 + 25 * 60)))  # iş zaman aşımı 350 dk; son tur + devir payı
ARALIK = 15 * 60
TAM_ARALIK = 60 * 60
PENCERE = 6 * 3600


def durum():
    """(canlı maç sayısı, en yakın başlama zamanı ya da None) — izlenen liglerde bugün + yarın (UTC)"""
    simdi = time.time()
    gunler = [(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=i)).strftime("%Y%m%d") for i in (0, 1)]
    istek = [(lig, g) for lig, _ in LIGLER for g in gunler]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        yanit = list(ex.map(lambda x: al(f"{ESPN}/{x[0]}/scoreboard?dates={x[1]}&limit=100")[0], istek))
    canli, sonraki = 0, None
    for j in yanit:
        for e in (j or {}).get("events", []):
            st = e.get("status", {}).get("type", {}).get("state")
            if st == "in": canli += 1; continue
            if st != "pre": continue
            try: ts = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00")).timestamp()
            except Exception: continue
            if ts < simdi - 1800: continue  # ertelenmiş / güncellenmemiş
            if sonraki is None or ts < sonraki: sonraki = ts
    return canli, sonraki


def tur(mod):
    t0 = time.time()
    s = subprocess.run(["bash", "arac/tur.sh", mod], capture_output=True, text=True)
    cikis = (s.stdout + s.stderr).strip().splitlines()
    ozet = [x for x in cikis if any(k in x for k in ("çekilecek", "kalan", "yazılmadı", "Error", "error", "::notice"))]
    print(f"  {mod} tur {time.time() - t0:.0f} sn, çıkış {s.returncode}: " + " | ".join(ozet[-4:])[:600], flush=True)
    return s.returncode == 0


def saat(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone(datetime.timedelta(hours=3))).strftime("%H:%M")


def main():
    bas = time.time(); son_tam = bas
    devam = False
    while True:
        canli, sonraki = durum()
        simdi = time.time()
        uzak = (sonraki - simdi) if sonraki else None
        print(f"{saat(simdi)} TR · canlı {canli} · sıradaki maç {saat(sonraki) if sonraki else '-'}", flush=True)
        if canli == 0 and (uzak is None or uzak > PENCERE):
            print("yakın maç yok: nöbet bitti (sıradaki çalışma zamanlayıcıdan)", flush=True)
            # Son tam tur: biten maçların sonuçları ve takip puanı yazılsın
            if simdi - son_tam > 10 * 60: tur("tam")
            break
        # Bir sonraki çeyrek saate kadar bekle (:02, :17, :32, :47 — saat başı yoğunluğundan uzak)
        hedef = (int(simdi // ARALIK) + 1) * ARALIK + 120
        if hedef - bas > SURE:
            devam = True
            print("süre doldu: sonraki nöbet başlatılıyor", flush=True)
            break
        time.sleep(max(0, hedef - time.time()))
        if time.time() - son_tam >= TAM_ARALIK - 60:
            if tur("tam"): son_tam = time.time()
        else:
            tur("hafif")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f: f.write(f"devam={'1' if devam else '0'}\n")


if __name__ == "__main__":
    main()
