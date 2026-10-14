from datetime import datetime, timedelta, timezone

import pytest

from serveur import codes
from serveur.erreurs import ErreurApi

SECRET = "secret-de-test"
EMAIL = "marie@exemple.fr"
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class FauxCourriel:
    def __init__(self):
        self.envois = []

    def __call__(self, destinataire, code):
        self.envois.append((destinataire, code))


@pytest.fixture
def courriel():
    return FauxCourriel()


def demander(depot, courriel, quand=T0):
    codes.demander_code(depot, EMAIL, SECRET, courriel, quand)
    return courriel.envois[-1][1]


def verifier(depot, code, quand=T0):
    codes.verifier_code(depot, EMAIL, code, SECRET, quand)


def statut_erreur(fonction):
    with pytest.raises(ErreurApi) as e:
        fonction()
    return e.value.statut


def test_normalisation_email():
    assert codes.normaliser_email("  Marie@Exemple.FR ") == EMAIL
    assert codes.email_valide(EMAIL)
    assert not codes.email_valide("pas-un-email")


def test_code_a_six_chiffres_envoye_et_stocke_hache(depot, courriel):
    code = demander(depot, courriel)
    assert len(code) == 6 and code.isdigit()
    assert courriel.envois == [(EMAIL, code)]
    stocke = str(depot.donnees)
    assert code not in stocke and EMAIL not in stocke
    enregistrement = next(iter(depot.donnees.values()))
    assert enregistrement["expireLe"] == T0 + timedelta(minutes=10)


def test_verification_reussie_puis_usage_unique(depot, courriel):
    code = demander(depot, courriel)
    verifier(depot, code)
    assert statut_erreur(lambda: verifier(depot, code)) == 400


def test_code_expire(depot, courriel):
    code = demander(depot, courriel)
    assert statut_erreur(lambda: verifier(depot, code, T0 + timedelta(minutes=10))) == 400
    verifier_ok = T0 + timedelta(minutes=9, seconds=59)
    verifier(depot, code, verifier_ok)


def test_code_incorrect(depot, courriel):
    code = demander(depot, courriel)
    mauvais = "000000" if code != "000000" else "111111"
    assert statut_erreur(lambda: verifier(depot, mauvais)) == 400
    verifier(depot, code)


def test_cinq_essais_maximum(depot, courriel):
    code = demander(depot, courriel)
    mauvais = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert statut_erreur(lambda: verifier(depot, mauvais)) == 400
    # Même le bon code est refusé après 5 échecs.
    assert statut_erreur(lambda: verifier(depot, code)) == 429


def test_aucun_code_en_attente(depot):
    assert statut_erreur(lambda: verifier(depot, "123456")) == 400


def test_un_code_par_minute(depot, courriel):
    demander(depot, courriel)
    assert statut_erreur(lambda: demander(depot, courriel, T0 + timedelta(seconds=59))) == 429
    demander(depot, courriel, T0 + timedelta(seconds=60))
    assert len(courriel.envois) == 2


def test_cinq_codes_par_heure(depot, courriel):
    for i in range(5):
        demander(depot, courriel, T0 + timedelta(minutes=2 * i))
    assert statut_erreur(lambda: demander(depot, courriel, T0 + timedelta(minutes=10))) == 429
    # Une heure après le premier envoi, une place se libère.
    demander(depot, courriel, T0 + timedelta(hours=1, seconds=1))
    assert len(courriel.envois) == 6


def test_nouveau_code_remplace_l_ancien(depot, courriel):
    ancien = demander(depot, courriel)
    nouveau = demander(depot, courriel, T0 + timedelta(minutes=2))
    quand = T0 + timedelta(minutes=3)
    if ancien != nouveau:
        assert statut_erreur(lambda: verifier(depot, ancien, quand)) == 400
    verifier(depot, nouveau, quand)


def test_code_lie_a_l_adresse():
    assert codes.hacher_code(SECRET, EMAIL, "123456") != codes.hacher_code(SECRET, "autre@exemple.fr", "123456")
    assert codes.hacher_code(SECRET, EMAIL, "123456") != codes.hacher_code("autre-secret", EMAIL, "123456")


def test_echec_d_envoi_remonte_l_erreur(depot):
    def echec(*_):
        raise ErreurApi(503, "Impossible d'envoyer l'e-mail pour le moment. Réessayez plus tard.")

    assert statut_erreur(lambda: codes.demander_code(depot, EMAIL, SECRET, echec, T0)) == 503
