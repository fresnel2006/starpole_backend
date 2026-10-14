import logging
import math
from typing import Optional

from firebase_admin import messaging
from google.cloud.firestore_v1.base_query import FieldFilter

from .erreurs import ErreurApi

logger = logging.getLogger("starpole")

TAILLE_LOT_FCM = 500
LONGUEUR_MAX_MESSAGE = 100
METRES_PAR_DEGRE = 111_320


class MessagerieFcm:
    """Envoi FCM. `envoyer` renvoie la liste des jetons devenus invalides."""

    def envoyer(
        self,
        jetons: list,
        donnees: dict,
        notification: Optional[tuple] = None,
        haute_priorite: bool = False,
    ) -> list:
        invalides = []
        for debut in range(0, len(jetons), TAILLE_LOT_FCM):
            lot = jetons[debut : debut + TAILLE_LOT_FCM]
            message = messaging.MulticastMessage(
                tokens=lot,
                data=donnees,
                notification=messaging.Notification(title=notification[0], body=notification[1])
                if notification
                else None,
                android=messaging.AndroidConfig(priority="high" if haute_priorite else "normal"),
                # Message "data" seul sur iOS : Apple impose la priorité 5 avec content-available.
                apns=messaging.APNSConfig(
                    headers={"apns-priority": "5"},
                    payload=messaging.APNSPayload(aps=messaging.Aps(content_available=True)),
                )
                if haute_priorite and not notification
                else None,
            )
            try:
                reponse = messaging.send_each_for_multicast(message)
            except Exception as e:
                logger.error("Échec de l'envoi FCM : %s", type(e).__name__)
                raise ErreurApi(502, "Échec de l'envoi des notifications. Réessayez plus tard.")
            for jeton, resultat in zip(lot, reponse.responses):
                if not resultat.success and isinstance(
                    resultat.exception, (messaging.UnregisteredError, messaging.SenderIdMismatchError)
                ):
                    invalides.append(jeton)
        return invalides


def distance_metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance haversine."""
    rayon_terre = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * rayon_terre * math.asin(min(1.0, math.sqrt(a)))


def tronquer(texte: str, longueur: int = LONGUEUR_MAX_MESSAGE) -> str:
    texte = (texte or "").strip()
    if len(texte) <= longueur:
        return texte
    return texte[: longueur - 1].rstrip() + "…"


def _texte(valeur) -> str:
    return "" if valeur is None else str(valeur)


def _nombre(valeur) -> Optional[float]:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    return float(valeur)


def _lire(db, collection: str, doc_id: str, nom: str) -> dict:
    instantane = db.collection(collection).document(doc_id).get()
    if not instantane.exists:
        raise ErreurApi(404, f"{nom} introuvable.")
    return instantane.to_dict() or {}


def _appareils(db, uid: str) -> list:
    return [d.id for d in db.collection("utilisateurs").document(uid).collection("appareils").stream()]


def _notifier(db, messagerie, destinataires: list, donnees: dict, notification=None, haute_priorite=False) -> dict:
    """Envoie à tous les appareils des destinataires et supprime les jetons invalides."""
    cibles = [(uid, jeton) for uid in destinataires for jeton in _appareils(db, uid)]
    if not cibles:
        return {"envoyes": 0, "jetonsSupprimes": 0}

    invalides = set(
        messagerie.envoyer(
            [jeton for _, jeton in cibles],
            donnees,
            notification=notification,
            haute_priorite=haute_priorite,
        )
    )
    supprimes = 0
    for uid, jeton in cibles:
        if jeton in invalides:
            db.collection("utilisateurs").document(uid).collection("appareils").document(jeton).delete()
            supprimes += 1
    if supprimes:
        logger.info("%d jeton(s) invalide(s) supprimé(s)", supprimes)
    return {"envoyes": len(cibles) - supprimes, "jetonsSupprimes": supprimes}


def notifier_appel(db, messagerie, uid: str, appel_id: str) -> dict:
    appel = _lire(db, "appels", appel_id, "Appel")
    if appel.get("appelantId") != uid:
        raise ErreurApi(403, "Vous n'êtes pas l'appelant de cet appel.")
    if appel.get("statut") != "sonne":
        raise ErreurApi(400, "Cet appel ne sonne plus.")
    appele_id = appel.get("appeleId")
    if not appele_id or not isinstance(appele_id, str):
        raise ErreurApi(400, "Appel incomplet : personne appelée manquante.")

    donnees = {
        "type": "appel",
        "appelId": appel_id,
        "appelantId": uid,
        "appelantNom": _texte(appel.get("appelantNom")),
        "video": "true" if appel.get("video") else "false",
    }
    return _notifier(db, messagerie, [appele_id], donnees, haute_priorite=True)


def notifier_message(db, messagerie, uid: str, conversation_id: str) -> dict:
    conversation = _lire(db, "conversations", conversation_id, "Conversation")
    participants = conversation.get("participants") or []
    if uid not in participants:
        raise ErreurApi(403, "Vous ne participez pas à cette conversation.")
    if conversation.get("dernierAuteurId") != uid:
        raise ErreurApi(403, "Vous n'êtes pas l'auteur du dernier message.")

    noms = conversation.get("noms") or {}
    titre = _texte(noms.get(uid)) or "Nouveau message"
    texte = tronquer(_texte(conversation.get("dernierMessage")))
    donnees = {"type": "message", "conversationId": conversation_id, "expediteurId": uid}
    destinataires = [p for p in participants if p != uid]
    return _notifier(db, messagerie, destinataires, donnees, notification=(titre, texte))


def notifier_alerte(db, messagerie, uid: str, alerte_id: str, rayon_metres: float) -> dict:
    alerte = _lire(db, "alertes", alerte_id, "Alerte")
    if alerte.get("auteurId") != uid:
        raise ErreurApi(403, "Vous n'êtes pas l'auteur de cette alerte.")
    latitude, longitude = _nombre(alerte.get("latitude")), _nombre(alerte.get("longitude"))
    if latitude is None or longitude is None or abs(latitude) > 90 or abs(longitude) > 180:
        raise ErreurApi(400, "Alerte incomplète : position invalide.")

    # Pré-filtre sur la latitude (un seul champ, sans index composite), puis distance exacte.
    ecart = rayon_metres / METRES_PAR_DEGRE
    candidats = (
        db.collection("utilisateurs")
        .where(filter=FieldFilter("position.latitude", ">=", latitude - ecart))
        .where(filter=FieldFilter("position.latitude", "<=", latitude + ecart))
        .stream()
    )
    proches = []
    for candidat in candidats:
        if candidat.id == uid:
            continue
        position = (candidat.to_dict() or {}).get("position") or {}
        lat, lon = _nombre(position.get("latitude")), _nombre(position.get("longitude"))
        if lat is None or lon is None:
            continue
        if distance_metres(latitude, longitude, lat, lon) <= rayon_metres:
            proches.append(candidat.id)

    categorie = _texte(alerte.get("categorie"))
    donnees = {
        "type": "alerte",
        "alerteId": alerte_id,
        "auteurId": uid,
        "auteurNom": _texte(alerte.get("auteurNom")),
        "categorie": categorie,
        "latitude": str(latitude),
        "longitude": str(longitude),
    }
    titre = f"Alerte : {categorie}" if categorie else "Alerte près de vous"
    texte = tronquer(_texte(alerte.get("description"))) or "Une alerte a été signalée près de vous."
    resultat = _notifier(db, messagerie, proches, donnees, notification=(titre, texte))
    resultat["utilisateursProches"] = len(proches)
    return resultat
