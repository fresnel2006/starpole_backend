from fastapi import APIRouter, Depends

from . import firebase, notifications
from .modeles import DemandeAlerte, DemandeAppel, DemandeMessage
from .securite import utilisateur_limite

routeur = APIRouter(prefix="/notifications", tags=["Notifications"])


def obtenir_messagerie() -> notifications.MessagerieFcm:
    return notifications.MessagerieFcm()


@routeur.post("/appel")
def appel(
    corps: DemandeAppel,
    uid: str = Depends(utilisateur_limite),
    db=Depends(firebase.obtenir_db),
    messagerie=Depends(obtenir_messagerie),
):
    return notifications.notifier_appel(db, messagerie, uid, corps.appelId)


@routeur.post("/message")
def message(
    corps: DemandeMessage,
    uid: str = Depends(utilisateur_limite),
    db=Depends(firebase.obtenir_db),
    messagerie=Depends(obtenir_messagerie),
):
    return notifications.notifier_message(db, messagerie, uid, corps.conversationId)


@routeur.post("/alerte")
def alerte(
    corps: DemandeAlerte,
    uid: str = Depends(utilisateur_limite),
    db=Depends(firebase.obtenir_db),
    messagerie=Depends(obtenir_messagerie),
):
    return notifications.notifier_alerte(db, messagerie, uid, corps.alerteId, corps.rayonMetres)
