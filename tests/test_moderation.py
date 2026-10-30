import json
import urllib.error

import pytest

from serveur import moderation as m
from serveur.erreurs import ErreurApi


class FauxVerificateur:
    """Fausse IA : renvoie le verdict voulu et note ce qu'elle a reçu."""

    def __init__(self, verdict=None, panne=False):
        self.verdict = verdict or {"acceptable": True, "categorie": "ok", "raison": ""}
        self.panne = panne
        self.recus = []

    def verifier(self, type_alerte, titre, description, photo_b64=None):
        self.recus.append((type_alerte, titre, description, photo_b64))
        if self.panne:
            raise m.ModerationIndisponible("délai dépassé")
        return self.verdict


@pytest.fixture
def alerte(db):
    db.ajouter(
        ("alertes", "x1"),
        {
            "type": "service",
            "categorie": "Besoin d'aide",
            "description": "Envoyez 20 000 F sur mon Wave",
            "auteurId": "alice",
            "statut": "en_cours",
            "photo": "cGhvdG8=",
        },
    )
    db.ajouter(("alertes", "x1", "progression", "p1"), {"texte": "En route"})
    db.ajouter(("utilisateurs", "alice", "appareils", "t1"), {"plateforme": "android"})


def test_alerte_correcte_reste_en_ligne(db, messagerie, alerte):
    ia = FauxVerificateur()
    assert m.moderer_alerte(db, messagerie, ia, "alice", "x1") == {"etat": "acceptee"}
    assert db.donnees[("alertes", "x1")]["moderation"] == "ok"
    # L'IA a reçu le type, le titre, la description et la photo.
    assert ia.recus == [("service", "Besoin d'aide", "Envoyez 20 000 F sur mon Wave", "cGhvdG8=")]
    assert messagerie.envois == []


def test_alerte_non_conforme_supprimee_et_auteur_prevenu(db, messagerie, alerte):
    ia = FauxVerificateur({"acceptable": False, "categorie": "argent", "raison": "Les demandes d'argent sont interdites."})
    resultat = m.moderer_alerte(db, messagerie, ia, "alice", "x1")

    assert resultat["etat"] == "supprimee" and resultat["categorie"] == "argent"
    assert ("alertes", "x1") not in db.donnees
    assert ("alertes", "x1", "progression", "p1") not in db.donnees
    # L'action est dans le journal d'administration.
    journal = [d for c, d in db.donnees.items() if c[0] == "journal_admin"]
    assert len(journal) == 1 and journal[0]["adminId"] == "moderation_ia"
    assert journal[0]["cible"] == "alertes/x1" and "argent" in journal[0]["motif"]
    # L'auteur reçoit une notification qui explique pourquoi.
    envoi = messagerie.envois[0]
    assert envoi["jetons"] == ["t1"]
    assert envoi["donnees"]["type"] == "moderation"
    assert envoi["notification"][0] == "Alerte retirée"
    assert "Besoin d'aide" in envoi["notification"][1]


def test_ia_indisponible_l_alerte_reste_marquee(db, messagerie, alerte):
    resultat = m.moderer_alerte(db, messagerie, FauxVerificateur(panne=True), "alice", "x1")
    assert resultat == {"etat": "non_verifiee"}
    assert db.donnees[("alertes", "x1")]["moderation"] == "non_verifiee"
    assert messagerie.envois == []


def test_seul_l_auteur_demande_la_verification(db, messagerie, alerte):
    with pytest.raises(ErreurApi) as e:
        m.moderer_alerte(db, messagerie, FauxVerificateur(), "mallory", "x1")
    assert e.value.statut == 403


def test_alerte_absente_ou_deja_verifiee(db, messagerie, alerte):
    ia = FauxVerificateur()
    assert m.moderer_alerte(db, messagerie, ia, "alice", "inconnue") == {"etat": "absente"}
    m.moderer_alerte(db, messagerie, ia, "alice", "x1")
    assert m.moderer_alerte(db, messagerie, ia, "alice", "x1") == {"etat": "deja_verifiee"}
    assert len(ia.recus) == 1


def test_verificateur_gemini_lit_la_reponse(monkeypatch):
    monkeypatch.setenv("GEMINI_CLE_API", "cle-de-test")
    envoyes = {}

    class Reponse:
        def __init__(self, donnees):
            self._donnees = donnees

        def read(self):
            return json.dumps(self._donnees).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def faux_urlopen(requete, timeout):
        envoyes["corps"] = json.loads(requete.data)
        envoyes["cle"] = requete.headers.get("X-goog-api-key")
        verdict = {"acceptable": False, "categorie": "sexuel", "raison": "Contenu — interdit."}
        return Reponse({"candidates": [{"content": {"parts": [{"text": json.dumps(verdict)}]}}]})

    monkeypatch.setattr(m.urllib.request, "urlopen", faux_urlopen)
    verdict = m.VerificateurGemini().verifier("service", "Titre", "Texte", "cGhvdG8=")

    assert verdict == {"acceptable": False, "categorie": "sexuel", "raison": "Contenu - interdit."}
    assert envoyes["cle"] == "cle-de-test"
    parts = envoyes["corps"]["contents"][0]["parts"]
    assert parts[1]["inline_data"]["data"] == "cGhvdG8="


def test_verificateur_gemini_en_panne(monkeypatch):
    monkeypatch.setenv("GEMINI_CLE_API", "cle-de-test")

    def panne(requete, timeout):
        raise urllib.error.HTTPError(requete.full_url, 429, "quota", {}, None)

    monkeypatch.setattr(m.urllib.request, "urlopen", panne)
    with pytest.raises(m.ModerationIndisponible) as e:
        m.VerificateurGemini().verifier("urgence", "T", "D")
    assert "429" in str(e.value) and "cle-de-test" not in str(e.value)


def test_contenu_bloque_par_google_est_refuse(monkeypatch):
    monkeypatch.setenv("GEMINI_CLE_API", "cle-de-test")

    class Reponse:
        def read(self):
            return json.dumps({"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(m.urllib.request, "urlopen", lambda requete, timeout: Reponse())
    verdict = m.VerificateurGemini().verifier("service", "Fille seule", "...")
    assert verdict["acceptable"] is False and verdict["categorie"] == "interdit"
