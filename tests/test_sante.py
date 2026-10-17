from fastapi.testclient import TestClient

from serveur import config
from serveur.main import app


def test_sante_liste_les_variables_manquantes(monkeypatch):
    for nom in config.VARIABLES_REQUISES:
        monkeypatch.delenv(nom, raising=False)
    monkeypatch.setenv("SMTP_HOTE", "smtp.exemple.fr")
    monkeypatch.setenv("SECRET_CODES", "   ")  # vide : compte comme manquante

    reponse = TestClient(app).get("/sante")

    assert reponse.status_code == 200
    donnees = reponse.json()
    assert donnees["pret"] is False
    assert "SMTP_HOTE" not in donnees["variablesManquantes"]
    assert "SECRET_CODES" in donnees["variablesManquantes"]
    assert "FIREBASE_SERVICE_ACCOUNT_JSON" in donnees["variablesManquantes"]
    # Jamais de valeur dans la réponse.
    assert "smtp.exemple.fr" not in reponse.text


def test_sante_prete_quand_tout_est_renseigne(monkeypatch):
    for nom in config.VARIABLES_REQUISES:
        monkeypatch.setenv(nom, "x")

    donnees = TestClient(app).get("/sante").json()

    assert donnees == {"pret": True, "variablesManquantes": []}
