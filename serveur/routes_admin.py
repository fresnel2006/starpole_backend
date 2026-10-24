from fastapi import APIRouter, Depends, Path
from firebase_admin import auth

from . import admin, firebase
from .modeles import FORMAT_ID, DemandeModeration
from .securite import administrateur_connecte

routeur = APIRouter(prefix="/admin", tags=["Administration"])


def identifiant():
    """Un paramètre de chemin par route (un objet Path partagé garde le premier nom)."""
    return Path(pattern=FORMAT_ID)


def obtenir_auth():
    return auth


@routeur.post("/alertes/{alerte_id}/supprimer")
def supprimer_alerte(
    corps: DemandeModeration,
    alerte_id: str = identifiant(),
    admin_id: str = Depends(administrateur_connecte),
    db=Depends(firebase.obtenir_db),
):
    return admin.supprimer_alerte(db, admin_id, alerte_id, corps.motif)


@routeur.post("/alertes/{alerte_id}/resoudre")
def resoudre_alerte(
    corps: DemandeModeration,
    alerte_id: str = identifiant(),
    admin_id: str = Depends(administrateur_connecte),
    db=Depends(firebase.obtenir_db),
):
    return admin.resoudre_alerte(db, admin_id, alerte_id, corps.motif)


@routeur.get("/utilisateurs/{uid}")
def etat_utilisateur(
    uid: str = identifiant(),
    _: str = Depends(administrateur_connecte),
    auth_=Depends(obtenir_auth),
):
    return admin.etat_compte(auth_, uid)


@routeur.post("/utilisateurs/{uid}/suspendre")
def suspendre_utilisateur(
    corps: DemandeModeration,
    uid: str = identifiant(),
    admin_id: str = Depends(administrateur_connecte),
    db=Depends(firebase.obtenir_db),
    auth_=Depends(obtenir_auth),
):
    return admin.suspendre_utilisateur(db, auth_, admin_id, uid, corps.motif)


@routeur.post("/utilisateurs/{uid}/reactiver")
def reactiver_utilisateur(
    corps: DemandeModeration,
    uid: str = identifiant(),
    admin_id: str = Depends(administrateur_connecte),
    db=Depends(firebase.obtenir_db),
    auth_=Depends(obtenir_auth),
):
    return admin.reactiver_utilisateur(db, auth_, admin_id, uid, corps.motif)
