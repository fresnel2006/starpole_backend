import logging
import smtplib
import ssl
from email.message import EmailMessage

from . import config
from .erreurs import ErreurApi

logger = logging.getLogger("starpole")

DELAI_SMTP_SECONDES = 10


def envoyer_code(destinataire: str, code: str) -> None:
    reglages = config.smtp()

    message = EmailMessage()
    message["Subject"] = "Votre code StarPole"
    message["From"] = reglages["expediteur"]
    message["To"] = destinataire
    message.set_content(
        "Bonjour,\n\n"
        f"Votre code de connexion StarPole est : {code}\n\n"
        "Il est valable 10 minutes et ne peut être utilisé qu'une seule fois.\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez simplement cet e-mail.\n\n"
        "L'équipe StarPole\n"
    )

    try:
        contexte = ssl.create_default_context()
        if reglages["port"] == 465:
            connexion = smtplib.SMTP_SSL(
                reglages["hote"], reglages["port"], timeout=DELAI_SMTP_SECONDES, context=contexte
            )
        else:
            connexion = smtplib.SMTP(reglages["hote"], reglages["port"], timeout=DELAI_SMTP_SECONDES)
        with connexion:
            if reglages["port"] != 465:
                connexion.starttls(context=contexte)
            connexion.login(reglages["utilisateur"], reglages["mot_de_passe"])
            connexion.send_message(message)
    except Exception as e:
        logger.error("Échec de l'envoi de l'e-mail : %s", type(e).__name__)
        raise ErreurApi(503, "Impossible d'envoyer l'e-mail pour le moment. Réessayez plus tard.")
