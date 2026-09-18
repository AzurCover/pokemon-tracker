# Tracker multi-sites — gros lots de cartes Pokémon, Magic & Yu-Gi-Oh

Sources actives : **eBay** (API) et **Leboncoin** (fonctionne sans clé).

Surveille les annonces eBay de lots en vrac, calcule le **prix par carte**, repère les
indices de pépites (Wizards, 1ère édition, années 90, holos, grenier/succession) et ne
te signale que les **nouvelles** annonces depuis le dernier passage.

## 1. Brancher l'API eBay (indispensable pour eBay uniquement)

Leboncoin marche tout de suite, sans rien configurer. Cette étape ne concerne qu'eBay.

Le scraping direct des pages eBay fonctionne quelques requêtes puis l'IP est bloquée
(HTTP 403). L'API officielle est gratuite : 5 000 appels/jour, largement suffisant.

1. Crée un compte sur https://developer.ebay.com (gratuit).
2. Va sur https://developer.ebay.com/my/keys
3. Récupère le **keyset Production** : `App ID (Client ID)` et `Cert ID (Client Secret)`.
4. Copie-les dans `credentials.json` :

```json
{ "client_id": "TonAppID", "client_secret": "TonCertID" }
```

Le tracker bascule automatiquement sur l'API dès que le fichier est rempli.

## 2. Lancer

```bash
cd ~/pokemon-tracker

python3 tracker.py                  # toutes les sources + rapport HTML
python3 tracker.py -s leboncoin     # une seule source (marche sans clés)
python3 tracker.py --open           # ouvre le rapport dans le navigateur
python3 tracker.py --all            # réaffiche tout, pas que les nouveautés
python3 tracker.py --debug          # explique pourquoi chaque annonce est rejetée
python3 tracker.py -q "vrac pokemon 5kg" -p 3
python3 tracker.py --min-cards 500 --max-total 150
python3 tracker.py --reset          # oublie l'historique
```

## 3. Notifications Telegram

Pour recevoir chaque nouvelle annonce sur le téléphone (photo, prix, €/carte, lien) :

```bash
python3 tracker.py --telegram-setup
```

La commande demande un token @BotFather, puis récupère toute seule le `chat_id`
dès que tu écris au bot. Tout est stocké dans `telegram.json`.

En CI (GitHub Actions), les variables `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`
prennent le relais du fichier.

Par passage, seules les 8 meilleures nouveautés partent en message (réglable via
`telegram_max_per_run`), le reste est résumé en une ligne.

### Partager le bot

```bash
python3 tracker.py --telegram-share            # lien, mot de passe, abonnés
python3 tracker.py --telegram-password secret  # changer le mot de passe
```

Tu envoies le lien **et** le mot de passe. La personne ouvre le bot, tape le mot de
passe, et choisit tout de suite les jeux qu'elle veut suivre avec trois boutons
(Pokémon / Magic / Yu-Gi-Oh). Chacun ne reçoit que ce qu'il a coché ; `/jeux` permet
d'en changer à tout moment, `/stop` de se désabonner.

Un bot Telegram est public par nature : n'importe qui tombant sur `@ton_bot` peut lui
écrire. C'est le mot de passe qui filtre, pas l'obscurité du lien. Au bout de 5 essais
ratés, l'importun est ignoré pendant une heure, et le message contenant le mot de passe
est effacé de la conversation une fois validé.

**Ne partage jamais le token**, seulement le lien : le token donne le contrôle total
du bot. S'il fuite, `/revoke` dans @BotFather en génère un nouveau, puis :

```bash
python3 tracker.py --telegram-token    # saisie masquée, abonnés conservés
```

Le bot reprend de lui-même à la minute qui suit : il relit le token à chaque passage.
N'utilise pas `--telegram-setup` pour ça, il refait tout l'appairage.

Les réponses doivent être immédiates, alors qu'un passage du tracker n'a lieu que
toutes les 10 minutes : l'écoute vit donc dans un **processus séparé** (`bot.py`,
LaunchAgent `com.maxence.pokemon-bot`, relancé automatiquement s'il tombe).

```bash
launchctl list | grep pokemon-bot   # doit afficher un PID
tail -f bot.log                     # abonnements et désabonnements en direct
```

C'est aussi le seul processus autorisé à lire les messages : deux programmes qui
appellent `getUpdates` en même temps se volent les messages l'un à l'autre.

L'apparence du bot (nom, description, commandes) est posée par `telegram.describe()`,
appelée au démarrage de `bot.py`. La photo de profil, elle, n'est pas modifiable par
l'API : elle passe obligatoirement par @BotFather → *Edit Bot* → *Edit Botpic*, avec
`bot-logo.png`.

## 4. Régler les filtres

Tout est dans `config.json` :

| clé | rôle |
|---|---|
| `sources` | `["ebay", "leboncoin"]` |
| `queries` | les recherches, par source |
| `games` | jeux surveillés : `["pokemon", "magic", "yugioh"]` — une annonce qui n'en mentionne aucun est écartée |
| `require_bulk_hint_when_unknown` | sans nombre de cartes, exiger un indice de volume |
| `min_cards` | nombre de cartes minimum (défaut 100) |
| `min_total` / `max_total` | fourchette de prix en € (port inclus) |
| `max_price_per_card` | plafond €/carte (défaut 0.50) |
| `premium_gem_score` | score d'indices vintage à partir duquel une annonce échappe aux filtres de volume (défaut 12) |
| `min_score` | sévérité du tri (monte-le si trop de bruit) |
| `exclude_keywords` | mots qui disqualifient une annonce |
| `keep_unknown_count` | garder les annonces sans nombre de cartes lisible |
| `location` | `null`, `"fr"` ou `"eu"` |

**Les enchères échappent aux planchers de prix** : un lot de 1000 cartes qui démarre à
1 € serait sinon éliminé, alors que c'est exactement la bonne affaire à surveiller.

**Les annonces « pépite » échappent aux filtres de volume.** Quand les seuls indices de
pépite d'un titre totalisent `premium_gem_score` ou plus — « dual lands liste réservée
1994 » (14), « Yu-Gi-Oh 1ère édition LOB 2002 » (18) — ni `min_cards` ni le plafond
€/carte ne s'appliquent : sur ce segment le vendeur ne chiffre jamais ses cartes, et
ces annonces se faisaient jeter faute de volume annoncé. Le plafond `max_total`, les
mots exclus et les signaux douteux, eux, continuent de s'appliquer. Le passe-droit
exige un contexte de lot (lot, vrac, collection, classeur… ou un nombre de cartes) :
une belle carte seule, même gradée 1ère édition, ne se trie pas et reste écartée.

## 5. Automatiser

**Leboncoin — sur le Mac** (LaunchAgent déjà installé, passage toutes les 10 min) :

```bash
launchctl list | grep pokemon                     # vérifier qu'il tourne
tail -f run.log                                   # suivre en direct
launchctl unload ~/Library/LaunchAgents/com.maxence.pokemon-tracker.plist   # arrêter
```

Il n'interroge que 2 recherches larges triées par date, 1 page : sur une simple
surveillance, des recherches qui se chevauchent n'apportent rien et multiplient
le risque de blacklist DataDome sur ton IP.

**eBay — sur GitHub Actions** (`.github/workflows/track.yml`), passage toutes les
10 min, gratuit et 24/7. Les identifiants vivent dans les *secrets* du repo.

Leboncoin **ne peut pas** tourner dans le cloud : DataDome renvoie 403 sur toute IP
de datacenter, y compris sur la page d'accueil et avec cookies de session. Il faut
une IP résidentielle, donc une machine à la maison.

## Comment le score est calculé

- **Volume** : +1 à +6 selon le nombre de cartes (1000+ = +5, 2000+ = +6)
- **Prix/carte** : +6 sous 0,04 € — +4 sous 0,08 € — −3 au-dessus de 0,60 €
- **Indices de pépite communs** : vintage +3, grenier/succession +3, gradée +3, holo/foil +2
- **Pépites Pokémon** : Wizards/WOTC +5, 1ère édition +5, 1996-2003 +4, set vintage +4, GX/VMAX +2
- **Pépites Magic** : liste réservée/duales +6, Alpha/Beta/P9 +6, sets 1993-95 +5,
  Revised +4, années 90 +4, fetch/shocklands +3
- **Pépites Yu-Gi-Oh** : LOB +6, sets 2002-03 +5, 1ère édition +5, années 2002-05 +4,
  haute rareté +3, cartes iconiques +3
- **Pénalités** : −4 par signal douteux (contrefaçon, proxy, custom, cartes code, stickers,
  accessoires de rangement, classeurs de marque type Ultra Pro)

**Yu-Gi-Oh n'est suivi qu'en vintage.** Konami réimprime sans limite et la banlist
efface la cote d'une carte du jour au lendemain : le vrac moderne ne vaut rien, même
en rares. Une annonce Yu-Gi-Oh doit donc mentionner un set 2002-05, une 1ère édition
ou « ancien/vintage » pour être seulement prise en compte. Pokémon et Magic n'ont pas
cette condition d'entrée : leur vrac récent garde une valeur de revente.

Le poids en kg est converti en cartes (~600 cartes/kg) quand le titre annonce « 2 kg de cartes ».

Sur Leboncoin le titre chiffre rarement les cartes (le nombre est dans la description),
donc des **indices de volume** prennent le relais : vrac +4, milliers +4, gros lot +3,
carton/caisse +3, collection entière +3, classeur rempli +3, communes/doubles +2.
Les contenants vides (top loader, « 252 emplacements ») sont écartés.

Le scellé (display, ETB, booster, coffret) **est écarté** : ça ne passe pas dans le
trieur. Le rejet n'a lieu que si le titre ne chiffre aucune carte, pour qu'un vrai vrac
qui mentionne un booster en cadeau (« 3000 cartes + 1 booster scellé offert ») reste pris.

## Autres pistes non branchées

| Site | État |
|---|---|
| **Vinted** | beaucoup de vrac, page accessible mais pas de JSON propre — faisable, plus fragile |
| **Delcampe** | spécialisé collection, bon pour le vintage — à tester |
| **Facebook Marketplace / groupes** | gros volume mais automatisation risquée (compte) |
| **Rakuten, Catawiki** | bloquent le scraping (403) |
| **Emmaüs, brocantes, vide-greniers** | hors ligne, souvent le meilleur rapport qualité/prix |

## Fichiers

- `tracker.py` — script principal, scoring, rapport HTML, notifications
- `ebay_api.py` — backend API officielle (recommandé)
- `ebay.py` — backend scraping HTML (secours, se fait bloquer)
- `leboncoin.py` — backend Leboncoin (lit le JSON `__NEXT_DATA__` de la page)
- `telegram.py` — bot de notification (appairage, envoi photo + lien)
- `score.py` — détection du jeu, extraction du nombre de cartes, scoring
- `config.json` — tes filtres
- `telegram.json` — token du bot + chat_id
- `seen.json` — historique des annonces déjà vues
- `report.html` — le rapport visuel
