#!/usr/bin/env bash
# Tek veri turu: "veri" dalındaki önceki veriyi alır, üretir, değiştiyse dala yazar.
#   tam   : paket + şut + keskin oranlar + bülten + takip + hata haritası
#   hafif : yalnız akıllı Pinnacle çekimi (+ çekim olduysa İddaa anlık görüntüsü)
# Gerekli ortam: TOKEN (github.token), GITHUB_REPOSITORY; isteğe bağlı ODDS_API_KEY, ZORLA.
set -u
mod=${1:-tam}
cd "$(git rev-parse --show-toplevel)"
rm -rf eski cikti kayit oran_degisti
mkdir -p eski
if git fetch -q --depth 1 origin veri 2>/dev/null; then
  git --work-tree=eski checkout -q origin/veri -- . || true
  git reset -q
fi

if [ "$mod" = tam ]; then
  python3 arac/paket.py eski || { echo "paket üretilemedi"; exit 1; }
  python3 arac/sutlar.py eski || cp eski/sutlar.json.gz cikti/ 2>/dev/null || true
  mkdir -p kayit && cp -r eski/kayit/. kayit/ 2>/dev/null || true
  ARSIV_DIR=kayit python3 arac/oranlar.py eski || cp eski/oranlar.json cikti/ 2>/dev/null || true
  python3 arac/bulten_kaydet.py || true
  mkdir -p cikti/kayit && cp -r kayit/. cikti/kayit/
  mkdir -p cikti/gunluk && cp -rn eski/gunluk/. cikti/gunluk/ 2>/dev/null || true
  python3 arac/takip.py eski || { mkdir -p cikti/takip && cp -rn eski/takip/. cikti/takip/ 2>/dev/null; true; }
  python3 arac/analiz.py || cp eski/analiz.json cikti/ 2>/dev/null || true
  # 120 günden eski kayıtları at (dosya adındaki tarihe göre)
  esik=$(date -u -d "120 days ago" +%F)
  for f in cikti/kayit/*.json cikti/gunluk/*.json; do
    [ -e "$f" ] || continue
    g=$(basename "$f" .json); g=${g#pin_}
    [[ "$g" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] && [[ "$g" < "$esik" ]] && rm -f "$f"
  done
  [ -f cikti/paket.json.gz ] || { echo "paket yok; yazılmadı"; exit 1; }
else
  mkdir -p cikti && cp -r eski/. cikti/
  ARSIV_DIR=cikti/kayit python3 arac/oranlar.py eski || true
  if [ ! -f oran_degisti ]; then echo "yeni çekim yok"; exit 0; fi
  mkdir -p kayit && cp -r cikti/kayit/. kayit/ 2>/dev/null || true
  python3 arac/bulten_kaydet.py --hafif || true
  cp -r kayit/. cikti/kayit/
fi

cd cikti
rm -f oran_degisti
git init -q -b veri
git config user.name "veri"; git config user.email "veri@users.noreply.github.com"
git add -A && git commit -qm "veri ($mod) $(date -u +%FT%H:%M)"
git push -qf "https://x-access-token:${TOKEN}@github.com/${GITHUB_REPOSITORY}" veri
if [ "$mod" = tam ]; then
  echo "::notice title=Paket::$(tr -d '\n ' < paket_bilgi.json | head -c 300)"
fi
python3 -c "import json;o=json.load(open('oranlar.json'));print('keskin oranlar: olay',len(o.get('olaylar',[])),'kalan kredi',o.get('kalan'),'bugün',o.get('gunKredi'))" 2>/dev/null || true
