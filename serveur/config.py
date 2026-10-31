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


VARIABLES_REQUISES = (
    "FIREBASE_SERVICE_ACCOUNT_JSON",
    "SMTP_HOTE",
    "SMTP_PORT",
    "SMTP_UTILISATEUR",
    "SMTP_MOT_DE_PASSE",
    "EXPEDITEUR_EMAIL",
    "SECRET_CODES",
    "GEMINI_CLE_API",
)


def variables_manquantes() -> list:
    """Les noms (jamais les valeurs) des variables absentes ou vides."""
    return [nom for nom in VARIABLES_REQUISES if not os.environ.get(nom, "").strip()]


ORIGINES_ADMIN_DEFAUT = (
    "http://localhost:5173",
    "https://starpole-3d84d.web.app",
    "https://starpole-3d84d.firebaseapp.com",
    # Site web public StarPole (Firebase Hosting).
    "https://starpole-web.web.app",
    "https://starpole-web.firebaseapp.com",
)


def origines_admin() -> list:
    """Adresses autorisées (CORS) : console d'administration et site web public.

    Variable facultative ORIGINES_ADMIN, séparée par des virgules. Par défaut :
    la console en local et son hébergement Firebase.
    """
    valeur = os.environ.get("ORIGINES_ADMIN", "").strip() or ",".join(ORIGINES_ADMIN_DEFAUT)
    return [o.strip().rstrip("/") for o in valeur.split(",") if o.strip()]


def secret_codes() -> str:
    return _requis("SECRET_CODES")


def cle_gemini() -> str:
    """Clé de l'API Gemini (vérification des alertes par l'IA)."""
    return _requis("GEMINI_CLE_API")


def modele_gemini() -> str:
    """Modèle Gemini utilisé (variable facultative GEMINI_MODELE)."""
    return os.environ.get("GEMINI_MODELE", "").strip() or "gemini-flash-lite-latest"


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
