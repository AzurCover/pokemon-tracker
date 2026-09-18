"""Journal des prix demandés, annonce par annonce, jour après jour.

Aucune source licenciable ne donne le prix réel du marché français : Cardmarket
ne publie aucune moyenne de ventes sur le scellé, et l'API eBay des prix vendus
est fermée. Ce journal est le seul moyen de s'en constituer une — il ne coûte
que de ne pas jeter ce qui passe déjà devant le tracker toutes les 10 minutes.

On enregistre **tout**, y compris les annonces rejetées par les filtres : ce qui
fait une référence de prix, c'est la distribution entière, pas la sélection.
"""

import json
import os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "history.jsonl")
INDEX = os.path.join(HERE, "history_index.json")

FIELDS = ("source", "title", "url", "price", "shipping", "total", "cards",
          "game", "score", "gem_score", "premium", "auction", "bids")


def record(items):
    """Une ligne par annonce inédite ou dont le prix a bougé. Renvoie le nombre écrit."""
    index = {}
    if os.path.exists(INDEX):
        try:
            with open(INDEX, encoding="utf-8") as fh:
                index = json.load(fh)
        except ValueError:
            pass  # index corrompu : on le reconstruit, le journal lui est intact

    stamp = datetime.now().isoformat(timespec="seconds")
    lines = []
    for it in items:
        key = str(it.get("id") or "")
        # déjà vue au même prix : une ligne de plus n'apprendrait rien
        if not key or (key in index and index[key] == it.get("total")):
            continue
        row = {"ts": stamp, "id": key}
        row.update({f: it[f] for f in FIELDS if it.get(f) is not None})
        lines.append(json.dumps(row, ensure_ascii=False))
        index[key] = it.get("total")

    if not lines:
        return 0

    # le journal s'écrit avant l'index : en cas de coupure on relogue une ligne
    # en double, ce qui est réparable, plutôt que d'en perdre une pour toujours
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(index, fh)
    os.replace(tmp, INDEX)
    return len(lines)
