"""Actions de modération de la console d'administration.

Chaque action réussie est enregistrée dans la collection `journal_admin`.
"""
from .codes import maintenant
from .erreurs import ErreurApi

JOURNAL = "journal_admin"


def _journaliser(db, admin_id: str, action: str, cible: str, motif: str) -> None:
    db.collection(JOURNAL).add(
        {"adminId": admin_id, "action": action, "cible": cible, "date": maintenant(), "motif": motif}
    )


def _alerte(db, alerte_id: str):
    ref = db.collection("alertes").document(alerte_id)
    instantane = ref.get()
    if not instantane.exists:
        raise ErreurApi(404, "Alerte introuvable.")
    return ref, instantane.to_dict()


def supprimer_alerte(db, admin_id: str, alerte_id: str, motif: str) -> dict:
    """Supprime l'alerte et sa sous-collection `progression`."""
    ref, _ = _alerte(db, alerte_id)
    progression = ref.collection("progression")
    for message in progression.stream():
        progression.document(message.id).delete()
    ref.delete()
    _journaliser(db, admin_id, "supprimer_alerte", f"alertes/{alerte_id}", motif)
    return {"ok": True}


def resoudre_alerte(db, admin_id: str, alerte_id: str, motif: str) -> dict:
    ref, donnees = _alerte(db, alerte_id)
    if donnees.get("statut") == "resolue":
        raise ErreurApi(409, "Cette alerte est déjà résolue.")
    ref.update({"statut": "resolue", "termineLe": maintenant()})
    _journaliser(db, admin_id, "resoudre_alerte", f"alertes/{alerte_id}", motif)
    return {"ok": True}


def _modifier_compte(auth, uid: str, desactive: bool) -> None:
    try:
        auth.update_user(uid, disabled=desactive)
    except auth.UserNotFoundError:
        raise ErreurApi(404, "Utilisateur introuvable.")


def suspendre_utilisateur(db, auth, admin_id: str, uid: str, motif: str) -> dict:
    """Désactive le compte Firebase Auth et révoque ses jetons."""
    if uid == admin_id:
        raise ErreurApi(400, "Vous ne pouvez pas suspendre votre propre compte.")
    _modifier_compte(auth, uid, True)
    auth.revoke_refresh_tokens(uid)
    _journaliser(db, admin_id, "suspendre_utilisateur", f"utilisateurs/{uid}", motif)
    return {"ok": True}


def reactiver_utilisateur(db, auth, admin_id: str, uid: str, motif: str) -> dict:
    _modifier_compte(auth, uid, False)
    _journaliser(db, admin_id, "reactiver_utilisateur", f"utilisateurs/{uid}", motif)
    return {"ok": True}


def etat_compte(auth, uid: str) -> dict:
    """État du compte Firebase Auth (lecture seule, non journalisée)."""
    try:
        utilisateur = auth.get_user(uid)
    except auth.UserNotFoundError:
        raise ErreurApi(404, "Utilisateur introuvable.")
    return {
        "suspendu": bool(utilisateur.disabled),
        "admin": bool((utilisateur.custom_claims or {}).get("admin")),
    }
