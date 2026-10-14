import copy
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import AlreadyExists

from serveur.depot import DepotMemoire


class FauxDocument:
    def __init__(self, doc_id, donnees):
        self.id = doc_id
        self.exists = donnees is not None
        self._donnees = donnees

    def to_dict(self):
        return copy.deepcopy(self._donnees)


class FausseReference:
    def __init__(self, base, chemin):
        self._base, self._chemin = base, chemin

    def get(self, **_):
        return FauxDocument(self._chemin[-1], self._base.donnees.get(self._chemin))

    def set(self, donnees):
        self._base.donnees[self._chemin] = copy.deepcopy(donnees)

    def create(self, donnees):
        if self._chemin in self._base.donnees:
            raise AlreadyExists("existe déjà")
        self.set(donnees)

    def delete(self):
        self._base.donnees.pop(self._chemin, None)

    def collection(self, nom):
        return FausseCollection(self._base, self._chemin + (nom,))


def _valeur(donnees, chemin):
    for morceau in chemin.split("."):
        if not isinstance(donnees, dict) or morceau not in donnees:
            return None
        donnees = donnees[morceau]
    return donnees


class FausseCollection:
    def __init__(self, base, chemin, filtres=()):
        self._base, self._chemin, self._filtres = base, chemin, filtres

    def document(self, doc_id):
        return FausseReference(self._base, self._chemin + (doc_id,))

    def where(self, filter):
        return FausseCollection(self._base, self._chemin, self._filtres + (filter,))

    def stream(self):
        for chemin, donnees in list(self._base.donnees.items()):
            if len(chemin) != len(self._chemin) + 1 or chemin[:-1] != self._chemin:
                continue
            if all(self._accepte(donnees, f) for f in self._filtres):
                yield FauxDocument(chemin[-1], donnees)

    @staticmethod
    def _accepte(donnees, f):
        v = _valeur(donnees, f.field_path)
        if v is None:
            return False
        return v >= f.value if f.op_string == ">=" else v <= f.value


class FausseBase:
    """Faux Firestore minimal : collection/document/get/set/create/delete/where/stream."""

    def __init__(self):
        self.donnees = {}

    def collection(self, nom):
        return FausseCollection(self, (nom,))

    def ajouter(self, chemin, donnees):
        self.donnees[tuple(chemin)] = copy.deepcopy(donnees)


class FausseMessagerie:
    def __init__(self, invalides=()):
        self.envois = []
        self.invalides = set(invalides)

    def envoyer(self, jetons, donnees, notification=None, haute_priorite=False):
        self.envois.append(
            {"jetons": list(jetons), "donnees": donnees, "notification": notification, "haute": haute_priorite}
        )
        return [j for j in jetons if j in self.invalides]


class FausseAuth:
    class UserNotFoundError(Exception):
        pass

    class EmailAlreadyExistsError(Exception):
        pass

    def __init__(self):
        self.utilisateurs = {}
        self.crees = 0

    def get_user_by_email(self, email):
        if email not in self.utilisateurs:
            raise self.UserNotFoundError()
        return self.utilisateurs[email]

    def create_user(self, **options):
        self.crees += 1
        utilisateur = SimpleNamespace(
            uid=f"uid{self.crees}",
            display_name=options.get("display_name"),
            disabled=False,
        )
        self.utilisateurs[options["email"]] = utilisateur
        return utilisateur

    def create_custom_token(self, uid):
        return f"jeton-{uid}".encode()


@pytest.fixture
def depot():
    return DepotMemoire()


@pytest.fixture
def db():
    return FausseBase()


@pytest.fixture
def messagerie():
    return FausseMessagerie()
