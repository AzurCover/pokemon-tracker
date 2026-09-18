"""Notifications Telegram : un message par nouvelle annonce, photo + bouton."""

import json
import os
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CREDS = os.path.join(HERE, "telegram.json")
API = "https://api.telegram.org/bot%s/%s"


def get_credentials():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat:
        return token, chat
    if os.path.exists(CREDS):
        with open(CREDS, encoding="utf-8") as fh:
            data = json.load(fh)
        token = token or str(data.get("bot_token") or "").strip()
        chat = chat or str(data.get("chat_id") or "").strip()
    return token, chat


def available():
    token, chat = get_credentials()
    return bool(token and chat)


def call(method, payload, token=None):
    token = token or get_credentials()[0]
    if not token:
        raise RuntimeError("aucun bot_token Telegram")
    req = urllib.request.Request(
        API % (token, method),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError("Telegram %s : %s" % (exc.code, detail)) from None


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def caption(it):
    lines = ["<b>%s</b>" % esc((it.get("title") or "")[:180])]

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
    """Envoie les meilleures annonces, résume le reste. Renvoie le nb envoyé."""
    token, chat_id = get_credentials()
    sent = 0
    for it in items[:limit]:
        try:
            send_item(it, token, chat_id)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            print("  ! Telegram : %s" % exc)
            break
        time.sleep(delay)

    rest = len(items) - sent
    if sent and rest > 0:
        try:
            call("sendMessage", {
                "chat_id": chat_id,
                "text": "<i>+ %d autre%s annonce%s dans le rapport HTML</i>" % (
                    rest, "s" if rest > 1 else "", "s" if rest > 1 else ""),
                "parse_mode": "HTML"}, token)
        except Exception:  # noqa: BLE001
            pass
    return sent


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
