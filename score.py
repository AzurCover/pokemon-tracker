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


SEALED = r"\bdisplay\b|\bbooster\b|\bscell[ée]e?s?\b|\bsealed\b|\betb\b|\bcoffret\b"

# Signaux de valeur valables quel que soit le jeu.
COMMON_GEMS = [
    (r"\bvintage\b|\bretro\b|\bancienne?s?\b|\bold\b", 3, "vintage"),
    (r"\bgrenier\b|\bsuccession\b|\bheritage\b|\bdebarras\b|collection perso", 3, "grenier/succession"),
    (r"\bpsa\b|\bpca\b|\bgrad[ée]e?s?\b|\bbgs\b", 3, "gradée"),
    (r"\bholo(graphique)?s?\b|\bbrillantes?\b|\bshiny\b|\bfoils?\b|\bpremiums?\b", 2, "holo/foil"),
    (r"\brares?\b", 1, "rares"),
    # le scellé est un autre hobby : il ne passe pas dans le trieur, donc poids nul
    (SEALED, 0, "scellé (pas du vrac)"),
]

GAMES = {
    "pokemon": {
        "match": r"\bpokemon\b|\bptcg\b",
        "gems": [
            (r"\bwizards?\b|\bwotc\b", 5, "Wizards/WOTC"),
            (r"1[eè]?re?\s*[ée]dition|\bedition\s*1\b|\b1ed\b|\bfirst edition\b", 5, "1ère édition"),
            (r"\b(199[6-9]|200[0-3])\b", 4, "années 90/2000"),
            (r"set de base|base set|\bfossile\b|\bfossil\b|\bjungle\b|\bneo\b|team rocket", 4, "set vintage"),
            (r"\bgx\b|\bvmax\b|\bvstar\b|\bprime\b|\blv\.?\s*x\b", 2, "cartes GX/VMAX"),
            (r"\bsecrete?s?\b|\brainbow\b|\bfull ?art\b|\balt(ernative)? ?art\b", 2, "full art/secrète"),
            (r"\bjapon(ais|aise)?e?s?\b|\bjapan(ese)?\b", 1, "japonais"),
        ],
    },
    "magic": {
        "match": r"\bmagic\b|\bmtg\b|\bgathering\b|l'?assemblee",
        "gems": [
            # la liste réservée ne sera jamais réimprimée : c'est là qu'est l'argent
            (r"liste reservee|reserved list|\bdual ?lands?\b|\bduales?\b", 6, "liste réservée/duales"),
            (r"\balpha\b|\bbeta\b|\bunlimited\b|black lotus|\bmox\b|power nine|\bp9\b", 6, "Alpha/Beta/P9"),
            (r"\blegends\b|antiquities|arabian nights|the dark|fallen empires", 5, "sets 1993-95"),
            (r"\brevised\b|revis[ée]e?\b|\b[34]\s*e(me)?\s*[ée]dition\b", 4, "Revised/4e"),
            (r"\b199[3-9]\b", 4, "années 90"),
            (r"ice age|\bmirage\b|\btempest\b|\bexodus\b|\burza\b|\bvisions\b|\bstronghold\b|\bsaga\b", 3, "sets vintage"),
            (r"\bfetch ?lands?\b|\bshock ?lands?\b|\bterrains? rares?\b", 3, "fetch/shocklands"),
            (r"\bmythiques?\b|\bmythics?\b", 1, "mythiques"),
            (r"\bcommander\b|\bedh\b|\blegacy\b|\bmodern\b", 1, "commander/legacy"),
        ],
    },
    "yugioh": {
        "match": r"\byu.?gi.?oh?\b|\bygo\b",
        # Konami réimprime sans limite et la banlist efface la cote : le vrac
        # Yu-Gi-Oh moderne ne vaut rien, même en rares. Seul le vintage se trie.
        "require": (r"1[eè]?re?\s*[ée]dition|\b1st\s*ed(ition)?\b|\blob\b|\bmrd\b|\bmrl\b|\bpsv\b|"
                    r"legend of blue.?eyes|metal raiders|magic ruler|pharaoh'?s servant|"
                    r"labyrinth of nightmare|\b200[2-5]\b|\bvintage\b|\bretro\b|\bancienne?s?\b"),
        "gems": [
            (r"\blob\b|legend of blue.?eyes", 6, "LOB"),
            (r"\bmrd\b|\bmrl\b|\bpsv\b|metal raiders|magic ruler|pharaoh'?s servant|labyrinth of nightmare", 5, "sets 2002-03"),
            (r"1[eè]?re?\s*[ée]dition|\b1st\s*ed(ition)?\b", 5, "1ère édition"),
            (r"\b200[2-5]\b", 4, "années 2002-05"),
            (r"ghost rare|ultimate rare|secrete?s? rares?|\bparallel\b", 3, "haute rareté"),
            (r"blue.?eyes|dragon blanc|magicien sombre|dark magician|\bexodia\b", 3, "cartes iconiques"),
        ],
    },
}


def detect_game(t, cfg):
    """Premier jeu suivi que le titre mentionne, et dont il remplit la condition."""
    for name in cfg.get("games") or ["pokemon"]:
        spec = GAMES.get(name)
        if not spec or not re.search(spec["match"], t):
            continue
        if spec.get("require") and not re.search(spec["require"], t):
            continue
        return name
    return None

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

# Le passe-droit "pépite" ne vaut que pour un lot : une belle carte seule, même
# gradée 1ère édition, n'a pas d'intérêt ici puisqu'elle ne se trie pas.
LOT_CONTEXT = (r"\blots?\b|\bcollections?\b|\bvracs?\b|\bensembles?\b|\bclasseurs?\b|"
               r"\bcartons?\b|\bstocks?\b|\balbums?\b|\bbinders?\b|\bportfolios?\b|"
               r"\bpaquets?\b|\bcaisses?\b|\bboites? pleines?\b")

RED_FLAGS = [
    (r"\bfakes?\b|\bfaux\b|\bcontrefa[çc]on\b|\bcounterfeit\b", "contrefaçon"),
    (r"\bproxy(s|ies)?\b|\borica\b|\bcustom\b|\bfanmade\b|fan ?art", "proxy/custom"),
    (r"\bnon officiel|\bunofficial\b|\bnot official\b", "non officiel"),
    (r"\bvide\b|\bempty\b", "vide"),
    (r"top.?loaders?|\bemplacements?\b|\brangements?\b|sans (les )?cartes|classeur seul", "contenant vide"),
    (r"\bcode\s*(carte|card|online|ptcgo|ptcgl|arena|mtgo)", "cartes code"),
    (r"\bstickers?\b|\bautocollants?\b|\bcartonnettes?\b", "stickers"),
    (r"feuilles?\s+(de\s+)?(classeur|protection|rangement)|(protection|rangement)s?\s+(de\s+)?cartes|\bpochettes?\b",
     "accessoire de rangement"),
]


ACCESSORY_BRAND = r"\bultra ?pro\b|\bdragon ?shield\b|\bgamegenic\b|\bultimate ?guard\b|\bexacompta\b"
CONTAINER = r"\bclasseurs?\b|\bbinders?\b|\bportfolios?\b|\balbums?\b|\bpochettes?\b|\bsleeves?\b|\bboites?\b"


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

    game = detect_game(t, cfg)
    item["game"] = game

    gems = []
    score = 0
    rules = COMMON_GEMS + (GAMES[game]["gems"] if game else [])
    for pat, weight, label in rules:
        if re.search(pat, t):
            score += weight
            gems.append(label)

    # Score des seuls indices de pépite, avant tout bonus de volume ou de prix :
    # c'est lui qui décide si l'annonce mérite d'échapper aux filtres de volume.
    item["gem_score"] = score
    item["premium"] = (score >= cfg.get("premium_gem_score", 12)
                       and bool(count or re.search(LOT_CONTEXT, t)))

    bulk = []
    for pat, weight, label in BULK_HINTS:
        if re.search(pat, t):
            score += weight
            bulk.append(label)
    item["bulk"] = bulk

    flags = [label for pat, label in RED_FLAGS if re.search(pat, t)]

    # "Album Ultra PRO ... 480 cartes" vend le classeur : le nombre annoncé est
    # une capacité, pas un contenu. On ne jette que si rien d'autre ne signale
    # des cartes en vrac, pour ne pas perdre un vrai lot livré avec son classeur.
    if (re.search(ACCESSORY_BRAND, t) and re.search(CONTAINER, t)
            and not re.search(r"\bvracs?\b|\bdoubles?\b|\bcommunes?\b", t)):
        flags.append("classeur de marque (contenant)")

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

    if not item.get("game"):
        item["_reject"] = "hors sujet (aucun jeu reconnu)"
        return False

    for word in cfg.get("exclude_keywords", []):
        if norm(word) in t:
            item["_reject"] = "mot exclu: %s" % word
            return False

    if cfg.get("reject_red_flags", True) and item.get("flags"):
        item["_reject"] = "red flag: %s" % ", ".join(item["flags"])
        return False

    # Le scellé ne passe pas dans le trieur. On ne l'écarte que faute de nombre
    # de cartes : "3000 cartes + un booster scellé" reste un vrac légitime.
    if item.get("cards") is None and re.search(SEALED, t):
        item["_reject"] = "scellé (pas du vrac)"
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

    # Un faisceau d'indices vintage exceptionnel (dual lands liste réservée,
    # LOB 1ère édition...) vaut plus qu'un gros volume : ces annonces ne
    # chiffrent presque jamais leurs cartes et se feraient jeter sans ça.
    premium = item.get("premium")

    count = item.get("cards")
    min_cards = cfg.get("min_cards", 0)
    if min_cards and not premium:
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
    if max_ppc and ppc is not None and not item.get("auction") and not premium and ppc > max_ppc:
        item["_reject"] = "%.3f EUR/carte" % ppc
        return False

    if item.get("score", 0) < cfg.get("min_score", -999):
        item["_reject"] = "score %d" % item["score"]
        return False

    return True
