from fastapi import APIRouter, Depends

from . import firebase, moderation, notifications
from .modeles import DemandeVerificationAlerte
from .securite import utilisateur_limite

routeur = APIRouter(prefix="/moderation", tags=["Modération"])


def obtenir_verificateur() -> moderation.VerificateurGemini:
    return moderation.VerificateurGemini()


def obtenir_messagerie() -> notifications.MessagerieFcm:
    return notifications.MessagerieFcm()


@routeur.post("/alerte")
def verifier_alerte(
    corps: DemandeVerificationAlerte,
    uid: str = Depends(utilisateur_limite),
    db=Depends(firebase.obtenir_db),
    messagerie=Depends(obtenir_messagerie),
    verificateur=Depends(obtenir_verificateur),
):
    """Vérifie par l'IA l'alerte que l'appelant vient de publier."""
    return moderation.moderer_alerte(db, messagerie, verificateur, uid, corps.alerteId)
