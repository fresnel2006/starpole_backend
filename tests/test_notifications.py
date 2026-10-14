import pytest

from serveur import notifications as n
from serveur.erreurs import ErreurApi
from tests.conftest import FausseMessagerie


def appareils(db, uid, *jetons):
    for jeton in jetons:
        db.ajouter(("utilisateurs", uid, "appareils", jeton), {"plateforme": "android"})


def statut(fonction, *args):
    with pytest.raises(ErreurApi) as e:
        fonction(*args)
    return e.value.statut


# ---------- appel ----------

@pytest.fixture
def appel(db):
    db.ajouter(
        ("appels", "a1"),
        {"appelantId": "alice", "appelantNom": "Alice", "appeleId": "bob", "video": True, "statut": "sonne"},
    )
    appareils(db, "bob", "t1", "t2")


def test_appel_envoye_en_data_haute_priorite(db, messagerie, appel):
    resultat = n.notifier_appel(db, messagerie, "alice", "a1")
    assert resultat == {"envoyes": 2, "jetonsSupprimes": 0}
    envoi = messagerie.envois[0]
    assert envoi["jetons"] == ["t1", "t2"]
    assert envoi["notification"] is None and envoi["haute"] is True
    assert envoi["donnees"] == {
        "type": "appel", "appelId": "a1", "appelantId": "alice", "appelantNom": "Alice", "video": "true",
    }


def test_appel_refus(db, messagerie, appel):
    assert statut(n.notifier_appel, db, messagerie, "mallory", "a1") == 403
    assert statut(n.notifier_appel, db, messagerie, "alice", "inconnu") == 404
    db.donnees[("appels", "a1")]["statut"] = "termine"
    assert statut(n.notifier_appel, db, messagerie, "alice", "a1") == 400
    assert messagerie.envois == []


def test_appel_supprime_les_jetons_invalides(db, appel):
    messagerie = FausseMessagerie(invalides=["t2"])
    resultat = n.notifier_appel(db, messagerie, "alice", "a1")
    assert resultat == {"envoyes": 1, "jetonsSupprimes": 1}
    assert ("utilisateurs", "bob", "appareils", "t2") not in db.donnees
    assert ("utilisateurs", "bob", "appareils", "t1") in db.donnees


def test_appel_sans_appareil(db, messagerie):
    db.ajouter(("appels", "a2"), {"appelantId": "alice", "appeleId": "bob", "statut": "sonne"})
    assert n.notifier_appel(db, messagerie, "alice", "a2") == {"envoyes": 0, "jetonsSupprimes": 0}
    assert messagerie.envois == []


# ---------- message ----------

@pytest.fixture
def conversation(db):
    db.ajouter(
        ("conversations", "c1"),
        {
            "participants": ["alice", "bob"],
            "noms": {"alice": "Alice", "bob": "Bob"},
            "dernierMessage": "x" * 300,
            "dernierAuteurId": "alice",
        },
    )
    appareils(db, "bob", "tb")
    appareils(db, "alice", "ta")


def test_message_notifie_l_autre_personne(db, messagerie, conversation):
    resultat = n.notifier_message(db, messagerie, "alice", "c1")
    assert resultat["envoyes"] == 1
    envoi = messagerie.envois[0]
    assert envoi["jetons"] == ["tb"]
    titre, texte = envoi["notification"]
    assert titre == "Alice" and len(texte) == n.LONGUEUR_MAX_MESSAGE and texte.endswith("…")


def test_message_refus(db, messagerie, conversation):
    assert statut(n.notifier_message, db, messagerie, "mallory", "c1") == 403
    assert statut(n.notifier_message, db, messagerie, "bob", "c1") == 403  # pas le dernier auteur
    assert statut(n.notifier_message, db, messagerie, "alice", "inconnue") == 404


# ---------- alerte ----------

@pytest.fixture
def alerte(db):
    db.ajouter(
        ("alertes", "al1"),
        {"auteurId": "alice", "auteurNom": "Alice", "categorie": "Accident",
         "description": "Route bloquée", "latitude": 48.8566, "longitude": 2.3522},
    )
    position = lambda lat, lon: {"position": {"latitude": lat, "longitude": lon}}
    db.ajouter(("utilisateurs", "alice"), position(48.8566, 2.3522))
    db.ajouter(("utilisateurs", "proche"), position(48.8580, 2.3522))   # ~155 m
    db.ajouter(("utilisateurs", "loin"), position(48.8700, 2.3522))     # ~1,5 km
    db.ajouter(("utilisateurs", "est"), position(48.8566, 2.3700))      # ~1,3 km, même latitude
    db.ajouter(("utilisateurs", "sans_position"), {"nom": "X"})
    for uid in ("alice", "proche", "loin", "est"):
        appareils(db, uid, f"jeton_{uid}")


def test_alerte_notifie_les_proches_sans_l_auteur(db, messagerie, alerte):
    resultat = n.notifier_alerte(db, messagerie, "alice", "al1", 500)
    assert resultat == {"envoyes": 1, "jetonsSupprimes": 0, "utilisateursProches": 1}
    envoi = messagerie.envois[0]
    assert envoi["jetons"] == ["jeton_proche"]
    assert envoi["notification"] == ("Alerte : Accident", "Route bloquée")
    assert envoi["donnees"]["type"] == "alerte"


def test_alerte_rayon_personnalise(db, messagerie, alerte):
    n.notifier_alerte(db, messagerie, "alice", "al1", 5000)
    assert sorted(messagerie.envois[0]["jetons"]) == ["jeton_est", "jeton_loin", "jeton_proche"]


def test_alerte_refus(db, messagerie, alerte):
    assert statut(n.notifier_alerte, db, messagerie, "mallory", "al1", 500) == 403
    assert statut(n.notifier_alerte, db, messagerie, "alice", "inconnue", 500) == 404
    db.donnees[("alertes", "al1")]["latitude"] = None
    assert statut(n.notifier_alerte, db, messagerie, "alice", "al1", 500) == 400


def test_distance_haversine():
    assert n.distance_metres(48.8566, 2.3522, 48.8566, 2.3522) == 0
    # Paris - Lyon, environ 392 km
    assert 385_000 < n.distance_metres(48.8566, 2.3522, 45.7640, 4.8357) < 400_000
