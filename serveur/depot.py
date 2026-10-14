"""Lecture-modification-écriture atomique d'un document.

`fonction` reçoit le dictionnaire actuel (ou None) et renvoie (nouveau, résultat).
Si `nouveau` est None, rien n'est écrit. La fonction peut être rejouée par Firestore
en cas de conflit : elle ne doit donc avoir aucun effet de bord.
"""
import copy
from typing import Any, Callable, Optional, Tuple

from google.cloud import firestore

Fonction = Callable[[Optional[dict]], Tuple[Optional[dict], Any]]


class DepotFirestore:
    def __init__(self, db):
        self._db = db

    def transformer(self, collection: str, doc_id: str, fonction: Fonction) -> Any:
        ref = self._db.collection(collection).document(doc_id)

        @firestore.transactional
        def _executer(transaction):
            instantane = ref.get(transaction=transaction)
            nouveau, resultat = fonction(instantane.to_dict() if instantane.exists else None)
            if nouveau is not None:
                transaction.set(ref, nouveau)
            return resultat

        return _executer(self._db.transaction())


class DepotMemoire:
    """Version en mémoire, utilisée par les tests."""

    def __init__(self):
        self.donnees: dict = {}

    def transformer(self, collection: str, doc_id: str, fonction: Fonction) -> Any:
        cle = (collection, doc_id)
        nouveau, resultat = fonction(copy.deepcopy(self.donnees.get(cle)))
        if nouveau is not None:
            self.donnees[cle] = copy.deepcopy(nouveau)
        return resultat
