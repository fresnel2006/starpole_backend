from fastapi import APIRouter, Depends
from firebase_admin import auth

from . import codes, comptes, config, courriel, firebase
from .modeles import DemandeCode, VerificationCode

routeur = APIRouter(prefix="/auth", tags=["Connexion"])


@routeur.post("/demander-code")
def demander_code(corps: DemandeCode, depot=Depends(firebase.obtenir_depot)):
    codes.demander_code(depot, corps.email, config.secret_codes(), courriel.envoyer_code)
    # Réponse identique, que le compte existe ou non.
    return {"message": "Si l'adresse est valide, un code de connexion vient de lui être envoyé."}


@routeur.post("/verifier-code")
def verifier_code(corps: VerificationCode, depot=Depends(firebase.obtenir_depot)):
    codes.verifier_code(depot, corps.email, corps.code, config.secret_codes())
    jeton = comptes.connecter(corps.email, corps.nom, auth, firebase.obtenir_db())
    return {"jetonPersonnalise": jeton}
