"""Vérification des alertes par l'IA (Gemini), en arrière-plan.

L'alerte est publiée tout de suite par l'appli. Juste après, l'appli demande
au serveur de la vérifier : si l'IA la juge non conforme (argent, contenu
sexuel, arnaque, haine...), elle est supprimée, l'action est inscrite dans le
journal d'administration et l'auteur reçoit une notification qui explique
pourquoi. Si l'IA ne répond pas, l'alerte reste en ligne, marquée
« non_verifiee », pour qu'un administrateur la regarde.
"""
import json
import logging
import urllib.error
import urllib.request

from . import config
from .codes import maintenant
from .erreurs import ErreurApi
from .notifications import _notifier, tronquer

logger = logging.getLogger("starpole")

JOURNAL = "journal_admin"
DELAI_SECONDES = 25

CONSIGNE = """Tu es le modérateur de StarPole, une application d'entraide de quartier à Abidjan (Côte d'Ivoire).
Les habitants publient des alertes : urgences (malaise, accident, incendie, vol, sécurité), demandes de service (coup de main, objet perdu, aide) et dons (vêtements, nourriture, meubles...).
Décide si l'alerte (titre, description et photo éventuelle) peut rester publiée.

REFUSE si :
- demande d'argent, de transfert ou de recharge (Wave, Orange Money, MTN MoMo, Moov, carte bancaire, « envoyez-moi », numéro pour paiement), sauf don d'objets ou de nourriture ;
- contenu sexuel, recherche de partenaire ou de relation intime, prostitution, propos ou photo suggestifs ou nus ;
- arnaque, publicité, vente commerciale, promotion, jeu d'argent, lien suspect ;
- insultes, harcèlement, haine, menace, appel à la violence, photo choquante ou sanglante sans rapport avec une urgence réelle ;
- accusation nominative ou informations personnelles d'un tiers (adresse privée de quelqu'un d'autre) ;
- texte sans rapport avec l'entraide de quartier, ou sans sens (spam, test, lettres au hasard) ;
- photo sans rapport avec l'alerte ou inappropriée.
ACCEPTE les vraies urgences, demandes d'aide, objets perdus ou trouvés et dons, même écrits simplement, avec des fautes ou en nouchi. En cas de doute sur une urgence, ACCEPTE.

Réponds uniquement en JSON : {"acceptable": true ou false, "categorie": "ok|argent|sexuel|arnaque|haine|vie_privee|hors_sujet|image", "raison": "explication courte en français, polie, adressée à l'auteur, sans tiret long"}"""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "acceptable": {"type": "BOOLEAN"},
        "categorie": {"type": "STRING"},
        "raison": {"type": "STRING"},
    },
    "required": ["acceptable", "categorie", "raison"],
}


class ModerationIndisponible(Exception):
    """L'IA n'a pas pu répondre (réseau, délai, quota, réponse illisible)."""


class VerificateurGemini:
    """Interroge Gemini. La clé vient de la variable GEMINI_CLE_API."""

    def verifier(self, type_alerte: str, titre: str, description: str, photo_b64=None) -> dict:
        parts = [{"text": f"Type : {type_alerte}\nTitre : {titre}\nDescription : {description}"}]
        if photo_b64:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": photo_b64}})
        corps = {
            "system_instruction": {"parts": [{"text": CONSIGNE}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }
        adresse = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{config.modele_gemini()}:generateContent"
        )
        requete = urllib.request.Request(
            adresse,
            data=json.dumps(corps).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-goog-api-key": config.cle_gemini()},
        )
        try:
            with urllib.request.urlopen(requete, timeout=DELAI_SECONDES) as reponse:
                donnees = json.load(reponse)
            if not donnees.get("candidates"):
                # Google a bloqué le contenu lui-même : il est clairement interdit.
                blocage = (donnees.get("promptFeedback") or {}).get("blockReason")
                if blocage:
                    return {
                        "acceptable": False,
                        "categorie": "interdit",
                        "raison": "Ce contenu n'est pas autorisé sur StarPole.",
                    }
            texte = donnees["candidates"][0]["content"]["parts"][0]["text"]
            verdict = json.loads(texte)
        except urllib.error.HTTPError as e:
            # Jamais la clé dans les journaux : seulement le code HTTP.
            raise ModerationIndisponible(f"HTTP {e.code}") from None
        except Exception as e:  # réseau, délai, réponse inattendue
            raise ModerationIndisponible(type(e).__name__) from None
        if not isinstance(verdict.get("acceptable"), bool):
            raise ModerationIndisponible("réponse sans décision")
        return {
            "acceptable": verdict["acceptable"],
            "categorie": str(verdict.get("categorie") or ""),
            "raison": str(verdict.get("raison") or "").replace("—", "-").strip(),
        }


def moderer_alerte(db, messagerie, verificateur, uid: str, alerte_id: str) -> dict:
    """Vérifie une alerte que l'appelant vient de publier."""
    ref = db.collection("alertes").document(alerte_id)
    instantane = ref.get()
    if not instantane.exists:
        return {"etat": "absente"}
    alerte = instantane.to_dict() or {}
    if alerte.get("auteurId") != uid:
        raise ErreurApi(403, "Vous n'êtes pas l'auteur de cette alerte.")
    if alerte.get("moderation") in ("ok", "non_verifiee"):
        return {"etat": "deja_verifiee"}

    titre = str(alerte.get("categorie") or "")
    try:
        verdict = verificateur.verifier(
            str(alerte.get("type") or ""),
            titre,
            str(alerte.get("description") or ""),
            alerte.get("photo") or None,
        )
    except ModerationIndisponible as e:
        # L'IA ne répond pas : on ne bloque pas une alerte peut-être urgente.
        logger.warning("Modération indisponible pour %s : %s", alerte_id, e)
        ref.update({"moderation": "non_verifiee"})
        return {"etat": "non_verifiee"}

    if verdict["acceptable"]:
        ref.update({"moderation": "ok"})
        return {"etat": "acceptee"}

    raison = verdict["raison"] or "Cette alerte ne respecte pas les règles de StarPole."
    progression = ref.collection("progression")
    for message in progression.stream():
        progression.document(message.id).delete()
    ref.delete()
    db.collection(JOURNAL).add(
        {
            "adminId": "moderation_ia",
            "action": "supprimer_alerte",
            "cible": f"alertes/{alerte_id}",
            "date": maintenant(),
            "motif": f"{verdict['categorie']} : {raison}",
            "auteurId": uid,
            "titre": titre,
        }
    )
    _notifier(
        db,
        messagerie,
        [uid],
        {"type": "moderation", "alerteId": alerte_id, "raison": tronquer(raison, 200)},
        notification=(
            "Alerte retirée",
            tronquer(f"« {titre} » a été retirée : {raison}", 200),
        ),
    )
    return {"etat": "supprimee", "categorie": verdict["categorie"], "raison": raison}
