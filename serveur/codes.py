import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from .erreurs import ErreurApi

logger = logging.getLogger("starpole")

COLLECTION = "codes_connexion"
VALIDITE = timedelta(minutes=10)
DELAI_ENTRE_CODES = timedelta(minutes=1)
MAX_CODES_PAR_HEURE = 5
MAX_ESSAIS = 5

_FORMAT_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def normaliser_email(email: str) -> str:
    return email.strip().lower()


def email_valide(email: str) -> bool:
    return len(email) <= 254 and bool(_FORMAT_EMAIL.match(email))


def _hmac(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def hacher_code(secret: str, email: str, code: str) -> str:
    return _hmac(secret, f"code:{email}:{code}")


def identifiant_document(secret: str, email: str) -> str:
    """Identifiant du document : l'e-mail n'apparaît jamais en clair dans Firestore."""
    return _hmac(secret, f"email:{email}")


def empreinte_journal(secret: str, email: str) -> str:
    return identifiant_document(secret, email)[:8]


def generer_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def demander_code(
    depot,
    email: str,
    secret: str,
    envoyer: Callable[[str, str], None],
    maintenant_: Optional[datetime] = None,
) -> None:
    """Crée un code, le stocke haché, puis l'envoie. `email` doit être normalisé."""
    maintenant_ = maintenant_ or maintenant()
    code = generer_code()
    code_hache = hacher_code(secret, email, code)

    def _preparer(donnees):
        envois = [
            t for t in (donnees or {}).get("envois", []) if t > maintenant_ - timedelta(hours=1)
        ]
        if envois and maintenant_ - max(envois) < DELAI_ENTRE_CODES:
            return None, "trop_rapide"
        if len(envois) >= MAX_CODES_PAR_HEURE:
            return None, "trop_nombreux"
        envois.append(maintenant_)
        return {
            "codeHache": code_hache,
            "expireLe": maintenant_ + VALIDITE,
            "essais": 0,
            "utilise": False,
            "creeLe": maintenant_,
            "envois": envois,
        }, "ok"

    statut = depot.transformer(COLLECTION, identifiant_document(secret, email), _preparer)
    if statut == "trop_rapide":
        raise ErreurApi(429, "Veuillez patienter une minute avant de demander un nouveau code.")
    if statut == "trop_nombreux":
        raise ErreurApi(429, "Trop de codes demandés pour cette adresse. Réessayez dans une heure.")

    envoyer(email, code)
    logger.info("Code envoyé (adresse %s)", empreinte_journal(secret, email))


def verifier_code(
    depot,
    email: str,
    code: str,
    secret: str,
    maintenant_: Optional[datetime] = None,
) -> None:
    """Valide le code ou lève une ErreurApi. `email` doit être normalisé."""
    maintenant_ = maintenant_ or maintenant()
    code_hache = hacher_code(secret, email, code)

    def _verifier(donnees):
        if not donnees or "codeHache" not in donnees:
            return None, "absent"
        if donnees.get("utilise"):
            return None, "utilise"
        if maintenant_ >= donnees["expireLe"]:
            return None, "expire"
        essais = donnees.get("essais", 0)
        if essais >= MAX_ESSAIS:
            return None, "trop_essais"
        if hmac.compare_digest(donnees["codeHache"], code_hache):
            return {**donnees, "utilise": True}, "ok"
        return {**donnees, "essais": essais + 1}, "incorrect"

    statut = depot.transformer(COLLECTION, identifiant_document(secret, email), _verifier)
    if statut == "ok":
        return
    logger.info("Code refusé (%s) pour l'adresse %s", statut, empreinte_journal(secret, email))
    if statut == "trop_essais":
        raise ErreurApi(429, "Trop de tentatives. Demandez un nouveau code.")
    messages = {
        "absent": "Aucun code en attente pour cette adresse. Demandez un nouveau code.",
        "utilise": "Ce code a déjà été utilisé. Demandez un nouveau code.",
        "expire": "Ce code a expiré. Demandez un nouveau code.",
        "incorrect": "Code incorrect.",
    }
    raise ErreurApi(400, messages[statut])
