from datetime import datetime, timedelta
from typing import Optional

from .codes import maintenant
from .erreurs import ErreurApi

COLLECTION = "limites_notifications"
MAX_APPELS = 30
FENETRE = timedelta(minutes=1)


def verifier_limite(depot, uid: str, maintenant_: Optional[datetime] = None) -> None:
    maintenant_ = maintenant_ or maintenant()

    def _compter(donnees):
        recents = [t for t in (donnees or {}).get("appels", []) if t > maintenant_ - FENETRE]
        if len(recents) >= MAX_APPELS:
            return None, False
        recents.append(maintenant_)
        return {"appels": recents}, True

    if not depot.transformer(COLLECTION, uid, _compter):
        raise ErreurApi(429, "Trop de requêtes. Réessayez dans un instant.")
