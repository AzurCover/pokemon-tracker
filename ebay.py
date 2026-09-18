"""Fetch + parse eBay search result pages (no external deps)."""

import gzip
import html
import json
import re
import time
import urllib.parse
import urllib.request
import zlib

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

SORT = {"recent": 10, "prix": 15, "prix_desc": 16, "fin_proche": 1, "pertinence": 12}


def build_url(query, page=1, sort="recent", min_price=None, max_price=None,
              site="www.ebay.fr", buy_it_now=False, location=None, per_page=60):
    params = {
        "_nkw": query,
        "_sop": SORT.get(sort, 10),
        "_ipg": per_page,
        "_pgn": page,
    }
    if min_price is not None:
        params["_udlo"] = min_price
    if max_price is not None:
        params["_udhi"] = max_price
    if buy_it_now:
        params["LH_BIN"] = 1
    if location == "fr":
        params["LH_PrefLoc"] = 1
    elif location == "eu":
        params["LH_PrefLoc"] = 3
    return "https://%s/sch/i.html?%s" % (site, urllib.parse.urlencode(params))


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip":
        raw = gzip.decompress(raw)
    elif enc == "deflate":
        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw.decode("utf-8", errors="replace")


def _clean(text):
    if text is None:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _money(text):
    """'1 234,56 EUR' -> 1234.56"""
    if not text:
        return None
    m = re.search(r"([\d  .]*\d)(?:[,.](\d{1,2}))?\s*(?:EUR|€|USD|\$|GBP|£)", text)
    if not m:
        return None
    whole = re.sub(r"[^\d]", "", m.group(1))
    if not whole:
        return None
    cents = m.group(2) or "0"
    try:
        return float("%s.%s" % (whole, cents.ljust(2, "0")))
    except ValueError:
        return None


CARD_BLOCK = re.compile(r'<li class="s-card\b')


def parse_listings(page_html):
    items = []
    parts = CARD_BLOCK.split(page_html)[1:]
    for blk in parts:
        blk = blk[:20000]
        m = re.search(r"data-listingid=(\d+)", blk)
        if not m:
            continue
        listing_id = m.group(1)

        mu = re.search(r"href=(https://www\.ebay\.[a-z.]+/itm/\d+)", blk)
        if not mu:
            continue
        url = mu.group(1)

        mt = re.search(
            r'class=s-card__title>.*?<span class="su-styled-text[^"]*">(.*?)</span>', blk, re.S
        )
        title = _clean(mt.group(1)) if mt else ""
        if not title or title.lower() == "shop on ebay":
            continue

        mp = re.search(r'class="[^"]*s-card__price">(.*?)</span>', blk, re.S)
        price_text = _clean(mp.group(1)) if mp else ""
        price = _money(price_text)

        mi = re.search(r"data-defer-load=(https://i\.ebayimg\.com/[^\s>]+)", blk)
        image = mi.group(1) if mi else ""

        subtitle = " ".join(
            _clean(s)
            for s in re.findall(
                r'class=s-card__subtitle>(.*?)</div>', blk, re.S
            )
        )

        attrs = [_clean(a) for a in re.findall(
            r'<span class="su-styled-text secondary[^"]*">(.*?)</span>', blk, re.S
        )]
        attr_text = " | ".join(a for a in attrs if a)

        shipping = None
        if re.search(r"livraison gratuite|free (postage|shipping)", attr_text, re.I):
            shipping = 0.0
        else:
            ms = re.search(
                r"\+\s*(\d[\d\s.,\u00a0\u202f]*(?:EUR|\u20ac))",
                attr_text, re.I)
            if ms:
                shipping = _money(ms.group(1))

        bids = None
        mb = re.search(r"(\d+)\s*(?:ench[eè]res?|bids?)", attr_text, re.I)
        if mb:
            bids = int(mb.group(1))

        best_offer = bool(re.search(r"faire une offre|best offer", attr_text, re.I))
        sponsored = False

        condition = ""
        mc = re.search(r"(Neuf|Occasion|Tr[eè]s bon [eé]tat|Bon [eé]tat|Reconditionn[eé])", subtitle, re.I)
        if mc:
            condition = mc.group(1)

        md = re.search(r'<span class="su-styled-text secondary bold large">(.*?)</span>', blk, re.S)
        listed = _clean(md.group(1)) if md else ""

        items.append({
            "id": listing_id,
            "title": title,
            "url": url,
            "price": price,
            "price_text": price_text,
            "shipping": shipping,
            "bids": bids,
            "auction": bids is not None,
            "best_offer": best_offer,
            "sponsored": sponsored,
            "condition": condition,
            "subtitle": subtitle,
            "attrs": attr_text,
            "listed": listed,
            "image": image,
        })
    return items


def search(query, pages=1, delay=2.0, **kw):
    out = []
    for page in range(1, pages + 1):
        url = build_url(query, page=page, **kw)
        try:
            page_html = fetch(url)
        except Exception as exc:  # noqa: BLE001
            print("  ! erreur %s (page %d): %s" % (query, page, exc))
            break
        found = parse_listings(page_html)
        out.extend(found)
        if len(found) < 20:
            break
        if page < pages:
            time.sleep(delay)
    return out
