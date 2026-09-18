"""Écoute Telegram en continu : mot de passe, abonnements, choix des jeux.

Processus séparé du tracker, parce qu'un bouton doit répondre tout de suite et
que le tracker, lui, ne passe que toutes les 10 minutes. C'est aussi le seul
consommateur de getUpdates : deux processus qui interrogent Telegram se volent
les messages.
"""

import hmac
import signal
import sys
import time

import telegram

MAX_TRIES = 5          # essais de mot de passe avant blocage
BLOCK_SECONDS = 3600

POLL = 25              # durée du long polling Telegram
WATCHDOG = POLL + 25   # au-delà, la connexion est considérée comme morte

ASK_PASSWORD = ("Ce bot est privé.\n\nEnvoie-moi le mot de passe pour recevoir "
                "les annonces.")
WELCOME = ("<b>C'est bon, tu as accès.</b>\n\n"
           "Je surveille eBay et Leboncoin en continu et je t'envoie chaque "
           "nouveau gros lot de cartes en vrac : prix par carte, nombre de "
           "cartes, indices de pépite et lien direct.\n\n"
           "Choisis ce que tu veux suivre :")
MENU = "Quels jeux veux-tu suivre ?"


def log(msg):
    # l'heure est le seul indice quand le bot se tait : c'est ce qui distingue
    # « personne n'a écrit » de « le processus ne lit plus rien »
    print("%s %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def games_markup(selected):
    rows = [[{"text": "%s %s" % ("✅" if key in selected else "▫️",
                                 telegram.GAME_LABELS[key]),
              "callback_data": "g:%s" % key}] for key in telegram.ALL_GAMES]
    rows.append([{"text": "Terminé", "callback_data": "done"}])
    return {"inline_keyboard": rows}


def say(token, chat_id, text, markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if markup:
        payload["reply_markup"] = markup
    try:
        return telegram.call("sendMessage", payload, token)
    except RuntimeError as exc:
        log("  ! envoi à %s : %s" % (chat_id, exc))
        return None


def find_sub(state, cid):
    """Entrée d'abonné : le propriétaire est stocké à part, à la racine."""
    if cid == str(state.get("chat_id") or ""):
        return state
    for sub in state.get("subscribers") or []:
        if str(sub.get("id")) == cid:
            return sub
    return None


def handle_message(state, token, msg):
    chat = msg.get("chat") or {}
    cid = str(chat.get("id") or "")
    text = (msg.get("text") or "").strip()
    if not cid or not text:
        return

    name = chat.get("first_name") or chat.get("title") or "invité"
    cmd = text.split()[0].split("@")[0].lower()
    sub = find_sub(state, cid)

    if cmd == "/stop":
        if sub is not None and cid != str(state.get("chat_id") or ""):
            state["subscribers"] = [s for s in state.get("subscribers") or []
                                    if str(s.get("id")) != cid]
            log("− %s (%s) s'est désabonné" % (name, cid))
        say(token, cid, "Très bien, je n'envoie plus rien. "
                        "<i>/start pour revenir.</i>")
        return

    if sub is not None:
        if cmd in ("/start", "/jeux"):
            say(token, cid, MENU, games_markup(sub.get("games")
                                               or telegram.ALL_GAMES))
        else:
            say(token, cid, "<i>/jeux</i> pour changer ce que tu suis, "
                            "<i>/stop</i> pour ne plus rien recevoir.")
        return

    # --- pas encore abonné : porte d'entrée ---
    blocked = (state.get("blocked") or {}).get(cid, 0)
    if time.time() < blocked:
        return

    if cmd == "/start":
        say(token, cid, ASK_PASSWORD)
        return

    expected = state.get("password") or ""
    if expected and hmac.compare_digest(text.lower().encode("utf-8"),
                                        expected.lower().encode("utf-8")):
        state.setdefault("subscribers", []).append(
            {"id": cid, "name": name, "games": list(telegram.ALL_GAMES)})
        (state.get("tries") or {}).pop(cid, None)
        log("+ %s (%s) vient de s'abonner" % (name, cid))
        # le mot de passe ne traîne pas dans l'historique de la conversation
        try:
            telegram.call("deleteMessage",
                          {"chat_id": cid, "message_id": msg["message_id"]}, token)
        except RuntimeError:
            pass
        say(token, cid, WELCOME, games_markup(telegram.ALL_GAMES))
        return

    tries = state.setdefault("tries", {})
    tries[cid] = tries.get(cid, 0) + 1
    if tries[cid] >= MAX_TRIES:
        state.setdefault("blocked", {})[cid] = time.time() + BLOCK_SECONDS
        tries.pop(cid, None)
        say(token, cid, "Trop d'essais. Réessaie dans une heure.")
        log("! %s (%s) bloqué après %d essais" % (name, cid, MAX_TRIES))
    else:
        say(token, cid, "Mot de passe incorrect.")


def handle_callback(state, token, cb):
    cid = str(((cb.get("message") or {}).get("chat") or {}).get("id") or "")
    msg_id = (cb.get("message") or {}).get("message_id")
    data = cb.get("data") or ""
    sub = find_sub(state, cid)

    def close(text=None):
        # à répondre dans les secondes qui suivent, sinon le bouton reste à tourner
        try:
            telegram.call("answerCallbackQuery",
                          {"callback_query_id": cb["id"], "text": text or ""}, token)
        except RuntimeError as exc:
            log("  ! answerCallbackQuery : %s" % exc)

    if sub is None:
        close("Envoie d'abord le mot de passe.")
        return

    games = list(sub.get("games") or telegram.ALL_GAMES)

    if data == "done":
        close()
        labels = " · ".join(telegram.GAME_LABELS[g] for g in telegram.ALL_GAMES
                            if g in games)
        edit(token, cid, msg_id, "editMessageText", {
            "parse_mode": "HTML",
            "text": "Tu suis : <b>%s</b>\n\n<i>/jeux pour changer.</i>" % labels})
        return

    if data.startswith("g:"):
        key = data[2:]
        if key in games:
            if len(games) == 1:
                close("Il faut garder au moins un jeu.")
                return
            games.remove(key)
        else:
            games.append(key)
        sub["games"] = [g for g in telegram.ALL_GAMES if g in games]
        telegram.save_state(state)
        close()
        log("  %s → %s" % (cid, "+".join(sub["games"])))
        edit(token, cid, msg_id, "editMessageReplyMarkup",
             {"reply_markup": games_markup(sub["games"])})


def edit(token, chat_id, msg_id, method, extra):
    payload = {"chat_id": chat_id, "message_id": msg_id}
    payload.update(extra)
    try:
        telegram.call(method, payload, token)
    except RuntimeError as exc:
        log("  ! %s : %s" % (method, exc))


def wedged(_sig, _frame):
    """Le Mac s'est endormi : la connexion est morte mais urlopen l'ignore."""
    raise OSError("aucune réponse de Telegram depuis %d s" % WATCHDOG)


def main():
    state = telegram.load_state()
    token = str(state.get("bot_token") or "").strip()
    if not token:
        log("Bot non appairé : lance d'abord tracker.py --telegram-setup")
        return 1

    telegram.get_password()        # en crée un au premier démarrage
    try:
        telegram.describe()
    except RuntimeError as exc:    # setMyName est limité à quelques appels/jour
        log("! description du bot : %s" % exc)
    signal.signal(signal.SIGALRM, wedged)
    log("Écoute de Telegram démarrée.")

    while True:
        state = telegram.load_state()
        payload = {"timeout": POLL, "limit": 20,
                   "allowed_updates": ["message", "callback_query"]}
        if state.get("offset"):
            payload["offset"] = state["offset"]
        try:
            signal.alarm(WATCHDOG)
            res = telegram.call("getUpdates", payload, token, timeout=POLL + 15)
        except (RuntimeError, OSError) as exc:
            log("! getUpdates : %s" % exc)
            time.sleep(10)
            continue
        finally:
            signal.alarm(0)

        updates = res.get("result") or []
        for upd in updates:
            state["offset"] = upd["update_id"] + 1
            kind = "message" if upd.get("message") else next(
                (k for k in upd if k != "update_id"), "?")
            detail = ((upd.get("message") or {}).get("text")
                      or (upd.get("callback_query") or {}).get("data") or "")
            log("> %s %s" % (kind, detail[:40]))
            try:
                if upd.get("message"):
                    handle_message(state, token, upd["message"])
                elif upd.get("callback_query"):
                    handle_callback(state, token, upd["callback_query"])
            except Exception as exc:  # noqa: BLE001
                log("! update %s : %s" % (upd.get("update_id"), exc))
        if updates:
            telegram.save_state(state)


if __name__ == "__main__":
    sys.exit(main() or 0)
