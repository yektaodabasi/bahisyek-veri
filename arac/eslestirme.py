"""Takım adı benzerliği (BahisYek Eslestirme.kt'nin Python kopyası): Nesine/Pinnacle/DK adlarını ESPN adlarıyla eşler."""
import re

TR = dict(zip("şŞçÇğĞıİöÖüÜéèáàãñóôíúøåäëïßćčšžł", "ssccggiioouueeaaanooiuoaaeisccszl"))
ATILAN = set(["1", "ac", "afc", "and", "as", "az", "bc", "bk", "bsc", "ca", "calcio", "cd", "cf", "club", "clube", "cr", "cs", "da", "de", "del", "e", "ec", "esporte", "fb", "fc", "fk", "fkp", "fsv", "futbol", "gnk", "hnk", "if", "ii", "jfk", "jk", "ks", "kulubu", "nk", "ofk", "pfc", "psv", "rc", "sc", "sd", "sfk", "sg", "sk", "sl", "sp", "spor", "ss", "ssc", "sv", "the", "tsv", "u", "ud", "und", "us", "ve", "vfb", "vfl"])
TAKMA = {"g.saray": "galatasaray", "gsaray": "galatasaray", "f.bahce": "fenerbahce", "fbahce": "fenerbahce", "b.jk": "besiktas", "bjk": "besiktas", "t.spor": "trabzonspor", "man.utd": "manchester united", "man.united": "manchester united", "man.city": "manchester city", "man city": "manchester city", "man utd": "manchester united", "psg": "paris saint germain", "p.saint germain": "paris saint germain", "a.madrid": "atletico madrid", "atl.madrid": "atletico madrid", "r.madrid": "real madrid", "b.munih": "bayern munich", "b.munich": "bayern munich", "b.dortmund": "borussia dortmund", "b.m.gladbach": "borussia monchengladbach", "m.gladbach": "borussia monchengladbach", "inter": "internazionale", "sporting": "sporting cp", "b.leverkusen": "bayer leverkusen", "e.frankfurt": "eintracht frankfurt", "a.bilbao": "athletic bilbao", "athletic club": "athletic bilbao", "r.sociedad": "real sociedad", "r.betis": "real betis", "c.palace": "crystal palace", "n.forest": "nottingham forest", "west ham utd": "west ham united", "wolves": "wolverhampton wanderers", "spurs": "tottenham hotspur", "newcastle utd": "newcastle united", "leeds utd": "leeds united", "sheffield utd": "sheffield united", "ajax": "ajax amsterdam", "feyenoord": "feyenoord rotterdam", "k.almaty": "kairat almaty", "o.marsilya": "marseille", "marsilya": "marseille", "lyon": "lyon", "o.lyon": "lyon", "lille": "lille", "monako": "monaco", "nice": "nice", "roma": "roma", "j.basaksehir": "istanbul basaksehir", "basaksehir": "istanbul basaksehir", "i.basaksehir": "istanbul basaksehir", "kasimpasa": "kasimpasa", "a.demirspor": "adana demirspor", "ç.rizespor": "caykur rizespor", "c.rizespor": "caykur rizespor", "rizespor": "caykur rizespor", "g.antep fk": "gaziantep", "gaziantep fk": "gaziantep", "k.erciyesspor": "kayserispor", "e.spor": "eyupspor", "eyupspor": "eyupspor", "goztepe": "goztepe", "s.gucu": "samsunspor", "samsunspor": "samsunspor", "k.gumruk": "fatih karagumruk", "karagumruk": "fatih karagumruk", "antalyaspor": "antalyaspor", "alanyaspor": "alanyaspor", "konyaspor": "konyaspor", "kocaelispor": "kocaelispor", "genclerbirligi": "genclerbirligi", "b.belediyespor": "besiktas"}
PARCA = {"prag": "prague", "munih": "munich", "viyana": "vienna", "lizbon": "lisbon", "atina": "athens", "marsilya": "marseille", "selanik": "thessaloniki", "kopenhag": "copenhagen", "bruksel": "brussels", "varsova": "warsaw", "bukres": "bucharest", "belgrad": "belgrade", "uskup": "skopje", "cenevre": "geneva", "zurih": "zurich", "moskova": "moscow", "kiev": "kyiv", "lefkosa": "nicosia", "sofya": "sofia", "kudus": "jerusalem", "roma": "roma", "napoli": "napoli", "torino": "torino", "kizilyildiz": "red star", "monako": "monaco", "nis": "nice", "sevilla": "sevilla", "bilbao": "bilbao", "girona": "girona", "koln": "cologne", "rennais": "rennes", "gladbach": "monchengladbach", "mgladbach": "monchengladbach", "hamburger": "hamburg", "guimaraes": "guimaraes", "famalicao": "famalicao", "wolverhampton": "wolverhampton"}


def sade(ad):
    sb = []
    for ch in (ad or "").strip():
        c = TR.get(ch, ch.lower())
        sb.append(c if (c.isalnum() or c in " .") else " ")
    s = re.sub(r"\s+", " ", "".join(sb)).strip()
    s = re.sub(r"\(.*?\)", "", s).strip()
    if s in TAKMA: return TAKMA[s]
    if s.replace(" ", "") in TAKMA: return TAKMA[s.replace(" ", "")]
    return re.sub(r"\s+", " ", s.replace(".", " ")).strip()


def parcalar(ad):
    out = []
    for p in sade(ad).split(" "):
        if not p or p in ATILAN: continue
        for q in PARCA.get(p, p).split(" "):
            out.append(q[:-4] if len(q) >= 8 and q.endswith("spor") else q)
    return out


def _onek(a, b):
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]: i += 1
    return i


def _pp(x, y):
    if x == y: return 1.0
    if len(x) >= 4 and y.startswith(x): return 0.9
    if len(y) >= 4 and x.startswith(y): return 0.9
    if len(x) >= 5 and len(y) >= 5 and _onek(x, y) >= 5: return 0.75
    if len(x) >= 4 and len(y) >= 4 and _onek(x, y) >= 3: return 0.55
    if len(x) == 1 and y.startswith(x): return 0.35
    return 0.0


def benzerlik(a, b):
    pa, pb = parcalar(a), parcalar(b)
    if not pa or not pb:
        # "PSV" gibi tamamen atılan kısa adlar: sade hâlleri eşitse ya da biri diğerini içeriyorsa
        sa, sb_ = sade(a), sade(b)
        return 0.8 if sa and sb_ and (sa in sb_ or sb_ in sa) else 0.0
    if sade(a) == sade(b) or pa == pb: return 1.0
    yon = lambda p1, p2: sum(max(_pp(x, y) for y in p2) for x in p1) / len(p1)
    puan = (yon(pa, pb) + yon(pb, pa)) / 2
    return puan * (1.0 if any(len(t) >= 4 for t in pa + pb) else 0.8)
