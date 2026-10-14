import logging

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

from .erreurs import ErreurApi

logger = logging.getLogger("starpole")


def _trouver_ou_creer(email: str, nom, auth):
    try:
        return auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        pass
    options = {"email": email, "email_verified": True}
    if nom:
        options["display_name"] = nom
    try:
        return auth.create_user(**options)
    except auth.EmailAlreadyExistsError:
        return auth.get_user_by_email(email)


def connecter(email: str, nom, auth, db) -> str:
    """Renvoie un custom token Firebase pour cet e-mail (compte créé si besoin)."""
    utilisateur = _trouver_ou_creer(email, nom, auth)
    if utilisateur.disabled:
        raise ErreurApi(403, "Ce compte est désactivé.")

    # `create` échoue si le document existe déjà : on n'écrase jamais un profil.
    try:
        db.collection("utilisateurs").document(utilisateur.uid).create(
            {
                "nom": nom or utilisateur.display_name or "",
                "email": email,
                "emailNormalise": email,
                "telephone": "",
                "telephoneNormalise": "",
                "creeLe": firestore.SERVER_TIMESTAMP,
            }
        )
    except AlreadyExists:
        pass

    jeton = auth.create_custom_token(utilisateur.uid)
    return jeton.decode() if isinstance(jeton, bytes) else jeton
