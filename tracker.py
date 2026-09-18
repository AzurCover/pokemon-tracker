#!/usr/bin/env python3
"""Tracker d'annonces eBay : gros lots de cartes Pokémon à trier."""

import argparse
import html
import json
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ebay  # noqa: E402
import ebay_api  # noqa: E402
import leboncoin  # noqa: E402
import score as scoring  # noqa: E402
import telegram  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")
SEEN = os.path.join(HERE, "seen.json")
REPORT = os.path.join(HERE, "report.html")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)


def ebay_backend(cfg, forced=None):
    mode = forced or cfg.get("backend", "auto")
    if mode == "scrape":
        return ebay, "eBay (scraping HTML)"
    if mode == "api" or ebay_api.available():
        return ebay_api, "eBay (API officielle)"
    return ebay, "eBay (scraping HTML — sans clés API, bloqué au bout de ~6 requêtes)"


def collect(cfg, sources, pages, forced_backend=None, override_queries=None):
    found = {}
    for name in sources:
        if name == "ebay":
            backend, label = ebay_backend(cfg, forced_backend)
            queries = override_queries or cfg.get("queries", {}).get("ebay", [])
            pause = cfg.get("delay_between_queries", 2.5) if backend is ebay else 0.3
        elif name == "leboncoin":
            backend, label = leboncoin, "Leboncoin"
            queries = override_queries or cfg.get("queries", {}).get("leboncoin", [])
            pause = cfg.get("delay_between_queries", 2.5)
        else:
            print("source inconnue : %s" % name)
            continue

        print("\n== %s ==" % label)
        for i, query in enumerate(queries):
            print("→ %s" % query)
            try:
                items = backend.search(
                    query,
                    pages=pages,
                    sort=cfg.get("sort", "recent"),
                    site=cfg.get("site", "www.ebay.fr"),
                    min_price=None,  # local : une enchère démarre à 1 €
                    max_price=cfg.get("max_total") or None,
                    buy_it_now=cfg.get("buy_it_now", False),
                    location=cfg.get("location"),
                )
            except Exception as exc:  # noqa: BLE001
                print("   ! %s" % exc)
                continue
            print("   %d annonces" % len(items))
            for it in items:
                it.setdefault("source", name)
                if it["id"] not in found:
                    it["query"] = query
                    found[it["id"]] = it
            if i < len(queries) - 1:
                time.sleep(pause)
    return list(found.values())


def notify(count, best):
    title = "%d nouveau%s lot Pokémon" % (count, "x" if count > 1 else "")
    body = (best or "")[:120].replace('"', "'")
    try:
        subprocess.run(
            ["osascript", "-e",
             'display notification "%s" with title "%s" sound name "Glass"' % (body, title)],
            check=False, capture_output=True,
        )
    except Exception:  # noqa: BLE001
        pass


def fmt_row(it, is_new):
    tag = "NEW " if is_new else "    "
    ppc = "%.3f€/c" % it["price_per_card"] if it.get("price_per_card") else "   -   "
    cards = "%5d c." % it["cards"] if it.get("cards") else "   ?  "
    total = "%7.2f€" % it["total"] if it.get("total") else "   ?   "
    gems = ", ".join(it.get("gems", [])[:3])
    return "%s[%3d] %s %s %s | %s\n        %s\n        %s" % (
        tag, it["score"], total, cards, ppc, it["title"][:78], gems, it["url"])


def render_html(items, new_ids, cfg):
    rows = []
    for it in items:
        badges = []
        if it["id"] in new_ids:
            badges.append('<span class="b new">NOUVEAU</span>')
        if it.get("game"):
            badges.append('<span class="b game %s">%s</span>' % (it["game"], it["game"].upper()))
        if it.get("premium"):
            badges.append('<span class="b premium">PÉPITE</span>')
        if it.get("cards"):
            src = it.get("cards_origin")
            label = "%d cartes" % it["cards"]
            if src and src != "titre":
                label += " (~%s)" % src
            badges.append('<span class="b">%s</span>' % html.escape(label))
        if it.get("price_per_card"):
            cls = "good" if it["price_per_card"] <= 0.1 else ""
            badges.append('<span class="b %s">%.3f €/carte</span>' % (cls, it["price_per_card"]))
        if it.get("bids") is not None:
            badges.append('<span class="b">%d enchères</span>' % it["bids"])
        if it.get("best_offer"):
            badges.append('<span class="b">offre possible</span>')
        for b in it.get("bulk", []):
            badges.append('<span class="b bulk">%s</span>' % html.escape(b))
        for g in it.get("gems", []):
            badges.append('<span class="b gem">%s</span>' % html.escape(g))
        for f in it.get("flags", []):
            badges.append('<span class="b bad">%s</span>' % html.escape(f))

        ship = ""
        if it.get("shipping") == 0:
            ship = " + port gratuit"
        elif it.get("shipping"):
            ship = " + %.2f€ port" % it["shipping"]

        rows.append("""
<article class="card">
  <a href="{url}" target="_blank"><img loading="lazy" src="{img}" alt=""></a>
  <div class="body">
    <div class="score">{score}</div>
    <a class="title" href="{url}" target="_blank">{title}</a>
    <div class="price">{price}<span class="ship">{ship}</span></div>
    <div class="badges">{badges}</div>
    <div class="meta"><span class="src {srccls}">{src}</span> · {cond} · {listed} · <span class="q">{query}</span></div>
  </div>
</article>""".format(
            url=html.escape(it["url"]),
            img=html.escape(it.get("image") or ""),
            score=it["score"],
            title=html.escape(it["title"]),
            price=html.escape(it.get("price_text") or "?"),
            ship=ship,
            badges="".join(badges),
            src=html.escape((it.get("source") or "ebay").upper()),
            srccls=html.escape(it.get("source") or "ebay"),
            cond=html.escape(it.get("condition") or "—"),
            listed=html.escape(it.get("listed") or ""),
            query=html.escape(it.get("query") or ""),
        ))

    doc = """<!doctype html><html lang="fr"><meta charset="utf-8">
<title>Lots Pokémon — {date}</title>
<style>
:root {{ color-scheme: dark; }}
body {{ font: 15px/1.45 -apple-system, system-ui, sans-serif; background:#12141a; color:#e8eaf0; margin:0; padding:28px; }}
h1 {{ font-size:22px; margin:0 0 4px; }}
.sub {{ color:#8a90a2; margin-bottom:22px; font-size:13px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(330px,1fr)); gap:16px; align-items:start; }}
.card {{ background:#1a1d26; border:1px solid #262a36; border-radius:12px; overflow:hidden; display:flex; }}
.card img {{ width:120px; height:150px; flex:none; object-fit:cover; background:#262a36; }}
.body {{ padding:11px 13px; flex:1; min-width:0; position:relative; }}
.score {{ position:absolute; top:9px; right:11px; font-weight:700; font-size:12px; color:#ffb454; }}
.title {{ color:#e8eaf0; text-decoration:none; font-weight:600; font-size:13.5px; display:block; padding-right:30px; }}
.title:hover {{ color:#7aa2f7; }}
.price {{ margin:6px 0; font-size:16px; font-weight:700; color:#9ece6a; }}
.ship {{ font-size:11px; font-weight:400; color:#8a90a2; margin-left:5px; }}
.badges {{ display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px; }}
.b {{ font-size:10.5px; padding:2px 6px; border-radius:5px; background:#262a36; color:#b8bed0; }}
.b.new {{ background:#7aa2f7; color:#12141a; font-weight:700; }}
.b.gem {{ background:#2d2a1a; color:#ffb454; }}
.b.good {{ background:#1d2e1d; color:#9ece6a; }}
.b.bad {{ background:#3a1e1e; color:#f7768e; }}
.b.bulk {{ background:#1b2b33; color:#7dcfff; }}
.b.game {{ font-weight:700; letter-spacing:.4px; }}
.b.game.pokemon {{ background:#3a2f12; color:#ffd166; }}
.b.game.magic {{ background:#2a1f38; color:#c39bff; }}
.b.game.yugioh {{ background:#38241a; color:#ffa07a; }}
.b.premium {{ background:#ffb454; color:#12141a; font-weight:700; letter-spacing:.4px; }}
.src {{ font-weight:700; letter-spacing:.3px; }}
.src.leboncoin {{ color:#ff6e40; }}
.src.ebay {{ color:#7aa2f7; }}
.b.dim {{ opacity:.5; }}
.meta {{ font-size:11px; color:#6b7186; }}
.q {{ opacity:.7; }}
</style>
<h1>Lots de cartes Pokémon</h1>
<div class="sub">{n} annonces · {nn} nouvelles · généré le {date} · filtres : ≥{mc} cartes, {mint}–{maxt} €, ≤{mppc} €/carte</div>
<div class="grid">{rows}</div>
</html>""".format(
        n=len(items), nn=len(new_ids),
        date=datetime.now().strftime("%d/%m/%Y %H:%M"),
        mc=cfg.get("min_cards"), mint=cfg.get("min_total"),
        maxt=cfg.get("max_total"), mppc=cfg.get("max_price_per_card"),
        rows="".join(rows),
    )
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(doc)


def main():
    ap = argparse.ArgumentParser(description="Tracker eBay — gros lots de cartes Pokémon")
    ap.add_argument("--query", "-q", action="append", help="recherche ad hoc (remplace la config)")
    ap.add_argument("--pages", "-p", type=int, help="pages par recherche")
    ap.add_argument("--all", action="store_true", help="afficher aussi les annonces déjà vues")
    ap.add_argument("--open", action="store_true", help="ouvrir le rapport HTML")
    ap.add_argument("--reset", action="store_true", help="oublier l'historique")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--min-cards", type=int)
    ap.add_argument("--max-total", type=float)
    ap.add_argument("--min-score", type=int)
    ap.add_argument("--debug", action="store_true", help="montrer les annonces rejetées")
    ap.add_argument("--backend", choices=["auto", "api", "scrape"], help="backend eBay")
    ap.add_argument("--source", "-s", action="append",
                    choices=["ebay", "leboncoin"], help="limiter aux sources choisies")
    ap.add_argument("--telegram-setup", action="store_true",
                    help="appairer le bot Telegram puis quitter")
    ap.add_argument("--telegram-invite", action="store_true",
                    help="afficher le lien d'invitation à partager")
    args = ap.parse_args()

    if args.telegram_setup:
        telegram.setup()
        return

    if args.telegram_invite:
        link = telegram.invite_link()
        if not link:
            print("Bot non appairé : lance d'abord --telegram-setup")
            return
        print("\nLien d'invitation (à envoyer à la personne de ton choix) :\n")
        print("  %s\n" % link)
        for cid, who in telegram.recipients():
            print("  abonné : %s (%s)" % (who, cid))
        return

    cfg = load_json(CONFIG, {})
    if args.min_cards is not None:
        cfg["min_cards"] = args.min_cards
    if args.max_total is not None:
        cfg["max_total"] = args.max_total
    if args.min_score is not None:
        cfg["min_score"] = args.min_score

    if args.reset and os.path.exists(SEEN):
        os.remove(SEEN)
        print("historique effacé")

    seen = load_json(SEEN, {})
    sources = args.source or cfg.get("sources", ["ebay"])
    pages = args.pages or cfg.get("pages", 2)

    raw = collect(cfg, sources, pages, args.backend, args.query)
    print("\n%d annonces uniques récupérées" % len(raw))

    kept, rejected = [], []
    for it in raw:
        scoring.analyse(it, cfg)
        (kept if scoring.passes(it, cfg) else rejected).append(it)

    kept.sort(key=lambda x: (-x["score"], x.get("price_per_card") or 9e9))
    kept = kept[: cfg.get("top_n", 80)]

    new_ids = {it["id"] for it in kept if it["id"] not in seen}

    print("%d retenues (%d rejetées) · %d nouvelles\n" % (
        len(kept), len(rejected), len(new_ids)))

    if args.debug:
        print("--- rejetées ---")
        for it in rejected[:40]:
            print("  %-60s  %s" % (it["title"][:60], it.get("_reject")))
        print()

    show = kept if args.all else [it for it in kept if it["id"] in new_ids]
    if not show and not args.all:
        print("Aucune nouvelle annonce. (--all pour tout revoir)")
    for it in show:
        print(fmt_row(it, it["id"] in new_ids))
        print()

    render_html(kept, new_ids, cfg)
    print("Rapport : %s" % REPORT)

    for it in kept:
        seen[it["id"]] = {
            "title": it["title"],
            "price": it.get("total"),
            "first_seen": seen.get(it["id"], {}).get(
                "first_seen", datetime.now().isoformat(timespec="seconds")),
        }
    save_json(SEEN, seen)

    fresh = [it for it in kept if it["id"] in new_ids]
    if not args.no_notify and telegram.available():
        for event in telegram.sync_subscribers():
            print("Telegram : %s" % event)

    if fresh and not args.no_notify:
        if cfg.get("notify", True):
            notify(len(fresh), fresh[0]["title"])
        if telegram.available():
            n = telegram.send_batch(fresh, limit=cfg.get("telegram_max_per_run", 8))
            print("Telegram : %d annonce(s) envoyée(s) à %d destinataire(s)"
                  % (n, len(telegram.recipients())))

    if args.open:
        subprocess.run(["open", REPORT], check=False)


if __name__ == "__main__":
    main()
