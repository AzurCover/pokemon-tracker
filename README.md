# Tracker multi-sites — gros lots de cartes Pokémon & Magic

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

## 4. Régler les filtres

Tout est dans `config.json` :

| clé | rôle |
|---|---|
| `sources` | `["ebay", "leboncoin"]` |
| `queries` | les recherches, par source |
| `games` | jeux surveillés : `["pokemon", "magic"]` — une annonce qui n'en mentionne aucun est écartée |
| `require_bulk_hint_when_unknown` | sans nombre de cartes, exiger un indice de volume |
| `min_cards` | nombre de cartes minimum (défaut 100) |
| `min_total` / `max_total` | fourchette de prix en € (port inclus) |
| `max_price_per_card` | plafond €/carte (défaut 0.50) |
| `min_score` | sévérité du tri (monte-le si trop de bruit) |
| `exclude_keywords` | mots qui disqualifient une annonce |
| `keep_unknown_count` | garder les annonces sans nombre de cartes lisible |
| `location` | `null`, `"fr"` ou `"eu"` |

**Les enchères échappent aux planchers de prix** : un lot de 1000 cartes qui démarre à
1 € serait sinon éliminé, alors que c'est exactement la bonne affaire à surveiller.

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
- **Pénalités** : −4 par signal douteux (contrefaçon, proxy, custom, cartes code, stickers)

Le poids en kg est converti en cartes (~600 cartes/kg) quand le titre annonce « 2 kg de cartes ».

Sur Leboncoin le titre chiffre rarement les cartes (le nombre est dans la description),
donc des **indices de volume** prennent le relais : vrac +4, milliers +4, gros lot +3,
carton/caisse +3, collection entière +3, classeur rempli +3, communes/doubles +2.
Les contenants vides (top loader, « 252 emplacements ») sont écartés.

Le scellé (display, ETB, booster) est volontairement à **poids nul** : ça ne passe pas
dans le trieur.

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
