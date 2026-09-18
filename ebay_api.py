"""Backend API officielle eBay (Browse API). Gratuit, 5000 appels/jour.

Identifiants : https://developer.ebay.com/my/keys  (clés *Production*)
Puis, au choix :
  export EBAY_CLIENT_ID=...  EBAY_CLIENT_SECRET=...
ou un fichier credentials.json : {"client_id": "...", "client_secret": "..."}
"""

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CREDS = os.path.join(HERE, "credentials.json")
TOKEN_CACHE = os.path.join(HERE, ".token.json")

OAUTH_URL = "https://api.ebay.com/identity/v2/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"

MARKETPLACE = {
    "www.ebay.fr": "EBAY_FR",
    "www.ebay.com": "EBAY_US",
    "www.ebay.de": "EBAY_DE",
    "www.ebay.be": "EBAY_FR",
    "www.ebay.it": "EBAY_IT",
    "www.ebay.es": "EBAY_ES",
    "www.ebay.co.uk": "EBAY_GB",
}

SORT = {"recent": "newlyListed", "prix": "price", "prix_desc": "-price", "fin_proche": "endingSoonest"}


def get_credentials():
    cid = os.environ.get("EBAY_CLIENT_ID")
    secret = os.environ.get("EBAY_CLIENT_SECRET")
    if cid and secret:
        return cid.strip(), secret.strip()
    if os.path.exists(CREDS):
        with open(CREDS, encoding="utf-8") as fh:
            data = json.load(fh)
        cid = (data.get("client_id") or "").strip()
        secret = (data.get("client_secret") or "").strip()
        if cid and secret:
            return cid, secret
    return None, None


def available():
    return all(get_credentials())


def _post(url, data, headers):
    req = urllib.request.Request(url, data=data.encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def get_token(force=False):
    if not force and os.path.exists(TOKEN_CACHE):
        try:
            with open(TOKEN_CACHE, encoding="utf-8") as fh:
                cached = json.load(fh)
            if cached.get("expires_at", 0) > time.time() + 60:
                return cached["token"]
        except Exception:  # noqa: BLE001
            pass

    cid, secret = get_credentials()
    if not cid:
        raise RuntimeError("Identifiants eBay absents (voir ebay_api.py)")

    basic = base64.b64encode(("%s:%s" % (cid, secret)).encode()).decode()
    payload = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPE})
    try:
        res = _post(OAUTH_URL, payload, {
            "Authorization": "Basic %s" % basic,
            "Content-Type": "application/x-www-form-urlencoded",
        })
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:300]
        raise RuntimeError("OAuth eBay a échoué (%s) : %s" % (exc.code, body))

    token = res["access_token"]
    with open(TOKEN_CACHE, "w", encoding="utf-8") as fh:
        json.dump({"token": token, "expires_at": time.time() + int(res.get("expires_in", 7200))}, fh)
    return token


def _normalise(node):
    price = None
    price_text = ""
    p = node.get("price") or {}
    if p.get("value") is not None:
        price = float(p["value"])
        price_text = "%.2f %s" % (price, p.get("currency", "EUR"))

    shipping = None
    opts = node.get("shippingOptions") or []
    if opts:
        cost = (opts[0] or {}).get("shippingCost") or {}
        if cost.get("value") is not None:
            shipping = float(cost["value"])

    buying = node.get("buyingOptions") or []
    image = ((node.get("image") or {}).get("imageUrl")
             or ((node.get("thumbnailImages") or [{}])[0] or {}).get("imageUrl") or "")

    seller = (node.get("seller") or {}).get("username", "")
    loc = (node.get("itemLocation") or {}).get("country", "")

    attrs = []
    if shipping == 0:
        attrs.append("Livraison gratuite")
    elif shipping:
        attrs.append("+%.2f EUR de frais de livraison" % shipping)
    if "BEST_OFFER" in buying:
        attrs.append("ou Faire une offre")
    if node.get("bidCount"):
        attrs.append("%s enchères" % node["bidCount"])

    return {
        "id": str(node.get("legacyItemId") or node.get("itemId", "")),
        "title": node.get("title", ""),
        "url": node.get("itemWebUrl", ""),
        "price": price,
        "price_text": price_text,
        "shipping": shipping,
        "bids": node.get("bidCount"),
        "auction": "AUCTION" in buying,
        "best_offer": "BEST_OFFER" in buying,
        "sponsored": False,
        "condition": node.get("condition", ""),
        "subtitle": "%s · %s" % (seller, loc),
        "attrs": " | ".join(attrs),
        "listed": (node.get("itemCreationDate") or "")[:16].replace("T", " "),
        "image": image,
    }


def search(query, pages=1, delay=0.4, sort="recent", site="www.ebay.fr",
           min_price=None, max_price=None, buy_it_now=False, location=None,
           category_ids=None, per_page=200):
    token = get_token()
    headers = {
        "Authorization": "Bearer %s" % token,
        "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE.get(site, "EBAY_FR"),
        "Accept": "application/json",
    }

    filters = []
    if min_price is not None or max_price is not None:
        lo = "" if min_price is None else "%g" % min_price
        hi = "" if max_price is None else "%g" % max_price
        filters.append("price:[%s..%s]" % (lo, hi))
        filters.append("priceCurrency:EUR")
    if buy_it_now:
        filters.append("buyingOptions:{FIXED_PRICE}")
    if location == "fr":
        filters.append("itemLocationCountry:FR")

    out = []
    for page in range(pages):
        params = {
            "q": query,
            "limit": min(per_page, 200),
            "offset": page * min(per_page, 200),
            "sort": SORT.get(sort, "newlyListed"),
        }
        if filters:
            params["filter"] = ",".join(filters)
        if category_ids:
            params["category_ids"] = ",".join(str(c) for c in category_ids)

        url = "%s?%s" % (SEARCH_URL, urllib.parse.urlencode(params))
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300]
            print("  ! API %s (page %d) : %s %s" % (query, page + 1, exc.code, body))
            break

        summaries = data.get("itemSummaries") or []
        out.extend(_normalise(n) for n in summaries)
        if len(summaries) < params["limit"]:
            break
        if page < pages - 1:
            time.sleep(delay)
    return [i for i in out if i["id"] and i["title"]]
