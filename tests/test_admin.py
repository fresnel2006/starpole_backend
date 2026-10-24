from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from serveur import firebase, routes_admin, securite
from serveur.main import app

ENTETE = {"Authorization": "Bearer jeton-admin"}
MOTIF = {"motif": "Contenu abusif signalé"}


class FausseAuthAdmin:
    """Faux module firebase_admin.auth pour les comptes."""

    class UserNotFoundError(Exception):
        pass

    def __init__(self):
        self.comptes = {
            "u1": SimpleNamespace(disabled=False, custom_claims=None),
            "chef": SimpleNamespace(disabled=False, custom_claims={"admin": True}),
        }
        self.revoques = []

    def get_user(self, uid):
        if uid not in self.comptes:
            raise self.UserNotFoundError()
        return self.comptes[uid]

    def update_user(self, uid, disabled):
        self.get_user(uid).disabled = disabled

    def revoke_refresh_tokens(self, uid):
        self.revoques.append(uid)


JETONS = {
    "jeton-admin": {"uid": "chef", "admin": True},
    "jeton-simple": {"uid": "u1"},
}


def _verifier(jeton, check_revoked=False):
    if jeton not in JETONS:
        raise ValueError("jeton invalide")
    return JETONS[jeton]


@pytest.fixture
def faux_auth():
    return FausseAuthAdmin()


@pytest.fixture
def client(db, faux_auth, monkeypatch):
    monkeypatch.setattr(securite.firebase, "application", lambda: None)
    monkeypatch.setattr(securite.auth, "verify_id_token", _verifier)
    app.dependency_overrides[firebase.obtenir_db] = lambda: db
    app.dependency_overrides[routes_admin.obtenir_auth] = lambda: faux_auth
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def alerte(db):
    db.ajouter(("alertes", "a1"), {"type": "urgence", "statut": "en_cours", "auteurId": "u1"})
    db.ajouter(("alertes", "a1", "progression", "p1"), {"texte": "J'arrive"})
    db.ajouter(("alertes", "a1", "progression", "p2"), {"texte": "Sur place"})
    db.ajouter(("alertes", "a2"), {"type": "don", "statut": "en_cours"})


def journal(db):
    return [v for k, v in db.donnees.items() if k[0] == "journal_admin"]


# ---------- accès ----------

def test_sans_jeton_refuse(client, alerte):
    reponse = client.post("/admin/alertes/a1/resoudre", json=MOTIF)
    assert reponse.status_code == 401


def test_jeton_invalide_refuse(client, alerte):
    reponse = client.post("/admin/alertes/a1/resoudre", json=MOTIF, headers={"Authorization": "Bearer faux"})
    assert reponse.status_code == 401


def test_utilisateur_non_admin_refuse(client, db, alerte):
    reponse = client.post(
        "/admin/alertes/a1/supprimer", json=MOTIF, headers={"Authorization": "Bearer jeton-simple"}
    )
    assert reponse.status_code == 403
    assert reponse.json() == {"erreur": "Accès réservé aux administrateurs."}
    assert ("alertes", "a1") in db.donnees
    assert journal(db) == []


@pytest.mark.parametrize("motif", ["", "  a ", "x" * 301])
def test_motif_obligatoire(client, alerte, motif):
    reponse = client.post("/admin/alertes/a1/resoudre", json={"motif": motif}, headers=ENTETE)
    assert reponse.status_code == 400


# ---------- alertes ----------

def test_supprimer_alerte_et_progression(client, db, alerte):
    reponse = client.post("/admin/alertes/a1/supprimer", json=MOTIF, headers=ENTETE)
    assert reponse.status_code == 200
    restants = [k for k in db.donnees if k[0] == "alertes"]
    assert restants == [("alertes", "a2")]
    [entree] = journal(db)
    assert entree["adminId"] == "chef"
    assert entree["action"] == "supprimer_alerte"
    assert entree["cible"] == "alertes/a1"
    assert entree["motif"] == "Contenu abusif signalé"
    assert entree["date"] is not None


def test_supprimer_alerte_absente(client, db):
    reponse = client.post("/admin/alertes/inconnue/supprimer", json=MOTIF, headers=ENTETE)
    assert reponse.status_code == 404
    assert journal(db) == []


def test_resoudre_alerte(client, db, alerte):
    reponse = client.post("/admin/alertes/a1/resoudre", json=MOTIF, headers=ENTETE)
    assert reponse.status_code == 200
    donnees = db.donnees[("alertes", "a1")]
    assert donnees["statut"] == "resolue"
    assert donnees["termineLe"] is not None
    assert donnees["type"] == "urgence"
    assert journal(db)[0]["action"] == "resoudre_alerte"


def test_resoudre_alerte_deja_resolue(client, db, alerte):
    client.post("/admin/alertes/a1/resoudre", json=MOTIF, headers=ENTETE)
    reponse = client.post("/admin/alertes/a1/resoudre", json=MOTIF, headers=ENTETE)
    assert reponse.status_code == 409
    assert len(journal(db)) == 1


def test_identifiant_mal_forme(client):
    reponse = client.post("/admin/alertes/a.b/resoudre", json=MOTIF, headers=ENTETE)
    assert reponse.status_code == 400


# ---------- utilisateurs ----------

def test_suspendre_puis_reactiver(client, db, faux_auth):
    reponse = client.post("/admin/utilisateurs/u1/suspendre", json=MOTIF, headers=ENTETE)
    assert reponse.status_code == 200
    assert faux_auth.comptes["u1"].disabled is True
    assert faux_auth.revoques == ["u1"]
    assert client.get("/admin/utilisateurs/u1", headers=ENTETE).json() == {"suspendu": True, "admin": False}

    reponse = client.post("/admin/utilisateurs/u1/reactiver", json=MOTIF, headers=ENTETE)
    assert reponse.status_code == 200
    assert faux_auth.comptes["u1"].disabled is False
    assert [e["action"] for e in journal(db)] == ["suspendre_utilisateur", "reactiver_utilisateur"]
    assert all(e["cible"] == "utilisateurs/u1" for e in journal(db))


def test_suspendre_utilisateur_absent(client, db):
    reponse = client.post("/admin/utilisateurs/personne/suspendre", json=MOTIF, headers=ENTETE)
    assert reponse.status_code == 404
    assert journal(db) == []


def test_admin_ne_peut_pas_se_suspendre(client, faux_auth):
    reponse = client.post("/admin/utilisateurs/chef/suspendre", json=MOTIF, headers=ENTETE)
    assert reponse.status_code == 400
    assert faux_auth.comptes["chef"].disabled is False


def test_etat_reserve_aux_admins(client):
    reponse = client.get("/admin/utilisateurs/u1", headers={"Authorization": "Bearer jeton-simple"})
    assert reponse.status_code == 403


# ---------- CORS ----------

def test_cors_console_autorisee(client):
    reponse = client.options(
        "/admin/alertes/a1/resoudre",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert reponse.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_autre_origine_refusee(client):
    reponse = client.options(
        "/admin/alertes/a1/resoudre",
        headers={"Origin": "https://pirate.exemple", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in reponse.headers


def test_cors_console_hebergee_autorisee(client):
    reponse = client.options(
        "/admin/alertes/a1/resoudre",
        headers={"Origin": "https://starpole-3d84d.web.app", "Access-Control-Request-Method": "POST"},
    )
    assert reponse.headers.get("access-control-allow-origin") == "https://starpole-3d84d.web.app"
