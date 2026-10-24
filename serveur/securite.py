import logging
from typing import Optional

from fastapi import Depends, Header
from firebase_admin import auth

from . import firebase, limites
from .erreurs import ErreurApi

logger = logging.getLogger("starpole")


def extraire_jeton(authorization: Optional[str]) -> str:
    if authorization:
        morceaux = authorization.split(" ", 1)
        if len(morceaux) == 2 and morceaux[0].lower() == "bearer" and morceaux[1].strip():
            return morceaux[1].strip()
    raise ErreurApi(401, "Authentification requise : en-tête Authorization Bearer manquant.")


def utilisateur_connecte(authorization: Optional[str] = Header(default=None)) -> str:
    jeton = extraire_jeton(authorization)
    firebase.application()
    try:
        return auth.verify_id_token(jeton)["uid"]
    except Exception as e:
        logger.info("Jeton d'identité refusé : %s", type(e).__name__)
        raise ErreurApi(401, "Jeton d'identité invalide ou expiré.")


def administrateur_connecte(authorization: Optional[str] = Header(default=None)) -> str:
    """Uid de l'appelant, s'il porte la revendication `admin: true`."""
    jeton = extraire_jeton(authorization)
    firebase.application()
    try:
        revendications = auth.verify_id_token(jeton, check_revoked=True)
    except Exception as e:
        logger.info("Jeton d'identité refusé : %s", type(e).__name__)
        raise ErreurApi(401, "Jeton d'identité invalide ou expiré.")
    if revendications.get("admin") is not True:
        raise ErreurApi(403, "Accès réservé aux administrateurs.")
    return revendications["uid"]


def utilisateur_limite(
    uid: str = Depends(utilisateur_connecte),
    depot=Depends(firebase.obtenir_depot),
) -> str:
    limites.verifier_limite(depot, uid)
    return uid
