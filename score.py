"""Extraction du nombre de cartes + scoring 'pépite' d'une annonce."""

import re
import unicodedata

CARDS_PER_KG = 600  # ~1.67 g par carte


def norm(text):
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def extract_card_count(title):
    """Renvoie (nb_cartes, origine) ou (None, None)."""
    t = norm(title)

    mw = re.search(r"(\d+(?:[.,]\d+)?)\s*(kgs?|kilos?|kilogrammes?)\b", t)
    if mw:
        kg = float(mw.group(1).replace(",", "."))
        if 0.1 <= kg <= 100:
            return int(kg * CARDS_PER_KG), "%g kg" % kg

    mg = re.search(r"(\d{3,4})\s*(?:g|grammes?)\b", t)
    if mg:
        grams = int(mg.group(1))
        if 100 <= grams <= 99000:
            return int(grams / 1000 * CARDS_PER_KG), "%d g" % grams

    patterns = [
        r"(?:lot|paquet|ensemble|collection|vrac|stock)\s*(?:de|d')?\s*(\d{2,5})(?!\s*/)(?!\s*(?:eur|€|%|ans))",
        r"(\d{2,5})\s*(?:cartes?|cards?)\b",
        r"\bx\s*(\d{2,5})\b",
        r"(\d{2,5})\s*(?:pcs?|pieces?)\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, t):
            n = int(m.group(1))
            if 10 <= n <= 50000:
                return n, "titre"
    return None, None


GEM_KEYWORDS = [
    # vintage / haute valeur
    (r"\bwizards?\b|\bwotc\b", 5, "Wizards/WOTC"),
    (r"1[eè]?re?\s*[ée]dition|\bedition\s*1\b|\b1ed\b|\bfirst edition\b", 5, "1ère édition"),
    (r"\b(199[6-9]|200[0-3])\b", 4, "années 90/2000"),
    (r"set de base|base set|\bfossile\b|\bfossil\b|\bjungle\b|\bneo\b|team rocket", 4, "set vintage"),
    (r"\bvintage\b|\bretro\b|\bancienne?s?\b|\bold\b", 3, "vintage"),
    (r"\bgrenier\b|\bsuccession\b|\bheritage\b|\bdebarras\b|collection perso", 3, "grenier/succession"),
    # cartes à valeur
    (r"\bpsa\b|\bpca\b|\bgrad[ée]e?s?\b|\bbgs\b", 3, "gradée"),
    (r"\bholo(graphique)?s?\b|\bbrillantes?\b|\bshiny\b", 2, "holo"),
    (r"\bex\b|\bgx\b|\bvmax\b|\bvstar\b|\bmega\b|\bprime\b|\blv\.?\s*x\b", 2, "cartes EX/GX"),
    (r"\bsecrete?s?\b|\brainbow\b|\bfull ?art\b|\balt(ernative)? ?art\b", 2, "full art/secrète"),
    (r"\bjapon(ais|aise)?e?s?\b|\bjapan(ese)?\b", 1, "japonais"),
    (r"\brares?\b", 1, "rares"),
    # scellé = un autre hobby : ça n'alimente pas le trieur, donc poids nul
    (r"\bdisplay\b|\bbooster\b|\bscell[ée]e?s?\b|\bsealed\b|\betb\b|\bcoffret\b", 0, "scellé (pas du vrac)"),
]

# Indices de gros volume quand le titre ne chiffre pas les cartes.
# Indispensable sur Leboncoin/Vinted où le nombre est dans la description.
BULK_HINTS = [
    (r"\ben vrac\b|\bvrac\b", 4, "vrac"),
    (r"\bmilliers?\b|\bdes milliers\b", 4, "milliers"),
    (r"(gros|enorme|grosse|important|immense|giga|mega)\s+(lot|quantite|collection|stock)", 3, "gros lot"),
    (r"\bcartons?\b|\bboites? pleines?\b|\bbac\b|\bcaisse\b", 3, "carton/caisse"),
    (r"toute (ma|la) collection|collection (complete|entiere)|fin de collection", 3, "collection entière"),
    (r"classeurs?\s+(rempli|plein|complet|full)|(rempli|plein)\s+de\s+cartes", 3, "classeur rempli"),
    (r"\bclasseurs?\b|\bbinder\b|\bportfolio\b|\balbums?\b", 1, "classeur/album"),
    (r"\bdestockage\b|\bdebarras\b|\bbrocante\b|\bvide.?grenier\b", 2, "déstockage"),
    (r"\bdoubles?\b|\bcommunes?\b|\bbulk\b", 2, "communes/doubles"),
]

RED_FLAGS = [
    (r"\bfakes?\b|\bfaux\b|\bcontrefa[çc]on\b|\bcounterfeit\b", "contrefaçon"),
    (r"\bproxy(s|ies)?\b|\borica\b|\bcustom\b|\bfanmade\b|fan ?art", "proxy/custom"),
    (r"\bnon officiel|\bunofficial\b|\bnot official\b", "non officiel"),
    (r"\bvide\b|\bempty\b", "vide"),
    (r"top.?loaders?|\bemplacements?\b|\brangements?\b|sans (les )?cartes|classeur seul", "contenant vide"),
    (r"\bcode\s*(carte|card|online|ptcgo|ptcgl)", "cartes code"),
    (r"\bstickers?\b|\bautocollants?\b|\bcartonnettes?\b", "stickers"),
]


def analyse(item, cfg):
    title = item.get("title", "")
    t = norm(title)

    count, origin = extract_card_count(title)
    item["cards"] = count
    item["cards_origin"] = origin

    price = item.get("price")
    shipping = item.get("shipping")
    total = None
    if price is not None:
        total = price + (shipping if shipping is not None else 0.0)
    item["total"] = total
    item["price_per_card"] = round(total / count, 4) if (total and count) else None

    gems = []
    score = 0
    for pat, weight, label in GEM_KEYWORDS:
        if re.search(pat, t):
            score += weight
            gems.append(label)

    bulk = []
    for pat, weight, label in BULK_HINTS:
        if re.search(pat, t):
            score += weight
            bulk.append(label)
    item["bulk"] = bulk

    flags = [label for pat, label in RED_FLAGS if re.search(pat, t)]

    # bonus volume
    if count:
        if count >= 2000:
            score += 6
        elif count >= 1000:
            score += 5
        elif count >= 500:
            score += 4
        elif count >= 200:
            score += 2
        elif count >= 100:
            score += 1

    # bonus prix par carte
    ppc = item["price_per_card"]
    if ppc is not None:
        if ppc <= 0.04:
            score += 6
        elif ppc <= 0.08:
            score += 4
        elif ppc <= 0.15:
            score += 2
        elif ppc >= 0.60:
            score -= 3

    if item.get("best_offer"):
        score += 1
    if item.get("auction") and count and count >= 300:
        score += 2
    score -= 4 * len(flags)

    item["gems"] = gems
    item["flags"] = flags
    item["score"] = score
    return item


def passes(item, cfg):
    t = norm(item.get("title", ""))

    required = cfg.get("require_keywords") or []
    if required and not any(norm(w) in t for w in required):
        item["_reject"] = "hors sujet (aucun mot requis)"
        return False

    for word in cfg.get("exclude_keywords", []):
        if norm(word) in t:
            item["_reject"] = "mot exclu: %s" % word
            return False

    if cfg.get("reject_red_flags", True) and item.get("flags"):
        item["_reject"] = "red flag: %s" % ", ".join(item["flags"])
        return False

    total = item.get("total")
    if total is not None:
        # une enchère en cours part souvent de 1 € : son prix actuel ne dit rien
        # de sa valeur, donc on ne la rejette jamais sur le plancher de prix.
        if not item.get("auction") and total < cfg.get("min_total", 0):
            item["_reject"] = "trop peu cher (%.2f)" % total
            return False
        if total > cfg.get("max_total", 1e9):
            item["_reject"] = "trop cher (%.2f)" % total
            return False

    count = item.get("cards")
    min_cards = cfg.get("min_cards", 0)
    if min_cards:
        if count is None:
            if not cfg.get("keep_unknown_count", True):
                item["_reject"] = "nombre de cartes inconnu"
                return False
            # Sur Leboncoin/Vinted le titre ne chiffre presque jamais les cartes :
            # sans chiffre, il faut au moins un indice de volume, sinon on récupère
            # tous les lots de 3 cartes.
            if cfg.get("require_bulk_hint_when_unknown", True) and not item.get("bulk"):
                item["_reject"] = "ni nombre de cartes ni indice de volume"
                return False
        elif count < min_cards:
            item["_reject"] = "seulement %d cartes" % count
            return False

    max_ppc = cfg.get("max_price_per_card")
    ppc = item.get("price_per_card")
    if max_ppc and ppc is not None and not item.get("auction") and ppc > max_ppc:
        item["_reject"] = "%.3f EUR/carte" % ppc
        return False

    if item.get("score", 0) < cfg.get("min_score", -999):
        item["_reject"] = "score %d" % item["score"]
        return False

    return True
