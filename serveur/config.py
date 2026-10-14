import logging
import os

from .erreurs import ErreurApi

logger = logging.getLogger("starpole")


def _requis(nom: str) -> str:
    valeur = os.environ.get(nom, "").strip()
    if not valeur:
        logger.error("Variable d'environnement manquante : %s", nom)
        raise ErreurApi(500, "Configuration du serveur incomplète.")
    return valeur


def secret_codes() -> str:
    return _requis("SECRET_CODES")


def compte_service_json() -> str:
    return _requis("FIREBASE_SERVICE_ACCOUNT_JSON")


def smtp() -> dict:
    try:
        port = int(_requis("SMTP_PORT"))
    except ValueError:
        logger.error("SMTP_PORT n'est pas un nombre")
        raise ErreurApi(500, "Configuration du serveur incomplète.")
    return {
        "hote": _requis("SMTP_HOTE"),
        "port": port,
        "utilisateur": _requis("SMTP_UTILISATEUR"),
        "mot_de_passe": _requis("SMTP_MOT_DE_PASSE"),
        "expediteur": _requis("EXPEDITEUR_EMAIL"),
    }
