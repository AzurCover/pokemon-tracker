"""Notifications Telegram : un message par nouvelle annonce, photo + bouton."""

import json
import os
import secrets
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CREDS = os.path.join(HERE, "telegram.json")
API = "https://api.telegram.org/bot%s/%s"


def load_state():
    if os.path.exists(CREDS):
        with open(CREDS, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_state(state):
    # écriture atomique : bot.py écrit pendant que tracker.py lit
    tmp = CREDS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, CREDS)


def get_credentials():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat:
        return token, chat
    data = load_state()
    token = token or str(data.get("bot_token") or "").strip()
    chat = chat or str(data.get("chat_id") or "").strip()
    return token, chat


ALL_GAMES = ["pokemon", "magic", "yugioh"]
GAME_LABELS = {"pokemon": "Pokémon", "magic": "Magic", "yugioh": "Yu-Gi-Oh"}


def recipients():
    """(chat_id, nom, jeux suivis) du propriétaire puis des invités."""
    state = load_state()
    token, owner = get_credentials()
    out = [(owner, "toi", state.get("games") or ALL_GAMES)] if owner else []
    for sub in state.get("subscribers") or []:
        cid = str(sub.get("id") or "")
        if cid and cid != owner:
            out.append((cid, sub.get("name") or "invité",
                        sub.get("games") or ALL_GAMES))
    return out


def available():
    token, chat = get_credentials()
    return bool(token and chat)


def get_password(create=True):
    """Mot de passe d'accès au bot, tiré au sort au premier appel."""
    state = load_state()
    if not state:
        return None
    pwd = state.get("password")
    if not pwd and create:
        pwd = "cartes-%04d" % secrets.randbelow(10000)
        state["password"] = pwd
        save_state(state)
    return pwd


def set_password(pwd):
    state = load_state()
    state["password"] = pwd.strip()
    save_state(state)
    return state["password"]


def bot_link(token=None):
    username = (call("getMe", {}, token).get("result") or {}).get("username", "")
    return "https://t.me/%s" % username


def call(method, payload, token=None, timeout=20):
    token = token or get_credentials()[0]
    if not token:
        raise RuntimeError("aucun bot_token Telegram")
    req = urllib.request.Request(
        API % (token, method),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError("Telegram %s : %s" % (exc.code, detail)) from None


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def caption(it):
    lines = []
    if it.get("premium"):
        lines.append("🔥 <b>PÉPITE VINTAGE</b>")
    lines.append("<b>%s</b>" % esc((it.get("title") or "")[:180]))

    money = []
    if it.get("total"):
        money.append("%.2f €" % it["total"])
    if it.get("cards"):
        money.append("%d cartes" % it["cards"])
    if it.get("price_per_card"):
        money.append("<b>%.3f €/carte</b>" % it["price_per_card"])
    if money:
        lines.append(" · ".join(money))

    tags = list(it.get("gems") or []) + list(it.get("bulk") or [])
    if tags:
        lines.append(esc(" · ".join(tags[:6])))

    foot = [(it.get("game") or "").upper(), "score %d" % it.get("score", 0),
            (it.get("source") or "").upper()]
    if it.get("auction"):
        bids = it.get("bids")
        foot.append("enchère%s" % (" · %d mises" % bids if bids else ""))
    if it.get("subtitle"):
        foot.append(it["subtitle"])
    lines.append("<i>%s</i>" % esc(" · ".join(x for x in foot if x)))
    return "\n".join(lines)


def send_item(it, token=None, chat_id=None):
    creds = get_credentials()
    token = token or creds[0]
    chat_id = chat_id or creds[1]
    text = caption(it)
    markup = {"inline_keyboard": [[{"text": "Voir l'annonce", "url": it["url"]}]]}

    image = it.get("image") or ""
    if image.startswith("http"):
        try:
            return call("sendPhoto", {
                "chat_id": chat_id, "photo": image, "caption": text,
                "parse_mode": "HTML", "reply_markup": markup}, token)
        except RuntimeError:
            pass  # Telegram refuse certaines miniatures : on retombe sur le texte

    return call("sendMessage", {
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "reply_markup": markup}, token)


def send_batch(items, limit=8, delay=1.2):
    """Envoie les meilleures annonces à tous les abonnés. Renvoie le nb envoyé."""
    token, _ = get_credentials()
    targets = recipients()
    if not targets:
        return 0

    sent = 0
    for it in items[:limit]:
        delivered = False
        for cid, who, games in targets:
            if it.get("game") not in games:
                continue
            try:
                send_item(it, token, cid)
                delivered = True
            except Exception as exc:  # noqa: BLE001
                print("  ! Telegram (%s) : %s" % (who, exc))
            time.sleep(delay)
        sent += 1 if delivered else 0

    rest = len(items) - sent
    if sent and rest > 0:
        for cid, _who, _games in targets:
            try:
                call("sendMessage", {
                    "chat_id": cid,
                    "text": "<i>+ %d autre%s annonce%s dans le rapport HTML</i>" % (
                        rest, "s" if rest > 1 else "", "s" if rest > 1 else ""),
                    "parse_mode": "HTML"}, token)
            except Exception:  # noqa: BLE001
                pass
    return sent


def describe():
    """Renseigne nom, descriptions et commandes du bot."""
    token = get_credentials()[0]
    call("setMyName", {"name": "Card Tracker"}, token)
    call("setMyShortDescription", {"short_description":
         "Repère les gros lots de cartes Pokémon, Magic et Yu-Gi-Oh en vrac "
         "sur eBay et Leboncoin, dès leur mise en ligne."}, token)
    call("setMyDescription", {"description":
         "Je surveille eBay et Leboncoin en continu et je t'envoie chaque "
         "nouveau gros lot de cartes en vrac qui vaut le coup.\n\n"
         "Pour chaque annonce : le prix par carte, le nombre de cartes, les "
         "indices de pépite (Wizards, 1ère édition, liste réservée, vintage) "
         "et le lien direct.\n\n"
         "Pokémon · Magic · Yu-Gi-Oh vintage"}, token)
    call("setMyCommands", {"commands": [
        {"command": "start", "description": "recevoir les annonces"},
        {"command": "jeux", "description": "choisir Pokémon, Magic, Yu-Gi-Oh"},
        {"command": "stop", "description": "ne plus rien recevoir"},
    ]}, token)


def discover_chat_id(token, wait=90):
    """Attend un message envoyé au bot et en extrait le chat_id."""
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            res = call("getUpdates", {"timeout": 10, "limit": 5}, token)
        except RuntimeError as exc:
            print(exc)
            return None, None
        for upd in reversed(res.get("result") or []):
            msg = upd.get("message") or upd.get("channel_post") or {}
            chat = msg.get("chat") or {}
            if chat.get("id"):
                name = chat.get("first_name") or chat.get("title") or ""
                return str(chat["id"]), name
        time.sleep(2)
    return None, None


def setup():
    print("\n=== Appairage Telegram ===")
    print("1. Dans Telegram, ouvre @BotFather → /newbot → choisis un nom")
    print("2. Il te renvoie un token du style 1234567890:AAE...\n")
    token = input("Colle le token ici : ").strip()
    if not token:
        print("annulé")
        return False

    try:
        me = call("getMe", {}, token)
    except RuntimeError as exc:
        print("Token refusé — %s" % exc)
        return False
    username = (me.get("result") or {}).get("username", "?")
    print("\nBot reconnu : @%s" % username)
    print("3. Ouvre https://t.me/%s et envoie-lui n'importe quel message." % username)
    print("   (j'attends...)")

    chat_id, name = discover_chat_id(token)
    if not chat_id:
        print("Aucun message reçu. Relance la commande après avoir écrit au bot.")
        return False

    with open(CREDS, "w", encoding="utf-8") as fh:
        json.dump({"bot_token": token, "chat_id": chat_id}, fh, indent=1)
    print("\nAppairé avec %s (chat %s) → telegram.json" % (name or "toi", chat_id))

    call("sendMessage", {
        "chat_id": chat_id,
        "text": "<b>Tracker Pokémon connecté.</b>\n"
                "Tu recevras ici chaque nouveau gros lot détecté.",
        "parse_mode": "HTML"}, token)
    print("Message de test envoyé.")
    return True


if __name__ == "__main__":
    setup()
