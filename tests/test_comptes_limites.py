from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from serveur import comptes, limites
from serveur.erreurs import ErreurApi
from serveur.securite import extraire_jeton

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
EMAIL = "marie@exemple.fr"


def test_inscription_cree_utilisateur_et_profil(db):
    from tests.conftest import FausseAuth

    auth = FausseAuth()
    jeton = comptes.connecter(EMAIL, "Marie", auth, db)
    assert jeton == "jeton-uid1"
    profil = db.donnees[("utilisateurs", "uid1")]
    assert profil["nom"] == "Marie"
    assert profil["email"] == EMAIL and profil["emailNormalise"] == EMAIL
    assert profil["telephone"] == "" and profil["telephoneNormalise"] == ""
    assert "creeLe" in profil


def test_connexion_ne_recree_ni_ecrase(db):
    from tests.conftest import FausseAuth

    auth = FausseAuth()
    comptes.connecter(EMAIL, "Marie", auth, db)
    db.donnees[("utilisateurs", "uid1")]["nom"] = "Nom modifié"
    comptes.connecter(EMAIL, "Autre", auth, db)
    assert auth.crees == 1
    assert db.donnees[("utilisateurs", "uid1")]["nom"] == "Nom modifié"


def test_compte_desactive_refuse(db):
    from tests.conftest import FausseAuth

    auth = FausseAuth()
    auth.utilisateurs[EMAIL] = SimpleNamespace(uid="u", display_name=None, disabled=True)
    with pytest.raises(ErreurApi) as e:
        comptes.connecter(EMAIL, None, auth, db)
    assert e.value.statut == 403


def test_limite_de_30_appels_par_minute(depot):
    for _ in range(30):
        limites.verifier_limite(depot, "u1", T0)
    with pytest.raises(ErreurApi) as e:
        limites.verifier_limite(depot, "u1", T0 + timedelta(seconds=30))
    assert e.value.statut == 429
    # Un autre utilisateur n'est pas touché, et la fenêtre se libère après une minute.
    limites.verifier_limite(depot, "u2", T0)
    limites.verifier_limite(depot, "u1", T0 + timedelta(seconds=61))


def test_extraction_du_jeton():
    assert extraire_jeton("Bearer abc") == "abc"
    assert extraire_jeton("bearer abc") == "abc"
    for invalide in (None, "", "Bearer", "Bearer  ", "Basic abc", "abc"):
        with pytest.raises(ErreurApi) as e:
            extraire_jeton(invalide)
        assert e.value.statut == 401
