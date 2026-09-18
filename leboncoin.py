"""Backend Leboncoin : les annonces sont dans le JSON __NEXT_DATA__ de la page."""

import gzip
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

SORT = {"recent": "time", "prix": "price", "pertinence": "relevance"}


def build_url(query, page=1, sort="recent", min_price=None, max_price=None, **_):
    params = {"text": query}
    if sort in SORT:
        params["sort"] = SORT[sort]
        if SORT[sort] == "time":
            params["order"] = "desc"
    if min_price is not None or max_price is not None:
        params["price"] = "%s-%s" % (
            int(min_price) if min_price is not None else "min",
            int(max_price) if max_price is not None else "max",
        )
    if page > 1:
        params["page"] = page
    return "https://www.leboncoin.fr/recherche?%s" % urllib.parse.urlencode(params)


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


def _find_ads(node):
    if isinstance(node, dict):
        for key, val in node.items():
            if key == "ads" and isinstance(val, list) and val:
                return val
            found = _find_ads(val)
            if found is not None:
                return found
    elif isinstance(node, list):
        for val in node:
            found = _find_ads(val)
            if found is not None:
                return found
    return None


def parse_listings(page_html):
    m = NEXT_DATA.search(page_html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return []
    ads = _find_ads(data) or []

    items = []
    for ad in ads:
        if not isinstance(ad, dict) or not ad.get("list_id"):
            continue
        price = None
        raw_price = ad.get("price")
        if isinstance(raw_price, list) and raw_price:
            price = float(raw_price[0])
        elif isinstance(raw_price, (int, float)):
            price = float(raw_price)

        loc = ad.get("location") or {}
        where = loc.get("city_label") or loc.get("city") or ""
        dept = loc.get("department_name") or ""
        images = ad.get("images") or {}

        items.append({
            "id": "lbc-%s" % ad["list_id"],
            "title": ad.get("subject", ""),
            "url": ad.get("url", ""),
            "price": price,
            "price_text": ("%.0f EUR" % price) if price is not None else "",
            "shipping": None,
            "bids": None,
            "auction": False,
            "best_offer": False,
            "sponsored": False,
            "condition": "",
            "subtitle": " · ".join(x for x in [where, dept] if x),
            "attrs": ad.get("category_name", ""),
            "listed": (ad.get("first_publication_date") or "")[:16],
            "image": images.get("small_url") or images.get("thumb_url") or "",
            "source": "leboncoin",
        })
    return items


def search(query, pages=1, delay=3.0, sort="recent", min_price=None,
           max_price=None, **_):
    out = []
    for page in range(1, pages + 1):
        url = build_url(query, page=page, sort=sort,
                        min_price=min_price, max_price=max_price)
        try:
            page_html = fetch(url)
        except Exception as exc:  # noqa: BLE001
            print("  ! leboncoin %s (page %d) : %s" % (query, page, exc))
            break
        found = parse_listings(page_html)
        out.extend(found)
        if len(found) < 20:
            break
        if page < pages:
            time.sleep(delay)
    return out
